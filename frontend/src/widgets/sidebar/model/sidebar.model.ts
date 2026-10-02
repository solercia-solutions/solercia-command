// Puente puro: `SidebarItem` es un modelo del dominio de navegación y vive en `entities/menu`.
// widgets/ SÍ puede importar de entities/ (dirección correcta en FSD), así que este archivo solo
// reexporta — los imports de `@widgets/sidebar` no cambian.
export type { SidebarItem } from '@entities/menu';
