"""Internal synchronous preview runner; no HTTP surface or filesystem inputs.

One shared admission slot per interpreter, no queue. Callers may cancel with a
threading.Event (the parser itself runs in a dedicated, killable process).
Limits belong to server construction, never to an upload/request. The deadline
covers child IO/execution, followed by bounded TERM and KILL/reap waits.
If the kernel cannot reap within those waits, cleanup_failed retains the child
in a process-wide quarantine and keeps admission closed. Later calls attempt a
nonblocking reap before admission; there is no detached reaper or retry loop.
An indefinitely unreapable child requires operator intervention; this module
cannot guarantee kernel termination or completion of Popen itself.

The exec child receives an empty environment and no session/provider objects.
This is NOT an OS/network sandbox: it retains the service user's OS privileges,
filesystem/network access, inherited working directory and installed Python packages. Do not expose publicly
without authentication, deployment-wide admission and OS resource isolation.
No hard RSS/CPU quota is provided. Output bytes and parser structure are capped.
"""
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
from threading import BoundedSemaphore, Event, Lock
from time import monotonic
from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints

from .contracts import ChecklistPreview, ChecklistProfile, ParseLimits, SourceSnapshot


class PreviewRunnerError(Exception):
    """Only a stable code; never include content or raw child exceptions."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RunnerLimits:
    timeout_seconds: float = 10
    terminate_grace_seconds: float = .2
    max_response_bytes: int = 8 * 1024 * 1024
    kill_grace_seconds: float = .5

    def __post_init__(self):
        for value in (self.timeout_seconds, self.terminate_grace_seconds, self.kill_grace_seconds):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError('El tiempo límite debe ser positivo y finito.')
        if type(self.max_response_bytes) is not int or self.max_response_bytes <= 0:
            raise ValueError('El límite de respuesta debe ser un entero positivo.')


_ADMISSION = BoundedSemaphore(1)
_QUARANTINE_LOCK = Lock()
_QUARANTINED_CHILD: subprocess.Popen | None = None
_TEMPORAL = {t.__name__: t for t in (date, datetime, time, timedelta)}


def _encode(value):
    if type(value) in _TEMPORAL.values():
        payload = ([value.days, value.seconds, value.microseconds]
                   if isinstance(value, timedelta) else value.isoformat())
        return {'type': type(value).__name__, 'value': payload}
    raise ValueError


def _decode(value, kind):
    """Decode JSON into only the existing DTO schema, never arbitrary objects."""
    origin, args = get_origin(kind), get_args(kind)
    if origin is UnionType:
        for alternative in args:
            try:
                return _decode(value, alternative)
            except (ValueError, TypeError, KeyError, OverflowError):
                pass
        raise ValueError
    if origin is Literal:
        if value not in args:
            raise ValueError
        return value
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError
        return tuple(_decode(item, args[0]) for item in value)
    if is_dataclass(kind):
        hints = get_type_hints(kind)
        if not isinstance(value, dict) or set(value) != set(hints):
            raise ValueError
        return kind(**{key: _decode(item, hints[key]) for key, item in value.items()})
    if kind in _TEMPORAL.values():
        if not isinstance(value, dict) or set(value) != {'type', 'value'} or value['type'] != kind.__name__:
            raise ValueError
        if kind is timedelta:
            parts = value['value']
            if not isinstance(parts, list) or len(parts) != 3 or any(type(p) is not int for p in parts):
                raise ValueError
            return timedelta(days=parts[0], seconds=parts[1], microseconds=parts[2])
        return kind.fromisoformat(value['value'])
    if type(value) is not kind or isinstance(value, float) and not math.isfinite(value):
        raise ValueError
    return value


def _validate_result(result, format, limits):
    """Check DTO cross-field invariants without reparsing source in the parent.

    This validates structure/consistency, not authenticity against a malicious
    worker. The child remains trusted code with the service user's privileges.
    """
    if not result.complete:
        if result.headers or result.rows or result.counts is not None or not result.issues:
            raise ValueError
        return
    if not result.headers or len(result.rows) + 1 > limits.max_rows:
        raise ValueError
    if format == 'csv' and result.sheet_names:
        raise ValueError
    if format == 'xlsx' and result.profile.sheet not in result.sheet_names:
        raise ValueError
    total = 0
    issues = set(result.issues)
    previous_line = 1
    for number, cells in [(1, result.headers)] + [(r.number, r.cells) for r in result.rows]:
        total += len(cells)
        if len(cells) > limits.max_columns or total > limits.max_cells:
            raise ValueError
        for index, cell in enumerate(cells, 1):
            letters = ''
            while index:
                index, digit = divmod(index - 1, 26)
                letters = chr(65 + digit) + letters
            if cell.coordinate != f'{letters}{number}':
                raise ValueError
            if isinstance(cell.value, str) and len(cell.value) > limits.max_cell_chars:
                raise ValueError
    for expected_number, row in enumerate(result.rows, 2):
        if row.number != expected_number or len(row.cells) < len(result.headers):
            raise ValueError
        if format == 'csv':
            if (row.sheet is not None or row.line_start is None or row.line_end is None
                    or row.line_start <= previous_line or row.line_end < row.line_start):
                raise ValueError
            previous_line = row.line_end
        elif row.sheet != result.profile.sheet or row.line_start is not None or row.line_end is not None:
            raise ValueError
        if row.disposition == 'candidate' and (row.issues or not row.source_id or not row.source_id.strip()):
            raise ValueError
        if any(issue.code == 'invalid_date' for issue in row.issues) and row.due_date is not None:
            raise ValueError
        if any(issue.row != row.number or issue not in issues for issue in row.issues):
            raise ValueError
        if row.disposition == 'blank_skipped' and (row.source_id is not None or row.due_date is not None or row.issues):
            raise ValueError
    for issue in result.issues:
        if issue.row is not None and not 1 <= issue.row <= len(result.rows) + 1:
            raise ValueError
        if issue.column is not None and not 1 <= issue.column <= limits.max_columns:
            raise ValueError


def _reap_quarantined():
    """Retain ownership and capacity until poll observes a completed reap."""
    global _QUARANTINED_CHILD
    with _QUARANTINE_LOCK:
        if _QUARANTINED_CHILD is None:
            return
        try:
            reaped = _QUARANTINED_CHILD.poll() is not None
        except Exception:
            reaped = False
        if not reaped:
            raise PreviewRunnerError('cleanup_failed')
        _QUARANTINED_CHILD = None
        _ADMISSION.release()


def _stop(child, limits):
    """Bound each wait; caller must quarantine on any cleanup failure."""
    try:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=limits.terminate_grace_seconds)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=limits.kill_grace_seconds)
    except Exception:
        raise PreviewRunnerError('cleanup_failed') from None
    finally:
        child.stdin.close()
        child.stdout.close()


class PreviewRunner:
    def __init__(self, *, limits=RunnerLimits(), parse_limits=ParseLimits()):
        self.limits = limits
        self.parse_limits = parse_limits

    def run(self, source: bytes | SourceSnapshot, *, format: str, profile: str,
            cancel: Event | None = None) -> ChecklistPreview:
        """Format/profile are explicit allowlisted IDs, not extensions or paths.

        Snapshot locators/provenance remain caller metadata in the parent; only
        bytes cross into the child. No source path is opened or inferred.
        Cancellation is cooperative via Event, checked at most every 50 ms.
        """
        if type(source) not in (bytes, SourceSnapshot):
            raise PreviewRunnerError('invalid_input')
        if format not in ('csv', 'xlsx'):
            raise PreviewRunnerError('unsupported_format')
        if profile != 'checklist':
            raise PreviewRunnerError('unsupported_profile')
        data = source if type(source) is bytes else source.data
        if len(data) > self.parse_limits.max_input_bytes:
            raise PreviewRunnerError('input_limit')
        if cancel is not None and cancel.is_set():
            raise PreviewRunnerError('cancelled')
        _reap_quarantined()
        if not _ADMISSION.acquire(blocking=False):
            raise PreviewRunnerError('busy')
        child = None
        try:
            deadline = monotonic() + self.limits.timeout_seconds
            # Fixed server-owned code path, not a caller filesystem locator.
            root = str(Path(__file__).resolve().parents[3])
            code = (f'import sys; sys.path.insert(0, {root!r}); '
                    'from app.modules.task_import.preview_runner import _child; _child()')
            child = subprocess.Popen(
                [sys.executable, '-I', '-B', '-c', code],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env={}, close_fds=True,
            )
            header = json.dumps({'format': format, 'limits': asdict(self.parse_limits),
                                 'response_limit': self.limits.max_response_bytes}).encode() + b'\n'
            response = self._exchange(child, header + data, deadline, cancel)
            if child.returncode != 0:
                raise PreviewRunnerError('worker_crash')
            try:
                payload = json.loads(response)
                if payload == {'error': 'response_limit'}:
                    raise PreviewRunnerError('response_limit')
                if payload == {'error': 'worker_failure'}:
                    raise PreviewRunnerError('worker_failure')
                hints = get_type_hints(ChecklistPreview)
                expected = set(hints) - {'source', 'profile'}
                if not isinstance(payload, dict) or set(payload) != expected:
                    raise ValueError
                result = ChecklistPreview(
                    source if type(source) is SourceSnapshot else SourceSnapshot(f'preview.{format}', data),
                    profile=ChecklistProfile(),
                    **{key: _decode(value, hints[key]) for key, value in payload.items()},
                )
                if result.sha256 != sha256(data).hexdigest():
                    raise ValueError
                if result.complete:
                    if result.counts is None or any(getattr(result.counts, k) != sum(
                            r.disposition == k for r in result.rows)
                            for k in ('candidate', 'rejected', 'blank_skipped')):
                        raise ValueError
                elif result.rows or result.counts is not None or not result.issues:
                    raise ValueError
                _validate_result(result, format, self.parse_limits)
                return result
            except PreviewRunnerError:
                raise
            except Exception:
                raise PreviewRunnerError('malformed_response') from None
        except PreviewRunnerError:
            raise
        except Exception:
            raise PreviewRunnerError('worker_failure') from None
        finally:
            global _QUARANTINED_CHILD
            if child is not None:
                try:
                    _stop(child, self.limits)
                except Exception:
                    # Never release capacity or drop the reference on failure.
                    with _QUARANTINE_LOCK:
                        _QUARANTINED_CHILD = child
                    raise PreviewRunnerError('cleanup_failed') from None
            _ADMISSION.release()

    def _exchange(self, child, request, deadline, cancel):
        output = bytearray()
        pending = memoryview(request)
        with selectors.DefaultSelector() as selector:
            for stream, event in ((child.stdin, selectors.EVENT_WRITE),
                                  (child.stdout, selectors.EVENT_READ)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, event)
            while selector.get_map() or child.poll() is None:
                if cancel is not None and cancel.is_set():
                    raise PreviewRunnerError('cancelled')
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise PreviewRunnerError('timeout')
                for key, _ in selector.select(min(.05, remaining)):
                    if key.fileobj is child.stdin:
                        try:
                            sent = os.write(child.stdin.fileno(), pending[:65536])
                            pending = pending[sent:]
                        except BrokenPipeError:
                            pending = pending[:0]
                        if not pending:
                            selector.unregister(child.stdin)
                            child.stdin.close()
                    else:
                        chunk = os.read(child.stdout.fileno(), min(
                            65536, self.limits.max_response_bytes + 1 - len(output)))
                        if not chunk:
                            selector.unregister(child.stdout)
                        output.extend(chunk)
                        if len(output) > self.limits.max_response_bytes:
                            raise PreviewRunnerError('response_limit')
            # The loop exits only after poll has reaped the child.
        return output


def _child():
    """Private exec entry point. No user code, environment settings or logging."""
    try:
        from .checklist_parser import parse_checklist
        header = json.loads(sys.stdin.buffer.readline(4096))
        limits = ParseLimits(**header['limits'])
        data = sys.stdin.buffer.read(limits.max_input_bytes + 1)
        if header['format'] not in ('csv', 'xlsx') or len(data) > limits.max_input_bytes:
            raise ValueError
        preview = parse_checklist(SourceSnapshot('preview.' + header['format'], data),
                                  ChecklistProfile(), limits)
        payload = {f.name: asdict(preview)[f.name] for f in fields(preview)
                   if f.name not in ('source', 'profile')}
        # Incremental encoding bounds the wire buffer even for large projections.
        output = bytearray()
        for part in json.JSONEncoder(default=_encode, allow_nan=False).iterencode(payload):
            output.extend(part.encode())
            if len(output) > header['response_limit']:
                output = b'{"error":"response_limit"}'
                break
        sys.stdout.buffer.write(output)
    except Exception:
        sys.stdout.buffer.write(b'{"error":"worker_failure"}')
