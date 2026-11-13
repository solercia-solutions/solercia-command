"""Business logic for the jira_import module (change 18-adapter-jira). NO
repository of its own — it never writes: reuses ``connectors``'
repository to read the conector and decrypt its ``api_token`` credentials,
then delegates the actual extraction/normalization to the REGISTERED
``jira`` adapter (specs/jira-import/spec.md "Frontera solo-lectura
estricta"). RBAC lives at the router layer (``require_role(admin,
manager)``); this service assumes the caller already passed that gate.
"""

import json
import uuid
from collections.abc import Awaitable, Sequence
from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.integrations.adapters.jira import errors
from app.integrations.adapters.jira.adapter import JiraAdapter
from app.integrations.adapters.jira.dtos import NormalizationReport, NormalizedJiraIssue
from app.integrations.registry import get_adapter
from app.methodology.factory import get_strategy
from app.modules.connectors.models import Connector
from app.modules.connectors.repository import ConnectedAccountRepository, ConnectorRepository
from app.modules.jira_import.importer import (
    DEFAULT_METHODOLOGY,
    AdapterIssueSource,
    ImportMapping,
    JiraProjectImporter,
)
from app.modules.jira_import.preview import (
    build_preview,
    project_jql,
    require_project_key,
    suggested_code,
)
from app.modules.jira_import.repository import JiraImportRepository
from app.modules.jira_import.schemas import (
    ImportedProjectRef,
    ImportSummaryRead,
    JiraImportProjectRequest,
    JiraImportRequest,
    JiraImportResponse,
    JiraPreviewResponse,
    JiraProjectRead,
    NormalizationReportRead,
    NormalizedJiraIssueRead,
)
from app.shared.exceptions import AppException

_PROJECT_UNAVAILABLE_MESSAGE = (
    "El proyecto de Jira no existe o la cuenta del conector ya no tiene acceso a él."
)


async def _translate_jira_errors[T](call: Awaitable[T], *, project_scoped: bool) -> T:
    """Run a Jira call of the project-import flow with wizard-safe errors.

    Jira's ``401`` becomes a ``400`` (a ``401`` would be read by the web
    client as an expired Command session); a rejected request on a project
    becomes ``jira_project_unavailable``. Messages never carry credentials.
    """

    try:
        return await call
    except errors.JiraAuthError as exc:
        raise AppException(exc.detail, code=exc.code, status_code=400) from exc
    except errors.JiraRequestFailed as exc:
        if not project_scoped:
            raise
        raise AppException(
            _PROJECT_UNAVAILABLE_MESSAGE, code="jira_project_unavailable", status_code=422
        ) from exc


def _to_response(
    issues: Sequence[NormalizedJiraIssue],
    report: NormalizationReport,
    *,
    truncated: bool = False,
    truncation_reason: str | None = None,
) -> JiraImportResponse:
    return JiraImportResponse(
        issues=[NormalizedJiraIssueRead.model_validate(issue) for issue in issues],
        report=NormalizationReportRead.model_validate(report),
        truncated=truncated,
        truncation_reason=truncation_reason,
    )


_EMPTY_RATE_LIMITED_REPORT = NormalizationReport(
    total=0,
    normalized=0,
    unmapped_types={},
    unmapped_statuses={},
    unmapped_priorities={},
    story_points_field=None,
    sprint_field=None,
    source="api",
)


class JiraImportService:
    """Orchestrates a Jira import (API or file vía) for a single
    organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.connectors = ConnectorRepository(db)
        self.accounts = ConnectedAccountRepository(db)
        self.imports = JiraImportRepository(db)

    async def list_projects(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> list[JiraProjectRead]:
        """Jira projects visible to the connector's account, flagged with
        the local project they were already imported into (read-only)."""

        source_kwargs = await self._source_kwargs(organization_id, connector_id)
        adapter = self._require_adapter()
        projects = await _translate_jira_errors(
            adapter.list_projects(
                base_url=source_kwargs["base_url"],
                email=source_kwargs["email"],
                api_token=source_kwargs["api_token"],
            ),
            project_scoped=False,
        )
        imported = await self.imports.jira_projects_by_key(organization_id)
        return [
            JiraProjectRead(
                key=project["key"],
                name=project["name"],
                imported_project=(
                    ImportedProjectRef.model_validate(imported[project["key"]])
                    if project["key"] in imported
                    else None
                ),
            )
            for project in projects
        ]

    async def preview(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID, project_key: str
    ) -> JiraPreviewResponse:
        """Counts and proposed mapping of one Jira project — persists nothing."""

        key = require_project_key(project_key)
        source = await self._issue_source(organization_id, connector_id)
        issues, report = await _translate_jira_errors(
            source.fetch_issues(project_jql(key)), project_scoped=True
        )
        existing = await self.imports.project_by_anchor(organization_id, key)
        methodology = existing.methodology if existing is not None else DEFAULT_METHODOLOGY
        preview = build_preview(issues, report, strategy=get_strategy(methodology))
        return JiraPreviewResponse(
            project_key=key,
            suggested_code=suggested_code(key),
            methodology=methodology.value,
            existing_project=(
                ImportedProjectRef.model_validate(existing) if existing is not None else None
            ),
            total=preview.total,
            counts_by_type=preview.counts_by_type,
            sprints=[asdict(sprint) for sprint in preview.sprints],
            status_mapping=[asdict(item) for item in preview.status_mapping],
            target_statuses=preview.target_statuses,
            estimated_hours=preview.estimated_hours,
            issues_with_estimate=preview.issues_with_estimate,
            story_points=preview.story_points,
            issues_with_points=preview.issues_with_points,
            unmapped_types=preview.unmapped_types,
            unmapped_statuses=preview.unmapped_statuses,
            unmapped_priorities=preview.unmapped_priorities,
            skipped_malformed=preview.skipped_malformed,
        )

    async def import_project(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        payload: JiraImportProjectRequest,
        *,
        actor_id: uuid.UUID | None,
    ) -> ImportSummaryRead:
        """Import (or reconcile) one Jira project in ONE transaction: it
        commits once on success and rolls everything back on any failure."""

        key = require_project_key(payload.project_key)
        source = await self._issue_source(organization_id, connector_id)
        mapping = ImportMapping(
            project_name=payload.project_name,
            project_code=payload.project_code,
            status_overrides=payload.status_overrides,
        )
        try:
            summary = await _translate_jira_errors(
                JiraProjectImporter(self.db).importar_proyecto(
                    source, key, mapping, organization_id=organization_id, actor_id=actor_id
                ),
                project_scoped=True,
            )
            result = ImportSummaryRead.model_validate(summary)
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            raise
        return result

    async def _source_kwargs(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> dict[str, str]:
        connector = await self._require_jira_connector(organization_id, connector_id)
        email, api_token, base_url = await self._decrypt_credentials(connector)
        return {"base_url": base_url, "email": email, "api_token": api_token}

    async def _issue_source(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> AdapterIssueSource:
        connector = await self._require_jira_connector(organization_id, connector_id)
        email, api_token, base_url = await self._decrypt_credentials(connector)
        return AdapterIssueSource(
            self._require_adapter(),
            base_url=base_url,
            email=email,
            api_token=api_token,
            jira_settings=self._jira_settings(connector),
        )

    async def import_via_api(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        payload: JiraImportRequest,
    ) -> JiraImportResponse:
        """Extract + normalize issues via the API vía
        (specs/jira-import/spec.md "Import por API devuelve issues +
        resumen")."""

        connector = await self._require_jira_connector(organization_id, connector_id)
        email, api_token, base_url = await self._decrypt_credentials(connector)
        adapter = self._require_adapter()

        try:
            issues, report = await adapter.import_issues(
                base_url=base_url,
                email=email,
                api_token=api_token,
                jql=payload.jql,
                jira_settings=self._jira_settings(connector),
                since=payload.since,
            )
        except errors.JiraRateLimited as exc:
            # "Reintentos agotados": pages already extracted survive as a
            # partial, successful import instead of a 503 that discards them.
            return _to_response(
                exc.normalized_partial_issues,
                exc.partial_report or _EMPTY_RATE_LIMITED_REPORT,
                truncated=True,
                truncation_reason="rate_limited",
            )
        return _to_response(issues, report)

    async def import_via_file(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        filename: str,
        content: bytes,
    ) -> JiraImportResponse:
        """Extract + normalize issues via an uploaded CSV/XLSX
        (specs/jira-import/spec.md "Import por archivo devuelve el mismo
        contrato")."""

        connector = await self._require_jira_connector(organization_id, connector_id)
        adapter = self._require_adapter()

        issues, report = adapter.parse_file(
            content, filename, jira_settings=self._jira_settings(connector)
        )
        return _to_response(issues, report)

    async def _require_jira_connector(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> Connector:
        """404 if the connector does not exist, belongs to another
        organization, or is not a ``jira`` connector (specs/jira-import/
        spec.md "Conector ajeno")."""

        connector = await self.connectors.get(organization_id, connector_id)
        if connector is None or connector.provider != "jira":
            raise AppException(
                "El conector no existe, no tienes acceso a él o no es un "
                "conector Jira.",
                code="connector_not_found",
                status_code=404,
            )
        return connector

    async def _decrypt_credentials(self, connector: Connector) -> tuple[str, str, str]:
        """Decrypt the connector's ``api_token`` credentials
        (``{base_url, email, api_token}``, registered via ``POST
        /connectors/{id}/credentials``). ``settings.jira.base_url``
        (durable, admin-configurable) wins over the value stored inside
        the credentials blob when both are present."""

        accounts = await self.accounts.list_accounts(connector.id, connector.organization_id)
        if not accounts:
            raise AppException(
                "El conector Jira no tiene credenciales registradas. "
                "Regístralas primero (POST /connectors/{id}/credentials).",
                code="jira_credentials_missing",
                status_code=400,
            )
        credentials = await self.accounts.get_credentials(accounts[0].id)
        if credentials is None:
            raise AppException(
                "El conector Jira no tiene credenciales registradas. "
                "Regístralas primero (POST /connectors/{id}/credentials).",
                code="jira_credentials_missing",
                status_code=400,
            )

        raw: dict[str, str] = json.loads(crypto.decrypt(credentials.access_token_enc))
        jira_settings = self._jira_settings(connector)
        base_url = jira_settings.get("base_url") or raw.get("base_url") or ""
        return raw.get("email", ""), raw.get("api_token", ""), base_url

    @staticmethod
    def _jira_settings(connector: Connector) -> dict:
        settings = connector.settings or {}
        jira_settings = settings.get("jira")
        return dict(jira_settings) if isinstance(jira_settings, dict) else {}

    @staticmethod
    def _require_adapter() -> JiraAdapter:
        adapter = get_adapter("jira")
        if not isinstance(adapter, JiraAdapter):
            raise AppException(
                "El proveedor Jira no está disponible.",
                code="provider_not_registered",
                status_code=404,
            )
        return adapter
