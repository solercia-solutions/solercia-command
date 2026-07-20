/**
 * Navigation item rendered by the sidebar and the mobile bottom-nav.
 *
 * Ported from boki-front (`widgets/sidebar`). In this host the items come
 * from the permission-driven menu tree (`MenuService.menus()`), mapped at the
 * app shell (`MenuNode.name` → `label`, `MenuNode.path` → `route`).
 */
export interface SidebarItem {
  id: string;
  label: string;
  /** Backend icon key (`menus.icon`), resolved via `getNavIconName`. */
  icon?: string | null;
  /** Router path. `null`/`undefined` renders a non-navigating group item. */
  route?: string | null;
  /** Optional counter rendered as a pill next to the label. */
  badge?: number | string | null;
  /** Set to `false` to hide the item without removing it from the tree. */
  visible?: boolean;
  children?: SidebarItem[];
}
