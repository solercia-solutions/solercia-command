"""Tests for audit exposure (R5, G4, G5) across the 11 audited models.

Three layers of coverage:
1. Structural — every audited ORM model declares nullable ``created_by``/
   ``updated_by`` columns (confirms ``AuditMixin`` is mixed into all 11,
   including the global ``Menu`` and the model-only ``Organization`` — gate
   #4: the criterion is "has SoftDeleteMixin", NOT "tenant-scoped").
2. Structural — every Read schema with an HTTP surface exposes both fields
   as optional (``None`` default), so a NULL row never fails serialization.
3. Integration — a representative endpoint (tasks) exposes ``created_by``/
   ``updated_by`` as `null` in the JSON body for a row written directly via
   the session (simulating ``db_init.py``'s unaudited seed writes — gate #5,
   accepted behavior, no backfill).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.alert_rules.models import AlertRule
from app.modules.alert_rules.schemas import AlertRuleRead
from app.modules.attachments.models import Attachment
from app.modules.attachments.schemas import AttachmentRead
from app.modules.auth.schemas import UserRead
from app.modules.comments.models import TaskComment
from app.modules.comments.schemas import CommentRead
from app.modules.dependencies.models import Dependency
from app.modules.dependencies.schemas import DependencyRead
from app.modules.menus.models import Menu
from app.modules.menus.schemas import MenuRead
from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectRead
from app.modules.roles.models import Role
from app.modules.roles.schemas import RoleRead
from app.modules.sprints.models import Sprint
from app.modules.sprints.schemas import SprintRead
from app.modules.tasks.models import Task
from app.modules.tasks.schemas import TaskRead
from app.modules.users.models import User
from tests.conftest import skip_no_db

# The 11 models with SoftDeleteMixin (design.md gate #4 — mechanical
# criterion, NOT "tenant-scoped": Menu (global) and Organization (no
# service) are both included).
AUDITED_MODELS = [
    AlertRule,
    Attachment,
    TaskComment,
    Dependency,
    Menu,
    Organization,
    Project,
    Role,
    Sprint,
    Task,
    User,
]

# Read schemas with an HTTP surface. Organization has no router/service (only
# the startup seed writes it directly) so it has no Read schema to check here
# — covered instead by the model-level assertion above.
AUDITED_READ_SCHEMAS = [
    AlertRuleRead,
    AttachmentRead,
    CommentRead,
    DependencyRead,
    MenuRead,
    ProjectRead,
    RoleRead,
    SprintRead,
    TaskRead,
    UserRead,
]


@pytest.mark.parametrize("model", AUDITED_MODELS, ids=lambda m: m.__name__)
def test_audited_model_declares_nullable_created_by_and_updated_by(model) -> None:
    """Every one of the 11 SoftDeleteMixin models has the audit columns."""

    mapper = inspect(model)
    for column_name in ("created_by", "updated_by"):
        column = mapper.columns[column_name]
        assert column.nullable is True
        foreign_keys = list(column.foreign_keys)
        assert len(foreign_keys) == 1
        assert foreign_keys[0].target_fullname == "users.id"
        assert foreign_keys[0].ondelete == "SET NULL"


@pytest.mark.parametrize("schema", AUDITED_READ_SCHEMAS, ids=lambda s: s.__name__)
def test_audited_read_schema_exposes_optional_created_by_and_updated_by(
    schema,
) -> None:
    """Every Read schema with an HTTP surface exposes both fields as optional."""

    fields = schema.model_fields
    for field_name in ("created_by", "updated_by"):
        assert field_name in fields, f"{schema.__name__} is missing {field_name}"
        assert fields[field_name].default is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_detail_exposes_null_audit_fields_for_a_seed_style_row(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A row written directly (no service, no actor — like db_init.py) exposes nulls.

    Mirrors the seed write pattern (``session.add(...)`` without going
    through a service), then reads it back via the real HTTP detail
    endpoint, proving the API never fails to serialize NULL audit columns.
    """

    from app.modules.organizations.models import OrganizationMember
    from app.modules.projects.models import Project as ProjectModel
    from app.shared.enums import MemberRole
    from app.shared.security import create_access_token, hash_password

    org = Organization(name="Seed-style Org", slug="seed-style-org-audit")
    session.add(org)
    await session.flush()

    reader = User(
        email="seed-reader@example.com",
        primer_nombre="Seed",
        primer_apellido="Reader",
        hashed_password=hash_password("Reader123*"),
    )
    session.add(reader)
    await session.flush()
    session.add(
        OrganizationMember(organization_id=org.id, user_id=reader.id, role=MemberRole.member)
    )
    await session.flush()
    token = create_access_token(str(reader.id))

    project = ProjectModel(
        organization_id=org.id, name="Seed Project", methodology="kanban", code="SDP"
    )
    session.add(project)
    await session.flush()

    seed_task = Task(
        project_id=project.id,
        title="Seed-style task (no actor)",
        task_type="task",
        status="todo",
        # created_by/updated_by intentionally omitted — same as db_init.py.
    )
    session.add(seed_task)
    await session.flush()
    assert seed_task.created_by is None
    assert seed_task.updated_by is None

    response = await client.get(
        f"/tasks/{seed_task.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["created_by"] is None
    assert data["updated_by"] is None
