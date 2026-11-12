"""Read-only post-execution invariant checks (design.md D8, I1-I8).

``collect_invariants`` never writes; ``runner.py`` gates its ``commit()`` on
``all(result.passed for result in ...)`` (D2).
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.maintenance.report import InvariantResult
from app.modules.attachments.models import Attachment
from app.modules.boards.models import Board, BoardColumn
from app.modules.comments.models import TaskComment
from app.modules.connectors.models import ConnectedAccount, Connector
from app.modules.intake.models import IntakeSettings
from app.modules.notifications.models import Notification
from app.modules.org_role_templates.models import (
    OrgRoleTemplate,
    OrgRoleTemplateInstantiation,
)
from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.reminders.models import Reminder
from app.modules.tasks.models import Task
from app.modules.users.models import User
from app.shared.enums import Methodology, ProjectKind

# (code, project_kind, methodology, parent_code) — mirrors bootstrap.py._HIERARCHY.
_EXPECTED_HIERARCHY: dict[str, tuple[ProjectKind, Methodology, str | None]] = {
    "SDM": (ProjectKind.area, Methodology.planner, None),
    "SEG": (ProjectKind.proyecto, Methodology.custom, "SDM"),
    "PAN": (ProjectKind.proyecto, Methodology.kanban, "SDM"),
}
_PROTECTED_CONNECTOR_PROVIDERS = ("jira", "google", "microsoft365")


async def collect_invariants(session: AsyncSession) -> tuple[InvariantResult, ...]:
    """Run every I1-I8 check and return the full, unfiltered result set."""

    return (
        await _i1_admin_exists(session),
        await _i2_solercia_not_acme(session),
        await _i3_hierarchy_shape(session),
        await _i4_seguridad_columns(session),
        await _i5_intake_default_project(session),
        await _i6_no_orphans(session),
        await _i7_templates_intact(session),
        await _i8_no_fake_connector(session),
    )


async def _i1_admin_exists(session: AsyncSession) -> InvariantResult:
    """spec.md's Requirement literally says "existe admin@solercia.com" —
    NOT "es el único usuario" (design.md's summary-table shorthand only)."""

    admin_id = await session.scalar(select(User.id).where(User.email == "admin@solercia.com"))
    passed = admin_id is not None
    return InvariantResult("I1", "Existe admin@solercia.com", passed, f"admin_id={admin_id}")


async def _i2_solercia_not_acme(session: AsyncSession) -> InvariantResult:
    result = await session.execute(select(Organization.name))
    names = {row[0] for row in result.all()}
    passed = "Solercia" in names and "Acme Consultores" not in names
    return InvariantResult(
        "I2",
        "Existe la organización Solercia; no existe Acme Consultores",
        passed,
        f"organizaciones: {sorted(names)}",
    )


async def _i3_hierarchy_shape(session: AsyncSession) -> InvariantResult:
    result = await session.execute(
        select(
            Project.code, Project.id, Project.project_kind, Project.methodology,
            Project.parent_project_id,
        ).where(Project.code.in_(_EXPECTED_HIERARCHY))
    )
    rows = {row.code: row for row in result.all()}
    sdm_id = rows["SDM"].id if "SDM" in rows else None
    problems = []
    for code, (kind, methodology, parent_code) in _EXPECTED_HIERARCHY.items():
        row = rows.get(code)
        if row is None:
            problems.append(f"{code} no existe")
            continue
        expected_parent = sdm_id if parent_code == "SDM" else None
        if row.project_kind != kind or row.methodology != methodology:
            problems.append(f"{code} kind/methodology inesperados")
        if row.parent_project_id != expected_parent:
            problems.append(f"{code} padre inesperado")
    return InvariantResult(
        "I3",
        "SDM/SEG/PAN existen con code, project_kind, methodology y padre esperados",
        not problems,
        "; ".join(problems) or "ok",
    )


async def _i4_seguridad_columns(session: AsyncSession) -> InvariantResult:
    description = "SEGURIDAD tiene 7 columnas, Completada la última"
    seguridad_id = await session.scalar(select(Project.id).where(Project.code == "SEG"))
    if seguridad_id is None:
        return InvariantResult("I4", description, False, "SEGURIDAD no existe")

    board_id = await session.scalar(
        select(Board.id).where(Board.project_id == seguridad_id, Board.is_active.is_(True))
    )
    if board_id is None:
        return InvariantResult("I4", description, False, "SEGURIDAD sin board")

    result = await session.execute(
        select(BoardColumn.status_key)
        .where(BoardColumn.board_id == board_id, BoardColumn.is_active.is_(True))
        .order_by(BoardColumn.order.asc())
    )
    keys = [row[0] for row in result.all()]
    passed = len(keys) == 7 and keys[-1] == "Completada"
    return InvariantResult(
        "I4",
        "SEGURIDAD tiene exactamente 7 columnas y Completada tiene el order mayor",
        passed,
        f"columnas ({len(keys)}): {keys}",
    )


async def _i5_intake_default_project(session: AsyncSession) -> InvariantResult:
    seguridad_id = await session.scalar(select(Project.id).where(Project.code == "SEG"))
    default_ids = {
        row[0] for row in (await session.execute(select(IntakeSettings.default_project_id))).all()
    }
    tareas_outlook = await session.scalar(
        select(func.count()).select_from(Project).where(Project.name == "Tareas Outlook")
    )
    passed = seguridad_id is not None and seguridad_id in default_ids and tareas_outlook == 0
    return InvariantResult(
        "I5",
        "intake_settings.default_project_id apunta a SEGURIDAD; no existe Tareas Outlook",
        passed,
        f"default_project_ids={default_ids}, Tareas Outlook={tareas_outlook}",
    )


async def _i6_no_orphans(session: AsyncSession) -> InvariantResult:
    task_ids = select(Task.id)
    valid_attachment_targets = task_ids.union(select(TaskComment.id))

    orphan_attachments = await session.scalar(
        select(func.count())
        .select_from(Attachment)
        .where(Attachment.target_id.not_in(valid_attachment_targets))
    )
    orphan_notifications = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.target_id.is_not(None), Notification.target_id.not_in(task_ids))
    )
    orphan_reminders = await session.scalar(
        select(func.count())
        .select_from(Reminder)
        .where(Reminder.task_id.is_not(None), Reminder.task_id.not_in(task_ids))
    )
    passed = orphan_attachments == 0 and orphan_notifications == 0 and orphan_reminders == 0
    return InvariantResult(
        "I6",
        "Cero huérfanos en attachments/notifications/reminders",
        passed,
        f"attachments={orphan_attachments}, notifications={orphan_notifications}, "
        f"reminders={orphan_reminders}",
    )


async def _i7_templates_intact(session: AsyncSession) -> InvariantResult:
    result = await session.execute(
        select(OrgRoleTemplate).where(OrgRoleTemplate.organization_id.is_(None))
    )
    templates = result.scalars().all()
    instantiations = await session.scalar(
        select(func.count()).select_from(OrgRoleTemplateInstantiation)
    )
    passed = (
        len(templates) == 5
        and all(template.is_system for template in templates)
        and instantiations == 0
    )
    return InvariantResult(
        "I7",
        "Las 5 org_role_templates de sistema están intactas; 0 instantiations",
        passed,
        f"{len(templates)} plantillas, {instantiations} instantiations",
    )


async def _i8_no_fake_connector(session: AsyncSession) -> InvariantResult:
    fake_count = await session.scalar(
        select(func.count()).select_from(Connector).where(Connector.provider == "fake")
    )
    providers = {
        row[0]
        for row in (await session.execute(select(Connector.provider).distinct())).all()
    }
    accounts_for_real_providers = (
        await session.scalar(
            select(func.count())
            .select_from(ConnectedAccount)
            .join(Connector, Connector.id == ConnectedAccount.connector_id)
            .where(Connector.provider.in_(_PROTECTED_CONNECTOR_PROVIDERS))
        )
        or 0
    )
    passed = (
        fake_count == 0
        and set(_PROTECTED_CONNECTOR_PROVIDERS).issubset(providers)
        and accounts_for_real_providers > 0
    )
    return InvariantResult(
        "I8",
        "0 conectores fake; jira/google/microsoft365 presentes con sus cuentas",
        passed,
        f"fake={fake_count}, providers={sorted(providers)}, "
        f"cuentas_reales={accounts_for_real_providers}",
    )
