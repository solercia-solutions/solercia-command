/**
 * Códigos con título y mensaje propios en `assets/i18n/es-CO.json` bajo
 * `shared.errorState.codes.{codigo}`. Cualquier otro código cae al genérico: no hay una entrada
 * por cada valor posible.
 */
const CODES_WITH_OWN_TEXT: ReadonlySet<number> = new Set([401, 403, 404, 500]);

function codeKey(code: number): string {
  return CODES_WITH_OWN_TEXT.has(code) ? String(code) : 'generic';
}

/** Clave i18n del título para un código de error HTTP. */
export function errorTitleKey(code: number): string {
  return `shared.errorState.codes.${codeKey(code)}.title`;
}

/** Clave i18n del mensaje por defecto para un código de error HTTP. */
export function errorMessageKey(code: number): string {
  return `shared.errorState.codes.${codeKey(code)}.message`;
}
