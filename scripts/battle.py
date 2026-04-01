#!/usr/bin/env python
"""
Simulate a 1v1 PvP matchup across all 9 shield scenarios.

Usage:
    python scripts/battle.py <species1> <fast1> <charged1> \
                              <species2> <fast2> <charged2> \
                              [--league great|ultra|master] \
                              [--ivs1 a/d/s] [--ivs2 a/d/s] \
                              [--policy pvpoke_ai|bait_with_cheapest|no_bait|optimal_timing] \
                              [--shadow1] [--shadow2]

    <charged> is a comma-separated list of 1 or 2 move IDs.

Examples:
    python scripts/battle.py Medicham PSYCHO_CUT DYNAMIC_PUNCH,PSYCHIC \
                              Azumarill BUBBLE ICE_BEAM,HYDRO_PUMP \
                              --ivs1 5/15/15 --ivs2 8/15/15

    python scripts/battle.py Swampert MUD_SHOT HYDRO_CANNON,EARTHQUAKE \
                              Registeel LOCK_ON FLASH_CANNON,FOCUS_BLAST \
                              --league great
"""
import argparse
import sys
import os

# Make sure the src layout is importable when run directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.pokemon import Pokemon
from gopvpsim.moves import get_moves
from gopvpsim.data import load_gamemaster
from gopvpsim.battle import (
    BattlePokemon, simulate,
    pvpoke_ai, pvpoke_dp, bait_with_cheapest, no_bait, optimal_timing,
)

POLICIES = {
    'pvpoke_dp':          pvpoke_dp,
    'pvpoke_ai':          pvpoke_ai,
    'bait_with_cheapest': bait_with_cheapest,
    'no_bait':            no_bait,
    'optimal_timing':     optimal_timing,
}


def parse_ivs(s):
    try:
        parts = s.split('/')
        if len(parts) != 3:
            raise ValueError
        return tuple(int(x) for x in parts)
    except ValueError:
        raise argparse.ArgumentTypeError(f"IVs must be in a/d/s format, e.g. 5/15/15, got {s!r}")


def make_battle_pokemon(species, fast_id, charged_ids, league, shields,
                        atk_iv, def_iv, sta_iv, shadow=False):
    pokemon = Pokemon.at_best_level(species, atk_iv, def_iv, sta_iv,
                                    league=league, shadow=shadow)
    fast_moves, charged_moves = get_moves()

    if fast_id not in fast_moves:
        sys.exit(f"Unknown fast move: {fast_id!r}")
    for cid in charged_ids:
        if cid not in charged_moves:
            sys.exit(f"Unknown charged move: {cid!r}")

    fm  = dict(fast_moves[fast_id])
    cms = [dict(charged_moves[cid]) for cid in charged_ids]

    gm  = load_gamemaster()
    mon = next((m for m in gm['pokemon'] if m['speciesName'] == species), None)
    if mon is None:
        sys.exit(f"Unknown species: {species!r}")
    from gopvpsim.data import parse_types
    types = parse_types(mon)

    return BattlePokemon(
        species=species, types=types,
        atk=pokemon.atk, def_=pokemon.def_, max_hp=pokemon.hp,
        fast_move=fm, charged_moves=cms, shields=shields,
    )


def mon_label(species, fast_id, charged_ids, atk_iv, def_iv, sta_iv,
              league, shadow=False):
    shadow_str = ' (Shadow)' if shadow else ''
    charged_str = ', '.join(charged_ids)
    return (f"{species}{shadow_str} | {fast_id} / {charged_str} | "
            f"{atk_iv}/{def_iv}/{sta_iv} | {league.title()} League")


def main():
    parser = argparse.ArgumentParser(
        description='Simulate a PvP 1v1 matchup across all 9 shield scenarios.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('species1')
    parser.add_argument('fast1',    metavar='fast_move1')
    parser.add_argument('charged1', metavar='charged_moves1',
                        help='Comma-separated, e.g. DYNAMIC_PUNCH,PSYCHIC')
    parser.add_argument('species2')
    parser.add_argument('fast2',    metavar='fast_move2')
    parser.add_argument('charged2', metavar='charged_moves2')
    parser.add_argument('--league',  default='great',
                        choices=['great', 'ultra', 'master'])
    parser.add_argument('--ivs1',   default='15/15/15', type=parse_ivs,
                        metavar='a/d/s', help='IVs for pokemon 1 (default 15/15/15)')
    parser.add_argument('--ivs2',   default='15/15/15', type=parse_ivs,
                        metavar='a/d/s', help='IVs for pokemon 2 (default 15/15/15)')
    parser.add_argument('--policy', default='pvpoke_dp', choices=list(POLICIES),
                        help='Charged move policy for both sides (default: pvpoke_ai)')
    parser.add_argument('--shadow1', action='store_true', help='Pokemon 1 is shadow')
    parser.add_argument('--shadow2', action='store_true', help='Pokemon 2 is shadow')

    args = parser.parse_args()

    charged_ids1 = [c.strip() for c in args.charged1.split(',')]
    charged_ids2 = [c.strip() for c in args.charged2.split(',')]
    policy = POLICIES[args.policy]
    a1, d1, s1 = args.ivs1
    a2, d2, s2 = args.ivs2

    print()
    print(mon_label(args.species1, args.fast1, charged_ids1, a1, d1, s1,
                    args.league, args.shadow1))
    print('  vs')
    print(mon_label(args.species2, args.fast2, charged_ids2, a2, d2, s2,
                    args.league, args.shadow2))
    print(f'  policy: {args.policy}')
    print()

    col_w = 14
    header = f"{'':10}" + ''.join(
        f"{'  ' + args.species2[:4] + ' ' + str(sa) + 's':<{col_w}}"
        for sa in range(3)
    )
    print(header)
    print('-' * len(header))

    for s1_shields in range(3):
        row = f"{args.species1[:4] + ' ' + str(s1_shields) + 's':<10}"
        for s2_shields in range(3):
            bp1 = make_battle_pokemon(
                args.species1, args.fast1, charged_ids1, args.league,
                s1_shields, a1, d1, s1, shadow=args.shadow1,
            )
            bp2 = make_battle_pokemon(
                args.species2, args.fast2, charged_ids2, args.league,
                s2_shields, a2, d2, s2, shadow=args.shadow2,
            )
            result = simulate(bp1, bp2,
                              charged_policy_0=policy,
                              charged_policy_1=policy)

            score0 = round(result.pvpoke_score(0))
            score1 = round(result.pvpoke_score(1))

            if result.winner == 0:
                cell = f"{args.species1[:4]} {score0}"
            elif result.winner == 1:
                cell = f"{args.species2[:4]} {score1}"
            else:
                cell = f"Tie {score0}"

            row += f"{cell:<{col_w}}"
        print(row)

    print()


if __name__ == '__main__':
    main()
