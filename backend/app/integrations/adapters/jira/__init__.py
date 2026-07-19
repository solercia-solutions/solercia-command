"""Jira adapter package (change 18-adapter-jira, specs/jira-import/spec.md).

Read-only issue import over Jira Cloud's REST API v3 and CSV/XLSX export;
``credential_kind=api_token`` (email + API token, HTTP Basic). Registration
(``register_adapter(JiraAdapter())``) is wired in Lote 6 — until then this
package only exposes its DTOs/mappings/normalizer/parser/client modules.
"""
