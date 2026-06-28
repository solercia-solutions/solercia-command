import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { CardComponent } from '../../shared/ui/card.component';
import {
  PRIORITY_CHIP_CLASS,
  PRIORITY_LABELS,
  Priority,
  formatShortDate,
} from '../projects/workspace/workspace.model';
import { METHODOLOGY_LABELS, Methodology } from '../projects/project.model';
import { ExecutiveService } from './executive.service';
import { ExecutiveDashboard } from './executive.model';

/**
 * Executive ("vista de jefe") dashboard: one scannable screen with team
 * workload, what each person is doing, risks and per-project progress.
 */
@Component({
  selector: 'sp-executive',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CardComponent],
  template: `
    <section class="flex flex-col gap-6">
      <div>
        <h1 class="text-2xl font-semibold text-text">Vista de jefe</h1>
        <p class="text-sm text-muted">
          Panorama del equipo: en qué anda cada uno, riesgos y avance.
        </p>
      </div>

      @if (loading()) {
        <p class="text-sm text-muted">Cargando panorama…</p>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (data(); as dash) {
        <!-- Totals -->
        <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <sp-card>
            <p class="text-sm text-muted">Proyectos</p>
            <p class="mt-1 text-3xl font-semibold text-text">
              {{ dash.totals.projects }}
            </p>
          </sp-card>
          <sp-card>
            <p class="text-sm text-muted">Tareas</p>
            <p class="mt-1 text-3xl font-semibold text-text">
              {{ dash.totals.tasks }}
            </p>
          </sp-card>
          <sp-card>
            <p class="text-sm text-muted">Vencidas</p>
            <p
              class="mt-1 text-3xl font-semibold"
              [class.text-danger]="dash.totals.overdue > 0"
              [class.text-text]="dash.totals.overdue === 0"
            >
              {{ dash.totals.overdue }}
            </p>
          </sp-card>
          <sp-card>
            <p class="text-sm text-muted">En riesgo</p>
            <p
              class="mt-1 text-3xl font-semibold"
              [class.text-warning]="dash.totals.at_risk > 0"
              [class.text-text]="dash.totals.at_risk === 0"
            >
              {{ dash.totals.at_risk }}
            </p>
          </sp-card>
        </div>

        <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <!-- En qué anda cada uno -->
          <div class="flex flex-col gap-3">
            <h2 class="text-lg font-semibold text-text">En qué anda cada uno</h2>
            @if (dash.by_assignee.length === 0) {
              <sp-card>
                <p class="py-4 text-center text-sm text-muted">
                  Nadie tiene tareas en progreso.
                </p>
              </sp-card>
            } @else {
              @for (person of dash.by_assignee; track person.user.id) {
                <sp-card>
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex items-center gap-2">
                      <span
                        class="grid h-7 w-7 place-items-center rounded-full bg-brand/10 text-xs font-semibold text-brand"
                        aria-hidden="true"
                      >
                        {{ initial(person.user.full_name) }}
                      </span>
                      <span class="text-sm font-medium text-text">
                        {{ person.user.full_name }}
                      </span>
                    </div>
                    <span
                      class="rounded-full bg-muted/15 px-2 py-0.5 text-xs font-medium text-muted"
                    >
                      {{ person.active_count }} activas
                    </span>
                  </div>
                  @if (person.in_progress.length > 0) {
                    <ul class="mt-3 flex flex-col gap-1.5">
                      @for (task of person.in_progress; track task.id) {
                        <li class="flex items-center gap-2 text-sm text-text">
                          <span
                            class="h-1.5 w-1.5 shrink-0 rounded-full bg-brand"
                            aria-hidden="true"
                          ></span>
                          <span class="truncate">{{ task.title }}</span>
                          <span
                            class="ml-auto shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
                            [class]="priorityChip(task.priority)"
                          >
                            {{ priorityLabel(task.priority) }}
                          </span>
                        </li>
                      }
                    </ul>
                  } @else {
                    <p class="mt-2 text-xs text-muted">Sin tareas en progreso.</p>
                  }
                </sp-card>
              }
            }
          </div>

          <!-- Riesgos -->
          <div class="flex flex-col gap-3">
            <h2 class="text-lg font-semibold text-text">Riesgos</h2>
            @if (dash.at_risk.length === 0) {
              <sp-card>
                <p class="py-4 text-center text-sm text-muted">
                  No hay tareas en riesgo. ¡Buen trabajo!
                </p>
              </sp-card>
            } @else {
              <sp-card>
                <ul class="flex flex-col divide-y divide-border">
                  @for (task of dash.at_risk; track task.id) {
                    <li class="flex items-center gap-3 py-2 first:pt-0 last:pb-0">
                      <span
                        class="shrink-0 text-danger"
                        aria-hidden="true"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          width="16"
                          height="16"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="2"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        >
                          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                          <line x1="12" y1="9" x2="12" y2="13" />
                          <line x1="12" y1="17" x2="12.01" y2="17" />
                        </svg>
                      </span>
                      <div class="min-w-0 flex-1">
                        <p class="truncate text-sm font-medium text-text">
                          {{ task.title }}
                        </p>
                        <p class="text-xs text-muted">
                          {{ task.assignee_name || 'Sin responsable' }}
                          @if (task.due_date) {
                            · Vence {{ shortDate(task.due_date) }}
                          }
                        </p>
                      </div>
                      <span
                        class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
                        [class]="priorityChip(task.priority)"
                      >
                        {{ priorityLabel(task.priority) }}
                      </span>
                    </li>
                  }
                </ul>
              </sp-card>
            }
          </div>
        </div>

        <!-- Carga del equipo -->
        <div class="flex flex-col gap-3">
          <h2 class="text-lg font-semibold text-text">Carga del equipo</h2>
          <sp-card>
            @if (dash.workload.length === 0) {
              <p class="py-4 text-center text-sm text-muted">
                No hay carga activa registrada.
              </p>
            } @else {
              <ul class="flex flex-col gap-3">
                @for (item of dash.workload; track item.user.id) {
                  <li class="flex items-center gap-3">
                    <span class="w-40 shrink-0 truncate text-sm text-text">
                      {{ item.user.full_name }}
                    </span>
                    <div
                      class="h-2.5 flex-1 overflow-hidden rounded-full bg-muted/15"
                      role="img"
                      [attr.aria-label]="
                        item.user.full_name +
                        ': ' +
                        item.active_count +
                        ' tareas activas'
                      "
                    >
                      <div
                        class="h-full rounded-full bg-brand transition-all"
                        [style.width.%]="barWidth(item.active_count)"
                      ></div>
                    </div>
                    <span
                      class="w-8 shrink-0 text-right text-sm font-medium text-text"
                    >
                      {{ item.active_count }}
                    </span>
                  </li>
                }
              </ul>
            }
          </sp-card>
        </div>

        <!-- Avance por proyecto -->
        <div class="flex flex-col gap-3">
          <h2 class="text-lg font-semibold text-text">Avance por proyecto</h2>
          @if (dash.projects_progress.length === 0) {
            <sp-card>
              <p class="py-4 text-center text-sm text-muted">
                Aún no hay proyectos con tareas.
              </p>
            </sp-card>
          } @else {
            <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
              @for (
                progress of dash.projects_progress;
                track progress.project.id
              ) {
                <sp-card>
                  <div class="flex items-center justify-between gap-2">
                    <h3 class="text-base font-semibold text-text">
                      {{ progress.project.name }}
                    </h3>
                    <span
                      class="rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand"
                    >
                      {{ methodologyLabel(progress.project.methodology) }}
                    </span>
                  </div>
                  <div class="mt-3">
                    <div class="flex items-center justify-between text-xs text-muted">
                      <span>{{ progress.done }} de {{ progress.total }} listas</span>
                      <span class="font-medium text-text"
                        >{{ progress.percent_done }}%</span
                      >
                    </div>
                    <div
                      class="mt-1.5 h-2.5 overflow-hidden rounded-full bg-muted/15"
                      role="img"
                      [attr.aria-label]="
                        'Avance ' + progress.percent_done + ' por ciento'
                      "
                    >
                      <div
                        class="h-full rounded-full bg-success transition-all"
                        [style.width.%]="progress.percent_done"
                      ></div>
                    </div>
                  </div>
                </sp-card>
              }
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class ExecutiveComponent implements OnInit {
  private readonly executiveService = inject(ExecutiveService);

  protected readonly data = signal<ExecutiveDashboard | null>(null);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);

  private readonly maxWorkload = computed<number>(() => {
    const workload = this.data()?.workload ?? [];
    return workload.reduce((max, item) => Math.max(max, item.active_count), 0);
  });

  ngOnInit(): void {
    this.load();
  }

  protected barWidth(count: number): number {
    const max = this.maxWorkload();
    if (max <= 0) {
      return 0;
    }
    return Math.round((count / max) * 100);
  }

  protected initial(name: string): string {
    const trimmed = name?.trim();
    return trimmed ? trimmed.charAt(0).toUpperCase() : '?';
  }

  protected priorityChip(priority: Priority): string {
    return PRIORITY_CHIP_CLASS[priority] ?? PRIORITY_CHIP_CLASS.medium;
  }

  protected priorityLabel(priority: Priority): string {
    return PRIORITY_LABELS[priority] ?? priority;
  }

  protected methodologyLabel(methodology: Methodology): string {
    return METHODOLOGY_LABELS[methodology] ?? methodology;
  }

  protected shortDate(value: string | null | undefined): string {
    return formatShortDate(value);
  }

  private load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.executiveService.dashboard().subscribe({
      next: (res) => {
        this.data.set(res.data);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? 'No fue posible conectar con el servidor. Inténtalo de nuevo.'
            : 'No se pudo cargar el panorama ejecutivo. Inténtalo más tarde.',
        );
      },
    });
  }
}
