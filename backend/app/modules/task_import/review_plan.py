"""Source-bound domain review, never an authorization or import token.

The application supplies the authoritative internal preview, its parser/profile
version and authenticated context separately from user decisions. Never accept a
client-deserialized preview as authoritative. Hash/coordinates are provenance,
not business identity. No storage, defaults, inference or writes occur here.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from typing import Literal

from .contracts import ChecklistPreview, ChecklistRow, PreviewCounts, SourceSnapshot
from .review_ports import ReviewFacts


@dataclass(frozen=True)
class TrustedContext:
    tenant_id: str
    actor_id: str


@dataclass(frozen=True)
class RowKey:
    source_hash: str
    sheet: str | None
    row: int


@dataclass(frozen=True)
class DateCorrection:
    field: str
    value: str | None  # None is explicit no-date; empty corrections mean absent.


@dataclass(frozen=True)
class ReviewDecision:
    key: RowKey
    action: Literal['include', 'exclude']
    project_id: str | None = None
    assignee_id: str | None = None
    reason: str | None = field(default=None, repr=False)
    corrections: tuple[DateCorrection, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, 'corrections', tuple(self.corrections))


@dataclass(frozen=True)
class ReviewInput:
    source_hash: str
    profile_version: str
    decisions: tuple[ReviewDecision, ...]

    def __post_init__(self):
        object.__setattr__(self, 'decisions', tuple(self.decisions))


@dataclass(frozen=True)
class ReviewedRow:
    key: RowKey
    original: ChecklistRow = field(repr=False)
    action: str
    project_id: str | None
    assignee_id: str | None
    effective_due_date: date | None
    effective_status: str | None
    reason: str | None = field(repr=False)
    corrections: tuple[DateCorrection, ...] = field(repr=False)
    issues: tuple[str, ...]


@dataclass(frozen=True)
class ReviewedPlan:
    source: SourceSnapshot = field(repr=False)
    source_hash: str
    profile_version: str
    context: TrustedContext
    counts: PreviewCounts | None
    rows: tuple[ReviewedRow, ...]
    issues: tuple[str, ...]
    status: Literal['blocked', 'validated_for_review']


def build_review_plan(
    preview: ChecklistPreview,
    profile_version: str,
    request: ReviewInput,
    context: TrustedContext,
    facts: ReviewFacts,
) -> ReviewedPlan:
    """Account for every source row, preserving blocking failures without omission.

    Date corrections can clear only invalid_date issues. All other parser errors
    remain blocking for included rows; explicit exclusions preserve originals.
    Facts failures propagate, never become successful validation.
    """
    issues = []
    if not context.tenant_id or not context.actor_id:
        issues.append('missing_trusted_context')
    if (sha256(preview.source.data).hexdigest() != preview.sha256
            or request.source_hash != preview.sha256):
        issues.append('source_hash_mismatch')
    if not profile_version or request.profile_version != profile_version:
        issues.append('profile_version_mismatch')
    if not preview.complete:
        issues.append('incomplete_preview')
    # The parser also aggregates row issues at preview level. Consume those
    # occurrences here; their resolution belongs exclusively to each row below.
    row_issues = Counter(issue for row in preview.rows for issue in row.issues)
    source_issues = Counter(preview.issues) - row_issues
    if any(issue.severity == 'error' for issue in source_issues):
        issues.append('source_error')
    counts = Counter(row.disposition for row in preview.rows)
    if (preview.counts != PreviewCounts(counts['candidate'], counts['blank_skipped'], counts['rejected'])
            or set(counts) - {'candidate', 'blank_skipped', 'rejected'}):
        issues.append('row_accounting_mismatch')
    keys = [RowKey(preview.sha256, row.sheet, row.number) for row in preview.rows]
    if len(set(keys)) != len(keys):
        issues.append('duplicate_source_coordinate')
    required = {key for key, row in zip(keys, preview.rows) if row.disposition != 'blank_skipped'}
    decisions: dict[RowKey, list[ReviewDecision]] = {}
    for decision in request.decisions:
        decisions.setdefault(decision.key, []).append(decision)
        if decision.key not in required:
            issues.append('unknown_row_decision')
    if any(len(group) != 1 for group in decisions.values()):
        issues.append('duplicate_row_decision')
    status_columns = [i for i, cell in enumerate(preview.headers) if cell.value == 'Estado']
    reviewed = []
    for key, row in zip(keys, preview.rows):
        errors = []
        group = decisions.get(key, [])
        decision = group[0] if len(group) == 1 else None
        due_date = row.due_date
        status = None
        if len(status_columns) == 1 and status_columns[0] < len(row.cells):
            value = row.cells[status_columns[0]].value
            status = value if isinstance(value, str) else None
        action = 'blank_skipped' if row.disposition == 'blank_skipped' else 'unresolved'
        if action != 'blank_skipped':
            if decision is None:
                errors.append('missing_or_duplicate_decision')
            else:
                action = decision.action
                if action == 'exclude':
                    if not isinstance(decision.reason, str) or not decision.reason.strip():
                        errors.append('exclusion_reason_required')
                    if decision.corrections or decision.project_id or decision.assignee_id:
                        errors.append('conflicting_exclusion')
                elif action == 'include':
                    corrected = False
                    if decision.corrections:
                        correction = decision.corrections[0]
                        if len(decision.corrections) != 1 or correction.field != 'due_date':
                            errors.append('unsupported_correction')
                        else:
                            try:
                                value = correction.value
                                if value is None:
                                    due_date = None
                                elif (isinstance(value, str) and len(value) == 10
                                      and date.fromisoformat(value).isoformat() == value):
                                    due_date = date.fromisoformat(value)
                                else:
                                    raise ValueError
                                corrected = True
                            except (ValueError, TypeError):
                                errors.append('invalid_date_correction')
                    errors.extend(issue.code for issue in row.issues if issue.severity == 'error'
                                  and not (issue.code == 'invalid_date' and corrected))
                    if row.disposition == 'rejected' and not any(i.severity == 'error' for i in row.issues):
                        errors.append('unexplained_rejection')
                    project = (facts.active_project(context.tenant_id, decision.project_id)
                               if decision.project_id else None)
                    if (project is None or project.tenant_id != context.tenant_id
                            or project.project_id != decision.project_id):
                        errors.append('invalid_project')
                    elif status is None or status not in project.supported_statuses:
                        errors.append('incompatible_status')
                    if (not decision.assignee_id
                            or not facts.active_member(context.tenant_id, decision.assignee_id)):
                        errors.append('invalid_assignee')
                else:
                    errors.append('invalid_action')
        reviewed.append(ReviewedRow(
            key, row, action, decision.project_id if decision else None,
            decision.assignee_id if decision else None, due_date, status,
            decision.reason if decision else None, decision.corrections if decision else (), tuple(errors),
        ))
    blocked = bool(issues or any(row.issues for row in reviewed))
    return ReviewedPlan(preview.source, preview.sha256, profile_version, context, preview.counts,
                        tuple(reviewed), tuple(issues), 'blocked' if blocked else 'validated_for_review')
