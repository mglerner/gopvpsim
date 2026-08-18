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
    """C(n,2) pairs x 2 directions x 2 bait modes. == is legitimate here:
    the expectation derives from the same meta the driver bakes from
    (testing-policy exception). n is NOT pinned -- the meta grows
    (31 -> 32 when Thievul was added 2026-08-18)."""
    import tomllib
    import worlds_meta as wm
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    keys = wp.expected_tier1_keys(entries)
    n = len(entries)
    assert n == len(wm.META) >= 31
    assert len(keys) == (n * (n - 1) // 2) * 2 * 2
    assert wp.pair_key('tinkaton', 'mantine', True) in keys
    assert wp.pair_key('mantine', 'tinkaton', False) in keys
    assert not any('aegislash_blade' in k for k in keys)


def test_worlds_code_hash_files_exist_and_hash_is_sensitive(tmp_path,
                                                           monkeypatch):
    for p in wp._WORLDS_SOURCE_FILES:
        assert p.exists(), f'renamed producer source: {p}'
    assert len(wp._WORLDS_SOURCE_FILES) >= 4
    names = {p.name for p in wp._WORLDS_SOURCE_FILES}
    # Boundary pins (2026-08-10 review): sweep.py builds every simmed
    # mon and is outside the engine hash -> IN; worlds_tier0.py never
    # runs in the plane path -> OUT (a tier0 edit must not cold a
    # 1,860-plane bake).
    assert 'sweep.py' in names
    assert 'worlds_tier0.py' not in names
    before = wp.worlds_code_hash()
    clone = tmp_path / 'x.py'
    clone.write_bytes(wp._WORLDS_SOURCE_FILES[0].read_bytes() + b'\n# byte\n')
    monkeypatch.setattr(wp, '_WORLDS_SOURCE_FILES',
                        (clone,) + wp._WORLDS_SOURCE_FILES[1:])
    assert wp.worlds_code_hash() != before


def test_margin_helper_widens_before_subtracting():
    """score - 500 on the raw uint16 plane wraps every loss to ~65k --
    the helper is THE read recipe (2026-08-10 review)."""
    score = np.array([[300, 500, 700]], dtype=np.uint16)
    m = wp.margin(score)
    assert m.tolist() == [[-200, 0, 200]]
    assert m.dtype == np.int32
    # The naive spelling really is broken (pin the hazard itself).
    assert (score - np.uint16(500))[0, 0] != -200


def test_meta_delta_add_change_remove():
    """Per-entry sim-relevant diffing: an added entry extends, a changed
    moveset / removed entry invalidates -- and NON-sim fields (usage,
    badges, prose, `generated`) are invisible to the digest, which is
    the whole point (whole-file hashing forced a full cold re-bake on
    every prose edit; 2026-08-10 review, HIGH)."""
    e1 = {'species_id': 'a', 'species': 'A', 'shadow': False,
          'fast_move_id': 'F', 'charged_move_ids': ['C1', 'C2'],
          'usage_recent_pct': 10.0, 'badge': 'PLAYED'}
    e2 = {'species_id': 'b', 'species': 'B', 'shadow': True,
          'fast_move_id': 'G', 'charged_move_ids': ['C3', 'C4']}
    manifest = {'meta_entries': wp.meta_sim_digests([e1, e2])}
    # Non-sim churn: invisible.
    e1_prose = {**e1, 'usage_recent_pct': 99.9, 'badge': 'MODEL',
                'forced_reason': 'reworded'}
    assert wp.meta_delta(manifest, [e1_prose, e2]) == ([], [], [])
    # Added: extendable.
    e3 = {'species_id': 'c', 'species': 'C', 'shadow': False,
          'fast_move_id': 'H', 'charged_move_ids': ['C5']}
    assert wp.meta_delta(manifest, [e1, e2, e3]) == ([], [], ['c'])
    # Changed moveset: invalidates.
    e2_new_move = {**e2, 'charged_move_ids': ['C3', 'C9']}
    assert wp.meta_delta(manifest, [e1, e2_new_move]) == (['b'], [], [])
    # Removed: invalidates.
    assert wp.meta_delta(manifest, [e1]) == ([], ['b'], [])


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


def test_fork_arms_pair_with_each_other_but_never_with_themselves():
    """Mirror-exclusion contract for moveset forks (2026-08-18): the two
    Thievul arms are distinct entries, so the CROSS-ARM pair is a real,
    baked matchup -- only the true self-mirror is excluded. The pair
    count must also grow by exactly n-1 pairs per added entry."""
    import tomllib
    entries = tomllib.load(open(wp.META_TOML, 'rb'))['entries']
    keys = wp.expected_tier1_keys(entries)
    arms = [e['species_id'] for e in entries if e['species'] == 'Thievul']
    assert len(arms) == 2, arms
    a, b = arms
    for focal, opp in ((a, b), (b, a)):
        for bait in (True, False):
            assert wp.pair_key(focal, opp, bait) in keys
    for sid in arms:                       # no self-mirror in either mode
        for bait in (True, False):
            assert wp.pair_key(sid, sid, bait) not in keys
    n = len(entries)
    assert len(keys) == (n * (n - 1) // 2) * 2 * 2
