import type { ThemeFile, ThemeMeta } from '@shared/ui';
import type { ThemeMetaExtras, ThemeSidebarBehavior } from './theme-meta-extras';
import { DEFAULT_SIDEBAR_BEHAVIOR } from './theme-meta-extras';

/**
 * Comportamiento del menú lateral declarado por el tema de la organización (`meta.sidebar`), ya
 * resuelto con sus valores por defecto. El bloque vive en `meta` (invariante de modo), lo persiste
 * la API dentro del ThemeFile y el Theme Studio lo conserva sin editarlo (`metaExtrasSchema`);
 * aquí se lee con tipo y se valida campo por campo, nunca se aplica a ciegas.
 *
 * Sin tema activo, o con un `meta.sidebar` ausente o malformado, devuelve
 * {@link DEFAULT_SIDEBAR_BEHAVIOR} — el shell nunca cambia de comportamiento por un JSON incompleto.
 */
export function readSidebarBehavior(theme: ThemeFile | null | undefined): ThemeSidebarBehavior {
  const meta = theme?.meta as (ThemeMeta & ThemeMetaExtras) | undefined;
  const declared = meta?.sidebar;
  if (!declared || typeof declared !== 'object') return { ...DEFAULT_SIDEBAR_BEHAVIOR };

  return {
    autoCloseOnNavigate:
      typeof declared.autoCloseOnNavigate === 'boolean'
        ? declared.autoCloseOnNavigate
        : DEFAULT_SIDEBAR_BEHAVIOR.autoCloseOnNavigate,
  };
}
