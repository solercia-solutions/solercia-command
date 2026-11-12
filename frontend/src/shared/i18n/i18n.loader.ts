import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Translation, TranslocoLoader } from '@jsverse/transloco';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';

/**
 * Carga perezosa de los JSON de traducción por idioma desde
 * `assets/i18n/{lang}.json`. Único punto de la app que sabe CÓMO se
 * resuelve un archivo de idioma — el resto del código depende de
 * `I18nService`, nunca de este loader ni de Transloco directamente.
 */
@Injectable({ providedIn: 'root' })
export class TranslocoHttpLoader implements TranslocoLoader {
  private readonly http = inject(HttpClient);

  getTranslation(lang: string): Observable<Translation> {
    // Petición de arranque: se excluye del manejador global de errores, que
    // necesita estas mismas traducciones para poder avisar.
    return this.http.get<Translation>(`assets/i18n/${lang}.json`, {
      context: skipGlobalErrorHandling(),
    });
  }
}
