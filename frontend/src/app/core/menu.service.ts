import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { apiBase } from './api.config';

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
 * Loads the menu tree the authenticated user is allowed to see
 * (GET /auth/me/menus) and exposes it as a signal so the shell can render a
 * permission-driven navigation. Falls back to an empty tree on error, which
 * lets the shell show its static links instead.
 */
@Injectable({ providedIn: 'root' })
export class MenuService {
  private readonly http = inject(HttpClient);
  private readonly _menus = signal<MenuNode[]>([]);
  private readonly _loaded = signal<boolean>(false);

  /** The accessible menu tree, ordered by `order`. */
  readonly menus = this._menus.asReadonly();

  /** True once a successful menu load has populated the tree. */
  readonly loaded = this._loaded.asReadonly();

  /** Fetch the menu tree for the current session. */
  load(): void {
    this.http.get<unknown>(`${apiBase}/auth/me/menus`).subscribe({
      next: (res) => {
        this._menus.set(normalizeMenus(res));
        this._loaded.set(true);
      },
      error: () => {
        this._menus.set([]);
        this._loaded.set(false);
      },
    });
  }

  /** Clear the tree (on logout). */
  clear(): void {
    this._menus.set([]);
    this._loaded.set(false);
  }
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
