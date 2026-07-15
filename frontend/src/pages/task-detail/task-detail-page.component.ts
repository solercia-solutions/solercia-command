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
         aria-label="Volver al proyecto">
        ← Volver
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
          <h2 class="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">Descripción</h2>
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
            <h2 class="text-sm font-semibold text-muted uppercase tracking-wide">Subtareas</h2>
            <button
              class="text-xs text-brand hover:underline"
              (click)="showSubtaskForm.set(true)"
              aria-label="Agregar subtarea">
              + Nueva subtarea
            </button>
          </div>

          @if (task()!.subtask_progress !== null) {
            <div class="mb-3">
              <div class="mb-1 flex justify-between text-xs text-muted">
                <span>Progreso</span>
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
                label="Título de la subtarea"
                [ngModel]="newSubtaskTitle()"
                (ngModelChange)="newSubtaskTitle.set($event)"
                placeholder="Título de la subtarea"
              />
              <div>
                <label class="mb-1 block text-xs text-muted">Horas estimadas</label>
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
                  aria-label="Guardar subtarea">
                  {{ savingSubtask() ? 'Guardando...' : 'Guardar' }}
                </button>
                <button
                  class="rounded border border-border px-3 py-1.5 text-xs text-muted hover:text-text"
                  (click)="showSubtaskForm.set(false)"
                  aria-label="Cancelar creación de subtarea">
                  Cancelar
                </button>
              </div>
            </div>
          }
        </div>

        <!-- Comments -->
        <div class="rounded-lg border border-border bg-surface p-4">
          <h2 class="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">Comentarios</h2>

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
                                aria-label="Editar comentario">
                          Editar
                        </button>
                        <button class="text-xs text-danger/70 hover:text-danger"
                                (click)="deleteComment(comment.id)"
                                aria-label="Eliminar comentario">
                          Eliminar
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
                          aria-label="Guardar edición">
                          Guardar
                        </button>
                        <button
                          class="rounded border border-border px-3 py-1.5 text-xs text-muted hover:text-text"
                          (click)="cancelEditComment()"
                          aria-label="Cancelar edición">
                          Cancelar
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
                                    aria-label="Descargar archivo">
                              Descargar
                            </button>
                          </li>
                        }
                      </ul>
                    }

                    <!-- Upload to comment -->
                    <label class="mt-1 inline-block cursor-pointer text-xs text-muted hover:text-text">
                      Subir archivo
                      <input type="file" class="sr-only"
                             (change)="uploadCommentFile(comment.id, $event)"
                             aria-label="Subir archivo al comentario" />
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
                aria-label="Agregar comentario">
                {{ savingComment() ? 'Enviando...' : 'Comentar' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Task attachments -->
        <div class="rounded-lg border border-border bg-surface p-4">
          <h2 class="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">Archivos adjuntos</h2>
          <ul class="space-y-2 mb-3">
            @for (att of taskAttachments(); track att.id) {
              <li class="flex items-center gap-2 text-sm">
                <span class="flex-1 truncate text-text">{{ att.original_name }}</span>
                <span class="text-xs text-muted">{{ formatBytes(att.size_bytes) }}</span>
                <button class="text-xs text-brand hover:underline"
                        (click)="downloadAttachment(att)"
                        aria-label="Descargar archivo adjunto">
                  Descargar
                </button>
              </li>
            }
          </ul>
          <label class="inline-flex cursor-pointer items-center gap-1 rounded border border-border px-3 py-1.5 text-xs text-muted hover:text-text">
            + Subir archivo
            <input type="file" class="sr-only"
                   (change)="uploadTaskFile($event)"
                   aria-label="Subir archivo adjunto" />
          </label>
        </div>

      </div>

      <!-- RIGHT sidebar -->
      <aside class="space-y-4">
        <div class="rounded-lg border border-border bg-surface p-4 space-y-4">

          <!-- Status -->
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Estado</label>
            <sol-select
              [options]="statusOptions()"
              [ngModel]="task()!.status"
              (ngModelChange)="updateField('status', $event)"
              placeholder="Seleccionar estado"
            />
          </div>

          <!-- Priority -->
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Prioridad</label>
            <sol-select
              [options]="priorityOptions"
              [ngModel]="task()!.priority"
              (ngModelChange)="updateField('priority', $event)"
              placeholder="Seleccionar prioridad"
            />
          </div>

          <!-- Assignee -->
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Responsable</label>
            <sol-select
              [options]="assigneeOptions()"
              [ngModel]="task()!.assignee_id ?? ''"
              (ngModelChange)="updateField('assignee_id', $event || null)"
              placeholder="Sin asignar"
            />
          </div>

          <!-- Estimation hours -->
          @if (task()!.estimation_hours !== null && task()!.estimation_hours !== undefined) {
            <div>
              <label class="mb-1 block text-xs font-medium text-muted">Horas estimadas</label>
              <p class="text-sm text-text">{{ task()!.estimation_hours }}h</p>
            </div>
          }

          <!-- Estimation points -->
          @if (task()!.estimation_points !== null && task()!.estimation_points !== undefined) {
            <div>
              <label class="mb-1 block text-xs font-medium text-muted">Story points</label>
              <p class="text-sm text-text">{{ task()!.estimation_points }}</p>
            </div>
          }

          <!-- Due date -->
          @if (task()!.due_date) {
            <div>
              <label class="mb-1 block text-xs font-medium text-muted">Fecha límite</label>
              <p class="text-sm text-text">{{ task()!.due_date | date:'dd/MM/yyyy' }}</p>
            </div>
          }

          <!-- Risk flag -->
          @if (task()!.risk_flag) {
            <div class="rounded border border-danger/30 bg-danger/10 p-3">
              <p class="text-xs font-semibold text-danger">En riesgo</p>
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

  readonly priorityOptions = [
    { value: 'critical', label: 'Crítica' },
    { value: 'high', label: 'Alta' },
    { value: 'medium', label: 'Media' },
    { value: 'low', label: 'Baja' },
  ];

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
      this.error.set('Clave de tarea no encontrada en la URL.');
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
            this.error.set('Error al cargar los datos de la tarea.');
            this.loading.set(false);
            console.error(err);
          },
        });
      },
      error: (err) => {
        this.error.set('No se encontró la tarea.');
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
