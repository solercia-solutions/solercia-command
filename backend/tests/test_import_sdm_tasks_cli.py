"""C01: the CLI keeps its flags, messages and exit codes on top of the sync service."""

import os

import pytest

from scripts import import_sdm_tasks as cli
from tests.conftest import skip_no_db
from tests.test_task_import_checklist_apply import HEADER, ROW


def _csv(tmp_path):
    path = tmp_path / "c.csv"
    path.write_text(f"{HEADER}\n{ROW}\n", encoding="utf-8")
    return path


def test_missing_checklist_is_a_usage_error(tmp_path, capsys):
    code = cli.main(["--organization-slug", "x", "--checklist", str(tmp_path / "no.csv"),
                     "--report", str(tmp_path / "r"), "--database-url",
                     "postgresql+asyncpg://u:p@127.0.0.1:1/none"])
    assert code == cli.EXIT_USAGE_ERROR
    assert "No existe el checklist" in capsys.readouterr().err


def test_apply_requires_matching_expect_database(tmp_path, capsys):
    code = cli.main(["--organization-slug", "x", "--checklist", str(_csv(tmp_path)),
                     "--report", str(tmp_path / "r"), "--apply", "--database-url",
                     "postgresql+asyncpg://u:p@127.0.0.1:1/none"])
    assert code == cli.EXIT_USAGE_ERROR
    assert "--expect-database debe ser exactamente el destino" in capsys.readouterr().err


def test_unreadable_source_exits_with_source_error(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_bytes(b"")
    code = cli.main(["--organization-slug", "x", "--checklist", str(bad),
                     "--report", str(tmp_path / "r"), "--database-url",
                     "postgresql+asyncpg://u:p@127.0.0.1:1/none"])
    assert code == cli.EXIT_SOURCE_ERROR
    assert "Fuente no válida" in capsys.readouterr().err


@skip_no_db
@pytest.mark.asyncio(loop_scope="session")
async def test_unknown_organization_exits_3_in_read_only_dry_run(engine, tmp_path, capsys):
    # ``engine`` builds the schema in the disposable test database first.
    args = cli.build_parser().parse_args(
        ["--organization-slug", "no-existe-c01", "--checklist", str(_csv(tmp_path)),
         "--report", str(tmp_path / "r"), "--database-url", os.environ["TEST_DATABASE_URL"]]
    )
    code = await cli.run(args)
    assert code == cli.EXIT_ORGANIZATION_NOT_FOUND
    assert "no existe o está inactiva" in capsys.readouterr().err
    assert not (tmp_path / "r.json").exists()


def test_report_helpers_remain_importable_from_the_cli():
    assert callable(cli.build_report) and callable(cli.render_markdown)
    assert callable(cli.write_report) and callable(cli.load_plan)


@pytest.mark.parametrize("flag", ["--namespace", "--tareas-root", "--assignee-email",
                                  "--actor-email", "--update-existing", "--expect-database"])
def test_flags_are_unchanged(flag):
    assert flag in cli.build_parser().format_help()
