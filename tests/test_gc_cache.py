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


# ---- reversible GC: --archive-dir / --restore-archive ----

def test_archive_dir_moves_not_deletes_and_restores(tmp_path, monkeypatch):
    """--archive-dir moves dropped dirs into the archive (not delete),
    preserving the path relative to the cache root; --restore-archive puts
    them back byte-for-byte. The kept current vintage is untouched."""
    root = tmp_path / 'cache'        # archive must be OUTSIDE the cache root
    sweep = root / 'sweep'
    cur = _make_vintage(sweep, 'cur', 'gm_current', mtime=1000)
    old = _make_vintage(sweep, 'old_oldest', 'gm_old_oldest', mtime=100)
    old_bytes = (old / 'col.npz').read_bytes()
    archive = tmp_path / 'archive'

    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_current')
    monkeypatch.setattr(sys, 'argv',
                        ['gc_cache.py', '--cache-root', str(root),
                         '--keep-vintages', '1', '--apply',
                         '--archive-dir', str(archive)])
    gc_cache.main()

    # Dropped dir MOVED, not deleted; current vintage kept; path preserved.
    assert not old.exists()
    assert cur.exists()
    archived = archive / 'sweep' / 'old_oldest'
    assert archived.is_dir()
    assert (archived / 'col.npz').read_bytes() == old_bytes  # intact
    assert (archive / 'MANIFEST.json').exists()

    # Restore round-trips it back in place.
    monkeypatch.setattr(sys, 'argv',
                        ['gc_cache.py', '--cache-root', str(root),
                         '--restore-archive', str(archive)])
    gc_cache.main()
    assert old.exists()
    assert (old / 'col.npz').read_bytes() == old_bytes
    assert not (archive / 'sweep' / 'old_oldest').exists()  # left the archive


def test_archive_dir_requires_apply(tmp_path, monkeypatch):
    """--archive-dir without --apply is a dry-run: nothing moves."""
    root = tmp_path / 'cache'
    sweep = root / 'sweep'
    old = _make_vintage(sweep, 'old', 'gm_old', mtime=100)
    _make_vintage(sweep, 'cur', 'gm_current', mtime=1000)
    archive = tmp_path / 'archive'

    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_current')
    monkeypatch.setattr(sys, 'argv',
                        ['gc_cache.py', '--cache-root', str(root),
                         '--keep-vintages', '1', '--archive-dir', str(archive)])
    gc_cache.main()
    assert old.exists()            # untouched
    assert not archive.exists()    # nothing written


def test_archive_dir_v7_columns_roundtrip(tmp_path, monkeypatch):
    """The PRIMARY (v7 column-level) reclaim path archives + restores stale
    columns byte-for-byte; current-stamp columns stay put."""
    root = tmp_path / 'cache'
    sweep = root / 'sweep'
    d, paths = _make_v7_dir(sweep, 'live', {'cur': 'gm_cur', 'old': 'gm_old'})
    os.utime(paths['cur'], (1000, 1000))
    os.utime(paths['cur'].with_suffix('.npz'), (1000, 1000))
    os.utime(paths['old'], (100, 100))
    os.utime(paths['old'].with_suffix('.npz'), (100, 100))
    old_npz_bytes = (d / 'old.npz').read_bytes()
    archive = tmp_path / 'archive'

    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_cur')
    monkeypatch.setattr(sys, 'argv',
                        ['gc_cache.py', '--cache-root', str(root),
                         '--keep-vintages', '1', '--apply',
                         '--archive-dir', str(archive)])
    gc_cache.main()
    # Stale column (npz+json) moved out; current column stays.
    assert not (d / 'old.npz').exists() and not (d / 'old.json').exists()
    assert (d / 'cur.npz').exists() and (d / 'cur.json').exists()
    assert (archive / 'sweep' / 'live' / 'old.npz').read_bytes() == old_npz_bytes

    monkeypatch.setattr(sys, 'argv',
                        ['gc_cache.py', '--cache-root', str(root),
                         '--restore-archive', str(archive)])
    gc_cache.main()
    assert (d / 'old.npz').read_bytes() == old_npz_bytes
    assert (d / 'old.json').exists()


def test_rearchive_into_nonempty_archive_refuses(tmp_path, monkeypatch):
    """Re-archiving a same-named dir into a used archive must RAISE, not nest
    (the shutil.move-into-existing-dir corruption the red-team found)."""
    root = tmp_path / 'cache'
    sweep = root / 'sweep'
    archive = tmp_path / 'archive'
    # Pre-seed the archive with a colliding path.
    (archive / 'sweep' / 'old').mkdir(parents=True)
    (archive / 'sweep' / 'old' / 'col.npz').write_bytes(b'prior')
    _make_vintage(sweep, 'old', 'gm_old', mtime=100)
    _make_vintage(sweep, 'cur', 'gm_current', mtime=1000)

    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_current')
    monkeypatch.setattr(sys, 'argv',
                        ['gc_cache.py', '--cache-root', str(root),
                         '--keep-vintages', '1', '--apply',
                         '--archive-dir', str(archive)])
    with __import__('pytest').raises(FileExistsError):
        gc_cache.main()
    # The cache dir was NOT removed (the failed move left it in place).
    assert (sweep / 'old').exists()


def test_restore_refuses_to_clobber(tmp_path, monkeypatch):
    """Restore must abort (move nothing) if a destination already exists — a
    re-dive may have re-created that path with current data."""
    root = tmp_path / 'cache'
    archive = tmp_path / 'archive'
    # Archive holds a stale column; the cache already has a fresh one there.
    (archive / 'sweep' / 'live').mkdir(parents=True)
    (archive / 'sweep' / 'live' / 'c.npz').write_bytes(b'STALE')
    (root / 'sweep' / 'live').mkdir(parents=True)
    (root / 'sweep' / 'live' / 'c.npz').write_bytes(b'FRESH')

    monkeypatch.setattr(sys, 'argv',
                        ['gc_cache.py', '--cache-root', str(root),
                         '--restore-archive', str(archive)])
    with __import__('pytest').raises(FileExistsError):
        gc_cache.main()
    # Fresh data untouched; stale copy still in the archive.
    assert (root / 'sweep' / 'live' / 'c.npz').read_bytes() == b'FRESH'
    assert (archive / 'sweep' / 'live' / 'c.npz').read_bytes() == b'STALE'


def test_archive_dir_inside_root_is_rejected(tmp_path, monkeypatch):
    """The footgun guard: an archive dir inside the cache root is refused
    (else GC would archive into the cache it is pruning)."""
    root = tmp_path / 'cache'
    sweep = root / 'sweep'
    _make_vintage(sweep, 'old', 'gm_old', mtime=100)
    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_current')
    monkeypatch.setattr(sys, 'argv',
                        ['gc_cache.py', '--cache-root', str(root),
                         '--keep-vintages', '1', '--apply',
                         '--archive-dir', str(root / 'inside')])
    with __import__('pytest').raises(SystemExit):
        gc_cache.main()
