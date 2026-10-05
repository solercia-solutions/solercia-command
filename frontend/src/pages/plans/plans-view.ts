import type {
  ActivityTask,
  ApiDecimal,
  Plan,
  PlanActivity,
  ReportPeriod,
} from '@entities/plan/plan.model';

/**
 * Pure view helpers of the «Planes» page (45c). No Angular, no I/O: every
 * function is deterministic so the state logic stays out of the template.
 *
 * Progress rule inherited from 45a (D3/D-F): `null` means "no evidence" and is
 * NEVER rendered or averaged as 0.
 */

/** Selectable periods, in display order. */
export const PERIODS: readonly ReportPeriod[] = ['I', 'II', 'III', 'ANUAL'];

/** Plan types in display order (`vocabularies.PLAN_TYPES`). */
export const PLAN_TYPE_ORDER: readonly string[] = ['pspi', 'ptr', 'pai', 'ptep'];

/**
 * Current four-month period ("cuatrimestre") of `date`: I = ene–abr,
 * II = may–ago, III = sep–dic. Smart default of the period selector.
 */
export function currentPeriod(date: Date): ReportPeriod {
  const month = date.getMonth(); // 0-based
  if (month <= 3) {
    return 'I';
  }
  if (month <= 7) {
    return 'II';
  }
  return 'III';
}

/** Reads a backend decimal (string or number) as a number; null-safe. */
export function toNumber(value: ApiDecimal | null | undefined): number | null {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Calculated progress (ratio 0..1) as a rounded percent, or null. */
export function calculatedPercent(activity: PlanActivity): number | null {
  const ratio = activity.calculated_progress;
  return ratio === null || ratio === undefined ? null : Math.round(ratio * 100);
}

/** Reported progress (already 0..100) as a rounded percent, or null. */
export function reportedPercent(activity: PlanActivity): number | null {
  const value = toNumber(activity.reported_progress);
  return value === null ? null : Math.round(value);
}

/** Per-plan roll-up shown on the card. Averages skip nulls, never count them as 0. */
export interface PlanSummary {
  activityCount: number;
  withTasks: number;
  calculatedAverage: number | null;
  withReport: number;
  reportedAverage: number | null;
  /** Activities with at least one linked task (primary or contributes). */
  linkedActivities: number;
  /** Task links of the plan (one task linked to two activities counts twice). */
  taskLinks: number;
}

function average(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

export function summarizePlan(activities: PlanActivity[]): PlanSummary {
  const calculated = activities
    .map(calculatedPercent)
    .filter((value): value is number => value !== null);
  const reported = activities
    .map(reportedPercent)
    .filter((value): value is number => value !== null);
  return {
    activityCount: activities.length,
    withTasks: calculated.length,
    calculatedAverage: average(calculated),
    withReport: reported.length,
    reportedAverage: average(reported),
    linkedActivities: activities.filter((activity) => linkedTaskCount(activity) > 0).length,
    taskLinks: activities.reduce((sum, activity) => sum + linkedTaskCount(activity), 0),
  };
}

/** Tasks linked to an activity, whatever their role. */
export function linkedTaskCount(activity: PlanActivity): number {
  return (activity.primary_task_count ?? 0) + (activity.contributing_task_count ?? 0);
}

/** Activities of one group inside a plan, in API order. */
export interface ActivityGroup {
  key: string;
  code: string | null;
  name: string | null;
  activities: PlanActivity[];
}

/** Groups by `(group_code, group_name)`, preserving first-appearance order. */
export function groupActivities(activities: PlanActivity[]): ActivityGroup[] {
  const groups = new Map<string, ActivityGroup>();
  for (const activity of activities) {
    const key = `${activity.group_code ?? ''}\u0000${activity.group_name ?? ''}`;
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        code: activity.group_code,
        name: activity.group_name,
        activities: [],
      };
      groups.set(key, group);
    }
    group.activities.push(activity);
  }
  return [...groups.values()];
}

/** Lowercase, accent-insensitive form for client-side search. */
export function normalize(text: string | null | undefined): string {
  return (text ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim();
}

/** Correlation filter: every activity, with tasks, without tasks or with conflicts. */
export type LinkFilter = 'all' | 'linked' | 'unlinked' | 'conflict';

export const LINK_FILTERS: readonly LinkFilter[] = ['all', 'linked', 'unlinked', 'conflict'];

export interface ActivityFilterState {
  onlyMine: boolean;
  query: string;
  link?: LinkFilter;
  /** activity id → number of `conflict` links. */
  conflicts?: Map<string, number>;
  /** activity id → searchable codes of its linked tasks (key, T-NN). */
  taskCodes?: Map<string, string[]>;
}

/**
 * «Solo mías», correlation with tasks, and search by key, code, name,
 * responsible or the code of a linked task («T-07», «SGSI-12»).
 */
export function filterActivities(
  activities: PlanActivity[],
  filter: ActivityFilterState,
): PlanActivity[] {
  const needle = normalize(filter.query);
  const link = filter.link ?? 'all';
  return activities.filter((activity) => {
    if (filter.onlyMine && !activity.is_mine) {
      return false;
    }
    if (link === 'linked' && linkedTaskCount(activity) === 0) {
      return false;
    }
    if (link === 'unlinked' && linkedTaskCount(activity) > 0) {
      return false;
    }
    if (link === 'conflict' && !(filter.conflicts?.get(activity.id) ?? 0)) {
      return false;
    }
    if (!needle) {
      return true;
    }
    return [
      activity.activity_key,
      activity.code,
      activity.name,
      activity.responsible,
      ...(filter.taskCodes?.get(activity.id) ?? []),
    ].some((field) => normalize(field).includes(needle));
  });
}

// --- Vigencia (plan year) -------------------------------------------------

/** Distinct `period_year` of the plans, newest first. */
export function planYears(plans: Plan[]): number[] {
  return [...new Set(plans.map((plan) => plan.period_year))].sort((a, b) => b - a);
}

/** Smart default: the current year when it has plans, else the newest one. */
export function defaultPlanYear(years: number[], today: Date): number | null {
  const current = today.getFullYear();
  return years.includes(current) ? current : (years[0] ?? null);
}

// --- Linked tasks (correlation) --------------------------------------------

/**
 * Business code the entity knows for an imported task: the checklist ID
 * («CHECKLIST_TAREAS:T-07» → «T-07») or the Jira key when it differs from the
 * Command key. `null` for native tasks.
 */
export function externalCode(task: Pick<ActivityTask, 'source' | 'external_key' | 'task_key'>): string | null {
  const raw = task.external_key?.trim();
  if (!raw) {
    return null;
  }
  const code = raw.includes(':') ? raw.slice(raw.lastIndexOf(':') + 1).trim() : raw;
  return code && code !== task.task_key ? code : null;
}

export type StatusTone = 'success' | 'info' | 'neutral' | 'danger';

const DONE_WORDS = ['completad', 'done', 'listo', 'finalizad', 'cerrad', 'terminad', 'hecho'];
const NOT_STARTED_WORDS = ['sin iniciar', 'to do', 'to_do', 'por hacer', 'pendiente', 'backlog', 'abierta'];
const DISCARDED_WORDS = ['cancel', 'removid', 'descartad', 'anulad'];

/**
 * Display tone of a task status. Board columns carry no category yet (S05),
 * so the tone is read from the status name; it only colors the badge, it
 * never feeds the calculated progress (that one comes from the backend).
 */
export function statusTone(status: string | null | undefined): StatusTone {
  const value = normalize(status);
  if (DISCARDED_WORDS.some((word) => value.includes(word))) {
    return 'danger';
  }
  if (DONE_WORDS.some((word) => value.includes(word))) {
    return 'success';
  }
  if (NOT_STARTED_WORDS.some((word) => value.includes(word))) {
    return 'neutral';
  }
  return 'info';
}

export interface StatusCount {
  /** Status as the first task shows it («Completada»). */
  status: string;
  count: number;
  tone: StatusTone;
}

const TONE_ORDER: Record<StatusTone, number> = { info: 0, neutral: 1, success: 2, danger: 3 };

/**
 * Aggregated state of the linked tasks: one entry per status (case- and
 * accent-insensitive, «COMPLETADA» = «Completada»), in progress first.
 */
export function summarizeTaskStatuses(tasks: Pick<ActivityTask, 'status'>[]): StatusCount[] {
  const byStatus = new Map<string, StatusCount>();
  for (const task of tasks) {
    const key = normalize(task.status);
    const entry = byStatus.get(key);
    if (entry) {
      entry.count += 1;
    } else {
      byStatus.set(key, { status: task.status, count: 1, tone: statusTone(task.status) });
    }
  }
  return [...byStatus.values()].sort(
    (a, b) => TONE_ORDER[a.tone] - TONE_ORDER[b.tone] || b.count - a.count,
  );
}

/** Plan types present in the loaded plans, in canonical order. */
export function presentPlanTypes(plans: Plan[]): string[] {
  const present = new Set(plans.map((plan) => plan.plan_type));
  const ordered = PLAN_TYPE_ORDER.filter((type) => present.has(type));
  const extra = [...present].filter((type) => !PLAN_TYPE_ORDER.includes(type)).sort();
  return [...ordered, ...extra];
}

/** Activities indexed by plan id (one pass). */
export function activitiesByPlan(activities: PlanActivity[]): Map<string, PlanActivity[]> {
  const byPlan = new Map<string, PlanActivity[]>();
  for (const activity of activities) {
    const list = byPlan.get(activity.plan_id);
    if (list) {
      list.push(activity);
    } else {
      byPlan.set(activity.plan_id, [activity]);
    }
  }
  return byPlan;
}

// --- Reporting and linking (task N3) ---------------------------------------

/**
 * Period whose value is shown as reference while reporting: I has none,
 * II → I, III → II, ANUAL → III (the last four-month period of the year).
 */
export function previousPeriod(period: ReportPeriod): ReportPeriod | null {
  switch (period) {
    case 'II':
      return 'I';
    case 'III':
      return 'II';
    case 'ANUAL':
      return 'III';
    default:
      return null;
  }
}

/** Reported progress typed by the user: valid only in [0, 100]. */
export type ProgressCheck = 'ok' | 'empty' | 'invalid' | 'outOfRange';

export function checkProgress(raw: string): ProgressCheck {
  const text = raw.trim().replace(',', '.');
  if (text === '') {
    return 'empty';
  }
  const value = Number(text);
  if (!Number.isFinite(value)) {
    return 'invalid';
  }
  return value < 0 || value > 100 ? 'outOfRange' : 'ok';
}

/** Parsed reported progress, rounded to 2 decimals (`Numeric(5,2)`), or null. */
export function parseProgress(raw: string): number | null {
  if (checkProgress(raw) !== 'ok') {
    return null;
  }
  return Math.round(Number(raw.trim().replace(',', '.')) * 100) / 100;
}

/** One evidence reference per line; blanks dropped; `null` when none. */
export function parseEvidence(raw: string): string[] | null {
  const refs = raw
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  return refs.length > 0 ? refs : null;
}

/** Tri-state (`Sí` / `No` / `Sin dato`) of the report's boolean fields. */
export type TriState = 'yes' | 'no' | 'unknown';

export function toTriState(value: boolean | null | undefined): TriState {
  if (value === true) {
    return 'yes';
  }
  return value === false ? 'no' : 'unknown';
}

export function fromTriState(value: TriState): boolean | null {
  return value === 'unknown' ? null : value === 'yes';
}

/**
 * Smart default of the link role: the first task of an activity without
 * `primary` tasks is its `primary` (it is what makes the calculated progress
 * exist); later ones `contributes`.
 */
export function defaultLinkRole(primaryTaskCount: number): 'primary' | 'contributes' {
  return primaryTaskCount === 0 ? 'primary' : 'contributes';
}

/** `{activity_id: n}` from the conflict-count rows. */
export function conflictIndex(
  rows: { activity_id: string; conflict_count: number }[],
): Map<string, number> {
  return new Map(rows.map((row) => [row.activity_id, row.conflict_count]));
}
