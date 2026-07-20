import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import {
  ConnectedAccount,
  Connector,
  ConnectorCreatePayload,
  JiraImportResult,
} from './connector.model';

@Injectable({ providedIn: 'root' })
export class ConnectorsService {
  private readonly http = inject(HttpClient);

  list(): Observable<{ data: Connector[] }> {
    return this.http.get<{ data: Connector[] }>(`${apiBase}/connectors`);
  }

  create(payload: ConnectorCreatePayload): Observable<{ data: Connector }> {
    return this.http.post<{ data: Connector }>(`${apiBase}/connectors`, payload);
  }

  delete(connectorId: string): Observable<void> {
    return this.http.delete<void>(`${apiBase}/connectors/${connectorId}`);
  }

  accounts(connectorId: string): Observable<{ data: ConnectedAccount[] }> {
    return this.http.get<{ data: ConnectedAccount[] }>(
      `${apiBase}/connectors/${connectorId}/accounts`,
    );
  }

  revokeAccount(accountId: string): Observable<void> {
    return this.http.delete<void>(`${apiBase}/connected-accounts/${accountId}`);
  }

  /** Registro directo de credenciales api_token (GLPI/Jira). */
  registerCredentials(
    connectorId: string,
    payload: Record<string, string>,
  ): Observable<{ data: ConnectedAccount }> {
    return this.http.post<{ data: ConnectedAccount }>(
      `${apiBase}/connectors/${connectorId}/credentials`,
      payload,
    );
  }

  /** Preview del import de archivo Jira (CSV/XLSX) — no persiste nada. */
  importJiraFile(
    connectorId: string,
    file: File,
  ): Observable<{ data: JiraImportResult }> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<{ data: JiraImportResult }>(
      `${apiBase}/connectors/${connectorId}/jira/import-file`,
      form,
    );
  }

  /**
   * URL de navegación completa hacia el authorize del backend.
   *
   * Al ser una navegación de página (302 al IdP) el interceptor no puede
   * adjuntar el header Bearer, así que `accessToken` viaja como
   * `access_token` en el query — soporte que el backend acepta SOLO en ese
   * endpoint. El token lo provee la capa que sí puede leer la sesión
   * (`features/auth`); esta entity se mantiene sin dependencias hacia
   * arriba (regla FSD: entities solo importa de shared).
   * `redirectTo` es el destino de retorno validado contra la allowlist del
   * backend: el callback devolverá al navegador allí con `?connected=1` o
   * `?error=<código>`.
   */
  authorizeUrl(
    connectorId: string,
    redirectTo: string,
    accessToken: string,
  ): string {
    const params = new URLSearchParams({
      access_token: accessToken,
      redirect_to: redirectTo,
    });
    return `${apiBase}/connectors/${connectorId}/authorize?${params.toString()}`;
  }
}
