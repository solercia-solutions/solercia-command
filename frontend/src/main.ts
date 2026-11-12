import { bootstrapApplication } from '@angular/platform-browser';
import { mergeApplicationConfig } from '@angular/core';
import { SOL_DEFAULT_THEME, type ThemeFile } from '@solercia/ui';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/app.component';
import solerciaDefaultTheme from './assets/themes/solercia-default.theme.json';

/**
 * URL del tema por defecto empaquetado (mismo asset que el import estático de
 * arriba). Ruta relativa resuelta contra `<base href="/">` → siempre
 * `/assets/themes/solercia-default.theme.json`, independiente de la ruta activa.
 */
const DEFAULT_THEME_URL = 'assets/themes/solercia-default.theme.json';

/**
 * Carga el tema por defecto desde el asset estático POR HTTP en el arranque.
 *
 * Por qué HTTP y no solo el import empaquetado: el default es el nivel 2 de la
 * cadena de degradación (organización → default → CSS de `:root`) y debe poder
 * suplantarse interceptando la petición del asset (pruebas en navegador sin
 * backend) o reemplazando el archivo desplegado. El import estático NO es
 * interceptable; el fetch sí. En producción el fetch devuelve el MISMO JSON,
 * así que el look no cambia.
 *
 * Si el fetch falla (asset ausente, red), cae al import empaquetado — el mismo
 * `solerciaDefaultTheme` que `app.config` ya provee como red de seguridad.
 */
async function resolveDefaultTheme(): Promise<ThemeFile> {
  try {
    const res = await fetch(DEFAULT_THEME_URL, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as ThemeFile;
  } catch {
    return solerciaDefaultTheme as ThemeFile;
  }
}

resolveDefaultTheme()
  .then((defaultTheme) =>
    // El default resuelto por HTTP gana sobre el `SOL_DEFAULT_THEME` empaquetado
    // de `app.config` (último provider del mismo token prevalece en Angular DI):
    // en producción es idéntico al import.
    bootstrapApplication(
      AppComponent,
      mergeApplicationConfig(appConfig, {
        providers: [{ provide: SOL_DEFAULT_THEME, useValue: defaultTheme }],
      }),
    ),
  )
  .catch((err) => console.error(err));
