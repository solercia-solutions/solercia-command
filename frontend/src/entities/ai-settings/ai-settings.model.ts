/** Contrato de `/ai/*` (C04). Ninguna respuesta trae la llave: solo `has_api_key` y sus 4 últimos. */

export type AiLocality = 'local' | 'external';
export type AiReasoningEffort = 'none' | 'low' | 'medium' | 'high';
export type AiSettingsSource = 'organization' | 'global' | 'default';

export interface AiSettings {
  preset: string;
  preset_label: string;
  locality: AiLocality;
  base_url: string;
  chat_model: string;
  embedding_model: string | null;
  has_api_key: boolean;
  api_key_last4: string | null;
  timeout_seconds: number;
  max_tokens: number;
  temperature: number;
  reasoning_effort: AiReasoningEffort | null;
  num_ctx: number | null;
  enabled: boolean;
  source: AiSettingsSource;
  updated_at: string | null;
  updated_by: string | null;
}

export interface AiPreset {
  key: string;
  label: string;
  locality: AiLocality;
  base_url: string | null;
  base_url_editable: boolean;
  chat_model: string;
  embedding_model: string | null;
  requires_api_key: boolean;
}

/**
 * Cuerpo de `PUT /ai/settings` y de `POST /ai/settings/test`. `api_key`: vacío o ausente conserva
 * la llave guardada (solo si la URL destino no cambia); `null` la borra.
 */
export interface AiSettingsUpdate {
  preset: string;
  base_url: string | null;
  chat_model: string | null;
  embedding_model: string | null;
  api_key?: string | null;
  timeout_seconds: number;
  max_tokens: number;
  temperature: number;
  reasoning_effort: AiReasoningEffort | null;
  num_ctx: number | null;
  enabled: boolean;
}

export interface AiConnectionTestResult {
  ok: boolean;
  preset: string;
  locality: AiLocality;
  chat_model: string;
  chat_latency_ms: number | null;
  embedding_model: string | null;
  embedding_latency_ms: number | null;
  embedding_dimensions: number | null;
  error: { stage: 'chat' | 'embeddings'; code: string; detail: string } | null;
}
