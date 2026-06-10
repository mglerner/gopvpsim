#!/usr/bin/env python
"""Verify signature-dedup exactness: full IV sweep both ways, assert equality.

For each species, runs iv_sweep twice — signature dedup ON (the
default sweep path since arc S3) and OFF (one sim per stat profile per
opponent) — and asserts the per-IV, per-opponent, per-scenario score
arrays are EXACTLY equal (raw floats, not rounded). Also reports the
measured dedup factor and wall-clock speedup.

This is the end-to-end proof that grouping by damage signature
(deep_dive_signature.py) never changes a single score. Run it after
any change to the signature components (damage tables, CMP handling,
stage-axis movability, form-change stats).

Usage:
    # Default verification set (Tinkaton / Azumarill / Aegislash (Shield),
    # great league, top-20 opponents + Aegislash (Shield) for opp-side
    # form coverage, all 9 shield scenarios):
    python scripts/verify_signature_dedup.py

    # Quick smoke (fewer opponents, even-shield scenarios only):
    python scripts/verify_signature_dedup.py --opponents 6 --scenarios even

    # Single species, both bait modes:
    python scripts/verify_signature_dedup.py --species Tinkaton \
        --modes pvpoke,pvpoke:nobait
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gopvpsim.data import get_default_moveset  # noqa: E402

import deep_dive  # noqa: E402
from deep_dive_logging import init_logger  # noqa: E402

ALL_NINE = [(a, b) for a in range(3) for b in range(3)]
EVEN = [(0, 0), (1, 1), (2, 2)]

DEFAULT_SPECIES = ['Tinkaton', 'Azumarill', 'Aegislash (Shield)']


def build_opponents(league, n_opp, extra):
    opponents = deep_dive.get_top_opponents(league, n_opp)
    for e in extra:
        if e and e not in opponents:
            opponents.append(e)
    names, movesets = [], []
    for opp in opponents:
        try:
            fast, charged = get_default_moveset(opp, league=league)
        except (KeyError, ValueError):
            print(f"  (skipping opponent {opp}: no default moveset)")
            continue
        names.append(opp)
        movesets.append((fast, charged))
    return names, movesets


def verify_species(species, league, opponents, opp_movesets, scenarios,
                   mode, shadow=False):
    fast, charged = get_default_moveset(species, league=league, shadow=shadow)
    print(f"\n=== {species} ({league}, mode={mode}) — "
          f"{fast} / {', '.join(charged)} — {len(opponents)} opponents, "
          f"{len(scenarios)} scenarios ===")

    runs = {}
    for dedup in (True, False):
        label = 'dedup' if dedup else 'per-profile'
        t0 = time.time()
        results, n_sims, cs, cm = deep_dive.iv_sweep(
            species, fast, charged, league, shadow,
            opponents, opp_movesets, scenarios,
            opp_iv_mode=mode, signature_dedup=dedup)
        elapsed = time.time() - t0
        print(f"  {label:12s}: {n_sims:>9,} sims in {elapsed:7.1f}s "
              f"({n_sims/elapsed:,.0f} sims/s)")
        runs[dedup] = (results, n_sims, cs, cm, elapsed)

    res_on, sims_on, cs_on, cm_on, t_on = runs[True]
    res_off, sims_off, cs_off, cm_off, t_off = runs[False]

    # Canonical (rounded, canonical-IV-order) arrays must match exactly.
    assert cm_on == cm_off, "canonical_meta mismatch"
    n_diff = sum(1 for a, b in zip(cs_on, cs_off) if a != b)
    assert len(cs_on) == len(cs_off)

    # Raw per-IV scores (unrounded floats) must also match exactly.
    def keyed(results):
        return {(r['atk_iv'], r['def_iv'], r['sta_iv']): r['per_opp']
                for r in results}
    k_on, k_off = keyed(res_on), keyed(res_off)
    assert k_on.keys() == k_off.keys()
    raw_diff = 0
    for k, per_opp in k_on.items():
        if per_opp != k_off[k]:
            raw_diff += 1
    factor = sims_off / sims_on if sims_on else float('nan')
    ok = (n_diff == 0 and raw_diff == 0)
    print(f"  dedup factor: {factor:.2f}x  |  wall-clock speedup: "
          f"{t_off/t_on:.2f}x")
    print(f"  score cells compared: {len(cs_on):,} rounded "
          f"+ {len(k_on):,} raw per-IV dicts")
    print(f"  -> {'EXACT MATCH' if ok else f'MISMATCH: {n_diff} rounded cells, {raw_diff} IVs differ'}")
    return ok, factor, t_off / t_on


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--species', action='append', default=None,
                   help=f'Focal species (repeatable). Default: {DEFAULT_SPECIES}')
    p.add_argument('--league', default='great',
                   choices=['great', 'ultra', 'master'])
    p.add_argument('--opponents', type=int, default=20,
                   help='Top-N rankings opponents (default 20)')
    p.add_argument('--extra-opponent', action='append',
                   default=['Aegislash (Shield)'],
                   help='Always-appended opponents (default: Aegislash '
                        '(Shield), for opponent-side form-change coverage)')
    p.add_argument('--scenarios', default='all', choices=['all', 'even'])
    p.add_argument('--modes', default='pvpoke',
                   help='Comma-separated opp_iv_mode values to verify '
                        '(e.g. pvpoke,pvpoke:nobait)')
    args = p.parse_args()

    species_list = args.species or DEFAULT_SPECIES
    scenarios = ALL_NINE if args.scenarios == 'all' else EVEN
    init_logger('signature-verify', args.league, log_file='/dev/null')

    opponents, opp_movesets = build_opponents(
        args.league, args.opponents, args.extra_opponent)
    print(f"Opponent pool ({len(opponents)}): {', '.join(opponents)}")

    failures = []
    for species in species_list:
        for mode in args.modes.split(','):
            ok, factor, speedup = verify_species(
                species, args.league, opponents, opp_movesets,
                scenarios, mode.strip())
            if not ok:
                failures.append((species, mode))

    print()
    if failures:
        print(f"FAILED: score mismatches for {failures}")
        sys.exit(1)
    print(f"All {len(species_list)} species x {len(args.modes.split(','))} "
          f"mode(s) verified: signature dedup is exact.")


if __name__ == '__main__':
    main()
