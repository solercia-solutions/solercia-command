import type { SidebarItem } from '../model/sidebar-item.model';

/**
 * Normaliza una ruta para compararla: sin query string ni fragmento, sin barra final y con una
 * sola barra inicial (`/dashboard/` y `dashboard` valen lo mismo que `/dashboard`).
 */
export function normalizeRoute(route: string | null | undefined): string {
  const path = (route ?? '').split('?')[0].split('#')[0].trim();
  if (!path) return '';
  const withoutTrailing = path.replace(/\/+$/, '');
  return withoutTrailing.startsWith('/') ? withoutTrailing : `/${withoutTrailing}`;
}

/**
 * Camino desde la raíz del menú hasta la hoja cuya ruta coincide con `url` (la hoja de última),
 * para armar un breadcrumb. Arreglo vacío si la URL no está en el menú (un enlace profundo a una
 * vista sin ítem propio): quien llama decide qué mostrar.
 *
 * Recorre en profundidad: si dos hojas comparten ruta, gana la primera en el orden del menú.
 */
export function breadcrumbTrail(items: readonly SidebarItem[], url: string): SidebarItem[] {
  const target = normalizeRoute(url);
  if (!target) return [];

  const search = (nodes: readonly SidebarItem[], ancestors: SidebarItem[]): SidebarItem[] => {
    for (const node of nodes) {
      const path = [...ancestors, node];
      if (!node.children?.length && normalizeRoute(node.route) === target) return path;
      const inChildren = search(node.children ?? [], path);
      if (inChildren.length > 0) return inChildren;
    }
    return [];
  };

  return search(items, []);
}
