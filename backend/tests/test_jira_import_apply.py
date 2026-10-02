"""Jira organization feed against real PostgreSQL: dry-run writes nothing,
apply creates the tree, a second apply creates 0 rows, existing roles stay."""

import uuid

import pytest
from sqlalchemy import func, select

from app.integrations.ports import CredentialKind
from app.modules.auth.models import FederatedIdentity
from app.modules.boards.models import Board, BoardColumn
from app.modules.connectors.models import ConnectedAccount, Connector
from app.modules.jira_import.apply import SessionJiraFeedUow, run_feed
from app.modules.jira_import.mapper import build_feed_plan
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.projects.models import Project
from app.modules.roles.models import Role, UserRole
from app.modules.sprints.models import Sprint
from app.modules.tasks.models import Task
from app.modules.users.models import User
from app.shared.enums import (
    AccountStatus,
    ConnectorStatus,
    MemberRole,
)
from tests.conftest import skip_no_db
from tests.jira_feed_fixtures import make_snapshot

_COUNTED = (
    User,
    FederatedIdentity,
    OrganizationMember,
    UserRole,
    Project,
    Board,
    BoardColumn,
    Sprint,
    Task,
)


async def _counts(session) -> dict[str, int]:
    return {
        model.__tablename__: (
            await session.execute(select(func.count()).select_from(model))
        ).scalar_one()
        for model in _COUNTED
    }


async def _seed_org(session):
    org = Organization(name="Entidad", slug=f"entidad-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.flush()
    owner = User(
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
        primer_nombre="Dueño",
        primer_apellido="Org",
        hashed_password="x",
    )
    session.add(owner)
    await session.flush()
    session.add(OrganizationMember(organization_id=org.id, user_id=owner.id, role=MemberRole.admin))
    admin_role = Role(organization_id=org.id, code="ADMIN", name="Administrador")
    member_role = Role(organization_id=org.id, code="MEMBER", name="Miembro")
    session.add_all([admin_role, member_role])
    await session.flush()
    session.add(UserRole(user_id=owner.id, role_id=admin_role.id))
    connector = Connector(
        organization_id=org.id,
        provider="jira",
        status=ConnectorStatus.active,
        credential_kind=CredentialKind.api_token,
    )
    session.add(connector)
    await session.flush()
    # The owner IS Jira account "acc-ana" (connected account of the org).
    session.add(
        ConnectedAccount(
            organization_id=org.id,
            connector_id=connector.id,
            user_id=owner.id,
            external_account_id="jira-acc-ana",
            status=AccountStatus.active,
        )
    )
    await session.flush()
    return org, owner, member_role


@skip_no_db
@pytest.mark.asyncio(loop_scope="session")
async def test_dry_run_apply_and_idempotent_reapply(session):
    org, owner, member_role = await _seed_org(session)
    plan = build_feed_plan(make_snapshot())
    uow = SessionJiraFeedUow(session)

    simulated = await run_feed(uow, org, plan, write=False)
    # run_feed rolled back the (savepoint) transaction: reseed the org.
    org, owner, member_role = await _seed_org(session)
    before = await _counts(session)
    assert simulated.tasks.created == 7 and simulated.projects.created == 2

    first = await run_feed(uow, org, plan, write=True)
    after_first = await _counts(session)
    assert first.users.created == 2  # acc-ana is the owner (connected account)
    assert first.projects.created == 2
    assert first.sprints.created == 2
    assert first.tasks.created == 7
    assert first.parents_linked == 3
    assert after_first["tasks"] - before["tasks"] == 7

    second = await run_feed(uow, org, plan, write=True)
    assert await _counts(session) == after_first
    assert second.users.created == second.tasks.created == second.projects.created == 0
    assert second.tasks.updated == second.sprints.updated == 0
    assert second.parents_linked == 0

    owner_member = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id, OrganizationMember.user_id == owner.id
            )
        )
    ).scalar_one()
    assert owner_member.role == MemberRole.admin
    owner_roles = (
        (await session.execute(select(UserRole.role_id).where(UserRole.user_id == owner.id)))
        .scalars()
        .all()
    )
    assert member_role.id not in owner_roles

    alfa = (
        await session.execute(
            select(Project).where(Project.organization_id == org.id, Project.code == "ALFA")
        )
    ).scalar_one()
    assert alfa.methodology.value == "scrum" and alfa.lead_user_id == owner.id
    assert alfa.task_counter == 5
    tasks = {
        t.external_key: t
        for t in (await session.execute(select(Task).where(Task.project_id == alfa.id))).scalars()
    }
    assert tasks["ALFA-3"].task_number == 3 and tasks["ALFA-3"].source == "jira"
    assert tasks["ALFA-2"].parent_task_id == tasks["ALFA-1"].id
    assert tasks["ALFA-1"].parent_task_id == tasks["ALFA-0"].id
    assert tasks["ALFA-2"].completed_at is not None and tasks["ALFA-1"].completed_at is None
    assert tasks["ALFA-2"].assignee_id == owner.id

    carla = (
        await session.execute(
            select(User)
            .join(FederatedIdentity, FederatedIdentity.user_id == User.id)
            .where(FederatedIdentity.subject == "557058:abc-def")
        )
    ).scalar_one()
    assert carla.hashed_password is None
    assert carla.email.endswith("@idartes.jira.example.org")
