import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  SolBadgeComponent,
  SolCardComponent,
  SolIconComponent,
  SolProgressBarComponent,
  type SolProgressVariant,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { TreeFocusState } from './tree-focus-state';
import {
  METHODOLOGY_BADGE_VARIANT,
  METHODOLOGY_LABELS,
  TreeNodeVM,
} from '@entities/project/project.model';

/**
 * Recursive tree node: renders itself for each child (design.md Decision 2 —
 * self-referencing component instead of a flattened list, so ARIA
 * `treeitem`/`group` nesting matches the DOM naturally). `role="treeitem"`
 * and keyboard handling live on the component HOST itself (not an inner
 * wrapper `<div>`), so this element is what receives focus and appears in
 * the roving-tabindex query in `moveFocus()`.
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
  host: {
    role: 'treeitem',
    class:
      'block rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50',
    '[attr.aria-expanded]': 'hasChildren() ? expanded() : null',
    '[attr.tabindex]': 'tabIndexValue()',
    '(keydown)': 'onKeydown($event)',
    '(focus)': 'onFocus()',
  },
  imports: [
    RouterLink,
    SolBadgeComponent,
    SolCardComponent,
    SolIconComponent,
    SolProgressBarComponent,
    ProjectTreeNodeComponent,
  ],
  template: `
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
            [attr.aria-label]="expandCollapseAria()"
            class="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-sunken hover:text-text"
          >
            <sol-icon
              [name]="expanded() ? 'chevron-down' : 'chevron-right'"
              size="sm"
            />
          </button>
        } @else {
          <span class="h-9 w-9 shrink-0" aria-hidden="true"></span>
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
            <span class="text-xs text-muted">{{ noTasksText() }}</span>
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
          [attr.aria-label]="goToProjectAria()"
          class="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-sunken hover:text-brand"
        >
          <sol-icon name="link" size="sm" />
        </a>
      </div>
    </sol-card>

    @if (hasChildren() && expanded()) {
      <div role="group" class="mt-1.5 flex flex-col gap-1.5 pl-2">
        @for (child of node().children; track child.id) {
          <sol-project-tree-node [node]="child" [depth]="depth() + 1" />
        }
      </div>
    }
  `,
})
export class ProjectTreeNodeComponent {
  readonly node = input.required<TreeNodeVM>();
  readonly depth = input<number>(0);

  private readonly el: ElementRef<HTMLElement> = inject(ElementRef);
  private readonly router = inject(Router);
  private readonly focus = inject(TreeFocusState);
  private readonly i18n = inject(I18nService);

  protected readonly noTasksText = this.i18n.t('hierarchy.node.noTasks');

  protected readonly expanded = signal(false);

  protected readonly hasChildren = computed(
    () => this.node().children.length > 0,
  );

  protected readonly isActive = computed(
    () => this.focus.activeId() === this.node().id,
  );

  /** Roving tabindex: only the active node is a Tab stop (task 4.2). */
  protected readonly tabIndexValue = computed(() => (this.isActive() ? 0 : -1));

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

  /** aria-label del botón de expandir/colapsar (varía con el nombre del nodo). */
  protected expandCollapseAria(): string {
    const key = this.expanded()
      ? 'hierarchy.node.collapseAria'
      : 'hierarchy.node.expandAria';
    return this.i18n.translate(key, { name: this.node().name });
  }

  /** aria-label de la acción "ir al proyecto" (varía con el nombre del nodo). */
  protected goToProjectAria(): string {
    return this.i18n.translate('hierarchy.node.goToProjectAria', {
      name: this.node().name,
    });
  }

  protected onFocus(): void {
    this.focus.activeId.set(this.node().id);
  }

  /** Enter/Espacio expande-colapsa o navega; flechas mueven el foco o el nivel (R8). */
  protected onKeydown(event: KeyboardEvent): void {
    switch (event.key) {
      case 'Enter':
      case ' ':
        event.preventDefault();
        this.activate();
        break;
      case 'ArrowRight':
        if (this.hasChildren() && !this.expanded()) {
          event.preventDefault();
          this.expanded.set(true);
        }
        break;
      case 'ArrowLeft':
        if (this.hasChildren() && this.expanded()) {
          event.preventDefault();
          this.expanded.set(false);
        }
        break;
      case 'ArrowDown':
        event.preventDefault();
        this.moveFocus(1);
        break;
      case 'ArrowUp':
        event.preventDefault();
        this.moveFocus(-1);
        break;
    }
  }

  /** Con hijos: expande/colapsa. Nodo hoja: activa "ir al proyecto" (task 4.2). */
  private activate(): void {
    if (this.hasChildren()) {
      this.expanded.update((value) => !value);
    } else {
      void this.router.navigate(['/projects', this.node().id]);
    }
  }

  /**
   * Mueve el foco al treeitem visible siguiente/anterior en orden del DOM.
   * Como los hijos colapsados no se renderizan, ese orden ya coincide con el
   * orden visual top-down — no hace falta una lista aplanada aparte.
   */
  private moveFocus(delta: number): void {
    const container = this.el.nativeElement.closest<HTMLElement>(
      '[role="tree"]',
    );
    if (!container) return;
    const items = Array.from(
      container.querySelectorAll<HTMLElement>('[role="treeitem"]'),
    );
    const index = items.indexOf(this.el.nativeElement);
    items[index + delta]?.focus();
  }
}
