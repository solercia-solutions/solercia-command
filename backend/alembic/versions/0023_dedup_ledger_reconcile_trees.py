"""dedup_ledger_reconcile_trees

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-20 00:00:01.000000

Change 27-plantillas-idempotentes (design.md "Migration / Rollout", Decisión
3/4). Reconciles the historical OAP-TI duplicates the bug in
``OrgRoleTemplateRepository.ledger_for`` produced (the old idempotency key
included ``lead_user_id`` — reinstantiating the SAME template with a
DIFFERENT responsible found no ledger match and recreated the entire tree)
and swaps the ledger's ``UNIQUE`` constraint to the new, lead-less key —
ALL in one transaction, so the new constraint is only created once every
pre-existing duplicate is already collapsed (Decisión 3, "acoplarlos evita
un estado intermedio con árboles huérfanos sin ledger").

``reconcile_duplicate_trees(connection)`` is the reusable, idempotent data
step:

1. Detects ``(organization_id, template_id)`` pairs whose ledger has more
   than one distinct ``project_id`` for the SAME ``node_id`` — the real
   duplicate shape (two historical ``instantiate()`` calls with different
   leads, each producing its OWN self-consistent tree keyed by that lead).
2. For each pair, treats every distinct ``lead_user_id`` present as one
   candidate tree, resolves its ROOT project (the node whose
   ``parent_node_id IS NULL``) and scores it by
   ``(active task count in its subtree, created_at)`` — more tasks wins;
   ties on task count fall back to the OLDER root (Decisión 4).
3. An EXACT tie (same task count AND same ``created_at``) leaves the group
   completely untouched and emits a ``UserWarning`` — "empate sin criterio
   determinista se reporta, no se adivina" (spec scenario), never guessed.
4. Otherwise, every LOSING tree's tasks are reassigned (by matching
   ``node_id``, never by name) to the WINNING tree's project for that same
   node, the losing project is soft-deleted, and its ledger row is removed
   — collapsing the ledger to one row per node, pointing to the survivor
   with the survivor's ``lead_user_id``.
5. ``project_kind`` is backfilled on every project still linked through the
   ledger, using the SAME node-with-children rule the generator applies
   going forward (Fase 4 of this change) — so pre-existing trees are never
   left with a stale ``project_kind`` after the cleanup.

Every step is idempotent: re-running it against already-reconciled data
finds no duplicate groups and the backfill recomputes the same values —
verified directly (bypassing ``alembic.command``, which never re-applies an
already-applied revision) via ``AsyncConnection.run_sync`` in
``test_migration_dedup_ledger_reconcile_trees.py``.

``downgrade()`` restores ``UNIQUE(organization_id, template_id, node_id,
lead_user_id)`` — reversible, zero ledger rows lost. The task reassignment
and soft-delete are **NOT** reverted (Decisión 3, "downgrade honesto"): they
are not trivially reversible data transformations, and reverting them is a
manual operation (backup + bitácora) outside the scope of this migration.
"""

import warnings
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "uq_org_role_template_instantiation"


def _duplicate_org_template_pairs(connection: sa.engine.Connection) -> list[tuple]:
    """Return distinct ``(organization_id, template_id)`` pairs that have at
    least one ``node_id`` with more than one distinct ``project_id`` in the
    ledger — the signature of a historical duplicate tree."""

    rows = connection.execute(
        sa.text(
            """
            SELECT DISTINCT organization_id, template_id
            FROM (
                SELECT organization_id, template_id, node_id
                FROM org_role_template_instantiations
                GROUP BY organization_id, template_id, node_id
                HAVING COUNT(DISTINCT project_id) > 1
            ) AS duplicated_nodes
            """
        )
    ).fetchall()
    return [(row.organization_id, row.template_id) for row in rows]


def _subtree_active_task_count(connection: sa.engine.Connection, project_id) -> int:
    """Count active tasks in ``project_id``'s own subtree (itself plus every
    descendant reachable via ``parent_project_id``) — degenerates to the
    project's own task count when it has no children."""

    row = connection.execute(
        sa.text(
            """
            WITH RECURSIVE subtree AS (
                SELECT id FROM projects WHERE id = :project_id
                UNION ALL
                SELECT child.id
                FROM projects child
                JOIN subtree ON child.parent_project_id = subtree.id
            )
            SELECT COUNT(*) AS n
            FROM tasks
            WHERE project_id IN (SELECT id FROM subtree) AND is_active = true
            """
        ),
        {"project_id": project_id},
    ).fetchone()
    return int(row.n)


def _root_project_for_lead(
    connection: sa.engine.Connection, organization_id, template_id, lead_user_id
):
    """Return ``(project_id, created_at)`` of the ROOT node's project for
    one candidate tree (``lead_user_id``), or ``None`` if this lead has no
    ledger row for the template's root node."""

    return connection.execute(
        sa.text(
            """
            SELECT p.id AS project_id, p.created_at AS created_at
            FROM org_role_template_instantiations orti
            JOIN org_role_template_nodes n ON n.id = orti.node_id
            JOIN projects p ON p.id = orti.project_id
            WHERE orti.organization_id = :organization_id
              AND orti.template_id = :template_id
              AND orti.lead_user_id = :lead_user_id
              AND n.parent_node_id IS NULL
            """
        ),
        {
            "organization_id": organization_id,
            "template_id": template_id,
            "lead_user_id": lead_user_id,
        },
    ).fetchone()


def _ledger_map_for_lead(
    connection: sa.engine.Connection, organization_id, template_id, lead_user_id
) -> dict:
    """Return ``{node_id: project_id}`` of every ledger row for one
    candidate tree (``lead_user_id``)."""

    rows = connection.execute(
        sa.text(
            """
            SELECT node_id, project_id
            FROM org_role_template_instantiations
            WHERE organization_id = :organization_id
              AND template_id = :template_id
              AND lead_user_id = :lead_user_id
            """
        ),
        {
            "organization_id": organization_id,
            "template_id": template_id,
            "lead_user_id": lead_user_id,
        },
    ).fetchall()
    return {row.node_id: row.project_id for row in rows}


def _duplicated_node_ids_for_pair(
    connection: sa.engine.Connection, organization_id, template_id
) -> list:
    """Return every ``node_id`` of this pair that currently has more than
    one distinct ``project_id`` in the ledger."""

    rows = connection.execute(
        sa.text(
            """
            SELECT node_id
            FROM org_role_template_instantiations
            WHERE organization_id = :organization_id AND template_id = :template_id
            GROUP BY node_id
            HAVING COUNT(DISTINCT project_id) > 1
            """
        ),
        {"organization_id": organization_id, "template_id": template_id},
    ).fetchall()
    return [row.node_id for row in rows]


def _ledger_row_ids_for_nodes(
    connection: sa.engine.Connection, organization_id, template_id, node_ids: list
) -> list:
    """Return every ledger row ``id`` for ``node_ids`` of this pair — the
    rows an unresolved tie leaves duplicated, which the new UNIQUE index
    must EXCLUDE (Decisión 4, "ningún árbol se soft-elimina automáticamente"
    — the ledger keeps every row of a tied group untouched)."""

    if not node_ids:
        return []
    stmt = sa.text(
        """
        SELECT id
        FROM org_role_template_instantiations
        WHERE organization_id = :organization_id AND template_id = :template_id
          AND node_id IN :node_ids
        """
    ).bindparams(sa.bindparam("node_ids", expanding=True))
    rows = connection.execute(
        stmt,
        {
            "organization_id": organization_id,
            "template_id": template_id,
            "node_ids": node_ids,
        },
    ).fetchall()
    return [row.id for row in rows]


def _reconcile_pair(
    connection: sa.engine.Connection, organization_id, template_id
) -> list:
    """Resolve ONE ``(organization_id, template_id)`` duplicate group:
    pick a survivor tree, reassign the losers' tasks/ledger to it and
    soft-delete the losers — or leave the group untouched and warn on an
    exact tie (Decisión 4). Returns the ledger row ids that must be
    EXCLUDED from the new UNIQUE index (non-empty only on an unresolved
    tie); empty otherwise."""

    lead_rows = connection.execute(
        sa.text(
            """
            SELECT DISTINCT lead_user_id
            FROM org_role_template_instantiations
            WHERE organization_id = :organization_id AND template_id = :template_id
            """
        ),
        {"organization_id": organization_id, "template_id": template_id},
    ).fetchall()
    leads = [row.lead_user_id for row in lead_rows]
    if len(leads) < 2:
        return []

    candidates = []
    for lead_user_id in leads:
        root = _root_project_for_lead(
            connection, organization_id, template_id, lead_user_id
        )
        if root is None:
            continue
        candidates.append(
            {
                "lead_user_id": lead_user_id,
                "project_id": root.project_id,
                "created_at": root.created_at,
                "task_count": _subtree_active_task_count(connection, root.project_id),
            }
        )
    if len(candidates) < 2:
        return []

    max_tasks = max(c["task_count"] for c in candidates)
    top = [c for c in candidates if c["task_count"] == max_tasks]
    if len(top) > 1:
        min_created = min(c["created_at"] for c in top)
        top = [c for c in top if c["created_at"] == min_created]
    if len(top) > 1:
        # Empate exacto (misma antigüedad Y mismo conteo de tareas): NO se
        # toca el grupo — se reporta para resolución manual (design.md
        # Decisión 4, "empate sin criterio determinista"). The duplicated
        # rows stay in the ledger, so they must be EXCLUDED from the new
        # UNIQUE index below or its creation would fail outright.
        warnings.warn(
            "org_role_template_instantiations: empate sin criterio "
            f"determinista para organization_id={organization_id} "
            f"template_id={template_id} — grupo dejado sin reconciliar, "
            "requiere resolución manual.",
            stacklevel=2,
        )
        duplicated_node_ids = _duplicated_node_ids_for_pair(
            connection, organization_id, template_id
        )
        return _ledger_row_ids_for_nodes(
            connection, organization_id, template_id, duplicated_node_ids
        )

    winner_lead = top[0]["lead_user_id"]
    winner_map = _ledger_map_for_lead(
        connection, organization_id, template_id, winner_lead
    )

    for candidate in candidates:
        if candidate["lead_user_id"] == winner_lead:
            continue
        loser_map = _ledger_map_for_lead(
            connection, organization_id, template_id, candidate["lead_user_id"]
        )
        for node_id, loser_project_id in loser_map.items():
            winner_project_id = winner_map.get(node_id)
            if winner_project_id is None:
                # This node only exists in the losing tree (e.g. it was
                # already independently reconciled) — nothing to merge.
                continue

            connection.execute(
                sa.text(
                    "UPDATE tasks SET project_id = :winner WHERE project_id = :loser"
                ),
                {"winner": winner_project_id, "loser": loser_project_id},
            )
            connection.execute(
                sa.text(
                    "UPDATE projects SET is_active = false, deleted_at = now() "
                    "WHERE id = :loser"
                ),
                {"loser": loser_project_id},
            )
            connection.execute(
                sa.text(
                    """
                    DELETE FROM org_role_template_instantiations
                    WHERE organization_id = :organization_id
                      AND template_id = :template_id
                      AND node_id = :node_id
                      AND lead_user_id = :lead_user_id
                    """
                ),
                {
                    "organization_id": organization_id,
                    "template_id": template_id,
                    "node_id": node_id,
                    "lead_user_id": candidate["lead_user_id"],
                },
            )

    return []


def _backfill_project_kind(connection: sa.engine.Connection) -> None:
    """Assign ``project_kind`` by node topology (container -> ``area``, leaf
    -> ``proyecto``) to every project currently linked through the ledger —
    same criterion the generator applies going forward (Fase 4). Idempotent:
    recomputes the same value on every run."""

    connection.execute(
        sa.text(
            """
            UPDATE projects p
            SET project_kind = 'area'
            FROM org_role_template_instantiations orti
            WHERE p.id = orti.project_id
              AND EXISTS (
                  SELECT 1 FROM org_role_template_nodes child
                  WHERE child.parent_node_id = orti.node_id
              )
              AND p.project_kind != 'area'
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE projects p
            SET project_kind = 'proyecto'
            FROM org_role_template_instantiations orti
            WHERE p.id = orti.project_id
              AND NOT EXISTS (
                  SELECT 1 FROM org_role_template_nodes child
                  WHERE child.parent_node_id = orti.node_id
              )
              AND p.project_kind != 'proyecto'
            """
        )
    )


def reconcile_duplicate_trees(connection: sa.engine.Connection) -> list:
    """Dedup every duplicated ``(organization_id, template_id)`` ledger group
    and backfill ``project_kind`` — the full idempotent data step this
    migration's ``upgrade()`` runs BEFORE swapping the ``UNIQUE`` constraint.

    Returns the ledger row ids left duplicated by an unresolved exact tie
    (empty list when every group reconciled cleanly) — ``upgrade()`` uses
    this to EXCLUDE those rows from the new UNIQUE index instead of letting
    ``CREATE UNIQUE INDEX`` fail outright on a group it deliberately left
    untouched.
    """

    excluded_ledger_row_ids: list = []
    for organization_id, template_id in _duplicate_org_template_pairs(connection):
        excluded_ledger_row_ids.extend(
            _reconcile_pair(connection, organization_id, template_id)
        )

    _backfill_project_kind(connection)
    return excluded_ledger_row_ids


def upgrade() -> None:
    bind = op.get_bind()
    excluded_ledger_row_ids = reconcile_duplicate_trees(bind)

    op.drop_constraint(
        _CONSTRAINT_NAME, "org_role_template_instantiations", type_="unique"
    )
    if excluded_ledger_row_ids:
        # An unresolved tie left >1 row per (org, template, node) for some
        # group — enforce the new key everywhere EXCEPT those specific rows
        # (Decisión 4: they stay registered/duplicated until a human
        # resolves the tie manually; the constraint must not block the rest
        # of the table from being enforced in the meantime).
        excluded_literal = ", ".join(
            f"'{row_id}'" for row_id in excluded_ledger_row_ids
        )
        op.create_index(
            _CONSTRAINT_NAME,
            "org_role_template_instantiations",
            ["organization_id", "template_id", "node_id"],
            unique=True,
            postgresql_where=sa.text(f"id NOT IN ({excluded_literal})"),
        )
    else:
        op.create_unique_constraint(
            _CONSTRAINT_NAME,
            "org_role_template_instantiations",
            ["organization_id", "template_id", "node_id"],
        )


def downgrade() -> None:
    # Reversible: the constraint swap alone. The task reassignment and
    # soft-delete performed by reconcile_duplicate_trees() are a DELIBERATE
    # no-op here (Decisión 3, "downgrade honesto") — reverting them requires
    # a manual operation with a backup, outside this migration's scope.
    # ``IF EXISTS`` on both statements: upgrade() may have created either a
    # plain UNIQUE constraint or a partial UNIQUE index (tie case) under the
    # SAME name — only one of the two ever exists.
    op.execute(
        f"ALTER TABLE org_role_template_instantiations "
        f"DROP CONSTRAINT IF EXISTS {_CONSTRAINT_NAME}"
    )
    op.execute(f"DROP INDEX IF EXISTS {_CONSTRAINT_NAME}")
    op.create_unique_constraint(
        _CONSTRAINT_NAME,
        "org_role_template_instantiations",
        ["organization_id", "template_id", "node_id", "lead_user_id"],
    )
