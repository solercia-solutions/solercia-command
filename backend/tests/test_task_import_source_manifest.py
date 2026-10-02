"""Synthetic inputs only; manifest construction never opens a source path."""
from dataclasses import FrozenInstanceError
from itertools import permutations

import pytest

from app.modules.task_import.contracts import Availability, SourceSnapshot, UnavailableSource
from app.modules.task_import.source_manifest import build_manifest


def test_manifest_inventories_every_entry_deterministically():
    entries = (
        SourceSnapshot('b.csv', b'ID\n', provenance='synthetic'),
        SourceSnapshot('a.xlsx', b'ID\n', provenance='synthetic'),
        SourceSnapshot('empty.csv', b''),
        SourceSnapshot('notes.pdf', b'other'),
        UnavailableSource('cloud.csv', Availability.UNAVAILABLE),
        UnavailableSource('failed.csv', Availability.ERROR),
    )
    expected = build_manifest(entries)
    for order in permutations(entries):
        assert build_manifest(order) == expected
    by_path = {item.source.relative_path: item for item in expected}
    assert len(expected) == 6
    assert by_path['a.xlsx'].sha256 == by_path['b.csv'].sha256
    assert by_path['notes.pdf'].sha256 != by_path['b.csv'].sha256
    assert by_path['empty.csv'].size_bytes == 0
    assert by_path['empty.csv'].sha256
    assert by_path['cloud.csv'].size_bytes is None
    assert by_path['cloud.csv'].sha256 is None
    assert by_path['failed.csv'].availability == Availability.ERROR
    assert 'unsupported_format' in {i.code for i in by_path['notes.pdf'].issues}
    assert by_path['b.csv'].source is entries[0]
    assert entries[0].data == b'ID\n'
    with pytest.raises(FrozenInstanceError):
        entries[0].data = b'changed'


@pytest.mark.parametrize('path', ['../x.csv', '/x.csv', 'C:\\x.csv', 'a/../x.csv', 'a\\x.csv', '', 'a//x.csv', './x.csv', 'x\x00.csv'])
def test_unsafe_locators_are_preserved_and_flagged(path):
    item, = build_manifest([SourceSnapshot(path, b'x')])
    assert item.source.relative_path == path
    assert 'unsafe_locator' in {i.code for i in item.issues}


def test_collisions_never_merge_or_rewrite_entries():
    entries = [SourceSnapshot('A.csv', b'1'), SourceSnapshot('a.csv', b'2'), SourceSnapshot('a.csv', b'3')]
    result = build_manifest(entries)
    assert len(result) == 3
    assert result == build_manifest(reversed(entries))
    assert all('locator_collision' in {i.code for i in x.issues} for x in result)
    assert {x.source.data for x in result} == {b'1', b'2', b'3'}


def test_snapshot_rejects_mutable_bytes_and_invalid_unavailable_state():
    with pytest.raises(TypeError):
        SourceSnapshot('x.csv', bytearray(b'x'))
    with pytest.raises(ValueError):
        UnavailableSource('x.csv', Availability.AVAILABLE)
