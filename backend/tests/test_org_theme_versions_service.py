"""Offline contracts of the organization theme history use cases (fakes, no DB).

``OrganizationThemeService`` is driven through an in-memory
``OrganizationThemePort`` that enforces the same rules as the PostgreSQL
adapter (tenant scope on every read, one initial capture per organization, a
source version of the SAME organization) and a transaction double that discards
uncommitted writes on rollback. Asserted here: the decisions and the
transaction intent — what is recorded, in which order, and that the use case
completes exactly once. The SQL behavior lives in
``test_org_theme_versions.py``.
"""

import copy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.organizations.service import OrganizationThemeService
from app.modules.organizations.theme_ports import (
    OrganizationTheme,
    ThemeVersionRecord,
)
from app.shared.exceptions import AppException

ORG_A, ORG_B, MISSING_ORG, ADMIN = (UUID(int=i) for i in range(1, 5))
NOW = datetime(2026, 10, 2, 15, tzinfo=UTC)


def theme(label: str) -> dict:
    return {"meta": {"tenant": label}, "modes": {"light": {}, "dark": {}}}


class FakeThemeStore:
    """Tenant-scoped in-memory port mirroring the adapter's integrity rules."""

    def __init__(self, themes: dict[UUID, dict | None]) -> None:
        self.themes = dict(themes)
        self.updated_by: dict[UUID, UUID | None] = {}
        self.versions: list[ThemeVersionRecord] = []
        self.calls: list[str] = []
        self.fail_on: str | None = None
        self._next_id = 1

    def _current(self, organization_id: UUID) -> OrganizationTheme | None:
        if organization_id not in self.themes:
            return None
        return OrganizationTheme(theme=self.themes[organization_id])

    def _of(self, organization_id: UUID) -> list[ThemeVersionRecord]:
        return [v for v in self.versions if v.organization_id == organization_id]

    async def find_theme(self, organization_id: UUID) -> OrganizationTheme | None:
        self.calls.append("find_theme")
        return self._current(organization_id)

    async def lock_theme(self, organization_id: UUID) -> OrganizationTheme | None:
        self.calls.append("lock_theme")
        return self._current(organization_id)

    async def replace_theme(
        self, organization_id: UUID, theme: dict | None, *, actor_id: UUID | None
    ) -> None:
        self.calls.append("replace_theme")
        if organization_id not in self.themes:
            raise LookupError("organization not found")
        self.themes[organization_id] = theme
        self.updated_by[organization_id] = actor_id

    async def has_versions(self, organization_id: UUID) -> bool:
        self.calls.append("has_versions")
        return bool(self._of(organization_id))

    async def add_version(
        self,
        organization_id: UUID,
        theme: dict,
        *,
        user_id: UUID | None,
        user_name: str | None,
        initial_capture: bool = False,
        source_version_id: int | None = None,
    ) -> ThemeVersionRecord:
        self.calls.append("add_version")
        if self.fail_on == "add_version":
            raise RuntimeError("flush failed")
        own = self._of(organization_id)
        if source_version_id is not None and all(
            v.id != source_version_id for v in own
        ):
            raise ValueError("source version belongs to another organization")
        if initial_capture and any(v.initial_capture for v in own):
            raise ValueError("initial capture already recorded")
        record = ThemeVersionRecord(
            id=self._next_id,
            organization_id=organization_id,
            theme=copy.deepcopy(theme),
            user_id=user_id,
            user_name=user_name,
            applied_at=NOW + timedelta(seconds=self._next_id),
            initial_capture=initial_capture,
            source_version_id=source_version_id,
        )
        self._next_id += 1
        self.versions.append(record)
        return record

    async def find_version(
        self, organization_id: UUID, version_id: int
    ) -> ThemeVersionRecord | None:
        self.calls.append("find_version")
        return next((v for v in self._of(organization_id) if v.id == version_id), None)

    async def list_versions(
        self, organization_id: UUID, *, before: int | None, limit: int
    ) -> list[ThemeVersionRecord]:
        self.calls.append("list_versions")
        rows = sorted(self._of(organization_id), key=lambda v: v.id, reverse=True)
        if before is not None:
            rows = [v for v in rows if v.id < before]
        return rows[:limit]


class FakeTransaction:
    """Transaction double: a rollback discards every uncommitted write."""

    def __init__(self, themes: FakeThemeStore) -> None:
        self.themes = themes
        self.commits = 0
        self.rollbacks = 0
        self._committed = self._snapshot()

    def _snapshot(self) -> tuple[dict, list]:
        return copy.deepcopy(self.themes.themes), list(self.themes.versions)

    async def commit(self) -> None:
        self.commits += 1
        self._committed = self._snapshot()

    async def rollback(self) -> None:
        self.rollbacks += 1
        themes, versions = self._committed
        self.themes.themes = copy.deepcopy(themes)
        self.themes.versions = list(versions)


def build(themes: dict[UUID, dict | None] | None = None):
    store = FakeThemeStore({ORG_A: None, ORG_B: None} if themes is None else themes)
    transaction = FakeTransaction(store)
    return OrganizationThemeService(transaction), store, transaction


async def apply(service, label: str, organization_id: UUID = ORG_A, **kwargs):
    return await service.set_theme(
        organization_id, theme(label), actor_id=ADMIN, actor_name="Ana Admin", **kwargs
    )


# ---------------------------------------------------------------------------
# Aplicar: guarda el tema y registra la versión en una sola transacción
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_stores_the_theme_and_records_one_version():
    service, store, transaction = build()

    applied = await apply(service, "v1")

    assert applied.theme == theme("v1")
    assert store.themes[ORG_A] == theme("v1")
    assert store.updated_by[ORG_A] == ADMIN
    assert [v.theme for v in store.versions] == [theme("v1")]
    assert applied.version.id == store.versions[0].id
    assert applied.version.user_id == ADMIN
    assert applied.version.user_name == "Ana Admin"
    assert applied.version.applied_at == store.versions[0].applied_at
    assert applied.version.initial_capture is False
    assert applied.version.source_version_id is None
    assert (transaction.commits, transaction.rollbacks) == (1, 0)


@pytest.mark.asyncio
async def test_apply_locks_the_theme_before_reading_or_writing():
    service, store, _ = build()

    await apply(service, "v1")

    assert store.calls[0] == "lock_theme"
    assert "find_theme" not in store.calls


@pytest.mark.asyncio
async def test_apply_captures_the_previous_theme_when_there_is_no_history():
    service, store, transaction = build({ORG_A: theme("legacy")})

    applied = await apply(service, "v1")

    capture, version = store.versions
    assert capture.theme == theme("legacy")
    assert capture.initial_capture is True
    assert (capture.user_id, capture.user_name) == (None, None)
    assert capture.source_version_id is None
    assert capture.id < version.id == applied.version.id
    assert version.initial_capture is False
    assert transaction.commits == 1


@pytest.mark.asyncio
async def test_apply_captures_the_previous_theme_only_once():
    service, store, _ = build({ORG_A: theme("legacy")})

    await apply(service, "v1")
    await apply(service, "v2")

    assert [v.initial_capture for v in store.versions] == [True, False, False]


@pytest.mark.asyncio
async def test_apply_without_previous_theme_records_no_initial_capture():
    service, store, _ = build()

    await apply(service, "v1")

    assert [v.initial_capture for v in store.versions] == [False]


@pytest.mark.asyncio
async def test_apply_from_a_restored_version_records_its_source():
    service, store, _ = build()
    first = await apply(service, "v1")
    await apply(service, "v2")

    restored = await apply(service, "v1", source_version_id=first.version.id)

    assert restored.version.source_version_id == first.version.id
    assert store.themes[ORG_A] == theme("v1")
    assert len(store.versions) == 3


@pytest.mark.asyncio
async def test_apply_rejects_a_source_version_of_another_organization():
    service, store, transaction = build()
    foreign = await apply(service, "b1", ORG_B)

    for source_version_id in (foreign.version.id, 999):
        with pytest.raises(AppException) as error:
            await apply(service, "a1", source_version_id=source_version_id)
        assert error.value.status_code == 422
        assert error.value.code == "theme_source_version_invalid"

    assert store.themes[ORG_A] is None
    assert [v.organization_id for v in store.versions] == [ORG_B]
    assert (transaction.commits, transaction.rollbacks) == (1, 2)


@pytest.mark.asyncio
async def test_apply_to_a_missing_organization_returns_404():
    service, store, transaction = build()

    with pytest.raises(AppException) as error:
        await apply(service, "v1", MISSING_ORG)

    assert error.value.status_code == 404
    assert error.value.code == "organization_not_found"
    assert store.versions == []
    assert transaction.commits == 0


@pytest.mark.asyncio
async def test_apply_rolls_back_everything_when_recording_the_version_fails():
    service, store, transaction = build({ORG_A: theme("legacy")})
    store.fail_on = "add_version"

    with pytest.raises(RuntimeError):
        await apply(service, "v1")

    assert store.themes[ORG_A] == theme("legacy")
    assert store.versions == []
    assert (transaction.commits, transaction.rollbacks) == (0, 1)


# ---------------------------------------------------------------------------
# Historial: 20 por página, de la más nueva a la más vieja, por cursor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_versions_pages_newest_first_by_cursor():
    service, store, _ = build()
    for index in range(45):
        await apply(service, f"v{index}")
    newest_first = [v.id for v in reversed(store.versions)]

    first = await service.list_versions(ORG_A, before=None)
    second = await service.list_versions(ORG_A, before=first.next)
    third = await service.list_versions(ORG_A, before=second.next)

    assert [v.id for v in first.versions] == newest_first[:20]
    assert first.next == newest_first[19]
    assert [v.id for v in second.versions] == newest_first[20:40]
    assert second.next == newest_first[39]
    assert [v.id for v in third.versions] == newest_first[40:]
    assert third.next is None


@pytest.mark.asyncio
async def test_list_versions_has_no_next_when_the_page_is_exactly_full():
    service, _, _ = build()
    for index in range(20):
        await apply(service, f"v{index}")

    page = await service.list_versions(ORG_A, before=None)

    assert len(page.versions) == 20
    assert page.next is None


@pytest.mark.asyncio
async def test_list_versions_is_scoped_to_the_organization():
    service, _, transaction = build()
    await apply(service, "a1")
    await apply(service, "b1", ORG_B)
    commits = transaction.commits

    page_a = await service.list_versions(ORG_A, before=None)
    page_b = await service.list_versions(ORG_B, before=None)

    assert len(page_a.versions) == len(page_b.versions) == 1
    assert page_a.versions[0].id != page_b.versions[0].id
    assert transaction.commits == commits


@pytest.mark.asyncio
async def test_get_version_returns_metadata_and_theme():
    service, _, _ = build()
    applied = await apply(service, "v1")

    detail = await service.get_version(ORG_A, applied.version.id)

    assert detail.id == applied.version.id
    assert detail.theme == theme("v1")
    assert detail.user_name == "Ana Admin"


@pytest.mark.asyncio
async def test_get_version_of_another_organization_returns_404():
    service, _, _ = build()
    foreign = await apply(service, "b1", ORG_B)

    for version_id in (foreign.version.id, 999):
        with pytest.raises(AppException) as error:
            await service.get_version(ORG_A, version_id)
        assert error.value.status_code == 404
        assert error.value.code == "theme_version_not_found"


# ---------------------------------------------------------------------------
# Restablecer: vuelve al tema por defecto y el historial se conserva
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_clears_the_theme_and_keeps_the_history():
    service, store, transaction = build()
    await apply(service, "v1")

    await service.reset_theme(ORG_A, actor_id=ADMIN)

    assert store.themes[ORG_A] is None
    assert await service.get_theme(ORG_A) is None
    assert [v.theme for v in store.versions] == [theme("v1")]
    assert (transaction.commits, transaction.rollbacks) == (2, 0)


@pytest.mark.asyncio
async def test_reset_captures_a_theme_that_has_no_history():
    service, store, _ = build({ORG_A: theme("legacy")})

    await service.reset_theme(ORG_A, actor_id=ADMIN)

    assert store.themes[ORG_A] is None
    assert [(v.theme, v.initial_capture) for v in store.versions] == [
        (theme("legacy"), True)
    ]


@pytest.mark.asyncio
async def test_reset_without_theme_records_nothing():
    service, store, transaction = build()

    await service.reset_theme(ORG_A, actor_id=ADMIN)

    assert store.versions == []
    assert transaction.commits == 1
