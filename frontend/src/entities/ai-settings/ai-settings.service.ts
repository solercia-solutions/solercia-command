import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import {
  AiConnectionTestResult,
  AiPreset,
  AiSettings,
  AiSettingsUpdate,
} from './ai-settings.model';

/** `/ai/*`: la pantalla muestra sus propios errores (sin el manejador global). */
@Injectable({ providedIn: 'root' })
export class AiSettingsService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/ai`;

  getSettings(): Observable<{ data: AiSettings }> {
    return this.http.get<{ data: AiSettings }>(`${this.base}/settings`, {
      context: skipGlobalErrorHandling(),
    });
  }

  getPresets(): Observable<{ data: AiPreset[] }> {
    return this.http.get<{ data: AiPreset[] }>(`${this.base}/presets`, {
      context: skipGlobalErrorHandling(),
    });
  }

  update(payload: AiSettingsUpdate): Observable<{ data: AiSettings }> {
    return this.http.put<{ data: AiSettings }>(`${this.base}/settings`, payload, {
      context: skipGlobalErrorHandling(),
    });
  }

  /** Prueba la propuesta SIN guardarla (o la configuración efectiva si no hay cuerpo). */
  test(payload: AiSettingsUpdate | null): Observable<{ data: AiConnectionTestResult }> {
    return this.http.post<{ data: AiConnectionTestResult }>(`${this.base}/settings/test`, payload, {
      context: skipGlobalErrorHandling(),
    });
  }
}
