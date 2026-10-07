/** Contrato de `/sync/*` (C02/C05): una corrida por organización con tres pasos aislados. */

export type SyncRunStatus = 'success' | 'partial' | 'failed';
export type SyncStepStatus = 'ok' | 'error' | 'skipped';
export type SyncTrigger = 'scheduled' | 'manual';

export interface SyncStep {
  name: 'checklist' | 'intake' | 'classification' | string;
  status: SyncStepStatus | string;
  counts: Record<string, unknown>;
  detail: string | null;
  error: { type?: string; detail?: string } | null;
}

export interface SyncRun {
  organization_id: string;
  trigger: SyncTrigger | string;
  status: SyncRunStatus | string;
  started_at: string;
  finished_at: string;
  actor_id: string | null;
  steps: SyncStep[];
}

export interface SyncRunPage {
  data: SyncRun[];
  meta: { page: number; size: number; total: number };
}

/**
 * Horario de la corrida programada. El API no lo expone: son los valores por defecto de
 * `SCHEDULED_SYNC_TIMES` y `SCHEDULED_SYNC_TZ` (`backend/app/config.py`). Bogotá no tiene horario
 * de verano, así que el desfase UTC−5 es fijo.
 */
export const SYNC_SCHEDULE = {
  times: ['06:00', '23:59'],
  timeZone: 'America/Bogota',
  utcOffsetHours: -5,
} as const;

/** Próximas `count` ejecuciones a partir de `now`, en orden. */
export function nextSyncRuns(now: Date, count = 2): Date[] {
  const offsetMs = SYNC_SCHEDULE.utcOffsetHours * 3_600_000;
  const local = new Date(now.getTime() + offsetMs);
  const result: Date[] = [];
  for (let day = 0; result.length < count && day < 3; day++) {
    for (const time of SYNC_SCHEDULE.times) {
      const [hour, minute] = time.split(':').map(Number);
      const utc =
        Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate() + day, hour, minute) -
        offsetMs;
      if (utc > now.getTime() && result.length < count) {
        result.push(new Date(utc));
      }
    }
  }
  return result;
}
