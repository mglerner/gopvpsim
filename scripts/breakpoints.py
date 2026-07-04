#!/usr/bin/env python
"""
Show fast-move breakpoints and bulkpoints for an attacker/move/defender pair.

For each distinct damage tier across all 4096 attacker IV combinations,
shows which IVs first achieve that damage and their stat product rank.
Also shows bulkpoints: which defender IV combinations take one less damage.

Usage:
    python scripts/breakpoints.py <attacker> <fast_move> <defender> \
                                   [--league great|ultra|master] \
                                   [--def-ivs a/d/s] [--atk-ivs a/d/s] \
                                   [--shadow-atk] [--shadow-def]

    --def-ivs: fix the defender's IVs (default 15/15/15)
    --atk-ivs: fix the attacker's IVs for bulkpoint analysis (default 15/15/15)

Examples:
    python scripts/breakpoints.py Medicham COUNTER Azumarill
    python scripts/breakpoints.py Medicham COUNTER Azumarill --def-ivs 8/15/15
    python scripts/breakpoints.py Medicham COUNTER Azumarill --league ultra
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.breakpoints import iv_breakpoints, iv_bulkpoints
from gopvpsim.pokemon import Pokemon, iv_rank


def parse_ivs(s):
    try:
        parts = s.split('/')
        if len(parts) != 3:
            raise ValueError
        return tuple(int(x) for x in parts)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"IVs must be in a/d/s format, e.g. 5/15/15, got {s!r}"
        )


def group_by_damage(results, iv_key='atk_iv'):
    """Group IV results by damage tier, returning the top-ranked IV set per tier."""
    seen = {}
    for r in results:
        dmg = r['damage']
        if dmg not in seen:
            seen[dmg] = r
    return seen  # damage -> best IV entry for that tier


def iv_rank_lookup(species, league, shadow=False):
    """Return a dict of (atk_iv, def_iv, sta_iv) -> rank."""
    ranks = iv_rank(species, league=league, shadow=shadow)
    return {(r['atk_iv'], r['def_iv'], r['sta_iv']): r['rank'] for r in ranks}


def main():
    parser = argparse.ArgumentParser(
        description='Show breakpoints and bulkpoints for an attacker/move/defender.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('attacker', help='Attacker species name')
    parser.add_argument('move',     help='Fast move ID, e.g. COUNTER')
    parser.add_argument('defender', help='Defender species name')
    parser.add_argument('--league',     default='great',
                        choices=['great', 'ultra', 'master'])
    parser.add_argument('--def-ivs',   default='15/15/15', type=parse_ivs,
                        metavar='a/d/s',
                        help="Defender's IVs for breakpoint analysis (default 15/15/15)")
    parser.add_argument('--atk-ivs',   default='15/15/15', type=parse_ivs,
                        metavar='a/d/s',
                        help="Attacker's IVs for bulkpoint analysis (default 15/15/15)")
    parser.add_argument('--shadow-atk', action='store_true',
                        help='Attacker is a shadow Pokemon')
    parser.add_argument('--shadow-def', action='store_true',
                        help='Defender is a shadow Pokemon')

    args = parser.parse_args()
    da, dd, ds = args.def_ivs
    aa, ad, as_ = args.atk_ivs

    # --- Breakpoints: all attacker IVs vs fixed defender ---
    try:
        bp_results = iv_breakpoints(
            args.attacker, args.move, args.defender,
            defender_atk_iv=da, defender_def_iv=dd, defender_sta_iv=ds,
            league=args.league,
            attacker_shadow=args.shadow_atk, defender_shadow=args.shadow_def,
        )
    except (KeyError, ValueError) as e:
        sys.exit(f"Error: {e}")

    # Build rank lookup for attacker
    atk_ranks = iv_rank_lookup(args.attacker, args.league, shadow=args.shadow_atk)

    # Get defender stats for context
    try:
        def_pokemon = Pokemon.at_best_level(
            args.defender, da, dd, ds, league=args.league, shadow=args.shadow_def
        )
    except (KeyError, ValueError) as e:
        sys.exit(f"Error: {e}")

    print()
    print(f"=== BREAKPOINTS: {args.attacker} {args.move} vs {args.defender} "
          f"({args.league.title()} League) ===")
    print(f"Defender: {args.defender} {da}/{dd}/{ds} "
          f"@ L{def_pokemon.level:.1f}  "
          f"def={def_pokemon.def_:.1f}  hp={def_pokemon.hp}")
    print()

    # Group by damage tier; show the best (highest stat product) IV combo per tier
    # bp_results is sorted by (damage desc, stat_product desc)
    damage_tiers = {}
    for r in bp_results:
        if r['damage'] not in damage_tiers:
            damage_tiers[r['damage']] = r

    # Count how many IVs achieve each tier
    tier_counts = {}
    for r in bp_results:
        tier_counts[r['damage']] = tier_counts.get(r['damage'], 0) + 1

    print(f"  {'Damage':<8} {'Best IVs':<12} {'Rank':<8} {'Atk':<10} {'# IVs'}")
    print(f"  {'-'*6:<8} {'-'*8:<12} {'-'*4:<8} {'-'*8:<10} {'-'*5}")
    for dmg in sorted(damage_tiers, reverse=True):
        r = damage_tiers[dmg]
        rank = atk_ranks.get((r['atk_iv'], r['def_iv'], r['sta_iv']), '?')
        count = tier_counts[dmg]
        print(f"  {dmg:<8} "
              f"{r['atk_iv']}/{r['def_iv']}/{r['sta_iv']:<8} "
              f"#{rank:<7} "
              f"{r['atk']:<10.2f} "
              f"{count} / 4096")

    # --- Bulkpoints: fixed attacker vs all defender IVs ---
    try:
        blk_results = iv_bulkpoints(
            args.defender, args.move, args.attacker,
            attacker_atk_iv=aa, attacker_def_iv=ad, attacker_sta_iv=as_,
            league=args.league,
            attacker_shadow=args.shadow_atk, defender_shadow=args.shadow_def,
        )
    except (KeyError, ValueError) as e:
        sys.exit(f"Error: {e}")

    def_ranks = iv_rank_lookup(args.defender, args.league, shadow=args.shadow_def)

    try:
        atk_pokemon = Pokemon.at_best_level(
            args.attacker, aa, ad, as_, league=args.league, shadow=args.shadow_atk
        )
    except (KeyError, ValueError) as e:
        sys.exit(f"Error: {e}")

    print()
    print(f"=== BULKPOINTS: {args.defender} tanking {args.attacker} {args.move} "
          f"({args.league.title()} League) ===")
    print(f"Attacker: {args.attacker} {aa}/{ad}/{as_} "
          f"@ L{atk_pokemon.level:.1f}  "
          f"atk={atk_pokemon.atk:.1f}")
    print()

    # blk_results sorted by (damage asc, stat_product desc)
    bulk_tiers = {}
    for r in blk_results:
        if r['damage'] not in bulk_tiers:
            bulk_tiers[r['damage']] = r

    bulk_counts = {}
    for r in blk_results:
        bulk_counts[r['damage']] = bulk_counts.get(r['damage'], 0) + 1

    print(f"  {'Damage':<8} {'Best IVs':<12} {'Rank':<8} {'Def':<10} {'# IVs'}")
    print(f"  {'-'*6:<8} {'-'*8:<12} {'-'*4:<8} {'-'*8:<10} {'-'*5}")
    for dmg in sorted(bulk_tiers):
        r = bulk_tiers[dmg]
        rank = def_ranks.get((r['atk_iv'], r['def_iv'], r['sta_iv']), '?')
        count = bulk_counts[dmg]
        print(f"  {dmg:<8} "
              f"{r['atk_iv']}/{r['def_iv']}/{r['sta_iv']:<8} "
              f"#{rank:<7} "
              f"{r['def']:<10.2f} "
              f"{count} / 4096")

    print()


if __name__ == '__main__':
    main()
