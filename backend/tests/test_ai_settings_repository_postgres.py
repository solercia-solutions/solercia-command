"""C04: `SqlAiProviderSettingsRepository` against real PostgreSQL — tenant
scoped lookup and the one-row-per-organization UNIQUE."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_settings.models import AiProviderSettings
from app.modules.ai_settings.repository import SqlAiProviderSettingsRepository
from tests.conftest import skip_no_db

pytestmark = [skip_no_db, pytest.mark.asyncio(loop_scope="session")]


def _row(organization_id, **overrides) -> AiProviderSettings:
    values = dict(
        organization_id=organization_id,
        preset="ollama_local",
        chat_model="qwen3.5:9b-q4_K_M",
        embedding_model="qwen3-embedding:0.6b",
        options={"num_ctx": 4096},
    )
    values.update(overrides)
    return AiProviderSettings(**values)


async def test_add_and_find_are_scoped_by_organization(
    session: AsyncSession, tenant, second_tenant
):
    repo = SqlAiProviderSettingsRepository(session)
    await repo.add(_row(tenant.id))
    found = await repo.find_for_organization(tenant.id)
    assert found is not None and found.options == {"num_ctx": 4096}
    assert found.enabled is True and found.reasoning_effort == "none"
    assert found.timeout_seconds == 60 and found.max_tokens == 1024
    assert await repo.find_for_organization(second_tenant.id) is None


async def test_one_row_per_organization(session: AsyncSession, tenant):
    repo = SqlAiProviderSettingsRepository(session)
    await repo.add(_row(tenant.id))
    with pytest.raises(IntegrityError):
        await repo.add(_row(tenant.id, preset="openai"))
