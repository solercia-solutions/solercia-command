import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { SolCardComponent } from '@shared/ui';
import { PerformanceService } from '@entities/performance/performance.service';
import { PerfCollaborator, PerformanceData } from '@entities/performance/performance.model';

/**
 * Per-collaborator performance ("Rendimiento") dashboard. For every member of
 * the organization it shows delivered work (completed tasks and points),
 * on-time delivery rate, plus current active and overdue load. Org-scoped via
 * the bearer token; no project context required.
 */
@Component({
  selector: 'sol-performance',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SolCardComponent],
  template: `
    <section class="flex flex-col gap-6">
      <div>
        <h1 class="text-2xl font-semibold text-text">Rendimiento</h1>
        <p class="text-sm text-muted">
          Desempeño por colaborador: trabajo entregado, cumplimiento y carga
          actual.
        </p>
      </div>

      @if (loading()) {
        <p class="text-sm text-muted">Cargando rendimiento…</p>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (collaborators().length === 0) {
        <sol-card>
          <p class="py-6 text-center text-sm text-muted">
            Todavía no hay datos de rendimiento para mostrar.
          </p>
        </sol-card>
      } @else {
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          @for (person of collaborators(); track person.user.id) {
            <sol-card>
              <!-- Header -->
              <div class="flex items-center gap-3">
                <span
                  class="grid h-9 w-9 place-items-center rounded-full bg-brand/10 text-sm font-semibold text-brand"
                  aria-hidden="true"
                >
                  {{ initial(person.user.full_name) }}
                </span>
                <h2 class="text-base font-semibold text-text">
                  {{ person.user.full_name }}
                </h2>
              </div>

              <!-- Metrics -->
              <div class="mt-4 grid grid-cols-2 gap-3">
                <div class="rounded-lg bg-muted/10 px-3 py-2">
                  <p class="text-xs text-muted">Tareas completadas</p>
                  <p class="mt-0.5 text-xl font-semibold text-text">
                    {{ person.completed_tasks }}
                  </p>
                </div>
                <div class="rounded-lg bg-muted/10 px-3 py-2">
                  <p class="text-xs text-muted">Puntos completados</p>
                  <p class="mt-0.5 text-xl font-semibold text-text">
                    {{ person.completed_points }}
                  </p>
                </div>
                <div class="rounded-lg bg-muted/10 px-3 py-2">
                  <p class="text-xs text-muted">Activas</p>
                  <p class="mt-0.5 text-xl font-semibold text-text">
                    {{ person.active_count }}
                  </p>
                </div>
                <div class="rounded-lg bg-muted/10 px-3 py-2">
                  <p class="text-xs text-muted">Vencidas</p>
                  <p
                    class="mt-0.5 text-xl font-semibold"
                    [class.text-danger]="person.overdue_count > 0"
                    [class.text-text]="person.overdue_count === 0"
                  >
                    {{ person.overdue_count }}
                  </p>
                </div>
              </div>

              <!-- Bars -->
              <div class="mt-4 flex flex-col gap-3">
                <div>
                  <div
                    class="flex items-center justify-between text-xs text-muted"
                  >
                    <span>Puntos completados</span>
                    <span class="font-medium text-text">
                      {{ person.completed_points }}
                    </span>
                  </div>
                  <div
                    class="mt-1.5 h-2.5 overflow-hidden rounded-full bg-muted/15"
                    role="img"
                    [attr.aria-label]="
                      person.completed_points + ' puntos completados'
                    "
                  >
                    <div
                      class="h-full rounded-full bg-brand transition-all"
                      [style.width.%]="pointsBar(person)"
                    ></div>
                  </div>
                </div>

                <div>
                  <div
                    class="flex items-center justify-between text-xs text-muted"
                  >
                    <span>% a tiempo</span>
                    <span class="font-medium text-text">
                      {{ onTimeLabel(person) }}
                    </span>
                  </div>
                  <div
                    class="mt-1.5 h-2.5 overflow-hidden rounded-full bg-muted/15"
                    role="img"
                    [attr.aria-label]="
                      onTimePercent(person) + ' por ciento a tiempo'
                    "
                  >
                    <div
                      class="h-full rounded-full transition-all"
                      [class]="onTimeBarClass(person)"
                      [style.width.%]="onTimePercent(person)"
                    ></div>
                  </div>
                </div>
              </div>
            </sol-card>
          }
        </div>

        @if (generatedAt()) {
          <p class="text-right text-xs text-muted">
            Actualizado: {{ generatedAt() }}
          </p>
        }
      }
    </section>
  `,
})
export class PerformanceComponent implements OnInit {
  private readonly performanceService = inject(PerformanceService);

  protected readonly data = signal<PerformanceData | null>(null);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);

  protected readonly collaborators = computed<PerfCollaborator[]>(
    () => this.data()?.collaborators ?? [],
  );

  /** Largest completed-points value, for normalizing the points bars. */
  private readonly maxPoints = computed<number>(() =>
    this.collaborators().reduce(
      (max, person) => Math.max(max, person.completed_points),
      0,
    ),
  );

  ngOnInit(): void {
    this.load();
  }

  protected initial(name: string): string {
    const trimmed = name?.trim();
    return trimmed ? trimmed.charAt(0).toUpperCase() : '?';
  }

  protected pointsBar(person: PerfCollaborator): number {
    const max = this.maxPoints();
    if (max <= 0) {
      return 0;
    }
    return Math.round((person.completed_points / max) * 100);
  }

  protected hasOnTime(person: PerfCollaborator): boolean {
    return person.on_time_rate !== null && person.on_time_rate !== undefined;
  }

  protected onTimePercent(person: PerfCollaborator): number {
    return this.hasOnTime(person)
      ? Math.round((person.on_time_rate as number) * 100)
      : 0;
  }

  protected onTimeLabel(person: PerfCollaborator): string {
    return this.hasOnTime(person) ? `${this.onTimePercent(person)}%` : 'sin datos';
  }

  protected onTimeBarClass(person: PerfCollaborator): string {
    if (!this.hasOnTime(person)) {
      return 'bg-muted/40';
    }
    const percent = this.onTimePercent(person);
    if (percent >= 80) {
      return 'bg-success';
    }
    if (percent >= 50) {
      return 'bg-warning';
    }
    return 'bg-danger';
  }

  protected generatedAt(): string {
    const value = this.data()?.generated_at;
    if (!value) {
      return '';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return '';
    }
    return date.toLocaleString('es-CO', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  private load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.performanceService.performance().subscribe({
      next: (res) => {
        this.data.set(res.data);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? 'No fue posible conectar con el servidor. Inténtalo de nuevo.'
            : 'No se pudo cargar el rendimiento. Inténtalo más tarde.',
        );
      },
    });
  }
}
