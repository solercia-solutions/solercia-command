"""Offline metadata SQL compilation and migration AST checks, NOT DB proof."""

import ast
from pathlib import Path

from sqlalchemy import CheckConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateColumn

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
CHECK = "NOT is_system OR (code IS NOT NULL AND code = 'GENERALES' AND methodology = 'custom' AND status = 'active' AND is_active AND deleted_at IS NULL)"


def test_model_column_and_constraint_compile():
    from app.modules.projects.models import Project

    column = Project.__table__.c.is_system
    sql = str(CreateColumn(column).compile(dialect=postgresql.dialect()))
    assert "BOOLEAN DEFAULT false NOT NULL" in sql
    assert column.default.arg is False
    constraints = [c for c in Project.__table__.constraints if isinstance(c, CheckConstraint)]
    assert any(c.name == "ck_projects_system_shape" and str(c.sqltext) == CHECK for c in constraints)


def test_migration_is_additive_and_matches_model():
    path = VERSIONS / "0026_add_project_is_system.py"
    tree = ast.parse(path.read_text())
    assignments = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
                   if isinstance(n, ast.Assign)}
    assert assignments["revision"] == "0026"
    assert assignments["down_revision"] == "0025"
    upgrade = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade")
    calls = [n.value for n in upgrade.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
    assert [c.func.attr for c in calls] == ["add_column", "create_check_constraint"]
    assert ast.literal_eval(calls[0].args[0]) == "projects"
    column = calls[0].args[1]
    assert ast.literal_eval(column.args[0]) == "is_system"
    assert column.args[1].func.attr == "Boolean"
    kw = {k.arg: k.value for k in column.keywords}
    assert ast.literal_eval(kw["nullable"]) is False
    assert kw["server_default"].func.attr == "false"
    assert [ast.literal_eval(arg) for arg in calls[1].args] == ["ck_projects_system_shape", "projects", CHECK]


def test_single_revision_head():
    revisions, parents = set(), set()
    for path in VERSIONS.glob("*.py"):
        tree = ast.parse(path.read_text())
        values = {}
        for node in tree.body:
            target = node.target if isinstance(node, ast.AnnAssign) else (
                node.targets[0] if isinstance(node, ast.Assign) else None
            )
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                values[target.id] = ast.literal_eval(node.value)
        revisions.add(values["revision"])
        parent = values["down_revision"]
        parents.update(parent if isinstance(parent, tuple) else [parent])
    # Still exactly ONE head; 0027 (institutional plans, change 45a) now sits on top of 0026.
    assert len(revisions - parents) == 1
    assert "0026" in revisions
