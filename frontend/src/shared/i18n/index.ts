export { I18nService } from './i18n.service';
export { provideI18n, I18N_DEFAULT_LANG } from './i18n.provider';
// Re-exportado tras nuestra propia superficie: úsalo en templates cuando un
// signal no sea práctico. Fuera de `core/i18n/`, este es el ÚNICO punto
// permitido para tocar Transloco directamente.
export { TranslocoPipe as SolTranslatePipe } from '@jsverse/transloco';
