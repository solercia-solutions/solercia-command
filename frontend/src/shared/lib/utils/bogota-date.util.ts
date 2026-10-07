/**
 * Fechas en hora de Bogotá (la zona de la sincronización programada y del checklist), con el
 * formato corto de la app. Una fecha inválida devuelve cadena vacía en vez de «Invalid Date».
 */
const ZONE = 'America/Bogota';

export function formatBogotaDateTime(value: string | Date | null | undefined): string {
  const date = toDate(value);
  if (!date) {
    return '';
  }
  return date.toLocaleString('es-CO', {
    timeZone: ZONE,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatBogotaDate(value: string | Date | null | undefined): string {
  const date = toDate(value);
  if (!date) {
    return '';
  }
  return date.toLocaleDateString('es-CO', {
    timeZone: ZONE,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

/** Fecha ISO sin hora (`2026-10-20`) mostrada tal cual el día, sin corrimiento por zona. */
export function formatIsoDay(value: string | null | undefined): string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value ?? '';
  }
  const [year, month, day] = value.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12)).toLocaleDateString('es-CO', {
    timeZone: 'UTC',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

/** Clave de día en Bogotá (`2026-10-07`) para decir «hoy» o «mañana». */
export function bogotaDayKey(value: Date): string {
  return value.toLocaleDateString('en-CA', { timeZone: ZONE });
}

export function formatBogotaTime(value: Date): string {
  return value.toLocaleTimeString('es-CO', {
    timeZone: ZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}
