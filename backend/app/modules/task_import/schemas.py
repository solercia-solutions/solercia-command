"""Public preview projection, deliberately separate from internal source DTOs."""
from datetime import date
from typing import Annotated, Literal, Protocol, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .contracts import CellValue, ChecklistPreview, Issue, IssueCode, ParseLimits
from .review_plan import DateCorrection, ReviewDecision, ReviewInput, ReviewedPlan, RowKey

# Stable binding for the exact current ChecklistProfile/parser semantics. A future
# incompatible profile must change this version; it is not an authorization token.
PROFILE_VERSION = 'checklist-v1'
MAX_DECISIONS = ParseLimits().max_rows - 1
MAX_ENCODED_SOURCE = 4 * ((ParseLimits().max_input_bytes + 2) // 3)


HeaderName = Literal[
    'ID', 'Estado', 'Vencido', 'Urgencia', 'Categoría', 'Tarea', 'Detalle',
    'Fecha Límite', 'Solicitante', 'Apoyo IA', 'Observaciones',
]
_ALLOWED_HEADERS = frozenset(get_args(HeaderName))


class PublicModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class OptionsQuery(PublicModel):
    projects_page: int = Field(default=1, ge=1, le=1000)
    projects_size: int = Field(default=20, ge=1, le=100)
    projects_q: str = Field(default='', max_length=100)
    members_page: int = Field(default=1, ge=1, le=1000)
    members_size: int = Field(default=20, ge=1, le=100)
    members_q: str = Field(default='', max_length=100)

    @field_validator('projects_q', 'members_q', mode='before')
    @classmethod
    def trim_search(cls, value: str) -> str:
        value = value.strip()
        if value and len(value) < 2:
            raise ValueError('La búsqueda debe tener al menos dos caracteres.')
        return value


class OptionItem(PublicModel):
    id: str
    label: str


class OptionMeta(PublicModel):
    page: int = Field(ge=1, le=1000)
    size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class OptionPage(PublicModel):
    items: list[OptionItem]
    meta: OptionMeta


class OptionsData(PublicModel):
    projects: OptionPage
    members: OptionPage
    default_project: OptionItem | None


class OptionsResponse(PublicModel):
    data: OptionsData
    message: str = 'Opciones disponibles sin guardar tareas.'


class OptionsReader(Protocol):
    async def load(self, tenant_id: str, query: OptionsQuery) -> OptionsData | None:
        """Read bounded labels; None means the organization is not eligible."""
        ...


class PreviewIssue(PublicModel):
    code: IssueCode
    severity: Literal['error', 'warning', 'info']
    row: int | None = None
    column: int | None = None


class PreviewField(PublicModel):
    name: HeaderName
    value: CellValue


class PublicRowKey(PublicModel):
    source_hash: str = Field(min_length=64, max_length=64, pattern=r'^[0-9a-f]{64}$')
    sheet: str | None = Field(max_length=128)
    row: int = Field(strict=True, ge=1, le=ParseLimits().max_rows)


class PreviewRow(PublicModel):
    key: PublicRowKey
    number: int
    disposition: Literal['candidate', 'blank_skipped', 'rejected']
    due_date: date | None
    fields: list[PreviewField]
    issues: list[PreviewIssue]


class PreviewCounts(PublicModel):
    candidate: int = Field(ge=0)
    rejected: int = Field(ge=0)
    blank_skipped: int = Field(ge=0)
    total: int = Field(ge=0)


class PreviewData(PublicModel):
    source_hash: str
    profile_version: str
    complete: bool
    rows: list[PreviewRow]
    issues: list[PreviewIssue]
    counts: PreviewCounts | None


class DateCorrections(PublicModel):
    # Required when this object is present: omission is not explicit null.
    due_date: str | None = Field(max_length=10)


class IncludeDecision(PublicModel):
    key: PublicRowKey
    action: Literal['include']
    project_id: str = Field(min_length=1, max_length=36)
    assignee_id: str = Field(min_length=1, max_length=36)
    corrections: DateCorrections = Field(default_factory=lambda: DateCorrections(due_date=None))


class ExcludeDecision(PublicModel):
    key: PublicRowKey
    action: Literal['exclude']
    reason: str = Field(min_length=1, max_length=512, pattern=r'\S')


class ReviewRequest(PublicModel):
    format: Literal['csv', 'xlsx']
    profile: Literal['checklist']
    source_base64: str = Field(min_length=1, max_length=MAX_ENCODED_SOURCE)
    source_hash: str = Field(min_length=64, max_length=64, pattern=r'^[0-9a-f]{64}$')
    profile_version: str = Field(min_length=1, max_length=64)
    decisions: list[Annotated[IncludeDecision | ExcludeDecision, Field(discriminator='action')]] = Field(
        max_length=MAX_DECISIONS,
    )

    def to_domain(self) -> ReviewInput:
        decisions = []
        for item in self.decisions:
            key = RowKey(item.key.source_hash, item.key.sheet, item.key.row)
            if isinstance(item, IncludeDecision):
                corrections = ((DateCorrection('due_date', item.corrections.due_date),)
                               if 'corrections' in item.model_fields_set else ())
                decisions.append(ReviewDecision(key, 'include', item.project_id,
                                                item.assignee_id, corrections=corrections))
            else:
                decisions.append(ReviewDecision(key, 'exclude', reason=item.reason))
        return ReviewInput(self.source_hash, self.profile_version, tuple(decisions))


class ReviewRow(PublicModel):
    key: PublicRowKey
    action: Literal['include', 'exclude', 'blank_skipped', 'unresolved']
    project_id: str | None
    assignee_id: str | None
    effective_due_date: date | None
    effective_status: str | None
    issues: list[str]


class ReviewData(PublicModel):
    status: Literal['blocked', 'validated_for_review']
    source_hash: str
    profile_version: str
    counts: PreviewCounts | None
    issues: list[str]
    rows: list[ReviewRow]


class ReviewResponse(PublicModel):
    data: ReviewData
    message: str = 'Revisión sin guardar tareas.'


def project_review(plan: ReviewedPlan) -> ReviewResponse:
    counts = plan.counts
    return ReviewResponse(data=ReviewData(
        status=plan.status, source_hash=plan.source_hash, profile_version=plan.profile_version,
        counts=None if counts is None else PreviewCounts(
            candidate=counts.candidate, rejected=counts.rejected,
            blank_skipped=counts.blank_skipped, total=counts.total),
        issues=list(plan.issues),
        rows=[ReviewRow(
            key=PublicRowKey(source_hash=row.key.source_hash, sheet=row.key.sheet, row=row.key.row),
            action=row.action, project_id=row.project_id, assignee_id=row.assignee_id,
            effective_due_date=row.effective_due_date, effective_status=row.effective_status,
            issues=list(row.issues),
        ) for row in plan.rows],
    ))


class PreviewResponse(PublicModel):
    data: PreviewData
    message: str = 'Vista previa sin guardar tareas.'


def _issue(issue: Issue) -> PreviewIssue:
    return PreviewIssue(code=issue.code, severity=issue.severity,
                        row=issue.row, column=issue.column)


def project_preview(preview: ChecklistPreview) -> PreviewResponse:
    """Only known checklist fields, row status, issues and counts leave HTTP.

    Unknown columns, source bytes/locator/provenance, sheet lists, raw headers
    and internal cell metadata are not exported. Hash/version/row coordinates
    bind a later fresh review; they are public provenance, never access tokens.
    Values are authorized uploaded content, not sanitized HTML or task writes.
    """
    columns = [(index, header.value) for index, header in enumerate(preview.headers)
               if isinstance(header.value, str) and header.value in _ALLOWED_HEADERS]
    counts = preview.counts
    return PreviewResponse(data=PreviewData(
        source_hash=preview.sha256, profile_version=PROFILE_VERSION,
        complete=preview.complete,
        rows=[PreviewRow(
            key=PublicRowKey(source_hash=preview.sha256, sheet=row.sheet, row=row.number),
            number=row.number, disposition=row.disposition, due_date=row.due_date,
            fields=[PreviewField(name=name, value=row.cells[index].value)
                    for index, name in columns],
            issues=[_issue(issue) for issue in row.issues],
        ) for row in preview.rows],
        issues=[_issue(issue) for issue in preview.issues],
        counts=None if counts is None else PreviewCounts(
            candidate=counts.candidate, rejected=counts.rejected,
            blank_skipped=counts.blank_skipped, total=counts.total,
        ),
    ))
