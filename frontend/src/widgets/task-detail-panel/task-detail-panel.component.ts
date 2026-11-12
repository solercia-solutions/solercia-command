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
import { HttpErrorResponse } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import { DecimalPipe } from '@angular/common';
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
import {
  Member,
  Sprint,
  TASK_TYPE_LABELS,
  TaskType,
  statusDisplay,
} from '@entities/workspace/workspace.model';
import { WorkspaceService } from '@entities/workspace/workspace.service';
import { EstimationMode, MethodologyInfo, Project } from '@entities/project/project.model';
import { ProjectsService } from '@entities/project/projects.service';
import {
  SolAvatarComponent,
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolErrorStateComponent,
  SolInputComponent,
  SolRichEditorComponent,
  SolSelectComponent,
  SolSpinnerComponent,
  SolTabsComponent,
  type SolTabItem,
  MentionUser,
  LinkableTask,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import {
  formatOriginalEstimate,
  parseOriginalEstimate,
} from '@shared/lib/estimation';

type LoadState = 'loading' | 'ready' | 'notFound' | 'forbidden' | 'error';
type TabId = 'detail' | 'subtasks' | 'comments' | 'attachments';
type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

/** Variante de `sol-badge` por prioridad (mismo criterio que la cuadrícula del workspace). */
const PRIORITY_TONE: Record<string, BadgeTone> = {
  critical: 'danger',
  high: 'warning',
  medium: 'info',
  low: 'neutral',
};

/** Orígenes conocidos de una tarea importada → llave i18n de su nombre legible. */
const SOURCE_KEYS: Record<string, string> = {
  checklist_xlsx: 'taskDetail.sources.checklist_xlsx',
  jira: 'taskDetail.sources.jira',
  api: 'taskDetail.sources.api',
  file: 'taskDetail.sources.file',
};

/**
 * Panel de detalle de tarea reutilizable, con el patrón de detalle de PANDORA
 * (`pages/perfil`): cabecera en `sol-card` y contenido en `sol-tabs`.
 *
 * Se hospeda en dos contextos sin duplicar UI:
 * - La página `/task/:key` (`compact=false`: Detalle a dos columnas y enlace
 *   de regreso al proyecto).
 * - El `sol-drawer` del workspace (`compact=true`: una columna y enlace a la
 *   página completa).
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
    DecimalPipe,
    FormsModule,
    SolAvatarComponent,
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolErrorStateComponent,
    SolInputComponent,
    SolRichEditorComponent,
    SolSelectComponent,
    SolSpinnerComponent,
    SolTabsComponent,
  ],
  template: `
  @switch (state()) {
    @case ('loading') {
      <div class="tdp__state" role="status" aria-live="polite">
        <sol-spinner size="lg" />
        <p>{{ text.loading() }}</p>
      </div>
    }
    @case ('notFound') {
      <div class="tdp__state">
        <sol-error-state [code]="404" [title]="text.notFoundTitle()" [message]="notFoundMessage()">
          <a routerLink="/projects" class="tdp__link-button">{{ text.goProjects() }}</a>
        </sol-error-state>
      </div>
    }
    @case ('forbidden') {
      <div class="tdp__state">
        <sol-error-state [code]="403" [title]="text.forbiddenTitle()" [message]="text.forbiddenMessage()">
          <a routerLink="/projects" class="tdp__link-button">{{ text.goProjects() }}</a>
        </sol-error-state>
      </div>
    }
    @case ('error') {
      <div class="tdp__alert" role="alert">
        <span>{{ text.loadError() }}</span>
        <sol-button type="button" variant="secondary" size="sm" (clicked)="retry()">
          {{ text.retry() }}
        </sol-button>
      </div>
    }
    @case ('ready') {
      @if (task(); as t) {
        <div class="tdp" [class.tdp--compact]="compact()">
          <!-- Cabecera: identidad de la tarea + acciones -->
          <sol-card>
            <div class="tdp__stack tdp__stack--sm">
            <div class="tdp__header-top">
              <div class="tdp__ids">
                @if (t.task_key) {
                  <span class="tdp__code">{{ t.task_key }}</span>
                }
                @if (sourceText(); as src) {
                  <span class="tdp__source" [attr.title]="text.sourceLabel()">
                    {{ text.sourceLabel() }}: {{ src }}
                  </span>
                }
              </div>
              <div class="tdp__actions">
                @if (compact()) {
                  @if (t.task_key) {
                    <a [routerLink]="['/task', t.task_key]" class="tdp__link-button"
                       [attr.aria-label]="text.openFullPageAria()">
                      {{ text.openFullPage() }}
                    </a>
                  }
                } @else {
                  <a [routerLink]="['/projects', t.project_id]" class="tdp__link-button"
                     [attr.aria-label]="text.backAria()">
                    ← {{ text.backAria() }}
                  </a>
                }
              </div>
            </div>

            @if (compact()) {
              <h2 class="tdp__title tdp__title--compact">{{ t.title }}</h2>
            } @else {
              <h1 class="tdp__title sol-display">{{ t.title }}</h1>
            }

            <div class="tdp__badges">
              <sol-badge [variant]="statusTone(t.status)">{{ statusLabel(t.status) }}</sol-badge>
              <sol-badge [variant]="priorityTone(t.priority)">
                {{ text.fieldPriority() }}: {{ priorityLabel(t.priority) }}
              </sol-badge>
              @if (typeLabel(t.task_type); as type) {
                <sol-badge variant="neutral">{{ type }}</sol-badge>
              }
              @if (t.risk_flag) {
                <sol-badge variant="danger">{{ text.fieldAtRisk() }}</sol-badge>
              }
            </div>

            <dl class="tdp__meta">
              <div class="tdp__meta-item">
                <dt>{{ text.fieldAssignee() }}</dt>
                <dd class="tdp__person">
                  @if (t.assignee_name) {
                    <sol-avatar [name]="t.assignee_name" size="sm" />
                    <span>{{ t.assignee_name }}</span>
                  } @else {
                    <span class="tdp__muted">{{ text.fieldAssigneePlaceholder() }}</span>
                  }
                </dd>
              </div>
              @if (project(); as p) {
                <div class="tdp__meta-item">
                  <dt>{{ text.metaProject() }}</dt>
                  <dd>
                    <a [routerLink]="['/projects', p.id]" class="tdp__inline-link">
                      {{ projectLabel(p) }}
                    </a>
                  </dd>
                </div>
              }
              <div class="tdp__meta-item">
                <dt>{{ text.metaDue() }}</dt>
                <dd [class.tdp__muted]="!t.due_date">{{ dateText(t.due_date) }}</dd>
              </div>
              @if (t.start_date) {
                <div class="tdp__meta-item">
                  <dt>{{ text.metaStart() }}</dt>
                  <dd>{{ dateText(t.start_date) }}</dd>
                </div>
              }
              <div class="tdp__meta-item">
                <dt>{{ text.metaCreated() }}</dt>
                <dd>{{ dateText(t.created_at) }}</dd>
              </div>
              @if (t.completed_at) {
                <div class="tdp__meta-item">
                  <dt>{{ text.metaCompleted() }}</dt>
                  <dd>{{ dateText(t.completed_at) }}</dd>
                </div>
              }
            </dl>
            </div>
          </sol-card>

          @if (actionError()) {
            <div class="tdp__alert" role="alert">
              <span>{{ actionError() }}</span>
              <sol-button type="button" variant="ghost" size="sm" (clicked)="actionError.set(null)">
                {{ text.dismiss() }}
              </sol-button>
            </div>
          }

          <sol-tabs [tabs]="tabs()" [activeTab]="activeTab()" (tabChange)="onTabChange($event)" />

          <div class="tdp__tab-content">
            @switch (activeTab()) {
              @case ('detail') {
                <div class="tdp__detail">
                  <!-- Campos editables -->
                  <sol-card class="tdp__fields">
                    <div class="tdp__stack">
                    <sol-select
                      [label]="text.fieldStatus()"
                      [options]="statusOptions()"
                      [ngModel]="t.status"
                      (ngModelChange)="updateField('status', $event)"
                      [placeholder]="text.fieldStatusPlaceholder()"
                    />
                    <sol-select
                      [label]="text.fieldPriority()"
                      [options]="priorityOptions()"
                      [ngModel]="t.priority"
                      (ngModelChange)="updateField('priority', $event)"
                      [placeholder]="text.fieldPriorityPlaceholder()"
                    />
                    <sol-select
                      [label]="text.fieldAssignee()"
                      [options]="assigneeOptions()"
                      [searchable]="assigneeOptions().length > 7"
                      [ngModel]="t.assignee_id ?? ''"
                      (ngModelChange)="updateField('assignee_id', $event || null)"
                      [placeholder]="text.fieldAssigneePlaceholder()"
                    />
                    @if (effectiveSprintsEnabled()) {
                      <sol-select
                        [label]="text.fieldSprint()"
                        [options]="sprintOptions()"
                        [ngModel]="t.sprint_id ?? ''"
                        (ngModelChange)="updateField('sprint_id', $event || null)"
                        [placeholder]="text.fieldSprintNone()"
                      />
                    }
                    @if (effectiveEstimationMode() === 'points' || effectiveEstimationMode() === 'both') {
                      <!-- Guarda al salir del campo o con Enter, no en cada tecla. -->
                      <sol-input
                        type="number"
                        [label]="text.fieldStoryPoints()"
                        [ngModel]="pointsDraft()"
                        (ngModelChange)="pointsDraft.set($event)"
                        (focusout)="commitPoints()"
                        (keydown.enter)="commitPoints()"
                        [error]="pointsError() ? text.fieldStoryPointsInteger() : ''"
                      />
                    }
                    @if (effectiveEstimationMode() === 'hours' || effectiveEstimationMode() === 'both') {
                      <sol-input
                        [label]="text.fieldOriginalEstimate()"
                        [placeholder]="text.fieldOriginalEstimatePlaceholder()"
                        [ngModel]="estimateDraft()"
                        (ngModelChange)="estimateDraft.set($event)"
                        (focusout)="commitEstimate()"
                        (keydown.enter)="commitEstimate()"
                        [error]="estimateError() ? text.fieldOriginalEstimateInvalid() : ''"
                      />
                    }
                    @if (t.risk_flag && t.risk_reason) {
                      <div class="tdp__risk" role="note">
                        <strong>{{ text.fieldAtRisk() }}</strong>
                        <p>{{ t.risk_reason }}</p>
                      </div>
                    }
                    </div>
                  </sol-card>

                  <!-- Descripción -->
                  <sol-card class="tdp__description">
                    <h3 class="tdp__section-title">{{ text.description() }}</h3>
                    <sol-rich-editor
                      [ngModel]="t.description ?? ''"
                      (ngModelChange)="updateField('description', $event)"
                      [mentionableUsers]="mentionableUsers()"
                      [linkableTasks]="linkableTasks()"
                    />
                  </sol-card>
                </div>
              }

              @case ('subtasks') {
                <sol-card>
                  <div class="tdp__stack">
                  <div class="tdp__section-head">
                    <h3 class="tdp__section-title">{{ text.subtasksTitle() }}</h3>
                    @if (!showSubtaskForm()) {
                      <sol-button type="button" variant="secondary" size="sm"
                                  (clicked)="showSubtaskForm.set(true)">
                        + {{ text.subtaskNew() }}
                      </sol-button>
                    }
                  </div>

                  @if (t.subtask_progress !== null) {
                    <div class="tdp__progress">
                      <div class="tdp__progress-label">
                        <span>{{ text.subtaskProgress() }}</span>
                        <span>{{ (t.subtask_progress! * 100) | number:'1.0-0' }}%</span>
                      </div>
                      <div class="tdp__progress-track" role="progressbar"
                           [attr.aria-valuenow]="(t.subtask_progress! * 100) | number:'1.0-0'"
                           aria-valuemin="0" aria-valuemax="100"
                           [attr.aria-label]="text.subtaskProgress()">
                        <div class="tdp__progress-bar" [style.width.%]="t.subtask_progress! * 100"></div>
                      </div>
                    </div>
                  }

                  @if (subtasks().length === 0 && !showSubtaskForm()) {
                    <p class="tdp__empty">{{ text.subtasksEmpty() }}</p>
                  }

                  <ul class="tdp__list">
                    @for (sub of subtasks(); track sub.id) {
                      <li class="tdp__list-item">
                        <sol-badge [variant]="statusTone(sub.status)">{{ statusLabel(sub.status) }}</sol-badge>
                        @if (sub.task_key) {
                          <span class="tdp__code">{{ sub.task_key }}</span>
                          <a [routerLink]="['/task', sub.task_key]" class="tdp__inline-link tdp__grow">
                            {{ sub.title }}
                          </a>
                        } @else {
                          <span class="tdp__grow">{{ sub.title }}</span>
                        }
                      </li>
                    }
                  </ul>

                  @if (showSubtaskForm()) {
                    <div class="tdp__form">
                      <sol-input
                        [label]="text.subtaskTitleField()"
                        [ngModel]="newSubtaskTitle()"
                        (ngModelChange)="newSubtaskTitle.set($event)"
                        [placeholder]="text.subtaskTitleField()"
                      />
                      <sol-input
                        type="number"
                        [label]="text.subtaskHours()"
                        [ngModel]="newSubtaskHours()"
                        (ngModelChange)="newSubtaskHours.set($event)"
                        placeholder="0"
                      />
                      @if (!newSubtaskTitle().trim()) {
                        <p class="tdp__hint">{{ text.subtaskTitleRequired() }}</p>
                      }
                      <div class="tdp__form-actions">
                        <sol-button type="button" variant="ghost" size="sm"
                                    (clicked)="showSubtaskForm.set(false)">
                          {{ text.subtaskCancel() }}
                        </sol-button>
                        <sol-button type="button" variant="primary" size="sm"
                                    [loading]="savingSubtask()"
                                    [disabled]="!newSubtaskTitle().trim()"
                                    (clicked)="createSubtask()">
                          {{ text.subtaskSave() }}
                        </sol-button>
                      </div>
                    </div>
                  }
                  </div>
                </sol-card>
              }

              @case ('comments') {
                <sol-card>
                  <div class="tdp__stack">
                  <h3 class="tdp__section-title">{{ text.commentsTitle() }}</h3>

                  @if (comments().length === 0) {
                    <p class="tdp__empty">{{ text.commentsEmpty() }}</p>
                  }

                  <ul class="tdp__comments">
                    @for (comment of comments(); track comment.id) {
                      <li class="tdp__comment">
                        <sol-avatar [name]="authorName(comment.author_id)" size="sm" />
                        <div class="tdp__comment-body">
                          <div class="tdp__comment-head">
                            <strong>{{ authorName(comment.author_id) }}</strong>
                            <span class="tdp__muted">{{ dateTimeText(comment.created_at) }}</span>
                            @if (auth.user()?.id === comment.author_id && editingCommentId() !== comment.id) {
                              <span class="tdp__comment-actions">
                                <button type="button" class="tdp__text-button"
                                        (click)="startEditComment(comment)"
                                        [attr.aria-label]="text.commentEditAria()">
                                  {{ text.commentEdit() }}
                                </button>
                                <button type="button" class="tdp__text-button tdp__text-button--danger"
                                        (click)="deleteComment(comment.id)"
                                        [attr.aria-label]="text.commentDeleteAria()">
                                  {{ text.commentDelete() }}
                                </button>
                              </span>
                            }
                          </div>

                          @if (editingCommentId() === comment.id) {
                            <sol-rich-editor
                              [ngModel]="editBody()"
                              (ngModelChange)="editBody.set($event)"
                              [mentionableUsers]="mentionableUsers()"
                              [linkableTasks]="linkableTasks()"
                            />
                            <div class="tdp__form-actions">
                              <sol-button type="button" variant="ghost" size="sm" (clicked)="cancelEditComment()">
                                {{ text.commentCancelEdit() }}
                              </sol-button>
                              <sol-button type="button" variant="primary" size="sm" (clicked)="saveEditComment()">
                                {{ text.commentSaveEdit() }}
                              </sol-button>
                            </div>
                          } @else {
                            <div class="tdp__prose" [innerHTML]="comment.body"></div>
                          }

                          @if ((commentAttachments()[comment.id] ?? []).length > 0) {
                            <ul class="tdp__files">
                              @for (att of commentAttachments()[comment.id]; track att.id) {
                                <li class="tdp__file">
                                  <span class="tdp__grow tdp__truncate">{{ att.original_name }}</span>
                                  <span class="tdp__muted">{{ formatBytes(att.size_bytes) }}</span>
                                  <button type="button" class="tdp__text-button"
                                          (click)="downloadAttachment(att)"
                                          [attr.aria-label]="text.commentDownloadAria()">
                                    {{ text.commentDownload() }}
                                  </button>
                                </li>
                              }
                            </ul>
                          }

                          <label class="tdp__text-button">
                            {{ text.commentUpload() }}
                            <input type="file" class="sr-only"
                                   (change)="uploadCommentFile(comment.id, $event)"
                                   [attr.aria-label]="text.commentUploadAria()" />
                          </label>
                        </div>
                      </li>
                    }
                  </ul>

                  <div class="tdp__new-comment">
                    <sol-rich-editor
                      [ngModel]="commentBody()"
                      (ngModelChange)="commentBody.set($event)"
                      [mentionableUsers]="mentionableUsers()"
                      [linkableTasks]="linkableTasks()"
                    />
                    <div class="tdp__form-actions">
                      <sol-button type="button" variant="primary" size="sm"
                                  [loading]="savingComment()"
                                  [disabled]="!commentBody().trim()"
                                  (clicked)="addComment()">
                        {{ text.commentSubmit() }}
                      </sol-button>
                    </div>
                  </div>
                  </div>
                </sol-card>
              }

              @case ('attachments') {
                <sol-card>
                  <div class="tdp__stack">
                  <div class="tdp__section-head">
                    <h3 class="tdp__section-title">{{ text.attachmentsTitle() }}</h3>
                    <label class="tdp__link-button">
                      + {{ text.attachmentUpload() }}
                      <input type="file" class="sr-only"
                             (change)="uploadTaskFile($event)"
                             [attr.aria-label]="text.attachmentUploadAria()" />
                    </label>
                  </div>
                  @if (taskAttachments().length === 0) {
                    <p class="tdp__empty">{{ text.attachmentsEmpty() }}</p>
                  }
                  <ul class="tdp__files">
                    @for (att of taskAttachments(); track att.id) {
                      <li class="tdp__file">
                        <span class="tdp__grow tdp__truncate">{{ att.original_name }}</span>
                        <span class="tdp__muted">{{ formatBytes(att.size_bytes) }}</span>
                        <button type="button" class="tdp__text-button"
                                (click)="downloadAttachment(att)"
                                [attr.aria-label]="text.attachmentDownloadAria()">
                          {{ text.attachmentDownload() }}
                        </button>
                      </li>
                    }
                  </ul>
                  </div>
                </sol-card>
              }
            }
          </div>
        </div>
      }
    }
  }
  `,
  styles: `
    :host { display: block; }

    .tdp {
      display: flex;
      flex-direction: column;
      gap: var(--sol-space-md);
      max-width: 1120px;
      margin: 0 auto;
    }

    .tdp__state {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--sol-space-sm);
      padding: var(--sol-space-xl) var(--sol-space-md);
      text-align: center;
      color: var(--sol-color-text-muted);
      font-size: var(--sol-font-size-sm);
    }

    .tdp__alert {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--sol-space-sm);
      padding: var(--sol-space-sm) var(--sol-space-md);
      border: 1px solid color-mix(in srgb, var(--sol-color-danger) 40%, transparent);
      border-radius: var(--sol-border-radius-md);
      background: color-mix(in srgb, var(--sol-color-danger) 10%, transparent);
      color: var(--sol-color-danger);
      font-size: var(--sol-font-size-sm);
    }

    .tdp__stack.tdp__stack--sm { gap: var(--sol-space-sm); }

    .tdp__ids, .tdp__actions, .tdp__badges {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--sol-space-sm);
      min-width: 0;
    }

    .tdp__code {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: var(--sol-font-size-sm);
      font-weight: 600;
      color: var(--sol-color-primary);
    }

    .tdp__source {
      padding: 2px 10px;
      border-radius: var(--sol-border-radius-full);
      background: var(--sol-bg-sunken);
      color: var(--sol-color-text-secondary);
      font-size: var(--sol-font-size-xs);
    }

    .tdp__title {
      margin: 0;
      font-size: var(--sol-font-size-xl);
      line-height: 1.3;
      color: var(--sol-color-text-primary);
      overflow-wrap: anywhere;
    }

    .tdp__title--compact { font-size: var(--sol-font-size-lg); font-weight: 600; }

    .tdp__meta {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: var(--sol-space-sm) var(--sol-space-md);
      margin: var(--sol-space-xs) 0 0;
      padding-top: var(--sol-space-sm);
      border-top: 1px solid var(--sol-border-color-default);
    }

    .tdp__meta-item { min-width: 0; }

    .tdp__meta dt {
      font-size: var(--sol-font-size-xs);
      color: var(--sol-color-text-muted);
    }

    .tdp__meta dd {
      margin: 2px 0 0;
      font-size: var(--sol-font-size-sm);
      color: var(--sol-color-text-primary);
    }

    .tdp__person {
      display: flex;
      align-items: center;
      gap: var(--sol-space-xs);
    }

    .tdp__muted { color: var(--sol-color-text-muted); }

    .tdp__tab-content { padding-top: var(--sol-space-xs); }

    .tdp__detail {
      display: grid;
      gap: var(--sol-space-md);
    }

    @media (min-width: 900px) {
      .tdp:not(.tdp--compact) .tdp__detail {
        grid-template-columns: minmax(0, 1fr) 320px;
      }
      .tdp:not(.tdp--compact) .tdp__fields { order: 2; align-self: start; }
      .tdp:not(.tdp--compact) .tdp__description { order: 1; }
    }

    .tdp__risk {
      padding: var(--sol-space-sm);
      border-radius: var(--sol-border-radius-md);
      background: color-mix(in srgb, var(--sol-color-danger) 10%, transparent);
      color: var(--sol-color-danger);
      font-size: var(--sol-font-size-sm);
    }

    .tdp__risk p { margin: var(--sol-space-xs) 0 0; }

    .tdp__stack {
      display: flex;
      flex-direction: column;
      gap: var(--sol-space-md);
    }

    .tdp__header-top, .tdp__section-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--sol-space-sm); }

    .tdp__section-title {
      margin: 0 0 var(--sol-space-sm);
      font-size: var(--sol-font-size-sm);
      font-weight: 600;
      color: var(--sol-color-text-secondary);
    }

    .tdp__section-head .tdp__section-title { margin: 0; }

    .tdp__empty {
      margin: 0;
      padding: var(--sol-space-md);
      border-radius: var(--sol-border-radius-md);
      background: var(--sol-bg-sunken);
      color: var(--sol-color-text-secondary);
      font-size: var(--sol-font-size-sm);
    }

    .tdp__progress-label { display: flex; justify-content: space-between; margin-bottom: var(--sol-space-xs); font-size: var(--sol-font-size-xs); color: var(--sol-color-text-muted); }
    .tdp__progress-track { height: 6px; border-radius: var(--sol-border-radius-full); background: var(--sol-bg-sunken); overflow: hidden; }
    .tdp__progress-bar { height: 100%; background: var(--sol-color-primary); }

    .tdp__list, .tdp__files, .tdp__comments {
      display: flex;
      flex-direction: column;
      gap: var(--sol-space-xs);
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .tdp__comments { gap: var(--sol-space-md); }

    .tdp__list-item, .tdp__file {
      display: flex;
      align-items: center;
      gap: var(--sol-space-sm);
      min-height: 40px;
      padding: var(--sol-space-xs) var(--sol-space-sm);
      border-radius: var(--sol-border-radius-md);
      font-size: var(--sol-font-size-sm);
      color: var(--sol-color-text-primary);
    }

    .tdp__list-item:hover { background: var(--sol-bg-sunken); }

    .tdp__grow { flex: 1 1 auto; min-width: 0; }
    .tdp__truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    .tdp__inline-link {
      color: var(--sol-color-text-primary);
      text-decoration: none;
    }

    .tdp__inline-link:hover, .tdp__inline-link:focus-visible {
      color: var(--sol-color-primary);
      text-decoration: underline;
    }

    .tdp__link-button {
      display: inline-flex;
      align-items: center;
      gap: var(--sol-space-xs);
      min-height: 36px;
      padding: 0 var(--sol-space-md);
      border: 1px solid var(--sol-border-color-default);
      border-radius: var(--sol-border-radius-md);
      background: var(--sol-bg-surface);
      color: var(--sol-color-text-primary);
      font-size: var(--sol-font-size-sm);
      font-weight: 500;
      text-decoration: none;
      cursor: pointer;
    }

    .tdp__link-button:hover { border-color: var(--sol-color-primary); color: var(--sol-color-primary); }

    .tdp__text-button {
      padding: 2px 4px;
      border: 0;
      background: transparent;
      color: var(--sol-color-primary);
      font-size: var(--sol-font-size-xs);
      cursor: pointer;
    }

    .tdp__text-button:hover { text-decoration: underline; }
    .tdp__text-button--danger { color: var(--sol-color-danger); }

    .tdp__form, .tdp__new-comment {
      display: flex;
      flex-direction: column;
      gap: var(--sol-space-sm);
      padding-top: var(--sol-space-md);
      border-top: 1px solid var(--sol-border-color-default);
    }

    .tdp__form-actions {
      display: flex;
      justify-content: flex-end;
      gap: var(--sol-space-sm);
      margin-top: var(--sol-space-xs);
    }

    .tdp__hint { margin: 0; font-size: var(--sol-font-size-xs); color: var(--sol-color-text-muted); }

    .tdp__comment { display: flex; align-items: flex-start; gap: var(--sol-space-sm); }

    .tdp__comment-body {
      flex: 1 1 auto;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: var(--sol-space-xs);
    }

    .tdp__comment-head {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: var(--sol-space-sm);
      font-size: var(--sol-font-size-xs);
    }

    .tdp__comment-actions { margin-left: auto; display: inline-flex; gap: var(--sol-space-xs); }

    .tdp__prose {
      font-size: var(--sol-font-size-sm);
      color: var(--sol-color-text-primary);
      overflow-wrap: anywhere;
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
    backAria: this.i18n.t('taskDetail.backAria'),
    openFullPage: this.i18n.t('taskDetail.openFullPage'),
    openFullPageAria: this.i18n.t('taskDetail.openFullPageAria'),
    description: this.i18n.t('taskDetail.description'),
    loading: this.i18n.t('taskDetail.states.loading'),
    notFoundTitle: this.i18n.t('taskDetail.states.notFoundTitle'),
    forbiddenTitle: this.i18n.t('taskDetail.states.forbiddenTitle'),
    forbiddenMessage: this.i18n.t('taskDetail.states.forbiddenMessage'),
    goProjects: this.i18n.t('taskDetail.states.goProjects'),
    loadError: this.i18n.t('taskDetail.errors.loadData'),
    retry: this.i18n.t('taskDetail.states.retry'),
    dismiss: this.i18n.t('taskDetail.states.dismiss'),
    sourceLabel: this.i18n.t('taskDetail.sources.label'),
    metaProject: this.i18n.t('taskDetail.meta.project'),
    metaDue: this.i18n.t('taskDetail.meta.due'),
    metaStart: this.i18n.t('taskDetail.meta.start'),
    metaCreated: this.i18n.t('taskDetail.meta.created'),
    metaCompleted: this.i18n.t('taskDetail.meta.completed'),
    metaNoDate: this.i18n.t('taskDetail.meta.noDate'),
    subtasksTitle: this.i18n.t('taskDetail.subtasks.title'),
    subtasksEmpty: this.i18n.t('taskDetail.subtasks.empty'),
    subtaskNew: this.i18n.t('taskDetail.subtasks.new'),
    subtaskProgress: this.i18n.t('taskDetail.subtasks.progress'),
    subtaskTitleField: this.i18n.t('taskDetail.subtasks.titleField'),
    subtaskTitleRequired: this.i18n.t('taskDetail.subtasks.titleRequired'),
    subtaskHours: this.i18n.t('taskDetail.subtasks.hours'),
    subtaskSave: this.i18n.t('taskDetail.subtasks.save'),
    subtaskCancel: this.i18n.t('taskDetail.subtasks.cancel'),
    commentsTitle: this.i18n.t('taskDetail.comments.title'),
    commentsEmpty: this.i18n.t('taskDetail.comments.empty'),
    commentEdit: this.i18n.t('taskDetail.comments.edit'),
    commentEditAria: this.i18n.t('taskDetail.comments.editAria'),
    commentDelete: this.i18n.t('taskDetail.comments.delete'),
    commentDeleteAria: this.i18n.t('taskDetail.comments.deleteAria'),
    commentSaveEdit: this.i18n.t('taskDetail.comments.saveEdit'),
    commentCancelEdit: this.i18n.t('taskDetail.comments.cancelEdit'),
    commentDownload: this.i18n.t('taskDetail.comments.download'),
    commentDownloadAria: this.i18n.t('taskDetail.comments.downloadAria'),
    commentUpload: this.i18n.t('taskDetail.comments.upload'),
    commentUploadAria: this.i18n.t('taskDetail.comments.uploadAria'),
    commentSubmit: this.i18n.t('taskDetail.comments.submit'),
    attachmentsTitle: this.i18n.t('taskDetail.attachments.title'),
    attachmentsEmpty: this.i18n.t('taskDetail.attachments.empty'),
    attachmentDownload: this.i18n.t('taskDetail.attachments.download'),
    attachmentDownloadAria: this.i18n.t('taskDetail.attachments.downloadAria'),
    attachmentUpload: this.i18n.t('taskDetail.attachments.upload'),
    attachmentUploadAria: this.i18n.t('taskDetail.attachments.uploadAria'),
    fieldStatus: this.i18n.t('taskDetail.fields.status'),
    fieldStatusPlaceholder: this.i18n.t('taskDetail.fields.statusPlaceholder'),
    fieldPriority: this.i18n.t('taskDetail.fields.priority'),
    fieldPriorityPlaceholder: this.i18n.t('taskDetail.fields.priorityPlaceholder'),
    fieldAssignee: this.i18n.t('taskDetail.fields.assignee'),
    fieldAssigneePlaceholder: this.i18n.t('taskDetail.fields.assigneePlaceholder'),
    fieldSprint: this.i18n.t('taskDetail.fields.sprint'),
    fieldSprintNone: this.i18n.t('taskDetail.fields.sprintNone'),
    fieldOriginalEstimate: this.i18n.t('taskDetail.fields.originalEstimate'),
    fieldOriginalEstimatePlaceholder: this.i18n.t('taskDetail.fields.originalEstimatePlaceholder'),
    fieldOriginalEstimateInvalid: this.i18n.t('taskDetail.fields.originalEstimateInvalid'),
    fieldStoryPoints: this.i18n.t('taskDetail.fields.storyPoints'),
    fieldStoryPointsInteger: this.i18n.t('taskDetail.fields.storyPointsInteger'),
    fieldAtRisk: this.i18n.t('taskDetail.fields.atRisk'),
  } as const;

  readonly task = signal<TaskDetail | null>(null);
  readonly project = signal<Project | null>(null);
  readonly subtasks = signal<TaskDetail[]>([]);
  readonly comments = signal<Comment[]>([]);
  readonly taskAttachments = signal<Attachment[]>([]);
  readonly commentAttachments = signal<Record<string, Attachment[]>>({});
  readonly members = signal<Member[]>([]);
  readonly projectTasks = signal<TaskDetail[]>([]);
  readonly state = signal<LoadState>('loading');
  /** Último guardado fallido (campo, comentario, subtarea o adjunto). */
  readonly actionError = signal<string | null>(null);
  readonly activeTab = signal<TabId>('detail');
  readonly commentBody = signal('');
  readonly savingComment = signal(false);
  readonly showSubtaskForm = signal(false);
  readonly newSubtaskTitle = signal('');
  readonly newSubtaskHours = signal<string | number | null>(null);
  readonly savingSubtask = signal(false);
  readonly editingCommentId = signal<string | null>(null);
  readonly editBody = signal('');

  /** Borradores de estimación: se guardan al salir del campo o con Enter. */
  readonly pointsDraft = signal<string>('');
  readonly estimateDraft = signal<string>('');

  /** El texto de estimación original no parsea ("4w 2d 3h" esperado). */
  readonly estimateError = signal(false);
  /** Los puntos de historia no son un entero no negativo. */
  readonly pointsError = signal(false);

  /** Configuración de metodología del proyecto de la tarea (cargada aquí). */
  readonly methodologyInfo = signal<MethodologyInfo | null>(null);

  /**
   * Sprints cargados por el propio widget cuando el host no los provee
   * (p. ej. deep-link `/task/:key`, donde la página solo pasa `taskKey`).
   */
  readonly fallbackSprints = signal<Sprint[]>([]);

  readonly effectiveSprintsEnabled = computed(
    () => this.sprintsEnabled() || !!this.methodologyInfo()?.sprints_enabled,
  );

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

  readonly effectiveEstimationMode = computed<EstimationMode>(
    () =>
      this.estimationMode() ??
      this.methodologyInfo()?.estimation_mode ??
      'both',
  );

  readonly priorityOptions = computed(() => {
    this.i18n.activeLang();
    return ['critical', 'high', 'medium', 'low'].map(value => ({
      value,
      label: this.i18n.translate(`taskDetail.priorities.${value}`),
    }));
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

  readonly sprintOptions = computed(() => [
    { value: '', label: this.text.fieldSprintNone() },
    ...this.effectiveSprints().map(s => ({ value: s.id, label: s.name })),
  ]);

  /** Pestañas con conteo, para que se sepa qué hay sin abrirlas. */
  readonly tabs = computed<SolTabItem[]>(() => {
    this.i18n.activeLang();
    const label = (key: string, count: number) =>
      this.i18n.translate(`taskDetail.tabs.${key}`, { count });
    return [
      { id: 'detail', label: this.i18n.translate('taskDetail.tabs.detail') },
      { id: 'subtasks', label: label('subtasks', this.subtasks().length) },
      { id: 'comments', label: label('comments', this.comments().length) },
      { id: 'attachments', label: label('attachments', this.taskAttachments().length) },
    ];
  });

  /** Origen legible: «Checklist de tareas · T-205», «Jira · CP-13». */
  readonly sourceText = computed<string | null>(() => {
    this.i18n.activeLang();
    const t = this.task();
    if (!t?.source) return null;
    const key = SOURCE_KEYS[t.source];
    const name = key ? this.i18n.translate(key) : t.source;
    const ref = t.external_key ? t.external_key.split(':').pop() : '';
    return ref && ref !== t.task_key ? `${name} · ${ref}` : name;
  });

  readonly notFoundMessage = computed(() => {
    this.i18n.activeLang();
    return this.i18n.translate('taskDetail.states.notFoundMessage', { key: this.taskKey() });
  });

  /** Última columna del flujo = cerrada (misma regla del listado de proyectos). */
  private readonly doneStatus = computed(() => {
    const allowed = this.methodologyInfo()?.allowed_statuses ?? [];
    return allowed.length > 0 ? allowed[allowed.length - 1] : null;
  });

  private readonly memberNames = computed(() => {
    const map = new Map<string, string>();
    this.members().forEach(m => map.set(m.user_id, m.full_name));
    return map;
  });

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

  retry(): void {
    this.loadAll(this.taskKey());
  }

  onTabChange(id: string): void {
    this.activeTab.set(id as TabId);
  }

  /**
   * Carga todo el detalle de la tarea `key`.
   *
   * Robustez ante navegación rápida entre tareas (mismo widget, distinto
   * `taskKey`): cada respuesta se descarta con `isStale(key)` si el key ya
   * cambió cuando llega, y toda subscripción se corta con
   * `takeUntilDestroyed` al destruir el widget.
   */
  private loadAll(key: string): void {
    this.state.set('loading');
    this.actionError.set(null);
    this.activeTab.set('detail');
    this.task.set(null);
    this.project.set(null);
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
          const t = res.data;
          this.setTask(t);
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
                this.project.set(data.project.data);
                this.methodologyInfo.set(data.project.data.methodology_info ?? null);
                this.state.set('ready');
                this.loadFallbackSprints(key, t.project_id);
                data.comments.data.forEach(c => {
                  this.svc.getCommentAttachments(c.id)
                    .pipe(takeUntilDestroyed(this.destroyRef))
                    .subscribe(r => {
                      if (this.isStale(key)) return;
                      this.commentAttachments.update(map => ({ ...map, [c.id]: r.data }));
                    });
                });
              },
              error: (err: HttpErrorResponse) => {
                if (this.isStale(key)) return;
                this.state.set(this.stateForError(err));
                console.error(err);
              },
            });
        },
        error: (err: HttpErrorResponse) => {
          if (this.isStale(key)) return;
          this.state.set(this.stateForError(err));
          console.error(err);
        },
      });
  }

  /** 404/422 (clave inexistente o mal formada) → no encontrada; 403 → sin permiso. */
  private stateForError(err: HttpErrorResponse): LoadState {
    if (err.status === 404 || err.status === 422) return 'notFound';
    if (err.status === 403) return 'forbidden';
    return 'error';
  }

  private isStale(key: string): boolean {
    return key !== this.taskKey();
  }

  /** Guarda la tarea y sincroniza los borradores de estimación. */
  private setTask(t: TaskDetail): void {
    this.task.set(t);
    this.pointsDraft.set(t.estimation_points == null ? '' : String(t.estimation_points));
    this.estimateDraft.set(formatOriginalEstimate(t.estimation_hours));
  }

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

  private failAction(err: unknown): void {
    console.error(err);
    const detail = err instanceof HttpErrorResponse ? err.error?.detail : null;
    this.actionError.set(
      typeof detail === 'string' && detail
        ? detail
        : this.i18n.translate('taskDetail.states.saveError'),
    );
  }

  updateField(field: string, value: unknown): void {
    const t = this.task();
    if (!t) return;
    if ((t as unknown as Record<string, unknown>)[field] === value) return;
    this.svc.updateTask(t.id, { [field]: value })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.actionError.set(null);
          this.setTask(res.data);
          this.taskChanged.emit(res.data);
        },
        error: (err) => this.failAction(err),
      });
  }

  /** Puntos de historia: vacío → null; solo enteros no negativos. */
  commitPoints(): void {
    const raw = String(this.pointsDraft() ?? '').trim();
    const value = raw === '' ? null : Number(raw);
    const invalid = value !== null && (!Number.isInteger(value) || value < 0);
    this.pointsError.set(invalid);
    if (invalid) return;
    if (value === (this.task()?.estimation_points ?? null)) return;
    this.updateField('estimation_points', value);
  }

  /**
   * Estimación original estilo Jira: parsea "4w 2d 3h" a horas (1w = 5 días
   * laborables, 1d = 8 horas). Vacío limpia; un texto que no parsea muestra
   * el error y no guarda.
   */
  commitEstimate(): void {
    const raw = String(this.estimateDraft() ?? '').trim();
    if (raw === formatOriginalEstimate(this.task()?.estimation_hours)) {
      this.estimateError.set(false);
      return;
    }
    if (raw === '') {
      this.estimateError.set(false);
      this.updateField('estimation_hours', null);
      return;
    }
    const hours = parseOriginalEstimate(raw);
    if (hours === null) {
      this.estimateError.set(true);
      return;
    }
    this.estimateError.set(false);
    this.updateField('estimation_hours', hours);
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
          this.svc.getCommentAttachments(res.data.id)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe(r => {
              this.commentAttachments.update(map => ({ ...map, [res.data.id]: r.data }));
            });
        },
        error: (err) => {
          this.savingComment.set(false);
          this.failAction(err);
        },
      });
  }

  deleteComment(id: string): void {
    this.svc.deleteComment(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => this.comments.update(cs => cs.filter(c => c.id !== id)),
        error: (err) => this.failAction(err),
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
        error: (err) => this.failAction(err),
      });
  }

  cancelEditComment(): void {
    this.editingCommentId.set(null);
    this.editBody.set('');
  }

  createSubtask(): void {
    const t = this.task();
    if (!t || !this.newSubtaskTitle().trim()) return;
    const rawHours = this.newSubtaskHours();
    const hours = rawHours === null || rawHours === '' ? null : Number(rawHours);
    this.savingSubtask.set(true);
    this.svc.createSubtask(t.project_id, {
      title: this.newSubtaskTitle(),
      estimation_hours: hours !== null && Number.isFinite(hours) ? hours : null,
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
                this.setTask(r.data);
                this.taskChanged.emit(r.data);
              });
          }
        },
        error: (err) => {
          this.savingSubtask.set(false);
          this.failAction(err);
        },
      });
  }

  downloadAttachment(att: Attachment): void {
    this.svc.downloadAttachment(att.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: blob => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = att.original_name;
          a.click();
          URL.revokeObjectURL(url);
        },
        error: (err) => this.failAction(err),
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
        error: (err) => this.failAction(err),
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
        error: (err) => this.failAction(err),
      });
  }

  protected readonly formatBytes = formatBytes;

  protected statusLabel(status: string): string {
    return statusDisplay(status);
  }

  /** Cerrada = última columna; primera = sin iniciar; el resto, en curso. */
  protected statusTone(status: string): BadgeTone {
    const allowed = this.methodologyInfo()?.allowed_statuses ?? [];
    if (status === this.doneStatus()) return 'success';
    if (status === 'cancelled') return 'neutral';
    if (allowed.length > 0 && status === allowed[0]) return 'neutral';
    return 'info';
  }

  protected priorityTone(priority: string): BadgeTone {
    return PRIORITY_TONE[priority] ?? 'neutral';
  }

  protected priorityLabel(priority: string): string {
    return this.i18n.translate(`taskDetail.priorities.${priority}`);
  }

  protected typeLabel(type: string | null | undefined): string {
    return type ? (TASK_TYPE_LABELS[type as TaskType] ?? type) : '';
  }

  protected projectLabel(p: Project): string {
    const code = (p as Project & { code?: string | null }).code;
    return code ? `${code} · ${p.name}` : p.name;
  }

  protected authorName(userId: string): string {
    return this.memberNames().get(userId) ?? this.i18n.translate('taskDetail.comments.authorUnknown');
  }

  /** Fecha en hora de Bogotá, con año: «4 oct 2026». */
  protected dateText(value: string | null | undefined): string {
    if (!value) return this.text.metaNoDate();
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return this.text.metaNoDate();
    return date.toLocaleDateString('es-CO', {
      day: 'numeric', month: 'short', year: 'numeric', timeZone: 'America/Bogota',
    });
  }

  protected dateTimeText(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString('es-CO', {
      day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit',
      timeZone: 'America/Bogota',
    });
  }
}
