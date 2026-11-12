import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  SolBadgeComponent,
  SolCardComponent,
  SolIconComponent,
  SolProgressBarComponent,
  SolTreeComponent,
  SolTreeNodeDefDirective,
  type SolProgressVariant,
  type SolTreeNode,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import {
  METHODOLOGY_BADGE_VARIANT,
  METHODOLOGY_LABELS,
  TreeNodeVM,
} from '@entities/project/project.model';

/**
 * Bosque de proyectos montado sobre `sol-tree` de `@solercia/ui`.
 *
 * El MECANISMO del árbol (recursión, ARIA `tree`/`treeitem`/`group`, roving
 * tabindex con flechas, expandir/colapsar con el chevron y la cota de
 * profundidad) vive desde 0.5.0 en la librería — se extrajo justamente de la
 * implementación local que había aquí, así que este widget ya no la repite.
 * Lo que queda es el DOMINIO: el mapeo de `TreeNodeVM` a `SolTreeNode`, la
 * plantilla de cada nodo (tarjeta, insignia de metodología, avance roll-up y
 * enlace al proyecto) y la navegación.
 */
@Component({
  selector: 'sol-project-tree',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    SolBadgeComponent,
    SolCardComponent,
    SolIconComponent,
    SolProgressBarComponent,
    SolTreeComponent,
    SolTreeNodeDefDirective,
  ],
  template: `
    <!-- Las raíces arrancan expandidas (default de la librería). El árbol existe
         para mostrar el avance agregado de cada proyecto; abrirlo colapsado
         obligaría a expandir antes de ver lo único que se vino a ver, y dejaría
         la pantalla en cero al entrar. Un nivel basta: la jerarquía profunda
         sigue plegada y no satura. -->
    <sol-tree
      [nodes]="treeNodes()"
      [ariaLabel]="treeAriaLabel()"
      (nodeSelected)="goToProject($event)"
    >
      <ng-template solTreeNodeDef let-node>
        @let vm = nodeVM(node);
        @let rollup = vm.rollup;

        <sol-card [hoverable]="true">
          <div class="flex flex-wrap items-center gap-2 sm:flex-nowrap">
            <span class="min-w-0 flex-1 truncate text-sm font-semibold text-text">
              {{ vm.name }}
            </span>

            <sol-badge [variant]="badgeVariant(vm)" size="sm">
              {{ methodologyLabel(vm) }}
            </sol-badge>

            <div class="flex min-w-28 items-center gap-2">
              @if (vm.rollupError) {
                <span class="text-xs text-danger">{{ vm.rollupError }}</span>
              } @else if (!rollup) {
                <span class="text-xs text-muted" aria-hidden="true">—</span>
              } @else if (rollup.total === 0) {
                <span class="text-xs text-muted">{{ noTasksText() }}</span>
              } @else {
                <span class="text-xs font-medium text-muted">
                  {{ rollup.done }}/{{ rollup.total }}
                </span>
                <sol-progress-bar
                  class="w-16"
                  mode="continuous"
                  size="sm"
                  [value]="rollup.done"
                  [max]="rollup.total"
                  [variant]="progressVariant(vm)"
                />
              }
            </div>

            <a
              [routerLink]="['/projects', vm.id]"
              tabindex="-1"
              [attr.aria-label]="goToProjectAria(vm)"
              class="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-sunken hover:text-brand"
            >
              <sol-icon name="link" size="sm" />
            </a>
          </div>
        </sol-card>
      </ng-template>
    </sol-tree>
  `,
})
export class ProjectTreeComponent {
  readonly nodes = input.required<TreeNodeVM[]>();

  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);

  protected readonly treeAriaLabel = this.i18n.t('hierarchy.tree.ariaLabel');
  protected readonly noTasksText = this.i18n.t('hierarchy.node.noTasks');

  /**
   * Bosque de dominio traducido al nodo genérico de la librería: solo `id`,
   * `label` y `children`; el `TreeNodeVM` completo viaja opaco en `data` y lo
   * lee la plantilla proyectada. El árbol nunca interpreta el dominio.
   */
  protected readonly treeNodes = computed<SolTreeNode<TreeNodeVM>[]>(() =>
    this.toTreeNodes(this.nodes()),
  );

  /**
   * Estrecha la carga opaca del nodo genérico al view-model del dominio.
   * `solTreeNodeDef` no tiene cómo anclar el genérico, así que el contexto de
   * la plantilla llega con `data: unknown` y el estrechamiento es del
   * consumidor (mismo compromiso que `matTreeNodeDef`).
   */
  protected nodeVM(node: SolTreeNode): TreeNodeVM {
    return node.data as TreeNodeVM;
  }

  protected methodologyLabel(node: TreeNodeVM): string {
    return METHODOLOGY_LABELS[node.methodology] ?? node.methodology;
  }

  /** La librería no exporta su union de variantes: se replica la de la entidad. */
  protected badgeVariant(
    node: TreeNodeVM,
  ): 'info' | 'success' | 'warning' | 'neutral' {
    return METHODOLOGY_BADGE_VARIANT[node.methodology] ?? 'neutral';
  }

  /** Umbral de color de la barra de roll-up (design.md Decisión 3). */
  protected progressVariant(node: TreeNodeVM): SolProgressVariant {
    const rollup = node.rollup;
    if (!rollup || rollup.total === 0) return 'primary';
    const percent = (rollup.done / rollup.total) * 100;
    if (percent >= 100) return 'success';
    if (percent < 30) return 'warning';
    return 'primary';
  }

  /** `aria-label` de la acción "ir al proyecto" (varía con el nombre del nodo). */
  protected goToProjectAria(node: TreeNodeVM): string {
    return this.i18n.translate('hierarchy.node.goToProjectAria', {
      name: node.name,
    });
  }

  /**
   * Activar una hoja con Enter/Espacio ya no navega dentro del árbol: la
   * librería emite `nodeSelected` y el destino lo decide el consumidor. Es el
   * mismo `/projects/:id` del enlace de la tarjeta.
   */
  protected goToProject(node: SolTreeNode): void {
    void this.router.navigate(['/projects', node.id]);
  }

  private toTreeNodes(nodes: readonly TreeNodeVM[]): SolTreeNode<TreeNodeVM>[] {
    return nodes.map((node) => ({
      id: node.id,
      label: node.name,
      children: this.toTreeNodes(node.children),
      data: node,
    }));
  }
}
