/** Proveedores de integración registrados en el backend. */
export type ConnectorProvider =
  | 'microsoft365'
  | 'google'
  | 'jira'
  | 'glpi'
  | 'mcp'
  | 'fake';

/** Cómo obtiene credenciales el conector (fijo al crearlo). */
export type CredentialKind = 'oauth' | 'api_token' | 'none';

export type ConnectorStatus = 'active' | 'inactive' | 'error';

export type AccountStatus = 'active' | 'revoked' | 'error';

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

/**
 * Catálogo de proveedores que la página de Conexiones ofrece: etiqueta
 * amigable, credential_kind que fija el backend y el ícono del registry
 * `@solercia/ui` con el que se pinta.
 */
export interface ProviderMeta {
  provider: ConnectorProvider;
  label: string;
  credentialKind: CredentialKind;
  icon: string;
}

export const PROVIDER_CATALOG: readonly ProviderMeta[] = [
  { provider: 'microsoft365', label: 'Microsoft 365', credentialKind: 'oauth', icon: 'envelope' },
  { provider: 'google', label: 'Google', credentialKind: 'oauth', icon: 'envelope' },
  { provider: 'jira', label: 'Jira', credentialKind: 'api_token', icon: 'clipboard' },
  { provider: 'glpi', label: 'GLPI', credentialKind: 'api_token', icon: 'cpu-chip' },
  { provider: 'mcp', label: 'MCP', credentialKind: 'api_token', icon: 'bolt' },
  { provider: 'fake', label: 'Demo (fake)', credentialKind: 'oauth', icon: 'beaker' },
] as const;

/** Etiqueta amigable de un proveedor (el provider crudo como respaldo). */
export function providerLabel(provider: string): string {
  return (
    PROVIDER_CATALOG.find((p) => p.provider === provider)?.label ?? provider
  );
}

/** Ícono del registry para un proveedor (genérico como respaldo). */
export function providerIcon(provider: string): string {
  return (
    PROVIDER_CATALOG.find((p) => p.provider === provider)?.icon ??
    'squares-2x2'
  );
}
