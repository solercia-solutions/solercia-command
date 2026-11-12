"""Solercia Connect facade — register one Microsoft account, drive the
supervised browser login Connect exposes over HTTP, read the connection
state and pull mail into intake, all from Command's API.

Connect owns the provider session (a Chromium profile on the person's own
machine); Command owns work. This service therefore never sees a Microsoft
credential: the only secret it handles is the runtime's API key, which it
reads from ``settings.SOLERCIA_CONNECT_API_KEY`` at registration, hands to
the generic ``register_api_token_credentials`` path (encrypted as the same
opaque blob every ``api_token`` provider uses) and later decrypts from
``ConnectionCredentials`` — never logging it, never returning it.

Every Connect answer is mapped HERE, once, from its typed envelope onto
Command's vocabulary (``SolerciaConnectState`` for status, ``AppException``
codes for the writes). The router stays thin and the intake pipeline stays
provider-agnostic: it keeps receiving the decrypted blob as
``AccessContext.access_token`` and the adapter decodes it.

Transaction ownership: repositories flush, this service commits
(``agents/rules/solercia-persistence.md``). Every read is scoped by
``organization_id`` and a connector of another provider is a 404, the same
"wrong kind == not found" convention ``_build_mcp_access_context`` uses.
"""

import dataclasses
import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.config import settings as default_settings
from app.integrations import crypto
from app.integrations.adapters.solercia_connect.adapter import LOGIN_REQUIRED_CODES, PROVIDER
from app.integrations.adapters.solercia_connect.client import (
    ConnectResponse,
    SolerciaConnectClient,
)
from app.integrations.adapters.solercia_connect.errors import (
    SolerciaConnectAuthError,
    SolerciaConnectConfigError,
    SolerciaConnectError,
    SolerciaConnectNotConfiguredError,
    SolerciaConnectUnavailableError,
)
from app.integrations.ports import CredentialKind
from app.modules.connectors.models import ConnectedAccount, Connector
from app.modules.connectors.repository import ConnectedAccountRepository, ConnectorRepository
from app.modules.connectors.schemas import (
    ConnectorRead,
    SolerciaConnectRegister,
    SolerciaConnectRegisterRead,
    SolerciaConnectRuntimeRead,
    SolerciaConnectSessionRead,
    SolerciaConnectSessionStartRead,
    SolerciaConnectSettingsRead,
    SolerciaConnectStatusRead,
    SolerciaConnectSyncError,
    SolerciaConnectSyncRead,
    SolerciaConnectSyncRequest,
)
from app.modules.connectors.service import ConnectorService
from app.modules.intake.service import IntakeRunOutcome, IntakeService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import AccountStatus, ConnectorStatus
from app.shared.exceptions import AppException

logger = logging.getLogger("solercia.connectors.solercia_connect")

#: Key under ``connectors.settings`` holding the NON-secret configuration
#: the UI reads back from ``ConnectorRead.settings``.
SETTINGS_KEY = "solercia_connect"

_CONNECTED_STATUSES = frozenset({"connected_browser", "connected_official"})
# Session failures that mean "log in again" (account -> expired); every other
# failure is an error of the runtime or the profile (account -> error).
_EXPIRED_SESSION_CODES = frozenset(
    {"browser_login_required", "browser_mfa_required", "browser_account_mismatch"}
)
# Connect hands out uuid4 session ids. Anything else never reaches its URL
# path: the id is interpolated into a request to a loopback runtime.
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

_STATE_TO_ACCOUNT_STATUS: dict[str, AccountStatus] = {
    "connected": AccountStatus.active,
    "needs_login": AccountStatus.expired,
    "error": AccountStatus.error,
    "misconfigured": AccountStatus.error,
}

_NOT_CONFIGURED_DETAIL = (
    "La conexión con Solercia Connect no está configurada. Regístrala desde Conexiones."
)


@dataclasses.dataclass(frozen=True)
class _ConnectorConfig:
    """The non-secret half: what ``connectors.settings["solercia_connect"]`` stores."""

    account: str
    target: str
    allow_browser_fallback: bool

    def as_read(self) -> SolerciaConnectSettingsRead:
        return SolerciaConnectSettingsRead(
            account=self.account,
            target=self.target,  # type: ignore[arg-type]
            allow_browser_fallback=self.allow_browser_fallback,
        )


@dataclasses.dataclass(frozen=True)
class _RuntimeAccess:
    """The secret half, decrypted from ``ConnectionCredentials`` for one call."""

    base_url: str
    api_key: str


def _not_configured(detail: str = _NOT_CONFIGURED_DETAIL) -> AppException:
    return AppException(detail, code="solercia_connect_not_configured", status_code=422)


def _map_failure(failure: SolerciaConnectError) -> AppException:
    """One place that turns adapter failures into Command's error envelope."""

    if isinstance(failure, SolerciaConnectConfigError):
        return _not_configured(
            "El servidor no tiene configurado Solercia Connect: revisa "
            "SOLERCIA_CONNECT_BASE_URL (debe estar en la allowlist) y SOLERCIA_CONNECT_API_KEY."
        )
    if isinstance(failure, SolerciaConnectNotConfiguredError):
        return AppException(
            "Solercia Connect está en ejecución pero no está configurado para atender "
            "esta solicitud. Revisa la configuración del runtime en tu equipo.",
            code="solercia_connect_unavailable",
            status_code=503,
        )
    if isinstance(failure, SolerciaConnectUnavailableError):
        return AppException(
            "Solercia Connect no responde en la dirección configurada. Inicia el "
            "runtime en tu equipo e inténtalo de nuevo.",
            code="solercia_connect_unavailable",
            status_code=503,
        )
    if isinstance(failure, SolerciaConnectAuthError):
        return AppException(
            "Solercia Connect rechazó la llave configurada. Verifica que "
            "SOLERCIA_CONNECT_API_KEY coincida con la del runtime y registra la conexión de nuevo.",
            code="solercia_connect_unauthorized",
            status_code=502,
        )
    return AppException(
        "Solercia Connect respondió en un formato que Command no reconoce.",
        code="solercia_connect_protocol_error",
        status_code=502,
    )


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _runtime_from_health(health: dict[str, Any]) -> SolerciaConnectRuntimeRead:
    data = health.get("data")
    payload = data if isinstance(data, dict) else {}
    version = payload.get("version")
    interactive = payload.get("interactive_login")
    return SolerciaConnectRuntimeRead(
        reachable=True,
        version=str(version) if isinstance(version, str | int | float) else None,
        interactive_login=interactive if isinstance(interactive, bool) else None,
    )


class SolerciaConnectService:
    """Use cases behind ``/connectors/solercia-connect*`` for one organization."""

    def __init__(self, db: AsyncSession, *, settings: Settings | None = None) -> None:
        self.db = db
        self.repo = ConnectorRepository(db)
        self.accounts = ConnectedAccountRepository(db)
        self.connectors = ConnectorService(db)
        self._settings = settings or default_settings

    # -- 1. register ---------------------------------------------------------

    async def register(
        self,
        organization_id: uuid.UUID,
        data: SolerciaConnectRegister,
        membership: OrganizationMember,
    ) -> SolerciaConnectRegisterRead:
        """Create or reuse the organization's single ``solercia_connect``
        connector, store its non-secret settings and register the runtime's
        API key as its ``api_token`` credentials.

        Order matters: the runtime is probed (``GET /v1/health``) BEFORE any
        row is written, so a stopped Connect leaves nothing half-registered.
        ``register_api_token_credentials`` then performs its own handshake
        (the adapter validates before persisting, as every ``api_token``
        provider does) — two health calls, both unauthenticated and cheap,
        in exchange for reusing the audited persistence path unchanged.

        Re-registering with a DIFFERENT account keeps one account per
        connector: the previous account is disconnected (its credentials
        purged) so intake never reads a mailbox the settings no longer name.
        """

        api_key = self._server_api_key()
        base_url = self._settings.SOLERCIA_CONNECT_BASE_URL
        try:
            runtime = _runtime_from_health(await self._client(base_url, api_key).health())
        except SolerciaConnectError as failure:
            raise _map_failure(failure) from failure

        config = _ConnectorConfig(
            account=data.account,
            target=data.target,
            allow_browser_fallback=data.allow_browser_fallback,
        )
        connector = await self._create_or_reuse_connector(
            organization_id, config, actor_id=membership.user_id
        )

        raw = {
            "connector_id": str(connector.id),
            "base_url": base_url,
            "api_key": api_key,
            "account": config.account,
            "target": config.target,
            "allow_browser_fallback": "true" if config.allow_browser_fallback else "false",
        }
        try:
            account = await self.connectors.register_api_token_credentials(
                organization_id, connector.id, raw, membership
            )
        except SolerciaConnectError as failure:
            raise _map_failure(failure) from failure

        await self._retire_other_accounts(
            organization_id,
            connector,
            keep_external_account_id=account.external_account_id,
            actor_id=membership.user_id,
        )
        logger.info(
            "Solercia Connect registrado: connector_id=%s target=%s", connector.id, config.target
        )
        return SolerciaConnectRegisterRead(
            connector=ConnectorRead.model_validate(connector),
            account=account,
            settings=config.as_read(),
            runtime=runtime,
        )

    async def _create_or_reuse_connector(
        self, organization_id: uuid.UUID, config: _ConnectorConfig, *, actor_id: uuid.UUID
    ) -> Connector:
        """Idempotent on ``uq_connectors_organization_provider``: the
        existing connector is reused (and re-activated) instead of tripping
        the constraint; settings are merged under :data:`SETTINGS_KEY` so
        namespaces other providers may share are left untouched."""

        payload = dataclasses.asdict(config)
        connector = await self.repo.get_by_provider(organization_id, PROVIDER)
        if connector is None:
            connector = Connector(
                organization_id=organization_id,
                provider=PROVIDER,
                scopes=None,
                status=ConnectorStatus.active,
                credential_kind=CredentialKind.api_token,
                settings={SETTINGS_KEY: payload},
                created_by=actor_id,
                updated_by=actor_id,
            )
            return await self.repo.create(connector)

        merged = dict(connector.settings or {})
        merged[SETTINGS_KEY] = payload
        connector.settings = merged
        connector.status = ConnectorStatus.active
        connector.updated_by = actor_id
        return await self.repo.save(connector)

    async def _retire_other_accounts(
        self,
        organization_id: uuid.UUID,
        connector: Connector,
        *,
        keep_external_account_id: str,
        actor_id: uuid.UUID,
    ) -> None:
        accounts = await self.accounts.list_accounts(connector.id, organization_id)
        for row in accounts:
            if row.external_account_id != keep_external_account_id:
                await self.accounts.soft_delete_account(row, actor_id=actor_id)

    # -- 2. status -----------------------------------------------------------

    async def status(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> SolerciaConnectStatusRead:
        """Ask Connect whether the stored session for the account is usable.

        A Connect-side failure is never raised here: the resulting ``state``
        IS the answer the UI renders. Only an unknown or foreign connector is
        a 404. Side effect: the account's lifecycle status follows the state
        (``connected`` → active, ``needs_login`` → expired, ``error``/
        ``misconfigured`` → error; runtime states leave it untouched).
        """

        connector = await self._require_connector(organization_id, connector_id)
        checked_at = datetime.now(UTC)
        config = self._config_of(connector)
        account_row = (
            await self._primary_account(organization_id, connector, config)
            if config is not None
            else None
        )
        access = await self._runtime_access(account_row) if account_row is not None else None

        def _result(
            state: str,
            *,
            runtime: SolerciaConnectRuntimeRead,
            detail: str | None,
            remediation: list[str] | None = None,
            route: str | None = None,
        ) -> SolerciaConnectStatusRead:
            return SolerciaConnectStatusRead(
                state=state,  # type: ignore[arg-type]
                route=route,
                account=config.account if config is not None else None,
                checked_at=checked_at,
                detail=detail,
                remediation=remediation or [],
                runtime=runtime,
            )

        unprobed = SolerciaConnectRuntimeRead(reachable=None)
        if config is None or account_row is None or access is None:
            return _result(
                "misconfigured",
                runtime=unprobed,
                detail=_NOT_CONFIGURED_DETAIL,
                remediation=["Registra la conexión de nuevo desde Conexiones."],
            )

        try:
            client = self._client(access.base_url, access.api_key)
        except SolerciaConnectConfigError:
            return _result(
                "misconfigured",
                runtime=unprobed,
                detail=(
                    "La dirección de Solercia Connect guardada ya no está permitida en el "
                    "servidor. Registra la conexión de nuevo."
                ),
            )

        runtime = SolerciaConnectRuntimeRead(reachable=False)
        state: str
        detail: str | None
        remediation: list[str] = []
        route: str | None = None
        try:
            runtime = _runtime_from_health(await client.health())
            response = await client.test_connection(
                type_=config.target,
                account=config.account,
                allow_browser_fallback=config.allow_browser_fallback,
            )
        except SolerciaConnectNotConfiguredError as failure:
            runtime = SolerciaConnectRuntimeRead(reachable=True)
            state, detail = "misconfigured", _map_failure(failure).detail
        except SolerciaConnectUnavailableError as failure:
            state, detail = "runtime_unavailable", _map_failure(failure).detail
        except SolerciaConnectAuthError as failure:
            state, detail = "runtime_unauthorized", _map_failure(failure).detail
        except SolerciaConnectError:
            state, detail = "error", _map_failure(SolerciaConnectError("protocol")).detail
        else:
            state, route, detail, remediation = self._map_test_response(
                response, interactive_login=runtime.interactive_login, config=config
            )

        await self._record_account_state(organization_id, account_row, state, actor_id=actor_id)
        return _result(state, runtime=runtime, detail=detail, remediation=remediation, route=route)

    @staticmethod
    def _map_test_response(
        response: ConnectResponse,
        *,
        interactive_login: bool | None,
        config: _ConnectorConfig,
    ) -> tuple[str, str | None, str | None, list[str]]:
        """Contract table for ``POST /v1/connections/test`` →
        ``(state, route, detail, remediation)``."""

        route_value = response.body.get("route")
        route = route_value if isinstance(route_value, str) else None
        if response.ok and response.status in _CONNECTED_STATUSES:
            return (
                "connected",
                route,
                f"La cuenta {config.account} está conectada en Solercia Connect.",
                [],
            )

        code = response.error_code
        remediation = response.remediation
        if response.status_code == 409 and code == "action_required":
            if interactive_login:
                return (
                    "needs_login",
                    route,
                    "Debes iniciar sesión en la cuenta con el navegador supervisado de "
                    "Solercia Connect.",
                    remediation,
                )
            return (
                "interactive_disabled",
                route,
                "Solercia Connect no permite iniciar sesión desde Command. Habilita el "
                "inicio interactivo por HTTP en el runtime.",
                remediation,
            )
        if code == "configuration_error":
            return (
                "misconfigured",
                route,
                response.error_message
                or "Solercia Connect no está configurado para atender esta cuenta.",
                remediation,
            )
        if code == "interactive_session_busy":
            return (
                "error",
                route,
                "Hay un inicio de sesión en curso en Solercia Connect. Espera a que "
                "termine antes de verificar la conexión.",
                remediation,
            )
        return (
            "error",
            route,
            response.error_message or "Solercia Connect no pudo verificar la conexión.",
            remediation,
        )

    # -- 3. start the supervised browser login ---------------------------------

    async def start_connect(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> SolerciaConnectSessionStartRead:
        """``POST /v1/connections/connect`` — Connect opens a headed browser
        on the person's machine; Command only gets the session id to poll."""

        _, config, access = await self._require_configured(organization_id, connector_id)
        if not config.allow_browser_fallback:
            raise AppException(
                "Habilita el inicio de sesión con navegador en la configuración de la conexión.",
                code="solercia_connect_fallback_not_allowed",
                status_code=409,
            )
        client = self._client_or_raise(access)
        try:
            response = await client.connect_browser(type_=config.target, account=config.account)
        except SolerciaConnectError as failure:
            raise _map_failure(failure) from failure

        if response.status_code == 202 or (response.ok and response.status == "started"):
            session_id = response.data.get("session_id")
            if not isinstance(session_id, str) or not session_id.strip():
                raise _map_failure(SolerciaConnectError("started without a session id"))
            expires = response.data.get("expires_in_seconds")
            return SolerciaConnectSessionStartRead(
                session_id=session_id,
                started=True,
                expires_in_seconds=expires if isinstance(expires, int) else None,
            )

        if response.status_code == 409 and response.error_code == "interactive_session_busy":
            running = response.data.get("session_id")
            raise AppException(
                "Ya hay un inicio de sesión en curso en Solercia Connect. Espera a que "
                "termine e inténtalo de nuevo.",
                code="solercia_connect_busy",
                status_code=409,
                meta={"session_id": running if isinstance(running, str) else None},
            )
        if response.status_code == 409 and response.error_code == "action_required":
            detail = " ".join(response.remediation) or response.error_message
            raise AppException(
                detail
                or "Solercia Connect no permite iniciar sesión desde Command. Habilita el "
                "inicio interactivo por HTTP en el runtime.",
                code="solercia_connect_interactive_disabled",
                status_code=409,
            )
        if response.status_code == 422:
            raise AppException(
                response.error_message
                or "Solercia Connect rechazó los datos de la conexión (cuenta o destino).",
                code="solercia_connect_invalid_request",
                status_code=422,
            )
        raise _map_failure(SolerciaConnectError(f"unexpected {response.status_code}"))

    # -- 4. poll the login session --------------------------------------------

    async def session(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        session_id: str,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> SolerciaConnectSessionRead:
        """``GET /v1/connections/sessions/{id}`` mapped onto
        ``running | connected | failed | not_found``; the account's status
        follows a finished session (connected → active; a login-type failure
        → expired; any other failure → error)."""

        if not _SESSION_ID.match(session_id):
            raise AppException(
                "El identificador de sesión no es válido.",
                code="solercia_connect_invalid_request",
                status_code=422,
            )
        connector, config, access = await self._require_configured(organization_id, connector_id)
        client = self._client_or_raise(access)
        try:
            response = await client.session(session_id)
        except SolerciaConnectError as failure:
            raise _map_failure(failure) from failure

        data = response.data
        route_value = response.body.get("route")
        result = SolerciaConnectSessionRead(
            state="not_found",
            route=route_value if isinstance(route_value, str) else None,
            started_at=_timestamp(data.get("started_at")),
            finished_at=_timestamp(data.get("finished_at")),
        )
        account_status: AccountStatus | None = None
        if (
            response.status_code == 404
            or response.status == "not_found"
            or response.error_code == "session_not_found"
        ):
            result = result.model_copy(update={"state": "not_found"})
        elif response.status == "running":
            result = result.model_copy(update={"state": "running"})
        elif response.ok and response.status in _CONNECTED_STATUSES:
            result = result.model_copy(
                update={
                    "state": "connected",
                    "detail": f"La cuenta {config.account} quedó conectada en Solercia Connect.",
                }
            )
            account_status = AccountStatus.active
        elif not response.ok:
            code = response.error_code
            result = result.model_copy(
                update={
                    "state": "failed",
                    "error_code": code,
                    "detail": response.error_message
                    or "El inicio de sesión supervisado no se completó.",
                    "remediation": response.remediation,
                }
            )
            account_status = (
                AccountStatus.expired if code in _EXPIRED_SESSION_CODES else AccountStatus.error
            )
        else:
            raise _map_failure(SolerciaConnectError("unknown session envelope"))

        if account_status is not None:
            account_row = await self._primary_account(organization_id, connector, config)
            if account_row is not None:
                await self.accounts.mark_status(
                    organization_id, account_row, account_status, actor_id=actor_id
                )
                await self.db.commit()
        return result

    # -- 5. sync ---------------------------------------------------------------

    async def sync(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        data: SolerciaConnectSyncRequest,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> SolerciaConnectSyncRead:
        """Run the intake pull restricted to THIS connector and summarize it.

        A run that read nothing because the person must log in first is a
        409 ``solercia_connect_needs_login`` (and the account is marked
        expired); any other failure is reported in ``errors`` with a 200 so
        partial progress is never hidden behind an error page.
        """

        connector, config, _ = await self._require_configured(organization_id, connector_id)
        since = datetime.now(UTC) - timedelta(days=data.since_days)
        outcomes = await IntakeService(self.db).pull_outcomes(
            organization_id, actor_id=actor_id, connector_id=connector.id, since=since
        )
        summary = self._summarize(outcomes)

        needs_login = (
            bool(outcomes)
            and summary.items_fetched == 0
            and all(outcome.error_code in LOGIN_REQUIRED_CODES for outcome in outcomes)
        )
        if needs_login:
            account_row = await self._primary_account(organization_id, connector, config)
            if account_row is not None:
                await self.accounts.mark_status(
                    organization_id, account_row, AccountStatus.expired, actor_id=actor_id
                )
                await self.db.commit()
            raise AppException(
                f"La cuenta {config.account} requiere iniciar sesión de nuevo en Solercia "
                "Connect antes de sincronizar.",
                code="solercia_connect_needs_login",
                status_code=409,
                meta={"errors": [error.model_dump(mode="json") for error in summary.errors]},
            )
        return summary

    @staticmethod
    def _summarize(outcomes: list[IntakeRunOutcome]) -> SolerciaConnectSyncRead:
        runs = [outcome.run for outcome in outcomes]
        errors: list[SolerciaConnectSyncError] = []
        for outcome in outcomes:
            if outcome.error_code is not None:
                errors.append(
                    SolerciaConnectSyncError(
                        run_id=outcome.run.id,
                        code=outcome.error_code,
                        detail=outcome.error_detail or "La ingesta de esta cuenta falló.",
                    )
                )
            if outcome.anchor_conflicts:
                errors.append(
                    SolerciaConnectSyncError(
                        run_id=outcome.run.id,
                        code="task_external_anchor_conflict",
                        detail=(
                            f"{outcome.anchor_conflicts} insumo(s) ya tenían una tarea con esa "
                            "procedencia externa y quedaron en triage."
                        ),
                    )
                )
        failed = sum(1 for outcome in outcomes if outcome.error_code is not None)
        if not outcomes:
            status = "skipped"
        elif failed == len(outcomes):
            status = "error"
        elif errors:
            status = "partial"
        else:
            status = "completed"
        converted = sum(run.items_converted for run in runs)
        return SolerciaConnectSyncRead(
            run_id=runs[0].id if runs else None,
            runs=runs,
            status=status,  # type: ignore[arg-type]
            items_fetched=sum(run.items_fetched for run in runs),
            items_new=sum(run.items_new for run in runs),
            items_duplicated=sum(run.items_duplicated for run in runs),
            items_converted=converted,
            tasks_created=converted,
            errors=errors,
        )

    # -- helpers ---------------------------------------------------------------

    def _server_api_key(self) -> str:
        key = self._settings.SOLERCIA_CONNECT_API_KEY
        value = key.get_secret_value().strip() if key is not None else ""
        if not value:
            raise _not_configured(
                "El servidor no tiene configurada la llave de Solercia Connect "
                "(SOLERCIA_CONNECT_API_KEY)."
            )
        return value

    def _client(self, base_url: str, api_key: str) -> SolerciaConnectClient:
        return SolerciaConnectClient(base_url=base_url, api_key=api_key, settings=self._settings)

    def _client_or_raise(self, access: _RuntimeAccess) -> SolerciaConnectClient:
        try:
            return self._client(access.base_url, access.api_key)
        except SolerciaConnectConfigError as failure:
            raise _map_failure(failure) from failure

    async def _require_connector(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> Connector:
        connector = await self.repo.get(organization_id, connector_id)
        if connector is None or connector.provider != PROVIDER:
            raise AppException(
                "El conector no existe o no tienes acceso a él.",
                code="connector_not_found",
                status_code=404,
            )
        return connector

    async def _require_configured(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> tuple[Connector, _ConnectorConfig, _RuntimeAccess]:
        connector = await self._require_connector(organization_id, connector_id)
        config = self._config_of(connector)
        if config is None:
            raise _not_configured()
        account_row = await self._primary_account(organization_id, connector, config)
        access = await self._runtime_access(account_row) if account_row is not None else None
        if access is None:
            raise _not_configured()
        return connector, config, access

    @staticmethod
    def _config_of(connector: Connector) -> _ConnectorConfig | None:
        stored = (connector.settings or {}).get(SETTINGS_KEY)
        if not isinstance(stored, dict):
            return None
        account = stored.get("account")
        target = stored.get("target")
        if not isinstance(account, str) or not account.strip():
            return None
        if not isinstance(target, str) or not target.strip():
            return None
        flag = stored.get("allow_browser_fallback", True)
        return _ConnectorConfig(
            account=account.strip().lower(),
            target=target,
            allow_browser_fallback=(
                flag if isinstance(flag, bool) else str(flag).strip().casefold() == "true"
            ),
        )

    async def _primary_account(
        self, organization_id: uuid.UUID, connector: Connector, config: _ConnectorConfig
    ) -> ConnectedAccount | None:
        """The account the settings name (its ``external_account_id`` is the
        canonical address), or the connector's only account as a fallback."""

        accounts = await self.accounts.list_accounts(connector.id, organization_id)
        for row in accounts:
            if row.external_account_id.casefold() == config.account.casefold():
                return row
        return accounts[0] if accounts else None

    async def _runtime_access(self, account_row: ConnectedAccount) -> _RuntimeAccess | None:
        """Decrypt the registration blob — the ONLY place the API key is in
        clear, for the duration of one call, never logged."""

        credentials = await self.accounts.get_credentials(account_row.id)
        if credentials is None:
            return None
        try:
            payload = json.loads(crypto.decrypt(credentials.access_token_enc))
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None
        base_url = payload.get("base_url")
        api_key = payload.get("api_key")
        if not isinstance(base_url, str) or not isinstance(api_key, str):
            return None
        if not base_url.strip() or not api_key.strip():
            return None
        return _RuntimeAccess(base_url=base_url, api_key=api_key)

    async def _record_account_state(
        self,
        organization_id: uuid.UUID,
        account_row: ConnectedAccount,
        state: str,
        *,
        actor_id: uuid.UUID | None,
    ) -> None:
        target = _STATE_TO_ACCOUNT_STATUS.get(state)
        if target is None:
            return
        await self.accounts.mark_status(organization_id, account_row, target, actor_id=actor_id)
        await self.db.commit()
