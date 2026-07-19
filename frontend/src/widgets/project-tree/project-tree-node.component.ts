import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  SolBadgeComponent,
  SolCardComponent,
  SolIconComponent,
  SolProgressBarComponent,
  type SolProgressVariant,
} from '@shared/ui';
import {
  METHODOLOGY_BADGE_VARIANT,
  METHODOLOGY_LABELS,
  TreeNodeVM,
} from '@entities/project/project.model';

/**
 * Recursive tree node: renders itself for each child (design.md Decision 2 —
 * self-referencing component instead of a flattened list, so ARIA
 * `treeitem`/`group` nesting matches the DOM naturally).
 *
 * Gap de librería (criterio del cambio 13-ui-component-audit): `@solercia/ui`
 * 0.3.0 no exporta un primitivo `sol-tree`, así que el árbol se arma a mano
 * aquí (`role="treeitem"`/`role="group"` + recursión). SÍ se reutilizan sus
 * primitivos de tarjeta, insignia, barra de avance e ícono — nada de eso se
 * reimplementa. Queda registrado como pendiente de aporte a la librería.
 */
@Component({
  selector: 'sol-project-tree-node',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    SolBadgeComponent,
    SolCardComponent,
    SolIconComponent,
    SolProgressBarComponent,
    ProjectTreeNodeComponent,
  ],
  template: `
    <div
      role="treeitem"
      [attr.aria-expanded]="hasChildren() ? expanded() : null"
      tabindex="0"
      class="rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
    >
      <sol-card [hoverable]="true">
        <div
          class="flex flex-wrap items-center gap-2 sm:flex-nowrap"
          [style.paddingLeft.px]="depth() * 16"
        >
          @if (hasChildren()) {
            <button
              type="button"
              tabindex="-1"
              (click)="toggle()"
              [attr.aria-label]="
                (expanded() ? 'Colapsar ' : 'Expandir ') + node().name
              "
              class="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-sunken hover:text-text"
            >
              <sol-icon
                [name]="expanded() ? 'chevron-down' : 'chevron-right'"
                size="sm"
              />
            </button>
          } @else {
            <span class="h-8 w-8 shrink-0" aria-hidden="true"></span>
          }

          <span class="min-w-0 flex-1 truncate text-sm font-semibold text-text">
            {{ node().name }}
          </span>

          <sol-badge [variant]="badgeVariant()" size="sm">
            {{ methodologyLabel() }}
          </sol-badge>

          <div class="flex min-w-28 items-center gap-2">
            @if (node().rollupError) {
              <span class="text-xs text-danger">{{ node().rollupError }}</span>
            } @else if (!node().rollup) {
              <span class="text-xs text-muted" aria-hidden="true">—</span>
            } @else if (node().rollup!.total === 0) {
              <span class="text-xs text-muted">Sin tareas</span>
            } @else {
              <span class="text-xs font-medium text-muted">
                {{ node().rollup!.done }}/{{ node().rollup!.total }}
              </span>
              <sol-progress-bar
                class="w-16"
                mode="continuous"
                size="sm"
                [value]="node().rollup!.done"
                [max]="node().rollup!.total"
                [variant]="progressVariant()"
              />
            }
          </div>

          <a
            [routerLink]="['/projects', node().id]"
            tabindex="-1"
            [attr.aria-label]="'Ir al proyecto ' + node().name"
            class="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-sunken hover:text-brand"
          >
            <sol-icon name="link" size="sm" />
          </a>
        </div>
      </sol-card>

      @if (hasChildren() && expanded()) {
        <div role="group" class="mt-1.5 flex flex-col gap-1.5">
          @for (child of node().children; track child.id) {
            <sol-project-tree-node [node]="child" [depth]="depth() + 1" />
          }
        </div>
      }
    </div>
  `,
})
export class ProjectTreeNodeComponent {
  readonly node = input.required<TreeNodeVM>();
  readonly depth = input<number>(0);

  protected readonly expanded = signal(false);

  protected readonly hasChildren = computed(
    () => this.node().children.length > 0,
  );

  protected readonly methodologyLabel = computed(
    () =>
      METHODOLOGY_LABELS[this.node().methodology] ?? this.node().methodology,
  );

  protected readonly badgeVariant = computed(
    () => METHODOLOGY_BADGE_VARIANT[this.node().methodology] ?? 'neutral',
  );

  /** Color threshold for the roll-up bar (design.md Decision 3, "variant por umbral"). */
  protected readonly progressVariant = computed<SolProgressVariant>(() => {
    const rollup = this.node().rollup;
    if (!rollup || rollup.total === 0) return 'primary';
    const percent = (rollup.done / rollup.total) * 100;
    if (percent >= 100) return 'success';
    if (percent < 30) return 'warning';
    return 'primary';
  });

  protected toggle(): void {
    this.expanded.update((value) => !value);
  }
}
