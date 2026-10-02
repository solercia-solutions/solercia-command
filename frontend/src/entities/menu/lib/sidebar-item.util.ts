import type { SidebarItem } from '../model/sidebar-item.model';

/**
 * Transformaciones puras sobre el árbol de `SidebarItem` (el modelo de navegación que consumen el
 * sidebar, la bottom-nav y el layout). Sin estado ni inyección.
 */

/**
 * Quita, a cualquier profundidad, los ítems con `visible === false`, y poda toda agrupación que se
 * quede sin hijos visibles. Es el mismo filtro que aplica `sol-sidebar`: quien lo use ve
 * exactamente lo que el menú lateral muestra.
 */
export function filterVisibleItems(items: readonly SidebarItem[]): SidebarItem[] {
  const resultado: SidebarItem[] = [];
  for (const item of items) {
    if (item.visible === false) continue;
    if (item.children?.length) {
      const hijosVisibles = filterVisibleItems(item.children);
      if (hijosVisibles.length === 0) continue;
      resultado.push({ ...item, children: hijosVisibles });
    } else {
      resultado.push(item);
    }
  }
  return resultado;
}

/**
 * Hojas (ítems navegables, con `route`) descendientes de `items`, en profundidad y en el orden del
 * menú. Una agrupación nunca se incluye: no tiene vista propia.
 */
export function leafItemsOf(items: readonly SidebarItem[]): SidebarItem[] {
  const hojas: SidebarItem[] = [];
  for (const item of items) {
    if (item.children?.length) {
      hojas.push(...leafItemsOf(item.children));
    } else if (item.route) {
      hojas.push(item);
    }
  }
  return hojas;
}

/** Clave estable de un ítem para conjuntos de estado (expandido, seleccionado). */
export function itemKey(item: SidebarItem): string {
  return item.id ?? item.label;
}

/** Claves de todos los descendientes de un ítem (no incluye al propio ítem). */
export function descendantKeys(item: SidebarItem): string[] {
  const claves: string[] = [];
  for (const hijo of item.children ?? []) {
    claves.push(itemKey(hijo), ...descendantKeys(hijo));
  }
  return claves;
}
