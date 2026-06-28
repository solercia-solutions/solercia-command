/** @type {import('tailwindcss').Config} */
module.exports = {
  // Toggle dark mode by adding/removing the 'dark' class on <html>.
  darkMode: 'class',
  content: ['./src/**/*.{html,ts}'],
  theme: {
    extend: {
      // Semantic colors driven by --sp-* CSS variables (RGB channels).
      // The values switch automatically between :root and .dark, so these
      // utilities respond to the theme without per-element dark: variants.
      colors: {
        brand: 'rgb(var(--sp-brand) / <alpha-value>)',
        'brand-fg': 'rgb(var(--sp-brand-fg) / <alpha-value>)',
        page: 'rgb(var(--sp-bg-page) / <alpha-value>)',
        surface: 'rgb(var(--sp-surface) / <alpha-value>)',
        text: 'rgb(var(--sp-text) / <alpha-value>)',
        muted: 'rgb(var(--sp-muted) / <alpha-value>)',
        border: 'rgb(var(--sp-border) / <alpha-value>)',
        success: 'rgb(var(--sp-success) / <alpha-value>)',
        warning: 'rgb(var(--sp-warning) / <alpha-value>)',
        danger: 'rgb(var(--sp-danger) / <alpha-value>)'
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif']
      }
    }
  },
  plugins: []
};
