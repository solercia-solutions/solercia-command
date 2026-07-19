import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { ProjectTreeNodeComponent } from './project-tree-node.component';
import { TreeNodeVM } from '@entities/project/project.model';

/**
 * Forest container: `role="tree"` wrapping one `project-tree-node` per root
 * (design.md Data Flow). The recursion for deeper levels lives entirely
 * inside `project-tree-node`.
 */
@Component({
  selector: 'sol-project-tree',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ProjectTreeNodeComponent],
  template: `
    <div role="tree" aria-label="Árbol de proyectos" class="flex flex-col gap-2">
      @for (root of nodes(); track root.id) {
        <sol-project-tree-node [node]="root" [depth]="0" />
      }
    </div>
  `,
})
export class ProjectTreeComponent {
  readonly nodes = input.required<TreeNodeVM[]>();
}
