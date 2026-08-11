#!/usr/bin/env python
"""Worlds 2026 ship gate (plan: guardrails + build-order item 5).

Hard-fails on any Worlds-surface inconsistency; registered in
run_ship_gates.SHIP_GATES so every publish path runs it. Checks, per
the {layer} x {lens} rule (the layer that RUNS and the lens that asks
"does it survive"):

[1] Tier-1 manifest present, stamps CURRENT (engine/gamemaster/
    producer), coverage exactly the 1,860-key worklist (== is the
    documented testing-policy exception: derived from the same meta).
[2] Tier-2 manifest (when present) stamps current; every entry's file
    exists; deferred list == amber pairs without full grids.
[3] Rendered surfaces exist and agree: hub + 31 cheat sheets +
    worlds-cmp + worlds-explorer; one pair page per fully-baked amber
    pair, no orphans; hub FN numbers match a fresh worlds_fn.fn_rate().
[4] No artifact matches *_great.toml (iOS bundler collision).

Exits 0 quiet-ish on success, 1 with the failure list otherwise.
``--quiet`` prints only failures.
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from build_website_index import WEBSITE_DIR  # noqa: E402
import worlds_planes as wp  # noqa: E402
import worlds_render_data as wrd  # noqa: E402


def check(failures, ok, msg):
    if not ok:
        failures.append(msg)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quiet', '-q', action='store_true')
    ap.add_argument('--website-dir', default=None)
    args = ap.parse_args()
    website = Path(args.website_dir) if args.website_dir else WEBSITE_DIR
    failures = []
    say = (lambda *a: None) if args.quiet else print

    # [1] Tier-1 manifest + stamps + coverage
    meta = wrd.load_meta()
    entries = meta['entries']
    manifest = wp.load_manifest()
    if check(failures, manifest is not None, 'Tier-1 manifest missing'):
        mism = wp.stamp_mismatches(manifest)
        check(failures, not mism, f'Tier-1 stamps stale: {mism}')
        expected = wp.expected_tier1_keys(entries)
        have = set(manifest.get('entries', {}))
        check(failures, have == expected,
              f'Tier-1 coverage {len(have)}/{len(expected)} '
              f'(missing {len(expected - have)}, extra {len(have - expected)})')
        missing_npz = [k for k, e in manifest.get('entries', {}).items()
                      if not wp.out_path(e['file']).exists()]
        check(failures, not missing_npz,
              f'Tier-1 manifest entries without npz: {len(missing_npz)}')
        say(f'[1] Tier-1: {len(have)} planes, stamps current')

    # [2] Tier-2 (optional but must be sound when present)
    import worlds_tier2 as t2
    t2m = t2.load_manifest()
    baked_pairs = set()
    if t2m is not None:
        mism = t2.stamp_mismatches(t2m)
        check(failures, not mism, f'Tier-2 stamps stale: {mism}')
        missing = [k for k, e in t2m.get('entries', {}).items()
                   if not wp.out_path(e['file'], t2.TIER2_DIR).exists()]
        check(failures, not missing,
              f'Tier-2 manifest entries without npz: {len(missing)}')
        cells = wrd.build_all_cells(entries)
        amber = {tuple(sorted(k)) for k, c in cells.items()
                 if not c.missing and c.amber}
        by_pair = {}
        for k in t2m.get('entries', {}):
            f, o, _b = k.split('|')
            p = tuple(sorted((f, o)))
            by_pair[p] = by_pair.get(p, 0) + 1
        baked_pairs = {p for p, n in by_pair.items()
                       if n == 4 and p in amber}
        deferred = {tuple(p) for p in t2m.get('deferred', [])}
        check(failures, deferred == amber - baked_pairs,
              f'Tier-2 deferred list drift: {len(deferred)} listed, '
              f'{len(amber - baked_pairs)} actual')
        say(f'[2] Tier-2: {len(by_pair)} pairs, {len(baked_pairs)} '
            f'amber fully baked, {len(deferred)} deferred')

    # [3] Rendered surfaces
    hub = website / 'worlds.html'
    if check(failures, hub.exists(), 'worlds.html missing'):
        hub_text = hub.read_text()
        for e in entries:
            p = website / f'worlds-{e["species_id"]}.html'
            check(failures, p.exists(), f'{p.name} missing')
        # CMP board + explorer must match a FRESH render of the current
        # meta/manifest -- existence alone would pass a stale page after
        # a meta edit + partial rebuild (verify catch, 2026-08-11).
        # Renders are deterministic (ordered dicts, repr'd floats).
        import build_worlds_cmp
        import build_worlds_explorer
        for extra, fresh in (
                ('worlds-cmp.html',
                 lambda: build_worlds_cmp.render_cmp_board(meta, manifest)),
                ('worlds-explorer.html',
                 lambda: build_worlds_explorer.render_explorer(meta,
                                                               manifest))):
            p = website / extra
            if check(failures, p.exists(), f'{extra} missing'):
                check(failures, p.read_text() == fresh(),
                      f'{extra} is stale vs a fresh render')
        on_disk = {p.name for p in website.glob('worlds-pair-*.html')}
        expected_pages = {
            f'worlds-pair-{a}--{b}.html' for a, b in baked_pairs}
        check(failures, on_disk == expected_pages,
              f'pair pages drift: {len(on_disk)} on disk, '
              f'{len(expected_pages)} expected '
              f'(orphans {sorted(on_disk - expected_pages)[:3]}, '
              f'missing {sorted(expected_pages - on_disk)[:3]})')
        if t2m is not None:
            import worlds_fn
            fn = worlds_fn.fn_rate()
            if fn:
                check(failures,
                      f'<strong>{fn["fn"]}</strong> show' in hub_text
                      and f'of {fn["n"]} sampled clean' in hub_text,
                      'hub FN block does not match a fresh fn_rate()')
        say(f'[3] surfaces: hub + {len(entries)} sheets + cmp + explorer '
            f'+ {len(on_disk)} pair pages')

    # [4] bundler-collision glob
    bad = list(REPO.glob('worlds/**/*_great.toml'))
    check(failures, not bad, f'*_great.toml under worlds/: {bad}')

    if failures:
        print('verify_worlds: FAIL')
        for f in failures:
            print('  -', f)
        return 1
    say('verify_worlds: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
