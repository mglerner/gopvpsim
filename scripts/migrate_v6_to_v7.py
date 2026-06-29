#!/usr/bin/env python
"""One-shot sweep-cache re-key migration: v6 dirs -> v7 dirs (cache-rework v7,
2026-06-29).

v7 moved the gamemaster hash OUT of the focal-dir key into a per-COLUMN
sidecar stamp (and narrowed it to the sim-relevant {pokemon,moves} subset).
That changes every focal-dir hash, so the existing v6 columns would be
orphaned (a cold re-dive). This tool RE-KEYS them into their v7 dirs so they
stay warm.

It is a pure MECHANICAL re-key — it makes NO claim that the columns are valid
under the current gamemaster. It stamps each column with the narrowed hash of
the gamemaster it was ACTUALLY baked under (supplied via --old-gamemaster-file).
The semantic step (blessing those columns across the old->current gamemaster
delta) is the SEPARATE, auditable `migrate_cache.py --from-gamemaster` pass,
which proves the delta touches nothing the columns read.

Safety (per the v7 adversarial review):
  - COPY, never move: the v6 source dir is left intact (GC reclaims it later as
    a legacy vintage). An interrupted run never loses the only copy.
  - Atomic dir publish: each v7 dir is built under a ``.tmp-<pid>`` name and
    os.replace'd into place only once complete, so a partial dir is never
    visible to a dive.
  - Idempotent / resumable: a focal whose v7 target dir already exists is
    SKIPPED (a prior run, or a live dive, already produced it — and a live
    dive's columns are >= as fresh, so we never clobber them).
  - Lockfile: refuses to run if another migration holds CACHE_DIR/.migrate.lock.
    DO NOT run dives concurrently with this migration.

Default is --dry-run. Pass --apply to write.

Usage:
  python scripts/migrate_v6_to_v7.py --old-gamemaster-file <687e blob> \
      --from-full-hash 687e17edc066 [--apply]
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep_cache  # noqa: E402


def _full_hash(gm):
    """The OLD whole-file hash (matches a v6 meta's 'gamemaster' field:
    md5 of json.dumps(json.loads(text)), as data.py reserializes)."""
    return hashlib.md5(json.dumps(gm).encode()).hexdigest()[:12]


def _narrow_hash(gm):
    blob = json.dumps(sweep_cache.gamemaster_subset(gm), sort_keys=True,
                      separators=(',', ':'))
    return hashlib.md5(blob.encode()).hexdigest()[:12]


def _v7_focal_fields(meta):
    """Rebuild the canonical v7 focal-key dict from a v6 meta, via the real
    API so the key structure is guaranteed identical to a live v7 dive."""
    return sweep_cache.focal_key_fields(
        species=meta['species'], league=meta['league'],
        shadow=meta['shadow'], fast_id=meta['fast'],
        charged_ids=meta['charged'], iv_floor=meta.get('iv_floor'),
        shield_scenarios=[tuple(s) for s in meta['scenarios']],
        bait_mode=meta['bait'], energy_lead=meta.get('energy_lead', 0),
        focal_max_level=meta.get('focal_max_level'))


def _v7_dir_for(cache_dir, meta):
    fields = _v7_focal_fields(meta)
    species_slug = (fields['species'].replace(' ', '_')
                    .replace('(', '').replace(')', ''))
    return (Path(cache_dir) /
            f"{species_slug}_{fields['league']}_"
            f"{sweep_cache._key_hash(fields, 12)}"), fields


def migrate(cache_dir, old_gm_file, from_full_hash, apply):
    cache_dir = Path(cache_dir)
    old_gm = json.loads(Path(old_gm_file).read_text())
    actual_full = _full_hash(old_gm)
    if actual_full != from_full_hash:
        print(f"ERROR: --old-gamemaster-file full-hashes to {actual_full}, "
              f"not --from-full-hash {from_full_hash}. Refusing.")
        sys.exit(2)
    narrow = _narrow_hash(old_gm)
    print(f"re-key: v6 gamemaster {from_full_hash} (full) -> per-column stamp "
          f"{narrow} (narrowed), CACHE_VERSION -> {sweep_cache.CACHE_VERSION}")

    lock = cache_dir / '.migrate.lock'
    if apply:
        if lock.exists():
            print(f"ERROR: {lock} exists — another migration running? Refusing.")
            sys.exit(2)
        cache_dir.mkdir(parents=True, exist_ok=True)
        lock.write_text(f'pid {os.getpid()}')
    try:
        rekeyed = skipped_exists = skipped_other_gm = cols = 0
        other_gm = {}
        for fd in sorted(cache_dir.iterdir()):
            if not fd.is_dir() or fd.name.startswith('.tmp-'):
                continue
            try:
                meta = json.loads((fd / 'meta.json').read_text())
            except Exception:
                continue
            if meta.get('v') != 6:
                continue  # only v6 dirs are re-keyed here
            if meta.get('gamemaster') != from_full_hash:
                other_gm[meta.get('gamemaster')] = other_gm.get(
                    meta.get('gamemaster'), 0) + 1
                skipped_other_gm += 1
                continue
            target, _fields = _v7_dir_for(cache_dir, meta)
            if target.exists():
                skipped_exists += 1
                continue
            rekeyed += 1
            cols += sum(1 for p in fd.glob('*.json') if p.name != 'meta.json')
            if apply:
                _rekey_one(fd, meta, target, narrow)
        print(f"\n  v6 dirs re-keyed:        {rekeyed}  ({cols} columns)")
        print(f"  skipped (v7 target exists): {skipped_exists}")
        print(f"  skipped (other gamemaster): {skipped_other_gm} "
              f"{dict(other_gm) if other_gm else ''}")
        print(f"  {'APPLIED' if apply else 'DRY-RUN (use --apply to write)'}")
        if not apply:
            print("\n  Next (after --apply): bless the re-keyed columns across "
                  "the gamemaster delta:\n"
                  f"    python scripts/migrate_cache.py --from-gamemaster {narrow} "
                  f"--old-gamemaster-file {old_gm_file} --apply")
    finally:
        if apply and lock.exists():
            lock.unlink()


def _rekey_one(src_dir, meta, target, narrow):
    """Build target as a fully-formed v7 dir under a .tmp name (COPY columns,
    rewrite sidecars), then atomically publish it."""
    tmp = target.with_name(f'.tmp-{os.getpid()}-{target.name}')
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    # v7 meta = canonical v7 focal fields (no gamemaster, v=7).
    tmp_meta = _v7_focal_fields(meta)
    (tmp / 'meta.json').write_text(json.dumps(tmp_meta, indent=1,
                                              sort_keys=True))
    for jp in src_dir.glob('*.json'):
        if jp.name == 'meta.json':
            continue
        try:
            side = json.loads(jp.read_text())
        except Exception:
            continue
        npz = jp.with_suffix('.npz')
        if not npz.exists():
            continue  # skip a half-written/orphaned sidecar
        shutil.copy2(npz, tmp / npz.name)  # COPY the scores (never move)
        (tmp / jp.name).write_text(json.dumps(
            {'engine': side.get('engine'), 'gamemaster': narrow,
             'col': side.get('col')}, indent=1, sort_keys=True))
    os.replace(tmp, target)  # atomic publish of the complete dir


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--old-gamemaster-file', required=True,
                    help='the gamemaster.json the v6 columns were baked under')
    ap.add_argument('--from-full-hash', required=True,
                    help="the v6 meta 'gamemaster' value to migrate (whole-file "
                         "md5[:12]); must match --old-gamemaster-file")
    ap.add_argument('--apply', action='store_true',
                    help='actually write (default: dry-run)')
    ap.add_argument('--cache-dir', default=None,
                    help='override the sweep cache dir (for tests)')
    a = ap.parse_args()
    migrate(a.cache_dir or sweep_cache.CACHE_DIR, a.old_gamemaster_file,
            a.from_full_hash, a.apply)


if __name__ == '__main__':
    main()
