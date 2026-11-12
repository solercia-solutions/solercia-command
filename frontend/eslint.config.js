// @ts-check
/** @type {import('eslint').Linter.Config[]} */
// Fronteras FSD, regla smart/dumb de shared/ui, restricción de Chart.js y
// convenciones de nombres (naming-convention + filename-case kebab) se heredan
// del preset compartible del ecosistema Solercia, publicado como paquete npm.
// Ver node_modules/@solercia/eslint-config/README.md.
import solerciaConfig from '@solercia/eslint-config';

export default [
  // Ignores GLOBALES: artefactos generados y dependencias.
  {
    ignores: [
      '.angular/',
      'dist/',
      'coverage/',
      'node_modules/',
      'playwright-report/',
      'test-results/',
    ],
  },
  ...solerciaConfig,
];
