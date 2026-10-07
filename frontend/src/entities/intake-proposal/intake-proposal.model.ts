/** Contrato de `/intake/proposals` (C05): una propuesta del clasificador por hilo de correo. */

export type ProposalStatus = 'propuesta' | 'aceptada' | 'descartada';
export type ThreadState = 'pendiente_respuesta' | 'respondido' | 'solo_saliente';
export type ProposalRelation = 'tarea_existente' | 'tarea_nueva' | 'irrelevante';

export const THREAD_STATES: readonly ThreadState[] = [
  'pendiente_respuesta',
  'respondido',
  'solo_saliente',
];

/** Salida del modelo ya saneada por el backend (`prompt.py`). Todo es opcional. */
export interface ProposalResult {
  relacion?: ProposalRelation;
  task_ref?: string | null;
  confianza?: number;
  atendida?: 'si' | 'no' | 'parcial';
  accion?: string | null;
  solicitante?: string | null;
  fecha_limite?: string | null;
  resumen?: string | null;
  motivo?: string | null;
  degradada?: boolean;
}

export interface ProposalCandidate {
  task_id: string;
  ref: string;
  title: string;
  score: number;
  via: 'clave' | 'similitud';
}

export interface IntakeProposal {
  id: string;
  conversation_key: string;
  conversation_id: string | null;
  subject: string;
  item_ids: string[];
  message_count: number;
  last_message_at: string;
  thread_state: ThreadState;
  relation: ProposalRelation | null;
  task_id: string | null;
  confidence: number | null;
  result: ProposalResult | null;
  candidates: ProposalCandidate[];
  provider: string | null;
  model: string | null;
  prompt_version: string | null;
  classification_error: string | null;
  status: ProposalStatus;
  created_task_id: string | null;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProposalQuery {
  status?: ProposalStatus | null;
  thread_state?: ThreadState | null;
  task_id?: string | null;
  page?: number;
  size?: number;
}

export interface ProposalPage {
  data: IntakeProposal[];
  meta: { page: number; size: number; total: number };
}

export type ConfidenceLevel = 'alta' | 'media' | 'baja';

/** Umbrales de la etiqueta de confianza (decisión de C06; el backend degrada a ≤ 0,3). */
export function confidenceLevel(value: number | null | undefined): ConfidenceLevel | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (value >= 0.75) {
    return 'alta';
  }
  return value >= 0.5 ? 'media' : 'baja';
}
