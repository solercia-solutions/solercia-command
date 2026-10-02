import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import {
  ConnectedAccount,
  Connector,
  ConnectorCreatePayload,
  JiraImportResult,
  SolerciaConnectRegisterPayload,
  SolerciaConnectRegisterResult,
  SolerciaConnectSession,
  SolerciaConnectSessionStart,
  SolerciaConnectStatus,
  SolerciaConnectSyncResult,
} from './connector.model';

/**
 * Todas las llamadas se excluyen del manejador global de errores: la página de
 * conexiones y la tarjeta de Solercia Connect ya muestran su propio error (y el
 * sondeo de estado y de sesión corre en segundo plano).
 */
@Injectable({ providedIn: 'root' })
export class ConnectorsService {
  private readonly http = inject(HttpClient);

  list(): Observable<{ data: Connector[] }> {
    return this.http.get<{ data: Connector[] }>(`${apiBase}/connectors`, {
      context: skipGlobalErrorHandling(),
    });
  }

  create(payload: ConnectorCreatePayload): Observable<{ data: Connector }> {
    return this.http.post<{ data: Connector }>(`${apiBase}/connectors`, payload, {
      context: skipGlobalErrorHandling(),
    });
  }

  delete(connectorId: string): Observable<void> {
    return this.http.delete<void>(`${apiBase}/connectors/${connectorId}`, {
      context: skipGlobalErrorHandling(),
    });
  }

  accounts(connectorId: string): Observable<{ data: ConnectedAccount[] }> {
    return this.http.get<{ data: ConnectedAccount[] }>(
      `${apiBase}/connectors/${connectorId}/accounts`,
      { context: skipGlobalErrorHandling() },
    );
  }

  revokeAccount(accountId: string): Observable<void> {
    return this.http.delete<void>(`${apiBase}/connected-accounts/${accountId}`, {
      context: skipGlobalErrorHandling(),
    });
  }

  /** Registro directo de credenciales api_token (GLPI/Jira). */
  registerCredentials(
    connectorId: string,
    payload: Record<string, string>,
  ): Observable<{ data: ConnectedAccount }> {
    return this.http.post<{ data: ConnectedAccount }>(
      `${apiBase}/connectors/${connectorId}/credentials`,
      payload,
      { context: skipGlobalErrorHandling() },
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
      { context: skipGlobalErrorHandling() },
    );
  }

  /**
   * Emite un ticket efímero de un solo uso para la navegación de authorize
   * (XHR normal con el interceptor Bearer). El JWT nunca viaja en una URL
   * (CWE-598): la navegación posterior usa SOLO este ticket opaco, que
   * expira en segundos y se consume al primer uso.
   */
  createAuthorizeTicket(
    connectorId: string,
  ): Observable<{ data: { ticket: string } }> {
    return this.http.post<{ data: { ticket: string } }>(
      `${apiBase}/connectors/${connectorId}/authorize-ticket`,
      {},
      { context: skipGlobalErrorHandling() },
    );
  }

  /**
   * URL de navegación completa hacia el authorize del backend.
   *
   * Al ser una navegación de página (302 al IdP) el interceptor no puede
   * adjuntar el header Bearer, así que la autenticación viaja como
   * `ticket` (ver {@link createAuthorizeTicket}). `redirectTo` es el
   * destino de retorno validado contra la allowlist del backend: el
   * callback devolverá al navegador allí con `?connected=1` o
   * `?error=<código>`.
   */
  authorizeUrl(connectorId: string, redirectTo: string, ticket: string): string {
    const params = new URLSearchParams({
      ticket,
      redirect_to: redirectTo,
    });
    return `${apiBase}/connectors/${connectorId}/authorize?${params.toString()}`;
  }

  // -- Solercia Connect --------------------------------------------------------

  /**
   * Registra (o re-registra, es idempotente por organización) la conexión de
   * Solercia Connect para UNA cuenta Microsoft 365. La llave del runtime la
   * pone el servidor; el navegador nunca la ve.
   */
  createSolerciaConnect(
    payload: SolerciaConnectRegisterPayload,
  ): Observable<{ data: SolerciaConnectRegisterResult }> {
    return this.http.post<{ data: SolerciaConnectRegisterResult }>(
      `${apiBase}/connectors/solercia-connect`,
      payload,
      { context: skipGlobalErrorHandling() },
    );
  }

  /**
   * Pregunta a Connect si la sesión guardada de la cuenta sirve. `data.state`
   * ES la respuesta: una falla del lado de Connect no viene como error HTTP.
   * No llamar mientras un inicio de sesión esté `running`.
   */
  solerciaConnectStatus(
    connectorId: string,
  ): Observable<{ data: SolerciaConnectStatus }> {
    return this.http.get<{ data: SolerciaConnectStatus }>(
      `${apiBase}/connectors/${connectorId}/solercia-connect/status`,
      { context: skipGlobalErrorHandling() },
    );
  }

  /** Abre el navegador supervisado en el equipo de la persona (202 + session_id). */
  startSolerciaConnectLogin(
    connectorId: string,
  ): Observable<{ data: SolerciaConnectSessionStart }> {
    return this.http.post<{ data: SolerciaConnectSessionStart }>(
      `${apiBase}/connectors/${connectorId}/solercia-connect/connect`,
      {},
      { context: skipGlobalErrorHandling() },
    );
  }

  /** Sondea una sesión de inicio de sesión supervisado. */
  solerciaConnectSession(
    connectorId: string,
    sessionId: string,
  ): Observable<{ data: SolerciaConnectSession }> {
    return this.http.get<{ data: SolerciaConnectSession }>(
      `${apiBase}/connectors/${connectorId}/solercia-connect/sessions/${encodeURIComponent(sessionId)}`,
      { context: skipGlobalErrorHandling() },
    );
  }

  /** Trae el correo de los últimos `sinceDays` días a insumos/tareas. */
  syncSolerciaConnect(
    connectorId: string,
    sinceDays: number,
  ): Observable<{ data: SolerciaConnectSyncResult }> {
    return this.http.post<{ data: SolerciaConnectSyncResult }>(
      `${apiBase}/connectors/${connectorId}/solercia-connect/sync`,
      { since_days: sinceDays },
      { context: skipGlobalErrorHandling() },
    );
  }
}
