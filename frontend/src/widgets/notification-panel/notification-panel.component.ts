import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  output,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';
import { NotificationsService } from '@entities/notification/notifications.service';
import {
  AppNotification,
  RULE_TYPE_LABELS,
} from '@entities/notification/notification.model';
import {
  SolNotificationItem,
  SolNotificationPanelComponent,
  SolNotificationTone,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';

/**
 * Carga opaca que viaja en `SolNotificationItem.data`. La librería nunca la
 * lee: solo la devuelve intacta en `itemSelected`/`markedRead`, y es lo único
 * que este contenedor necesita para decidir a dónde navega cada notificación.
 * Así el panel de `@solercia/ui` no conoce `target_type` ni `target_id`.
 */
interface NotificationTarget {
  readonly targetType: string;
  readonly targetId: string | null;
}

/** Notificación ya mapeada al tipo genérico de la librería. */
type NotificationRow = SolNotificationItem<NotificationTarget>;

/**
 * Tono del `sol-badge` por tipo de regla. Vive aquí (y no en `@entities`)
 * porque es una decisión de presentación del panel, no del dominio: la
 * entidad solo aporta el texto de la etiqueta (`RULE_TYPE_LABELS`).
 */
const RULE_TYPE_TONES: Record<string, SolNotificationTone> = {
  task_overdue: 'danger',
  task_at_risk: 'warning',
  sprint_at_risk: 'warning',
  license_expiring: 'warning',
  license_expired: 'danger',
  workload_imbalance: 'info',
  blocked_task: 'danger',
};

/**
 * Contenedor del centro de notificaciones: trae los datos, los mapea al tipo
 * genérico de la librería y reacciona a los eventos del panel.
 *
 * La presentación (encabezado, contador de no leídas, estados, filas y
 * acciones) la resuelve `SolNotificationPanelComponent` de `@solercia/ui`.
 * Aquí se queda todo lo que NO es presentación: `NotificationsService`, el
 * `Router` y la resolución UUID → `task_key` para navegar a la tarea.
 *
 * El selector es `sol-notification-center` —y no `sol-notification-panel`—
 * porque ese último es el del componente de la librería que este contenedor
 * monta: dos componentes con el mismo selector en el mismo ámbito harían que
 * la plantilla se resolviera contra sí misma.
 *
 * Mejora que aporta la librería: el estado de error deja de confundirse con
 * el vacío. Antes, una carga fallida mostraba "no tienes notificaciones"
 * (deuda registrada en la auditoría `2026-07-19-13-ui-component-audit`);
 * ahora el fallo se pinta como error, con el mensaje real y un reintento.
 */
@Component({
  selector: 'sol-notification-center',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SolNotificationPanelComponent],
  // El panel de la librería ocupa el 100 % del ancho disponible, así que el
  // ancho del desplegable lo fija el contenedor (mismo que el markup previo).
  host: { class: 'block w-80 sm:w-96' },
  template: `
    <sol-notification-panel
      [items]="items()"
      [loading]="loading()"
      [error]="failed()"
      [errorMessage]="errorMessage()"
      (itemSelected)="openNotification($event)"
      (markedRead)="markRead($event)"
      (markedAllRead)="markAllRead()"
      (retryRequested)="load()"
      (closed)="closed.emit()"
    />
  `,
})
export class NotificationPanelComponent implements OnInit {
  private readonly notifService = inject(NotificationsService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);

  /** Se emite cuando el panel debe cerrarse (cierre explícito o navegación). */
  readonly closed = output<void>();

  /** Notificaciones activas tal como las devuelve el backend. */
  private readonly notifications = signal<AppNotification[]>([]);

  protected readonly loading = signal(false);
  protected readonly failed = signal(false);
  /** Detalle del error ya resuelto a texto; vacío cuando no hay error. */
  protected readonly errorMessage = signal('');

  /**
   * `AppNotification` → `SolNotificationItem`: la etiqueta de tipo llega ya
   * resuelta a texto en `typeLabel` (con su `tone`), y lo necesario para
   * enrutar viaja opaco en `data`.
   *
   * La lista es la de notificaciones activas, así que ninguna está leída:
   * `read: false` es un hecho del filtro, no una suposición.
   */
  protected readonly items = computed<readonly NotificationRow[]>(() =>
    this.notifications().map((notification) => ({
      id: notification.id,
      title: notification.title,
      body: notification.body,
      timestamp: notification.created_at,
      read: false,
      typeLabel: RULE_TYPE_LABELS[notification.rule_type] ?? notification.rule_type,
      tone: RULE_TYPE_TONES[notification.rule_type] ?? 'neutral',
      data: {
        targetType: notification.target_type,
        targetId: notification.target_id,
      },
    })),
  );

  ngOnInit(): void {
    this.load();
  }

  /** Carga (o recarga, desde `retryRequested`) las notificaciones activas. */
  protected load(): void {
    this.loading.set(true);
    this.failed.set(false);
    this.errorMessage.set('');
    this.notifService.list('active').subscribe({
      next: (res) => {
        this.notifications.set(res.data);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        // La lista queda vacía, pero el panel debe decir "no pudimos saberlo"
        // y no "no tienes notificaciones".
        this.notifications.set([]);
        this.failed.set(true);
        this.errorMessage.set(this.messageFor(err));
      },
    });
  }

  protected markRead(item: NotificationRow): void {
    this.notifService.updateStatus(String(item.id), 'read').subscribe({
      next: () =>
        this.notifications.update((list) =>
          list.filter((notification) => notification.id !== item.id),
        ),
    });
  }

  protected markAllRead(): void {
    const active = this.notifications();
    if (active.length === 0) return;
    this.notifService.markAllRead(active).subscribe({
      next: () => this.notifications.set([]),
    });
  }

  /**
   * Notificación activada. Para `target_type='task'` resuelve el `task_key`
   * a partir del UUID y navega a `/task/{task_key}`; si no hay clave (o la
   * notificación no apunta a una tarea) no hace nada, igual que antes.
   */
  protected openNotification(item: NotificationRow): void {
    const target = item.data;
    if (!target || target.targetType !== 'task' || !target.targetId) return;

    this.notifService.resolveTaskKey(target.targetId).subscribe({
      next: (res) => {
        const key = res.data.task_key;
        if (key) {
          void this.router.navigate(['/task', key]);
          this.closed.emit();
        }
      },
      error: () => {
        // Tarea inexistente o sin task_key: se ignora en silencio.
      },
    });
  }

  /** Traduce el fallo HTTP al texto que el panel muestra bajo el error. */
  private messageFor(err: HttpErrorResponse): string {
    return err.status === 0
      ? this.i18n.translate('notificationPanel.errors.network')
      : this.i18n.translate('notificationPanel.errors.load');
  }
}
