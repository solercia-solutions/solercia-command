import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Translation, TranslocoLoader } from '@jsverse/transloco';

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
    return this.http.get<Translation>(`assets/i18n/${lang}.json`);
  }
}
