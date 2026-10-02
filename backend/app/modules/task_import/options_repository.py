"""Read-only, bounded picker projections in the caller's trusted tenant/session.

No ORM hydration, writes, locks, transaction completion or provisioning. Counts
and pages share predicates, not a repeatable-read snapshot: concurrent changes
can affect separate SELECTs. The organization gate is specific to options; it
neither changes shared authentication nor claims review checks this lifecycle.
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.projects.models import Project
from app.modules.users.models import User
from app.shared.enums import Methodology, ProjectStatus

from .schemas import OptionItem, OptionMeta, OptionPage, OptionsData, OptionsQuery


def _literal_contains(value: str) -> str:
    return '%' + value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


class OptionsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _execute(self, statement):
        return await self._session.execute(statement.execution_options(autoflush=False))

    async def _page(self, source, identifier, label, predicates, page, size) -> OptionPage:
        count = select(func.count()).select_from(source).where(*predicates)
        total = (await self._execute(count)).scalar_one()
        statement = (select(identifier.label('id'), label).select_from(source)
                     .where(*predicates).order_by(label, identifier)
                     .limit(size).offset((page - 1) * size))
        rows = (await self._execute(statement)).all()
        return OptionPage(items=[OptionItem(id=str(key), label=name) for key, name in rows],
                          meta=OptionMeta(page=page, size=size, total=total))

    async def load(self, tenant_id: str, query: OptionsQuery) -> OptionsData | None:
        """Return eligible labels and the canonical default, never create a default.

        Ordinary projects follow review facts' active/nondeleted eligibility,
        regardless of lifecycle status or methodology. Members use USER IDs;
        OrganizationMember has no active/deleted fields in the actual schema.
        """
        tenant = UUID(tenant_id)
        org = Organization.__table__.c
        gate = select(org.id).where(org.id == tenant, org.is_active.is_(True),
                                    org.deleted_at.is_(None))
        if (await self._execute(gate)).scalar_one_or_none() is None:
            return None

        project = Project.__table__.c
        project_label = project.name.label('label')
        project_predicates = [project.organization_id == tenant,
                              project.is_active.is_(True), project.deleted_at.is_(None)]
        if query.projects_q:
            project_predicates.append(project_label.ilike(_literal_contains(query.projects_q), escape='\\'))
        projects = await self._page(Project.__table__, project.id, project_label,
                                    project_predicates, query.projects_page, query.projects_size)

        member = OrganizationMember.__table__.c
        user = User.__table__.c
        # Same SQL short-name convention as User.full_name, using scalar columns
        # to avoid ORM relationship loaders or selecting private user fields.
        member_label = func.trim(func.concat(func.coalesce(user.primer_nombre, ''), ' ',
                                            func.coalesce(user.primer_apellido, ''))).label('label')
        member_predicates = [member.organization_id == tenant,
                             user.is_active.is_(True), user.deleted_at.is_(None)]
        if query.members_q:
            member_predicates.append(member_label.ilike(_literal_contains(query.members_q), escape='\\'))
        source = OrganizationMember.__table__.join(User.__table__, user.id == member.user_id)
        members = await self._page(source, user.id, member_label, member_predicates,
                                   query.members_page, query.members_size)

        default_statement = select(project.id, project.name).where(
            project.organization_id == tenant, project.is_system.is_(True),
            project.code == 'GENERALES', project.is_active.is_(True),
            project.deleted_at.is_(None), project.status == ProjectStatus.active,
            project.methodology == Methodology.custom,
        ).limit(1)
        default = (await self._execute(default_statement)).first()
        return OptionsData(projects=projects, members=members,
                           default_project=None if default is None else
                           OptionItem(id=str(default[0]), label=default[1]))
