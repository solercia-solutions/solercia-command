"""RED tests for the Jira adapter's file parser (change 18-adapter-jira,
specs/jira-import/spec.md "Import por archivo CSV/Excel con las mismas
garantías que la API" + Threat Matrix "Bomba de descompresión XLSX").
Operates entirely over fixtures in ``tests/fixtures/jira/`` — zero real
file-system tricks, zero network.
"""

from pathlib import Path

import pytest

from app.config import Settings

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "jira"


def _read(name: str) -> bytes:
    return (_FIXTURES_DIR / name).read_bytes()


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


class TestParseCsv:
    def test_bom_is_stripped_and_repeated_labels_columns_merge_into_a_list(
        self,
    ) -> None:
        from app.integrations.adapters.jira.file_parser import parse_csv

        rows = parse_csv(_read("export.csv"))

        assert len(rows) == 1
        row = rows[0]
        assert row["Issue key"] == "PROJ-42"
        assert row["Labels"] == ["backend", "auth"]
        assert row["Sprint"] == ["Sprint 3"]
        assert row["Story Points"] == "5"

    def test_missing_issue_key_column_raises_a_controlled_error_with_no_rows(
        self,
    ) -> None:
        from app.integrations.adapters.jira import errors
        from app.integrations.adapters.jira.file_parser import parse_csv

        with pytest.raises(errors.JiraFileFormatError) as exc_info:
            parse_csv(_read("export_malformado.csv"))

        assert "Issue key" in exc_info.value.missing_columns

    def test_row_count_over_the_limit_is_rejected_without_finishing_the_read(
        self,
    ) -> None:
        from app.integrations.adapters.jira import errors
        from app.integrations.adapters.jira.file_parser import parse_csv

        header = "Issue key,Summary\n"
        rows = "\n".join(f"PROJ-{i},Fila de relleno" for i in range(5)) + "\n"
        content = (header + rows).encode("utf-8")

        with pytest.raises(errors.JiraFileTooLarge):
            parse_csv(content, settings=_settings(JIRA_FILE_MAX_ROWS=2))


class TestParseXlsx:
    def test_parses_the_same_issue_as_the_csv_export(self) -> None:
        from app.integrations.adapters.jira.file_parser import parse_csv, parse_xlsx

        csv_rows = parse_csv(_read("export.csv"))
        xlsx_rows = parse_xlsx(_read("export.xlsx"))

        assert len(xlsx_rows) == 1
        assert xlsx_rows[0]["Issue key"] == csv_rows[0]["Issue key"]
        assert xlsx_rows[0]["Labels"] == csv_rows[0]["Labels"]
        assert xlsx_rows[0]["Sprint"] == csv_rows[0]["Sprint"]

    def test_bomb_file_over_the_row_limit_is_rejected_without_processing(self) -> None:
        """Threat Matrix: `export_bomba.xlsx` has 50.001 data rows — the
        guard fires and the file is never processed."""

        from app.integrations.adapters.jira import errors
        from app.integrations.adapters.jira.file_parser import parse_xlsx

        with pytest.raises(errors.JiraFileTooLarge):
            parse_xlsx(_read("export_bomba.xlsx"))

    def test_cell_count_over_the_limit_is_also_rejected(self) -> None:
        """The guard fires on EITHER threshold — cells, not just rows."""

        from app.integrations.adapters.jira import errors
        from app.integrations.adapters.jira.file_parser import parse_xlsx

        with pytest.raises(errors.JiraFileTooLarge):
            parse_xlsx(_read("export_bomba.xlsx"), settings=_settings(JIRA_FILE_MAX_CELLS=10))


class TestParseFile:
    def test_dispatches_by_extension(self) -> None:
        from app.integrations.adapters.jira.file_parser import parse_file

        csv_rows = parse_file(_read("export.csv"), "export.csv")
        xlsx_rows = parse_file(_read("export.xlsx"), "EXPORT.XLSX")

        assert csv_rows[0]["Issue key"] == xlsx_rows[0]["Issue key"]

    def test_unsupported_extension_raises_a_controlled_error(self) -> None:
        from app.integrations.adapters.jira import errors
        from app.integrations.adapters.jira.file_parser import parse_file

        with pytest.raises(errors.JiraFileFormatError):
            parse_file(b"key,value", "export.txt")
