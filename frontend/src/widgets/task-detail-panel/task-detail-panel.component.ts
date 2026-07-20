import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { AuthService } from '@features/auth/auth.service';
import { TaskDetailService } from '@entities/task/task-detail.service';
import {
  Attachment,
  Comment,
  TaskDetail,
  formatBytes,
} from '@entities/task/task-detail.model';
import { Member, Sprint, statusDisplay } from '@entities/workspace/workspace.model';
import { WorkspaceService } from '@entities/workspace/workspace.service';
import { EstimationMode, MethodologyInfo } from '@entities/project/project.model';
import { ProjectsService } from '@entities/project/projects.service';
import {
  SolBadgeComponent,
  SolSelectComponent,
  SolRichEditorComponent,
  SolInputComponent,
  MentionUser,
  LinkableTask,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';

/**
 * Panel de detalle de tarea reutilizable (widget presentacional + datos).
 *
 * Extraído de `pages/task-detail` para poder hospedarlo en dos contextos sin
 * duplicar UI:
 * - La página `/task/:key` (modo `compact=false`: layout de dos columnas,
 *   enlace de regreso al proyecto).
 * - El `sol-drawer` del workspace (modo `compact=true`: una sola columna,
 *   enlace a la página completa, estilo Jira).
 *
 * Carga todo por `taskKey` vía `TaskDetailService` y permite editar lo
 * esencial (estado, prioridad, responsable, sprint, estimación, descripción),
 * además de subtareas, comentarios y adjuntos. Cada guardado exitoso emite
 * `taskChanged` para que el host refresque sus listas.
 */
@Component({
  selector: 'sol-task-detail-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    DatePipe,
    DecimalPipe,
    FormsModule,
    SolBadgeComponent,
    SolSelectComponent,
    SolRichEditorComponent,
    SolInputComponent,
  ],
  template: `
  @if (loading()) {
    <div class="flex justify-center py-20">
      <div class="h-8 w-8 animate-spin rounded-full border-2 border-brand border-t-transparent"></div>
    </div>
  }
  @if (error()) {
    <div class="rounded-lg border border-danger/30 bg-danger/10 p-4 text-danger">
      {{ error() }}
    </div>
  }
  @if (!loading() && task()) {
    <!-- Header -->
    <div class="mb-4 flex items-center gap-3">
      @if (!compact()) {
        <a [routerLink]="['/projects', task()!.project_id]"
           class="flex items-center gap-1 text-sm text-muted hover:text-text transition-colors"
           [attr.aria-label]="text.backAria()">
          ← {{ text.back() }}
        </a>
      }
      @if (task()!.task_key) {
        <span class="font-mono text-sm font-semibold text-brand">{{ task()!.task_key }}</span>
      }
      @if (compact() && task()!.task_key) {
        <a [routerLink]="['/task', task()!.task_key]"
           class="ml-auto text-xs text-brand hover:underline"
           [attr.aria-label]="text.openFullPageAria()">
          {{ text.openFullPage() }}
        </a>
      }
    </div>

    <h1 class="mb-6 font-bold text-text" [class]="compact() ? 'text-lg' : 'text-2xl'">
      {{ task()!.title }}
    </h1>

    <div [class]="compact() ? 'flex flex-col gap-6' : 'grid gap-6 md:grid-cols-[1fr_320px]'">
      <!-- Fields (sidebar on page, first block in drawer) -->
      <aside class="space-y-4" [class]="compact() ? '' : 'md:order-2'">
        <div class="rounded-lg border border-border bg-surface p-4 space-y-4">

          <!-- Status -->
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">{{ text.fieldStatus() }}</label>
            <sol-select
              [options]="statusOptions()"
              [ngModel]="task()!.status"
              (ngModelChange)="updateField('status', $event)"
              [placeholder]="text.fieldStatusPlaceholder()"
            />
          </div>

          <!-- Priority -->
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">{{ text.fieldPriority() }}</label>
            <sol-select
              [options]="priorityOptions()"
              [ngModel]="task()!.priority"
              (ngModelChange)="updateField('priority', $event)"
              [placeholder]="text.fieldPriorityPlaceholder()"
            />
          </div>

          <!-- Assignee -->
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">{{ text.fieldAssignee() }}</label>
            <sol-select
              [options]="assigneeOptions()"
              [ngModel]="task()!.assignee_id ?? ''"
              (ngModelChange)="updateField('assignee_id', $event || null)"
              [placeholder]="text.fieldAssigneePlaceholder()"
            />
          </div>

          <!-- Sprint (only when the host or the project methodology enables sprints) -->
          @if (effectiveSprintsEnabled()) {
            <div>
              <label class="mb-1 block text-xs font-medium text-muted">{{ text.fieldSprint() }}</label>
              <sol-select
                [options]="sprintOptions()"
                [ngModel]="task()!.sprint_id ?? ''"
                (ngModelChange)="updateField('sprint_id', $event || null)"
                [placeholder]="text.fieldSprintNone()"
              />
            </div>
          }

          <!-- Estimation: points -->
          @if (effectiveEstimationMode() === 'points' || effectiveEstimationMode() === 'both') {
            <div>
              <label for="tdp-points" class="mb-1 block text-xs font-medium text-muted">
                {{ text.fieldStoryPoints() }}
              </label>
              <input
                id="tdp-points"
                type="number"
                min="0"
                class="w-full rounded border border-border bg-surface px-3 py-1.5 text-sm text-text focus:border-brand focus:outline-none"
                [value]="task()!.estimation_points ?? ''"
                (change)="updateNumberField('estimation_points', $event)"
                [attr.aria-label]="text.fieldStoryPoints()"
              />
            </div>
          }

          <!-- Estimation: hours -->
          @if (effectiveEstimationMode() === 'hours' || effectiveEstimationMode() === 'both') {
            <div>
              <label for="tdp-hours" class="mb-1 block text-xs font-medium text-muted">
                {{ text.fieldEstimationHours() }}
              </label>
              <input
                id="tdp-hours"
                type="number"
                min="0"
                step="0.5"
                class="w-full rounded border border-border bg-surface px-3 py-1.5 text-sm text-text focus:border-brand focus:outline-none"
                [value]="task()!.estimation_hours ?? ''"
                (change)="updateNumberField('estimation_hours', $event)"
                [attr.aria-label]="text.fieldEstimationHours()"
              />
            </div>
          }

          <!-- Due date -->
          @if (task()!.due_date) {
            <div>
              <label class="mb-1 block text-xs font-medium text-muted">{{ text.fieldDueDate() }}</label>
              <p class="text-sm text-text">{{ task()!.due_date | date:'dd/MM/yyyy' }}</p>
            </div>
          }

          <!-- Risk flag -->
          @if (task()!.risk_flag) {
            <div class="rounded border border-danger/30 bg-danger/10 p-3">
              <p class="text-xs font-semibold text-danger">{{ text.fieldAtRisk() }}</p>
              @if (task()!.risk_reason) {
                <p class="mt-1 text-xs text-danger/80">{{ task()!.risk_reason }}</p>
              }
            </div>
          }
        </div>
      </aside>

      <!-- Main content -->
      <div class="space-y-6" [class]="compact() ? '' : 'md:order-1'">

        <!-- Description -->
        <div class="rounded-lg border border-border bg-surface p-4">
          <h2 class="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">{{ text.description() }}</h2>
          <sol-rich-editor
            [ngModel]="task()!.description ?? ''"
            (ngModelChange)="updateField('description', $event)"
            [mentionableUsers]="mentionableUsers()"
            [linkableTasks]="linkableTasks()"
          />
        </div>

        <!-- Subtasks -->
        <div class="rounded-lg border border-border bg-surface p-4">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-semibold text-muted uppercase tracking-wide">{{ text.subtasksTitle() }}</h2>
            <button
              class="text-xs text-brand hover:underline"
              (click)="showSubtaskForm.set(true)"
              [attr.aria-label]="text.subtaskAddAria()">
              + {{ text.subtaskNew() }}
            </button>
          </div>

          @if (task()!.subtask_progress !== null) {
            <div class="mb-3">
              <div class="mb-1 flex justify-between text-xs text-muted">
                <span>{{ text.subtaskProgress() }}</span>
                <span>{{ (task()!.subtask_progress! * 100) | number:'1.0-0' }}%</span>
              </div>
              <div class="h-1.5 rounded-full bg-muted/20">
                <div class="h-full rounded-full bg-brand transition-all"
                     [style.width]="(task()!.subtask_progress! * 100) + '%'"></div>
              </div>
            </div>
          }

          <ul class="space-y-2">
            @for (sub of subtasks(); track sub.id) {
              <li class="flex items-center gap-2 rounded p-2 hover:bg-muted/5">
                <sol-badge [variant]="statusTone(sub.status)">{{ sub.status }}</sol-badge>
                @if (sub.task_key) {
                  <a [routerLink]="['/task', sub.task_key]"
                     class="text-sm text-text hover:text-brand hover:underline flex-1">
                    {{ sub.title }}
                  </a>
                } @else {
                  <span class="text-sm text-text flex-1">{{ sub.title }}</span>
                }
              </li>
            }
          </ul>

          @if (showSubtaskForm()) {
            <div class="mt-3 space-y-2 border-t border-border pt-3">
              <sol-input
                [label]="text.subtaskTitleField()"
                [ngModel]="newSubtaskTitle()"
                (ngModelChange)="newSubtaskTitle.set($event)"
                [placeholder]="text.subtaskTitleField()"
              />
              <div>
                <label class="mb-1 block text-xs text-muted">{{ text.subtaskHours() }}</label>
                <input
                  type="number"
                  class="w-full rounded border border-border bg-surface px-3 py-1.5 text-sm text-text focus:border-brand focus:outline-none"
                  [value]="newSubtaskHours()"
                  (input)="newSubtaskHours.set(+$any($event.target).value || null)"
                  placeholder="0"
                  min="0"
                />
              </div>
              <div class="flex gap-2">
                <button
                  class="rounded bg-brand px-3 py-1.5 text-xs font-medium text-brand-fg hover:opacity-90 disabled:opacity-50"
                  (click)="createSubtask()"
                  [disabled]="savingSubtask() || !newSubtaskTitle().trim()"
                  [attr.aria-label]="text.subtaskSaveAria()">
                  {{ savingSubtask() ? text.subtaskSaving() : text.subtaskSave() }}
                </button>
                <button
                  class="rounded border border-border px-3 py-1.5 text-xs text-muted hover:text-text"
                  (click)="showSubtaskForm.set(false)"
                  [attr.aria-label]="text.subtaskCancelAria()">
                  {{ text.subtaskCancel() }}
                </button>
              </div>
            </div>
          }
        </div>

        <!-- Comments -->
        <div class="rounded-lg border border-border bg-surface p-4">
          <h2 class="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">{{ text.commentsTitle() }}</h2>

          <ul class="space-y-4 mb-4">
            @for (comment of comments(); track comment.id) {
              <li class="space-y-2">
                <div class="flex items-start gap-3">
                  <div class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-brand/10 text-xs font-semibold text-brand">
                    {{ comment.author_id.slice(0, 2).toUpperCase() }}
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-1">
                      <span class="text-xs text-muted">{{ comment.created_at | date:'dd/MM/yyyy HH:mm' }}</span>
                      @if (auth.user()?.id === comment.author_id) {
                        <button class="text-xs text-muted hover:text-text"
                                (click)="startEditComment(comment)"
                                [attr.aria-label]="text.commentEditAria()">
                          {{ text.commentEdit() }}
                        </button>
                        <button class="text-xs text-danger/70 hover:text-danger"
                                (click)="deleteComment(comment.id)"
                                [attr.aria-label]="text.commentDeleteAria()">
                          {{ text.commentDelete() }}
                        </button>
                      }
                    </div>

                    @if (editingCommentId() === comment.id) {
                      <sol-rich-editor
                        [ngModel]="editBody()"
                        (ngModelChange)="editBody.set($event)"
                        [mentionableUsers]="mentionableUsers()"
                        [linkableTasks]="linkableTasks()"
                      />
                      <div class="mt-2 flex gap-2">
                        <button
                          class="rounded bg-brand px-3 py-1.5 text-xs font-medium text-brand-fg hover:opacity-90"
                          (click)="saveEditComment()"
                          [attr.aria-label]="text.commentSaveEditAria()">
                          {{ text.commentSaveEdit() }}
                        </button>
                        <button
                          class="rounded border border-border px-3 py-1.5 text-xs text-muted hover:text-text"
                          (click)="cancelEditComment()"
                          [attr.aria-label]="text.commentCancelEditAria()">
                          {{ text.commentCancelEdit() }}
                        </button>
                      </div>
                    } @else {
                      <div class="prose prose-sm max-w-none text-text" [innerHTML]="comment.body"></div>
                    }

                    <!-- Comment attachments -->
                    @if ((commentAttachments()[comment.id] ?? []).length > 0) {
                      <ul class="mt-2 space-y-1">
                        @for (att of commentAttachments()[comment.id]; track att.id) {
                          <li class="flex items-center gap-2 text-xs text-muted">
                            <span class="flex-1 truncate">{{ att.original_name }}</span>
                            <span>{{ formatBytes(att.size_bytes) }}</span>
                            <button class="text-brand hover:underline"
                                    (click)="downloadAttachment(att)"
                                    [attr.aria-label]="text.commentDownloadAria()">
                              {{ text.commentDownload() }}
                            </button>
                          </li>
                        }
                      </ul>
                    }

                    <!-- Upload to comment -->
                    <label class="mt-1 inline-block cursor-pointer text-xs text-muted hover:text-text">
                      {{ text.commentUpload() }}
                      <input type="file" class="sr-only"
                             (change)="uploadCommentFile(comment.id, $event)"
                             [attr.aria-label]="text.commentUploadAria()" />
                    </label>
                  </div>
                </div>
              </li>
            }
          </ul>

          <!-- New comment -->
          <div class="border-t border-border pt-4">
            <sol-rich-editor
              [ngModel]="commentBody()"
              (ngModelChange)="commentBody.set($event)"
              [mentionableUsers]="mentionableUsers()"
              [linkableTasks]="linkableTasks()"
            />
            <div class="mt-2 flex justify-end">
              <button
                class="rounded bg-brand px-4 py-1.5 text-sm font-medium text-brand-fg hover:opacity-90 disabled:opacity-50"
                (click)="addComment()"
                [disabled]="savingComment() || !commentBody().trim()"
                [attr.aria-label]="text.commentSubmitAria()">
                {{ savingComment() ? text.commentSending() : text.commentSubmit() }}
              </button>
            </div>
          </div>
        </div>

        <!-- Task attachments -->
        <div class="rounded-lg border border-border bg-surface p-4">
          <h2 class="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">{{ text.attachmentsTitle() }}</h2>
          <ul class="space-y-2 mb-3">
            @for (att of taskAttachments(); track att.id) {
              <li class="flex items-center gap-2 text-sm">
                <span class="flex-1 truncate text-text">{{ att.original_name }}</span>
                <span class="text-xs text-muted">{{ formatBytes(att.size_bytes) }}</span>
                <button class="text-xs text-brand hover:underline"
                        (click)="downloadAttachment(att)"
                        [attr.aria-label]="text.attachmentDownloadAria()">
                  {{ text.attachmentDownload() }}
                </button>
              </li>
            }
          </ul>
          <label class="inline-flex cursor-pointer items-center gap-1 rounded border border-border px-3 py-1.5 text-xs text-muted hover:text-text">
            + {{ text.attachmentUpload() }}
            <input type="file" class="sr-only"
                   (change)="uploadTaskFile($event)"
                   [attr.aria-label]="text.attachmentUploadAria()" />
          </label>
        </div>

      </div>
    </div>
  }
  `,
})
export class TaskDetailPanelComponent {
  protected readonly svc = inject(TaskDetailService);
  protected readonly auth = inject(AuthService);
  private readonly projectsService = inject(ProjectsService);
  private readonly workspaceService = inject(WorkspaceService);
  private readonly i18n = inject(I18nService);
  private readonly destroyRef = inject(DestroyRef);

  /** Clave de la tarea (`task_key`) a cargar. Reactivo: si cambia, recarga. */
  readonly taskKey = input.required<string>();

  /**
   * `true` cuando el panel vive en un drawer: una sola columna, sin enlace
   * de regreso y con enlace a la página completa `/task/:key`.
   */
  readonly compact = input<boolean>(false);

  /** Sprints del proyecto para reasignar desde el detalle (host los provee). */
  readonly sprints = input<Sprint[]>([]);

  /** Muestra el selector de sprint solo si la metodología los habilita. */
  readonly sprintsEnabled = input<boolean>(false);

  /**
   * Controla qué campos de estimación son editables. `null` (default) deriva
   * el modo de la metodología del proyecto cargado.
   */
  readonly estimationMode = input<EstimationMode | null>(null);

  /** Emitido tras cada guardado exitoso (campo, sprint, estimación, subtarea). */
  readonly taskChanged = output<TaskDetail>();

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    back: this.i18n.t('taskDetail.back'),
    backAria: this.i18n.t('taskDetail.backAria'),
    openFullPage: this.i18n.t('taskDetail.openFullPage'),
    openFullPageAria: this.i18n.t('taskDetail.openFullPageAria'),
    description: this.i18n.t('taskDetail.description'),
    subtasksTitle: this.i18n.t('taskDetail.subtasks.title'),
    subtaskAddAria: this.i18n.t('taskDetail.subtasks.addAria'),
    subtaskNew: this.i18n.t('taskDetail.subtasks.new'),
    subtaskProgress: this.i18n.t('taskDetail.subtasks.progress'),
    subtaskTitleField: this.i18n.t('taskDetail.subtasks.titleField'),
    subtaskHours: this.i18n.t('taskDetail.subtasks.hours'),
    subtaskSaving: this.i18n.t('taskDetail.subtasks.saving'),
    subtaskSave: this.i18n.t('taskDetail.subtasks.save'),
    subtaskSaveAria: this.i18n.t('taskDetail.subtasks.saveAria'),
    subtaskCancel: this.i18n.t('taskDetail.subtasks.cancel'),
    subtaskCancelAria: this.i18n.t('taskDetail.subtasks.cancelAria'),
    commentsTitle: this.i18n.t('taskDetail.comments.title'),
    commentEdit: this.i18n.t('taskDetail.comments.edit'),
    commentEditAria: this.i18n.t('taskDetail.comments.editAria'),
    commentDelete: this.i18n.t('taskDetail.comments.delete'),
    commentDeleteAria: this.i18n.t('taskDetail.comments.deleteAria'),
    commentSaveEdit: this.i18n.t('taskDetail.comments.saveEdit'),
    commentSaveEditAria: this.i18n.t('taskDetail.comments.saveEditAria'),
    commentCancelEdit: this.i18n.t('taskDetail.comments.cancelEdit'),
    commentCancelEditAria: this.i18n.t('taskDetail.comments.cancelEditAria'),
    commentDownload: this.i18n.t('taskDetail.comments.download'),
    commentDownloadAria: this.i18n.t('taskDetail.comments.downloadAria'),
    commentUpload: this.i18n.t('taskDetail.comments.upload'),
    commentUploadAria: this.i18n.t('taskDetail.comments.uploadAria'),
    commentSending: this.i18n.t('taskDetail.comments.sending'),
    commentSubmit: this.i18n.t('taskDetail.comments.submit'),
    commentSubmitAria: this.i18n.t('taskDetail.comments.submitAria'),
    attachmentsTitle: this.i18n.t('taskDetail.attachments.title'),
    attachmentDownload: this.i18n.t('taskDetail.attachments.download'),
    attachmentDownloadAria: this.i18n.t('taskDetail.attachments.downloadAria'),
    attachmentUpload: this.i18n.t('taskDetail.attachments.upload'),
    attachmentUploadAria: this.i18n.t('taskDetail.attachments.uploadAria'),
    fieldStatus: this.i18n.t('taskDetail.fields.status'),
    fieldStatusPlaceholder: this.i18n.t('taskDetail.fields.statusPlaceholder'),
    fieldPriority: this.i18n.t('taskDetail.fields.priority'),
    fieldPriorityPlaceholder: this.i18n.t(
      'taskDetail.fields.priorityPlaceholder',
    ),
    fieldAssignee: this.i18n.t('taskDetail.fields.assignee'),
    fieldAssigneePlaceholder: this.i18n.t(
      'taskDetail.fields.assigneePlaceholder',
    ),
    fieldSprint: this.i18n.t('taskDetail.fields.sprint'),
    fieldSprintNone: this.i18n.t('taskDetail.fields.sprintNone'),
    fieldEstimationHours: this.i18n.t('taskDetail.fields.estimationHours'),
    fieldStoryPoints: this.i18n.t('taskDetail.fields.storyPoints'),
    fieldDueDate: this.i18n.t('taskDetail.fields.dueDate'),
    fieldAtRisk: this.i18n.t('taskDetail.fields.atRisk'),
  } as const;

  readonly task = signal<TaskDetail | null>(null);
  readonly subtasks = signal<TaskDetail[]>([]);
  readonly comments = signal<Comment[]>([]);
  readonly taskAttachments = signal<Attachment[]>([]);
  readonly commentAttachments = signal<Record<string, Attachment[]>>({});
  readonly members = signal<Member[]>([]);
  readonly projectTasks = signal<TaskDetail[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly commentBody = signal('');
  readonly savingComment = signal(false);
  readonly showSubtaskForm = signal(false);
  readonly newSubtaskTitle = signal('');
  readonly newSubtaskHours = signal<number | null>(null);
  readonly savingSubtask = signal(false);
  readonly editingCommentId = signal<string | null>(null);
  readonly editBody = signal('');

  /** Configuración de metodología del proyecto de la tarea (cargada aquí). */
  readonly methodologyInfo = signal<MethodologyInfo | null>(null);

  /**
   * Sprints cargados por el propio widget cuando el host no los provee
   * (p. ej. deep-link `/task/:key`, donde la página solo pasa `taskKey`).
   */
  readonly fallbackSprints = signal<Sprint[]>([]);

  /**
   * Selector de sprint visible si el host lo habilita o si la metodología
   * del proyecto cargado tiene sprints (cubre el deep-link sin inputs).
   */
  readonly effectiveSprintsEnabled = computed(
    () => this.sprintsEnabled() || !!this.methodologyInfo()?.sprints_enabled,
  );

  /** Sprints efectivos: los del host si llegan; si no, los auto-cargados. */
  readonly effectiveSprints = computed(() =>
    this.sprints().length > 0 ? this.sprints() : this.fallbackSprints(),
  );

  /**
   * Estados válidos según la metodología del proyecto (los mismos que valida
   * el backend en el PATCH). Fallback genérico solo si el proyecto no cargó.
   */
  readonly statusOptions = computed(() => {
    const allowed = this.methodologyInfo()?.allowed_statuses;
    if (allowed && allowed.length > 0) {
      return allowed.map(s => ({ value: s, label: statusDisplay(s) }));
    }
    const statuses = ['backlog', 'to_do', 'in_progress', 'in_review', 'done', 'cancelled'];
    return statuses.map(s => ({ value: s, label: s.replace(/_/g, ' ') }));
  });

  /** Modo de estimación efectivo: input del host o el de la metodología. */
  readonly effectiveEstimationMode = computed<EstimationMode>(
    () =>
      this.estimationMode() ??
      this.methodologyInfo()?.estimation_mode ??
      'both',
  );

  readonly priorityOptions = computed(() => {
    this.i18n.activeLang();
    return [
      { value: 'critical', label: this.i18n.translate('taskDetail.priorities.critical') },
      { value: 'high', label: this.i18n.translate('taskDetail.priorities.high') },
      { value: 'medium', label: this.i18n.translate('taskDetail.priorities.medium') },
      { value: 'low', label: this.i18n.translate('taskDetail.priorities.low') },
    ];
  });

  readonly mentionableUsers = computed<MentionUser[]>(() =>
    this.members().map(m => ({ id: m.user_id, name: m.full_name })),
  );

  readonly linkableTasks = computed<LinkableTask[]>(() =>
    this.projectTasks().map(t => ({ key: t.task_key ?? t.id, title: t.title })),
  );

  readonly assigneeOptions = computed(() =>
    this.members().map(m => ({ value: m.user_id, label: m.full_name })),
  );

  /** Opciones del selector de sprint: primero "sin sprint" (backlog). */
  readonly sprintOptions = computed(() => [
    { value: '', label: this.text.fieldSprintNone() },
    ...this.effectiveSprints().map(s => ({ value: s.id, label: s.name })),
  ]);

  constructor() {
    // Recarga reactiva: la primera asignación de `taskKey` y cualquier cambio
    // posterior (p. ej. abrir otra tarea en el mismo drawer) recargan todo.
    effect(() => {
      const key = this.taskKey();
      if (key) {
        this.loadAll(key);
      }
    });
  }

  /**
   * Carga todo el detalle de la tarea `key`.
   *
   * Robustez ante navegación rápida entre tareas (mismo widget, distinto
   * `taskKey`): cada respuesta se descarta con `isStale(key)` si el key ya
   * cambió cuando llega, y toda subscripción se corta con
   * `takeUntilDestroyed` al destruir el widget. Así una respuesta lenta de
   * la tarea anterior nunca pisa los datos de la actual.
   */
  private loadAll(key: string): void {
    this.loading.set(true);
    this.error.set(null);
    this.task.set(null);
    this.subtasks.set([]);
    this.comments.set([]);
    this.taskAttachments.set([]);
    this.commentAttachments.set({});
    this.methodologyInfo.set(null);
    this.fallbackSprints.set([]);

    this.svc.getTaskByKey(key)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          if (this.isStale(key)) return;
          this.task.set(res.data);
          const t = res.data;
          forkJoin({
            subtasks: this.svc.getSubtasks(t.id),
            comments: this.svc.getComments(t.id),
            attachments: this.svc.getTaskAttachments(t.id),
            members: this.svc.getMembers(t.project_id),
            projectTasks: this.svc.getProjectTasks(t.project_id),
            project: this.projectsService.get(t.project_id),
          })
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: (data) => {
                if (this.isStale(key)) return;
                this.subtasks.set(data.subtasks.data);
                this.comments.set(data.comments.data);
                this.taskAttachments.set(data.attachments.data);
                this.members.set(data.members.data);
                this.projectTasks.set(data.projectTasks.data);
                this.methodologyInfo.set(data.project.data.methodology_info);
                this.loading.set(false);
                this.loadFallbackSprints(key, t.project_id);
                // Adjuntos por comentario
                data.comments.data.forEach(c => {
                  this.svc.getCommentAttachments(c.id)
                    .pipe(takeUntilDestroyed(this.destroyRef))
                    .subscribe(r => {
                      if (this.isStale(key)) return;
                      this.commentAttachments.update(map => ({ ...map, [c.id]: r.data }));
                    });
                });
              },
              error: (err) => {
                if (this.isStale(key)) return;
                this.error.set(this.i18n.translate('taskDetail.errors.loadData'));
                this.loading.set(false);
                console.error(err);
              },
            });
        },
        error: (err) => {
          if (this.isStale(key)) return;
          this.error.set(this.i18n.translate('taskDetail.errors.notFound'));
          this.loading.set(false);
          console.error(err);
        },
      });
  }

  /** `true` si la respuesta pertenece a un `taskKey` que ya no es el actual. */
  private isStale(key: string): boolean {
    return key !== this.taskKey();
  }

  /**
   * Auto-carga los sprints del proyecto cuando la metodología los habilita y
   * el host no los proveyó (deep-link `/task/:key`). El drawer del workspace
   * sí los pasa por input, así que allí no hay doble carga.
   */
  private loadFallbackSprints(key: string, projectId: string): void {
    if (!this.effectiveSprintsEnabled() || this.sprints().length > 0) return;
    this.workspaceService.sprints(projectId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          if (this.isStale(key)) return;
          this.fallbackSprints.set(res.data);
        },
        error: (err) => console.error('Error cargando sprints del proyecto', err),
      });
  }

  updateField(field: string, value: unknown): void {
    const t = this.task();
    if (!t) return;
    this.svc.updateTask(t.id, { [field]: value })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.task.set(res.data);
          this.taskChanged.emit(res.data);
        },
        error: (err) => console.error('Error actualizando campo', field, err),
      });
  }

  /** Parsea un input numérico nativo: cadena vacía → null. */
  updateNumberField(field: 'estimation_points' | 'estimation_hours', event: Event): void {
    const raw = (event.target as HTMLInputElement).value.trim();
    const value = raw === '' ? null : Number(raw);
    if (value !== null && Number.isNaN(value)) return;
    this.updateField(field, value);
  }

  addComment(): void {
    const t = this.task();
    if (!t || !this.commentBody().trim()) return;
    this.savingComment.set(true);
    this.svc.createComment(t.id, this.commentBody())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.comments.update(cs => [...cs, res.data]);
          this.commentBody.set('');
          this.savingComment.set(false);
          // Adjuntos del comentario recién creado
          this.svc.getCommentAttachments(res.data.id)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe(r => {
              this.commentAttachments.update(map => ({ ...map, [res.data.id]: r.data }));
            });
        },
        error: (err) => {
          this.savingComment.set(false);
          console.error(err);
        },
      });
  }

  deleteComment(id: string): void {
    this.svc.deleteComment(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => this.comments.update(cs => cs.filter(c => c.id !== id)),
        error: (err) => console.error(err),
      });
  }

  startEditComment(comment: Comment): void {
    this.editingCommentId.set(comment.id);
    this.editBody.set(comment.body);
  }

  saveEditComment(): void {
    const id = this.editingCommentId();
    if (!id) return;
    this.svc.updateComment(id, this.editBody())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.comments.update(cs => cs.map(c => c.id === id ? res.data : c));
          this.editingCommentId.set(null);
          this.editBody.set('');
        },
        error: (err) => console.error(err),
      });
  }

  cancelEditComment(): void {
    this.editingCommentId.set(null);
    this.editBody.set('');
  }

  createSubtask(): void {
    const t = this.task();
    if (!t || !this.newSubtaskTitle().trim()) return;
    this.savingSubtask.set(true);
    this.svc.createSubtask(t.project_id, {
      title: this.newSubtaskTitle(),
      estimation_hours: this.newSubtaskHours(),
      parent_task_id: t.id,
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.subtasks.update(ss => [...ss, res.data]);
          this.newSubtaskTitle.set('');
          this.newSubtaskHours.set(null);
          this.showSubtaskForm.set(false);
          this.savingSubtask.set(false);
          // Re-fetch de la tarea para refrescar subtask_progress
          const key = this.taskKey();
          if (key) {
            this.svc.getTaskByKey(key)
              .pipe(takeUntilDestroyed(this.destroyRef))
              .subscribe(r => {
                if (this.isStale(key)) return;
                this.task.set(r.data);
                this.taskChanged.emit(r.data);
              });
          }
        },
        error: (err) => {
          this.savingSubtask.set(false);
          console.error(err);
        },
      });
  }

  downloadAttachment(att: Attachment): void {
    this.svc.downloadAttachment(att.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = att.original_name;
        a.click();
        URL.revokeObjectURL(url);
      });
  }

  uploadTaskFile(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    const t = this.task();
    if (!file || !t) return;
    this.svc.uploadTaskAttachment(t.id, file)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => this.taskAttachments.update(atts => [...atts, res.data]),
        error: (err) => console.error(err),
      });
  }

  uploadCommentFile(commentId: string, event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.svc.uploadCommentAttachment(commentId, file)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.commentAttachments.update(map => ({
            ...map,
            [commentId]: [...(map[commentId] ?? []), res.data],
          }));
        },
        error: (err) => console.error(err),
      });
  }

  protected readonly formatBytes = formatBytes;

  statusTone(s: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
    const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral'> = {
      done: 'success',
      in_progress: 'info',
      cancelled: 'neutral',
      in_review: 'warning',
      to_do: 'neutral',
      backlog: 'neutral',
    };
    return map[s] ?? 'neutral';
  }
}
