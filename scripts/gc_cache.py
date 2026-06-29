#!/usr/bin/env python
"""Version-aware GC for the gopvpsim disk caches (~/.cache/gopvpsim).

The caches never auto-prune: every gamemaster refresh writes a new vintage
and orphans the prior columns, so the on-disk cache grows without bound
(~45 GB / 140k+ sweep columns as of 2026-06-27). This tool reclaims old
vintages, keeping the current gamemaster plus the N-1 most recent others
(decision D, 2026-06-27).

Only the SWEEP cache stores its gamemaster vintage readably, so it gets
true vintage-aware pruning. The ``slayer`` and ``iv_envelope`` namespaces
bake engine+gamemaster into opaque filename hashes (no readable vintage),
so they are REPORTED, not auto-deleted — note that ``iv_envelope`` is
retired once the ML path moves onto the sweep cache (cache-rework Phase 6)
and can then be removed wholesale.

Sweep cache has TWO schema eras (cache-rework v7, 2026-06-29):
  - Legacy dirs (meta ``v`` < 7): gamemaster lived in the focal-dir KEY, so
    each gamemaster vintage minted its own dirs. These get DIR-level
    vintage pruning (keep current + N-1 recent vintages) — the original
    decision D policy.
  - v7 dirs (meta ``v`` >= 7): gamemaster is a per-COLUMN sidecar stamp, so
    a dir is gamemaster-independent and holds columns of mixed vintages. The
    DIR is always kept (dropping it = a full cold re-sim); reclamation moves
    to COLUMN granularity (keep columns at the current + N-1 recent
    gamemaster stamps; unlink older ones — the v7 analog of vintage pruning,
    and the replacement for the dir-drop that v7 removes).

Default is --dry-run (report only). Pass --apply to delete.

Usage:
  python scripts/gc_cache.py                 # report what would be pruned
  python scripts/gc_cache.py --apply         # prune (keep current + 1 prior)
  python scripts/gc_cache.py --keep-vintages 3 --apply
"""
import argparse
import json
import os
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep_cache  # noqa: E402

GOPVPSIM_CACHE = Path.home() / '.cache' / 'gopvpsim'


def _dir_size_mtime(d):
    """(total bytes, newest mtime) over all files under directory ``d``."""
    total = 0
    newest = 0.0
    for p in d.rglob('*'):
        if p.is_file():
            st = p.stat()
            total += st.st_size
            newest = max(newest, st.st_mtime)
    return total, newest


def _fmt(nbytes):
    g = nbytes / 1e9
    return f'{g:.2f} GB' if g >= 1 else f'{nbytes / 1e6:.1f} MB'


def _vintage_keep_set(vintage_mtime, current, keep_vintages):
    """Given ``{vintage: newest_mtime}``, return the set of vintages to KEEP:
    ``current`` always, plus the ``keep_vintages - 1`` most-recent others.
    Shared by dir-level (legacy) and column-level (v7) pruning."""
    others = [v for v in vintage_mtime if v != current]
    others.sort(key=lambda v: vintage_mtime[v], reverse=True)
    return {current} | set(others[:max(0, keep_vintages - 1)])


def plan_sweep(sweep_dir, current_gm, keep_vintages):
    """Plan dir-level sweep pruning. Returns (keep_dirs, drop_dirs, by_gm,
    keep_gms, v7_dirs).

    v7 dirs (meta ``v`` >= sweep_cache.CACHE_VERSION) are gamemaster-keyless
    and ALWAYS kept (reclamation is per-column — see plan_v7_columns). Dirs
    with unreadable meta are kept (best-effort: dropping a live dir is a full
    cold re-sim, so we never drop on a transient read error). Legacy dirs
    (older schema, gamemaster in the focal key) are grouped by their meta
    gamemaster vintage and pruned to current + N-1 most-recent vintages."""
    v7_dirs, unreadable_dirs = [], []
    by_gm = defaultdict(list)  # legacy only: gm -> [(focal_dir, size, mtime)]
    for focal_dir in sorted(sweep_dir.iterdir()):
        if not focal_dir.is_dir():
            continue
        try:
            meta = json.loads((focal_dir / 'meta.json').read_text())
        except Exception:
            unreadable_dirs.append(focal_dir)  # keep, best-effort
            continue
        if meta.get('v', 0) >= sweep_cache.CACHE_VERSION:
            v7_dirs.append(focal_dir)  # servable line: always keep the dir
            continue
        size, mtime = _dir_size_mtime(focal_dir)
        by_gm[meta.get('gamemaster')].append((focal_dir, size, mtime))

    # Rank legacy vintages by recency (newest member mtime).
    keep_gms = _vintage_keep_set(
        {gm: max(m for _d, _s, m in entries) for gm, entries in by_gm.items()},
        current_gm, keep_vintages)

    keep_dirs = list(v7_dirs) + list(unreadable_dirs)
    drop_dirs = []
    for gm, entries in by_gm.items():
        (keep_dirs if gm in keep_gms else drop_dirs).extend(
            d for d, _s, _m in entries)
    return keep_dirs, drop_dirs, by_gm, keep_gms, v7_dirs


def plan_v7_columns(v7_dirs, current_gm, keep_vintages):
    """Plan COLUMN-level reclamation inside v7 dirs (the v7 analog of legacy
    vintage pruning). Groups every column's ``.json`` sidecar by its
    gamemaster STAMP, keeps current + N-1 most-recent stamp vintages, and
    returns (drop_pairs, by_stamp_count, keep_stamps) where drop_pairs is a
    list of (npz_path, json_path) for columns provably non-servable now AND
    outside the bless window. A column with an unreadable/absent gamemaster
    stamp is KEPT (best-effort)."""
    cols = []  # (stamp, mtime, npz, json)
    for d in v7_dirs:
        for jp in d.glob('*.json'):
            if jp.name == 'meta.json':
                continue
            stamp = sweep_cache.SweepCache.read_gm_stamp(jp)
            if stamp is None:
                continue  # keep best-effort (don't risk a live/odd column)
            npz = jp.with_suffix('.npz')
            try:
                mtime = jp.stat().st_mtime
            except OSError:
                continue
            cols.append((stamp, mtime, npz, jp))

    stamp_mtime = {}
    for stamp, mtime, _n, _j in cols:
        stamp_mtime[stamp] = max(stamp_mtime.get(stamp, 0.0), mtime)
    keep_stamps = _vintage_keep_set(stamp_mtime, current_gm, keep_vintages)

    drop_pairs = [(npz, jp) for stamp, _m, npz, jp in cols
                  if stamp not in keep_stamps]
    by_stamp_count = Counter(stamp for stamp, _m, _n, _j in cols)
    return drop_pairs, by_stamp_count, keep_stamps


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true',
                    help='actually delete (default: dry-run report)')
    ap.add_argument('--keep-vintages', type=int, default=2,
                    help='total gamemaster vintages to keep, including the '
                         'current one (default 2 = current + 1 prior)')
    ap.add_argument('--cache-root', default=None,
                    help='override ~/.cache/gopvpsim (for tests)')
    a = ap.parse_args()
    root = Path(a.cache_root) if a.cache_root else GOPVPSIM_CACHE
    current_gm = sweep_cache.gamemaster_hash()
    print(f"cache root: {root}")
    print(f"current gamemaster: {current_gm}  keep-vintages={a.keep_vintages}")

    sweep_dir = root / 'sweep'
    if sweep_dir.is_dir():
        keep_dirs, drop_dirs, by_gm, keep_gms, v7_dirs = plan_sweep(
            sweep_dir, current_gm, a.keep_vintages)
        n_legacy = sum(len(v) for v in by_gm.values())
        print(f"\nsweep/: {len(v7_dirs)} v7 dir(s) (always kept), "
              f"{n_legacy} legacy dir(s) across {len(by_gm)} vintage(s)")
        for gm, entries in sorted(by_gm.items(),
                                  key=lambda kv: max(m for _d, _s, m in kv[1]),
                                  reverse=True):
            size = sum(s for _d, s, _m in entries)
            tag = ' KEEP' if gm in keep_gms else ' DROP'
            cur = ' (current)' if gm == current_gm else ''
            print(f"  legacy {tag} {str(gm)[:12]:>12}{cur}: "
                  f"{len(entries)} dirs, {_fmt(size)}")
        drop_bytes = sum(_dir_size_mtime(d)[0] for d in drop_dirs)
        print(f"  -> {'DELETING' if a.apply else 'would delete'} "
              f"{len(drop_dirs)} legacy dirs, {_fmt(drop_bytes)}")
        if a.apply:
            for d in drop_dirs:
                shutil.rmtree(d, ignore_errors=True)

        # v7 column-level reclaim: drop columns at stale gamemaster stamps
        # (outside the current + N-1 keep window) — the v7 analog of legacy
        # vintage pruning, since a gamemaster change no longer mints new dirs.
        if v7_dirs:
            drop_pairs, by_stamp, keep_stamps = plan_v7_columns(
                v7_dirs, current_gm, a.keep_vintages)
            print(f"\nsweep/ v7 columns: {sum(by_stamp.values())} across "
                  f"{len(by_stamp)} gamemaster stamp(s)")
            for stamp, n in by_stamp.most_common():
                tag = ' KEEP' if stamp in keep_stamps else ' DROP'
                cur = ' (current)' if stamp == current_gm else ''
                print(f"  col {tag} {str(stamp)[:12]:>12}{cur}: {n} columns")
            col_bytes = 0
            for npz, _jp in drop_pairs:
                try:
                    col_bytes += npz.stat().st_size
                except OSError:
                    pass
            print(f"  -> {'DELETING' if a.apply else 'would delete'} "
                  f"{len(drop_pairs)} stale columns, ~{_fmt(col_bytes)}")
            if a.apply:
                for npz, jp in drop_pairs:
                    for p in (npz, jp):
                        try:
                            p.unlink()
                        except OSError:
                            pass
    else:
        print("\nsweep/: (none)")

    # slayer/ and iv_envelope/: vintage not readable from the files -> report
    # only. iv_envelope is retired once the ML path uses the sweep cache.
    for ns in ('slayer', 'iv_envelope'):
        d = root / ns
        if d.is_dir():
            size, _ = _dir_size_mtime(d)
            n = sum(1 for _ in d.iterdir())
            print(f"\n{ns}/: {n} entries, {_fmt(size)} "
                  f"(report-only — vintage not stored; prune by hand if needed)")


if __name__ == '__main__':
    main()
