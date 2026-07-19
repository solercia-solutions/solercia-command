import { Injectable, signal } from '@angular/core';

/**
 * Roving-tabindex state shared by every `project-tree-node` inside one
 * `project-tree` (DI-scoped via the container's `providers: [TreeFocusState]`
 * — task 4.2). Only the node whose id matches `activeId` gets `tabindex="0"`;
 * every other node gets `-1`, so a single Tab press enters/leaves the tree
 * while arrow keys move focus between the currently visible treeitems.
 */
@Injectable()
export class TreeFocusState {
  readonly activeId = signal<string | null>(null);
}
