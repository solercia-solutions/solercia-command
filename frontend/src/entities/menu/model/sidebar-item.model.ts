/**
 * Ítem de navegación del shell: lo consumen los widgets de presentación (sidebar, menú móvil
 * inferior, layout y migas de pan). Vive en `entities/menu` porque es un modelo del dominio de
 * navegación; `widgets/sidebar` lo reexporta como puente puro.
 *
 * En esta aplicación los ítems salen del árbol de menú por permisos (`GET /auth/me/menus`), que
 * `MenuService` convierte con `toSidebarItem`.
 */
export interface SidebarItem {
  id: string;
  label: string;
  /** Clave de ícono del backend (`menus.icon`); se resuelve con `getNavIconName`. */
  icon: string;
  /** Ausente en una agrupación pura: el sidebar la pinta como botón de expandir/colapsar, nunca
   *  como `routerLink`. Una agrupación que SÍ trae ruta propia la conserva como primera hoja
   *  (ver `toSidebarItem`). */
  route?: string;
  children?: SidebarItem[];
  badge?: string | number;
  visible?: boolean;
  /** Query params a aplicar en `[routerLink]` (opcional). */
  queryParams?: Record<string, string>;
}
