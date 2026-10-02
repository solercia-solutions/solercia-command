"""Synthetic domain fixtures only: no database, HTTP or source files."""
from dataclasses import FrozenInstanceError, replace
from datetime import date
from hashlib import sha256

import pytest

from app.modules.task_import.contracts import (
    ChecklistPreview, ChecklistProfile, ChecklistRow, Issue, PreviewCounts,
    RawCell, SourceSnapshot, ParseLimits,
)
from app.modules.task_import.review_plan import (
    DateCorrection, ReviewDecision, ReviewInput, RowKey, TrustedContext, build_review_plan,
)
from app.modules.task_import.review_ports import ProjectFacts


class Facts:
    def active_project(self, tenant_id, project_id):
        if (tenant_id, project_id) == ('tenant', 'project'):
            return ProjectFacts('tenant', 'project', frozenset({'PENDIENTE'}))
        return None

    def active_member(self, tenant_id, user_id):
        return (tenant_id, user_id) == ('tenant', 'member')


def fixture():
    source = SourceSnapshot('synthetic.csv', b'synthetic immutable source')
    digest = sha256(source.data).hexdigest()
    profile = ChecklistProfile()
    headers = tuple(RawCell(str(i), h, 'text') for i, h in enumerate(profile.headers))
    values = ('T1', 'PENDIENTE', '', '', '', 'Synthetic', '', 'later', 'requester', '', '')
    row = ChecklistRow(2, None, 2, 2,
                       tuple(RawCell(str(i), v, 'text') for i, v in enumerate(values)),
                       'T1', None, 'rejected', (Issue('invalid_date', row=2, column=8),))
    blank = ChecklistRow(3, None, 3, 3, (), None, None, 'blank_skipped', ())
    preview = ChecklistPreview(source, digest, profile, headers, (row, blank),
                               complete=True, counts=PreviewCounts(0, 1, 1))
    decision = ReviewDecision(RowKey(digest, None, 2), 'include', 'project', 'member',
                              corrections=(DateCorrection('due_date', '2026-09-12'),))
    request = ReviewInput(digest, 'v1', (decision,))
    return preview, request


def run(preview, request, facts=None):
    return build_review_plan(preview, 'v1', request, TrustedContext('tenant', 'actor'), facts or Facts())


def test_explicit_date_correction_preserves_source_and_complete_accounting():
    preview, request = fixture()
    plan = run(preview, request)
    assert plan.status == 'validated_for_review'
    assert plan.source is preview.source
    assert plan.counts == preview.counts
    assert len(plan.rows) == 2
    row = plan.rows[0]
    assert row.original is preview.rows[0]
    assert row.original.cells[7].value == 'later'
    assert row.effective_due_date.isoformat() == '2026-09-12'
    assert (row.project_id, row.assignee_id) == ('project', 'member')
    assert plan.context.actor_id == 'actor'
    with pytest.raises(FrozenInstanceError):
        row.project_id = 'other'


@pytest.mark.parametrize('value', [None, '2026-02-28'])
def test_explicit_no_date_is_a_decision(value):
    preview, request = fixture()
    decision = replace(request.decisions[0], corrections=(DateCorrection('due_date', value),))
    plan = run(preview, replace(request, decisions=(decision,)))
    assert plan.status == 'validated_for_review'
    assert plan.rows[0].corrections == decision.corrections
    assert (plan.rows[0].effective_due_date is None) == (value is None)


@pytest.mark.parametrize('change', ['absent', 'bad_date', 'unsupported', 'duplicate_correction',
                                     'missing', 'duplicate', 'forged', 'hash', 'profile',
                                     'project', 'member', 'status', 'incomplete', 'counts',
                                     'snapshot', 'other_issue', 'blank_decision'])
def test_invalid_or_incomplete_review_blocks(change):
    preview, request = fixture()
    decision = request.decisions[0]
    if change == 'absent':
        decision = replace(decision, corrections=())
    elif change in ('bad_date', 'unsupported', 'duplicate_correction'):
        corrections = {'bad_date': (DateCorrection('due_date', '2026-02-30'),),
                       'unsupported': (DateCorrection('title', 'replacement'),),
                       'duplicate_correction': decision.corrections * 2}[change]
        decision = replace(decision, corrections=corrections)
    elif change in ('project', 'member'):
        decision = replace(decision, **{'project_id' if change == 'project' else 'assignee_id': 'foreign-or-inactive'})
    elif change == 'forged':
        decision = replace(decision, key=replace(decision.key, row=999))
    elif change == 'blank_decision':
        decision = replace(decision, key=replace(decision.key, row=3))
    request = replace(request, decisions=(decision,))
    if change == 'missing':
        request = replace(request, decisions=())
    elif change == 'duplicate':
        request = replace(request, decisions=(decision, decision))
    elif change == 'hash':
        request = replace(request, source_hash='stale')
    elif change == 'profile':
        request = replace(request, profile_version='stale')
    elif change == 'incomplete':
        preview = replace(preview, complete=False)
    elif change == 'counts':
        preview = replace(preview, counts=PreviewCounts(0, 0, 0))
    elif change == 'snapshot':
        preview = replace(preview, source=replace(preview.source, data=b'changed'))
    elif change == 'other_issue':
        row = replace(preview.rows[0], issues=preview.rows[0].issues + (Issue('formula'),))
        preview = replace(preview, rows=(row, preview.rows[1]))
    elif change == 'status':
        cells = list(preview.rows[0].cells)
        cells[1] = replace(cells[1], value='UNKNOWN')
        preview = replace(preview, rows=(replace(preview.rows[0], cells=tuple(cells)), preview.rows[1]))
    plan = run(preview, request)
    assert plan.status == 'blocked'
    assert plan.issues or any(row.issues for row in plan.rows)
    assert len(plan.rows) == len(preview.rows)


def test_exclusion_is_explicit_and_retains_reason_and_original():
    preview, request = fixture()
    decision = ReviewDecision(request.decisions[0].key, 'exclude', reason='Needs separate review')
    plan = run(preview, replace(request, decisions=(decision,)))
    assert plan.status == 'validated_for_review'
    assert plan.rows[0].action == 'exclude'
    assert plan.rows[0].reason == decision.reason
    assert plan.rows[0].original == preview.rows[0]
    assert run(preview, replace(request, decisions=(replace(decision, reason=' '),))).status == 'blocked'


def test_candidate_needs_explicit_assignee_without_date_correction():
    preview, request = fixture()
    original = replace(preview.rows[0], due_date=date(2026, 9, 1),
                       disposition='candidate', issues=())
    preview = replace(preview, rows=(original, preview.rows[1]), counts=PreviewCounts(1, 1, 0))
    decision = replace(request.decisions[0], corrections=())
    plan = run(preview, replace(request, decisions=(decision,)))
    assert plan.status == 'validated_for_review'
    assert plan.rows[0].effective_due_date == original.due_date
    assert run(preview, replace(request, decisions=(replace(decision, assignee_id=None),))).status == 'blocked'


def test_rows_on_different_sheets_require_separate_decisions():
    preview, request = fixture()
    another = replace(preview.rows[0], sheet='Other')
    preview = replace(preview, rows=preview.rows + (another,), counts=PreviewCounts(0, 1, 2))
    assert run(preview, request).status == 'blocked'
    decision = replace(request.decisions[0], key=replace(request.decisions[0].key, sheet='Other'))
    plan = run(preview, replace(request, decisions=request.decisions + (decision,)))
    assert plan.status == 'validated_for_review'
    assert len(plan.rows) == 3


@pytest.mark.parametrize('value', ['', '20260912', '2026-9-12', '2026-09-12T00:00:00', 'Recurrente'])
def test_correction_accepts_only_canonical_iso_or_explicit_none(value):
    preview, request = fixture()
    decision = replace(request.decisions[0], corrections=(DateCorrection('due_date', value),))
    assert run(preview, replace(request, decisions=(decision,))).status == 'blocked'


def test_parser_aggregated_row_issue_is_resolved_only_by_explicit_decision():
    from app.modules.task_import.checklist_parser import parse_checklist
    profile = ChecklistProfile()
    content = ';'.join(profile.headers) + '\nT1;PENDIENTE;;;;Synthetic;;later;requester;;\n'
    preview = parse_checklist(SourceSnapshot('synthetic.csv', content.encode()), profile, ParseLimits())
    assert preview.complete and preview.counts.rejected == 1
    assert preview.issues == preview.rows[0].issues
    decision = ReviewDecision(RowKey(preview.sha256, None, 2), 'include', 'project', 'member',
                              corrections=(DateCorrection('due_date', None),))
    request = ReviewInput(preview.sha256, 'v1', (decision,))
    assert run(preview, request).status == 'validated_for_review'
    assert run(preview, replace(request, decisions=(replace(decision, corrections=()),))).status == 'blocked'
    assert run(replace(preview, issues=preview.issues + (Issue('missing_header', row=1),)), request).status == 'blocked'


def test_port_receives_only_trusted_tenant_and_foreign_facts_block():
    class ForeignFacts(Facts):
        def active_project(self, tenant_id, project_id):
            assert tenant_id == 'tenant'
            return ProjectFacts('foreign', project_id, frozenset({'PENDIENTE'}))
    assert run(*fixture(), facts=ForeignFacts()).status == 'blocked'
