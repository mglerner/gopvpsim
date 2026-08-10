"""Worlds plane storage (scripts/worlds_planes.py): npz format, path
guards, manifest stamps, gitignore split.

The npz gotchas here are the measured ones from the 2026-08-10 guards
audit: packbits pads to whole bytes (so shape must be STORED, and the
round-trip test uses a non-multiple-of-8, asymmetric plane -- a
Tier-1-shaped plane is divisible by 8 and would pass a broken reader
silently); unpackbits returns uint8 (so the reader must hand back real
bools); scores wrap if anyone re-introduces a signed margin in uint16.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT / 'src', REPO_ROOT / 'scripts'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import worlds_planes as wp  # noqa: E402


def _tiny_arrays(shape=(2, 7, 3)):
    """Asymmetric, non-multiple-of-8 plane (42 cells): catches bitorder
    flips and shape-inference bugs the real Tier-1 shape hides."""
    rng = np.arange(int(np.prod(shape))).reshape(shape)
    won = (rng * 7 % 5) < 2                     # asymmetric pattern
    score = np.where(won, 700, 300).astype(np.uint16)
    n = shape[1]
    return wp.plane_arrays(
        won, score,
        focal_ivs=[(0, 15, 15)] * shape[0],
        focal_levels=[40.0] * shape[0],
        opp_ivs=[(0, 15, 14)] * n,
        opp_levels=[39.5] * n,
        scenarios=[(0, 0), (1, 1), (2, 2)],
        top512_mask=[True] * n,
        atkband_mask=[False] * n), won, score


def test_roundtrip_non_multiple_of_8_asymmetric(tmp_path):
    arrs, won, score = _tiny_arrays()
    wp.write_plane('a__vs__b__bait.npz', arrs, tmp_path)
    back = wp.read_plane('a__vs__b__bait.npz', tmp_path)
    assert back['won'].dtype == np.bool_
    assert np.array_equal(back['won'], won)
    assert np.array_equal(back['score'], score)
    # packbits really padded (42 bools -> 48 bits -> 6 bytes)
    assert back['won_packed'].size * 8 > won.size
    # uint8-complement footgun stays out: complement is a bool count
    assert (~back['won']).sum() == (~won).sum()


def test_pack_unpack_shape_is_load_bearing():
    won = np.zeros((3, 5), dtype=bool)
    won[1, 4] = True
    packed, shape = wp.pack_won(won)
    assert np.array_equal(wp.unpack_won(packed, shape), won)
    with pytest.raises(ValueError):
        wp.unpack_won(packed, (5, 5))            # count > stored bits


def test_score_range_guard():
    arrs, won, score = _tiny_arrays()
    bad = score.copy()
    bad[0, 0, 0] = 1500
    with pytest.raises(ValueError, match='score out of pvpoke range'):
        wp.plane_arrays(won, bad,
                        focal_ivs=[(0, 0, 0)] * won.shape[0],
                        focal_levels=[40.0] * won.shape[0],
                        opp_ivs=[(0, 0, 0)] * won.shape[1],
                        opp_levels=[40.0] * won.shape[1],
                        scenarios=[(0, 0)] * won.shape[2],
                        top512_mask=[True] * won.shape[1],
                        atkband_mask=[False] * won.shape[1])


def test_out_path_rejects_great_toml_and_escapes(tmp_path):
    with pytest.raises(ValueError, match='_great.toml'):
        wp.out_path('lickilicky_great.toml', tmp_path)
    with pytest.raises(ValueError, match='only .npz/.json'):
        wp.out_path('notes.txt', tmp_path)
    with pytest.raises(ValueError, match='escapes'):
        wp.out_path('../../thresholds/x.npz', tmp_path)


def test_content_md5_is_order_independent():
    a = {'x': np.arange(4), 'y': np.ones(3)}
    b = {'y': np.ones(3), 'x': np.arange(4)}
    assert wp.content_md5(a) == wp.content_md5(b)
    c = {'x': np.arange(4), 'y': np.ones(3) * 2}
    assert wp.content_md5(a) != wp.content_md5(c)


def test_stamp_mismatch_detection_and_no_deletion(tmp_path):
    arrs, _, _ = _tiny_arrays()
    wp.write_plane('a__vs__b__bait.npz', arrs, tmp_path)
    manifest = {**wp.fresh_stamps(), 'entries': {
        'a|b|bait': {'file': 'a__vs__b__bait.npz'}}}
    assert wp.stamp_mismatches(manifest) == []
    for key in wp.STAMP_KEYS:
        doctored = dict(manifest)
        doctored[key] = 'stale-value'
        mm = wp.stamp_mismatches(doctored)
        assert [m[0] for m in mm] == [key]
    # Detection never deletes anything -- refusal is the driver's job.
    assert wp.out_path('a__vs__b__bait.npz', tmp_path).exists()


def test_is_baked_requires_entry_AND_file(tmp_path):
    arrs, _, _ = _tiny_arrays()
    manifest = {'entries': {'a|b|bait': {'file': 'a__vs__b__bait.npz'}}}
    assert not wp.is_baked(manifest, 'a|b|bait', tmp_path)   # entry, no file
    wp.write_plane('a__vs__b__bait.npz', arrs, tmp_path)
    assert wp.is_baked(manifest, 'a|b|bait', tmp_path)
    assert not wp.is_baked(manifest, 'b|a|bait', tmp_path)   # file, no entry
    assert not wp.is_baked(None, 'a|b|bait', tmp_path)


def test_expected_tier1_keys_from_real_meta():
    """C(31,2)=465 pairs x 2 directions x 2 bait modes. == is legitimate
    here: the expectation derives from the same meta the driver bakes
    from (testing-policy exception)."""
    import tomllib
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    keys = wp.expected_tier1_keys(entries)
    n = len(entries)
    assert n == 31
    assert len(keys) == (n * (n - 1) // 2) * 2 * 2 == 1860
    assert wp.pair_key('tinkaton', 'mantine', True) in keys
    assert wp.pair_key('mantine', 'tinkaton', False) in keys
    assert not any('aegislash_blade' in k for k in keys)


def test_worlds_code_hash_files_exist_and_hash_is_sensitive(tmp_path,
                                                           monkeypatch):
    for p in wp._WORLDS_SOURCE_FILES:
        assert p.exists(), f'renamed producer source: {p}'
    assert len(wp._WORLDS_SOURCE_FILES) >= 4
    before = wp.worlds_code_hash()
    clone = tmp_path / 'x.py'
    clone.write_bytes(wp._WORLDS_SOURCE_FILES[0].read_bytes() + b'\n# byte\n')
    monkeypatch.setattr(wp, '_WORLDS_SOURCE_FILES',
                        (clone,) + wp._WORLDS_SOURCE_FILES[1:])
    assert wp.worlds_code_hash() != before


def test_fresh_stamps_refuses_fake_gamemaster(monkeypatch):
    monkeypatch.setattr(wp, 'gamemaster_hash', lambda: 'no-gamemaster')
    with pytest.raises(SystemExit, match='fake provenance'):
        wp.fresh_stamps()


def test_manifest_save_load_roundtrip(tmp_path):
    manifest = {**wp.fresh_stamps(), 'entries': {}}
    wp.save_manifest(manifest, tmp_path)
    assert wp.load_manifest(tmp_path) == manifest
    # and it is valid json on disk (tracked artifact, reviewed in git)
    raw = json.loads((tmp_path / 'manifest.json').read_text())
    assert raw['mechanics'] == 'legacy'


def test_plane_npz_gitignored_but_manifest_tracked():
    """Both directions, so the split cannot pass vacuously."""
    npz = subprocess.run(
        ['git', 'check-ignore', '-q', 'worlds/planes/x.npz'],
        cwd=REPO_ROOT)
    assert npz.returncode == 0, 'plane npz blobs must be gitignored'
    man = subprocess.run(
        ['git', 'check-ignore', '-q', 'worlds/planes/manifest.json'],
        cwd=REPO_ROOT)
    assert man.returncode == 1, 'the manifest is the provenance record ' \
                                'and must stay tracked'
