"""assistant routes: `GET /assistant/health` — `LlmPort` diagnostic
endpoint (change 48-puerto-llm, design.md "Endpoint de salud"). Same RBAC
shape as `glpi_sync`/`connectors`: `require_role(admin, manager)`; `member`
and `viewer` get 403 (spec `assistant-health` R1).
"""

from fastapi import APIRouter, Depends, Query

from app.dependencies import require_role
from app.modules.assistant.service import AssistantHealthService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Module-level singleton (ruff B008, precedent `glpi_sync/router.py:26`).
require_assistant_role = require_role(MemberRole.admin, MemberRole.manager)


@router.get("/health")
async def get_health(
    probe: bool = Query(False),
    membership: OrganizationMember = Depends(require_assistant_role),
) -> dict:
    """Report the active `LlmPort` adapter's configuration. `?probe=true`
    additionally checks reachability WITHOUT generating text (spec
    `assistant-health` R3); the body never carries a secret (R4)."""

    service = AssistantHealthService()
    data = await service.describe(probe=probe)
    return {"data": data, "message": "Estado del proveedor de IA."}
