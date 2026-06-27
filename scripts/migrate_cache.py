#!/usr/bin/env python
"""Selective sweep-cache invalidation after a localized engine fix.

The sweep cache stamps each column with the engine hash that produced it
(v6, in the .json sidecar). After a localized engine change, most columns
are provably unaffected and only a characterizable subset changed. This
tool BLESSES the unaffected columns (rewrites their stamp to the current
engine, so a re-dive serves them warm) and DELETES the affected ones (so
they re-sim cold), instead of cold-rebaking the whole cache.

Soundness rests on the predicate, which must be PROVEN, not guessed:

  shadow_xor  — bug #1 (the fire_now CMP gate using cmp_atk instead of
                shadow-boosted atk). A matchup's score changes ONLY when
                exactly one side is shadow. both-non-shadow: cmp_atk == atk
                on both sides, so the gate boolean is unchanged. both-shadow:
                dividing both atks by 1.2 preserves the `>` inequality, so
                the gate boolean is unchanged. Hence affected = (focal.shadow
                XOR opp.shadow). Proof pinned by tests/test_migrate_cache.py
                and the engine test tests/test_fire_now_cmp_shadow.py.

Preconditions enforced here:
  - Only columns whose stamp == --from-engine are touched (scopes the
    predicate to the exact characterized delta; columns from other engine
    vintages are left alone).
  - Only focal dirs whose gamemaster == the current gamemaster are touched
    (gamemaster lives in the focal-dir key, so this guarantees the from->to
    delta is engine-only — the predicate models nothing about gamemaster).

Default is --dry-run (report only). Pass --apply to write.

Usage:
  python scripts/migrate_cache.py --list-stamps
  python scripts/migrate_cache.py --from-engine <oldhash> [--predicate shadow_xor]
  python scripts/migrate_cache.py --from-engine <oldhash> --apply
"""
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep_cache  # noqa: E402


# affected(focal_fields, col_fields) -> True if the engine change changed
# this column's scores (must be re-simmed); False if provably unchanged.
PREDICATES = {
    'shadow_xor': lambda f, c: bool(f.get('shadow')) != bool(c.get('shadow')),
}


def _iter_columns(cache_dir):
    """Yield (focal_dir, meta_fields, json_path, stamp, col_fields) for every
    stored column under ``cache_dir``."""
    cache_dir = Path(cache_dir)
    if not cache_dir.exists():
        return
    for focal_dir in sorted(cache_dir.iterdir()):
        if not focal_dir.is_dir():
            continue
        meta_p = focal_dir / 'meta.json'
        try:
            meta = json.loads(meta_p.read_text())
        except Exception:
            continue
        for jp in sorted(focal_dir.glob('*.json')):
            if jp.name == 'meta.json':
                continue
            try:
                side = json.loads(jp.read_text())
            except Exception:
                continue
            yield focal_dir, meta, jp, side.get('engine'), side.get('col')


def list_stamps(cache_dir):
    counts = Counter()
    for _fd, _meta, _jp, stamp, _col in _iter_columns(cache_dir):
        counts[stamp] += 1
    cur = sweep_cache.engine_hash()
    print(f"current engine hash: {cur}")
    if not counts:
        print("(no columns found)")
        return
    print(f"{'count':>8}  engine stamp")
    for stamp, n in counts.most_common():
        tag = '  <- current' if stamp == cur else ''
        print(f"{n:>8}  {stamp}{tag}")


def migrate(cache_dir, from_engine, predicate_name, apply):
    affected = PREDICATES[predicate_name]
    to_engine = sweep_cache.engine_hash()
    cur_gm = sweep_cache.gamemaster_hash()
    if from_engine == to_engine:
        print(f"--from-engine {from_engine} equals the current engine; "
              "nothing to migrate.")
        return
    blessed = deleted = skipped_gm = skipped_other = 0
    for _fd, meta, jp, stamp, col in _iter_columns(cache_dir):
        if meta.get('gamemaster') != cur_gm:
            skipped_gm += 1
            continue
        if stamp != from_engine:
            skipped_other += 1
            continue
        npz = jp.with_suffix('.npz')
        if affected(meta, col):
            deleted += 1
            if apply:
                for p in (npz, jp):
                    try:
                        p.unlink()
                    except OSError:
                        pass
        else:
            blessed += 1
            if apply:
                # Bless: rewrite only the tiny sidecar stamp; the .npz (the
                # old-engine scores, provably still valid) is left untouched.
                tmp = jp.with_name(jp.name + '.tmp')
                tmp.write_text(json.dumps({'engine': to_engine, 'col': col},
                                          indent=1, sort_keys=True))
                os.replace(tmp, jp)
    mode = 'APPLIED' if apply else 'DRY-RUN (use --apply to write)'
    print(f"predicate={predicate_name}  from={from_engine}  to={to_engine}")
    print(f"  blessed (unaffected, served warm): {blessed}")
    print(f"  deleted (affected, will re-sim):   {deleted}")
    print(f"  skipped (other engine vintage):    {skipped_other}")
    print(f"  skipped (other gamemaster):        {skipped_gm}")
    print(f"  {mode}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--list-stamps', action='store_true',
                    help='report the distinct engine stamps in the cache and exit')
    ap.add_argument('--from-engine',
                    help='only migrate columns stamped with this engine hash '
                         '(the pre-fix hash; see --list-stamps)')
    ap.add_argument('--predicate', default='shadow_xor',
                    choices=sorted(PREDICATES),
                    help='which proven invalidation predicate to apply '
                         '(default: %(default)s)')
    ap.add_argument('--apply', action='store_true',
                    help='actually write changes (default: dry-run)')
    ap.add_argument('--cache-dir', default=None,
                    help='override the sweep cache dir (for tests)')
    a = ap.parse_args()
    cache_dir = a.cache_dir or sweep_cache.CACHE_DIR

    if a.list_stamps:
        list_stamps(cache_dir)
        return
    if not a.from_engine:
        ap.error('--from-engine is required (or use --list-stamps)')
    migrate(cache_dir, a.from_engine, a.predicate, a.apply)


if __name__ == '__main__':
    main()
