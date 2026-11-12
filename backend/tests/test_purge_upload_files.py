"""Cierra el hallazgo CRITICAL #1 de ``verify-report.md`` (2026-08-26):
``delete_referenced_files`` (``scripts/purge_demo_data.py:131-148``) no tenía
ninguna prueba que la invocara de extremo a extremo. Las pruebas existentes en
``test_purge_cli.py`` cubren solo ``is_within_upload_dir`` de forma aislada.

Estas pruebas invocan la función REAL contra un ``UPLOAD_DIR`` real en
``tmp_path`` — sin base de datos (design.md, capa "CLI (sin BD)") — y cubren
el escenario de ``spec.md`` "--purge-upload-files borra solo los archivos
referenciados", incluyendo el caso de traversal de la Threat Matrix ("Borrado
en sistema de ficheros"): una referencia que apunta fuera de ``UPLOAD_DIR``
jamás debe borrarse.
"""

from scripts.purge_demo_data import delete_referenced_files


def test_delete_referenced_files_borra_solo_los_referenciados_y_preserva_el_resto(
    tmp_path,
) -> None:
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    referenciados = [upload_dir / f"referenciado-{i}.pdf" for i in range(3)]
    for archivo in referenciados:
        archivo.write_bytes(b"contenido demo")

    no_referenciado = upload_dir / "no-referenciado.pdf"
    no_referenciado.write_bytes(b"no debe tocarse")

    # Threat Matrix "Borrado en sistema de ficheros": traversal fuera de
    # UPLOAD_DIR jamas se toca, aunque venga en stored_names.
    fuera_de_uploads = tmp_path / "fuera-de-uploads.pdf"
    fuera_de_uploads.write_bytes(b"externo, jamas se toca")

    stored_names = [archivo.name for archivo in referenciados] + ["../fuera-de-uploads.pdf"]

    deleted, warnings = delete_referenced_files(upload_dir, stored_names)

    assert deleted == 3
    assert warnings == 1
    for archivo in referenciados:
        assert not archivo.exists()
    assert no_referenciado.exists()
    assert fuera_de_uploads.exists()


def test_delete_referenced_files_cuenta_un_fichero_ya_ausente_como_advertencia(
    tmp_path,
) -> None:
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    deleted, warnings = delete_referenced_files(upload_dir, ["nunca-existio.pdf"])

    assert deleted == 0
    assert warnings == 1
