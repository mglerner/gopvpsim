#!/usr/bin/env python
"""
Simulate a 1v1 PvP matchup across all 9 shield scenarios.

Usage:
    python scripts/battle.py <species1> [fast1] [charged1] \
                              <species2> [fast2] [charged2] \
                              [--league great|ultra|master] \
                              [--ivs1 a/d/s] [--ivs2 a/d/s] \
                              [--policy pvpoke_ai|bait_with_cheapest|no_bait|optimal_timing] \
                              [--shadow1] [--shadow2] \
                              [--pvpoke-scores] \
                              [--shields1 N] [--shields2 N] \
                              [--log] [--debug] [--trace-shields] [--trace-dp] [--stats]

    fast/charged moves are optional — if omitted, PvPoke's recommended moveset
    for that species/league is used (from rankings data).
    <charged> is a comma-separated list of 1 or 2 move IDs.
    --shields1 / --shields2: restrict to a single shield scenario (0, 1, or 2).
    --log:   print a turn-by-turn battle timeline after the result table.
    --debug: print policy decisions interleaved with the timeline (implies --log).
             Use --shields1/--shields2 to focus on one scenario when debugging.
    --trace-shields: log every shield-policy call with inputs/results (implies --debug).
    --trace-dp: log DP queue plans and bandaid decisions (implies --debug).
    --stats: print computed stats (atk, def, hp, CP, types) for both pokemon.

Examples:
    python scripts/battle.py Medicham Azumarill

    python scripts/battle.py Medicham PSYCHO_CUT DYNAMIC_PUNCH,PSYCHIC \
                              Azumarill BUBBLE ICE_BEAM,HYDRO_PUMP \
                              --ivs1 5/15/15 --ivs2 8/15/15

    python scripts/battle.py Swampert MUD_SHOT HYDRO_CANNON,EARTHQUAKE \
                              Registeel LOCK_ON FLASH_CANNON,FOCUS_BLAST \
                              --league great

    python scripts/battle.py Azumarill BUBBLE ICE_BEAM,HYDRO_PUMP \
                              Forretress VOLT_SWITCH ROCK_TOMB \
                              --ivs1 4/15/13 --ivs2 5/15/13 \
                              --shields1 2 --shields2 2 --debug
"""
import argparse
import sys
import os

# Make sure the src layout is importable when run directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.pokemon import Pokemon
from gopvpsim.moves import get_moves
from gopvpsim.data import load_gamemaster, get_default_moveset
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

    # from_pokemon (not direct construction) so form changes attach —
    # direct construction silently simmed Aegislash/Mimikyu/Morpeko
    # with no form mechanics (same bug class as the 2026-06-10 arc-S1
    # dive-worker fix; found 2026-06-12 via the Blade-focal oracle).
    from gopvpsim.pokemon import LEAGUE_CAPS
    return BattlePokemon.from_pokemon(
        pokemon, fm, cms, shields=shields,
        league_cp=LEAGUE_CAPS[league],
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
    parser.add_argument('pokemon', nargs='+', metavar='ARG',
                        help='species1 [fast1 charged1] species2 [fast2 charged2]. '
                             'Moves default to PvPoke recommended if omitted.')
    parser.add_argument('--league',  default='great',
                        choices=['great', 'ultra', 'master'])
    parser.add_argument('--ivs1',   default='15/15/15', type=parse_ivs,
                        metavar='a/d/s', help='IVs for pokemon 1 (default 15/15/15)')
    parser.add_argument('--ivs2',   default='15/15/15', type=parse_ivs,
                        metavar='a/d/s', help='IVs for pokemon 2 (default 15/15/15)')
    parser.add_argument('--policy', default='pvpoke_dp', choices=list(POLICIES),
                        help='Charged move policy for both sides (default: pvpoke_ai)')
    parser.add_argument('--mechanics', choices=['legacy', 'new'], default='legacy',
                        help='Turn-resolution model. legacy (default) = pre-2026-06-23. '
                             'new = 2026-06-23 PvP turn system (EXPERIMENTAL, no PvPoke reference)')
    parser.add_argument('--shadow1', action='store_true', help='Pokemon 1 is shadow')
    parser.add_argument('--shadow2', action='store_true', help='Pokemon 2 is shadow')
    parser.add_argument('--pvpoke-scores', action='store_true',
                        help='Report all scores from species1\'s perspective '
                             '(like PvPoke\'s table: scores <500 mean species1 loses)')
    parser.add_argument('--shields1', type=int, choices=[0, 1, 2], default=None,
                        metavar='N', help='Simulate only this shield count for species1')
    parser.add_argument('--shields2', type=int, choices=[0, 1, 2], default=None,
                        metavar='N', help='Simulate only this shield count for species2')
    parser.add_argument('--log', action='store_true',
                        help='Print a turn-by-turn battle timeline after the result table')
    parser.add_argument('--debug', action='store_true',
                        help='Print policy decisions interleaved with timeline (implies --log)')
    parser.add_argument('--trace-shields', action='store_true',
                        help='Log every shield-policy call with inputs and results (implies --debug)')
    parser.add_argument('--trace-dp', action='store_true',
                        help='Log DP queue plans and bandaid decisions (implies --debug)')
    parser.add_argument('--stats', action='store_true',
                        help='Print computed stats (atk, def, hp, CP, types) for both pokemon')
    parser.add_argument('--show-damage', action='store_true',
                        help='Print damage each move deals to the opponent (for verification)')
    parser.add_argument('--battle-log', action='store_true',
                        help='Print compact charged-move sequence for each scenario '
                             '(useful for adding to tests)')

    args = parser.parse_args()

    if args.mechanics == 'new':
        import sys
        print('WARNING: --mechanics new is EXPERIMENTAL / UNVALIDATED -- it models the '
              '2026-06-23 PvP turn system, which PvPoke has not implemented, so there is '
              'no reference to cross-check against.', file=sys.stderr)

    # Parse positional args: accept 2, 4, 5, or 6 positional args.
    #   2: species1 species2                    (both use default moves)
    #   5: species1 fast1 charged1 species2     (species2 uses defaults; rare)
    #   6: species1 fast1 charged1 species2 fast2 charged2
    # We detect the pattern by checking if arg looks like a species name
    # (starts with uppercase) vs a move ID (all uppercase with underscores).
    positional = args.pokemon
    if len(positional) == 2:
        species1, species2 = positional
        fast1 = charged1_str = fast2 = charged2_str = None
    elif len(positional) == 6:
        species1, fast1, charged1_str, species2, fast2, charged2_str = positional
    elif len(positional) == 4:
        # species1 fast1 charged1 species2 (species2 uses defaults)
        species1, fast1, charged1_str, species2 = positional
        fast2 = charged2_str = None
    else:
        sys.exit(f"Expected 2, 4, or 6 positional args "
                 f"(species1 [fast charged] species2 [fast charged]), got {len(positional)}.\n"
                 f"  2 args: species1 species2  (both use PvPoke default moves)\n"
                 f"  6 args: species1 fast1 charged1 species2 fast2 charged2")

    # Resolve default movesets from PvPoke rankings when not specified
    if fast1 is None or charged1_str is None:
        default_fast, default_charged = get_default_moveset(
            species1, league=args.league, shadow=args.shadow1)
        if fast1 is None:
            fast1 = default_fast
        if charged1_str is None:
            charged1_str = ','.join(default_charged)

    if fast2 is None or charged2_str is None:
        default_fast, default_charged = get_default_moveset(
            species2, league=args.league, shadow=args.shadow2)
        if fast2 is None:
            fast2 = default_fast
        if charged2_str is None:
            charged2_str = ','.join(default_charged)

    charged_ids1 = [c.strip() for c in charged1_str.split(',')]
    charged_ids2 = [c.strip() for c in charged2_str.split(',')]
    policy = POLICIES[args.policy]
    a1, d1, s1 = args.ivs1
    a2, d2, s2 = args.ivs2

    print()
    print(mon_label(species1, fast1, charged_ids1, a1, d1, s1,
                    args.league, args.shadow1))
    print('  vs')
    print(mon_label(species2, fast2, charged_ids2, a2, d2, s2,
                    args.league, args.shadow2))
    print(f'  policy: {args.policy}')
    print()

    if args.stats:
        from gopvpsim.data import parse_types
        for label, species, fast_id, charged_ids_list, ivs, shadow in [
            ('P1', species1, fast1, charged_ids1, args.ivs1, args.shadow1),
            ('P2', species2, fast2, charged_ids2, args.ivs2, args.shadow2),
        ]:
            a, d, s = ivs
            p = Pokemon.at_best_level(species, a, d, s, league=args.league, shadow=shadow)
            fast_moves, charged_moves = get_moves()
            fm = fast_moves[fast_id]
            gm = load_gamemaster()
            mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
            types = parse_types(mon)
            print(f'  {label} {species}: CP={p.cp} L{p.level} | '
                  f'atk={p.atk:.2f} def={p.def_:.2f} hp={p.hp} | '
                  f'types={types}')
            print(f'      fast: {fast_id} (power={fm["power"]} energy={fm["energyGain"]}'
                  f' cd={fm["cooldown"]}ms = {fm["cooldown"]//500}T)')
            for cid in charged_ids_list:
                cm = charged_moves[cid]
                buff_str = ''
                if cm.get('buffs'):
                    buff_str = (f' buffs={cm["buffs"]} target={cm.get("buffTarget","?")}'
                                f' chance={cm.get("buffApplyChance","?")}')
                print(f'      chrg: {cid} (power={cm["power"]} energy={cm["energy"]}{buff_str})')
        print()

    if args.show_damage:
        # Build one pair of BattlePokemon to compute damage values
        bp1 = make_battle_pokemon(
            species1, fast1, charged_ids1, args.league,
            2, a1, d1, s1, shadow=args.shadow1)
        bp2 = make_battle_pokemon(
            species2, fast2, charged_ids2, args.league,
            2, a2, d2, s2, shadow=args.shadow2)
        print(f'  Damage: {species1} → {species2}')
        print(f'    {fast1}: {bp1.fast_move_damage(bp2)} dmg'
              f'  (power={bp1.fast_move["power"]}'
              f' energy={bp1.fast_move["energyGain"]}'
              f' turns={bp1.fast_move.get("_turns", bp1.fast_move["cooldown"]//500)})')
        for cm in bp1.charged_moves:
            print(f'    {cm["moveId"]}: {bp1.charged_move_damage(cm, bp2)} dmg'
                  f'  (power={cm["power"]} energy={cm["energy"]})')
        print(f'  Damage: {species2} → {species1}')
        print(f'    {fast2}: {bp2.fast_move_damage(bp1)} dmg'
              f'  (power={bp2.fast_move["power"]}'
              f' energy={bp2.fast_move["energyGain"]}'
              f' turns={bp2.fast_move.get("_turns", bp2.fast_move["cooldown"]//500)})')
        for cm in bp2.charged_moves:
            print(f'    {cm["moveId"]}: {bp2.charged_move_damage(cm, bp1)} dmg'
                  f'  (power={cm["power"]} energy={cm["energy"]})')
        print()

    do_trace_shields = args.trace_shields
    do_trace_dp     = args.trace_dp
    do_debug = args.debug or do_trace_shields or do_trace_dp
    do_log   = args.log or do_debug or args.battle_log

    shield_range1 = [args.shields1] if args.shields1 is not None else range(3)
    shield_range2 = [args.shields2] if args.shields2 is not None else range(3)

    col_w = 14
    s2_list = list(shield_range2)
    header = f"{'':10}" + ''.join(
        f"{'  ' + species2[:4] + ' ' + str(sa) + 's':<{col_w}}"
        for sa in s2_list
    )
    print(header)
    print('-' * len(header))

    timelines = []  # (label, timeline_lines) collected for printing after table

    for s1_shields in shield_range1:
        row = f"{species1[:4] + ' ' + str(s1_shields) + 's':<10}"
        for s2_shields in s2_list:
            bp1 = make_battle_pokemon(
                species1, fast1, charged_ids1, args.league,
                s1_shields, a1, d1, s1, shadow=args.shadow1,
            )
            bp2 = make_battle_pokemon(
                species2, fast2, charged_ids2, args.league,
                s2_shields, a2, d2, s2, shadow=args.shadow2,
            )
            result = simulate(bp1, bp2,
                              charged_policy_0=policy,
                              charged_policy_1=policy,
                              log=do_log,
                              debug=do_debug,
                              trace_shields=do_trace_shields,
                              trace_dp=do_trace_dp,
                              mechanics=args.mechanics)

            score0 = round(result.pvpoke_score(0))
            score1 = round(result.pvpoke_score(1))

            if args.pvpoke_scores:
                # PvPoke style: always show score from species1's perspective.
                # >500 = species1 wins, <500 = species1 loses.
                cell = str(score0)
            elif result.winner == 0:
                cell = f"{species1[:4]} {score0}"
            elif result.winner == 1:
                cell = f"{species2[:4]} {score1}"
            else:
                cell = f"Tie {score0}"

            row += f"{cell:<{col_w}}"

            if do_log and result.timeline:
                label = (f"--- {species1} {s1_shields}s  vs  "
                         f"{species2} {s2_shields}s "
                         f"(score: {score0}) ---")
                timelines.append((label, result.timeline))

        print(row)

    print()

    for label, tl in timelines:
        print(label)
        for line in tl:
            print(line)
        print()

    if args.battle_log:
        print('Battle logs (charged moves only):')
        print()
        for label, tl in timelines:
            print(label)
            for line in tl:
                if ('uses' not in line or '→' not in line
                        or 'fast' in line.lower()
                        or 'floating' in line.lower()):
                    continue
                raw = line.strip()
                body = raw.split(': ', 1)[1]  # strip "T xx: "
                who, rest = body.split(' uses ', 1)
                move_name = rest.split(' →')[0]
                if 'SHIELDED' in raw:
                    print(f'  {who}: {move_name} (shielded)')
                else:
                    print(f'  {who}: {move_name}')
            print()


if __name__ == '__main__':
    main()
