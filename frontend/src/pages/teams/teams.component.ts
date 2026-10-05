import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { toSignal } from '@angular/core/rxjs-interop';
import {
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolEmptyStateComponent,
  SolIconComponent,
  SolProgressBarComponent,
  SolSelectComponent,
  SolSkeletonComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { OrgRoleTemplatesService } from '@entities/org-role-template/org-role-templates.service';
import {
  InstantiatedProject,
  OrgRoleTemplate,
  OrgRoleTemplateNode,
} from '@entities/org-role-template/org-role-template.model';
import { ProjectsService } from '@entities/project/projects.service';
import { WorkspaceService } from '@entities/workspace/workspace.service';
import { UsersService } from '@entities/user/users.service';
import {
  METHODOLOGY_LABELS,
  Methodology,
} from '@entities/project/project.model';

/** Nodo del árbol de la plantilla aplanado para pintarlo con sangría. */
interface FlatTemplateNode {
  name: string;
  methodology: Methodology;
  depth: number;
}

/**
 * Onboarding de "Equipos": genera el árbol de proyectos de un equipo a
 * partir de una plantilla organizacional (org-role-templates) con la
 * persona líder elegida. La instanciación es idempotente/reconciliable en
 * el backend, así que repetirla no duplica proyectos.
 *
 * Patrón de PANDORA: encabezado `h1.sol-display`, avance del asistente en `sol-progress-bar`
 * segmentada, plantillas como tarjetas seleccionables y estados con «Reintentar».
 */
@Component({
  selector: 'sol-teams',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    ReactiveFormsModule,
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolEmptyStateComponent,
    SolIconComponent,
    SolProgressBarComponent,
    SolSelectComponent,
    SolSkeletonComponent,
  ],
  styleUrl: '../page-layout.scss',
  styles: [
    `
      .tm-option {
        display: flex;
        align-items: flex-start;
        gap: var(--sol-space-sm, 8px);
        width: 100%;
        min-height: 44px;
        padding: 0;
        border: 0;
        background: none;
        color: var(--sol-color-text-primary);
        font: inherit;
        font-weight: 600;
        text-align: left;
        cursor: pointer;
      }
      .tm-option:focus-visible,
      .tm-toggle:focus-visible {
        outline: 2px solid var(--sol-color-primary);
        outline-offset: 2px;
      }
      .tm-radio {
        display: inline-grid;
        place-items: center;
        flex: 0 0 18px;
        width: 18px;
        height: 18px;
        margin-top: 2px;
        border: 2px solid var(--sol-border-color-default, #d1d5db);
        border-radius: 50%;
      }
      .tm-radio--on {
        border-color: var(--sol-color-primary);
      }
      .tm-radio--on::after {
        content: '';
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--sol-color-primary);
      }
      .tm-card--on {
        display: block;
        border-radius: var(--sol-border-radius-lg, 12px);
        outline: 2px solid var(--sol-color-primary);
      }
      .tm-toggle {
        display: inline-flex;
        align-items: center;
        gap: var(--sol-space-xs, 4px);
        min-height: 44px;
        padding: 0;
        border: 0;
        background: none;
        color: var(--sol-color-primary);
        font: inherit;
        font-size: var(--sol-font-size-sm, 0.875rem);
        cursor: pointer;
      }
      .tm-tree {
        margin: 0;
        padding: 0 0 0 var(--sol-space-sm, 8px);
        border-left: 1px solid var(--sol-border-color-default, #e5e7eb);
        list-style: none;
      }
      .tm-tree li {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: var(--sol-space-xs, 4px) var(--sol-space-sm, 8px);
        padding: 2px 0;
        font-size: var(--sol-font-size-sm, 0.875rem);
        color: var(--sol-color-text-primary);
      }
      .tm-badges {
        display: flex;
        flex-wrap: wrap;
        gap: var(--sol-space-xs, 4px);
        margin-top: var(--sol-space-xs, 4px);
        font-weight: 400;
      }
      .tm-body {
        display: flex;
        flex-direction: column;
        gap: 0;
      }
      .tm-success-icon {
        color: var(--sol-color-success);
      }
      .tm-actions {
        display: flex;
        flex-wrap: wrap;
        gap: var(--sol-space-sm, 8px);
      }
      .pg-filter.tm-leader {
        flex-basis: 420px;
        max-width: 100%;
      }
      .tm-error {
        margin: var(--sol-space-xs, 4px) 0 0;
        font-size: var(--sol-font-size-xs, 0.75rem);
        color: var(--sol-color-danger);
      }
    `,
  ],
  template: `
    <section class="pg-page">
      <header class="pg-header">
        <div class="pg-header__text">
          <h1 class="pg-title sol-display">{{ text.title() }}</h1>
          <p class="pg-muted">{{ text.subtitle() }}</p>
        </div>
      </header>

      @if (result(); as generated) {
        <!-- Paso final: resumen del equipo generado. -->
        <sol-card>
          <div class="pg-section" role="status">
            <div class="pg-row">
              <sol-icon class="tm-success-icon" name="check-circle" aria-hidden="true" />
              <div class="pg-header__text">
                <h2 class="pg-subtitle">{{ text.successTitle() }}</h2>
                <p class="pg-muted">{{ successSubtitle() }}</p>
              </div>
            </div>
            <h3 class="pg-subtitle">{{ text.successProjectsHeading() }}</h3>
            <ul class="tm-tree">
              @for (item of resultRows(); track item.id) {
                <li [style.padding-left.rem]="item.depth * 1.25">
                  <span>{{ item.name }}</span>
                  <sol-badge variant="info" size="sm">{{ methodologyLabel(item.methodology) }}</sol-badge>
                </li>
              }
            </ul>
            <div class="tm-actions">
              <a routerLink="/hierarchy">
                <sol-button type="button" variant="primary">{{ text.successGoHierarchy() }}</sol-button>
              </a>
              <sol-button type="button" variant="ghost" (clicked)="resetFlow()">
                {{ text.successAgain() }}
              </sol-button>
            </div>
          </div>
        </sol-card>
      } @else if (loading()) {
        <div class="pg-section" role="status" aria-live="polite" [attr.aria-label]="text.loading()">
          <div class="pg-grid"><sol-skeleton variant="card" [count]="2" /></div>
        </div>
      } @else if (loadError(); as message) {
        <div class="pg-alert" role="alert">
          <span>{{ message }}</span>
          <sol-button type="button" variant="secondary" size="sm" (clicked)="loadTemplates()">
            {{ text.retry() }}
          </sol-button>
        </div>
      } @else if (templates().length === 0) {
        <sol-empty-state
          icon="users"
          titleKey="teams.empty.title"
          descriptionKey="teams.empty.subtitle"
        />
      } @else {
        <sol-card>
          <div class="pg-section">
            <sol-progress-bar
              mode="segmented"
              [steps]="3"
              [current]="stepIndex()"
              [showLabel]="true"
            />
            <p class="pg-muted">{{ stepHint() }}</p>
          </div>
        </sol-card>

        <div class="pg-section">
          <h2 class="pg-subtitle">1. {{ text.stepTemplate() }}</h2>
          <div class="pg-grid" role="radiogroup" [attr.aria-label]="text.stepTemplate()">
            @for (template of templates(); track template.id) {
              <sol-card [class.tm-card--on]="selectedId() === template.id">
                <div class="tm-body">
                  <button
                    type="button"
                    class="tm-option"
                    role="radio"
                    [attr.aria-checked]="selectedId() === template.id"
                    [attr.aria-label]="selectAria(template.name)"
                    (click)="selectTemplate(template)"
                  >
                    <span class="tm-radio" [class.tm-radio--on]="selectedId() === template.id" aria-hidden="true"></span>
                    <span class="pg-grow">
                      {{ template.name }}
                      <span class="tm-badges">
                        @if (selectedId() === template.id) {
                          <sol-badge variant="info" size="sm">{{ text.selectedBadge() }}</sol-badge>
                        }
                        @if (template.is_system) {
                          <sol-badge variant="neutral" size="sm">{{ text.systemBadge() }}</sol-badge>
                        }
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    class="tm-toggle"
                    [attr.aria-label]="isExpanded(template.id) ? collapseAria(template.name) : expandAria(template.name)"
                    [attr.aria-expanded]="isExpanded(template.id)"
                    (click)="toggleTree(template)"
                  >
                    <sol-icon [name]="isExpanded(template.id) ? 'chevron-down' : 'chevron-right'" size="sm" />
                    {{ isExpanded(template.id) ? text.hideTree() : text.showTree() }}
                  </button>
                  @if (isExpanded(template.id)) {
                    @if (treeLoadingIds().has(template.id)) {
                      <p class="pg-small" role="status">{{ text.treeLoading() }}</p>
                    } @else if (treeErrors().has(template.id)) {
                      <div class="pg-alert" role="alert">
                        <span>{{ text.treeError() }}</span>
                        <sol-button type="button" variant="secondary" size="sm" (clicked)="retryTree(template.id)">
                          {{ text.retry() }}
                        </sol-button>
                      </div>
                    } @else if (trees().get(template.id); as nodes) {
                      <ul class="tm-tree">
                        @for (node of nodes; track $index) {
                          <li [style.padding-left.rem]="node.depth * 1.25">
                            <span>{{ node.name }}</span>
                            <sol-badge variant="info" size="sm">{{ methodologyLabel(node.methodology) }}</sol-badge>
                          </li>
                        }
                      </ul>
                    }
                  }
                </div>
              </sol-card>
            }
          </div>
        </div>

        <div class="pg-section">
          <h2 class="pg-subtitle">2. {{ text.stepLeader() }}</h2>
          <sol-card>
            <div class="pg-section">
              <div class="pg-filters">
                <sol-select
                  class="pg-filter tm-leader"
                  [label]="text.leaderLabel()"
                  [placeholder]="text.leaderPlaceholder()"
                  [options]="memberOptions()"
                  [searchable]="true"
                  [error]="showLeadRequired() ? text.leaderRequired() : ''"
                  [formControl]="leadControl"
                />
              </div>
              @if (membersError(); as message) {
                <p class="tm-error" role="alert">{{ message }}</p>
              }
            </div>
          </sol-card>
        </div>

        <div class="pg-section">
          <h2 class="pg-subtitle">3. {{ text.stepReview() }}</h2>
          @if (generateError(); as message) {
            <div class="pg-alert" role="alert"><span>{{ message }}</span></div>
          }
          <div class="tm-actions">
            <sol-button
              type="button"
              variant="primary"
              [loading]="generating()"
              [disabled]="generating() || !selectedId()"
              (clicked)="generate()"
            >
              {{ generating() ? text.generating() : text.generate() }}
            </sol-button>
          </div>
        </div>
      }
    </section>
  `,
})
export class TeamsComponent implements OnInit {
  private readonly templatesService = inject(OrgRoleTemplatesService);
  private readonly projectsService = inject(ProjectsService);
  private readonly workspaceService = inject(WorkspaceService);
  private readonly usersService = inject(UsersService);
  private readonly i18n = inject(I18nService);

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    title: this.i18n.t('teams.title'),
    subtitle: this.i18n.t('teams.subtitle'),
    loading: this.i18n.t('teams.loading'),
    stepTemplate: this.i18n.t('teams.steps.template'),
    stepLeader: this.i18n.t('teams.steps.leader'),
    stepReview: this.i18n.t('teams.steps.review'),
    systemBadge: this.i18n.t('teams.systemBadge'),
    selectedBadge: this.i18n.t('teams.selectedBadge'),
    showTree: this.i18n.t('teams.template.showTree'),
    hideTree: this.i18n.t('teams.template.hideTree'),
    treeLoading: this.i18n.t('teams.template.treeLoading'),
    treeError: this.i18n.t('teams.errors.treeLoad'),
    leaderLabel: this.i18n.t('teams.leader.label'),
    leaderPlaceholder: this.i18n.t('teams.leader.placeholder'),
    leaderRequired: this.i18n.t('teams.leader.required'),
    generate: this.i18n.t('teams.generate'),
    generating: this.i18n.t('teams.generating'),
    successTitle: this.i18n.t('teams.success.title'),
    successProjectsHeading: this.i18n.t('teams.success.projectsHeading'),
    successGoHierarchy: this.i18n.t('teams.success.goHierarchy'),
    successAgain: this.i18n.t('teams.success.again'),
    retry: this.i18n.t('teams.retry'),
  } as const;

  protected readonly templates = signal<OrgRoleTemplate[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  /** Plantilla elegida para instanciar. */
  protected readonly selectedId = signal<string | null>(null);

  /** Árboles ya cargados por plantilla (aplanados para la sangría). */
  protected readonly trees = signal<Map<string, FlatTemplateNode[]>>(new Map());
  protected readonly expanded = signal<Set<string>>(new Set());
  /**
   * Ids con el árbol en carga. Es un Set (no un escalar) para que dos
   * plantillas expandidas con requests solapados conserven cada una su
   * indicador — mismo patrón que `treeErrors`.
   */
  protected readonly treeLoadingIds = signal<Set<string>>(new Set());
  protected readonly treeErrors = signal<Set<string>>(new Set());

  /** Miembros de la organización elegibles como líder. */
  protected readonly memberOptions = signal<
    { value: string; label: string }[]
  >([]);
  protected readonly membersError = signal<string | null>(null);

  protected readonly leadControl = new FormControl<string>('', {
    nonNullable: true,
    validators: [Validators.required],
  });
  protected readonly leadRequiredVisible = signal(false);
  private readonly leadValue = toSignal(this.leadControl.valueChanges, { initialValue: '' });

  /** Paso actual del asistente (base 0): plantilla → líder → generar. */
  protected readonly stepIndex = computed(() =>
    !this.selectedId() ? 0 : !this.leadValue() ? 1 : 2,
  );

  protected readonly stepHint = computed(() =>
    this.i18n.translate(`teams.stepHint.${this.stepIndex()}`),
  );

  protected readonly generating = signal(false);
  protected readonly generateError = signal<string | null>(null);
  protected readonly result = signal<InstantiatedProject[] | null>(null);

  /** Filas del resumen final, con sangría derivada del padre generado. */
  protected readonly resultRows = computed(() => {
    const rows = this.result() ?? [];
    const depths = new Map<string, number>();
    const depthOf = (p: InstantiatedProject): number => {
      const known = depths.get(p.id);
      if (known !== undefined) {
        return known;
      }
      const parent = rows.find((r) => r.id === p.parent_project_id);
      const depth = parent ? depthOf(parent) + 1 : 0;
      depths.set(p.id, depth);
      return depth;
    };
    return rows.map((r) => ({ ...r, depth: depthOf(r) }));
  });

  ngOnInit(): void {
    this.loadTemplates();
    this.loadMembers();
  }

  protected methodologyLabel(methodology: Methodology): string {
    return METHODOLOGY_LABELS[methodology] ?? methodology;
  }

  protected successSubtitle(): string {
    return this.i18n.translate('teams.success.subtitle', {
      count: String(this.result()?.length ?? 0),
    });
  }

  protected selectAria(name: string): string {
    return this.i18n.translate('teams.template.selectAria', { name });
  }

  protected expandAria(name: string): string {
    return this.i18n.translate('teams.template.expandAria', { name });
  }

  protected collapseAria(name: string): string {
    return this.i18n.translate('teams.template.collapseAria', { name });
  }

  protected isExpanded(id: string): boolean {
    return this.expanded().has(id);
  }

  protected showLeadRequired(): boolean {
    return (
      this.leadRequiredVisible() ||
      (this.leadControl.invalid &&
        (this.leadControl.touched || this.leadControl.dirty))
    );
  }

  protected selectTemplate(template: OrgRoleTemplate): void {
    this.selectedId.set(template.id);
    this.generateError.set(null);
  }

  protected toggleTree(template: OrgRoleTemplate): void {
    const next = new Set(this.expanded());
    if (next.has(template.id)) {
      next.delete(template.id);
      this.expanded.set(next);
      return;
    }
    next.add(template.id);
    this.expanded.set(next);
    if (!this.trees().has(template.id)) {
      this.loadTree(template.id);
    }
  }

  protected generate(): void {
    const templateId = this.selectedId();
    if (!templateId) {
      return;
    }
    if (this.leadControl.invalid) {
      this.leadControl.markAsTouched();
      this.leadRequiredVisible.set(true);
      return;
    }
    this.leadRequiredVisible.set(false);
    this.generateError.set(null);
    this.generating.set(true);

    this.templatesService
      .instantiate(templateId, this.leadControl.value)
      .subscribe({
        next: (res) => {
          this.generating.set(false);
          this.result.set(res.data ?? []);
        },
        error: (err: HttpErrorResponse) => {
          this.generating.set(false);
          this.generateError.set(this.instantiateErrorMessage(err));
        },
      });
  }

  protected resetFlow(): void {
    this.result.set(null);
    this.generateError.set(null);
  }

  private instantiateErrorMessage(err: HttpErrorResponse): string {
    if (err.status === 0) {
      return this.i18n.translate('teams.errors.network');
    }
    if (err.status === 403) {
      return this.i18n.translate('teams.errors.forbidden');
    }
    if (err.error?.code === 'lead_not_member') {
      return this.i18n.translate('teams.errors.leadNotMember');
    }
    return this.i18n.translate('teams.errors.instantiate');
  }

  protected retryTree(templateId: string): void {
    this.loadTree(templateId);
  }

  protected loadTemplates(): void {
    this.loading.set(true);
    this.loadError.set(null);

    this.templatesService.list().subscribe({
      next: (res) => {
        const templates = res.data ?? [];
        this.templates.set(templates);
        // Valor por defecto: con una sola plantilla no hay nada que decidir.
        if (templates.length === 1 && !this.selectedId()) {
          this.selectedId.set(templates[0].id);
        }
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? this.i18n.translate('teams.errors.network')
            : this.i18n.translate('teams.errors.load'),
        );
      },
    });
  }

  private loadTree(templateId: string): void {
    this.treeLoadingIds.update((ids) => new Set(ids).add(templateId));
    const errors = new Set(this.treeErrors());
    errors.delete(templateId);
    this.treeErrors.set(errors);

    this.templatesService.get(templateId).subscribe({
      next: (res) => {
        const flat: FlatTemplateNode[] = [];
        this.flatten(res.data.tree, 0, flat);
        const next = new Map(this.trees());
        next.set(templateId, flat);
        this.trees.set(next);
        this.removeTreeLoading(templateId);
      },
      error: () => {
        this.removeTreeLoading(templateId);
        const failed = new Set(this.treeErrors());
        failed.add(templateId);
        this.treeErrors.set(failed);
      },
    });
  }

  /** Retira un id del Set de árboles en carga sin afectar a los demás. */
  private removeTreeLoading(templateId: string): void {
    this.treeLoadingIds.update((ids) => {
      const next = new Set(ids);
      next.delete(templateId);
      return next;
    });
  }

  private flatten(
    node: OrgRoleTemplateNode,
    depth: number,
    out: FlatTemplateNode[],
  ): void {
    out.push({
      name: node.name,
      methodology: node.default_methodology,
      depth,
    });
    for (const child of node.children ?? []) {
      this.flatten(child, depth + 1, out);
    }
  }

  /**
   * Carga los miembros elegibles como líder. Usa el endpoint de miembros por
   * proyecto (accesible para cualquier miembro autenticado, a diferencia de
   * `/admin/users` que exige rol admin); si la organización aún no tiene
   * proyectos, intenta el listado de administración como respaldo.
   */
  private loadMembers(): void {
    this.membersError.set(null);

    this.projectsService.list().subscribe({
      next: (res) => {
        const first = (res.data ?? [])[0];
        if (first) {
          this.workspaceService.members(first.id).subscribe({
            next: (members) => {
              this.memberOptions.set(
                (members.data ?? []).map((m) => ({
                  value: m.user_id,
                  label: `${m.full_name} (${m.email})`,
                })),
              );
            },
            error: () => this.loadMembersViaAdmin(),
          });
        } else {
          this.loadMembersViaAdmin();
        }
      },
      error: () => this.loadMembersViaAdmin(),
    });
  }

  /** Respaldo admin-only: GET /admin/users (403 silencioso → mensaje claro). */
  private loadMembersViaAdmin(): void {
    this.usersService.list().subscribe({
      next: (res) => {
        this.memberOptions.set(
          (res.data ?? [])
            .filter((u) => u.is_active)
            .map((u) => ({
              value: u.id,
              label: `${u.full_name} (${u.email})`,
            })),
        );
      },
      error: () => {
        this.membersError.set(
          this.i18n.translate('teams.errors.membersLoad'),
        );
      },
    });
  }
}
