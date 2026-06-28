/** An app-level activity ("actividad") / navigation menu, hierarchical. */
export interface AdminMenu {
  id: string;
  name: string;
  icon?: string | null;
  path?: string | null;
  parent_id?: string | null;
  order: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

/** A menu plus its resolved children, for tree rendering. */
export interface AdminMenuNode extends AdminMenu {
  children: AdminMenuNode[];
}

/** Backend list envelope: { data: [...], meta: { total } }. */
export interface AdminMenuListResponse {
  data: AdminMenu[];
  meta?: { total: number };
}

/** Backend single-item envelope: { data: {...} }. */
export interface AdminMenuItemResponse {
  data: AdminMenu;
}

/** Payload for creating/updating a menu. */
export interface AdminMenuPayload {
  name: string;
  icon?: string | null;
  path?: string | null;
  parent_id?: string | null;
  order?: number;
  is_active?: boolean;
}

/**
 * Build a hierarchical tree from a flat list using `parent_id`. Children and
 * roots are ordered by `order`. Resilient to unknown/missing parents (treated
 * as roots) so a malformed dataset never drops nodes.
 */
export function buildMenuTree(flat: AdminMenu[]): AdminMenuNode[] {
  const byId = new Map<string, AdminMenuNode>();
  for (const menu of flat) {
    byId.set(menu.id, { ...menu, children: [] });
  }

  const roots: AdminMenuNode[] = [];
  for (const node of byId.values()) {
    const parent = node.parent_id ? byId.get(node.parent_id) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }

  const sort = (nodes: AdminMenuNode[]): void => {
    nodes.sort((a, b) => a.order - b.order);
    for (const node of nodes) {
      sort(node.children);
    }
  };
  sort(roots);
  return roots;
}

/** Flatten a tree into rows annotated with their depth (for indentation). */
export function flattenMenuTree(
  nodes: AdminMenuNode[],
  depth = 0,
): Array<{ menu: AdminMenuNode; depth: number }> {
  const rows: Array<{ menu: AdminMenuNode; depth: number }> = [];
  for (const node of nodes) {
    rows.push({ menu: node, depth });
    rows.push(...flattenMenuTree(node.children, depth + 1));
  }
  return rows;
}
