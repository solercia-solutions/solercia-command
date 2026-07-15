import { Injectable, Signal, inject } from '@angular/core';
import { TranslocoService, translateSignal } from '@jsverse/transloco';
import { SolI18n } from '@solercia/ui';

/**
 * Fachada propia sobre Transloco. Los componentes y features dependen
 * ÚNICAMENTE de este servicio — nunca importan `@jsverse/transloco`
 * directamente — para mantener bajo el costo de reemplazar la librería.
 *
 * Implementa el contrato `SolI18n` de `@solercia/ui`, así que también es el
 * motor de traducción de los componentes `sol-*` (se cablea vía `SOL_I18N` en
 * `app.config.ts`).
 */
@Injectable({ providedIn: 'root' })
export class I18nService implements SolI18n {
  private readonly transloco = inject(TranslocoService);

  /** Idioma activo como signal reactivo (ej. para un selector de idioma). */
  readonly activeLang: Signal<string> = this.transloco.activeLang;

  /**
   * Traducción instantánea (síncrona) de una clave. Si la clave no existe en
   * el JSON del idioma activo, Transloco cae de forma segura: devuelve la
   * clave misma (nunca lanza, nunca devuelve `undefined`).
   */
  translate(key: string, params?: Record<string, unknown>): string {
    return this.transloco.translate(key, params);
  }

  /**
   * Traducción reactiva de una clave: el signal devuelto se recalcula solo
   * cuando cambia el idioma activo. Debe llamarse dentro de un contexto de
   * inyección (inicializador de campo o constructor).
   */
  t(key: string, params?: Record<string, unknown>): Signal<string> {
    return translateSignal(key, params);
  }

  /**
   * Variante de `t()` para varias claves a la vez, en el mismo orden.
   * Útil para listas estáticas (ej. pasos de un asistente).
   */
  tMany(keys: string[]): Signal<string[]> {
    return translateSignal(keys);
  }

  setActiveLang(lang: string): void {
    this.transloco.setActiveLang(lang);
  }
}
