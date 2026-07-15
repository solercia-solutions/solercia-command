import {
  ApplicationConfig,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import {
  provideTheme,
  SOL_DEFAULT_THEME,
  SOL_I18N,
  type ThemeFile,
} from '@solercia/ui';
import { routes } from './app.routes';
import { authInterceptor } from '@features/auth/auth.interceptor';
import { provideI18n, I18nService } from '@shared/i18n';
import solerciaDefaultTheme from '../assets/themes/solercia-default.theme.json';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withXhr(), withInterceptors([authInterceptor])),
    // Runtime de theming de @solercia/ui: es la ÚNICA fuente de verdad del tema.
    // Emite los 95 tokens --sol-* sobre :root y gestiona el toggle claro/oscuro
    // (clave localStorage `sol-dark-mode`, clase `.dark` en <html>/<body>).
    provideTheme(),
    // Identidad visual de gestion_proyectos (marca índigo) como tema por
    // defecto: sustituye al tema "Vértice" empaquetado en la librería.
    { provide: SOL_DEFAULT_THEME, useValue: solerciaDefaultTheme as unknown as ThemeFile },
    // i18n real (Transloco, es-CO por defecto).
    ...provideI18n(),
    // Cablea el contrato i18n de @solercia/ui a nuestra fachada Transloco, para
    // que los componentes sol-* traduzcan con el mismo motor que la app.
    { provide: SOL_I18N, useExisting: I18nService },
  ],
};
