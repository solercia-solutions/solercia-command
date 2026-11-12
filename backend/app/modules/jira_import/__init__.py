"""jira_import module (change 18-adapter-jira, specs/jira-import/spec.md).

Read-only REST surface that triggers a Jira issue import (API vía or
uploaded CSV/XLSX) for a connector of the caller's organization. Has NO
``repository`` — it never writes: ``router -> service`` reuses
``connectors``' repository to read the conector and decrypt credentials,
and delegates extraction/normalization to the registered ``jira`` adapter
(specs/jira-import/spec.md "Frontera solo-lectura estricta"). The
conversion to ``Task``/persistence of imported issues is change 22 —
out of scope here.
"""
