import { SOL_TABLE_VARIANTS, type SolTableVariant } from '@shared/ui';
import type { ThemeLoaderConfig } from '@solercia/ui/theme-studio';

/**
 * Campos `meta` que viajan dentro del ThemeFile fuera del contrato `ThemeMeta` de la librería.
 * El Theme Studio de `@solercia/ui/theme-studio` los edita (`features.loader`,
 * `features.tableVariantMetaKey`); el shell los lee de aquí y los aplica sobre `<html>`.
 *
 * Solo tipos y listas cerradas: el import de `@solercia/ui/theme-studio` es `type`-only para que
 * el bundle inicial no cargue el Studio.
 */
export type StudioTableStyle = SolTableVariant;
export type StudioLoaderPresentation = ThemeLoaderConfig['presentation'];
export type StudioLoaderAnimation = ThemeLoaderConfig['animation'];
export type ThemeStudioLoaderForm = ThemeLoaderConfig;

export const STUDIO_TABLE_STYLES: ReadonlyArray<StudioTableStyle> = SOL_TABLE_VARIANTS;
export const STUDIO_LOADER_PRESENTATIONS: ReadonlyArray<StudioLoaderPresentation> = [
  'current',
  'centered',
  'backdrop',
];
export const STUDIO_LOADER_ANIMATIONS: ReadonlyArray<StudioLoaderAnimation> = [
  'spin',
  'pulse',
  'shake',
  'none',
];

export interface ThemeMetaExtras {
  loader?: ThemeStudioLoaderForm;
  tableStyle?: StudioTableStyle;
}
