#!/usr/bin/env python
"""Owned-collection IV breakdown -- point the IV-guide breakdown at the mons you
actually OWN, to decide which to build/power up.

Given a species, a league, a moveset, and a list of owned IV spreads, this sims
each owned spread vs the league meta pool and reports, per owned mon: CP, level,
effective stats, how many matchups it wins, and the named matchups it gives up
versus the best-possible spread for that species in that league (rank-1 by stat
product -- which in GL/UL is usually NOT the hundo, because lower IVs reach a
higher level under the CP cap).

League-aware via Pokemon.at_best_level (the CP cap binds in GL/UL; Master runs
to level 51). This is the Python REFERENCE implementation; the website-JS and
gobattlekit versions must reproduce its numbers.

MVP CLI takes IV spreads directly; PokeGenie-CSV input (via gopvpsim
user_collection) is the next wiring step.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gopvpsim.pokemon import (
    Pokemon, LEAGUE_CAPS, battle_stats, best_level, get_species,
    cp as calc_cp,
)
from gopvpsim.moves import get_moves
from gopvpsim.battle import simulate, pvpoke_dp, BattlePokemon
from gopvpsim.data import get_default_moveset
from gopvpsim.user_collection import parse_csv_text, get_species_name
from gopvpsim.evolution_lines import get_final_forms
from deep_dive import _parse_opponent_pool_line, parse_opponent_spec

_FAST, _CHARGED = get_moves()
EVEN_SHIELDS = [(0, 0), (1, 1), (2, 2)]

# Default meta pools per league (the same pools the dives/guides use).
DEFAULT_POOLS = {
    'great':  'opponent_pools/gl_top50_plus_cs.txt',
    'ultra':  'opponent_pools/ul_top60.txt',
    'master': 'opponent_pools/master_top60.txt',
}


def load_pool(path, league):
    opps = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            display, base, is_shadow, fast_ov, charged_ov = _parse_opponent_pool_line(line)
            base_clean, _v, sh = parse_opponent_spec(display)
            if fast_ov is None or charged_ov is None:
                d_fast, d_charged = get_default_moveset(base_clean, league=league, shadow=sh)
            fast = fast_ov if fast_ov is not None else d_fast
            charged = list(charged_ov) if charged_ov is not None else list(d_charged)
            opps.append({'display': display, 'base': base_clean, 'shadow': sh,
                         'fast': fast, 'charged': charged})
    return opps


def make_bp(species, fast, charged, ivs, shields, league, shadow, max_level):
    p = Pokemon.at_best_level(species, *ivs, league=league,
                              max_level=max_level, shadow=shadow)
    fm = dict(_FAST[fast])
    cms = [dict(_CHARGED[c]) for c in charged]
    bp = BattlePokemon.from_pokemon(p, fm, cms, shields=shields,
                                    league_cp=LEAGUE_CAPS[league])
    return bp, p


def won_set(species, fast, charged, ivs, shadow, opponents, league,
            my_level, opp_level, shieldset=EVEN_SHIELDS):
    """Set of (opp_display, (shf, sho)) this spread wins over shieldset."""
    won = set()
    for o in opponents:
        for shf, sho in shieldset:
            bp0, _ = make_bp(species, fast, charged, ivs, shf, league, shadow, my_level)
            bp1, _ = make_bp(o['base'], o['fast'], o['charged'], (15, 15, 15),
                             sho, league, o['shadow'], opp_level)
            r = simulate(bp0, bp1, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp)
            if r.pvpoke_score(0) > r.pvpoke_score(1):
                won.add((o['display'], (shf, sho)))
    return won


def rank1_spread(species, league, max_level):
    """IV spread (a, d, h) with the highest stat product at the league cap."""
    base = get_species(species)
    ba, bd, bh = base['atk'], base['def'], base['hp']
    best, best_sp = None, -1.0
    for a in range(16):
        for d in range(16):
            for h in range(16):
                lvl = best_level(ba, bd, bh, a, d, h,
                                 max_cp=LEAGUE_CAPS[league], max_level=max_level)
                if lvl is None:
                    continue
                s = battle_stats(ba, bd, bh, a, d, h, lvl)
                sp = s['atk'] * s['def'] * s['hp']
                if sp > best_sp:
                    best_sp, best = sp, (a, d, h)
    return best


def describe(species, league, ivs, shadow, max_level):
    base = get_species(species)
    p = Pokemon.at_best_level(species, *ivs, league=league,
                              max_level=max_level, shadow=shadow)
    s = battle_stats(base['atk'], base['def'], base['hp'], *ivs, p.level)
    cp = calc_cp(base['atk'], base['def'], base['hp'], *ivs, p.level)
    return {'level': p.level, 'cp': cp,
            'stats': (round(s['atk'], 1), round(s['def'], 1), int(s['hp']))}


def breakdown(species, league, fast, charged, owned, shadow=False,
              pool_path=None, max_level=51.0, opp_level=51.0,
              shieldset=EVEN_SHIELDS):
    """Per owned spread: stats + wins + matchups dropped vs the rank-1 spread."""
    pool_path = pool_path or DEFAULT_POOLS[league]
    opponents = load_pool(pool_path, league)
    ref = rank1_spread(species, league, max_level)
    ref_won = won_set(species, fast, charged, ref, shadow, opponents, league,
                      max_level, opp_level, shieldset)

    rows = []
    for ivs in [ref] + [iv for iv in owned if tuple(iv) != tuple(ref)]:
        ivs = tuple(ivs)
        won = won_set(species, fast, charged, ivs, shadow, opponents, league,
                      max_level, opp_level, shieldset)
        dropped = sorted(f"{d} {s[0]}-{s[1]}" for (d, s) in (ref_won - won))
        d = describe(species, league, ivs, shadow, max_level)
        rows.append({'ivs': ivs, 'is_ref': ivs == tuple(ref),
                     'wins': len(won), 'total': len(opponents) * len(shieldset),
                     'dropped_vs_ref': dropped, **d})
    rows.sort(key=lambda r: (-r['wins'], r['dropped_vs_ref'] != []))
    return {'species': species, 'league': league, 'rank1': ref,
            'pool': pool_path, 'n_opp': len(opponents), 'rows': rows}


def _fmt(res):
    out = [f"{res['species']} ({res['league'].title()} League) -- rank-1 IV "
           f"{'/'.join(map(str, res['rank1']))}, {res['n_opp']} opponents, even shields"]
    for r in res['rows']:
        tag = '  [rank-1]' if r['is_ref'] else ''
        a, d, h = r['ivs']
        out.append(f"  {a}/{d}/{h}  L{r['level']}  CP{r['cp']}  "
                   f"({r['stats'][0]}/{r['stats'][1]}/{r['stats'][2]})  "
                   f"wins {r['wins']}/{r['total']}{tag}")
        drops = ', '.join(r['dropped_vs_ref']) or 'nothing (matches rank-1 win set)'
        out.append(f"        gives up vs rank-1: {drops}")
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description='Owned-mon IV breakdown.')
    ap.add_argument('species', help='PvPoke speciesName, base form (form OK, no '
                    '"(Shadow)" suffix -- use --shadow)')
    ap.add_argument('--league', default='great', choices=list(LEAGUE_CAPS))
    ap.add_argument('--shadow', action='store_true')
    ap.add_argument('--ivs', nargs='+',
                    help='owned spreads as a/d/h, e.g. --ivs 0/15/15 1/14/14')
    ap.add_argument('--csv', help='PokeGenie CSV export; owned copies of '
                    '<species> are pulled from it (use --ivs OR --csv)')
    ap.add_argument('--fast'); ap.add_argument('--charged', nargs='+')
    ap.add_argument('--pool')
    ap.add_argument('--top', type=int, default=12,
                    help='show only your best N spreads (+ rank-1); default 12')
    a = ap.parse_args()

    if a.fast and a.charged:
        fast, charged = a.fast, a.charged
    else:
        fast, charged = get_default_moveset(a.species.replace(' (Shadow)', ''),
                                            league=a.league, shadow=a.shadow)
        charged = list(charged)

    if a.csv:
        target = a.species + (' (Shadow)' if a.shadow else '')
        mons = parse_csv_text(open(a.csv, encoding='utf-8-sig').read())
        # Include pre-evolutions: IVs carry through evolution unchanged, so a
        # Tinkatink counts as an owned Tinkaton-to-be. Shadow status also
        # carries through, so it must match.
        spreads = [(m['atk_iv'], m['def_iv'], m['sta_iv']) for m in mons
                   if m['is_shadow'] == a.shadow
                   and a.species in get_final_forms(
                       get_species_name(m['name'], m['form'], False))]
        if not spreads:
            print(f"No owned {target} (or its pre-evos) found in {a.csv}.")
            return
        owned = sorted(set(spreads))
        print(f"Found {len(spreads)} owned {target} (incl. pre-evos); "
              f"{len(owned)} distinct IV spreads.\n")
    elif a.ivs:
        owned = [tuple(int(x) for x in s.split('/')) for s in a.ivs]
    else:
        ap.error('provide --csv or --ivs')

    res = breakdown(a.species, a.league, fast, charged, owned,
                    shadow=a.shadow, pool_path=a.pool)
    shown = len(res['rows'])
    res['rows'] = res['rows'][:max(1, a.top)]
    print(_fmt(res))
    if shown > len(res['rows']):
        print(f"  ... ({shown - len(res['rows'])} more distinct spreads; "
              f"--top {shown} to show all)")


if __name__ == '__main__':
    main()
