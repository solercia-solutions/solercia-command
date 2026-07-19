import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  input,
} from '@angular/core';
import { I18nService } from '@shared/i18n';
import { ProjectTreeNodeComponent } from './project-tree-node.component';
import { TreeFocusState } from './tree-focus-state';
import { TreeNodeVM } from '@entities/project/project.model';

/**
 * Forest container: `role="tree"` wrapping one `project-tree-node` per root
 * (design.md Data Flow). The recursion for deeper levels lives entirely
 * inside `project-tree-node`. Provides `TreeFocusState` so every descendant
 * node — at any depth — shares one roving-tabindex cursor (task 4.2).
 */
@Component({
  selector: 'sol-project-tree',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [TreeFocusState],
  imports: [ProjectTreeNodeComponent],
  template: `
    <div
      role="tree"
      [attr.aria-label]="treeAriaLabel()"
      class="flex flex-col gap-1.5 sm:gap-2"
    >
      @for (root of nodes(); track root.id) {
        <sol-project-tree-node [node]="root" [depth]="0" />
      }
    </div>
  `,
})
export class ProjectTreeComponent implements OnInit {
  readonly nodes = input.required<TreeNodeVM[]>();

  private readonly focus = inject(TreeFocusState);
  private readonly i18n = inject(I18nService);

  protected readonly treeAriaLabel = this.i18n.t('hierarchy.tree.ariaLabel');

  /** Roving tabindex starts on the first root — the tree has one Tab stop. */
  ngOnInit(): void {
    const roots = this.nodes();
    if (roots.length > 0) {
      this.focus.activeId.set(roots[0].id);
    }
  }
}
