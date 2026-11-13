/** Proveedores de integración registrados en el backend. */
export type ConnectorProvider =
  | 'solercia_connect'
  | 'microsoft365'
  | 'google'
  | 'jira'
  | 'glpi'
  | 'gitlab'
  | 'mcp'
  | 'fake';

/** Cómo obtiene credenciales el conector (fijo al crearlo). */
export type CredentialKind = 'oauth' | 'api_token' | 'none';

export type ConnectorStatus = 'active' | 'inactive' | 'error';

export type AccountStatus = 'active' | 'revoked' | 'expired' | 'error';

/** Conector como lo devuelve la API (nunca expone tokens). */
export interface Connector {
  id: string;
  provider: string;
  credential_kind: CredentialKind;
  status: ConnectorStatus;
  scopes: string[] | null;
  settings: Record<string, unknown> | null;
  created_at: string;
}

/** Cuenta conectada de un conector (nunca expone tokens). */
export interface ConnectedAccount {
  id: string;
  connector_id: string;
  user_id: string;
  external_account_id: string;
  display_name: string | null;
  status: AccountStatus;
}

/** Payload de creación: el proveedor fija el credential_kind. */
export interface ConnectorCreatePayload {
  provider: string;
  credential_kind: CredentialKind;
  settings?: Record<string, unknown>;
  token?: string;
}

/**
 * Cuerpo de error que devuelve la API (`app/shared/exceptions.py`):
 * `detail` humano, `code` estable y, a veces, `meta` con contexto accionable
 * (p. ej. el `session_id` de un inicio de sesión ya en curso tras un 409).
 */
export interface ApiErrorBody {
  detail?: string;
  code?: string;
  status?: number;
  meta?: Record<string, unknown> | null;
}

/** Issue normalizado que devuelve el preview del import de Jira. */
export interface NormalizedJiraIssue {
  key: string;
  title: string;
  issue_type: string;
  status_raw: string;
  status_bucket: string;
  priority: string;
  assignee_raw: string | null;
  sprint_name: string | null;
  story_points: number | null;
  labels: string[];
  source: string;
}

export interface JiraImportReport {
  total: number;
  normalized: number;
  unmapped_types: Record<string, number>;
  unmapped_statuses: Record<string, number>;
  unmapped_priorities: Record<string, number>;
  source: string;
}

export interface JiraImportResult {
  issues: NormalizedJiraIssue[];
  report: JiraImportReport;
  truncated: boolean;
  truncation_reason: string | null;
}

// ---------------------------------------------------------------------------
// Solercia Connect (`/connectors/solercia-connect*`): un conector por
// organización, una cuenta Microsoft 365, sesión de navegador supervisada en el
// equipo de la persona. Los nombres de campo reflejan
// `backend/app/modules/connectors/schemas.py`.
// ---------------------------------------------------------------------------

export type SolerciaConnectTarget = 'outlook' | 'teams' | 'onedrive';

export const SOLERCIA_CONNECT_TARGETS: readonly SolerciaConnectTarget[] = [
  'outlook',
  'teams',
  'onedrive',
] as const;

/** Estado durable de la conexión según `GET .../solercia-connect/status`. */
export type SolerciaConnectState =
  | 'connected'
  | 'needs_login'
  | 'runtime_unavailable'
  | 'runtime_unauthorized'
  | 'interactive_disabled'
  | 'misconfigured'
  | 'error';

/** Estado de una sesión de inicio de sesión supervisado. */
export type SolerciaConnectSessionState =
  | 'running'
  | 'connected'
  | 'failed'
  | 'not_found';

/** Configuración NO secreta guardada en `connectors.settings.solercia_connect`. */
export interface SolerciaConnectSettings {
  account: string;
  target: SolerciaConnectTarget;
  allow_browser_fallback: boolean;
}

/** Payload de `POST /connectors/solercia-connect`. */
export interface SolerciaConnectRegisterPayload {
  account: string;
  target: SolerciaConnectTarget;
  allow_browser_fallback: boolean;
}

/** Lo que dijo el documento de salud del runtime de Connect. */
export interface SolerciaConnectRuntime {
  reachable: boolean | null;
  version?: string | null;
  interactive_login?: boolean | null;
}

export interface SolerciaConnectRegisterResult {
  connector: Connector;
  account: ConnectedAccount;
  settings: SolerciaConnectSettings;
  runtime: SolerciaConnectRuntime;
}

export interface SolerciaConnectStatus {
  state: SolerciaConnectState;
  route: string | null;
  account: string | null;
  checked_at: string;
  detail: string | null;
  remediation: string[];
  runtime: SolerciaConnectRuntime;
}

/** Respuesta 202 de `POST .../solercia-connect/connect`. */
export interface SolerciaConnectSessionStart {
  session_id: string;
  started: boolean;
  expires_in_seconds: number | null;
}

export interface SolerciaConnectSession {
  state: SolerciaConnectSessionState;
  route: string | null;
  error_code: string | null;
  detail: string | null;
  remediation: string[];
  started_at: string | null;
  finished_at: string | null;
}

export interface SolerciaConnectSyncError {
  run_id: string | null;
  code: string;
  detail: string;
}

export interface SolerciaConnectSyncResult {
  run_id: string | null;
  runs: unknown[];
  status: 'completed' | 'partial' | 'error' | 'skipped';
  items_fetched: number;
  items_new: number;
  items_duplicated: number;
  items_converted: number;
  tasks_created: number;
  errors: SolerciaConnectSyncError[];
}

/**
 * Lee la configuración de Solercia Connect que el backend guarda dentro de
 * `Connector.settings`; `null` si el conector no la tiene o está incompleta.
 */
export function solerciaConnectSettingsOf(
  connector: Connector,
): SolerciaConnectSettings | null {
  const raw = connector.settings?.['solercia_connect'];
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const stored = raw as Record<string, unknown>;
  const account = stored['account'];
  const target = stored['target'];
  if (typeof account !== 'string' || typeof target !== 'string') {
    return null;
  }
  if (!SOLERCIA_CONNECT_TARGETS.includes(target as SolerciaConnectTarget)) {
    return null;
  }
  const flag = stored['allow_browser_fallback'];
  return {
    account,
    target: target as SolerciaConnectTarget,
    allow_browser_fallback:
      typeof flag === 'boolean' ? flag : String(flag ?? 'true').toLowerCase() === 'true',
  };
}

/**
 * Catálogo de proveedores que la página de Conexiones ofrece CREAR: etiqueta
 * amigable, credential_kind que fija el backend y el ícono del registry
 * `@solercia/ui` con el que se pinta. Hoy una sola opción: Solercia Connect.
 */
export interface ProviderMeta {
  provider: ConnectorProvider;
  label: string;
  credentialKind: CredentialKind;
  icon: string;
}

export const PROVIDER_CATALOG: readonly ProviderMeta[] = [
  {
    provider: 'solercia_connect',
    label: 'Solercia Connect · Microsoft 365',
    credentialKind: 'api_token',
    icon: 'plug',
  },
] as const;

/**
 * Etiquetas e íconos de TODOS los proveedores conocidos, incluidos los que ya
 * no se pueden crear desde la UI pero siguen existiendo en la base de datos
 * (p. ej. `jira`, `google`): sus tarjetas deben seguir pintándose con nombre
 * propio.
 */
const PROVIDER_PRESENTATION: Readonly<
  Record<ConnectorProvider, { label: string; icon: string }>
> = {
  solercia_connect: { label: 'Solercia Connect · Microsoft 365', icon: 'plug' },
  microsoft365: { label: 'Microsoft 365', icon: 'envelope' },
  google: { label: 'Google', icon: 'envelope' },
  jira: { label: 'Jira', icon: 'clipboard' },
  glpi: { label: 'GLPI', icon: 'cpu-chip' },
  gitlab: { label: 'GitLab', icon: 'git-branch' },
  mcp: { label: 'MCP', icon: 'bolt' },
  fake: { label: 'Demo (fake)', icon: 'beaker' },
};

function presentationOf(
  provider: string,
): { label: string; icon: string } | undefined {
  return Object.prototype.hasOwnProperty.call(PROVIDER_PRESENTATION, provider)
    ? PROVIDER_PRESENTATION[provider as ConnectorProvider]
    : undefined;
}

/** Etiqueta amigable de un proveedor (el provider crudo como respaldo). */
export function providerLabel(provider: string): string {
  return presentationOf(provider)?.label ?? provider;
}

/** Ícono del registry para un proveedor (genérico como respaldo). */
export function providerIcon(provider: string): string {
  return presentationOf(provider)?.icon ?? 'squares-2x2';
}
