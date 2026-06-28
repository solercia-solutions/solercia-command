/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

/**
 * Runtime theme contract (light + dark) loaded from a JSON file at startup.
 *
 * Portable theming template: copy this model + ThemeService + a default.json
 * into any project and get JSON-driven, multi-tenant theming out of the box.
 * Modernizing the look = editing the JSON.
 *
 * Colors are authored as hex for human readability; ThemeService converts them
 * to "R G B" channels so Tailwind utilities can apply alpha
 * (e.g. rgb(var(--sp-brand) / 0.1)). Non-color scales (radius, shadow,
 * typography, motion) are injected as raw CSS values.
 */
export interface ThemeFile {
  light: ThemeConfig;
  dark: ThemeConfig;
}

export interface ThemeConfig {
  meta: ThemeMeta;
  color: ThemeColors;
  radius: ThemeScale;
  shadow: ThemeScale;
  typography: ThemeTypography;
  motion: ThemeMotion;
}

export interface ThemeMeta {
  /** Tenant id this palette belongs to (multi-tenant theming). */
  tenant: string;
  /** Human-readable theme name. */
  name: string;
}

/**
 * Semantic, role-based colors — defined PER MODE so light/dark differences
 * live in data, not in `dark:` variants scattered through templates.
 * `*Soft` are solid tint backgrounds with a matching `*SoftFg` foreground
 * (proper contrast chips, not washed-out alpha tints).
 */
export interface ThemeColors {
  brand: string;
  brandFg: string;
  brandHover: string;
  brandSoft: string;
  brandSoftFg: string;

  page: string;
  surface: string;
  elevated: string;
  sunken: string;

  text: string;
  muted: string;
  subtle: string;

  border: string;
  borderStrong: string;

  success: string;
  successSoft: string;
  successSoftFg: string;
  warning: string;
  warningSoft: string;
  warningSoftFg: string;
  danger: string;
  dangerSoft: string;
  dangerSoftFg: string;
  info: string;
  accent: string;
  ring: string;
}

export interface ThemeTypography {
  fontSans: string;
  fontDisplay: string;
  fontMono: string;
}

export interface ThemeMotion {
  fast: string;
  base: string;
  slow: string;
  ease: string;
}

/** A named scale of raw CSS values (e.g. radius, shadow). */
export type ThemeScale = Record<string, string>;
