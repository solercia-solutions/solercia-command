"""Explicit definition of the demo-data purge scope (design.md Decision D3).

``DemoScope`` is literal data, never a heuristic: every field is resolved by
an exact name/email/provider match against the live database, verified
2026-08-26 against the real ``solercia`` database. It carries no I/O — the
SQL that resolves it into concrete row ids lives in ``repository.py``.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoScope:
    """The literal set of demo rows the purge targets.

    ``organization_names`` closes an entire demo tenant (e.g. "Acme
    Consultores"). ``project_names`` additionally matches demo projects
    seeded INSIDE "Solercia" by ``db_init._ensure_demo_projects`` — resolved
    by name, never ``code`` (those rows have none). Both are closed under
    the full descendant subtree of ``parent_project_id`` (``SET NULL``,
    never cascades) by ``MaintenanceRepository.resolve_demo_scope``.
    """

    organization_names: tuple[str, ...] = ("Acme Consultores",)
    user_emails: tuple[str, ...] = (
        "ana@solercia.com",
        "carlos@solercia.com",
        "diana@solercia.com",
        "verify-smoke-11@solercia.com",
    )
    project_names: tuple[str, ...] = (
        "Plataforma Web",
        "Soporte Técnico",
        "Mejoras Internas 2026",
        "ACTUALIZACIÓN DE DOCUMENTOS",
        "Desarrollo",
    )
    # Projects reachable ONLY via an org-role-template instantiation ledger
    # row (the OAP-TI tree) also close the scope, even when not listed above.
    include_template_instantiations: bool = True
    connector_providers: tuple[str, ...] = ("fake",)
    asset_names: tuple[str, ...] = ("Verify Test Asset",)

    # Corrección 2 (Fase 5, decisión #3682): template-instantiated trees
    # under the PROTECTED organization are demo too — the real OAP-TI tree
    # was instantiated under "Solercia" in production, never under
    # "Acme Consultores". Its soft-deleted duplicate, orphaned from the
    # ``org_role_template_instantiations`` ledger once reconciliation
    # retargets it at a NEWER active tree (see that model's docstring),
    # closes by ``deleted_at IS NOT NULL`` inside this same organization.
    # Explicit scope rule, never a heuristic.
    soft_deleted_scope_organization_names: tuple[str, ...] = ("Solercia",)
    # Defense in depth for the OAP-TI umbrella specifically: both hyphen
    # variants (U+2011 non-breaking — the one the seeder actually uses —
    # and the plain ASCII U+002D) close the scope by NAME alone, even when
    # no ledger row exists for it.
    template_root_name_aliases: tuple[str, ...] = ("OAP‑TI", "OAP-TI")

    # Never touched by the purge — read by the fail-closed guards.
    protected_admin_email: str = "admin@solercia.com"
    protected_organization_names: tuple[str, ...] = ("Solercia",)
    protected_project_codes: tuple[str, ...] = ("SDM", "SEG", "PAN")
    protected_connector_providers: tuple[str, ...] = (
        "jira",
        "google",
        "microsoft365",
    )
