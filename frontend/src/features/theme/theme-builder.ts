import type { ThemeFile } from '@shared/ui';
import baseThemeJson from '../../assets/themes/solercia-default.theme.json';

/**
 * Value of the appearance editor form — the SUBSET of the ThemeFile this UI
 * edits. Everything else keeps the bundled default (solercia-default.theme):
 * the builder deep-clones the default and overrides only these fields, so the
 * result always satisfies the 47 mandatory v1 tokens (`isRenderableTheme`).
 */
export interface AppearanceFormValue {
  /** Nombre de marca (meta.logo.altText → ThemeService.brandName). */
  brandName: string;
  /** URL del logo (http/https o data-URL; @solercia/ui la sanitiza). */
  logoUrl: string;
  /** Color primario (hex #rrggbb) — ambos modos. */
  primaryColor: string;
  /** Color de acento (hex #rrggbb) — ambos modos. */
  accentColor: string;
  /** Fondo de página (hex #rrggbb) — SOLO modo claro; el oscuro conserva el suyo. */
  pageBg: string;
  /** Radio base en px (primitives.radius.md; sm/lg se derivan). */
  radius: number;
  /** Densidad de controles y espaciado. */
  density: 'compact' | 'comfortable';
  /** Ancho de borde en px (primitives.borderWidth.thin). */
  borderWidth: number;
  /** Personalizar sidebar/header; apagado = siguen el modo claro/oscuro. */
  customChrome: boolean;
  /** Fondo del sidebar (ambos modos, branding fijo del tenant). */
  sidebarBg: string;
  /** Texto del sidebar (ambos modos). */
  sidebarText: string;
  /** Fondo del header (ambos modos). */
  headerBg: string;
}

/** Defaults = the resolved values of solercia-default.theme.json (light). */
export const DEFAULT_APPEARANCE: AppearanceFormValue = {
  brandName: '',
  logoUrl: '',
  primaryColor: '#4F46E5',
  accentColor: '#F59E0B',
  pageBg: '#F4F6FB',
  radius: 10,
  density: 'comfortable',
  borderWidth: 1,
  customChrome: false,
  sidebarBg: '#FFFFFF',
  sidebarText: '#647189',
  headerBg: '#FFFFFF',
};

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

/** True when the value is a 6-digit hex color (the only form the editor emits). */
export function isHexColor(value: unknown): value is string {
  return typeof value === 'string' && HEX_RE.test(value);
}

/**
 * Loose structural view of the ThemeFile for building/reading. The v2 blocks
 * (`sidebar`/`header`) are emitted PARTIALLY on purpose: `resolveCssVars`
 * resolves each EMIT_TABLE row independently, so any path we do not set falls
 * back to its default (derived from the primary color / the active mode) —
 * e.g. `--sol-sidebar-active-bg` keeps its `color-mix(primary 10%)` default.
 */
interface ThemeShape {
  meta: { tenant: string; logo?: { url: string; altText: string; width: number } };
  primitives: {
    radius: Record<string, string>;
    space: Record<string, string>;
    size: { control: Record<string, string> };
    borderWidth: { thin: string };
    [key: string]: unknown;
  };
  modes: Record<
    'light' | 'dark',
    {
      semantic: {
        color: Record<string, string>;
        surface: Record<string, string>;
        [key: string]: unknown;
      };
      component: {
        sidebar?: { bg: string; text: string };
        header?: { bg: string; blur: string };
        [key: string]: unknown;
      };
    }
  >;
}

const BASE_THEME = baseThemeJson as unknown as ThemeShape;

/**
 * Build a complete, renderable ThemeFile from the editor form: deep clone of
 * the bundled default + the edited overrides. Mapped fields:
 * - `primaryColor`/`accentColor` → `semantic.color.primary|accent` (both modes)
 * - `pageBg` → `semantic.surface.page` (LIGHT mode only)
 * - `radius` → `primitives.radius.sm|md|lg` (derived scale)
 * - `density` → `primitives.size.control.*` + `primitives.space.*`
 * - `borderWidth` → `primitives.borderWidth.thin`
 * - `customChrome` + sidebar/header colors → `component.sidebar|header` (both
 *   modes — per-tenant chrome branding is mode-invariant by design)
 * - `brandName`/`logoUrl` → `meta.tenant` + `meta.logo`
 */
export function buildThemeFile(form: AppearanceFormValue): ThemeFile {
  const file = structuredClone(BASE_THEME);
  const brand = form.brandName.trim();
  const logoUrl = form.logoUrl.trim();

  file.meta = {
    tenant: brand || file.meta.tenant,
    logo: { url: logoUrl, altText: brand || 'Solercia Command', width: 120 },
  };

  const radius = clampInt(form.radius, 0, 24);
  file.primitives.radius['sm'] = `${Math.max(0, radius - 2)}px`;
  file.primitives.radius['md'] = `${radius}px`;
  file.primitives.radius['lg'] = `${radius === 0 ? 0 : radius + 4}px`;
  file.primitives.borderWidth.thin = `${clampInt(form.borderWidth, 1, 3)}px`;

  if (form.density === 'compact') {
    file.primitives.size.control = { sm: '28px', md: '32px', lg: '36px' };
    file.primitives.space = {
      xs: '2px',
      sm: '6px',
      md: '12px',
      lg: '18px',
      xl: '24px',
    };
  }

  for (const mode of ['light', 'dark'] as const) {
    const modeConfig = file.modes[mode];
    if (isHexColor(form.primaryColor)) {
      modeConfig.semantic.color['primary'] = form.primaryColor;
    }
    if (isHexColor(form.accentColor)) {
      modeConfig.semantic.color['accent'] = form.accentColor;
    }
    if (form.customChrome) {
      if (isHexColor(form.sidebarBg) && isHexColor(form.sidebarText)) {
        modeConfig.component.sidebar = {
          bg: form.sidebarBg,
          text: form.sidebarText,
        };
      }
      if (isHexColor(form.headerBg)) {
        modeConfig.component.header = { bg: form.headerBg, blur: 'none' };
      }
    }
  }

  if (isHexColor(form.pageBg)) {
    file.modes.light.semantic.surface['page'] = form.pageBg;
  }

  return file as unknown as ThemeFile;
}

/**
 * Hydrate the editor form from a STORED theme (`null` = defaults). Reads only
 * the literal values this editor writes; token references or missing paths
 * fall back to the default form value — defensive against hand-edited themes.
 */
export function readAppearance(theme: ThemeFile | null): AppearanceFormValue {
  if (!theme) {
    return { ...DEFAULT_APPEARANCE };
  }
  const shape = theme as unknown as Partial<ThemeShape>;
  const light = shape.modes?.light;
  const sidebar = light?.component?.sidebar;
  const header = light?.component?.header;
  const tenant = shape.meta?.tenant ?? '';

  return {
    brandName:
      shape.meta?.logo?.altText && shape.meta.logo.altText !== 'Solercia Command'
        ? shape.meta.logo.altText
        : tenant !== 'solercia-pm'
          ? tenant
          : '',
    logoUrl: shape.meta?.logo?.url ?? '',
    primaryColor: hexOr(light?.semantic?.color?.['primary'], DEFAULT_APPEARANCE.primaryColor),
    accentColor: hexOr(light?.semantic?.color?.['accent'], DEFAULT_APPEARANCE.accentColor),
    pageBg: hexOr(light?.semantic?.surface?.['page'], DEFAULT_APPEARANCE.pageBg),
    radius: pxOr(shape.primitives?.radius?.['md'], DEFAULT_APPEARANCE.radius),
    density:
      shape.primitives?.size?.control?.['md'] === '32px' ? 'compact' : 'comfortable',
    borderWidth: pxOr(shape.primitives?.borderWidth?.thin, DEFAULT_APPEARANCE.borderWidth),
    customChrome: Boolean(sidebar || header),
    sidebarBg: hexOr(sidebar?.bg, DEFAULT_APPEARANCE.sidebarBg),
    sidebarText: hexOr(sidebar?.text, DEFAULT_APPEARANCE.sidebarText),
    headerBg: hexOr(header?.bg, DEFAULT_APPEARANCE.headerBg),
  };
}

function hexOr(value: unknown, fallback: string): string {
  return isHexColor(value) ? value : fallback;
}

function pxOr(value: unknown, fallback: number): number {
  if (typeof value !== 'string') {
    return fallback;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clampInt(value: number, min: number, max: number): number {
  const n = Math.round(Number.isFinite(value) ? value : min);
  return Math.min(max, Math.max(min, n));
}
