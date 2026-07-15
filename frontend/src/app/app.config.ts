import {
  ApplicationConfig,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import { routes } from './app.routes';
import { authInterceptor } from './core/auth.interceptor';
import { provideTheme } from './core/theme.provider';
import {
  provideTheme as provideSolerciaUiTheme,
  SOL_I18N,
  createIdentitySolI18n,
} from '@solercia/ui';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withXhr(), withInterceptors([authInterceptor])),
    // Theming propio de la app (tokens --sp-*), consumido por los componentes bk-*.
    provideTheme(),
    // Runtime de theming de @solercia/ui: emite los tokens --sol-* en :root a
    // partir del tema por defecto empaquetado en la librería (zero-config).
    provideSolerciaUiTheme(),
    // i18n passthrough: la app no tiene motor de i18n, así que se usa el
    // adaptador identidad de la librería (devuelve la clave sin traducir).
    { provide: SOL_I18N, useValue: createIdentitySolI18n() },
  ],
};
