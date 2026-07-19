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
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.integrations.adapters.jira.adapter import JiraAdapter
from app.integrations.adapters.jira.dtos import NormalizationReport, NormalizedJiraIssue
from app.integrations.registry import get_adapter
from app.modules.connectors.models import Connector
from app.modules.connectors.repository import ConnectedAccountRepository, ConnectorRepository
from app.modules.jira_import.schemas import (
    JiraImportRequest,
    JiraImportResponse,
    NormalizationReportRead,
    NormalizedJiraIssueRead,
)
from app.shared.exceptions import AppException


def _to_response(
    issues: Sequence[NormalizedJiraIssue], report: NormalizationReport
) -> JiraImportResponse:
    return JiraImportResponse(
        issues=[NormalizedJiraIssueRead.model_validate(issue) for issue in issues],
        report=NormalizationReportRead.model_validate(report),
    )


class JiraImportService:
    """Orchestrates a Jira import (API or file vía) for a single
    organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.connectors = ConnectorRepository(db)
        self.accounts = ConnectedAccountRepository(db)

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

        issues, report = await adapter.import_issues(
            base_url=base_url,
            email=email,
            api_token=api_token,
            jql=payload.jql,
            jira_settings=self._jira_settings(connector),
            since=payload.since,
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
