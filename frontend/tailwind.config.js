/** @type {import('tailwindcss').Config} */

// Puente de utilidades de marca -> tokens vivos de @solercia/ui.
// Los colores apuntan a las CSS custom properties `--sol-*` que emite el
// ThemeService (provideTheme); así `bg-brand`, `text-text`, `bg-surface`, etc.
// se retematizan solos por tenant y en claro/oscuro (clase `.dark`).
//
// NOTA (Wave B): los tokens --sol-* son colores HEX (no canales RGB), por lo
// que el modificador de opacidad de Tailwind (`bg-brand/10`) no puede inyectar
// alpha y renderiza opaco. Los tintes suaves usan `color-mix` explícito
// (brand-soft, success-soft, ...). El puente estático --sp-* se retiró.
const v = (name) => `var(--sol-${name})`;
const soft = (name, pct) => `color-mix(in srgb, var(--sol-${name}) ${pct}, transparent)`;

module.exports = {
  // Toggle dark mode by adding/removing the 'dark' class on <html> (ThemeService).
  darkMode: 'class',
  content: ['./src/**/*.{html,ts}'],
  theme: {
    extend: {
      colors: {
        brand: v('color-primary'),
        'brand-fg': '#ffffff',
        'brand-hover': v('color-primary'),
        'brand-soft': soft('color-primary', '12%'),
        'brand-soft-fg': v('color-primary'),

        // Compat con utilidades brand-blue heredadas de plantillas.
        'brand-blue': {
          light: soft('color-primary', '60%'),
          DEFAULT: v('color-primary'),
          dark: v('color-primary'),
        },

        page: v('bg-page'),
        surface: v('bg-surface'),
        elevated: v('bg-surface'),
        sunken: v('bg-sunken'),

        text: v('color-text-primary'),
        muted: v('color-text-secondary'),
        subtle: v('color-text-muted'),

        border: v('border-color-default'),
        'border-strong': v('border-color-default'),

        success: v('color-success'),
        'success-soft': soft('color-success', '14%'),
        'success-soft-fg': v('color-success'),
        warning: v('color-warning'),
        'warning-soft': soft('color-warning', '14%'),
        'warning-soft-fg': v('color-warning'),
        danger: v('color-danger'),
        'danger-soft': soft('color-danger', '12%'),
        'danger-soft-fg': v('color-danger'),
        info: v('color-info'),
        accent: v('color-accent'),
        ring: v('color-primary'),
      },
      borderRadius: {
        sm: v('border-radius-sm'),
        DEFAULT: v('border-radius-md'),
        md: v('border-radius-md'),
        lg: v('border-radius-lg'),
        full: v('border-radius-full'),
      },
      boxShadow: {
        xs: v('shadow-sm'),
        sm: v('shadow-sm'),
        DEFAULT: v('shadow-sm'),
        md: v('shadow-md'),
        lg: v('shadow-lg'),
        xl: v('shadow-lg'),
      },
      fontFamily: {
        sans: ['var(--sol-font-family)'],
        display: ['var(--sol-font-display)', 'var(--sol-font-family)'],
        mono: ['var(--sol-font-family-mono)'],
      },
      transitionTimingFunction: {
        theme: 'var(--sol-ease, cubic-bezier(0.4, 0, 0.2, 1))',
      },
      ringColor: {
        DEFAULT: v('color-primary'),
      },
    },
  },
  plugins: [],
};
