/**
 * Un tramo del breadcrumb del shell. Con `route` se pinta como enlace; sin ella es un texto plano —
 * las agrupaciones del menú no tienen vista propia y el último tramo es la ubicación actual.
 */
export interface BreadcrumbItem {
  label: string;
  /** Ruta del shell (routerLink). Ausente en agrupaciones y en el tramo actual. */
  route?: string;
  /** Nombre de ícono del registry de `@solercia/ui`, ya resuelto (solo el primer tramo lo usa). */
  icon?: string;
}
