/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

// Semantic color -> CSS variable (RGB channels) with alpha support.
const c = (name) => `rgb(var(--sp-${name}) / <alpha-value>)`;

/**
 * Tailwind CSS preset for @boki/ui.
 *
 * Add to your tailwind.config.js:
 *   presets: [require('@boki/ui/tailwind-preset')]
 *
 * Token values are driven by --sp-* CSS variables injected at runtime
 * by ThemeService from the active theme JSON.
 */
module.exports = {
  theme: {
    extend: {
      // Semantic colors driven by --sp-* variables. Values switch between
      // :root and .dark by ThemeService at runtime.
      colors: {
        brand: c('brand'),
        'brand-fg': c('brand-fg'),
        'brand-hover': c('brand-hover'),
        'brand-soft': c('brand-soft'),
        'brand-soft-fg': c('brand-soft-fg'),

        page: c('page'),
        surface: c('surface'),
        elevated: c('elevated'),
        sunken: c('sunken'),

        text: c('text'),
        muted: c('muted'),
        subtle: c('subtle'),

        border: c('border'),
        'border-strong': c('border-strong'),

        success: c('success'),
        'success-soft': c('success-soft'),
        'success-soft-fg': c('success-soft-fg'),
        warning: c('warning'),
        'warning-soft': c('warning-soft'),
        'warning-soft-fg': c('warning-soft-fg'),
        danger: c('danger'),
        'danger-soft': c('danger-soft'),
        'danger-soft-fg': c('danger-soft-fg'),
        info: c('info'),
        accent: c('accent'),
        ring: c('ring'),
      },
      borderRadius: {
        sm: 'var(--sp-radius-sm)',
        DEFAULT: 'var(--sp-radius-md)',
        md: 'var(--sp-radius-md)',
        lg: 'var(--sp-radius-lg)',
        xl: 'var(--sp-radius-xl)',
        '2xl': 'var(--sp-radius-2xl)',
        full: 'var(--sp-radius-full)',
      },
      boxShadow: {
        xs: 'var(--sp-shadow-xs)',
        sm: 'var(--sp-shadow-sm)',
        DEFAULT: 'var(--sp-shadow-sm)',
        md: 'var(--sp-shadow-md)',
        lg: 'var(--sp-shadow-lg)',
        xl: 'var(--sp-shadow-xl)',
      },
      fontFamily: {
        sans: ['var(--sp-font-sans)'],
        display: ['var(--sp-font-display)'],
        mono: ['var(--sp-font-mono)'],
      },
      transitionTimingFunction: {
        theme: 'var(--sp-ease)',
      },
      ringColor: {
        DEFAULT: c('ring'),
      },
    },
  },
};
