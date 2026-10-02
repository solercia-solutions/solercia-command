"""Inventory supplied entries only: no traversal, copying, merging or file I/O."""
from collections import Counter
from collections.abc import Iterable
from hashlib import sha256
import posixpath
import unicodedata

from .contracts import Availability, Issue, ManifestEntry, SourceSnapshot, UnavailableSource


def locator_issues(path: str) -> tuple[Issue, ...]:
    """Portable relative POSIX locators; flag ambiguity without rewriting input."""
    if (not path or '\\' in path or ':' in path
            or any(ord(char) < 32 or ord(char) == 127 for char in path)
            or any(part in ('', '.', '..') for part in path.split('/'))):
        return (Issue('unsafe_locator'),)
    return ()


def source_format(path: str) -> str:
    return posixpath.splitext(path)[1].lower()


def _collision_key(path: str) -> str:
    # Comparison only, not a replacement locator. Conservative for Mac/Windows.
    return unicodedata.normalize('NFC', posixpath.normpath(path.replace('\\', '/'))).casefold()


def build_manifest(entries: Iterable[SourceSnapshot | UnavailableSource]) -> tuple[ManifestEntry, ...]:
    """Preserve every entry and original spelling. Stable under input permutation.

    Case/Unicode/path aliases are flagged conservatively; no filesystem identity
    or symlink resolution is attempted. Equal entries may remain repeated.
    """
    sources = tuple(entries)
    collisions = Counter(_collision_key(s.relative_path) for s in sources)
    result = []
    for source in sources:
        issues = list(locator_issues(source.relative_path))
        if collisions[_collision_key(source.relative_path)] > 1:
            issues.append(Issue('locator_collision'))
        if source_format(source.relative_path) not in ('.csv', '.xlsx'):
            issues.append(Issue('unsupported_format', 'warning'))
        if isinstance(source, SourceSnapshot):
            size, digest = len(source.data), sha256(source.data).hexdigest()
            availability = Availability.AVAILABLE
            if not source.data:
                issues.append(Issue('empty_source'))
        else:
            size, digest, availability = None, None, source.availability
            issues.append(Issue('unavailable' if availability == Availability.UNAVAILABLE else 'source_error'))
        result.append(ManifestEntry(source, availability, size, digest, tuple(issues)))
    return tuple(sorted(result, key=lambda item: (
        item.source.relative_path, item.availability, item.sha256 or '',
        item.source.provenance,
        item.source.data if isinstance(item.source, SourceSnapshot) else b'',
    )))
