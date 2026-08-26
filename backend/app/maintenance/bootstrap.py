"""Idempotent SDMUJER hierarchy bootstrap use case (design.md D2/D6).

``bootstrap_sdmujer`` NEVER calls ``commit()``/``rollback()`` — the caller
owns the transaction (``runner.py``, this same rebanada).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.maintenance.repository import MaintenanceRepository
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectCreate
from app.modules.projects.service import ProjectService
from app.shared.enums import Methodology, ProjectKind

# (code, name, project_kind, methodology, parent_code) — design.md D6.
_HIERARCHY: tuple[tuple[str, str, ProjectKind, Methodology, str | None], ...] = (
    ("SDM", "SDMUJER", ProjectKind.area, Methodology.planner, None),
    ("SEG", "SEGURIDAD", ProjectKind.proyecto, Methodology.custom, "SDM"),
    ("PAN", "PANDORA", ProjectKind.proyecto, Methodology.kanban, "SDM"),
)

# Literal — status_key equals name verbatim (D6); "Completada" LAST (order 6).
SEGURIDAD_COLUMNS: tuple[str, ...] = (
    "Sin iniciar",
    "En curso",
    "Diferida",
    "Recurrente",
    "Gestionada aparte",
    "Removida",
    "Completada",
)


async def bootstrap_sdmujer(
    session: AsyncSession, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None
) -> tuple[str, ...]:
    """Create — or reuse by ``code`` — SDMUJER > {SEGURIDAD, PANDORA},
    SEGURIDAD's 7 literal columns, and the intake default project (D6).

    A second call on an already-bootstrapped organization is a no-op: every
    project is found by ``code`` and reused, and ``ensure_board_columns``
    inserts nothing new.
    """

    repo = MaintenanceRepository(session)
    project_service = ProjectService(session)
    messages: list[str] = []
    projects_by_code: dict[str, Project] = {}

    for code, name, project_kind, methodology, parent_code in _HIERARCHY:
        existing = await repo.find_project_by_code(organization_id, code)
        if existing is not None:
            projects_by_code[code] = existing
            messages.append(f"{name} ({code}) ya existía — reutilizado")
            continue

        parent_project_id = projects_by_code[parent_code].id if parent_code else None
        # _create_project_unit is the ONLY way to force project_kind=area —
        # create_project always forces "proyecto" (projects/service.py:118).
        project = await project_service._create_project_unit(  # noqa: SLF001
            organization_id,
            ProjectCreate(
                name=name,
                methodology=methodology,
                code=code,
                parent_project_id=parent_project_id,
                project_kind=project_kind,
            ),
            actor_id=actor_id,
        )
        projects_by_code[code] = project
        messages.append(f"{name} ({code}) creado")

    seguridad = projects_by_code["SEG"]
    board_id = await repo.find_board_id_for_project(seguridad.id)
    if board_id is None:  # pragma: no cover - defensive, seed_board always runs
        raise RuntimeError("SEGURIDAD no tiene board activo tras _create_project_unit.")
    added = await repo.ensure_board_columns(board_id, SEGURIDAD_COLUMNS)
    messages.append(f"SEGURIDAD: {added} columna(s) nueva(s) de {len(SEGURIDAD_COLUMNS)}")

    await repo.upsert_intake_default_project(organization_id, seguridad.id)
    messages.append("intake_settings.default_project_id -> SEGURIDAD")

    return tuple(messages)
