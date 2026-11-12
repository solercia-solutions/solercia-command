import { Injectable, computed, inject, signal, untracked } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import { readApiError } from '@shared/lib/api-error';
import type { SidebarItem } from '@entities/menu';

/** A node of the navigation menu tree the current user can access. */
export interface MenuNode {
  id: string;
  name: string;
  icon?: string | null;
  path?: string | null;
  order: number;
  children: MenuNode[];
}

/**
 * Menu situation, one per state the shell must be able to show. `empty` is
 * legitimate (a user without assigned options) and is NOT an error: "no data"
 * and "the request failed" must look different on screen.
 */
export type MenuStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

/**
 * Loads the menu tree the authenticated user is allowed to see
 * (GET /auth/me/menus) and exposes it as signals so the shell can render a
 * permission-driven, multi-level navigation with its own state.
 *
 * A failed load is no longer disguised as an empty menu: it stays as `error`
 * and the sidebar offers a retry (`load()` again). A refresh that fails keeps
 * the menu already painted.
 */
@Injectable({ providedIn: 'root' })
export class MenuService {
  private readonly http = inject(HttpClient);
  private readonly _menus = signal<MenuNode[]>([]);
  private readonly _loading = signal<boolean>(false);
  private readonly _loaded = signal<boolean>(false);
  private readonly _failed = signal<boolean>(false);
  private readonly _errorDetail = signal<string | null>(null);

  /** The accessible menu tree, ordered by `order`. */
  readonly menus = this._menus.asReadonly();

  /** True once a successful menu load has populated the tree. */
  readonly loaded = this._loaded.asReadonly();

  /**
   * Message the backend sent with the last failed load, or `null` when it
   * sent none (the sidebar then shows its generic error text).
   */
  readonly errorDetail = this._errorDetail.asReadonly();

  /** The menu tree in the shape the sidebar, bottom-nav and breadcrumb consume. */
  readonly sidebarItems = computed<SidebarItem[]>(() => this._menus().map(toSidebarItem));

  /**
   * Derived state. Loading or failing only win while there is nothing to
   * show: a menu already painted stays `ready`.
   */
  readonly status = computed<MenuStatus>(() => {
    if (this._menus().length > 0) return 'ready';
    if (this._loading()) return 'loading';
    if (this._failed()) return 'error';
    return this._loaded() ? 'empty' : 'idle';
  });

  /** Fetch (or retry) the menu tree for the current session. */
  load(): void {
    // The shell's hydration effect re-runs whenever auth signals settle; the
    // in-flight guard keeps those re-runs from firing duplicate requests. It
    // is read untracked so a caller inside an effect does not subscribe to it.
    if (untracked(this._loading)) {
      return;
    }
    this._loading.set(true);
    // Background hydration: opts out of the global error handler (the sidebar
    // shows its own error state with a retry).
    this.http
      .get<unknown>(`${apiBase}/auth/me/menus`, { context: skipGlobalErrorHandling() })
      .subscribe({
        next: (res) => {
          this._menus.set(normalizeMenus(res));
          this._failed.set(false);
          this._errorDetail.set(null);
          this._loaded.set(true);
          this._loading.set(false);
        },
        error: (err: unknown) => {
          this._failed.set(true);
          this._errorDetail.set(readApiError(err).detail);
          this._loading.set(false);
        },
      });
  }

  /** Clear the tree (on logout). */
  clear(): void {
    this._loading.set(false);
    this._menus.set([]);
    this._failed.set(false);
    this._errorDetail.set(null);
    this._loaded.set(false);
  }
}

/** Id suffix of the leaf that keeps a group's own route (see `toSidebarItem`). */
const OWN_ROUTE_LEAF_SUFFIX = ':self';

/**
 * Maps a menu node to the sidebar shape: name → label, path → route.
 *
 * A node with children becomes a group (the sidebar paints it as an
 * accordion, it never navigates). If it also has its own path, that route is
 * not lost: it becomes the first leaf of the group, with the same name and
 * icon.
 */
export function toSidebarItem(node: MenuNode): SidebarItem {
  const base = { id: node.id, label: node.name, icon: node.icon ?? '' };
  const route = node.path?.trim() || undefined;
  if (node.children.length === 0) {
    return route ? { ...base, route } : base;
  }
  const children = node.children.map(toSidebarItem);
  const ownLeaf: SidebarItem[] = route
    ? [{ ...base, id: `${node.id}${OWN_ROUTE_LEAF_SUFFIX}`, route }]
    : [];
  return { ...base, children: [...ownLeaf, ...children] };
}

/**
 * True for the leaf `toSidebarItem` adds to keep a group's own route. It
 * repeats its parent's name, so a breadcrumb drops it.
 */
export function isOwnRouteLeaf(item: SidebarItem): boolean {
  return item.id.endsWith(OWN_ROUTE_LEAF_SUFFIX);
}

/**
 * Accepts either a bare array or a `{ data: [...] }` envelope (the auth
 * endpoints return bare objects, the rest use the envelope) and coerces it to
 * a sorted `MenuNode[]`.
 */
function normalizeMenus(res: unknown): MenuNode[] {
  const raw = Array.isArray(res)
    ? res
    : (res as { data?: unknown } | null)?.data;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.map(toNode).sort((a, b) => a.order - b.order);
}

function toNode(value: unknown): MenuNode {
  const node = (value ?? {}) as Record<string, unknown>;
  const children = Array.isArray(node['children'])
    ? (node['children'] as unknown[]).map(toNode).sort((a, b) => a.order - b.order)
    : [];
  return {
    id: String(node['id'] ?? ''),
    name: String(node['name'] ?? ''),
    icon: (node['icon'] as string | null | undefined) ?? null,
    path: (node['path'] as string | null | undefined) ?? null,
    order: Number(node['order'] ?? 0),
    children,
  };
}
