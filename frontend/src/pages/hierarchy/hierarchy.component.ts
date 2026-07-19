import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Observable, catchError, forkJoin, map, of, timeout } from 'rxjs';
import { I18nService } from '@shared/i18n';
import { SolSpinnerComponent } from '@shared/ui';
import { ProjectTreeComponent } from '@widgets/project-tree';
import { ProjectsService } from '@entities/project/projects.service';
import {
  Project,
  ProjectProgressNode,
  TreeNodeVM,
} from '@entities/project/project.model';

/** Tope por rama para `/progress`: una raíz lenta no debe congelar el resto (R7). */
const PROGRESS_TIMEOUT_MS = 15_000;

/**
 * Host de datos de la vista jerárquica: compone el bosque en el cliente a
 * partir de `GET /projects` (estructura, agrupada por `parent_project_id`)
 * más una llamada `GET /projects/{id}/progress` por raíz (roll-up anidado,
 * cubre todo el subárbol — design.md Decisión 1).
 */
@Component({
  selector: 'sol-hierarchy',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ProjectTreeComponent, SolSpinnerComponent],
  template: `
    <section class="flex flex-col gap-6">
      <div>
        <h1 class="text-2xl font-semibold text-text">{{ text.title() }}</h1>
        <p class="text-sm text-muted">{{ text.subtitle() }}</p>
      </div>

      @if (loading()) {
        <div class="flex items-center gap-3 py-8" role="status">
          <sol-spinner size="md" />
          <span class="text-sm text-muted">{{ text.loading() }}</span>
        </div>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (roots().length === 0) {
        <div
          class="rounded-xl border border-border bg-surface px-4 py-8 text-center"
        >
          <p class="text-base font-medium text-text">
            {{ text.emptyTitle() }}
          </p>
          <p class="mt-1 text-sm text-muted">{{ text.emptySubtitle() }}</p>
        </div>
      } @else {
        <sol-project-tree [nodes]="roots()" />
      }
    </section>
  `,
})
export class HierarchyComponent implements OnInit {
  private readonly projectsService = inject(ProjectsService);
  private readonly i18n = inject(I18nService);

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    title: this.i18n.t('hierarchy.title'),
    subtitle: this.i18n.t('hierarchy.subtitle'),
    loading: this.i18n.t('hierarchy.loading'),
    emptyTitle: this.i18n.t('hierarchy.empty.title'),
    emptySubtitle: this.i18n.t('hierarchy.empty.subtitle'),
  } as const;

  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly roots = signal<TreeNodeVM[]>([]);

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.loadError.set(null);

    this.projectsService.list().subscribe({
      next: (res) => this.buildForest(res.data ?? []),
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? this.i18n.translate('hierarchy.errors.network')
            : this.i18n.translate('hierarchy.errors.load'),
        );
      },
    });
  }

  /** Raíces = `parent_project_id == null`; huérfano (padre inactivo/ausente) se promueve a raíz (design.md Decisión 1). */
  private buildForest(projects: Project[]): void {
    const byId = new Map(projects.map((project) => [project.id, project]));
    const childrenOf = new Map<string, Project[]>();
    const rootProjects: Project[] = [];

    for (const project of projects) {
      const parentId = project.parent_project_id;
      if (parentId && byId.has(parentId)) {
        const siblings = childrenOf.get(parentId) ?? [];
        siblings.push(project);
        childrenOf.set(parentId, siblings);
      } else {
        rootProjects.push(project);
      }
    }

    if (rootProjects.length === 0) {
      this.roots.set([]);
      this.loading.set(false);
      return;
    }

    // timeout + catchError individual por raíz: si el /progress de una rama
    // falla O se demora más de PROGRESS_TIMEOUT_MS, esa rama queda marcada
    // con error mientras las demás se resuelven normal (R7 — "Falla parcial
    // de una raíz" no bloquea el resto del bosque ni congela la vista).
    forkJoin(
      rootProjects.map(
        (root): Observable<ProgressOutcome> =>
          this.projectsService.progress(root.id).pipe(
            timeout(PROGRESS_TIMEOUT_MS),
            map((res): ProgressOutcome => ({
              rootId: root.id,
              node: res.data,
              error: null,
            })),
            catchError(() =>
              of<ProgressOutcome>({
                rootId: root.id,
                node: null,
                error: this.i18n.translate('hierarchy.errors.branch'),
              }),
            ),
          ),
      ),
    ).subscribe((outcomes) => {
      const rollupById = new Map<string, { done: number; total: number }>();
      const errorByRoot = new Map<string, string>();
      for (const outcome of outcomes) {
        if (outcome.node) {
          this.flattenRollup(outcome.node, rollupById);
        } else if (outcome.error) {
          errorByRoot.set(outcome.rootId, outcome.error);
        }
      }
      this.roots.set(
        rootProjects.map((root) =>
          this.toNode(root, childrenOf, rollupById, errorByRoot.get(root.id)),
        ),
      );
      this.loading.set(false);
    });
  }

  private flattenRollup(
    node: ProjectProgressNode,
    into: Map<string, { done: number; total: number }>,
  ): void {
    into.set(node.project_id, {
      done: node.rollup.done,
      total: node.rollup.total,
    });
    node.children.forEach((child) => this.flattenRollup(child, into));
  }

  private toNode(
    project: Project,
    childrenOf: Map<string, Project[]>,
    rollupById: Map<string, { done: number; total: number }>,
    rollupError?: string,
  ): TreeNodeVM {
    return {
      id: project.id,
      name: project.name,
      methodology: project.methodology,
      rollup: rollupById.get(project.id),
      rollupError,
      // El error sólo se atribuye al nodo raíz de la rama fallida; los hijos
      // simplemente quedan sin `rollup` (se renderizan con "—", sin repetir
      // el mensaje en cada nivel).
      children: (childrenOf.get(project.id) ?? []).map((child) =>
        this.toNode(child, childrenOf, rollupById),
      ),
    };
  }
}

/** Resultado de un `/progress` individual dentro del `forkJoin` por raíz. */
interface ProgressOutcome {
  rootId: string;
  node: ProjectProgressNode | null;
  error: string | null;
}
