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
from iv_envelope_cache import WonSetCache, sig_fields

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
CACHE = None                       # WonSetCache, set in main() unless --no-cache
# The recommended-IV table renders all four quadrants: both your-best-buddy
# states, each vs a best-buddy AND a non-best-buddy meta. The vs-non-BB-meta
# pair is the more expensive half (another full 64-combo sweep at opp L50), but
# the won-set cache makes re-runs cheap, so we sim all four.
REC_QUADRANTS = ['wbb_vs_bb', 'nobb_vs_bb', 'wbb_vs_nonbb', 'nobb_vs_nonbb']
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

# Close-call significance: a KEPT WIN (focal wins at both the hundo and the
# dropped IV) whose post-match margin moved enough vs the perfect-IV (15)
# baseline that a teambuilder would act on it. Anchored to end-state
# BattleResult fields, decision-relevance not raw deltas. One reason per line,
# in priority order, so each close-call is a single most-actionable note:
#   shield    -> focal burns a shield it kept at a hundo (shields_remaining drop)
#   neardeath -> the drop pushes a winning focal under 15% max HP (was >= 15%)
#   energy    -> focal banks one fewer charged move (energy delta >= cheapest cost)
# Outright win/loss flips are already the 'dropped' set, so they are excluded.
NEAR_DEATH_FRAC = 0.15
# A near-death close-call must also represent a MEANINGFUL HP swing, not just a
# 1-HP wobble across the 15% line (e.g. base 32 HP -> drop 31 HP both ~15%).
# Require the dropped IV to shed at least this fraction of max HP vs the hundo.
NEAR_DEATH_MIN_DELTA_FRAC = 0.10


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
    if CACHE is not None:
        hit = CACHE.get(ivs, my_lvl, opp_lvl)
        if hit is not None:
            return hit
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
    if CACHE is not None:
        CACHE.put(ivs, my_lvl, opp_lvl, won)
    return won


def result_metrics(species, fast_id, charged_ids, ivs, my_lvl, opp_lvl,
                   opponents):
    """Per (opp_display, shields): the focal's end-state after the fight.

    Returns {(disp, (shf, sho)): {'won','hp','max_hp','energy','shields'}}.
    Used only for the per-stat close-call diff (a bounded set: one hundo
    baseline per quadrant + the 9 per-stat-IV spreads the detail loop already
    walks), so unlike won_set it is deliberately not cached -- the won-set
    cache stores only the won SET, not these margins."""
    out = {}
    for o in opponents:
        for shf, sho in SHIELDS:
            bp0 = build_mon(species, fast_id, charged_ids, ivs, shf, my_lvl,
                            shadow=FOCAL_SHADOW)
            bp1 = build_mon(o['base'], o['fast'], o['charged'], (15, 15, 15),
                            sho, opp_lvl, shadow=o['shadow'])
            r = simulate(bp0, bp1, charged_policy_0=pvpoke_dp,
                         charged_policy_1=pvpoke_dp)
            out[(o['display'], (shf, sho))] = {
                'won': r.pvpoke_score(0) > r.pvpoke_score(1),
                'hp': max(0, r.hp_remaining[0]),
                'max_hp': r.max_hp[0],
                'energy': r.energy_remaining[0],
                'shields': r.shields_remaining[0],
            }
    return out


def score_set(species, fast_id, charged_ids, ivs, my_lvl, opp_lvl, opponents):
    """Like won_set, but ALSO keeps the full per-(opp, shields) battle score
    (centered on 500) AND the focal's post-match leftover energy.
    Returns (scores, won, energy):
      scores: {(opp_display, (shf, sho)): int focal score}
      won:    set of (opp_display, (shf, sho)) the focal wins
      energy: {(opp_display, (shf, sho)): int focal leftover energy}

    Feeds the guide's 'check my IVs' HP-margin bars + best-buddy flip overlay
    (the raw score; HP% proxy = (score-500)/500) and the banked-energy line
    under the bars (leftover energy -> fast-move-equivalents + fractions of each
    charged move, via the shared cmpMarginPanel energy annotation). The `won`
    set is derived with the EXACT same test won_set uses (pvpoke_score(0) >
    pvpoke_score(1)), not a `score>500` shortcut -- the two differ by one only in
    an unreachable timeout where the floor makes the two scores sum to 999, but
    deriving `won` identically keeps the rec-table drops provably unchanged.

    NOT cached: the won-set disk cache stores only booleans. On a cold/full bake
    these are the SAME sims the rec-table sweep already runs for `drops`, so the
    rec loop derives `won` from this and adds no sims. (A warm-cache iteration
    re-sims the 64 combos; teaching WonSetCache to store scores is the follow-up.)"""
    scores = {}
    won = set()
    energy = {}
    for o in opponents:
        for shf, sho in SHIELDS:
            bp0 = build_mon(species, fast_id, charged_ids, ivs, shf, my_lvl,
                            shadow=FOCAL_SHADOW)
            bp1 = build_mon(o['base'], o['fast'], o['charged'], (15, 15, 15),
                            sho, opp_lvl, shadow=o['shadow'])
            r = simulate(bp0, bp1, charged_policy_0=pvpoke_dp,
                         charged_policy_1=pvpoke_dp)
            key = (o['display'], (shf, sho))
            scores[key] = int(r.pvpoke_score(0))
            energy[key] = max(0, int(r.energy_remaining[0]))
            if r.pvpoke_score(0) > r.pvpoke_score(1):
                won.add(key)
    return scores, won, energy


def _move_abbr(mid):
    """Short move tag for the energy line: multi-word -> initials (Roar Of Time
    -> ROT), single word -> first 3 letters (Crunch -> CRU). Mirrors the
    deep-dive's _mv_abbr so the guide's energy breakdown reads the same."""
    w = mid.replace('_', ' ').title().split()
    return (''.join(x[0] for x in w).upper() if len(w) > 1
            else (w[0][:3].upper() if w else '?'))


def energy_moves_blob(fast_id, charged_ids):
    """{fast:{abbr,gain}, charged:[{abbr,cost}]} -- the move energetics the
    shared cmpMarginPanel uses to render leftover energy as fast-move-equivalents
    and fractions of each charged move."""
    return {
        'fast': {'abbr': _move_abbr(fast_id),
                 'gain': _FAST_DB[fast_id].get('energyGain', 0)},
        'charged': [{'abbr': _move_abbr(cid), 'cost': _CHARGED_DB[cid]['energy']}
                    for cid in charged_ids],
    }


def pack_scores(flat):
    """Pack a flat int list as little-endian uint16 -> gzip(level9, mtime=0) ->
    base64 ascii, the exact pipeline the deep-dive uses (deep_dive.py) so the
    guide's DecompressionStream decoder is identical. mtime=0 keeps the output
    byte-stable run-to-run."""
    import base64, gzip, struct
    clamped = [max(0, min(65535, int(v))) for v in flat]
    raw = struct.pack(f'<{len(clamped)}H', *clamped)
    gz = gzip.compress(raw, compresslevel=9, mtime=0)
    return base64.b64encode(gz).decode('ascii')


def close_calls(base_metrics, drop_metrics, cheapest_cost):
    """Significant KEPT-WIN margin shifts at a dropped IV vs the hundo baseline.

    base_metrics / drop_metrics: result_metrics() maps at IV 15/15/15 and at the
    dropped IV. Emits one compact dict per qualifying (opponent, shield):
        {'opp','shield','kind','margin'}  (margin is a ready-to-render string)
    Only kept wins (won at both) qualify; flips are already the 'dropped' set.
    The first matching kind wins (priority shield > neardeath > energy) so each
    line carries a single, most-actionable reason. ASCII hyphens only."""
    calls = []
    for key, base in base_metrics.items():
        drop = drop_metrics.get(key)
        if drop is None or not base['won'] or not drop['won']:
            continue  # only kept wins; flips are already the 'dropped' set
        disp, sh = key
        lab = shield_label(sh)
        kind = margin = None
        if drop['shields'] < base['shields']:
            kind = 'shield'
            n = base['shields'] - drop['shields']
            margin = (f"keeps the win but spends {n} more "
                      f"shield{'s' if n != 1 else ''} "
                      f"(now {drop['shields']} left, was {base['shields']})")
        elif (base['hp'] >= NEAR_DEATH_FRAC * base['max_hp']
              and drop['hp'] < NEAR_DEATH_FRAC * drop['max_hp']
              and base['hp'] - drop['hp']
                  >= NEAR_DEATH_MIN_DELTA_FRAC * base['max_hp']):
            kind = 'neardeath'
            margin = (f"still wins but barely survives, {drop['hp']} HP left of "
                      f"{drop['max_hp']} (was {base['hp']})")
        elif base['energy'] - drop['energy'] >= cheapest_cost:
            kind = 'energy'
            margin = (f"still wins but banks {base['energy'] - drop['energy']} "
                      f"less energy, about one fewer charged move "
                      f"(now {drop['energy']}, was {base['energy']})")
        if kind is not None:
            calls.append({'opp': disp, 'shield': lab,
                          'kind': kind, 'margin': margin})
    calls.sort(key=lambda c: (c['opp'], c['shield']))
    return calls


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
    global SHIELDS, FOCAL_SHADOW, POOL_FILE, CACHE, IVS
    ap = argparse.ArgumentParser(description='ML IV envelope analysis -> JSON.')
    ap.add_argument('species', nargs='?', default='Dialga (Origin)')
    ap.add_argument('--all-shields', action='store_true',
                    help='Use all 9 ordered shield scenarios (your x opp) '
                         'instead of just the 3 evens; writes a separate '
                         '*_all9 JSON so the even-shield output is preserved.')
    ap.add_argument('--pool', default=POOL_FILE,
                    help='opponent pool file (default: %(default)s). Override '
                         'for a fast smaller-pool smoke/repro run.')
    ap.add_argument('--no-cache', action='store_true',
                    help='skip the won-set disk cache (force fresh sims; for '
                         'timing/debugging).')
    ap.add_argument('--rec-close-calls-all-quadrants', action='store_true',
                    help='compute the recommended-table per-combo close-calls '
                         'for all four quadrants, not just the headline one. '
                         'Much slower (4x the rec-table margin sims); reserve '
                         'for a staged full re-bake, not a shared/iterative '
                         'run. Default: headline quadrant only.')
    ap.add_argument('--iv-floor', type=int, default=12,
                    help='lowest per-stat IV to sweep (default 12 = the '
                         'lucky-trade floor). Use 10 for untradeable mythicals '
                         '/ Routes-only mons whose only obtainable floor is the '
                         '10/10/10 research-or-raid-reward minimum, so a '
                         'legitimately-owned sub-12 spread can be evaluated.')
    a = ap.parse_args()
    species = a.species

    if not 0 <= a.iv_floor <= 15:
        ap.error('--iv-floor must be in [0, 15]')
    # floor 12 -> [15,14,13,12] (default behavior preserved); floor 10 ->
    # [15..10]. Propagates to the detail loops, the recommended-combo
    # product(IVS, repeat=3), and the emitted 'iv_range' (all read this global).
    IVS = list(range(15, a.iv_floor - 1, -1))

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
    cheapest_cost = min(_CHARGED_DB[cid]['energy'] for cid in charged_ids)
    opponents = load_opponents()
    slug = species.lower().replace(' ', '_').replace('(', '').replace(')', '')
    suffix = '_all9' if a.all_shields else ''
    out_path = f"userdata/dives/{slug}_iv_envelope{suffix}.json"

    if not a.no_cache:
        sig = sig_fields(base_clean, FOCAL_SHADOW, fast_id, charged_ids,
                         SHIELDS, opponents)
        CACHE = WonSetCache(slug, variant, sig, enabled=True)

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
    base_metrics_by_q = {}        # hundo end-state per quadrant; reused in step 5
    for q, (ml, ol) in QUADRANTS.items():
        quadrants[q] = {'my_level': ml, 'opp_level': ol,
                        'atk': {}, 'def': {}, 'hp': {}}
        # Hundo end-state baseline for this quadrant, simmed once and reused
        # across every stat/iv close-call diff in it AND the rec-table combos.
        base_metrics = result_metrics(base_clean, fast_id, charged_ids,
                                      (15, 15, 15), ml, ol, opponents)
        base_metrics_by_q[q] = base_metrics
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
                drop_metrics = result_metrics(
                    base_clean, fast_id, charged_ids, tuple(ivs),
                    ml, ol, opponents)
                entry = {
                    'pvp_stat': stat_values['bb' if ml == 51.0 else 'nobb'][stat][iv],
                    'dropped': by_sh,
                    'gained': sorted(f"{d} {shield_label(s)}"
                                     for (d, s) in gained),
                    'close_calls': close_calls(base_metrics, drop_metrics,
                                               cheapest_cost),
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
    #    Also (new) the per-combo close-calls -- kept wins whose post-match
    #    margin shifts enough to matter -- so the "check my IVs" box can show
    #    close-call detail for ANY 12-15 spread. Same significance gate as
    #    close_calls(), filtered at compute time so the JSON stays compact.
    #    Headline quadrant only by default (the box defaults there and the box
    #    is the only consumer); --rec-close-calls-all-quadrants does all four
    #    (4x the margin sims) for a staged full re-bake.
    cc_quads = (REC_QUADRANTS if a.rec_close_calls_all_quadrants
                else [HEADLINE_QUADRANT])
    sp15 = {lv: stat_product(focal_base, (15, 15, 15), lv) for lv in (50.0, 51.0)}
    rec_rows = []
    combos = [c for c in product(IVS, repeat=3)]
    # Raw battle-score grids for the 'check my IVs' HP-margin bars + best-buddy
    # flip overlay. One flat uint16 list per quadrant, in (combo, scenario, opp)
    # order so the shared cmp_panels.js cmpVal() indexes it as
    #   grid[combo_idx * nScenarios * nOpponents + si * nOpponents + oi].
    # Captured from the SAME sims the rec table already runs (the rec loop now
    # derives `won` from these scores instead of a separate won_set call).
    cmp_score_grid = {q: [] for q in REC_QUADRANTS}
    # Parallel leftover-energy grids (same shape/order) for the banked-energy
    # line under the HP-margin bars (shared cmpMarginPanel energy annotation).
    cmp_energy_grid = {q: [] for q in REC_QUADRANTS}
    for (av, dv, sv) in combos:
        row = {'ivs': [av, dv, sv]}
        for lvkey, lv in LEVELS.items():
            ea, ed, eh = my_eff(focal_base, (av, dv, sv), lv)
            row[f'cp_{lvkey}'] = calc_cp(focal_base['atk'], focal_base['def'],
                                         focal_base['hp'], av, dv, sv, lv)
            row[f'perfect_{lvkey}'] = round(
                100.0 * stat_product(focal_base, (av, dv, sv), lv) / sp15[lv], 2)
            row[f'pvp_{lvkey}'] = [round(ea, 1), round(ed, 1), int(eh)]
        # matchups dropped vs hundo (all rendered quadrants) + per-combo
        # close-calls (the cc_quads subset only).
        drops = {}
        ccalls = {}
        is_perfect = (av, dv, sv) == (15, 15, 15)
        for q in REC_QUADRANTS:
            ml, ol = QUADRANTS[q]
            sc, won, en = score_set(base_clean, fast_id, charged_ids,
                                    (av, dv, sv), ml, ol, opponents)
            # Append this combo's scores + energy in scenario-major, opp-inner
            # order (cmpVal indexes both grids identically).
            for (shf, sho) in SHIELDS:
                for o in opponents:
                    cmp_score_grid[q].append(sc[(o['display'], (shf, sho))])
                    cmp_energy_grid[q].append(en[(o['display'], (shf, sho))])
            dr = hundo_won[q] - won
            drops[q] = sorted(f"{disp} {shield_label(sh)}" for (disp, sh) in dr)
            if q not in cc_quads:
                ccalls[q] = []
            elif is_perfect:
                ccalls[q] = []        # the hundo IS the baseline: no close-calls
            else:
                drop_metrics = result_metrics(base_clean, fast_id, charged_ids,
                                              (av, dv, sv), ml, ol, opponents)
                ccalls[q] = close_calls(base_metrics_by_q[q], drop_metrics,
                                        cheapest_cost)
        row['drops'] = drops
        row['close_calls'] = ccalls
        rec_rows.append(row)
    rec_rows.sort(key=lambda r: -r['perfect_bb'])
    print(f"  recommended table: {len(rec_rows)} combos "
          f"(close-calls: {', '.join(cc_quads)})")

    # Pack the score grids for embedding. combos[] is the grid's combo-index
    # reference (the 'check my IVs' box resolves a typed spread to its index
    # here); scenarios/opponentsDisplay/quadrant_levels let the box build the
    # def/alt grids + ✦ best-buddy-flip marker without re-deriving anything.
    cmp_scores = {
        'combos': [list(c) for c in combos],
        'scenarios': [list(s) for s in SHIELDS],
        'opponentsDisplay': [o['display'] for o in opponents],
        'quadrants': REC_QUADRANTS,
        'quadrant_levels': {q: list(QUADRANTS[q]) for q in REC_QUADRANTS},
        'grids': {q: pack_scores(cmp_score_grid[q]) for q in REC_QUADRANTS},
        # Leftover-energy grids (same packing/order as scores) + the build's
        # move energetics, so the margin panel can show the banked-energy line.
        'energy_grids': {q: pack_scores(cmp_energy_grid[q]) for q in REC_QUADRANTS},
        'energy_moves': energy_moves_blob(fast_id, charged_ids),
    }

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
        # Packed raw-score grids for the 'check my IVs' HP-margin bars + ✦
        # best-buddy flip overlay (see render_iv_envelope_article.py compare box).
        'cmp_scores': cmp_scores,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(data, f, indent=2)
    if CACHE is not None:
        CACHE.flush()
        print(f"won-set cache: {CACHE.hits} hits, {CACHE.misses} misses")
    print(f"\nWrote {out_path}")


if __name__ == '__main__':
    main()
