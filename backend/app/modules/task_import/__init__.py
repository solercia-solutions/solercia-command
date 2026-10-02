"""Pure source inventory/checklist preview foundation, not an import service.

Use build_manifest(entries) for all supplied byte/unavailable entries and
parse_checklist(snapshot, ChecklistProfile(), ParseLimits()) for a preview.
No filesystem, persistence, network, settings or application bootstrap access.
Consumers must resolve scope, responsibility, identity and approval separately.
"""
