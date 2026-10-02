"""Synthetic subprocess checks only; no application startup or database."""
from dataclasses import asdict
from datetime import date, datetime
from io import BytesIO
import json
import os
import signal
import subprocess
import sys
from threading import Event, Thread

import pytest

from app.modules.task_import.contracts import ChecklistProfile, ParseLimits, SourceSnapshot
from app.modules.task_import.preview_runner import PreviewRunner, PreviewRunnerError, RunnerLimits


def csv_bytes():
    return (';'.join(ChecklistProfile().headers) + '\n'
            'T1;;;;;Synthetic;;;Nobody;;\n'
            'T2;;;;;Synthetic;;not-a-date;;;\n').encode()


def test_real_child_preserves_invalid_date_and_snapshot():
    source = SourceSnapshot('metadata.csv', csv_bytes(), 'synthetic')
    preview = PreviewRunner().run(source, format='csv', profile='checklist')
    assert preview.source == source
    assert preview.complete
    assert preview.counts.candidate == 1
    assert preview.counts.rejected == 1
    assert preview.rows[1].issues[0].code == 'invalid_date'
    assert preview.rows[1].due_date is None


@pytest.mark.parametrize('source,format,profile,code', [
    ('/not/a/file.csv', 'csv', 'checklist', 'invalid_input'),
    (bytearray(b'x'), 'csv', 'checklist', 'invalid_input'),
    (b'x', 'pdf', 'checklist', 'unsupported_format'),
    (b'x', 'csv', 'custom', 'unsupported_profile'),
    (b'12345', 'csv', 'checklist', 'input_limit'),
])
def test_preflight_never_spawns(monkeypatch, source, format, profile, code):
    def forbidden(*args, **kwargs):
        pytest.fail('spawned before validation')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    runner = PreviewRunner(parse_limits=ParseLimits(max_input_bytes=4))
    with pytest.raises(PreviewRunnerError) as error:
        runner.run(source, format=format, profile=profile)
    assert error.value.code == code
    assert str(error.value) == code


def controlled(monkeypatch, program):
    """Replace only the private spawn seam; keep production pipe/cleanup logic."""
    children = []
    real = subprocess.Popen

    def spawn(*args, **kwargs):
        child = real([sys.executable, '-I', '-B', '-c', program], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, 'Popen', spawn)
    return children


def assert_reaped(children):
    assert children
    for child in children:
        assert child.returncode is not None
        with pytest.raises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)
        assert child.stdin.closed and child.stdout.closed


@pytest.mark.parametrize('program,code', [
    ('import sys; sys.exit(7)', 'worker_crash'),
    ('import sys; sys.stdin.buffer.read(); print("not-json")', 'malformed_response'),
    ('import sys; sys.stdin.buffer.read(); print("{}")', 'malformed_response'),
    ('import sys; sys.stdin.buffer.read(); sys.stdout.write("x"*2048)', 'response_limit'),
    ('import time; time.sleep(60)', 'timeout'),
])
def test_failures_are_typed_reaped_and_capacity_released(monkeypatch, program, code):
    children = controlled(monkeypatch, program)
    runner = PreviewRunner(limits=RunnerLimits(timeout_seconds=1, max_response_bytes=1024))
    for _ in range(2):
        with pytest.raises(PreviewRunnerError) as error:
            runner.run(b'x', format='csv', profile='checklist')
        assert error.value.code == code
        assert_reaped(children)
    monkeypatch.undo()
    assert PreviewRunner().run(csv_bytes(), format='csv', profile='checklist').complete


def test_cancellation_kills_term_resistant_child_and_releases_admission(monkeypatch):
    # Child emits a readiness byte only after installing SIGTERM resistance.
    program = ('import signal,sys,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); '
               'sys.stdout.buffer.write(b" "); sys.stdout.buffer.flush(); time.sleep(60)')
    children = controlled(monkeypatch, program)
    runner = PreviewRunner(limits=RunnerLimits(timeout_seconds=10, terminate_grace_seconds=.1))
    cancelled = Event()
    observed = []
    ready = Event()
    original_read = os.read

    def read(fd, size):
        data = original_read(fd, size)
        if data == b' ':
            ready.set()
        return data

    monkeypatch.setattr(os, 'read', read)

    def run():
        try:
            runner.run(b'x', format='csv', profile='checklist', cancel=cancelled)
        except PreviewRunnerError as exc:
            observed.append(exc.code)

    thread = Thread(target=run)
    thread.start()
    try:
        assert ready.wait(5)
        with pytest.raises(PreviewRunnerError, match='busy'):
            runner.run(b'x', format='csv', profile='checklist')
        assert len(children) == 1
    finally:
        cancelled.set()
        thread.join(5)
    assert not thread.is_alive()
    assert observed == ['cancelled']
    assert children[0].returncode == -signal.SIGKILL
    assert_reaped(children)
    # Pre-cancelled calls do not consume capacity or spawn.
    with pytest.raises(PreviewRunnerError, match='cancelled'):
        runner.run(b'x', format='csv', profile='checklist', cancel=cancelled)
    assert len(children) == 1


def test_child_environment_is_empty_and_descriptors_closed(monkeypatch):
    real = subprocess.Popen
    calls = []

    def spawn(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(subprocess, 'Popen', spawn)
    assert PreviewRunner().run(csv_bytes(), format='csv', profile='checklist').complete
    assert calls[0]['env'] == {}
    assert calls[0]['close_fds'] is True
    assert calls[0]['stderr'] == subprocess.DEVNULL


def test_real_xlsx_roundtrip_preserves_temporal_cells_and_bytes():
    from openpyxl import Workbook
    from app.modules.task_import.checklist_parser import parse_checklist

    book = Workbook()
    book.active.title = ChecklistProfile().sheet
    book.active.append(ChecklistProfile().headers)
    for index, value in enumerate((date(2026, 1, 2), datetime(2026, 2, 3, 14, 25)), 1):
        book.active.append([f'T{index}', '', '', '', '', 'Synthetic', '', value])
    stream = BytesIO()
    book.save(stream)
    book.close()
    source = SourceSnapshot('synthetic.xlsx', stream.getvalue(), 'synthetic')
    expected = parse_checklist(source, ChecklistProfile(), ParseLimits())
    result = PreviewRunner().run(source, format='xlsx', profile='checklist')
    assert result == expected
    assert result.source is source
    assert result.complete and result.counts.candidate == 2
    assert [row.due_date for row in result.rows] == [date(2026, 1, 2), date(2026, 2, 3)]
    assert result.rows[1].cells[7].value == datetime(2026, 2, 3, 14, 25)


def malformed_result(monkeypatch, mutation):
    from app.modules.task_import.checklist_parser import parse_checklist
    from app.modules.task_import.preview_runner import _encode

    preview = parse_checklist(SourceSnapshot('preview.csv', csv_bytes()), ChecklistProfile(), ParseLimits())
    payload = asdict(preview)
    del payload['source'], payload['profile']
    payload = json.loads(json.dumps(payload, default=_encode))
    row = payload['rows'][0]
    if mutation == 'hash':
        payload['sha256'] = '0' * 64
    elif mutation == 'counts':
        payload['counts']['candidate'] = 99
    elif mutation == 'boolean_count':
        payload['counts']['candidate'] = True
    elif mutation == 'unknown_issue':
        payload['issues'][0]['code'] = 'arbitrary'
    elif mutation == 'partial_failure':
        payload['complete'] = False
    elif mutation == 'row_number':
        row['number'] = -1
    elif mutation == 'coordinate':
        row['cells'][0]['coordinate'] = 'A999'
    elif mutation == 'candidate_issue':
        row['issues'] = [payload['rows'][1]['issues'][0]]
    elif mutation == 'invalid_date':
        payload['rows'][1]['due_date'] = {'type': 'date', 'value': '2026-01-01'}
    elif mutation == 'missing_headers':
        payload['headers'] = []
    elif mutation == 'line_range':
        row['line_end'] = 0
    elif mutation == 'sheet':
        row['sheet'] = 'Unexpected'
    children = controlled(monkeypatch, 'import sys; sys.stdin.buffer.read(); print(' + repr(json.dumps(payload)) + ')')
    try:
        PreviewRunner().run(csv_bytes(), format='csv', profile='checklist')
    except PreviewRunnerError as error:
        assert error.code == 'malformed_response'
        return True
    finally:
        assert_reaped(children)
    return False


def test_semantically_malformed_child_results_are_rejected(monkeypatch):
    accepted = []
    for mutation in ('row_number', 'coordinate', 'candidate_issue', 'invalid_date',
                     'missing_headers', 'line_range', 'sheet', 'hash', 'counts',
                     'boolean_count', 'unknown_issue', 'partial_failure'):
        with monkeypatch.context() as patch:
            if not malformed_result(patch, mutation):
                accepted.append(mutation)
    assert accepted == []


def test_capacity_recovers_to_real_success_after_cancellation(monkeypatch):
    with monkeypatch.context() as patch:
        test_cancellation_kills_term_resistant_child_and_releases_admission(patch)
    assert PreviewRunner().run(csv_bytes(), format='csv', profile='checklist').complete


class SyntheticUnreapableChild:
    """No OS process: exhaust waits deterministically without creating zombies."""

    def __init__(self):
        self.stdin = BytesIO()
        self.stdout = BytesIO()
        self.returncode = None
        self.wait_timeouts = []
        self.signals = []

    def poll(self):
        return self.returncode

    def terminate(self):
        self.signals.append('TERM')

    def kill(self):
        self.signals.append('KILL')

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        # Guard against the old unbounded wait without blocking the test.
        if timeout is None:
            raise AssertionError('unbounded cleanup wait')
        raise subprocess.TimeoutExpired('synthetic', timeout)


def test_exhausted_cleanup_quarantines_capacity_until_observed_reap(monkeypatch):
    import app.modules.task_import.preview_runner as module

    child = SyntheticUnreapableChild()
    spawns = []

    def spawn(*args, **kwargs):
        spawns.append(child)
        return child

    monkeypatch.setattr(subprocess, 'Popen', spawn)
    runner = PreviewRunner()

    def cancelled(*args):
        raise PreviewRunnerError('cancelled')

    monkeypatch.setattr(runner, '_exchange', cancelled)
    try:
        with pytest.raises(PreviewRunnerError, match='cleanup_failed'):
            runner.run(b'x', format='csv', profile='checklist')
        assert child.signals == ['TERM', 'KILL']
        assert len(child.wait_timeouts) == 2
        assert all(timeout > 0 for timeout in child.wait_timeouts)
        assert child.stdin.closed and child.stdout.closed
        for _ in range(2):
            with pytest.raises(PreviewRunnerError, match='cleanup_failed'):
                PreviewRunner().run(b'x', format='csv', profile='checklist')
        assert spawns == [child]
        assert module._QUARANTINED_CHILD is child
    finally:
        # Simulate a later successful nonblocking reap, never discard ownership.
        child.returncode = -signal.SIGKILL
        if hasattr(module, '_reap_quarantined'):
            module._reap_quarantined()
    monkeypatch.undo()
    assert PreviewRunner().run(csv_bytes(), format='csv', profile='checklist').complete


def test_normal_term_cleanup_is_reaped(monkeypatch):
    children = controlled(monkeypatch, 'import time; time.sleep(60)')
    with pytest.raises(PreviewRunnerError, match='timeout'):
        PreviewRunner(limits=RunnerLimits(timeout_seconds=.2)).run(
            b'x', format='csv', profile='checklist')
    assert children[0].returncode == -signal.SIGTERM
    assert_reaped(children)


def test_parser_failure_is_not_partial_success():
    result = PreviewRunner().run(b'\xff', format='csv', profile='checklist')
    assert not result.complete
    assert result.rows == () and result.counts is None
    assert result.issues[0].code == 'encoding_error'
