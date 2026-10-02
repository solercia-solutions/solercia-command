import {
  ApplicationConfig,
  inject,
  provideZoneChangeDetection,
} from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeEsCo from '@angular/common/locales/es-CO';
import { provideRouter, withNavigationErrorHandler } from '@angular/router';
import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import {
  provideTheme,
  SOL_DEFAULT_THEME,
  SOL_I18N,
  THEME_SOURCE,
  type ThemeFile,
} from '@solercia/ui';
import { routes } from './app.routes';
import { authInterceptor } from '@features/auth/auth.interceptor';
import { OrgThemeSource } from '@features/theme/org-theme.source';
import { provideI18n, I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { reloadOnMissingChunk } from '@shared/lib/utils/reload-on-missing-chunk.util';
import solerciaDefaultTheme from '../assets/themes/solercia-default.theme.json';

// Los pipes de fecha/moneda usan 'es-CO' explícito; sin este registro
// Angular lanza NG0701 y el bloque que usa el pipe no se renderiza.
registerLocaleData(localeEsCo);

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    // Tras un rebuild, una pestaña abierta con el build anterior pide chunks que ya no
    // existen (404) y el router abortaba la navegación en silencio: aquí se recarga la
    // página sobre la URL destino, una sola vez por URL. Si esa misma URL vuelve a
    // fallar (despliegue incompleto), no se recarga otra vez y se avisa, para no repetir
    // la pantalla en blanco sin mensaje. Ver reload-on-missing-chunk.util.
    provideRouter(
      routes,
      withNavigationErrorHandler((error) => {
        if (reloadOnMissingChunk(error) !== 'blocked') return;
        // Duración 0: el aviso se queda hasta que la persona lo cierre.
        inject(AlertService).showWarning(
          inject(I18nService).translate('shared.errorState.outdatedVersion'),
          0,
        );
      }),
    ),
    provideHttpClient(withXhr(), withInterceptors([authInterceptor])),
    // Runtime de theming de @solercia/ui: es la ÚNICA fuente de verdad del tema.
    // Emite los 95 tokens --sol-* sobre :root y gestiona el toggle claro/oscuro
    // (clave localStorage `sol-dark-mode`, clase `.dark` en <html>/<body>).
    provideTheme(),
    // Identidad visual de gestion_proyectos (marca índigo) como tema por
    // defecto: sustituye al tema "Vértice" empaquetado en la librería.
    // Nota: main.ts vuelve a resolver este MISMO asset por HTTP en el arranque
    // y sobreescribe este provider con el resultado (último provider gana). Este
    // valor empaquetado queda como red de seguridad si el fetch del asset falla.
    { provide: SOL_DEFAULT_THEME, useValue: solerciaDefaultTheme as ThemeFile },
    // Puerto THEME_SOURCE: carga el ThemeFile de la organización del JWT
    // (GET /organizations/me/theme). El host lo consume vía push
    // (TenantThemeService → setTenantTheme) porque el pull de la librería
    // (SOL_TENANT_RESOLVER) solo tipa tenants numéricos y aquí son UUID.
    { provide: THEME_SOURCE, useExisting: OrgThemeSource },
    // i18n real (Transloco, es-CO por defecto).
    ...provideI18n(),
    // Cablea el contrato i18n de @solercia/ui a nuestra fachada Transloco, para
    // que los componentes sol-* traduzcan con el mismo motor que la app.
    { provide: SOL_I18N, useExisting: I18nService },
  ],
};
