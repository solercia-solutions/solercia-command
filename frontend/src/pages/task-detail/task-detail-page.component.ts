import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { ActivatedRoute } from '@angular/router';
import { AuthService } from '@features/auth/auth.service';
import { TaskDetailService } from '@entities/task/task-detail.service';
import { Attachment, Comment, TaskDetail, formatBytes } from '@entities/task/task-detail.model';
import { Member } from '@entities/workspace/workspace.model';
import { SolBadgeComponent } from '@shared/ui';
import { SolSelectComponent } from '@shared/ui';
import { SolRichEditorComponent } from '@shared/ui/rich-editor.component';
import { SolInputComponent } from '@shared/ui';
import { MentionUser, LinkableTask } from '@shared/ui/rich-editor.component';
import { I18nService } from '@shared/i18n';

@Component({
  selector: 'sol-task-detail-page',
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
<div class="min-h-screen bg-page px-4 py-6 md:px-8">
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
    <div class="mb-6 flex items-center gap-3">
      <a [routerLink]="['/projects', task()!.project_id]"
         class="flex items-center gap-1 text-sm text-muted hover:text-text transition-colors"
         [attr.aria-label]="text.backAria()">
        ← {{ text.back() }}
      </a>
      @if (task()!.task_key) {
        <span class="font-mono text-sm font-semibold text-brand">{{ task()!.task_key }}</span>
      }
    </div>

    <h1 class="text-2xl font-bold text-text mb-6">{{ task()!.title }}</h1>

    <!-- Two-column layout -->
    <div class="grid gap-6 md:grid-cols-[1fr_320px]">
      <!-- LEFT column -->
      <div class="space-y-6">

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

      <!-- RIGHT sidebar -->
      <aside class="space-y-4">
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

          <!-- Estimation hours -->
          @if (task()!.estimation_hours !== null && task()!.estimation_hours !== undefined) {
            <div>
              <label class="mb-1 block text-xs font-medium text-muted">{{ text.fieldEstimationHours() }}</label>
              <p class="text-sm text-text">{{ task()!.estimation_hours }}h</p>
            </div>
          }

          <!-- Estimation points -->
          @if (task()!.estimation_points !== null && task()!.estimation_points !== undefined) {
            <div>
              <label class="mb-1 block text-xs font-medium text-muted">{{ text.fieldStoryPoints() }}</label>
              <p class="text-sm text-text">{{ task()!.estimation_points }}</p>
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
    </div>
  }
</div>
  `,
})
export class TaskDetailPageComponent implements OnInit {
  protected readonly svc = inject(TaskDetailService);
  protected readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly i18n = inject(I18nService);

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    back: this.i18n.t('taskDetail.back'),
    backAria: this.i18n.t('taskDetail.backAria'),
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
  private readonly taskKey = signal<string>('');

  readonly statusOptions = computed(() => {
    const statuses = ['backlog', 'to_do', 'in_progress', 'in_review', 'done', 'cancelled'];
    return statuses.map(s => ({ value: s, label: s.replace(/_/g, ' ') }));
  });

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

  ngOnInit(): void {
    const key = this.route.snapshot.paramMap.get('key');
    if (key) {
      this.taskKey.set(key);
      this.loadAll(key);
    } else {
      this.error.set(this.i18n.translate('taskDetail.errors.missingKey'));
      this.loading.set(false);
    }
  }

  private loadAll(key: string): void {
    this.svc.getTaskByKey(key).subscribe({
      next: (res) => {
        this.task.set(res.data);
        const t = res.data;
        forkJoin({
          subtasks: this.svc.getSubtasks(t.id),
          comments: this.svc.getComments(t.id),
          attachments: this.svc.getTaskAttachments(t.id),
          members: this.svc.getMembers(t.project_id),
          projectTasks: this.svc.getProjectTasks(t.project_id),
        }).subscribe({
          next: (data) => {
            this.subtasks.set(data.subtasks.data);
            this.comments.set(data.comments.data);
            this.taskAttachments.set(data.attachments.data);
            this.members.set(data.members.data);
            this.projectTasks.set(data.projectTasks.data);
            this.loading.set(false);
            // Load comment attachments
            data.comments.data.forEach(c => {
              this.svc.getCommentAttachments(c.id).subscribe(r => {
                this.commentAttachments.update(map => ({ ...map, [c.id]: r.data }));
              });
            });
          },
          error: (err) => {
            this.error.set(this.i18n.translate('taskDetail.errors.loadData'));
            this.loading.set(false);
            console.error(err);
          },
        });
      },
      error: (err) => {
        this.error.set(this.i18n.translate('taskDetail.errors.notFound'));
        this.loading.set(false);
        console.error(err);
      },
    });
  }

  updateField(field: string, value: unknown): void {
    const t = this.task();
    if (!t) return;
    this.svc.updateTask(t.id, { [field]: value }).subscribe({
      next: (res) => this.task.set(res.data),
      error: (err) => console.error('Error actualizando campo', field, err),
    });
  }

  addComment(): void {
    const t = this.task();
    if (!t || !this.commentBody().trim()) return;
    this.savingComment.set(true);
    this.svc.createComment(t.id, this.commentBody()).subscribe({
      next: (res) => {
        this.comments.update(cs => [...cs, res.data]);
        this.commentBody.set('');
        this.savingComment.set(false);
        // Load attachments for new comment
        this.svc.getCommentAttachments(res.data.id).subscribe(r => {
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
    this.svc.deleteComment(id).subscribe({
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
    this.svc.updateComment(id, this.editBody()).subscribe({
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
    }).subscribe({
      next: (res) => {
        this.subtasks.update(ss => [...ss, res.data]);
        this.newSubtaskTitle.set('');
        this.newSubtaskHours.set(null);
        this.showSubtaskForm.set(false);
        this.savingSubtask.set(false);
        // Re-fetch task to update subtask_progress
        const key = this.taskKey();
        if (key) {
          this.svc.getTaskByKey(key).subscribe(r => this.task.set(r.data));
        }
      },
      error: (err) => {
        this.savingSubtask.set(false);
        console.error(err);
      },
    });
  }

  downloadAttachment(att: Attachment): void {
    this.svc.downloadAttachment(att.id).subscribe(blob => {
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
    this.svc.uploadTaskAttachment(t.id, file).subscribe({
      next: (res) => this.taskAttachments.update(atts => [...atts, res.data]),
      error: (err) => console.error(err),
    });
  }

  uploadCommentFile(commentId: string, event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.svc.uploadCommentAttachment(commentId, file).subscribe({
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

  priorityTone(p: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
    const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral'> = {
      critical: 'danger',
      high: 'warning',
      medium: 'info',
      low: 'neutral',
    };
    return map[p] ?? 'neutral';
  }
}
