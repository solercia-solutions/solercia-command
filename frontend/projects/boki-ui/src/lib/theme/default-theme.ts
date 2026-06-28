/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { ThemeFile } from './theme.model';

/**
 * Bundled default theme — same data as assets/themes/default.json.
 *
 * ThemeService uses this as the initial signal value so the app is themed
 * even before the HTTP request completes (or if it fails entirely).
 * Consumers can override by calling ThemeService.loadTheme(url) or
 * ThemeService.loadThemeObject(file).
 */
export const DEFAULT_THEME: ThemeFile = {
  light: {
    meta: { tenant: 'default', name: 'Solercia Light' },
    color: {
      brand: '#4F46E5',
      brandFg: '#FFFFFF',
      brandHover: '#4338CA',
      brandSoft: '#EEF2FF',
      brandSoftFg: '#4338CA',

      page: '#F4F6FB',
      surface: '#FFFFFF',
      elevated: '#FFFFFF',
      sunken: '#EDF1F8',

      text: '#0B1220',
      muted: '#5A6B85',
      subtle: '#8A99B3',

      border: '#E5E9F2',
      borderStrong: '#D3DAE8',

      success: '#0E9F6E',
      successSoft: '#E3F5EE',
      successSoftFg: '#047857',
      warning: '#D97706',
      warningSoft: '#FDF0E3',
      warningSoftFg: '#B45309',
      danger: '#E02424',
      dangerSoft: '#FDEBEB',
      dangerSoftFg: '#B91C1C',
      info: '#2563EB',
      accent: '#7C3AED',
      ring: '#6366F1',
    },
    radius: {
      sm: '8px',
      md: '10px',
      lg: '14px',
      xl: '18px',
      '2xl': '24px',
      full: '9999px',
    },
    shadow: {
      xs: '0 1px 2px 0 rgba(15, 23, 42, 0.04)',
      sm: '0 1px 3px 0 rgba(15, 23, 42, 0.07), 0 1px 2px -1px rgba(15, 23, 42, 0.05)',
      md: '0 6px 16px -4px rgba(15, 23, 42, 0.10), 0 2px 6px -2px rgba(15, 23, 42, 0.06)',
      lg: '0 16px 36px -10px rgba(15, 23, 42, 0.16), 0 6px 14px -8px rgba(15, 23, 42, 0.10)',
      xl: '0 28px 60px -16px rgba(15, 23, 42, 0.22)',
    },
    typography: {
      fontSans: "'Inter', system-ui, -apple-system, sans-serif",
      fontDisplay: "'Manrope', 'Inter', system-ui, sans-serif",
      fontMono: "'JetBrains Mono', ui-monospace, monospace",
    },
    motion: {
      fast: '120ms',
      base: '200ms',
      slow: '320ms',
      ease: 'cubic-bezier(0.4, 0, 0.2, 1)',
    },
  },
  dark: {
    meta: { tenant: 'default', name: 'Solercia Dark' },
    color: {
      brand: '#6366F1',
      brandFg: '#FFFFFF',
      brandHover: '#818CF8',
      brandSoft: '#20264A',
      brandSoftFg: '#C7D2FE',

      page: '#0A0F1C',
      surface: '#131A2B',
      elevated: '#1B2438',
      sunken: '#0E1424',

      text: '#E6EBF4',
      muted: '#93A1B8',
      subtle: '#647189',

      border: '#25304A',
      borderStrong: '#36425F',

      success: '#34D399',
      successSoft: '#10241E',
      successSoftFg: '#6EE7B7',
      warning: '#FBBF24',
      warningSoft: '#2A2110',
      warningSoftFg: '#FCD34D',
      danger: '#F87171',
      dangerSoft: '#2C1618',
      dangerSoftFg: '#FCA5A5',
      info: '#60A5FA',
      accent: '#A78BFA',
      ring: '#818CF8',
    },
    radius: {
      sm: '8px',
      md: '10px',
      lg: '14px',
      xl: '18px',
      '2xl': '24px',
      full: '9999px',
    },
    shadow: {
      xs: '0 1px 2px 0 rgba(0, 0, 0, 0.40)',
      sm: '0 1px 3px 0 rgba(0, 0, 0, 0.50), 0 1px 2px -1px rgba(0, 0, 0, 0.40)',
      md: '0 8px 20px -6px rgba(0, 0, 0, 0.60), 0 3px 8px -4px rgba(0, 0, 0, 0.50)',
      lg: '0 18px 40px -12px rgba(0, 0, 0, 0.70), 0 6px 14px -8px rgba(0, 0, 0, 0.55)',
      xl: '0 30px 64px -16px rgba(0, 0, 0, 0.75)',
    },
    typography: {
      fontSans: "'Inter', system-ui, -apple-system, sans-serif",
      fontDisplay: "'Manrope', 'Inter', system-ui, sans-serif",
      fontMono: "'JetBrains Mono', ui-monospace, monospace",
    },
    motion: {
      fast: '120ms',
      base: '200ms',
      slow: '320ms',
      ease: 'cubic-bezier(0.4, 0, 0.2, 1)',
    },
  },
};
