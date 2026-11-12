/**
 * Jira-style original-estimate parsing and formatting.
 *
 * Convention (Jira defaults):
 *   1w = 5 working days = 40 hours
 *   1d = 8 hours
 *   1h = 1 hour
 *
 * Input format: one or more tokens separated by whitespace, each token being
 * a number followed by a unit (`w`, `d` or `h`, case-insensitive). Tokens are
 * additive and may repeat.
 *
 * Examples (documented convention — no spec runner is configured in this
 * repo, so these serve as the executable contract):
 *   parseOriginalEstimate('4w')       -> 160   (4 * 40)
 *   parseOriginalEstimate('2d')       -> 16    (2 * 8)
 *   parseOriginalEstimate('3h')       -> 3
 *   parseOriginalEstimate('1w 2d 4h') -> 60    (40 + 16 + 4)
 *   parseOriginalEstimate('2.5h')     -> 2.5
 *   parseOriginalEstimate('')         -> null  (empty: no estimate)
 *   parseOriginalEstimate('abc')      -> null  (invalid: show an error)
 *   parseOriginalEstimate('4')        -> null  (missing unit: invalid)
 *
 *   formatOriginalEstimate(160)  -> '4w'
 *   formatOriginalEstimate(60)   -> '1w 2d 4h'
 *   formatOriginalEstimate(2.5)  -> '2.5h'
 *   formatOriginalEstimate(0)    -> '0h'
 *   formatOriginalEstimate(null) -> ''
 */

const HOURS_PER_DAY = 8;
const DAYS_PER_WEEK = 5;
const HOURS_PER_WEEK = HOURS_PER_DAY * DAYS_PER_WEEK;

const HOURS_PER_UNIT: Record<string, number> = {
  w: HOURS_PER_WEEK,
  d: HOURS_PER_DAY,
  h: 1,
};

/** One estimate token: a positive number (int or decimal) plus w/d/h unit. */
const TOKEN_RE = /^(\d+(?:[.,]\d+)?)([wdh])$/i;

/**
 * Parses a Jira-style estimate string ("4w", "2d", "3h", "1w 2d 4h") into
 * decimal hours. Returns `null` for an empty input (no estimate) and also
 * for an invalid one — the caller distinguishes both cases by checking
 * whether the trimmed input was empty (empty = clear, non-empty = error).
 */
export function parseOriginalEstimate(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === '') {
    return null;
  }
  let hours = 0;
  for (const token of trimmed.split(/\s+/)) {
    const match = TOKEN_RE.exec(token);
    if (!match) {
      return null;
    }
    const amount = Number(match[1].replace(',', '.'));
    if (!Number.isFinite(amount)) {
      return null;
    }
    hours += amount * HOURS_PER_UNIT[match[2].toLowerCase()];
  }
  return hours;
}

/**
 * Formats decimal hours back into the Jira-style string ("1w 2d 4h").
 * Whole weeks and days are extracted greedily; the remaining hours keep up
 * to two decimals (e.g. 2.5h). Returns '' when there is no estimate.
 */
export function formatOriginalEstimate(
  hours: number | null | undefined,
): string {
  if (hours == null || !Number.isFinite(hours) || hours < 0) {
    return '';
  }
  if (hours === 0) {
    return '0h';
  }
  const parts: string[] = [];
  let remaining = hours;

  const weeks = Math.floor(remaining / HOURS_PER_WEEK);
  if (weeks > 0) {
    parts.push(`${weeks}w`);
    remaining -= weeks * HOURS_PER_WEEK;
  }
  const days = Math.floor(remaining / HOURS_PER_DAY);
  if (days > 0) {
    parts.push(`${days}d`);
    remaining -= days * HOURS_PER_DAY;
  }
  if (remaining > 0) {
    // Round to two decimals to absorb floating-point noise (e.g. 0.30000004).
    const rounded = Math.round(remaining * 100) / 100;
    if (rounded > 0) {
      parts.push(`${rounded}h`);
    }
  }
  return parts.join(' ');
}
