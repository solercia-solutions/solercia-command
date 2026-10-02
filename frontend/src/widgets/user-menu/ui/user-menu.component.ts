import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  Injector,
  afterNextRender,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { I18nService } from '@shared/i18n';
import { SolAvatarComponent, SolIconComponent } from '@shared/ui';

let nextMenuId = 0;

/** Una entrada del menú de usuario: navega (`route`) o se reporta por `action` (sin `route`). */
export interface UserMenuAction {
  readonly id: string;
  readonly label: string;
  readonly route?: string;
}

/** Nombres en dos líneas, SIEMPRE desde campos explícitos del perfil (nunca partiendo un nombre). */
export interface UserMenuNameLines {
  readonly given: string;
  readonly family: string;
}

/**
 * Menú de usuario del encabezado: disparador (avatar + nombre en una o dos líneas + chevron) que
 * abre un panel (patrón «menu button» de WAI-ARIA, sin CDK: la regla de ESLint reserva
 * `@angular/cdk` a la librería) con la cabecera (avatar, nombre, insignia y subtítulo), un reloj de
 * soporte opcional, las acciones que defina la página y «Cerrar sesión».
 *
 * Presentacional: no conoce la sesión ni las rutas. Quien lo monta pasa los datos del usuario y
 * las acciones; recibe `action` (id de una entrada sin ruta) y `logout`.
 *
 * El reloj de soporte deja claro que es la hora del NAVEGADOR en la zona indicada (no la del
 * servidor): sirve para que la persona reporte a soporte el instante exacto de un problema. Solo
 * corre mientras el panel está abierto.
 *
 * Teclado: Enter/Espacio o flecha abajo abren y enfocan la primera entrada; flechas recorren,
 * Inicio/Fin saltan, Escape cierra y devuelve el foco al disparador; un clic fuera cierra.
 */
@Component({
  standalone: true,
  selector: 'sol-user-menu',
  imports: [RouterLink, SolAvatarComponent, SolIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'sol-user-menu',
    '(document:click)': 'onDocumentClick($event)',
    '(keydown)': 'onKeydown($event)',
  },
  template: `
    <button
      #trigger
      type="button"
      class="sol-user-menu__trigger"
      aria-haspopup="menu"
      [attr.aria-expanded]="open()"
      [attr.aria-controls]="panelId"
      [attr.aria-label]="triggerLabel()"
      [title]="displayName()"
      (click)="toggle()"
    >
      <sol-avatar [name]="displayName()" size="sm" />
      <span class="sol-user-menu__name">
        <span class="sol-user-menu__name-line" data-testid="user-given-names">{{ nameLines()?.given || displayName() }}</span>
        @if (nameLines()?.family) {
          <span class="sol-user-menu__name-line" data-testid="user-family-names">{{ nameLines()?.family }}</span>
        }
      </span>
      <sol-icon class="sol-user-menu__chevron" name="chevron-down" size="sm" />
    </button>

    @if (open()) {
      <div class="sol-user-menu__panel" role="menu" [id]="panelId" [attr.aria-label]="triggerLabel()">
        <div class="sol-user-menu__header">
          <sol-avatar [name]="displayName()" size="md" />
          <div class="sol-user-menu__header-info">
            <div class="sol-user-menu__header-top">
              <span class="sol-user-menu__header-name">{{ displayName() }}</span>
              @if (badge(); as text) {
                <span class="sol-user-menu__badge">{{ text }}</span>
              }
            </div>
            @if (subtitle(); as text) {
              <span class="sol-user-menu__header-sub">{{ text }}</span>
            }
          </div>
        </div>

        @if (supportTimeZone(); as zone) {
          <section class="sol-user-menu__support-time" [attr.aria-label]="supportTimeTitle()">
            <span>{{ supportTimeTitle() }}</span>
            <time data-testid="user-support-clock" [attr.datetime]="supportInstant().toISOString()">{{ supportTime() }}</time>
            <span>{{ supportTimeNote() }}</span>
          </section>
        }

        <div class="sol-user-menu__separator" role="separator"></div>

        @for (entry of actions(); track entry.id) {
          @if (entry.route) {
            <!-- Enlace real (no botón + navigate) para conservar ctrl/cmd-clic en otra pestaña. -->
            <a
              [routerLink]="entry.route"
              role="menuitem"
              class="sol-user-menu__item"
              [attr.data-testid]="'user-menu-' + entry.id"
              (click)="close(false)"
            >
              {{ entry.label }}
            </a>
          } @else {
            <button
              type="button"
              role="menuitem"
              class="sol-user-menu__item"
              [attr.data-testid]="'user-menu-' + entry.id"
              (click)="choose(entry.id)"
            >
              {{ entry.label }}
            </button>
          }
        }

        <button
          type="button"
          role="menuitem"
          class="sol-user-menu__item sol-user-menu__item--logout"
          data-testid="user-menu-logout"
          (click)="chooseLogout()"
        >
          {{ logoutLabel() }}
        </button>
      </div>
    }
  `,
  styles: [`
    :host {
      position: relative;
      display: inline-flex;
    }

    .sol-user-menu__trigger {
      display: inline-flex;
      align-items: center;
      gap: var(--sol-space-sm, 8px);
      max-width: 220px;
      height: var(--sol-size-component-md, 36px);
      padding: 0 var(--sol-space-sm, 8px);
      border: none;
      border-radius: var(--sol-border-radius-md, 8px);
      background: transparent;
      color: var(--sol-color-text-primary, #111827);
      font-family: var(--sol-font-family);
      cursor: pointer;
      transition: background-color 0.15s ease, color 0.15s ease;
    }

    .sol-user-menu__trigger:hover,
    .sol-user-menu__trigger[aria-expanded="true"] {
      background: color-mix(in srgb, var(--sol-color-primary, #2563eb) 10%, transparent);
      color: var(--sol-color-primary, #2563eb);
    }

    .sol-user-menu__name {
      display: flex;
      flex-direction: column;
      min-width: 0;
      text-align: left;
      line-height: 1.2;
      max-width: 10rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: var(--sol-font-size-sm, 0.875rem);
      font-weight: var(--sol-font-weight-bold, 600);
    }

    .sol-user-menu__name-line {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .sol-user-menu__support-time {
      display: flex;
      flex-direction: column;
      gap: var(--sol-space-xs, 4px);
      padding: var(--sol-space-sm, 8px) var(--sol-space-md, 16px);
      color: var(--sol-color-text-secondary);
      font-size: var(--sol-font-size-sm, 12px);
      overflow-wrap: anywhere;
    }

    .sol-user-menu__chevron {
      flex-shrink: 0;
    }

    /* Objetivo táctil bajo el breakpoint canónico (ley de Fitts, 44 px). Crece la caja del propio
       <button> — el elemento que abre el menú —, no un envoltorio: el alto fijo cede a auto para
       que min-height mande. Aditivo: escritorio conserva su densidad. */
    @media (max-width: 767px) {
      .sol-user-menu__trigger {
        height: auto;
        min-height: var(--sol-size-control-touch, 44px);
      }
    }

    /* ── Panel ─────────────────────────────────────────────────────────── */
    .sol-user-menu__panel {
      position: absolute;
      top: calc(100% + var(--sol-space-xs, 4px));
      right: 0;
      z-index: var(--sol-z-dropdown, 100);
      width: 288px;
      max-width: calc(100vw - 2 * var(--sol-space-md, 16px));
      overflow: hidden;
      background: var(--sol-card-bg, var(--sol-bg-surface));
      border: var(--sol-card-border, 1px solid transparent);
      border-radius: var(--sol-card-radius, var(--sol-border-radius-lg));
      box-shadow: var(--sol-shadow-lg);
    }

    .sol-user-menu__header {
      display: flex;
      align-items: center;
      gap: var(--sol-space-sm, 8px);
      padding: var(--sol-space-md, 16px);
    }

    .sol-user-menu__header-info {
      min-width: 0;
      flex: 1 1 auto;
    }

    .sol-user-menu__header-top {
      display: flex;
      align-items: center;
      gap: var(--sol-space-xs, 4px);
      flex-wrap: wrap;
    }

    .sol-user-menu__header-name {
      max-width: 10rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--sol-color-text-primary);
      font-size: var(--sol-font-size-sm, 0.875rem);
      font-weight: var(--sol-font-weight-bold, 600);
    }

    .sol-user-menu__badge {
      flex-shrink: 0;
      padding: 2px 8px;
      border-radius: var(--sol-border-radius-full, 9999px);
      background: var(--sol-color-primary);
      color: var(--sol-color-primary-contrast, #fff);
      font-size: 10px;
      font-weight: var(--sol-font-weight-bold, 600);
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }

    .sol-user-menu__header-sub {
      display: block;
      overflow: hidden;
      margin-top: 2px;
      color: var(--sol-color-text-muted);
      font-size: var(--sol-font-size-sm, 0.75rem);
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .sol-user-menu__separator {
      height: 1px;
      margin: 0;
      border: none;
      background: var(--sol-border-color-default, #e2e8f0);
    }

    .sol-user-menu__item {
      display: flex;
      width: 100%;
      align-items: center;
      justify-content: space-between;
      gap: var(--sol-space-sm, 8px);
      padding: var(--sol-space-sm, 8px) var(--sol-space-md, 16px);
      border: none;
      background: transparent;
      color: var(--sol-color-text-primary);
      font-family: var(--sol-font-family);
      font-size: var(--sol-font-size-sm, 0.875rem);
      text-align: left;
      cursor: pointer;
      transition: background-color 0.15s ease;
    }

    .sol-user-menu__item:hover,
    .sol-user-menu__item:focus-visible {
      outline: none;
      background: color-mix(in srgb, var(--sol-color-primary) 8%, transparent);
    }

    .sol-user-menu__item--logout {
      color: var(--sol-color-danger, #ef4444);
    }

    .sol-user-menu__item--logout:hover {
      background: color-mix(in srgb, var(--sol-color-danger, #ef4444) 10%, transparent);
    }

    /* Header móvil: el nombre cede espacio al resto de acciones del encabezado. */
    @media (max-width: 767px) {
      .sol-user-menu__name {
        display: none;
      }
    }
  `],
})
export class SolUserMenuComponent {
  private readonly i18n = inject(I18nService);
  private readonly injector = inject(Injector);

  /** Nombre completo a mostrar (nunca un documento de identidad si hay nombre). */
  readonly displayName = input.required<string>();

  /** Nombres y apellidos en dos líneas; sin valor, el disparador muestra `displayName`. */
  readonly nameLines = input<UserMenuNameLines | null>(null);

  /** Segunda línea de la cabecera del panel (p. ej. el correo). */
  readonly subtitle = input<string | null>(null);

  /** Insignia junto al nombre (p. ej. el rol o la empresa activa). */
  readonly badge = input<string | null>(null);

  /** Entradas del menú, en orden, antes de «Cerrar sesión». */
  readonly actions = input<readonly UserMenuAction[]>([]);

  /** Zona IANA del reloj de soporte (p. ej. `America/Bogota`); `null` lo oculta. */
  readonly supportTimeZone = input<string | null>(null);

  /** Se eligió una entrada sin `route`; lleva su `id`. */
  readonly action = output<string>();

  /** Se eligió «Cerrar sesión». */
  readonly logout = output<void>();

  protected readonly triggerLabel = this.i18n.t('widgets.userMenu.trigger');
  protected readonly logoutLabel = this.i18n.t('widgets.userMenu.logout');
  protected readonly supportTimeTitle = this.i18n.t('widgets.userMenu.supportTimeTitle');
  protected readonly supportTimeNote = computed(() =>
    this.i18n.translate('widgets.userMenu.supportTimeNote', { zone: this.supportTimeZone() ?? '' }),
  );

  protected readonly supportInstant = signal(new Date());
  protected readonly supportTime = computed(() => {
    const timeZone = this.supportTimeZone();
    if (!timeZone) return '';
    return new Intl.DateTimeFormat('es-CO', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    }).format(this.supportInstant());
  });

  /** Id estable del panel, para `aria-controls` (varios menús en una página no chocan). */
  protected readonly panelId = `sol-user-menu-${++nextMenuId}`;

  protected readonly open = signal(false);

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private clockTimer?: ReturnType<typeof setInterval>;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.stopSupportClock());
  }

  protected toggle(): void {
    if (this.open()) {
      this.close(true);
    } else {
      this.openPanel();
    }
  }

  protected choose(id: string): void {
    this.close(true);
    this.action.emit(id);
  }

  protected chooseLogout(): void {
    this.close(false);
    this.logout.emit();
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (this.open() && !this.host.nativeElement.contains(event.target as Node)) this.close(false);
  }

  protected onKeydown(event: KeyboardEvent): void {
    const items = this.menuItems();
    if (!this.open()) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        this.openPanel();
      }
      return;
    }
    const index = items.indexOf(document.activeElement as HTMLElement);
    const focusAt = (next: number) => items[(next + items.length) % items.length]?.focus();
    switch (event.key) {
      case 'Escape':
        event.preventDefault();
        this.close(true);
        break;
      case 'ArrowDown':
        event.preventDefault();
        focusAt(index + 1);
        break;
      case 'ArrowUp':
        event.preventDefault();
        focusAt(index <= 0 ? items.length - 1 : index - 1);
        break;
      case 'Home':
        event.preventDefault();
        focusAt(0);
        break;
      case 'End':
        event.preventDefault();
        focusAt(items.length - 1);
        break;
      case 'Tab':
        this.close(false);
        break;
    }
  }

  private openPanel(): void {
    this.open.set(true);
    this.startSupportClock();
    // El panel existe tras el próximo render: ahí recibe el foco la primera entrada.
    afterNextRender(() => this.menuItems()[0]?.focus(), { injector: this.injector });
  }

  /** Cierra el panel; con `restoreFocus` el foco vuelve al disparador (Escape, elección). */
  protected close(restoreFocus: boolean): void {
    if (!this.open()) return;
    this.open.set(false);
    this.stopSupportClock();
    if (restoreFocus) this.host.nativeElement.querySelector<HTMLElement>('.sol-user-menu__trigger')?.focus();
  }

  private menuItems(): HTMLElement[] {
    return Array.from(this.host.nativeElement.querySelectorAll<HTMLElement>('[role="menuitem"]'));
  }

  protected startSupportClock(): void {
    this.stopSupportClock();
    if (!this.supportTimeZone()) return;
    this.supportInstant.set(new Date());
    this.clockTimer = setInterval(() => this.supportInstant.set(new Date()), 1000);
  }

  protected stopSupportClock(): void {
    if (this.clockTimer !== undefined) clearInterval(this.clockTimer);
    this.clockTimer = undefined;
  }
}
