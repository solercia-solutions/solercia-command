import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { map, of, switchMap } from 'rxjs';
import {
  SolButtonComponent,
  SolConfirmDialogComponent,
  SolModalComponent,
  SolSelectComponent,
  SolSelectOption,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { readApiError } from '@shared/lib/api-error';
import { formatIsoDay } from '@shared/lib/utils/bogota-date.util';
import { IntakeProposalsService } from '@entities/intake-proposal/intake-proposals.service';
import { IntakeProposal } from '@entities/intake-proposal/intake-proposal.model';
import { ProjectsService } from '@entities/project/projects.service';
import { TaskDetailService } from '@entities/task/task-detail.service';
import { statusDisplay } from '@entities/workspace/workspace.model';
import { ProposalTaskRef } from './proposal-task-resolver';

type Pending = 'dismiss' | 'create' | null;

/** Opción «Mantener el estado»: no se envía `status` y la tarea no se mueve. */
const KEEP = '__keep__';

/**
 * Acciones sobre una propuesta abierta: Aceptar (vincula; el estado de la tarea cambia solo si
 * se elige uno de los estados reales del proyecto), Crear tarea y Descartar. Descartar y crear se
 * confirman con `sol-confirm-dialog`; aceptar usa `sol-modal` porque lleva el selector de estado
 * (el diálogo de confirmación de la librería no proyecta contenido).
 */
@Component({
  selector: 'sol-proposal-actions',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolButtonComponent,
    SolConfirmDialogComponent,
    SolModalComponent,
    SolSelectComponent,
  ],
  styles: [
    `
      :host {
        display: block;
      }
      .pa-row {
        display: flex;
        flex-wrap: wrap;
        gap: var(--sol-space-sm, 8px);
      }
      .pa-busy {
        margin: var(--sol-space-xs, 4px) 0 0;
        font-size: var(--sol-font-size-xs, 0.75rem);
        color: var(--sol-color-text-muted);
      }
      .pa-modal {
        display: flex;
        flex-direction: column;
        gap: var(--sol-space-md, 16px);
      }
      .pa-modal p {
        margin: 0;
        font-size: var(--sol-font-size-sm, 0.875rem);
        color: var(--sol-color-text-secondary);
      }
      .pa-modal strong {
        color: var(--sol-color-text-primary);
      }
      .pa-error {
        color: var(--sol-color-danger) !important;
      }
      .pa-modal__actions {
        display: flex;
        flex-wrap: wrap;
        justify-content: flex-end;
        gap: var(--sol-space-sm, 8px);
      }
    `,
  ],
  template: `
    <div class="pa-row">
      @if (task()) {
        <sol-button type="button" variant="primary" size="sm" [disabled]="busy()" (clicked)="openAccept()">
          {{ t('proposals.actions.accept') }}
        </sol-button>
      }
      @if (canCreate()) {
        <sol-button
          type="button"
          [variant]="task() ? 'secondary' : 'primary'"
          size="sm"
          [disabled]="busy()"
          (clicked)="pending.set('create')"
        >
          {{ t('proposals.actions.createTask') }}
        </sol-button>
      }
      <sol-button
        type="button"
        [variant]="irrelevant() ? 'primary' : 'ghost'"
        size="sm"
        [disabled]="busy()"
        (clicked)="pending.set('dismiss')"
      >
        {{ t('proposals.actions.dismiss') }}
      </sol-button>
    </div>
    @if (busy()) {
      <p class="pa-busy" role="status">{{ t('proposals.actions.working') }}</p>
    }

    @if (acceptOpen()) {
    <sol-modal
      [open]="true"
      [title]="t('proposals.accept.title')"
      size="sm"
      (closed)="closeAccept()"
    >
      <div class="pa-modal">
        <p>
          {{ t('proposals.accept.message') }}
          <strong>{{ taskLabel() }}</strong>
        </p>
        @if (statusLoading()) {
          <p role="status">{{ t('proposals.accept.loadingStatuses') }}</p>
        } @else if (statusOptions().length > 1) {
          <sol-select
            [label]="t('proposals.accept.statusLabel')"
            [options]="statusOptions()"
            [formControl]="statusControl"
            [searchable]="false"
          />
          <p>{{ t('proposals.accept.statusHint') }}</p>
        } @else {
          <p>{{ t('proposals.accept.statusUnavailable') }}</p>
        }
        @if (acceptError(); as message) {
          <p class="pa-error" role="alert">{{ message }}</p>
        }
        <div class="pa-modal__actions">
          <sol-button type="button" variant="ghost" (clicked)="closeAccept()">
            {{ t('proposals.actions.cancel') }}
          </sol-button>
          <sol-button type="button" variant="primary" [loading]="busy()" (clicked)="accept()">
            {{ acceptLabel() }}
          </sol-button>
        </div>
      </div>
    </sol-modal>
    }

    @if (pending() === 'dismiss') {
    <sol-confirm-dialog
      [open]="true"
      variant="warning"
      [title]="t('proposals.dismiss.title')"
      [message]="t('proposals.dismiss.message', { subject: proposal().subject })"
      [confirmLabel]="t('proposals.actions.dismiss')"
      [cancelLabel]="t('proposals.actions.cancel')"
      (confirm)="dismiss()"
      (cancel)="pending.set(null)"
    />
    }
    @if (pending() === 'create') {
    <sol-confirm-dialog
      [open]="true"
      variant="info"
      [title]="t('proposals.create.title')"
      [message]="createMessage()"
      [confirmLabel]="t('proposals.actions.createTask')"
      [cancelLabel]="t('proposals.actions.cancel')"
      (confirm)="createTask()"
      (cancel)="pending.set(null)"
    />
    }
  `,
})
export class ProposalActionsComponent {
  private readonly service = inject(IntakeProposalsService);
  private readonly tasks = inject(TaskDetailService);
  private readonly projects = inject(ProjectsService);
  private readonly i18n = inject(I18nService);
  private readonly alerts = inject(AlertService);

  readonly proposal = input.required<IntakeProposal>();
  readonly task = input<ProposalTaskRef | null>(null);
  /** Emite la propuesta ya decidida, o `null` si cambió en otro lado (409) y hay que releer. */
  readonly decided = output<IntakeProposal | null>();

  protected readonly pending = signal<Pending>(null);
  protected readonly busy = signal(false);
  protected readonly acceptOpen = signal(false);
  protected readonly acceptError = signal<string | null>(null);
  protected readonly statusLoading = signal(false);
  private readonly allowedStatuses = signal<string[]>([]);
  private readonly currentStatus = signal<string | null>(null);
  protected readonly statusControl = new FormControl(KEEP, { nonNullable: true });
  private readonly chosenStatus = signal(KEEP);

  /** Crear solo cuando el hilo pide algo nuevo; un hilo irrelevante se descarta. */
  protected readonly canCreate = computed(() => {
    const relation = this.proposal().relation;
    return relation === 'tarea_nueva' || (relation !== 'irrelevante' && !this.task());
  });
  protected readonly irrelevant = computed(() => this.proposal().relation === 'irrelevante');

  protected readonly taskLabel = computed(() => {
    const task = this.task();
    if (!task) {
      return '';
    }
    const code = task.ref ?? task.key;
    return code ? `${code} · ${task.title}` : task.title;
  });

  protected readonly statusOptions = computed<SolSelectOption[]>(() => {
    this.i18n.activeLang();
    const current = this.currentStatus();
    const keep: SolSelectOption = {
      value: KEEP,
      label: current
        ? this.t('proposals.accept.keepStatus', { status: statusDisplay(current) })
        : this.t('proposals.accept.keepStatusUnknown'),
    };
    return [
      keep,
      ...this.allowedStatuses()
        .filter((s) => s !== current)
        .map((s) => ({ value: s, label: statusDisplay(s) })),
    ];
  });

  protected readonly acceptLabel = computed(() =>
    this.chosenStatus() !== KEEP
      ? this.t('proposals.accept.confirmWithStatus', { status: statusDisplay(this.chosenStatus()) })
      : this.t('proposals.accept.confirm'),
  );

  protected readonly createMessage = computed(() => {
    const proposal = this.proposal();
    const title = proposal.result?.accion || proposal.subject;
    const due = proposal.result?.fecha_limite;
    return due
      ? this.t('proposals.create.messageWithDue', { title, due: formatIsoDay(due) })
      : this.t('proposals.create.message', { title });
  });

  constructor() {
    this.statusControl.valueChanges.subscribe((value) => this.chosenStatus.set(value));
  }

  protected t(key: string, params?: Record<string, unknown>): string {
    return this.i18n.translate(key, params);
  }

  protected openAccept(): void {
    const task = this.task();
    if (!task) {
      return;
    }
    this.acceptError.set(null);
    this.statusControl.setValue(KEEP);
    this.acceptOpen.set(true);
    this.statusLoading.set(true);
    // Estados reales del proyecto de la tarea (los mismos que valida el PATCH del backend).
    const project$ = task.projectId
      ? of({ projectId: task.projectId, status: task.status })
      : this.tasks.getTask(task.id).pipe(map((res) => ({ projectId: res.data.project_id, status: res.data.status })));
    project$
      .pipe(
        switchMap(({ projectId, status }) =>
          this.projects.get(projectId).pipe(
            map((res) => ({ status, allowed: res.data.methodology_info?.allowed_statuses ?? [] })),
          ),
        ),
      )
      .subscribe({
        next: ({ status, allowed }) => {
          this.currentStatus.set(status ?? null);
          this.allowedStatuses.set(allowed);
          this.statusLoading.set(false);
        },
        error: () => {
          // Sin estados se puede vincular igual: solo no se ofrece cambiar el estado.
          this.allowedStatuses.set([]);
          this.statusLoading.set(false);
        },
      });
  }

  protected closeAccept(): void {
    if (!this.busy()) {
      this.acceptOpen.set(false);
    }
  }

  protected accept(): void {
    const task = this.task();
    this.busy.set(true);
    this.acceptError.set(null);
    this.service
      .accept(this.proposal().id, { task_id: task?.id ?? null, status: this.chosenStatus() === KEEP ? null : this.chosenStatus() })
      .subscribe({
        next: (res) => {
          this.busy.set(false);
          this.acceptOpen.set(false);
          this.alerts.showSuccess(this.t('proposals.accept.done', { task: this.taskLabel() }));
          this.decided.emit(res.data);
        },
        error: (err) => {
          this.busy.set(false);
          if (readApiError(err).status === 409) {
            this.acceptOpen.set(false);
            this.alerts.showError(this.describe(err));
            this.decided.emit(null);
            return;
          }
          this.acceptError.set(this.describe(err));
        },
      });
  }

  protected dismiss(): void {
    this.pending.set(null);
    this.busy.set(true);
    this.service.dismiss(this.proposal().id).subscribe({
      next: (res) => {
        this.busy.set(false);
        this.alerts.showSuccess(this.t('proposals.dismiss.done'));
        this.decided.emit(res.data);
      },
      error: (err) => this.fail(err),
    });
  }

  protected createTask(): void {
    this.pending.set(null);
    this.busy.set(true);
    this.service.createTask(this.proposal().id).subscribe({
      next: (res) => {
        this.busy.set(false);
        this.alerts.showSuccess(this.t('proposals.create.done'));
        this.decided.emit(res.data);
      },
      error: (err) => this.fail(err),
    });
  }

  private fail(err: unknown): void {
    this.busy.set(false);
    this.alerts.showError(this.describe(err));
    if (readApiError(err).status === 409) {
      this.decided.emit(null);
    }
  }

  private describe(err: unknown): string {
    const api = readApiError(err);
    if (api.status === 0) {
      return this.t('proposals.errors.network');
    }
    return api.detail ?? this.t('proposals.errors.action');
  }
}
