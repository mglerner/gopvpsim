"""Tests for scripts/gc_cache.py — version-aware cache GC.

Pins decision D (2026-06-27): keep the current gamemaster vintage plus the
N-1 most-recent other vintages; drop the rest. The current vintage is always
kept regardless of recency.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sweep_cache = sys.modules.get("sweep_cache") or _load("sweep_cache")
gc_cache = sys.modules.get("gc_cache") or _load("gc_cache")


def _make_vintage(sweep_dir, name, gm, mtime):
    """Create a LEGACY (v6) focal dir stamped to gamemaster ``gm`` and a dummy
    column, with all files set to ``mtime`` (controls recency rank)."""
    d = sweep_dir / name
    d.mkdir(parents=True)
    (d / 'meta.json').write_text(json.dumps({'gamemaster': gm, 'v': 6}))
    (d / 'col.npz').write_bytes(b'x' * 100)
    for p in (d / 'meta.json', d / 'col.npz', d):
        os.utime(p, (mtime, mtime))
    return d


def _make_v7_dir(sweep_dir, name, col_stamps, mtime=500):
    """Create a v7 focal dir (no per-dir gamemaster) whose columns carry the
    given per-column gamemaster stamps. ``col_stamps`` = {colname: gm_stamp}."""
    d = sweep_dir / name
    d.mkdir(parents=True)
    (d / 'meta.json').write_text(json.dumps({'v': sweep_cache.CACHE_VERSION}))
    paths = {}
    for colname, stamp in col_stamps.items():
        (d / f'{colname}.npz').write_bytes(b'x' * 100)
        (d / f'{colname}.json').write_text(json.dumps(
            {'engine': 'e', 'gamemaster': stamp, 'col': {}}))
        paths[colname] = d / f'{colname}.json'
    for p in d.rglob('*'):
        os.utime(p, (mtime, mtime))
    os.utime(d, (mtime, mtime))
    return d, paths


def test_plan_keeps_current_plus_recent(tmp_path):
    sweep = tmp_path / 'sweep'
    cur = _make_vintage(sweep, 'cur', 'gm_current', mtime=1000)
    old_new = _make_vintage(sweep, 'old_new', 'gm_old_new', mtime=900)
    old_oldest = _make_vintage(sweep, 'old_oldest', 'gm_old_oldest', mtime=100)

    keep, drop, _by, keep_gms, v7 = gc_cache.plan_sweep(
        sweep, 'gm_current', keep_vintages=2)
    assert keep_gms == {'gm_current', 'gm_old_new'}
    assert set(keep) == {cur, old_new}
    assert set(drop) == {old_oldest}
    assert v7 == []


def test_plan_keep_only_current(tmp_path):
    sweep = tmp_path / 'sweep'
    cur = _make_vintage(sweep, 'cur', 'gm_current', mtime=100)  # oldest mtime!
    a = _make_vintage(sweep, 'a', 'gm_a', mtime=900)
    b = _make_vintage(sweep, 'b', 'gm_b', mtime=1000)
    # keep_vintages=1 -> only current survives, even though it's the oldest.
    keep, drop, _by, keep_gms, _v7 = gc_cache.plan_sweep(
        sweep, 'gm_current', keep_vintages=1)
    assert keep_gms == {'gm_current'}
    assert set(keep) == {cur}
    assert set(drop) == {a, b}


def test_v7_dir_always_kept_even_keep_vintages_1(tmp_path):
    # The BLOCKER fix: a v7 dir (no per-dir gamemaster) must survive even with
    # --keep-vintages 1 and a NEWER legacy vintage present, current_gm being a
    # real hash that matches no v7 dir.
    sweep = tmp_path / 'sweep'
    v7_dir, _ = _make_v7_dir(sweep, 'live_v7', {'c1': 'b3e793', 'c2': 'b3e793'},
                             mtime=100)  # oldest mtime on purpose
    newer_legacy = _make_vintage(sweep, 'legacy', 'gm_old', mtime=9999)
    keep, drop, _by, _keep_gms, v7 = gc_cache.plan_sweep(
        sweep, 'b3e793', keep_vintages=1)
    assert v7 == [v7_dir]
    assert v7_dir in keep
    assert newer_legacy in drop   # legacy still pruned


def test_v7_unreadable_meta_is_kept(tmp_path):
    sweep = tmp_path / 'sweep'
    bad = sweep / 'corrupt'
    bad.mkdir(parents=True)
    (bad / 'meta.json').write_text('{ not json')
    keep, drop, _by, _kg, _v7 = gc_cache.plan_sweep(
        sweep, 'gm_current', keep_vintages=1)
    assert bad in keep and bad not in drop


def test_v7_column_reclaim_keeps_current_plus_recent(tmp_path):
    sweep = tmp_path / 'sweep'
    # One v7 dir with columns at three gamemaster stamps.
    d, paths = _make_v7_dir(sweep, 'live', {
        'cur': 'gm_cur', 'mid': 'gm_mid', 'old': 'gm_old'})
    # Make stamps rank by mtime: cur newest, old oldest.
    os.utime(paths['cur'], (1000, 1000))
    os.utime(paths['cur'].with_suffix('.npz'), (1000, 1000))
    os.utime(paths['mid'], (500, 500))
    os.utime(paths['mid'].with_suffix('.npz'), (500, 500))
    os.utime(paths['old'], (100, 100))
    os.utime(paths['old'].with_suffix('.npz'), (100, 100))

    drop_pairs, by_stamp, keep_stamps = gc_cache.plan_v7_columns(
        [d], 'gm_cur', keep_vintages=2)
    assert keep_stamps == {'gm_cur', 'gm_mid'}
    dropped_npz = {npz.name for npz, _jp in drop_pairs}
    assert dropped_npz == {'old.npz'}


def test_apply_deletes_only_dropped(tmp_path, monkeypatch):
    sweep = tmp_path / 'sweep'
    _make_vintage(sweep, 'cur', 'gm_current', mtime=1000)
    _make_vintage(sweep, 'old_new', 'gm_old_new', mtime=900)
    old = _make_vintage(sweep, 'old_oldest', 'gm_old_oldest', mtime=100)

    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_current')
    monkeypatch.setattr(sys, 'argv',
                        ['gc_cache.py', '--cache-root', str(tmp_path),
                         '--keep-vintages', '2', '--apply'])
    gc_cache.main()

    assert (sweep / 'cur').exists()
    assert (sweep / 'old_new').exists()
    assert not old.exists()


def test_dry_run_deletes_nothing(tmp_path, monkeypatch):
    sweep = tmp_path / 'sweep'
    old = _make_vintage(sweep, 'old_oldest', 'gm_old_oldest', mtime=100)
    _make_vintage(sweep, 'cur', 'gm_current', mtime=1000)

    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_current')
    monkeypatch.setattr(sys, 'argv',
                        ['gc_cache.py', '--cache-root', str(tmp_path),
                         '--keep-vintages', '1'])  # no --apply
    gc_cache.main()
    assert old.exists()  # dry-run is non-destructive
