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
import { SolButtonComponent } from '@shared/ui';
import { SolCardComponent } from '@shared/ui';
import { SolEmptyStateComponent } from '@shared/ui';
import { SolIconComponent } from '@shared/ui';
import { SolSelectComponent } from '@shared/ui';
import { SolSpinnerComponent } from '@shared/ui';
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
 */
@Component({
  selector: 'sol-teams',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    ReactiveFormsModule,
    SolButtonComponent,
    SolCardComponent,
    SolEmptyStateComponent,
    SolIconComponent,
    SolSelectComponent,
    SolSpinnerComponent,
  ],
  template: `
    <section class="flex flex-col gap-6">
      <div>
        <h1 class="text-2xl font-semibold text-text">{{ text.title() }}</h1>
        <p class="text-sm text-muted">{{ text.subtitle() }}</p>
      </div>

      @if (result(); as generated) {
        <!-- Paso final: resumen del equipo generado. -->
        <sol-card>
          <div class="flex flex-col gap-4">
            <div class="flex items-center gap-3">
              <span
                class="inline-flex h-10 w-10 items-center justify-center rounded-full bg-success/10 text-success"
                aria-hidden="true"
              >
                <sol-icon name="check-circle" />
              </span>
              <div>
                <h2 class="text-lg font-semibold text-text">
                  {{ text.successTitle() }}
                </h2>
                <p class="text-sm text-muted">{{ successSubtitle() }}</p>
              </div>
            </div>

            <div>
              <h3 class="mb-2 text-sm font-semibold text-text">
                {{ text.successProjectsHeading() }}
              </h3>
              <ul class="flex flex-col gap-1">
                @for (item of resultRows(); track item.id) {
                  <li
                    class="flex items-center gap-2 text-sm text-text"
                    [style.padding-left.rem]="item.depth * 1.25"
                  >
                    <sol-icon name="layers" size="sm" class="text-muted" />
                    <span>{{ item.name }}</span>
                    <span
                      class="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand"
                    >
                      {{ methodologyLabel(item.methodology) }}
                    </span>
                  </li>
                }
              </ul>
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <a routerLink="/hierarchy">
                <sol-button type="button" variant="primary">
                  {{ text.successGoHierarchy() }}
                </sol-button>
              </a>
              <sol-button type="button" variant="ghost" (click)="resetFlow()">
                {{ text.successAgain() }}
              </sol-button>
            </div>
          </div>
        </sol-card>
      } @else {
        <!-- Pasos del onboarding. -->
        <ol class="flex flex-col gap-1 text-sm text-muted sm:flex-row sm:gap-6">
          <li>1. {{ text.stepTemplate() }}</li>
          <li>2. {{ text.stepLeader() }}</li>
          <li>3. {{ text.stepReview() }}</li>
        </ol>

        @if (loading()) {
          <div class="flex items-center gap-3 py-8">
            <sol-spinner size="sm" />
            <p class="text-sm text-muted">{{ text.loading() }}</p>
          </div>
        } @else if (loadError()) {
          <div
            role="alert"
            class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
          >
            {{ loadError() }}
          </div>
        } @else if (templates().length === 0) {
          <sol-empty-state
            icon="users"
            titleKey="teams.empty.title"
            descriptionKey="teams.empty.subtitle"
          />
        } @else {
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
            @for (template of templates(); track template.id) {
              <sol-card>
                <div class="flex flex-col gap-3">
                  <div class="flex items-start justify-between gap-2">
                    <button
                      type="button"
                      class="flex items-center gap-2 text-left text-base font-semibold text-text
                             focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
                      [attr.aria-label]="selectAria(template.name)"
                      (click)="selectTemplate(template)"
                    >
                      <span
                        class="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border"
                        [class.border-brand]="selectedId() === template.id"
                        [class.border-border]="selectedId() !== template.id"
                        aria-hidden="true"
                      >
                        @if (selectedId() === template.id) {
                          <span class="h-2 w-2 rounded-full bg-brand"></span>
                        }
                      </span>
                      {{ template.name }}
                    </button>
                    <div class="flex shrink-0 items-center gap-1.5">
                      @if (selectedId() === template.id) {
                        <span
                          class="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand"
                        >
                          {{ text.selectedBadge() }}
                        </span>
                      }
                      @if (template.is_system) {
                        <span
                          class="rounded-full bg-sunken px-2 py-0.5 text-xs text-muted"
                        >
                          {{ text.systemBadge() }}
                        </span>
                      }
                    </div>
                  </div>

                  <button
                    type="button"
                    class="inline-flex w-fit items-center gap-1 text-sm text-brand
                           hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
                    [attr.aria-label]="
                      isExpanded(template.id)
                        ? collapseAria(template.name)
                        : expandAria(template.name)
                    "
                    [attr.aria-expanded]="isExpanded(template.id)"
                    (click)="toggleTree(template)"
                  >
                    <sol-icon
                      [name]="isExpanded(template.id) ? 'chevron-down' : 'chevron-right'"
                      size="sm"
                    />
                    {{
                      isExpanded(template.id)
                        ? text.hideTree()
                        : text.showTree()
                    }}
                  </button>

                  @if (isExpanded(template.id)) {
                    @if (treeLoadingIds().has(template.id)) {
                      <p class="text-sm text-muted">{{ text.treeLoading() }}</p>
                    } @else if (treeErrors().has(template.id)) {
                      <p class="text-sm text-danger">{{ text.treeError() }}</p>
                    } @else if (trees().get(template.id); as nodes) {
                      <ul class="flex flex-col gap-1 border-l border-border pl-3">
                        @for (node of nodes; track $index) {
                          <li
                            class="flex items-center gap-2 text-sm text-text"
                            [style.padding-left.rem]="node.depth * 1.25"
                          >
                            <sol-icon name="layers" size="sm" class="text-muted" />
                            <span>{{ node.name }}</span>
                            <span
                              class="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand"
                            >
                              {{ methodologyLabel(node.methodology) }}
                            </span>
                          </li>
                        }
                      </ul>
                    }
                  }
                </div>
              </sol-card>
            }
          </div>

          <sol-card>
            <div class="flex flex-col gap-4">
              <div>
                <sol-select
                  [label]="text.leaderLabel()"
                  [placeholder]="text.leaderPlaceholder()"
                  [options]="memberOptions()"
                  [searchable]="true"
                  [formControl]="leadControl"
                ></sol-select>
                @if (membersError()) {
                  <p class="mt-1 text-xs text-danger">{{ membersError() }}</p>
                }
                @if (showLeadRequired()) {
                  <p class="mt-1 text-xs text-danger">
                    {{ text.leaderRequired() }}
                  </p>
                }
              </div>

              @if (generateError()) {
                <div
                  role="alert"
                  class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
                >
                  {{ generateError() }}
                </div>
              }

              <div>
                <sol-button
                  type="button"
                  variant="primary"
                  [disabled]="generating() || !selectedId()"
                  (click)="generate()"
                >
                  {{ generating() ? text.generating() : text.generate() }}
                </sol-button>
              </div>
            </div>
          </sol-card>
        }
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

  private loadTemplates(): void {
    this.loading.set(true);
    this.loadError.set(null);

    this.templatesService.list().subscribe({
      next: (res) => {
        this.templates.set(res.data ?? []);
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
