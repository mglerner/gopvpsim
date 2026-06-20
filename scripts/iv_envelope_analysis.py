#!/usr/bin/env python
"""XehrFelrose-style ML IV envelope analysis -> reusable JSON.

For a focal ML mon with its "with the move" build, computes everything the
gold-standard IV writeup needs, across the full 2x2 of (my best-buddy status)
x (meta best-buddy status), using even shields (0-0, 1-1, 2-2) per the
XehrFelrose convention:

  - PvP stat values (atk/def/hp) at each IV from 15 down to 12.
  - Key wins / key losses vs the Master top-60 (hundo).
  - Per stat (atk/def/hp), per IV: the named matchups DROPPED vs a hundo at
    each shield count, plus the mechanism that moved:
      * attack: CMP ties lost, fast-move breakpoints lost
      * defense: fast-move bulkpoints lost
      * hp:     (matchups only; HP has no breakpoint/bulkpoint/CMP mechanic)
  - A neutral recommended-IV table (all stats 12-15): CP at L50/L51, IV %,
    PvP stats, and which matchups each spread drops vs a hundo. "Premium" =
    drops nothing; "thrifty" = drops the listed matchups. No gameplay/
    teambuilding judgment is made here -- the reader decides what matters.

Output: userdata/dives/<species_slug>_iv_envelope.json (reusable; the article
renderer reads this, so wording/layout tweaks need no re-simulation).

Usage: python scripts/iv_envelope_analysis.py ["Dialga (Origin)"]
"""
import sys, os, json
from itertools import product

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

from gopvpsim.pokemon import (
    Pokemon, LEAGUE_CAPS, battle_stats, get_species, cp as calc_cp,
    SHADOW_ATK_BONUS, SHADOW_DEF_MULT,
)
from gopvpsim.moves import get_moves, damage as calc_damage
from gopvpsim.breakpoints import _get_types
from gopvpsim.battle import simulate, pvpoke_dp, BattlePokemon
from gopvpsim.data import get_default_moveset
from deep_dive import _parse_opponent_pool_line, parse_opponent_spec

LEAGUE    = 'master'
POOL_FILE = 'opponent_pools/master_top60.txt'

# Focal builds (with the signature move). Add Palkia here to reuse.
BUILDS = {
    'Dialga (Origin)': ('DRAGON_BREATH', ['ROAR_OF_TIME', 'IRON_HEAD']),
    'Palkia (Origin)': ('DRAGON_BREATH', ['AQUA_TAIL', 'SPACIAL_REND']),
}

IVS = [15, 14, 13, 12]            # per-stat detail range
EVEN_SHIELDS = [(0, 0), (1, 1), (2, 2)]
ALL9_SHIELDS = [(a, b) for a in (0, 1, 2) for b in (0, 1, 2)]
SHIELDS = EVEN_SHIELDS             # reassigned in main() per --all-shields
FOCAL_SHADOW = False               # reassigned in main() once focal is resolved
# The recommended-IV table only needs the two quadrants the article renders
# (best-buddy and no-best-buddy, both vs a best-buddy meta), so we don't sim
# all four there -- keeps the all-9 run from getting 3x more expensive.
REC_QUADRANTS = ['wbb_vs_bb', 'nobb_vs_bb']
LEVELS = {'nobb': 50.0, 'bb': 51.0}
# Quadrant key -> (my_level, opp_level)
QUADRANTS = {
    'nobb_vs_nonbb': (50.0, 50.0),
    'nobb_vs_bb':    (50.0, 51.0),
    'wbb_vs_nonbb':  (51.0, 50.0),
    'wbb_vs_bb':     (51.0, 51.0),
}
HEADLINE_QUADRANT = 'wbb_vs_bb'    # reference for Key Wins/Losses

_FAST_DB, _CHARGED_DB = get_moves()


def eff_stats(base, ivs, level, shadow=False):
    """Effective (atk, def, hp) for a base-stats dict at IVs/level."""
    s = battle_stats(base['atk'], base['def'], base['hp'], *ivs, level)
    atk = s['atk'] * (SHADOW_ATK_BONUS if shadow else 1.0)
    df = s['def'] * (SHADOW_DEF_MULT if shadow else 1.0)
    return atk, df, s['hp']


def stat_product(base, ivs, level, shadow=False):
    a, d, h = eff_stats(base, ivs, level, shadow)
    return a * d * h


def build_mon(species, fast_id, charged_ids, ivs, shields, level, shadow=False):
    p = Pokemon.at_best_level(species, *ivs, league=LEAGUE,
                              max_level=level, shadow=shadow)
    fm = dict(_FAST_DB[fast_id])
    cms = [dict(_CHARGED_DB[cid]) for cid in charged_ids]
    return BattlePokemon.from_pokemon(p, fm, cms, shields=shields,
                                      league_cp=LEAGUE_CAPS[LEAGUE])


def load_opponents():
    opps = []
    with open(POOL_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            display, base, is_shadow, fast_ov, charged_ov = (
                _parse_opponent_pool_line(line))
            base_clean, _variant, sh = parse_opponent_spec(display)
            if fast_ov is None or charged_ov is None:
                d_fast, d_charged = get_default_moveset(
                    base_clean, league=LEAGUE, shadow=sh)
            fast_id = fast_ov if fast_ov is not None else d_fast
            charged_ids = (list(charged_ov) if charged_ov is not None
                           else list(d_charged))
            opps.append({
                'display': display, 'base': base_clean, 'shadow': sh,
                'fast': fast_id, 'charged': charged_ids,
                'base_stats': get_species(base_clean),
                'types': _get_types(base_clean),
            })
    return opps


# --- Matchup sims ---------------------------------------------------------

def won_set(species, fast_id, charged_ids, ivs, my_lvl, opp_lvl, opponents):
    """Set of (opp_display, shields) this spread wins, over the SHIELDS set."""
    won = set()
    for o in opponents:
        for shf, sho in SHIELDS:
            bp0 = build_mon(species, fast_id, charged_ids, ivs, shf, my_lvl,
                            shadow=FOCAL_SHADOW)
            bp1 = build_mon(o['base'], o['fast'], o['charged'], (15, 15, 15),
                            sho, opp_lvl, shadow=o['shadow'])
            r = simulate(bp0, bp1, charged_policy_0=pvpoke_dp,
                         charged_policy_1=pvpoke_dp)
            if r.pvpoke_score(0) > r.pvpoke_score(1):
                won.add((o['display'], (shf, sho)))
    return won


def shield_label(sh):
    return f"{sh[0]}-{sh[1]}"


# --- Analytic mechanics (breakpoints / bulkpoints / CMP) ------------------

def my_eff(focal_base, ivs, level):
    return eff_stats(focal_base, ivs, level, shadow=FOCAL_SHADOW)


def breakpoints_lost(focal_base, focal_types, fast_move, opponents,
                     my_lvl, opp_lvl, stat_iv):
    """Opponents where dropping focal attack to stat_iv (def/hp=15) makes the
    fast move deal less damage than at 15 attack."""
    atk15, _, _ = my_eff(focal_base, (15, 15, 15), my_lvl)
    atkx, _, _ = my_eff(focal_base, (stat_iv, 15, 15), my_lvl)
    lost = []
    for o in opponents:
        _, odef, _ = eff_stats(o['base_stats'], (15, 15, 15), opp_lvl,
                               shadow=o['shadow'])
        d15 = calc_damage(fast_move['power'], atk15, odef,
                          fast_move['type'], focal_types, o['types'])
        dx = calc_damage(fast_move['power'], atkx, odef,
                         fast_move['type'], focal_types, o['types'])
        if dx < d15:
            lost.append(o['display'])
    return lost


def bulkpoints_lost(focal_base, focal_types, opponents,
                    my_lvl, opp_lvl, stat_iv):
    """Opponents whose fast move deals MORE damage to focal when defense drops
    to stat_iv (atk/hp=15) than at 15 defense."""
    _, def15, _ = my_eff(focal_base, (15, 15, 15), my_lvl)
    _, defx, _ = my_eff(focal_base, (15, stat_iv, 15), my_lvl)
    lost = []
    for o in opponents:
        oatk, _, _ = eff_stats(o['base_stats'], (15, 15, 15), opp_lvl,
                               shadow=o['shadow'])
        ofast = _FAST_DB[o['fast']]
        d15 = calc_damage(ofast['power'], oatk, def15,
                          ofast['type'], o['types'], focal_types)
        dx = calc_damage(ofast['power'], oatk, defx,
                         ofast['type'], o['types'], focal_types)
        if dx > d15:
            lost.append(o['display'])
    return lost


def cmp_lost(focal_base, opponents, my_lvl, opp_lvl, stat_iv):
    """Opponents we beat-or-tie on CMP (charge priority, higher attack throws
    first) at 15 attack but lose at stat_iv attack."""
    atk15, _, _ = my_eff(focal_base, (15, 15, 15), my_lvl)
    atkx, _, _ = my_eff(focal_base, (stat_iv, 15, 15), my_lvl)
    lost = []
    for o in opponents:
        oatk, _, _ = eff_stats(o['base_stats'], (15, 15, 15), opp_lvl,
                               shadow=o['shadow'])
        if atk15 >= oatk and atkx < oatk:
            lost.append(o['display'])
    return lost


def main():
    import argparse
    global SHIELDS, FOCAL_SHADOW, POOL_FILE
    ap = argparse.ArgumentParser(description='ML IV envelope analysis -> JSON.')
    ap.add_argument('species', nargs='?', default='Dialga (Origin)')
    ap.add_argument('--all-shields', action='store_true',
                    help='Use all 9 ordered shield scenarios (your x opp) '
                         'instead of just the 3 evens; writes a separate '
                         '*_all9 JSON so the even-shield output is preserved.')
    ap.add_argument('--pool', default=POOL_FILE,
                    help='opponent pool file (default: %(default)s). Override '
                         'for a fast smaller-pool smoke/repro run.')
    a = ap.parse_args()
    species = a.species

    POOL_FILE = a.pool
    SHIELDS = ALL9_SHIELDS if a.all_shields else EVEN_SHIELDS
    variant = 'all9' if a.all_shields else 'even'
    shield_conv = ('all 9 ordered shields, your-opp (0-0 .. 2-2)'
                   if a.all_shields else 'even shields only (0-0, 1-1, 2-2)')

    # Resolve the focal moveset + shadow status. parse_opponent_spec keeps real
    # form suffixes (e.g. "(Origin)") in the base name but strips "(Shadow)"
    # into the shadow flag, matching how opponents are parsed. Species listed in
    # BUILDS use their hand-picked signature move; everything else falls back to
    # PvPoke's default Master moveset (never guess from the legal-move pool).
    base_clean, _variant, FOCAL_SHADOW = parse_opponent_spec(species)
    if species in BUILDS:
        fast_id, charged_ids = BUILDS[species]
        build_source = 'signature'
    else:
        fast_id, charged_ids = get_default_moveset(
            base_clean, league=LEAGUE, shadow=FOCAL_SHADOW)
        charged_ids = list(charged_ids)
        build_source = 'default'
    focal_base = get_species(base_clean)
    focal_types = _get_types(base_clean)
    fast_move = _FAST_DB[fast_id]
    opponents = load_opponents()
    slug = species.lower().replace(' ', '_').replace('(', '').replace(')', '')
    suffix = '_all9' if a.all_shields else ''
    out_path = f"userdata/dives/{slug}_iv_envelope{suffix}.json"

    print(f"{species}: {len(opponents)} opponents, build {fast_id} / "
          f"{', '.join(charged_ids)}")

    # 1. PvP stat values per level / stat / iv.
    stat_values = {}
    for lvkey, lv in LEVELS.items():
        stat_values[lvkey] = {'atk': {}, 'def': {}, 'hp': {}}
        for iv in IVS:
            a_a, _, _ = my_eff(focal_base, (iv, 15, 15), lv)
            _, d_d, _ = my_eff(focal_base, (15, iv, 15), lv)
            _, _, h_h = my_eff(focal_base, (15, 15, iv), lv)
            stat_values[lvkey]['atk'][iv] = round(a_a, 1)
            stat_values[lvkey]['def'][iv] = round(d_d, 1)
            stat_values[lvkey]['hp'][iv] = int(h_h)

    # 2. Hundo win-sets per quadrant (drives key wins/losses + the drop diffs).
    hundo_won = {}
    for q, (ml, ol) in QUADRANTS.items():
        hundo_won[q] = won_set(base_clean, fast_id, charged_ids, (15, 15, 15),
                               ml, ol, opponents)
        print(f"  hundo {q}: {len(hundo_won[q])} won (of "
              f"{len(opponents) * len(SHIELDS)})")

    # 3. Key wins / losses at the headline quadrant, summarized on the 3 EVEN
    # shields (the high-level overview; requiring all 9 would make almost
    # everything "split"). The full per-shield detail lives in the quadrant
    # tables. The renderer also recomputes this, so it stays consistent.
    even_set = set(EVEN_SHIELDS)
    by_opp = {}
    for (disp, sh) in hundo_won[HEADLINE_QUADRANT]:
        if sh in even_set:
            by_opp.setdefault(disp, set()).add(sh)
    key_wins, key_losses, key_split = [], [], []
    for o in opponents:
        n = len(by_opp.get(o['display'], set()))
        if n == len(EVEN_SHIELDS):
            key_wins.append(o['display'])
        elif n == 0:
            key_losses.append(o['display'])
        else:
            key_split.append(o['display'])

    # 4. Per quadrant / stat / iv: dropped matchups + mechanics.
    quadrants = {}
    for q, (ml, ol) in QUADRANTS.items():
        quadrants[q] = {'my_level': ml, 'opp_level': ol,
                        'atk': {}, 'def': {}, 'hp': {}}
        for stat, slot in (('atk', 0), ('def', 1), ('hp', 2)):
            for iv in IVS:
                if iv == 15:
                    continue
                ivs = [15, 15, 15]
                ivs[slot] = iv
                won = won_set(base_clean, fast_id, charged_ids, tuple(ivs),
                              ml, ol, opponents)
                dropped = hundo_won[q] - won
                gained = won - hundo_won[q]
                by_sh = {shield_label(s): [] for s in SHIELDS}
                for (disp, sh) in sorted(dropped):
                    by_sh[shield_label(sh)].append(disp)
                entry = {
                    'pvp_stat': stat_values['bb' if ml == 51.0 else 'nobb'][stat][iv],
                    'dropped': by_sh,
                    'gained': sorted(f"{d} {shield_label(s)}"
                                     for (d, s) in gained),
                }
                if stat == 'atk':
                    entry['breakpoints_lost'] = breakpoints_lost(
                        focal_base, focal_types, fast_move, opponents,
                        ml, ol, iv)
                    entry['cmp_lost'] = cmp_lost(
                        focal_base, opponents, ml, ol, iv)
                elif stat == 'def':
                    entry['bulkpoints_lost'] = bulkpoints_lost(
                        focal_base, focal_types, opponents, ml, ol, iv)
                quadrants[q][stat][iv] = entry
        print(f"  detail {q}: done")

    # 5. Neutral recommended-IV table: all stats 12-15 (64 combos).
    #    For each, CP/% at L50 & L51 and matchups dropped vs hundo in each
    #    quadrant. No "critical" labels -- just what each spread keeps/drops.
    sp15 = {lv: stat_product(focal_base, (15, 15, 15), lv) for lv in (50.0, 51.0)}
    rec_rows = []
    combos = [c for c in product(IVS, repeat=3)]
    for (a, d, s) in combos:
        row = {'ivs': [a, d, s]}
        for lvkey, lv in LEVELS.items():
            ea, ed, eh = my_eff(focal_base, (a, d, s), lv)
            row[f'cp_{lvkey}'] = calc_cp(focal_base['atk'], focal_base['def'],
                                         focal_base['hp'], a, d, s, lv)
            row[f'perfect_{lvkey}'] = round(
                100.0 * stat_product(focal_base, (a, d, s), lv) / sp15[lv], 2)
            row[f'pvp_{lvkey}'] = [round(ea, 1), round(ed, 1), int(eh)]
        # matchups dropped vs hundo, only for the quadrants the article renders
        drops = {}
        for q in REC_QUADRANTS:
            ml, ol = QUADRANTS[q]
            won = won_set(base_clean, fast_id, charged_ids, (a, d, s),
                          ml, ol, opponents)
            dr = hundo_won[q] - won
            drops[q] = sorted(f"{disp} {shield_label(sh)}" for (disp, sh) in dr)
        row['drops'] = drops
        rec_rows.append(row)
    rec_rows.sort(key=lambda r: -r['perfect_bb'])
    print(f"  recommended table: {len(rec_rows)} combos")

    data = {
        'species': species,
        'shadow': FOCAL_SHADOW,
        'build': {'fast': fast_id, 'charged': charged_ids, 'source': build_source},
        'base_stats': focal_base,
        'pool': POOL_FILE,
        'n_opponents': len(opponents),
        'shields': [shield_label(s) for s in SHIELDS],
        'shield_convention': shield_conv,
        'variant': variant,
        'iv_range': IVS,
        'quadrant_levels': {k: list(v) for k, v in QUADRANTS.items()},
        'headline_quadrant': HEADLINE_QUADRANT,
        'stat_values': stat_values,
        'key_wins': key_wins,
        'key_losses': key_losses,
        'key_split': key_split,
        # Per-quadrant hundo win-sets, so the renderer can derive what
        # best-buddy gains (wbb vs nobb, holding the meta's BB status fixed).
        'hundo_won': {
            q: sorted(f"{disp} {shield_label(sh)}" for (disp, sh) in won)
            for q, won in hundo_won.items()
        },
        'quadrants': quadrants,
        'recommended': rec_rows,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == '__main__':
    main()
