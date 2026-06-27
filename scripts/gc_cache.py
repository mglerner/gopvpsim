#!/usr/bin/env python
"""Version-aware GC for the gopvpsim disk caches (~/.cache/gopvpsim).

The caches never auto-prune: every gamemaster refresh writes a new vintage
and orphans the prior columns, so the on-disk cache grows without bound
(~45 GB / 140k+ sweep columns as of 2026-06-27). This tool reclaims old
vintages, keeping the current gamemaster plus the N-1 most recent others
(decision D, 2026-06-27).

Only the SWEEP cache stores its gamemaster vintage readably (focal-dir
``meta.json``), so it gets true vintage-aware pruning. The ``slayer`` and
``iv_envelope`` namespaces bake engine+gamemaster into opaque filename
hashes (no readable vintage), so they are REPORTED, not auto-deleted —
note that ``iv_envelope`` is retired once the ML path moves onto the sweep
cache (cache-rework Phase 6) and can then be removed wholesale.

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
from collections import defaultdict
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


def plan_sweep(sweep_dir, current_gm, keep_vintages):
    """Group sweep focal dirs by gamemaster vintage; return (keep_dirs,
    drop_dirs, per-vintage stats). The current gamemaster is always kept;
    among the other vintages the ``keep_vintages - 1`` most recent (by
    newest file mtime) are kept, the rest dropped."""
    by_gm = defaultdict(list)  # gm -> [(focal_dir, size, mtime)]
    for focal_dir in sorted(sweep_dir.iterdir()):
        if not focal_dir.is_dir():
            continue
        try:
            gm = json.loads((focal_dir / 'meta.json').read_text()).get('gamemaster')
        except Exception:
            gm = None  # unreadable meta -> its own bucket; never "current"
        size, mtime = _dir_size_mtime(focal_dir)
        by_gm[gm].append((focal_dir, size, mtime))

    # Rank non-current vintages by recency (newest member mtime).
    others = [gm for gm in by_gm if gm != current_gm]
    others.sort(key=lambda gm: max(m for _d, _s, m in by_gm[gm]), reverse=True)
    keep_gms = {current_gm} | set(others[:max(0, keep_vintages - 1)])

    keep_dirs, drop_dirs = [], []
    for gm, entries in by_gm.items():
        (keep_dirs if gm in keep_gms else drop_dirs).extend(
            d for d, _s, _m in entries)
    return keep_dirs, drop_dirs, by_gm, keep_gms


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
        keep_dirs, drop_dirs, by_gm, keep_gms = plan_sweep(
            sweep_dir, current_gm, a.keep_vintages)
        print(f"\nsweep/: {sum(len(v) for v in by_gm.values())} focal dirs "
              f"across {len(by_gm)} gamemaster vintage(s)")
        for gm, entries in sorted(by_gm.items(),
                                  key=lambda kv: max(m for _d, _s, m in kv[1]),
                                  reverse=True):
            size = sum(s for _d, s, _m in entries)
            tag = ' KEEP' if gm in keep_gms else ' DROP'
            cur = ' (current)' if gm == current_gm else ''
            print(f"  {tag} {str(gm)[:12]:>12}{cur}: "
                  f"{len(entries)} dirs, {_fmt(size)}")
        drop_bytes = sum(_dir_size_mtime(d)[0] for d in drop_dirs)
        print(f"  -> {'DELETING' if a.apply else 'would delete'} "
              f"{len(drop_dirs)} dirs, {_fmt(drop_bytes)}")
        if a.apply:
            for d in drop_dirs:
                shutil.rmtree(d, ignore_errors=True)
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
