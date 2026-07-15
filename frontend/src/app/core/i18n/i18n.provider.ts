import {
  EnvironmentProviders,
  Provider,
  isDevMode,
  provideAppInitializer,
  inject,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { provideTransloco, translocoConfig, TranslocoService } from '@jsverse/transloco';
import { TranslocoHttpLoader } from './i18n.loader';

/** Idioma por defecto y de respaldo del proyecto: español colombiano formal. */
export const I18N_DEFAULT_LANG = 'es-CO';

/**
 * Providers de i18n para `app.config.ts`. Un `provideAppInitializer` garantiza
 * que el JSON del idioma por defecto esté cargado ANTES de que la app termine
 * de arrancar. Si la carga falla, degrada de forma segura (las claves sin
 * traducir se muestran tal cual) en vez de bloquear el bootstrap — mismo patrón
 * que el runtime de theming de `@solercia/ui`.
 */
export function provideI18n(): (Provider | EnvironmentProviders)[] {
  return [
    ...provideTransloco({
      config: translocoConfig({
        defaultLang: I18N_DEFAULT_LANG,
        fallbackLang: I18N_DEFAULT_LANG,
        availableLangs: [I18N_DEFAULT_LANG],
        reRenderOnLangChange: true,
        prodMode: !isDevMode(),
      }),
      loader: TranslocoHttpLoader,
    }),
    provideAppInitializer(async () => {
      const transloco = inject(TranslocoService);
      try {
        await firstValueFrom(transloco.load(transloco.getDefaultLang()));
      } catch (error) {
        // Fallback: si el JSON del idioma por defecto no carga (ausente,
        // corrupto o bloqueado), la app debe arrancar igual — las claves sin
        // traducir se muestran tal cual. Nunca relanzar: eso rechazaría la
        // promesa del inicializador y dejaría la app en blanco en TODAS las
        // rutas.
        console.warn(
          'provideI18n: no se pudo cargar el idioma por defecto, se usarán claves sin traducir.',
          error,
        );
      }
    }),
  ];
}
