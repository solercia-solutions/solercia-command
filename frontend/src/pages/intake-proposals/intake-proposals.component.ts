import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription, catchError, forkJoin, map, merge, of } from 'rxjs';
import {
  SolButtonComponent,
  SolCardComponent,
  SolEmptyStateComponent,
  SolPaginationComponent,
  SolSelectComponent,
  SolSelectOption,
  SolSkeletonComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { readApiError } from '@shared/lib/api-error';
import { ActiveRoleService } from '@features/organizations/active-role.service';
import { IntakeProposalsService } from '@entities/intake-proposal/intake-proposals.service';
import {
  IntakeProposal,
  ProposalRelation,
  ProposalStatus,
  THREAD_STATES,
  ThreadState,
} from '@entities/intake-proposal/intake-proposal.model';
import { ProposalCardComponent } from './proposal-card.component';
import { ProposalTaskRef, ProposalTaskResolver } from './proposal-task-resolver';

type StatusFilter = ProposalStatus | 'all';
type ThreadFilter = ThreadState | 'all';
type RelationFilter = ProposalRelation | 'all';

const PAGE_SIZE = 20;
const STATUSES: readonly StatusFilter[] = ['propuesta', 'aceptada', 'descartada', 'all'];
const RELATIONS: readonly RelationFilter[] = ['all', 'tarea_existente', 'tarea_nueva', 'irrelevante'];

/**
 * `/intake/proposals` «Bandeja de seguimiento» (C06): propuestas del clasificador agrupadas por
 * el estado del hilo. Estado de la propuesta, hilo y tarea viajan al API; la relación filtra la
 * página cargada (el API no la acepta). Los contadores también son atajos de filtro.
 */
@Component({
  selector: 'sol-intake-proposals-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [ProposalTaskResolver],
  imports: [
    ReactiveFormsModule,
    RouterLink,
    SolButtonComponent,
    SolCardComponent,
    SolEmptyStateComponent,
    SolPaginationComponent,
    SolSelectComponent,
    SolSkeletonComponent,
    ProposalCardComponent,
  ],
  styleUrls: ['../page-layout.scss', './proposals.scss'],
  template: `
    <section class="pg-page">
      <header class="pg-header">
        <div class="pg-header__text">
          <h1 class="pg-title sol-display">{{ t('proposals.title') }}</h1>
          <p class="pg-muted">{{ subtitle() }}</p>
        </div>
      </header>

      <!-- Contadores por estado del hilo: también filtran -->
      <div class="pp-counters" role="group" [attr.aria-label]="t('proposals.counters.label')">
        @for (state of threadStates; track state) {
          <button
            type="button"
            class="pp-counter"
            [class.pp-counter--active]="thread() === state"
            [attr.aria-pressed]="thread() === state"
            (click)="toggleThread(state)"
          >
            <span class="pp-counter__value">{{ counts()[state] ?? '—' }}</span>
            <span class="pp-counter__label">{{ t('proposals.thread.' + state) }}</span>
          </button>
        }
      </div>

      <sol-card>
        <div class="pp-filters-bar">
          <button
            type="button"
            class="pp-filters-toggle"
            [attr.aria-expanded]="filtersOpen()"
            aria-controls="pp-filters"
            (click)="filtersOpen.set(!filtersOpen())"
          >
            {{ activeFilters() > 0 ? t('proposals.filters.toggleCount', { count: activeFilters() }) : t('proposals.filters.toggle') }}
          </button>
          <div id="pp-filters" class="pg-filters pp-filters" [class.pp-filters--open]="filtersOpen()">
            <sol-select class="pg-filter" [label]="t('proposals.filters.status')" [options]="statusOptions()" [searchable]="false" [formControl]="statusControl" />
            <sol-select class="pg-filter" [label]="t('proposals.filters.thread')" [options]="threadOptions()" [searchable]="false" [formControl]="threadControl" />
            <sol-select class="pg-filter" [label]="t('proposals.filters.relation')" [options]="relationOptions()" [searchable]="false" [formControl]="relationControl" />
            <sol-select
              class="pg-filter"
              [label]="t('proposals.filters.task')"
              [options]="taskOptions()"
              [searchable]="taskOptions().length > 8"
              [formControl]="taskControl"
            />
            @if (activeFilters() > 0) {
              <sol-button type="button" variant="ghost" size="sm" (clicked)="clearFilters()">
                {{ t('proposals.filters.clear') }}
              </sol-button>
            }
          </div>
          <span class="pg-small" aria-live="polite">
            @if (activeFilters() > 0) {
              {{ activeFilters() === 1 ? t('proposals.filters.activeOne') : t('proposals.filters.active', { count: activeFilters() }) }}
            }
          </span>
        </div>
      </sol-card>

      @if (loading()) {
        <div class="pg-section" role="status" aria-live="polite" [attr.aria-label]="t('proposals.loading')">
          <sol-skeleton variant="card" [count]="3" />
        </div>
      } @else if (loadError(); as message) {
        <div class="pg-alert" role="alert">
          <span>{{ message }}</span>
          @if (canRetry()) {
            <sol-button type="button" variant="secondary" size="sm" (clicked)="load()">
              {{ t('proposals.retry') }}
            </sol-button>
          }
        </div>
      } @else if (total() === 0 && activeFilters() === 0) {
        <sol-empty-state icon="envelope" titleKey="proposals.empty.title" descriptionKey="proposals.empty.description" />
        @if (roles.isAdmin()) {
          <p class="pp-center"><a class="pg-link" routerLink="/sync">{{ t('proposals.empty.goToSync') }}</a></p>
        }
      } @else if (visible().length === 0) {
        <div class="pg-state" role="status">
          <span>{{ total() > 0 ? t('proposals.noMatchesOnPage') : t('proposals.noMatches') }}</span>
          <sol-button type="button" variant="secondary" size="sm" (clicked)="clearFilters()">
            {{ t('proposals.filters.clear') }}
          </sol-button>
        </div>
      } @else {
        @for (group of groups(); track group.state) {
          <section class="pg-section" [attr.aria-labelledby]="'pp-group-' + group.state">
            <h2 class="pg-subtitle" [id]="'pp-group-' + group.state">
              {{ t('proposals.thread.' + group.state) }}
              <span class="pg-small">({{ group.items.length }})</span>
            </h2>
            <div class="pp-list">
              @for (proposal of group.items; track proposal.id) {
                <sol-proposal-card [proposal]="proposal" [task]="taskFor(proposal)" (decided)="onDecided($event)" />
              }
            </div>
          </section>
        }
      }

      @if (!loading() && !loadError() && total() > pageSize) {
        <sol-pagination
          [totalItems]="total()"
          [pageSize]="pageSize"
          [currentPage]="page()"
          [pageSizeOptions]="[pageSize]"
          (pageChanged)="goToPage($event)"
        />
      }
    </section>
  `,
})
export class IntakeProposalsComponent implements OnInit {
  private readonly service = inject(IntakeProposalsService);
  private readonly resolver = inject(ProposalTaskResolver);
  private readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly roles = inject(ActiveRoleService);

  protected readonly pageSize = PAGE_SIZE;
  protected readonly threadStates = THREAD_STATES;

  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly canRetry = signal(true);
  protected readonly proposals = signal<IntakeProposal[]>([]);
  protected readonly total = signal(0);
  protected readonly page = signal(1);
  protected readonly counts = signal<Partial<Record<ThreadState, number>>>({});
  protected readonly filtersOpen = signal(false);

  protected readonly statusControl = new FormControl<StatusFilter>('propuesta', { nonNullable: true });
  protected readonly threadControl = new FormControl<ThreadFilter>('all', { nonNullable: true });
  protected readonly relationControl = new FormControl<RelationFilter>('all', { nonNullable: true });
  protected readonly taskControl = new FormControl<string>('all', { nonNullable: true });

  protected readonly status = signal<StatusFilter>('propuesta');
  protected readonly thread = signal<ThreadFilter>('all');
  protected readonly relation = signal<RelationFilter>('all');
  protected readonly taskId = signal<string>('all');

  /** Tareas vistas en la bandeja (se acumulan para que el filtro no pierda opciones al aplicarse). */
  private readonly knownTasks = signal<ReadonlyMap<string, string>>(new Map());
  private loadSub: Subscription | null = null;

  protected readonly activeFilters = computed(
    () =>
      (this.status() !== 'propuesta' ? 1 : 0) +
      (this.thread() !== 'all' ? 1 : 0) +
      (this.relation() !== 'all' ? 1 : 0) +
      (this.taskId() !== 'all' ? 1 : 0),
  );

  protected readonly subtitle = computed(() => {
    const total = this.total();
    if (this.loading() || this.loadError()) {
      return this.t('proposals.subtitle');
    }
    return total === 1
      ? this.t(`proposals.summaryOne.${this.status()}`)
      : this.t(`proposals.summary.${this.status()}`, { count: total });
  });

  protected readonly statusOptions = computed<SolSelectOption[]>(() => {
    this.i18n.activeLang();
    return STATUSES.map((value) => ({ value, label: this.t(`proposals.filters.statusOptions.${value}`) }));
  });

  protected readonly threadOptions = computed<SolSelectOption[]>(() => {
    const counts = this.counts();
    return [
      { value: 'all', label: this.t('proposals.filters.allThreads') },
      ...THREAD_STATES.map((state) => ({
        value: state,
        label: `${this.t('proposals.thread.' + state)} (${counts[state] ?? 0})`,
      })),
    ];
  });

  protected readonly relationOptions = computed<SolSelectOption[]>(() => {
    this.i18n.activeLang();
    return RELATIONS.map((value) => ({
      value,
      label: value === 'all' ? this.t('proposals.filters.allRelations') : this.t(`proposals.relation.${value}`),
    }));
  });

  protected readonly taskOptions = computed<SolSelectOption[]>(() => {
    const refs = this.resolver.refs();
    const options = [...this.knownTasks().entries()]
      .map(([id, fallback]) => {
        const ref = refs.get(id);
        const code = ref?.ref ?? ref?.key ?? '';
        const title = ref?.title || fallback;
        return { value: id, label: code ? `${code} · ${title}` : title };
      })
      .sort((a, b) => a.label.localeCompare(b.label, 'es'));
    return [{ value: 'all', label: this.t('proposals.filters.allTasks') }, ...options];
  });

  protected readonly visible = computed(() => {
    const relation = this.relation();
    return this.proposals().filter((p) => relation === 'all' || p.relation === relation);
  });

  protected readonly groups = computed(() =>
    THREAD_STATES.map((state) => ({
      state,
      items: this.visible().filter((p) => p.thread_state === state),
    })).filter((group) => group.items.length > 0),
  );

  ngOnInit(): void {
    this.roles.ensureLoaded();
    this.readQueryParams();
    merge(
      this.statusControl.valueChanges.pipe(map(() => 'status')),
      this.threadControl.valueChanges.pipe(map(() => 'thread')),
      this.taskControl.valueChanges.pipe(map(() => 'task')),
      this.relationControl.valueChanges.pipe(map(() => 'relation')),
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((source) => {
        this.status.set(this.statusControl.value);
        this.thread.set(this.threadControl.value);
        this.taskId.set(this.taskControl.value);
        this.relation.set(this.relationControl.value);
        this.writeQueryParams();
        if (source !== 'relation') {
          this.page.set(1);
          this.load();
        }
      });
    this.load();
  }

  protected t(key: string, params?: Record<string, unknown>): string {
    return this.i18n.translate(key, params);
  }

  protected taskFor(proposal: IntakeProposal): ProposalTaskRef | null {
    this.resolver.refs();
    return this.resolver.refFor(proposal);
  }

  protected toggleThread(state: ThreadState): void {
    this.threadControl.setValue(this.thread() === state ? 'all' : state);
  }

  protected clearFilters(): void {
    this.statusControl.setValue('propuesta', { emitEvent: false });
    this.threadControl.setValue('all', { emitEvent: false });
    this.relationControl.setValue('all', { emitEvent: false });
    this.taskControl.setValue('all');
  }

  protected goToPage(page: number): void {
    this.page.set(page);
    this.writeQueryParams();
    this.load();
  }

  protected onDecided(updated: IntakeProposal | null): void {
    if (updated) {
      this.resolver.forget(updated.task_id);
    }
    // Releer: la propuesta sale de «Por decidir» y los contadores cambian.
    this.load();
  }

  protected load(): void {
    this.loadSub?.unsubscribe();
    this.loading.set(true);
    this.loadError.set(null);
    const status = this.status() === 'all' ? null : (this.status() as ProposalStatus);
    const taskId = this.taskId() === 'all' ? null : this.taskId();
    const thread = this.thread() === 'all' ? null : (this.thread() as ThreadState);
    const counts$ = forkJoin(
      THREAD_STATES.map((state) =>
        this.service.list({ status, task_id: taskId, thread_state: state, size: 1 }).pipe(
          map((res) => [state, res.meta.total] as const),
          catchError(() => of([state, undefined] as const)),
        ),
      ),
    );
    this.loadSub = forkJoin([
      this.service.list({ status, task_id: taskId, thread_state: thread, page: this.page(), size: PAGE_SIZE }),
      counts$,
    ]).subscribe({
      next: ([page, counts]) => {
        this.proposals.set(page.data ?? []);
        this.total.set(page.meta?.total ?? 0);
        this.counts.set(Object.fromEntries(counts.filter(([, n]) => n !== undefined)));
        this.rememberTasks(page.data ?? []);
        this.resolver.resolve(page.data ?? []);
        this.loading.set(false);
      },
      error: (err) => {
        const api = readApiError(err);
        this.loading.set(false);
        this.canRetry.set(api.status !== 403);
        this.loadError.set(
          api.status === 403
            ? this.t('proposals.errors.forbidden')
            : api.status === 0
              ? this.t('proposals.errors.network')
              : this.t('proposals.errors.load'),
        );
      },
    });
  }

  private rememberTasks(proposals: IntakeProposal[]): void {
    const next = new Map(this.knownTasks());
    for (const proposal of proposals) {
      const id = ProposalTaskResolver.taskIdOf(proposal);
      if (id && !next.has(id)) {
        const candidate = proposal.candidates.find((c) => c.task_id === id);
        next.set(id, candidate?.title ?? proposal.result?.task_ref ?? id.slice(0, 8));
      }
    }
    this.knownTasks.set(next);
  }

  private readQueryParams(): void {
    const params = this.route.snapshot.queryParamMap;
    const status = params.get('estado') as StatusFilter | null;
    const thread = params.get('hilo') as ThreadFilter | null;
    const relation = params.get('relacion') as RelationFilter | null;
    const task = params.get('tarea');
    const page = Number(params.get('pagina'));
    if (status && STATUSES.includes(status)) {
      this.statusControl.setValue(status, { emitEvent: false });
      this.status.set(status);
    }
    if (thread && (thread === 'all' || THREAD_STATES.includes(thread as ThreadState))) {
      this.threadControl.setValue(thread, { emitEvent: false });
      this.thread.set(thread);
    }
    if (relation && RELATIONS.includes(relation)) {
      this.relationControl.setValue(relation, { emitEvent: false });
      this.relation.set(relation);
    }
    if (task) {
      this.knownTasks.set(new Map([[task, task.slice(0, 8)]]));
      this.taskControl.setValue(task, { emitEvent: false });
      this.taskId.set(task);
    }
    if (Number.isInteger(page) && page > 1) {
      this.page.set(page);
    }
  }

  private writeQueryParams(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      replaceUrl: true,
      queryParams: {
        estado: this.status() !== 'propuesta' ? this.status() : null,
        hilo: this.thread() !== 'all' ? this.thread() : null,
        relacion: this.relation() !== 'all' ? this.relation() : null,
        tarea: this.taskId() !== 'all' ? this.taskId() : null,
        pagina: this.page() > 1 ? this.page() : null,
      },
    });
  }
}
