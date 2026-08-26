"""Tests for ``scripts.purge_demo_data`` (Fase 4 — Rebanada 3).

Most tests here run WITHOUT a database (mandatory inclusion #3, design.md
D7): argument parsing, backup verification and upload-path containment are
pure functions; the exit-code translation is exercised by replacing
``run_maintenance`` with a fake — the CLI never touches a real Postgres in
those cases. The single exception is
``test_dry_run_real_via_subprocess_registra_el_orm_completo`` (Corrección 1,
Fase 5): it launches the CLI as a FRESH ``python -m`` subprocess against
``TEST_DATABASE_URL``, exactly like the orchestrator's manual dry-run.
A same-process call would NOT reproduce the defect — the ``engine`` fixture
in ``conftest.py`` already imports ``app.db_init`` (to build the schema),
which pre-registers every ORM model for the rest of the pytest process
before this module's own tests run, masking the incomplete-registry bug
that a real standalone invocation hits.
"""

import os
import subprocess
import sys
from pathlib import Path

from app.maintenance.report import (
    ConnectedAccountRisk,
    InvariantResult,
    MaintenanceReport,
    PurgeGuardError,
)
from scripts.purge_demo_data import (
    build_parser,
    is_within_upload_dir,
    main,
    redact_database_url,
)
from tests.conftest import skip_no_db

_FAKE_DATABASE_URL = "postgresql+asyncpg://app:app@127.0.0.1:5434/solercia"


def _report(*, mode: str, all_pass: bool) -> MaintenanceReport:
    return MaintenanceReport(
        mode=mode,
        inventory=(),
        planned=(),
        deleted=(),
        bootstrap=("SDMUJER (SDM) creado",),
        invariants=(
            InvariantResult("I1", "Existe admin@solercia.com", all_pass, "ok"),
            InvariantResult("I4", "SEGURIDAD tiene 7 columnas", True, "ok"),
        ),
    )


# -- 4.1: argument parsing and backup verification (no run_maintenance) -----


def test_dry_run_es_el_modo_por_defecto() -> None:
    parser = build_parser()

    assert parser.parse_args([]).execute is False
    # Triangulate: the opposite input flips the same flag.
    assert parser.parse_args(["--execute"]).execute is True


def test_execute_sin_backup_file_falla_con_codigo_1() -> None:
    assert main(["--execute", "--database-url", _FAKE_DATABASE_URL]) == 1


def test_backup_file_inexistente_o_vacio_falla_con_codigo_1(tmp_path) -> None:
    missing = tmp_path / "no-existe.sql"
    assert (
        main(
            [
                "--execute",
                "--database-url",
                _FAKE_DATABASE_URL,
                "--backup-file",
                str(missing),
            ]
        )
        == 1
    )

    # Triangulate: an existing-but-empty file fails the same way.
    empty = tmp_path / "vacio.sql"
    empty.write_bytes(b"")
    assert (
        main(
            [
                "--execute",
                "--database-url",
                _FAKE_DATABASE_URL,
                "--backup-file",
                str(empty),
            ]
        )
        == 1
    )


def test_purge_upload_files_esta_apagado_por_defecto() -> None:
    parser = build_parser()

    assert parser.parse_args([]).purge_upload_files is False
    # Triangulate: the flag actually flips when passed.
    assert parser.parse_args(["--purge-upload-files"]).purge_upload_files is True


def test_purge_upload_files_rechaza_rutas_fuera_de_upload_dir(tmp_path) -> None:
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    assert is_within_upload_dir(upload_dir, "../../etc/passwd") is None
    assert is_within_upload_dir(upload_dir, "/etc/passwd") is None

    # Triangulate: a stored_name that DOES stay inside resolves to a real path.
    resolved = is_within_upload_dir(upload_dir, "abc123.pdf")
    assert resolved == (upload_dir / "abc123.pdf").resolve()


def test_la_url_de_base_de_datos_se_redacta_en_la_salida() -> None:
    redacted = redact_database_url("postgresql+asyncpg://app:supersecreto@127.0.0.1:5434/solercia")

    assert "supersecreto" not in redacted
    assert "app:***@127.0.0.1:5434/solercia" in redacted

    # Triangulate: a different user/host still redacts only the password.
    other = redact_database_url("postgresql+asyncpg://admin:otraClave@postgres:5432/solercia")
    assert "otraClave" not in other
    assert "admin:***@postgres:5432/solercia" in other


# -- 4.2: translation of use-case outcomes to exit codes, via fakes --------


def test_dry_run_exitoso_retorna_codigo_0(monkeypatch) -> None:
    async def fake_run_maintenance(session, *, execute, scope=None):
        return _report(mode="dry-run", all_pass=True)

    monkeypatch.setattr("scripts.purge_demo_data.run_maintenance", fake_run_maintenance)

    assert main(["--database-url", _FAKE_DATABASE_URL]) == 0


def test_execute_exitoso_con_invariantes_en_pass_retorna_codigo_0(monkeypatch, tmp_path) -> None:
    async def fake_run_maintenance(session, *, execute, scope=None):
        return _report(mode="execute", all_pass=True)

    monkeypatch.setattr("scripts.purge_demo_data.run_maintenance", fake_run_maintenance)

    backup = tmp_path / "respaldo.sql"
    backup.write_text("-- pg_dump --")

    assert (
        main(
            [
                "--execute",
                "--database-url",
                _FAKE_DATABASE_URL,
                "--backup-file",
                str(backup),
            ]
        )
        == 0
    )


def test_guarda_de_seguridad_retorna_codigo_2_sin_escribir(monkeypatch, tmp_path) -> None:
    async def fake_run_maintenance(session, *, execute, scope=None):
        raise PurgeGuardError(
            "cuenta conectada de un usuario demo",
            risks=(ConnectedAccountRisk("jira", "Cuenta Jira de Carlos", "carlos@solercia.com"),),
        )

    monkeypatch.setattr("scripts.purge_demo_data.run_maintenance", fake_run_maintenance)

    backup = tmp_path / "respaldo.sql"
    backup.write_text("-- pg_dump --")

    assert (
        main(
            [
                "--execute",
                "--database-url",
                _FAKE_DATABASE_URL,
                "--backup-file",
                str(backup),
            ]
        )
        == 2
    )


def test_invariante_en_fail_retorna_codigo_3(monkeypatch) -> None:
    async def fake_run_maintenance(session, *, execute, scope=None):
        return _report(mode="dry-run", all_pass=False)

    monkeypatch.setattr("scripts.purge_demo_data.run_maintenance", fake_run_maintenance)

    assert main(["--database-url", _FAKE_DATABASE_URL]) == 3


def test_excepcion_inesperada_retorna_codigo_4(monkeypatch) -> None:
    async def fake_run_maintenance(session, *, execute, scope=None):
        raise RuntimeError("fallo inesperado de conexión")

    monkeypatch.setattr("scripts.purge_demo_data.run_maintenance", fake_run_maintenance)

    assert main(["--database-url", _FAKE_DATABASE_URL]) == 4


# -- Corrección 1 (Fase 5): registro ORM real, sin fakes, subprocess real ---


@skip_no_db
def test_dry_run_real_via_subprocess_registra_el_orm_completo() -> None:
    """Antes de la corrección, el módulo solo importaba ``app.config`` y
    ``app.maintenance.*``; el registro de SQLAlchemy quedaba incompleto y el
    primer query fallaba con ``NameError: name 'Role' is not defined`` al
    resolver ``relationship("Role", order_by="Role.name")`` en ``User``,
    saliendo con código 4 (EXIT_UNEXPECTED_ERROR) SIN imprimir ningún
    reporte. Este test invoca la MISMA CLI real, en un subproceso limpio, en
    modo dry-run (sin ``--execute``) contra ``TEST_DATABASE_URL`` —
    ``solercia_test`` está vacía (sin seed), así que las invariantes I1-I5/
    I8 fallan legítimamente (código 3); lo que prueba el registro ORM
    completo es que la consulta real corrió de principio a fin y produjo el
    reporte, en vez de reventar antes con la excepción del mapper."""

    backend_dir = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.purge_demo_data",
            "--database-url",
            os.environ["TEST_DATABASE_URL"],
        ],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode in (0, 3), result.stderr
    assert "ERROR INESPERADO" not in result.stderr
    assert "Modo: dry-run" in result.stdout
