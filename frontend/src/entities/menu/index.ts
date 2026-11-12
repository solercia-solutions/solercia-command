// Barril del modelo de navegación del shell. El modelo y el servicio de administración de menús
// (`menu-admin.model.ts`, `menus.service.ts`) se siguen importando por su ruta completa.
export type { SidebarItem } from './model/sidebar-item.model';
export {
  filterVisibleItems,
  leafItemsOf,
  itemKey,
  descendantKeys,
} from './lib/sidebar-item.util';
export { breadcrumbTrail, normalizeRoute } from './lib/breadcrumb-trail.util';
