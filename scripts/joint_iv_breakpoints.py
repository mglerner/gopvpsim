#!/usr/bin/env python
"""Closed-form breakpoint / mechanism layer for the joint IV robustness
kit (docs/joint_iv_reuse_plan.md section 2).

Takes one pair config (pairs/*.toml, see scripts/joint_iv_config.py) and
runs the focal species' kit against the opponent's. Companion to the bake
step (which sims the 4096x4096 joint grids); this script computes the
*damage-tier structure* that explains those grids, plus whatever
community claims the pair's `[breakpoints.claim_*]` tables name.

Everything here is closed-form: damage comes from `gopvpsim.moves.damage`
(the same function `battle.py` imports as `calc_damage`), stat-stage
multipliers from `gopvpsim.battle._stat_stage_mult`, and IV spreads /
stats from `gopvpsim.pokemon.iv_rank(species, league)` -- the same
canonical stat-product order both axes of the bake use.

Output: <data_dir>/breakpoints.json (or --out), embeddable verbatim as
`TL_DATA.breakpoints`.

The JSON schema/key names are held FIXED across pairs (the page renderer
reads them positionally), so the names are SLOTS, not species/move facts.
`[breakpoints] focal_key / opp_key / opp_short` spell the focal and
opponent halves of every such key (defaults: the config's slugs; the
Thievul configs pin the shipped Lickitung-era names so their artifacts
rebuild byte-identically). On the opponent's move axis the frozen slots
are `lick_* = fast move`, `body_slam_* = first charged move`,
`power_whip_* = second charged move`; `meta.move_slots` and
`meta.schema_note` record the real move id behind every slot so a
renderer can relabel instead of mislabelling.

Run:  direnv exec . python scripts/joint_iv_breakpoints.py \
          pairs/thievul_lickilicky.toml
"""
import argparse
import datetime
import json
import math
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gopvpsim.battle import _stat_stage_mult, simulate  # noqa: E402
from gopvpsim.data import get_default_moveset, load_gamemaster  # noqa: E402
from gopvpsim.moves import (BONUS, STAB_MULTIPLIER, damage, get_moves,  # noqa: E402
                            parse_types, stab, type_effectiveness)
from gopvpsim.pokemon import iv_rank  # noqa: E402
from deep_dive_analysis import move_abbr  # noqa: E402
from joint_iv_config import load_pair  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent

# Independent transcription of the Pokemon GO type chart for the
# verification block's independent() damage formula -- deliberately NOT
# moves.py's chart (the check must not compare the engine to itself).
# Non-neutral entries only: attacker type -> {defender type: multiplier},
# super-effective float32(1.6) per the engine-constant sourcing rule
# (the game computes in float32; 0.625 and 0.390625 = 0.625^2 are exact
# in binary already). Hand-typed from the standard chart; any typo aborts
# the verification loudly against engine damage (PvPoke-pinned, 324 cells).
_SE, _NV, _IM = 1.600000023841858, 0.625, 0.390625
_INDEP_CHART = {
    'normal': {'rock': _NV, 'steel': _NV, 'ghost': _IM},
    'fire': {'grass': _SE, 'ice': _SE, 'bug': _SE, 'steel': _SE,
             'fire': _NV, 'water': _NV, 'rock': _NV, 'dragon': _NV},
    'water': {'fire': _SE, 'ground': _SE, 'rock': _SE,
              'water': _NV, 'grass': _NV, 'dragon': _NV},
    'electric': {'water': _SE, 'flying': _SE,
                 'electric': _NV, 'grass': _NV, 'dragon': _NV,
                 'ground': _IM},
    'grass': {'water': _SE, 'ground': _SE, 'rock': _SE,
              'fire': _NV, 'grass': _NV, 'poison': _NV, 'flying': _NV,
              'bug': _NV, 'dragon': _NV, 'steel': _NV},
    'ice': {'grass': _SE, 'ground': _SE, 'flying': _SE, 'dragon': _SE,
            'fire': _NV, 'water': _NV, 'ice': _NV, 'steel': _NV},
    'fighting': {'normal': _SE, 'ice': _SE, 'rock': _SE, 'dark': _SE,
                 'steel': _SE,
                 'poison': _NV, 'flying': _NV, 'psychic': _NV, 'bug': _NV,
                 'fairy': _NV, 'ghost': _IM},
    'poison': {'grass': _SE, 'fairy': _SE,
               'poison': _NV, 'ground': _NV, 'rock': _NV, 'ghost': _NV,
               'steel': _IM},
    'ground': {'fire': _SE, 'electric': _SE, 'poison': _SE, 'rock': _SE,
               'steel': _SE,
               'grass': _NV, 'bug': _NV, 'flying': _IM},
    'flying': {'grass': _SE, 'fighting': _SE, 'bug': _SE,
               'electric': _NV, 'rock': _NV, 'steel': _NV},
    'psychic': {'fighting': _SE, 'poison': _SE,
                'psychic': _NV, 'steel': _NV, 'dark': _IM},
    'bug': {'grass': _SE, 'psychic': _SE, 'dark': _SE,
            'fire': _NV, 'fighting': _NV, 'poison': _NV, 'flying': _NV,
            'ghost': _NV, 'steel': _NV, 'fairy': _NV},
    'rock': {'fire': _SE, 'ice': _SE, 'flying': _SE, 'bug': _SE,
             'fighting': _NV, 'ground': _NV, 'steel': _NV},
    'ghost': {'psychic': _SE, 'ghost': _SE,
              'dark': _NV, 'normal': _IM},
    'dragon': {'dragon': _SE, 'steel': _NV, 'fairy': _IM},
    'dark': {'psychic': _SE, 'ghost': _SE,
             'fighting': _NV, 'dark': _NV, 'fairy': _NV},
    'steel': {'ice': _SE, 'rock': _SE, 'fairy': _SE,
              'fire': _NV, 'water': _NV, 'electric': _NV, 'steel': _NV},
    'fairy': {'fighting': _SE, 'dragon': _SE, 'dark': _SE,
              'fire': _NV, 'poison': _NV, 'steel': _NV},
}

# Charged-move debuffs on the opponent's ATTACK open an extra axis; the
# ladder floors at -4 (the game's cap), and collapses to [0] for a focal
# kit that carries no such move.
FULL_STAGES = [0, -1, -2, -3, -4]
COHORTS = {'all': 4096, 'top512': 512, 'top100': 100, 'rank1': 1}

_BP_KNOWN = {'focal_key', 'opp_key', 'opp_short', 'headline_move',
             'headline_abbr', 'expected_tiers', 'assert_focal_default_moveset',
             'claim_a', 'claim_b', 'named_spreads', 'sim_probes',
             'stage_probe', 'resisted_probe', 'stage_ladder_from_rank1',
             'assert_opponent_default_moveset'}
_CLAIM_KNOWN = {'key', 'answer_key', 'slug', 'ivs', 'claim'}
_PROBE_KNOWN = {'focal_ivs', 'opp_ivs', 'arm', 'shields'}


def r2(x):
    return round(float(x), 2)


def r4(x):
    return round(float(x), 4)


# ---------------------------------------------------------------------------
# Spread tables
# ---------------------------------------------------------------------------

def spread_table(species, league, shadow=False):
    """iv_rank rows plus value/index compaction for atk, def, hp.

    Damage is a function of the *stat value*, and a species has far fewer
    distinct stat values than the 4096 spreads (Thievul in GL: 89 atk,
    123 def -- an example, not a constant) -- so every tier table below
    is indexed by stat value, and `*_index` maps rank order -> value
    index.
    """
    rows = iv_rank(species, league=league, shadow=shadow)
    assert len(rows) == 4096, (species, len(rows))
    out = {'rows': rows}
    for key, field in (('atk', 'atk'), ('def', 'def_'), ('hp', 'hp')):
        vals = sorted({e[field] for e in rows})
        pos = {v: i for i, v in enumerate(vals)}
        out[key + '_values'] = vals
        out[key + '_index'] = [pos[e[field]] for e in rows]
    return out


def dmg_matrix(power, atk_values, def_values, move_type, atk_types, def_types,
               atk_mult=1.0):
    """[len(atk_values)][len(def_values)] integer damage, via moves.damage."""
    return [[damage(power, a * atk_mult, d, move_type, atk_types, def_types)
             for d in def_values] for a in atk_values]


def tier_counts(matrix_row, def_index_by_rank, tiers, cohort_n):
    """Count opponents (first `cohort_n` ranks) at each damage tier."""
    pos = {t: i for i, t in enumerate(tiers)}
    counts = [0] * len(tiers)
    for oi in range(cohort_n):
        counts[pos[matrix_row[def_index_by_rank[oi]]]] += 1
    return counts


def focal_arms(cfg):
    """Unique (fast, charged) movesets in grid order -- the bait/no-bait
    suffix pairs collapse, so this is the pair's moveset ARM list."""
    arms = []
    for g in cfg.grids:
        key = (g.focal_fast, tuple(g.focal_charged))
        if key not in arms:
            arms.append(key)
    return arms


def focal_move_list(arms):
    """[(move_id, kind)] = the union of the arms' moves, in arm order
    (fast moves first). The ORDER is only the moves_meta dict order; no
    math depends on it."""
    out, seen = [], set()
    for fast, _ch in arms:
        if fast not in seen:
            seen.add(fast)
            out.append((fast, 'fast'))
    for _fast, ch in arms:
        for c in ch:
            if c not in seen:
                seen.add(c)
                out.append((c, 'charged'))
    return out


def _probe(table, arms, default_focal_ivs, default_opp_ivs, default_shields):
    unknown = set(table) - _PROBE_KNOWN
    if unknown:
        raise SystemExit('ABORT: [breakpoints] probe has unknown keys '
                         f'{sorted(unknown)}')
    ai = int(table.get('arm', 0))
    return (tuple(table.get('focal_ivs', default_focal_ivs)),
            tuple(table.get('opp_ivs', default_opp_ivs)),
            arms[ai][0], list(arms[ai][1]),
            int(table.get('shields', default_shields)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('pair', help='pair config TOML (scripts/joint_iv_config.py)')
    ap.add_argument('--out', help='output path override (default: the pair '
                                  "config's data_dir/breakpoints.json)")
    args = ap.parse_args()

    cfg = load_pair(args.pair)
    bp_cfg = cfg.section('breakpoints')
    unknown = set(bp_cfg) - _BP_KNOWN
    if unknown:
        raise SystemExit(f'ABORT: [breakpoints] unknown keys {sorted(unknown)}')
    # Shadow sides: iv_rank(shadow=True) returns EFFECTIVE (multiplied)
    # atk/def, which is what every closed form here wants; the sim probes
    # pass shadow through make_battle_pokemon; CMP strips the x1.2 like
    # battle.cmp_atk does. First shadow pair: Quagsire (Shadow) vs
    # Lickilicky, 2026-08-19.
    F_SHADOW, O_SHADOW = cfg.focal_shadow, cfg.opp_shadow

    FOCAL = cfg.focal
    OPPONENT = cfg.opponent
    LEAGUE = cfg.league
    ARMS = focal_arms(cfg)
    T_MOVES = focal_move_list(ARMS)
    L_MOVES = [(cfg.opp_fast, 'fast')] + [(m, 'charged') for m in cfg.opp_charged]
    L_FAST, L_CH1, L_CH2 = (m[0] for m in L_MOVES)
    OUT = pathlib.Path(args.out) if args.out else cfg.data_dir / 'breakpoints.json'

    # Frozen JSON key slots: `focal_key`/`opp_key` name the two species
    # halves, `opp_short` the opponent's short form used in the
    # "..._vs_rank1_<opp>" family. Defaults are the config slugs; the
    # Thievul pairs pin the shipped names.
    FK = bp_cfg.get('focal_key', cfg.focal_slug)
    OK = bp_cfg.get('opp_key', cfg.opp_slug)
    OS = bp_cfg.get('opp_short', cfg.opp_slug)
    assert FK != OK, (FK, OK)
    OS_NICE = OS[:1].upper() + OS[1:]

    # PROSE names: reader-visible sentences name the real species
    # (lowercased), never the frozen slot prefixes -- 'thievul_atk' on a
    # Wigglytuff page was a 2026-08-19 review major. JSON KEYS keep the
    # frozen slots.
    PROSE_F = cfg.focal.lower()
    PROSE_O = cfg.opponent.lower()

    # The headline move is resolved AFTER the spread tables exist (its
    # auto-pick needs the focal atk range vs the rank-1 opponent def);
    # a configured [breakpoints] headline_move is authoritative.
    _cfg_headline = bp_cfg.get('headline_move')
    if _cfg_headline is not None and _cfg_headline not in dict(T_MOVES):
        raise SystemExit(f'ABORT: headline_move {_cfg_headline} is not in '
                         "the focal arms' move union")

    gm = load_gamemaster()
    # The opponent kit must BE PvPoke's rankings default, never a guess
    # from the gamemaster's legal-move pool (CLAUDE.md testing note).
    if bp_cfg.get('assert_opponent_default_moveset', True):
        _d_fast, _d_charged = get_default_moveset(OPPONENT, LEAGUE,
                                                  shadow=O_SHADOW)
        # Order-insensitive (charged order is sim-irrelevant); the
        # worlds MODAL moveset can deliberately differ from PvPoke's
        # default (Quagsire (Shadow) runs Stone Edge, 62.4% of the
        # field) -- an explicit config opt-out, never a silent absence.
        assert (_d_fast == L_MOVES[0][0]
                and frozenset(_d_charged)
                == frozenset(m[0] for m in L_MOVES[1:])), (
            OPPONENT, _d_fast, _d_charged, L_MOVES)
    # Same rule for the focal side, but relaxed to "SOME arm is the
    # default": a focal kit's LANDING build is often deliberately off-meta
    # (the Thievul pages ship SP/IW+PR while PvPoke recommends SP/NS+IW,
    # which those pairs bake as their second arm). A pair whose every arm
    # is off-meta sets assert_focal_default_moveset = false -- an explicit
    # opt-out, never a silently absent check.
    if bp_cfg.get('assert_focal_default_moveset', True):
        _f_fast, _f_charged = get_default_moveset(FOCAL, LEAGUE,
                                                   shadow=cfg.focal_shadow)
        # Charged ORDER is sim-irrelevant (pinned by the meta step's [b2]
        # order-independence check), and the worlds meta stores its own
        # order -- compare as a set (Altaria: SKY_ATTACK,FLAMETHROWER vs
        # FLAMETHROWER,SKY_ATTACK, 2026-08-19).
        _default_arm = (_f_fast, frozenset(_f_charged))
        _arm_sets = {(f, frozenset(c)) for f, c in ARMS}
        assert _default_arm in _arm_sets, (FOCAL, _default_arm, ARMS)
    sp_index = {p['speciesName']: p for p in gm['pokemon']}
    t_types = parse_types(sp_index[FOCAL])
    l_types = parse_types(sp_index[OPPONENT])
    fast_moves, charged_moves = get_moves()

    def move(mid, kind):
        return dict(fast_moves[mid] if kind == 'fast' else charged_moves[mid])

    # The opponent-attack debuff move (if the focal kit has one) is what
    # opens the stage axis; derive it instead of naming it.
    debuff_mid = None
    for mid, kind in T_MOVES:
        mv = move(mid, kind)
        if (mv.get('buffTarget') == 'opponent' and mv.get('buffs')
                and mv['buffs'][0] < 0):
            debuff_mid = mid
            break
    STAGES = list(FULL_STAGES) if debuff_mid else [0]

    T = spread_table(FOCAL, LEAGUE, F_SHADOW)
    L = spread_table(OPPONENT, LEAGUE, O_SHADOW)
    t_rows, l_rows = T['rows'], L['rows']
    iv_to_rank_t = {(e['atk_iv'], e['def_iv'], e['sta_iv']): i
                    for i, e in enumerate(t_rows)}

    # Headline move resolution. Config wins; the auto-pick prefers the
    # arms' shared FAST move (it always flies) whenever its damage vs the
    # rank-1 opponent actually VARIES across the focal atk range, else
    # the charged move with the most distinct tiers -- a flat-tier
    # headline has no breakpoint story (Corviknight's Sand Attack is
    # damage 2 vs Lickilicky for every one of the 4096 spreads,
    # 2026-08-19; the >=2-tiers floor below still guards the pick).
    def _tiers_of(mid, kind):
        mv = move(mid, kind)
        r1_def = l_rows[0]['def_']
        return {damage(mv['power'], e['atk'], r1_def, mv['type'],
                       t_types, l_types) for e in t_rows}

    if _cfg_headline is not None:
        HEADLINE = _cfg_headline
    else:
        _fasts = sorted({a[0] for a in ARMS})
        if len(_fasts) != 1:
            raise SystemExit('ABORT: the arms do not share one fast move, '
                             'so [breakpoints] headline_move must be set '
                             'explicitly')
        if len(_tiers_of(_fasts[0], 'fast')) >= 2:
            HEADLINE = _fasts[0]
        else:
            _charged = [(mid, len(_tiers_of(mid, 'charged')))
                        for mid, kind in T_MOVES if kind == 'charged']
            _charged.sort(key=lambda x: (-x[1], x[0]))
            HEADLINE = _charged[0][0]
            print(f'headline auto-pick: fast move {_fasts[0]} is '
                  f'tier-flat vs the rank-1 {OPPONENT}; using '
                  f'{HEADLINE} ({_charged[0][1]} tiers)')
    HA = bp_cfg.get('headline_abbr') or move_abbr(HEADLINE)
    ha = HA.lower()
    HEAD_KEY = HEADLINE.lower()
    HEAD_KIND = dict(T_MOVES)[HEADLINE]
    HEAD_NAME = move(HEADLINE, HEAD_KIND)['name']

    # ---------------------------------------------------------------- meta
    meta = {
        'generated': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'league': LEAGUE,
        'focal': FOCAL, 'opponent': OPPONENT,
        'focal_types': t_types, 'opponent_types': l_types,
        'formula': ('floor(0.5 * BONUS * power * atk / def * effectiveness '
                    '* stab) + 1, via gopvpsim.moves.damage (the same '
                    'function battle.py imports as calc_damage)'),
        'constants': {'BONUS': BONUS, 'STAB_MULTIPLIER': STAB_MULTIPLIER,
                      'note': 'float32-truncated, matching PvPoke / the game'},
        'stat_stage_formula': ('gopvpsim.battle._stat_stage_mult: '
                               'stage >= 0 -> (4 + stage) / 4; '
                               'stage < 0 -> 4 / (4 - stage)'),
        'stat_stage_multipliers': {str(s): r4(_stat_stage_mult(s))
                                   for s in range(-4, 5)},
        'axis_order': ('both species indexed in '
                       "gopvpsim.pokemon.iv_rank(species, league='%s') "
                       'order; index i = stat-product rank i+1 (same order '
                       'as the baked joint grids)' % LEAGUE),
        'cohorts': {k: ('%s iv_rank rows 0..%d' % (OPPONENT, n - 1))
                    for k, n in COHORTS.items()},
        'cohort_sizes': dict(COHORTS),
        'model': ('closed-form damage tiers only. No shields, no energy, '
                  'no timing -- the simulated grids carry the real fight. '
                  'Use this layer to EXPLAIN the grids, not to replace them.'),
    }
    # The JSON key names are frozen SLOTS so a single renderer reads every
    # pair's file. For the pair the slots were named after they happen to
    # be literal; for anyone else reading a move name out of a key would
    # mislabel the tables -- so ship the slot map.
    keys_are_literal = (OK == OPPONENT.lower()
                        and (L_FAST, L_CH1, L_CH2)
                        == ('LICK', 'BODY_SLAM', 'POWER_WHIP'))
    # move_slots is emitted ALWAYS, including when the key names happen to
    # be literal: the renderer's only honest alternative to reading it is a
    # hardcoded move name, and a page that silently falls back to one is a
    # page that can print a confidently wrong move.
    meta['move_slots'] = {'fast': L_FAST, 'charged_1': L_CH1,
                          'charged_2': L_CH2}
    if not keys_are_literal:
        meta['schema_note'] = (
            'key names are held fixed across opponents so one renderer '
            'reads both files. Keys spelled "%s" name THE OPPONENT '
            '(meta.opponent = %s), and the survival / claim keys spelled '
            '"lick_*", "body_slam_*", "power_whip_*" name the fast, first-'
            'charged and second-charged SLOTS respectively -- here %s, %s '
            'and %s. Relabel from meta.move_slots; do NOT read a move name '
            'out of a key.' % (OK, OPPONENT, L_FAST, L_CH1, L_CH2))

    # --------------------------------------------------------------- moves
    moves_meta = {}
    for mid, kind in T_MOVES:
        mv = move(mid, kind)
        moves_meta[mid] = {
            'attacker': FOCAL, 'kind': kind, 'type': mv['type'],
            'power': mv['power'],
            'stab': stab(mv['type'], t_types) > 1.0,
            'stab_mult': r4(stab(mv['type'], t_types)),
            'effectiveness_vs_defender': r4(type_effectiveness(mv['type'], l_types)),
            'energy': mv.get('energy', 0), 'energy_gain': mv.get('energyGain', 0),
            'turns': mv.get('turns'),
            'buffs': mv.get('buffs'), 'buff_target': mv.get('buffTarget'),
        }
    for mid, kind in L_MOVES:
        mv = move(mid, kind)
        moves_meta[mid] = {
            'attacker': OPPONENT, 'kind': kind, 'type': mv['type'],
            'power': mv['power'],
            'stab': stab(mv['type'], l_types) > 1.0,
            'stab_mult': r4(stab(mv['type'], l_types)),
            'effectiveness_vs_defender': r4(type_effectiveness(mv['type'], t_types)),
            'energy': mv.get('energy', 0), 'energy_gain': mv.get('energyGain', 0),
            'turns': mv.get('turns'),
        }

    # ------------------------------------------------ focal offense (part 1)
    t_atk_vals = T['atk_values']
    l_def_vals = L['def_values']
    l_def_idx = L['def_index']          # opponent rank -> def value index
    t_atk_idx = T['atk_index']          # focal rank -> atk value index
    rank1_opp_def_i = l_def_idx[0]

    offense = {}
    k_by_move = {}
    for mid, kind in T_MOVES:
        mv = move(mid, kind)
        mat = dmg_matrix(mv['power'], t_atk_vals, l_def_vals, mv['type'],
                         t_types, l_types)
        tiers = sorted({v for row in mat for v in row})
        # closed-form ratio thresholds: dmg >= tier iff K*atk/def >= tier-1
        K = (0.5 * BONUS * mv['power']
             * type_effectiveness(mv['type'], l_types)
             * stab(mv['type'], t_types))
        k_by_move[mid] = K
        bounds = [{'tier_from': tiers[i], 'tier_to': tiers[i + 1],
                   'min_atk_over_def': r4((tiers[i + 1] - 1) / K)}
                  for i in range(len(tiers) - 1)]
        entry = {
            'tiers': tiers,
            'damage_constant_K': r4(K),
            'damage_identity': 'dmg = floor(K * atk / def) + 1',
            'tier_boundaries': bounds,
            'dmg_by_atk_index_x_def_index': mat,
            'tier_counts_by_atk_index': {
                ck: [tier_counts(mat[ai], l_def_idx, tiers, n)
                     for ai in range(len(t_atk_vals))]
                for ck, n in COHORTS.items()
            },
            f'dmg_vs_rank1_{OS}_by_atk_index': [mat[ai][rank1_opp_def_i]
                                                for ai in range(len(t_atk_vals))],
        }
        offense[mid] = entry

    # ------------------------------------------ the headline move's boundary
    sp = offense[HEADLINE]
    sp_tiers = sp['tiers']
    sp_mat = sp['dmg_by_atk_index_x_def_index']
    base_tier = sp_tiers[0]
    hi_tier = base_tier + 1          # the breakpoint everyone is chasing
    K_sp = sp['damage_constant_K']
    # `answers.<headline>_tier_boundary.pair_tier_note` names the tiers
    # literally; fail loudly rather than ship prose that lies. The prose is
    # formatted from sp_tiers, and a pair that additionally PINS the tiers
    # in its config gets the drift check too.
    expected_tiers = bp_cfg.get('expected_tiers')
    if expected_tiers is not None:
        assert sp_tiers == list(expected_tiers), (sp_tiers, expected_tiers)
    assert len(sp_tiers) >= 2, sp_tiers

    # per-focal-spread counts of opponent spreads taking >= hi_tier
    ge_hi_by_atk = {}
    for ck, n in COHORTS.items():
        col = []
        for ai in range(len(t_atk_vals)):
            row = sp_mat[ai]
            col.append(sum(1 for oi in range(n)
                           if row[l_def_idx[oi]] >= hi_tier))
        ge_hi_by_atk[ck] = col
    sp_ge_hi_spread = {ck: [ge_hi_by_atk[ck][t_atk_idx[i]] for i in range(4096)]
                       for ck in COHORTS}
    sp_tier_vs_rank1_spread = [sp_mat[t_atk_idx[i]][rank1_opp_def_i]
                               for i in range(4096)]

    # exact atk thresholds per opponent defense value. K_head is the SAME
    # constant the offense table above published (unrounded), so the move's
    # power / type / effectiveness / STAB are never re-inlined here.
    K_head = k_by_move[HEADLINE]
    per_opp_def = []
    for di, dv in enumerate(l_def_vals):
        thr = {}
        for t in sp_tiers[1:]:
            need = (t - 1) * dv / K_head
            achievable = [a for a in t_atk_vals if a >= need]
            thr[str(t)] = {
                'min_atk_required': r4(need),
                f'reachable_by_{FK}': bool(achievable),
                f'min_{FK}_atk_value_clearing': (r2(achievable[0])
                                                 if achievable else None),
                f'n_{FK}_spreads_clearing': sum(
                    1 for i in range(4096) if t_atk_vals[t_atk_idx[i]] >= need),
            }
        per_opp_def.append({'def_index': di, 'def_value': r2(dv),
                            'atk_threshold_for_tier': thr})

    # min atk_iv needed to clear the hi tier vs the rank-1 opponent, per
    # (def_iv, sta_iv)
    min_atk_iv_grid = [[None] * 16 for _ in range(16)]
    for i, e in enumerate(t_rows):
        if sp_tier_vs_rank1_spread[i] >= hi_tier:
            d, s, a = e['def_iv'], e['sta_iv'], e['atk_iv']
            cur = min_atk_iv_grid[d][s]
            if cur is None or a < cur:
                min_atk_iv_grid[d][s] = a

    rank1_def = l_rows[0]['def_']
    sp_thr_hi = (hi_tier - 1) * rank1_def / K_head
    clearing = [i for i in range(4096) if sp_tier_vs_rank1_spread[i] >= hi_tier]
    sp[f'breakpoint_vs_rank1_{OS}'] = {
        f'{OS}_ivs': [l_rows[0]['atk_iv'], l_rows[0]['def_iv'], l_rows[0]['sta_iv']],
        f'{OS}_def': r4(rank1_def),
        'base_tier': base_tier, 'hi_tier': hi_tier,
        f'min_{FK}_atk_for_hi_tier': r4(sp_thr_hi),
        f'lowest_{FK}_atk_value_clearing': r2(min(
            t_atk_vals[t_atk_idx[i]] for i in clearing)) if clearing else None,
        f'highest_{FK}_atk_value_failing': (
            r4(max(t_atk_vals[t_atk_idx[i]] for i in range(4096)
                   if sp_tier_vs_rank1_spread[i] < hi_tier))
            if len(clearing) < 4096 else None),
        'n_spreads_clearing': len(clearing),
        'n_spreads_failing': 4096 - len(clearing),
        'best_rank_clearing': (min(clearing) + 1) if clearing else None,
        'min_atk_iv_by_def_iv_sta_iv': min_atk_iv_grid,
        'min_atk_iv_grid_note': ('grid[def_iv][sta_iv] = lowest atk_iv whose '
                                 'spread reaches the hi tier vs rank-1 '
                                 '%s; null = unreachable at that '
                                 'def/sta pair' % OPPONENT),
    }
    sp['ge_hi_tier_count_by_spread'] = sp_ge_hi_spread
    sp['ge_hi_tier_count_by_spread_note'] = (
        'divide by meta.cohort_sizes[cohort] for the fraction')
    sp[f'tier_vs_rank1_{OS}_by_spread'] = sp_tier_vs_rank1_spread

    # full-coverage threshold: clearing the hi tier vs EVERY opponent spread
    # means clearing it vs the bulkiest one
    max_l_def = max(l_def_vals)
    # `answers.<headline>_tier_boundary.cohort_note` claims the bulkiest
    # opponent sits inside every cohort down to top512 -- check, don't assert
    # it in prose only.
    assert min(i for i in range(4096)
               if l_rows[i]['def_'] == max_l_def) < 512
    full_cov_atk = (hi_tier - 1) * max_l_def / K_head
    full_cov = [i for i in range(4096)
                if sp_ge_hi_spread['all'][i] == 4096]
    sp[f'full_coverage_vs_all_{OS}'] = {
        f'bulkiest_{OS}_def': r4(max_l_def),
        f'min_{FK}_atk_for_hi_tier_vs_every_{OS}': r4(full_cov_atk),
        f'lowest_{FK}_atk_value_achieving': (
            r4(min(t_atk_vals[t_atk_idx[i]] for i in full_cov))
            if full_cov else None),
        'n_spreads': len(full_cov),
        'best_iv_rank': (min(full_cov) + 1) if full_cov else None,
    }
    sp[f'atk_thresholds_per_{OS}_def'] = per_opp_def

    # --------------------------------------------- opponent offense (part 2)
    t_def_vals = T['def_values']
    l_atk_vals = L['atk_values']
    l_atk_idx = L['atk_index']
    t_def_idx = T['def_index']
    t_hp_vals = T['hp_values']
    t_hp_idx = T['hp_index']

    if debuff_mid:
        _dbf = move(debuff_mid, 'charged')
        stages_note = ('%s %s applies buffs %s to the opponent, so each %s '
                       'that lands drops %s one attack stage (floor %d)'
                       % (FOCAL, debuff_mid, _dbf['buffs'], _dbf['name'],
                          OPPONENT, STAGES[-1]))
    else:
        _dbf = None
        stages_note = ('no %s move debuffs the opponent, so only attack '
                       'stage 0 is modelled' % FOCAL)

    l_offense = {}
    for mid, kind in L_MOVES:
        mv = move(mid, kind)
        per_stage = {}
        for st in STAGES:
            m = _stat_stage_mult(st)
            mat = dmg_matrix(mv['power'], l_atk_vals, t_def_vals, mv['type'],
                             l_types, t_types, atk_mult=m)
            flat = {v for row in mat for v in row}
            rec = {'stage_mult': r4(m), 'tiers': sorted(flat)}
            if len(flat) == 1:
                rec['constant_damage'] = flat.pop()
            else:
                rec[f'dmg_by_{OS}_atk_index_x_{FK}_def_index'] = mat
            per_stage[str(st)] = rec
        l_offense[mid] = {
            'stages_note': stages_note,
            'by_stage': per_stage,
        }

    # ----------------------------------------------------- survival / bulk
    def ko_hits(hp, dmg):
        return math.ceil(hp / dmg) if dmg > 0 else None

    survival = {'model': ('additive, no shields, no healing: hits = '
                          'ceil(%s_hp / per-hit damage). Real fights '
                          'mix moves and shields -- this isolates the bulk '
                          'tiers only.' % PROSE_F),
                'refs': {}}
    for ref_name, ref_idx in ((f'{OS}_rank1', 0), (f'{OS}_max_atk', None)):
        if ref_idx is None:
            ref_idx = max(range(4096), key=lambda i: l_rows[i]['atk'])
        lr = l_rows[ref_idx]
        ai = l_atk_idx[ref_idx]
        ref = {f'{OS}_rank': ref_idx + 1,
               f'{OS}_ivs': [lr['atk_iv'], lr['def_iv'], lr['sta_iv']],
               f'{OS}_atk': r4(lr['atk']),
               'by_stage': {}}
        for st in STAGES:
            m = _stat_stage_mult(st)
            per_move = {}
            for mid, kind in L_MOVES:
                mv = move(mid, kind)
                dmg_by_def = [damage(mv['power'], lr['atk'] * m, dv,
                                     mv['type'], l_types, t_types)
                              for dv in t_def_vals]
                K = (0.5 * BONUS * mv['power']
                     * type_effectiveness(mv['type'], t_types)
                     * stab(mv['type'], l_types))
                tiers = sorted(set(dmg_by_def))
                # d >= t  iff  focal_def <= K * opp_atk / (t - 1);
                # so "def strictly above that value" drops you to tier t-1.
                bulk = []
                for t in tiers[1:]:
                    cut = K * lr['atk'] * m / (t - 1)
                    n_at_or_above = sum(1 for i in range(4096)
                                        if dmg_by_def[t_def_idx[i]] >= t)
                    bulk.append({
                        'tier_hi': t, 'tier_lo': t - 1,
                        f'max_{FK}_def_still_taking_tier_hi': r4(cut),
                        f'n_{FK}_spreads_taking_ge_tier_hi': n_at_or_above,
                    })
                per_move[mid] = {
                    'tiers': tiers,
                    f'dmg_by_{FK}_def_index': dmg_by_def,
                    'bulkpoints': bulk,
                    'hits_to_ko_by_def_index_x_hp_index': [
                        [ko_hits(hp, d) for hp in t_hp_vals]
                        for d in dmg_by_def],
                    'hits_to_ko_histogram': {
                        str(k): sum(1 for i in range(4096)
                                    if ko_hits(t_rows[i]['hp'],
                                               dmg_by_def[t_def_idx[i]]) == k)
                        for k in sorted({ko_hits(t_rows[i]['hp'],
                                                 dmg_by_def[t_def_idx[i]])
                                         for i in range(4096)})},
                }
                if mid == L_CH1:
                    # the headline "does 15 HP buy a charged-slot-1 hit?" array
                    per_move[mid][f'hits_to_ko_by_{FK}_spread'] = [
                        ko_hits(t_rows[i]['hp'], dmg_by_def[t_def_idx[i]])
                        for i in range(4096)]
            ref['by_stage'][str(st)] = per_move
        survival['refs'][ref_name] = ref

    # per-focal-spread convenience arrays vs the rank-1 opponent, stage 0
    r1 = l_rows[0]
    bs = move(L_CH1, 'charged')
    pw = move(L_CH2, 'charged')
    lk = move(L_FAST, 'fast')
    bs_dmg_by_def = [damage(bs['power'], r1['atk'], dv, bs['type'], l_types, t_types)
                     for dv in t_def_vals]
    pw_dmg_by_def = [damage(pw['power'], r1['atk'], dv, pw['type'], l_types, t_types)
                     for dv in t_def_vals]
    lk_dmg_by_def = [damage(lk['power'], r1['atk'], dv, lk['type'], l_types, t_types)
                     for dv in t_def_vals]
    per_spread = {
        'body_slam_dmg': [bs_dmg_by_def[t_def_idx[i]] for i in range(4096)],
        'power_whip_dmg': [pw_dmg_by_def[t_def_idx[i]] for i in range(4096)],
        'lick_dmg': [lk_dmg_by_def[t_def_idx[i]] for i in range(4096)],
        'hp': [t_rows[i]['hp'] for i in range(4096)],
    }
    per_spread['body_slams_to_ko'] = [
        ko_hits(per_spread['hp'][i], per_spread['body_slam_dmg'][i])
        for i in range(4096)]
    per_spread['power_whips_to_ko'] = [
        ko_hits(per_spread['hp'][i], per_spread['power_whip_dmg'][i])
        for i in range(4096)]
    per_spread['licks_to_ko'] = [
        ko_hits(per_spread['hp'][i], per_spread['lick_dmg'][i])
        for i in range(4096)]
    # hp still standing after (body_slams_to_ko - 1) charged-slot-1 hits: how
    # much of the last hit is "wasted" -- small margin = fragile to a def/hp
    # downgrade
    per_spread['hp_margin_over_prev_bs_tier'] = [
        per_spread['hp'][i]
        - (per_spread['body_slams_to_ko'][i] - 1) * per_spread['body_slam_dmg'][i]
        for i in range(4096)]
    survival[f'per_{FK}_spread_vs_rank1_{OS}_stage0'] = per_spread

    # mixed kill: fast hits still needed after k charged-slot-1 hits
    # (k = 0..4), stage 0, keyed [focal_def_index][focal_hp_index][k]
    survival[f'licks_after_k_body_slams_vs_rank1_{OS}_stage0'] = [
        [[(0 if hp - k * bs_dmg_by_def[di] <= 0
           else ko_hits(hp - k * bs_dmg_by_def[di], lk_dmg_by_def[di]))
          for k in range(5)]
         for hp in t_hp_vals]
        for di in range(len(t_def_vals))]
    survival['licks_after_k_body_slams_note'] = (
        'grid[def_index][hp_index][k] = additional %ss needed to KO after '
        'k unshielded %ss (stage 0, rank-1 %s). 0 = already '
        'dead. Additive model only.' % (lk['name'], bs['name'], OPPONENT))

    # cohort-mean charged-slot-1 hits to KO (stage 0) by focal
    # (def_index, hp_index)
    cohort_bs = {}
    for ck, n in COHORTS.items():
        grid = []
        for di, dv in enumerate(t_def_vals):
            dmgs = [damage(bs['power'], l_rows[oi]['atk'], dv, bs['type'],
                           l_types, t_types) for oi in range(n)]
            grid.append([r4(sum(ko_hits(hp, d) for d in dmgs) / n)
                         for hp in t_hp_vals])
        cohort_bs[ck] = grid
    survival['mean_body_slams_to_ko_by_def_index_x_hp_index'] = cohort_bs

    # ------------------------------------------------------------ 3. CMP
    from gopvpsim.pokemon import SHADOW_ATK_BONUS

    def _cmp_of(row, shadow):
        # battle.cmp_atk: shadow's x1.2 boosts damage, not priority
        return row['atk'] / SHADOW_ATK_BONUS if shadow else row['atk']
    max_l_cmp = max(_cmp_of(e, O_SHADOW) for e in l_rows)
    min_t_cmp = min(_cmp_of(e, F_SHADOW) for e in t_rows)
    argmax_l = max(range(4096), key=lambda i: _cmp_of(l_rows[i], O_SHADOW))
    argmin_t = min(range(4096), key=lambda i: _cmp_of(t_rows[i], F_SHADOW))
    cmp_block = {
        'definition': (('BattlePokemon.cmp_atk == atk (neither side is '
                        'shadow, so no x1.2 strip applies); higher cmp_atk '
                        'resolves simultaneous charged moves first'
                        if not (F_SHADOW or O_SHADOW) else
                        'BattlePokemon.cmp_atk: the shadow side\'s x1.2 '
                        'atk bonus boosts damage, NOT priority, so it is '
                        'stripped here exactly as battle.cmp_atk strips '
                        'it; higher cmp_atk resolves simultaneous charged '
                        'moves first'),),
        f'max_{OK}_cmp_atk': r4(max_l_cmp),
        f'max_{OK}_spread': [l_rows[argmax_l]['atk_iv'],
                             l_rows[argmax_l]['def_iv'],
                             l_rows[argmax_l]['sta_iv']],
        f'max_{OK}_rank': argmax_l + 1,
        f'min_{FK}_cmp_atk': r4(min_t_cmp),
        f'min_{FK}_spread': [t_rows[argmin_t]['atk_iv'],
                             t_rows[argmin_t]['def_iv'],
                             t_rows[argmin_t]['sta_iv']],
        f'min_{FK}_rank': argmin_t + 1,
        'margin': r4(min_t_cmp - max_l_cmp),
        f'{FK}_always_wins_cmp': bool(min_t_cmp > max_l_cmp),
        'verdict': (('CONFIRMED: every %s spread out-CMPs every '
                     '%s spread' % (FOCAL, OPPONENT))
                    if min_t_cmp > max_l_cmp else
                    ('REFUTED: some %s spreads out-CMP some %s '
                     'spreads' % (OPPONENT, FOCAL))),
    }
    cmp_block['definition'] = cmp_block['definition'][0]

    # ------------------------------------------------------ 4. claim checks
    bs_ko_by_stage = {
        st: survival['refs'][f'{OS}_rank1']['by_stage'][st][L_CH1][
            f'hits_to_ko_by_{FK}_spread'] for st in map(str, STAGES)}
    lick_dmg_by_stage = {
        st: survival['refs'][f'{OS}_rank1']['by_stage'][st][L_FAST][
            f'dmg_by_{FK}_def_index'] for st in map(str, STAGES)}

    def spread_card(a, d, s, label=None):
        i = iv_to_rank_t[(a, d, s)]
        e = t_rows[i]
        return {
            'label': label, 'ivs': [a, d, s], 'rank': i + 1,
            'level': e['level'], 'cp': e['cp'],
            'atk': r4(e['atk']), 'def': r4(e['def_']), 'hp': e['hp'],
            f'{ha}_dmg_vs_rank1_{OS}': sp_tier_vs_rank1_spread[i],
            f'{ha}_ge_hi_count': {ck: sp_ge_hi_spread[ck][i] for ck in COHORTS},
            f'{ha}_ge_hi_frac': {ck: r4(sp_ge_hi_spread[ck][i] / COHORTS[ck])
                                 for ck in COHORTS},
            f'body_slam_dmg_from_rank1_{OS}': per_spread['body_slam_dmg'][i],
            'body_slams_to_ko': per_spread['body_slams_to_ko'][i],
            'hp_margin_over_prev_bs_tier': per_spread['hp_margin_over_prev_bs_tier'][i],
            'power_whips_to_ko': per_spread['power_whips_to_ko'][i],
            f'lick_dmg_from_rank1_{OS}': per_spread['lick_dmg'][i],
            f'body_slams_to_ko_by_{OS}_atk_stage': {
                st: bs_ko_by_stage[st][i] for st in map(str, STAGES)},
            f'lick_dmg_by_{OS}_atk_stage': {
                st: lick_dmg_by_stage[st][t_def_idx[i]] for st in map(str, STAGES)},
        }

    # The claim spreads are pair EDITORIAL (a community discussion this
    # page answers), so they live in the config, key slug and all.
    claim_a_cfg = bp_cfg.get('claim_a', {})
    claim_b_cfg = bp_cfg.get('claim_b', {})
    for _c in (claim_a_cfg, claim_b_cfg):
        _unknown = set(_c) - _CLAIM_KNOWN
        if _unknown:
            raise SystemExit('ABORT: [breakpoints.claim_*] unknown keys '
                             f'{sorted(_unknown)}')
    # Defaults: the rank-1 stat-product spread and the hundo, which exist
    # for every species -- so a pair with no community claim still emits a
    # well-formed (if uninteresting) claims block.
    A_IVS = tuple(claim_a_cfg.get('ivs') or (t_rows[0]['atk_iv'],
                                             t_rows[0]['def_iv'],
                                             t_rows[0]['sta_iv']))
    B_IVS = tuple(claim_b_cfg.get('ivs') or (15, 15, 15))
    A_SLUG = claim_a_cfg.get('slug') or '%d_%d_%d' % A_IVS
    B_SLUG = claim_b_cfg.get('slug') or '%d_%d_%d' % B_IVS
    A_LABEL = '%d/%d/%d' % A_IVS
    B_LABEL = '%d/%d/%d' % B_IVS
    A_KEY = claim_a_cfg.get('key') or f'a_{A_SLUG}_best_for_{ha}_bp'
    B_KEY = claim_b_cfg.get('key') or f'b_{B_SLUG}'
    A_ANSWER_KEY = claim_a_cfg.get('answer_key') or f'claim_a_{A_SLUG}'
    B_ANSWER_KEY = claim_b_cfg.get('answer_key') or f'claim_b_{B_SLUG}'

    max_all = max(sp_ge_hi_spread['all'])
    max_512 = max(sp_ge_hi_spread['top512'])
    best_all = [i for i in range(4096) if sp_ge_hi_spread['all'][i] == max_all]
    best_512 = [i for i in range(4096) if sp_ge_hi_spread['top512'][i] == max_512]
    i_a = iv_to_rank_t[A_IVS]

    claim_a = {
        'claim': claim_a_cfg.get(
            'claim', '"%s is the best possible spread for the %s bp on %s" '
                     '(placeholder: no [breakpoints.claim_a] claim text '
                     'configured for this pair)'
                     % (A_LABEL, HEAD_NAME, OPPONENT)),
        'spread': spread_card(*A_IVS, A_LABEL),
        f'clears_bp_vs_rank1_{OS}': sp_tier_vs_rank1_spread[i_a] >= hi_tier,
        'max_ge_hi_count': {'all': max_all, 'top512': max_512},
        'max_ge_hi_frac': {'all': r4(max_all / 4096), 'top512': r4(max_512 / 512)},
        'n_spreads_at_max_coverage': {'all': len(best_all), 'top512': len(best_512)},
        f'is_{A_SLUG}_at_max_coverage': {'all': i_a in best_all,
                                         'top512': i_a in best_512},
        f'n_spreads_strictly_better_than_{A_SLUG}': {
            ck: sum(1 for i in range(4096)
                    if sp_ge_hi_spread[ck][i] > sp_ge_hi_spread[ck][i_a])
            for ck in COHORTS},
        f'coverage_rank_of_{A_SLUG}': {
            ck: 1 + sum(1 for i in range(4096)
                        if sp_ge_hi_spread[ck][i] > sp_ge_hi_spread[ck][i_a])
            for ck in COHORTS},
        # OTHER spreads at the same coverage (excludes the claim spread
        # itself -- the self-inclusive count rendered as "tied with" reads
        # wrong).
        f'n_spreads_tied_with_{A_SLUG}': {
            ck: sum(1 for i in range(4096)
                    if sp_ge_hi_spread[ck][i] == sp_ge_hi_spread[ck][i_a])
                - 1
            for ck in COHORTS},
        'max_coverage_examples': [
            spread_card(t_rows[i]['atk_iv'], t_rows[i]['def_iv'],
                        t_rows[i]['sta_iv'])
            for i in sorted(best_all)[:12]],
        'best_iv_rank_at_max_coverage': min(best_all) + 1,
        'best_stat_product_spread_at_max_coverage': spread_card(
            t_rows[min(best_all)]['atk_iv'], t_rows[min(best_all)]['def_iv'],
            t_rows[min(best_all)]['sta_iv'], 'best-rank max-coverage'),
        'best_stat_product_spread_clearing_bp_vs_rank1': spread_card(
            t_rows[min(clearing)]['atk_iv'], t_rows[min(clearing)]['def_iv'],
            t_rows[min(clearing)]['sta_iv'],
            'best-rank spread clearing the bp vs rank-1 %s' % OS_NICE),
        'verdict_metric': ('"best for the %s bp" read as: number of the 4096 '
                           '%s spreads on which %s reaches '
                           'the hi tier (%d). Both a stricter reading '
                           '("clears the bp vs the rank-1 %s") and the '
                           'coverage reading are reported.'
                           % (HA, OPPONENT, HEAD_NAME, hi_tier, OS_NICE)),
    }

    sta15 = [i for i in range(4096) if t_rows[i]['sta_iv'] == 15]
    sta15_clearing = [i for i in sta15 if sp_tier_vs_rank1_spread[i] >= hi_tier]
    claim_b = {
        'claim': claim_b_cfg.get(
            'claim', '"do you not want 15 hp" -- i.e. prefer sta_iv 15 over '
                     'the low-sta stat-product-optimal spreads (no community '
                     'claim configured)'),
        'n_sta15_spreads': len(sta15),
        f'n_sta15_clearing_{ha}_bp_vs_rank1': len(sta15_clearing),
        'best_rank_sta15': min(sta15) + 1,
        'best_rank_sta15_clearing_bp': (min(sta15_clearing) + 1
                                        if sta15_clearing else None),
        f'max_{ha}_coverage_among_sta15': {
            ck: max(sp_ge_hi_spread[ck][i] for i in sta15) for ck in COHORTS},
        'best_sta15_by_iv_rank': [
            spread_card(t_rows[i]['atk_iv'], t_rows[i]['def_iv'],
                        t_rows[i]['sta_iv'])
            for i in sorted(sta15)[:8]],
        'best_sta15_clearing_bp_by_iv_rank': [
            spread_card(t_rows[i]['atk_iv'], t_rows[i]['def_iv'],
                        t_rows[i]['sta_iv'])
            for i in sorted(sta15_clearing)[:8]],
        'direct_comparison_%d_%d_%d_vs_%d_%d_%d' % (A_IVS + B_IVS): {
            A_LABEL: spread_card(*A_IVS, A_LABEL),
            B_LABEL: spread_card(*B_IVS, B_LABEL),
        },
        'sta15_max_coverage_spread': spread_card(
            *max(((t_rows[i]['atk_iv'], t_rows[i]['def_iv'], t_rows[i]['sta_iv'])
                  for i in sta15),
                 key=lambda k: sp_ge_hi_spread['all'][iv_to_rank_t[k]]),
            label='best sta15 by %s coverage' % HA),
    }

    # named_spreads: pair editorial too, except the two entries that are
    # DERIVED -- "rank-1 stat product" is a per-species fact (labelling a
    # literal IV triple that way is a mislabel waiting to happen) and the
    # hundo is 15/15/15 for everyone.
    named_cfg = bp_cfg.get('named_spreads') or [
        {'derived': 'rank1', 'label': 'rank-1 stat product'},
        {'derived': 'hundo', 'label': 'hundo'}]
    named = {}
    for spec in named_cfg:
        if spec.get('derived') == 'rank1':
            a, d, s = (t_rows[0]['atk_iv'], t_rows[0]['def_iv'],
                       t_rows[0]['sta_iv'])
        elif spec.get('derived') == 'hundo':
            a, d, s = 15, 15, 15
        elif spec.get('derived'):
            raise SystemExit('ABORT: [breakpoints.named_spreads] unknown '
                             f"derived={spec['derived']!r}")
        else:
            a, d, s = spec['ivs']
        named[f'{a}/{d}/{s}'] = spread_card(a, d, s, spec['label'])
    # exemplar of the max-coverage set with the highest HP (bulk-friendly)
    best_hp_i = max(best_all, key=lambda i: (t_rows[i]['hp'], -i))
    named['max_coverage_max_hp'] = spread_card(
        t_rows[best_hp_i]['atk_iv'], t_rows[best_hp_i]['def_iv'],
        t_rows[best_hp_i]['sta_iv'],
        'max %s coverage, highest HP within set' % HA)

    # ------------------------------------------- computed answer summary
    sp_pair_totals = {str(t): 0 for t in sp_tiers}
    for i in range(4096):
        row = sp_mat[t_atk_idx[i]]
        for o in range(4096):
            sp_pair_totals[str(row[l_def_idx[o]])] += 1
    i_b = iv_to_rank_t[B_IVS]
    sta15_full_cov = [i for i in sta15 if sp_ge_hi_spread['all'][i] == 4096]
    if len(sp_tiers) > 2:
        pair_tier_note = ('tier %d needs %s_atk / %s_def >= '
                          '%s, which only the very top-attack %s '
                          'spreads reach against the frailest %s '
                          '-- it is a rounding curiosity, not a target. '
                          'The bp everyone means is %d -> %d.'
                          % (sp_tiers[-1], PROSE_F, PROSE_O,
                             r4((sp_tiers[-1] - 1) / K_sp), FOCAL, OPPONENT,
                             base_tier, hi_tier))
    else:
        pair_tier_note = ('%s does exactly two damage tiers into %s, so the '
                          'bp is the only boundary there is: %d -> %d.'
                          % (HA, OPPONENT, base_tier, hi_tier))
    answers = {
        'note': ('every number here is computed by this script from the '
                 'arrays above; nothing is asserted without a source array'),
        f'{HEAD_KEY}_tier_boundary': {
            'tiers': sp_tiers,
            'K': K_sp,
            'identity': 'dmg = floor(K * %s_atk / %s_def) + 1'
                        % (PROSE_F, PROSE_O),
            'hi_tier': hi_tier,
            f'vs_rank1_{OS}': {
                f'{OS}_def': r4(rank1_def),
                f'{FK}_atk_needed': r4(sp_thr_hi),
                # None = the set is EMPTY (every spread clears, or none
                # does) -- a real state, not a crash (Altaria vs
                # Corviknight clears with all 4096, 2026-08-19).
                'highest_atk_value_below': (r4(max(
                    t_atk_vals[t_atk_idx[i]] for i in range(4096)
                    if sp_tier_vs_rank1_spread[i] < hi_tier))
                    if len(clearing) < 4096 else None),
                'lowest_atk_value_at_or_above': (r4(min(
                    t_atk_vals[t_atk_idx[i]] for i in clearing))
                    if clearing else None),
                'n_spreads_clearing': len(clearing),
                'n_spreads_failing': 4096 - len(clearing),
            },
            f'vs_every_{OS}': sp[f'full_coverage_vs_all_{OS}'],
            'pair_tier_totals_over_4096x4096': sp_pair_totals,
            'pair_tier_note': pair_tier_note,
            f'{OS}_def_range_by_cohort': {
                ck: {'min': r4(min(l_def_vals[l_def_idx[o]] for o in range(n))),
                     'max': r4(max(l_def_vals[l_def_idx[o]] for o in range(n)))}
                for ck, n in COHORTS.items()},
            'cohort_note': ('the bulkiest %s (def %s) is present in '
                            'every cohort down to top512, so the full-'
                            'coverage set is identical for all and top512'
                            % (OPPONENT, r4(max(l_def_vals)))),
        },
        'cmp': {'verdict': cmp_block['verdict'],
                f'min_{FK}_cmp_atk': cmp_block[f'min_{FK}_cmp_atk'],
                f'max_{OK}_cmp_atk': cmp_block[f'max_{OK}_cmp_atk'],
                'margin': cmp_block['margin']},
        A_ANSWER_KEY: {
            f'clears_bp_vs_rank1_{OS}': bool(sp_tier_vs_rank1_spread[i_a] >= hi_tier),
            'coverage_all': sp_ge_hi_spread['all'][i_a],
            'coverage_all_frac': r4(sp_ge_hi_spread['all'][i_a] / 4096),
            'coverage_top512': sp_ge_hi_spread['top512'][i_a],
            'coverage_top512_frac': r4(sp_ge_hi_spread['top512'][i_a] / 512),
            'coverage_top100': sp_ge_hi_spread['top100'][i_a],
            'max_coverage_all': max_all,
            'n_spreads_strictly_better_all':
                claim_a[f'n_spreads_strictly_better_than_{A_SLUG}']['all'],
            'n_spreads_at_max_coverage': len(best_all),
            'is_best': False if claim_a[
                f'n_spreads_strictly_better_than_{A_SLUG}']['all'] else True,
            'best_iv_rank_at_max_coverage': min(best_all) + 1,
            'best_iv_rank_clearing_bp_vs_rank1': min(clearing) + 1,
            f'iv_rank_of_{A_SLUG}': i_a + 1,
        },
        B_ANSWER_KEY: {
            'body_slams_to_ko_is_constant_at_stage0': (
                len(set(per_spread['body_slams_to_ko'])) == 1),
            'body_slams_to_ko_stage0_value': per_spread['body_slams_to_ko'][0],
            'body_slams_to_ko_histogram_by_stage': {
                st: survival['refs'][f'{OS}_rank1']['by_stage'][st][
                    L_CH1]['hits_to_ko_histogram'] for st in map(str, STAGES)},
            'power_whips_to_ko_stage0_histogram': {
                str(k): sum(1 for v in per_spread['power_whips_to_ko'] if v == k)
                for k in sorted(set(per_spread['power_whips_to_ko']))},
            f'lick_bulkpoint_vs_rank1_{OS}': survival['refs'][f'{OS}_rank1'][
                'by_stage']['0'][L_FAST]['bulkpoints'],
            'n_spreads_taking_1_lick_vs_rank1': sum(
                1 for v in per_spread['lick_dmg'] if v == 1),
            'n_spreads_taking_2_lick_vs_rank1': sum(
                1 for v in per_spread['lick_dmg'] if v == 2),
            f'{A_SLUG}_vs_{B_SLUG}': {
                f'{ha}_dmg_vs_rank1': [sp_tier_vs_rank1_spread[i_a],
                                       sp_tier_vs_rank1_spread[i_b]],
                'coverage_all': [sp_ge_hi_spread['all'][i_a],
                                 sp_ge_hi_spread['all'][i_b]],
                'coverage_all_delta': (sp_ge_hi_spread['all'][i_b]
                                       - sp_ge_hi_spread['all'][i_a]),
                'coverage_top512': [sp_ge_hi_spread['top512'][i_a],
                                    sp_ge_hi_spread['top512'][i_b]],
                'coverage_top512_delta': (sp_ge_hi_spread['top512'][i_b]
                                          - sp_ge_hi_spread['top512'][i_a]),
                'hp': [t_rows[i_a]['hp'], t_rows[i_b]['hp']],
                'body_slams_to_ko_by_stage': {
                    st: [bs_ko_by_stage[st][i_a], bs_ko_by_stage[st][i_b]]
                    for st in map(str, STAGES)},
                'lick_dmg_vs_rank1': [per_spread['lick_dmg'][i_a],
                                      per_spread['lick_dmg'][i_b]],
                'order': [A_LABEL, B_LABEL],
            },
            'n_sta15_spreads': len(sta15),
            'n_sta15_clearing_bp_vs_rank1': len(sta15_clearing),
            'n_sta15_at_full_coverage': len(sta15_full_cov),
            'best_iv_rank_sta15_at_full_coverage': (
                min(sta15_full_cov) + 1 if sta15_full_cov else None),
            'best_sta15_full_coverage_card': (
                spread_card(t_rows[min(sta15_full_cov)]['atk_iv'],
                            t_rows[min(sta15_full_cov)]['def_iv'],
                            t_rows[min(sta15_full_cov)]['sta_iv'],
                            'best-rank sta15 at full %s coverage' % HA)
                if sta15_full_cov else None),
        },
    }
    # The two legacy `n_spreads_taking_{1,2}_lick_vs_rank1` counters hardcode
    # damage values 1 and 2, which are the only two Lick can do into Thievul.
    # A different fast move lands on different tiers and would leave both
    # counters reading 0 -- a true but silently useless pair. Ship the real
    # histogram whenever the legacy pair does not account for all 4096
    # spreads (it does for Lickitung, so that file is unchanged).
    _cb = answers[B_ANSWER_KEY]
    if (_cb['n_spreads_taking_1_lick_vs_rank1']
            + _cb['n_spreads_taking_2_lick_vs_rank1']) != 4096:
        _cb['fast_move_dmg_histogram_vs_rank1'] = {
            str(k): sum(1 for v in per_spread['lick_dmg'] if v == k)
            for k in sorted(set(per_spread['lick_dmg']))}
        _cb['fast_move_dmg_histogram_note'] = (
            '%s damage taken from the rank-1 %s at stage 0, over all 4096 '
            '%s spreads. The n_spreads_taking_1/2_lick_vs_rank1 keys '
            'above are hardcoded to damage 1 and 2 (the only values Lick '
            'reaches) and read 0 here -- use this histogram instead.'
            % (lk['name'], OPPONENT, FOCAL))

    # ------------------------------------------------------- VERIFICATION
    ver = {'formula_samples': [], 'sim_checks': []}

    def independent(power, atk, def_, mtype, atypes, dtypes):
        """Formula re-implemented here from the spec in CLAUDE.md, so the
        check is not just moves.damage compared to itself.

        The type chart is a deliberate INDEPENDENT literal: calling
        type_effectiveness() would make the check compare moves.damage to
        itself. _INDEP_CHART below is a hand transcription of the full GO
        chart (non-neutral entries only; 1.6 / 0.625 / 0.390625) -- the
        original 7-pair table covered only the Thievul-vs-Licki type
        combos and KeyError'd on the first generic pair (Rollout vs
        Wigglytuff, 2026-08-19). A transcription error here fails LOUDLY:
        every sample is compared against the engine's damage, whose own
        chart is pinned by the 324-cell PvPoke test."""
        eff = 1.0
        for t in dtypes:
            eff *= _INDEP_CHART.get(mtype, {}).get(t, 1.0)
        st = STAB_MULTIPLIER if mtype in atypes else 1.0
        return math.floor(0.5 * BONUS * power * atk / def_ * eff * st) + 1

    # Every focal move in the config's arm union gets a sample: the headline
    # move at three probe points (rank-1 atk, claim-spread atk, and the
    # extreme corner), the first two other charged moves at the claim
    # spread's atk vs the rank-1 opponent, any remaining ones at the rank-1
    # focal atk vs a mid-cohort opponent. Then the opponent's kit across
    # three attack stages.
    _other_charged = [(mid, kind) for mid, kind in T_MOVES
                      if kind == 'charged' and mid != HEADLINE]
    samples = [
        (HEADLINE, HEAD_KIND, t_types, l_types, t_rows[0]['atk'], l_rows[0]['def_'], 1.0),
        (HEADLINE, HEAD_KIND, t_types, l_types, t_rows[i_a]['atk'], l_rows[0]['def_'], 1.0),
        (HEADLINE, HEAD_KIND, t_types, l_types, max(t_atk_vals), min(l_def_vals), 1.0),
    ] + [(mid, kind, t_types, l_types, t_rows[i_a]['atk'], l_rows[0]['def_'], 1.0)
         for mid, kind in _other_charged[:2]] + [
        (mid, kind, t_types, l_types, t_rows[0]['atk'], l_rows[100]['def_'], 1.0)
        for mid, kind in _other_charged[2:]] + [
        (L_FAST, 'fast', l_types, t_types, l_rows[0]['atk'], t_rows[i_a]['def_'], 1.0),
        (L_CH1, 'charged', l_types, t_types, l_rows[0]['atk'], t_rows[i_a]['def_'], 1.0),
        (L_CH1, 'charged', l_types, t_types, l_rows[0]['atk'], t_rows[0]['def_'],
         _stat_stage_mult(-1)),
        (L_CH1, 'charged', l_types, t_types, l_rows[0]['atk'], t_rows[0]['def_'],
         _stat_stage_mult(-2)),
        (L_CH2, 'charged', l_types, t_types, l_rows[0]['atk'], t_rows[0]['def_'],
         _stat_stage_mult(-4)),
    ]
    # Any opponent CHARGED move that is not neutral vs the focal gets its own
    # unstaged sample. (For Lickitung the only resisted move is the FAST one,
    # Lick/ghost, which the opponent-fast sample already covers -- so this
    # adds nothing there and the Lickitung output is unchanged.)
    # RESISTED means the damage is materially reduced (x0.625 or the
    # x0.390625 double), not any float-noise deviation from 1.0: a
    # super-effective x resisted dual type multiplies to 1.0000000149
    # under the float32 constants (Stone Edge vs flying/steel,
    # 2026-08-19) and is NEUTRAL for every damage purpose.
    resisted_charged = [m for m, k in L_MOVES if k == 'charged'
                        and type_effectiveness(move(m, k)['type'],
                                               t_types) < 0.99]
    samples += [(m, 'charged', l_types, t_types, l_rows[0]['atk'],
                 t_rows[i_a]['def_'], 1.0) for m in resisted_charged]
    for mid, kind, atypes, dtypes, a, d, m in samples:
        mv = move(mid, kind)
        got = damage(mv['power'], a * m, d, mv['type'], atypes, dtypes)
        exp = independent(mv['power'], a * m, d, mv['type'], atypes, dtypes)
        ver['formula_samples'].append({
            'move': mid, 'atk': r4(a), 'atk_stage_mult': r4(m), 'def': r4(d),
            'moves_damage': got, 'independent_formula': exp, 'match': got == exp})
    assert all(s['match'] for s in ver['formula_samples'])

    # ---- engine cross-check: real simulate() timelines
    sys.path.insert(0, str(REPO / 'scripts'))
    from battle import make_battle_pokemon  # noqa: E402

    def sim_check(t_ivs, l_ivs, t_fast, t_charged, shields):
        tp = make_battle_pokemon(FOCAL, t_fast, t_charged, LEAGUE,
                                 shields, *t_ivs, shadow=F_SHADOW)
        lp = make_battle_pokemon(OPPONENT, L_FAST, [L_CH1, L_CH2],
                                 LEAGUE, shields, *l_ivs, shadow=O_SHADOW)
        t_atk_engine, t_def_engine, t_hp_engine = tp.atk, tp.def_, tp.hp
        l_atk_engine = lp.atk
        res = simulate(tp, lp, log=True)   # mutates tp/lp (hp, energy, stages)
        seen = {}
        for line in res.timeline:
            if FOCAL + ' fast' in line and 'focal' not in seen:
                # NB: the arrow is a genuine U+2192 -- battle.py's timeline
                # emits "{species} uses {move} → {dmg} dmg" (see
                # log_event calls around battle.py:2775-2791), so this is
                # the engine's real token, not a stray unicode glyph.
                seen['focal'] = int(line.split('→')[1].split('dmg')[0])
            if OPPONENT + ' fast' in line and 'opp' not in seen:
                seen['opp'] = int(line.split('→')[1].split('dmg')[0])
        # closed-form predictions at stage 0 (first hits, before any debuff)
        ti = iv_to_rank_t[tuple(t_ivs)]
        li = [j for j in range(4096)
              if (l_rows[j]['atk_iv'], l_rows[j]['def_iv'],
                  l_rows[j]['sta_iv']) == tuple(l_ivs)][0]
        f_mat = offense[t_fast]['dmg_by_atk_index_x_def_index']
        pred_focal = f_mat[t_atk_idx[ti]][l_def_idx[li]]
        pred_lick = damage(lk['power'], l_rows[li]['atk'], t_rows[ti]['def_'],
                           lk['type'], l_types, t_types)
        return {
            f'{FK}_ivs': list(t_ivs), f'{OK}_ivs': list(l_ivs),
            f'{FK}_charged': t_charged, 'shields': shields,
            f'engine_{FK}_atk': r4(t_atk_engine),
            f'closed_form_{FK}_atk': r4(t_rows[ti]['atk']),
            f'engine_{FK}_def': r4(t_def_engine), f'engine_{FK}_hp': t_hp_engine,
            f'closed_form_{FK}_hp': t_rows[ti]['hp'],
            f'engine_{OS}_atk': r4(l_atk_engine),
            f'closed_form_{OS}_atk': r4(l_rows[li]['atk']),
            f'sim_{t_fast.lower()}_dmg': seen.get('focal'),
            f'closed_form_{t_fast.lower()}_dmg': pred_focal,
            'sim_lick_dmg': seen.get('opp'), 'closed_form_lick_dmg': pred_lick,
            'match': (seen.get('focal') == pred_focal
                      and seen.get('opp') == pred_lick
                      and t_hp_engine == t_rows[ti]['hp']
                      and abs(t_atk_engine - t_rows[ti]['atk']) < 1e-9
                      and abs(t_def_engine - t_rows[ti]['def_']) < 1e-9
                      and abs(l_atk_engine - l_rows[li]['atk']) < 1e-9),
        }

    rank1_t_ivs = (t_rows[0]['atk_iv'], t_rows[0]['def_iv'], t_rows[0]['sta_iv'])
    rank1_l_ivs = (l_rows[0]['atk_iv'], l_rows[0]['def_iv'], l_rows[0]['sta_iv'])
    probe_cfgs = bp_cfg.get('sim_probes') or [
        {'focal_ivs': list(rank1_t_ivs), 'opp_ivs': list(rank1_l_ivs),
         'arm': i, 'shields': min(i, 2)} for i in range(len(ARMS))]
    for pc in probe_cfgs:
        ver['sim_checks'].append(sim_check(
            *_probe(pc, ARMS, rank1_t_ivs, rank1_l_ivs, 0)))
    assert all(c['match'] for c in ver['sim_checks'])

    # ---- engine cross-check: the opponent-attack debuff lowers the
    # charged-slot-1 damage exactly as the closed form says. Skipped (and
    # therefore absent from the JSON) when the focal kit has no debuff move.
    if debuff_mid:
        iv_to_rank_l = {(e['atk_iv'], e['def_iv'], e['sta_iv']): i
                        for i, e in enumerate(l_rows)}
        # Probe selection: a configured stage_probe is authoritative (the
        # thievul pins). Without one, the rank1-vs-rank1 default cannot be
        # assumed to exercise the debuff (Wigglytuff-vs-Lickilicky never
        # throws Icy Wind in that fight, 2026-08-19), so candidates are
        # tried in order until one OBSERVES the ladder: longer fights via
        # shields, then a max-def focal (survives longer), then a min-atk
        # opponent (kills slower).
        # SEAT AMBIGUITY (same-species pairs whose opponent also carries
        # the debuff move, first hit: the Thievul cross-arm mirror,
        # 2026-08-24): timeline lines carry only the species name, so
        # 'uses <debuff>' cannot be attributed by seat -- the opponent's
        # own throws made any_thrown a false positive there, masking an
        # honest debuff_unreachable (the NS+IW arm never throws Icy Wind
        # vs the IW+PR arm). In that case the focal's throws are counted
        # from the OPPONENT's post-fight attack stage instead (simulate
        # mutates lp), which is sound only when no OTHER move in either
        # kit can touch the opponent's attack stage -- verified here.
        ambiguous_seat = (FOCAL == OPPONENT
                          and debuff_mid in (L_FAST, L_CH1, L_CH2))
        if ambiguous_seat:
            if F_SHADOW != O_SHADOW:
                raise SystemExit(
                    'ABORT: the stage probe is seat-ambiguous (both seats '
                    f'are {FOCAL}) but the shadow flags differ, so the two '
                    'seats cannot be given identical stats and the '
                    'name-ambiguous ladder parse is unsound -- the parser '
                    'needs per-seat move logs before this pair can be '
                    'checked')
            # Moves that could confound lp.atk_stage. A CHANCE self-buff
            # (e.g. Night Slash, 12.5%) is applied by the engine's
            # deterministic meter (battle.py _buff_apply_meters: starts
            # at the chance -- 0.0 for exactly 0.5 -- accumulates per
            # throw, fires on an integer crossing), so it is harmless in
            # any fight whose pooled throw count of that move stays below
            # the meter's first firing; that is checked PER PROBE FIGHT
            # in the candidate loop below. Guaranteed movers make the
            # attribution unsound outright.
            def _meter_can_fire(chance, n_throws):
                meter = 0.0 if chance == 0.5 else chance
                for _ in range(n_throws):
                    if math.floor(meter + chance) > math.floor(meter):
                        return True
                    meter += chance
                return False

            opp_chance_atk_buffs = []
            hard_movers = [
                mid for mid, kind in T_MOVES
                if mid != debuff_mid
                and (mv := move(mid, kind)).get('buffTarget') == 'opponent'
                and mv.get('buffs') and mv['buffs'][0] != 0]
            for mid, kind in ((L_FAST, 'fast'), (L_CH1, 'charged'),
                              (L_CH2, 'charged')):
                mv = move(mid, kind)
                if (mv.get('buffTarget') == 'self' and mv.get('buffs')
                        and mv['buffs'][0] != 0):
                    ch = float(mv.get('buffApplyChance', 0) or 0)
                    if ch >= 1:
                        hard_movers.append(mid)
                    elif ch > 0:
                        opp_chance_atk_buffs.append((mv['name'], ch))
            if hard_movers:
                raise SystemExit(
                    'ABORT: the stage probe is seat-ambiguous (both seats '
                    f'are {FOCAL} and both carry {debuff_mid}) and '
                    f'{sorted(set(hard_movers))} can also move the '
                    "opponent's attack stage, so the stage-based throw "
                    'attribution is unsound -- the parser needs per-seat '
                    'move logs before this pair can be checked')
        if 'stage_probe' in bp_cfg:
            candidates = [bp_cfg['stage_probe']]
        else:
            maxdef_t = max(t_rows, key=lambda e: e['def_'])
            minatk_l = min(l_rows, key=lambda e: e['atk'])
            md = [maxdef_t['atk_iv'], maxdef_t['def_iv'], maxdef_t['sta_iv']]
            ma = [minatk_l['atk_iv'], minatk_l['def_iv'], minatk_l['sta_iv']]
            if ambiguous_seat:
                # Same-species/same-stats probes keep the ladder readable
                # under the name-ambiguous parse (either seat's unshielded
                # hit of the move is a sample of the SAME damage ladder),
                # so the long-fight candidates use IDENTICAL builds on
                # both seats instead of max-def-vs-min-atk.
                candidates = [{}, {'shields': 1}, {'shields': 2},
                              {'focal_ivs': md, 'opp_ivs': md,
                               'shields': 2},
                              {'focal_ivs': ma, 'opp_ivs': ma,
                               'shields': 2},
                              {'focal_ivs': md, 'opp_ivs': md,
                               'shields': 0}]
            else:
                candidates = [{}, {'shields': 1}, {'shields': 2},
                              {'focal_ivs': md, 'shields': 2},
                              {'focal_ivs': md, 'opp_ivs': ma, 'shields': 2},
                              {'focal_ivs': md, 'opp_ivs': ma, 'shields': 0}]
        # LADDER SOURCE. The strictly correct reference is the PROBE
        # opponent actually simulated. stage_ladder_from_rank1=true
        # preserves the SHIPPED thievul_lickilicky behavior instead: its
        # ladder was built from the rank-1 opponent (l_rows[0]) while the
        # probe simulated (8,14,15) -- a documented latent bug kept only
        # for byte-identical rebuilds (the check passed there because the
        # observed values land in both ladders; the correct ladder differs
        # at stage -3: 22, not 21). Flip the flag off and re-bake to fix.
        ladder_from_rank1 = bool(bp_cfg.get('stage_ladder_from_rank1'))

        chosen = None
        any_thrown = False
        n_skipped = 0
        for ci, pc in enumerate(candidates):
            st_ivs, sl_ivs, st_fast, st_charged, st_shields = _probe(
                pc, ARMS, rank1_t_ivs, rank1_l_ivs, 0)
            if debuff_mid not in st_charged:
                raise SystemExit('ABORT: [breakpoints] stage_probe arm does '
                                 f'not carry the debuff move {debuff_mid}')
            tp = make_battle_pokemon(FOCAL, st_fast, st_charged,
                                     LEAGUE, st_shields, *st_ivs,
                                     shadow=F_SHADOW)
            lp = make_battle_pokemon(OPPONENT, L_FAST, [L_CH1, L_CH2],
                                     LEAGUE, st_shields, *sl_ivs,
                                     shadow=O_SHADOW)
            res = simulate(tp, lp, log=True)
            # Shielded throws land 1 damage regardless of stage ("→
            # SHIELDED (1 dmg)") and carry no stage information -- skip
            # them; only unshielded hits test the ladder.
            bs_hits = [int(l.split('→')[1].split('dmg')[0])
                       for l in res.timeline
                       if bs['name'] + ' →' in l and 'SHIELDED' not in l]
            iw_count = sum(1 for l in res.timeline
                           if 'uses ' + _dbf['name'] in l)
            if ambiguous_seat:
                if (tuple(st_ivs) != tuple(sl_ivs)):
                    raise SystemExit(
                        'ABORT: [breakpoints] stage_probe gives the two '
                        f'seats different builds, but both seats are {FOCAL} '
                        'and the timeline parse cannot attribute hits by '
                        'name -- a seat-ambiguous probe must use IDENTICAL '
                        'builds so either seat samples the same ladder')
                # Chance self-buffs in the opponent's kit are harmless
                # only while the buff meter cannot have fired; the pooled
                # (both-seat) throw count bounds either single seat's. A
                # fight where the meter COULD have fired is unsound for
                # this candidate both ways (a buffed seat's hit would sit
                # at a positive stage, outside the 0..-4 ladder), so the
                # candidate is skipped, not fatal -- another candidate
                # may still observe the ladder cleanly.
                meter_unsound = False
                for mv_name, ch in opp_chance_atk_buffs:
                    n = sum(1 for l in res.timeline
                            if 'uses ' + mv_name in l)
                    if _meter_can_fire(ch, n):
                        print(f'NOTE: stage-probe candidate {ci} skipped: '
                              f'{mv_name} (chance self-buff, {ch:g}) was '
                              f'thrown {n} times pooled across the two '
                              'seats, enough for the engine buff meter to '
                              'fire, so neither the throw attribution nor '
                              'the observed ladder is sound in this fight')
                        meter_unsound = True
                        break
                if meter_unsound:
                    n_skipped += 1
                    continue
                # lp is mutated by simulate; with the sole-mover guard
                # above, a negative opponent attack stage can only come
                # from the FOCAL's debuff throws. (A debuff throw that
                # faints the opponent may not register a stage; such a
                # fight ends before the ladder is observable anyway.)
                thrown_here = lp.atk_stage < 0
            else:
                thrown_here = iw_count > 0
            any_thrown = any_thrown or thrown_here
            ti = iv_to_rank_t[tuple(st_ivs)]
            ladder_atk = (l_rows[0]['atk'] if ladder_from_rank1
                          else l_rows[iv_to_rank_l[tuple(sl_ivs)]]['atk'])
            pred_by_stage = {st: damage(bs['power'],
                                        ladder_atk * _stat_stage_mult(st),
                                        t_rows[ti]['def_'], bs['type'],
                                        l_types, t_types)
                             for st in STAGES}
            flat = len(set(pred_by_stage.values())) == 1
            observed = bool(bs_hits) and (
                flat or any(v != pred_by_stage[0] for v in bs_hits))
            if observed:
                chosen = ci
                break
        if chosen is None and not any_thrown and 'stage_probe' not in bp_cfg:
            # The focal never FUNDED the debuff move in any candidate fight
            # (first case: Charm-Wigglytuff never reaches Icy Wind vs
            # Lickilicky, 0 throws in 36 extreme spread/shield combos,
            # 2026-08-19). The ladder describes a move that does not fly in
            # this matchup, so there is nothing to cross-check -- a TRUE,
            # recorded finding, not a skipped one.
            ver[f'{debuff_mid.lower()}_stage_check'] = {
                'debuff_unreachable': True,
                'note': (f'{_dbf["name"]} was never thrown in any of '
                         f'the {len(candidates) - n_skipped} probe fights '
                         'tried (extreme spread/shield candidates'
                         + (f'; {n_skipped} further candidate(s) skipped '
                            'as unsound for the seat-ambiguous parse'
                            if n_skipped else '')
                         + '), so the '
                         'stage ladder could not be exercised in this '
                         'matchup and has no observed in-matchup '
                         'consequence. Recorded, not silently skipped; '
                         'set [breakpoints] stage_probe to override.'),
                'candidates_tried': len(candidates) - n_skipped,
            }
        elif chosen is None:
            raise SystemExit(
                'ABORT: no stage probe observed the %s debuff (tried %d '
                'candidate fights; the move WAS thrown in at least one, so '
                'it is reachable); set [breakpoints] stage_probe by hand '
                'to a fight that exercises it' % (_dbf['name'],
                                                  len(candidates)))
    if debuff_mid and chosen is not None:
        ver[f'{debuff_mid.lower()}_stage_check'] = {
            f'{FK}_ivs': list(st_ivs), f'{OK}_ivs': list(sl_ivs),
            'shields': st_shields,
            f'{debuff_mid.lower()}s_thrown': iw_count,
            'sim_body_slam_damages_in_order': bs_hits,
            'closed_form_body_slam_by_stage': {str(k): v
                                               for k, v in pred_by_stage.items()},
            'note': ('each observed %s damage must equal the closed-form '
                     'value at some attack stage 0..%d'
                     % (bs['name'], STAGES[-1]))
                    + (' SEAT-AMBIGUOUS PARSE: both seats are %s and both '
                       'carry %s, so the thrown count and the observed '
                       'damages pool the two seats; the probe builds are '
                       'identical, so either seat samples the same ladder, '
                       "and the focal's own throws were confirmed from the "
                       "opponent's post-fight attack stage."
                       % (FOCAL, _dbf['name']) if ambiguous_seat else ''),
            'all_observed_in_closed_form_set': all(
                v in set(pred_by_stage.values()) for v in bs_hits),
        }
        if chosen > 0:
            # New-pair auto-search only; a configured probe is candidate 0,
            # so the thievul payloads never gain this field.
            ver[f'{debuff_mid.lower()}_stage_check']['auto_probe'] = (
                'default rank1-vs-rank1 fight never exercised the debuff; '
                f'auto-probe candidate {chosen} (of {len(candidates)}) '
                'was the first to observe it')
        assert bs_hits, 'no charged-slot-1 hit landed; the stage check would pass vacuously'
        ladder_is_flat = flat
        if ladder_is_flat:
            # The closed form itself says the debuff CANNOT change this
            # damage (tier boundaries too coarse for this power/def pair --
            # first hit generically: Body Slam vs Wigglytuff, 2026-08-19).
            # Nothing to observe, so the non-stage-0 assert would demand
            # the impossible; record the flatness instead of skipping
            # silently.
            ver[f'{debuff_mid.lower()}_stage_check']['note'] += (
                ' LADDER IS FLAT: the closed form predicts the same '
                'damage at every stage 0..%d, so the debuff cannot be '
                'observed in this quantity and the non-stage-0 assert is '
                'vacuously untestable (recorded, not skipped silently).'
                % STAGES[-1])
        else:
            assert any(v != pred_by_stage[0] for v in bs_hits), (
                'every observed hit is the stage-0 value although the '
                'ladder is non-flat, so the %s debuff itself is untested '
                '-- set [breakpoints] stage_probe to a longer fight (more '
                'shields / bulkier spreads)' % _dbf['name'])
            # the timeline parse for iw_count is on the move's DISPLAY
            # name; a miss would read 0 silently, and the stage evidence
            # above proves at least one landed. (Only assertable when the
            # ladder is non-flat -- a flat ladder carries no such proof.)
            assert iw_count, ('the "%s" timeline parse found no throw '
                              'although the damage drop proves one landed'
                              % _dbf['name'])
        assert ver[f'{debuff_mid.lower()}_stage_check'][
            'all_observed_in_closed_form_set']

    # ---- engine cross-check: resisted opponent CHARGED moves.
    # The fast-move comparison in sim_check() already pins a resisted move
    # whenever the opponent's FAST move is resisted (Lickitung's Lick is
    # ghost), but a resisted CHARGED move (Lickilicky's Shadow Ball, ghost,
    # x0.625 into dark) never appears there. This block is empty -- and
    # therefore absent from the JSON -- whenever every opponent charged move
    # is neutral, which is exactly the Lickitung case.
    if resisted_charged:
        rt_ivs, rl_ivs, rt_fast, rt_charged, r_shields = _probe(
            bp_cfg.get('resisted_probe', {}), ARMS, rank1_t_ivs, rank1_l_ivs, 0)
        checks = []
        for mid in resisted_charged:
            mv = move(mid, 'charged')
            t_ivs, l_ivs, shields = rt_ivs, rl_ivs, r_shields
            hits, probe_set, thrown_by_default = None, None, None
            # First ask whether the DEFAULT moveset ever throws it; if the
            # engine prefers the other charged move every time, fall back to a
            # single-charged-move build so the damage still gets pinned
            # against a real timeline (and record that it took a forced build).
            # MIRROR seat ambiguity: the timeline line '<species> uses
            # <move>' cannot tell the two seats apart, so on a mirror the
            # FOCAL's probe kit must exclude the probed move (else its own
            # throws pollute the observed set -- Corviknight, 2026-08-20).
            focal_kit = list(rt_charged)
            if FOCAL == OPPONENT and F_SHADOW == O_SHADOW:
                focal_kit = [c for c in rt_charged if c != mid]
            if not focal_kit:
                checks.append(dict(
                    used={f'{FK}_ivs': list(t_ivs),
                          'opponent_ivs': list(l_ivs)},
                    move=mid, skipped=(
                        'mirror pair and the probed move is the focal\'s '
                        'only charged move: the timeline cannot attribute '
                        'throws to a seat, so this check is not runnable '
                        '-- recorded, not silent')))
                continue
            for cand in ([L_CH1, L_CH2], [mid]):
                tp = make_battle_pokemon(FOCAL, rt_fast,
                                         focal_kit, LEAGUE,
                                         shields, *t_ivs, shadow=F_SHADOW)
                lp = make_battle_pokemon(OPPONENT, L_FAST, cand,
                                         LEAGUE, shields, *l_ivs,
                                         shadow=O_SHADOW)
                res = simulate(tp, lp, log=True)
                obs = [int(l.split('→')[1].split('dmg')[0])
                       for l in res.timeline
                       if mv['name'] + ' →' in l and 'SHIELDED' not in l]
                if thrown_by_default is None:
                    thrown_by_default = bool(obs)
                if obs:
                    hits, probe_set = obs, list(cand)
                    break
            ti = iv_to_rank_t[tuple(t_ivs)]
            li = [j for j in range(4096)
                  if (l_rows[j]['atk_iv'], l_rows[j]['def_iv'],
                      l_rows[j]['sta_iv']) == tuple(l_ivs)][0]
            used = {f'{FK}_ivs': list(t_ivs), 'opponent_ivs': list(l_ivs),
                    'shields': shields, 'probe_opponent_charged': probe_set,
                    'thrown_with_default_moveset': thrown_by_default}
            assert hits, ('%s never landed in any probe matchup; the check '
                          'would pass vacuously' % mid)
            # The OPPONENT's own atk-raising moves (Air Cutter's chance
            # buff fires deterministically via the sim's buffApplyMeter)
            # push observed damage ABOVE the stage-0 value -- the
            # closed-form set must span the reachable positive stages
            # too, not only the focal-debuff negatives (Corviknight
            # mirror, 2026-08-20).
            _opp_kit_moves = [move(L_FAST, 'fast')] + [
                move(c, 'charged') for c in (probe_set or [mid])]
            _opp_self_buffs = any(
                (mv2.get('buffTarget') == 'self' and mv2.get('buffs')
                 and mv2['buffs'][0] > 0) for mv2 in _opp_kit_moves)
            _stages_r = sorted(set(STAGES)
                               | (set(range(0, 5)) if _opp_self_buffs
                                  else {0}))
            pred = {st: damage(mv['power'],
                               l_rows[li]['atk'] * _stat_stage_mult(st),
                               t_rows[ti]['def_'], mv['type'], l_types, t_types)
                    for st in _stages_r}
            # The neutral baseline: what the same-power move would do with
            # effectiveness 1.0. The shipped (thievul) computation modeled
            # it as a literal normal-TYPE move, which only works when the
            # focal takes normal neutrally -- vs a steel focal the baseline
            # is itself resisted and the visibility check self-defeats
            # (Corviknight, 2026-08-19). When normal is not neutral vs the
            # focal, compute the eff=1.0 closed form with the move's OWN
            # stab instead (byte-identical path kept for the shipped pins).
            baseline_note = None
            if type_effectiveness('normal', t_types) == 1.0:
                neutral = {st: damage(mv['power'],
                                      l_rows[li]['atk'] * _stat_stage_mult(st),
                                      t_rows[ti]['def_'], 'normal', l_types,
                                      t_types) for st in _stages_r}
            else:
                _stab_m = (STAB_MULTIPLIER if mv['type'] in l_types else 1.0)
                neutral = {st: math.floor(
                    0.5 * BONUS * mv['power']
                    * (l_rows[li]['atk'] * _stat_stage_mult(st))
                    / t_rows[ti]['def_'] * 1.0 * _stab_m) + 1
                    for st in _stages_r}
                baseline_note = (
                    'the focal resists normal, so the baseline is the '
                    'eff=1.0 closed form with the move\'s own stab, not a '
                    'literal normal-type move')
            check = dict(
                used, move=mid, move_type=mv['type'],
                **{f'effectiveness_vs_{FK}': r4(type_effectiveness(mv['type'],
                                                                   t_types))},
                sim_damages_in_order=hits,
                closed_form_by_stage={str(k): v for k, v in pred.items()},
                same_power_neutral_by_stage={str(k): v
                                             for k, v in neutral.items()},
                resistance_is_visible=all(pred[st] < neutral[st]
                                          for st in STAGES),
                all_observed_in_closed_form_set=all(
                    v in set(pred.values()) for v in hits))
            if baseline_note:
                check['neutral_baseline_note'] = baseline_note
            checks.append(check)
        ver['resisted_charged_sim_checks'] = checks
        ver['resisted_charged_note'] = (
            'each observed damage must equal the closed-form value at some '
            'opponent attack stage 0..%d, and the resisted value must be '
            'strictly below what the same-power NEUTRAL move would do '
            '(otherwise the type resistance would be untested). '
            'thrown_with_default_moveset=false means the engine never chose '
            'the move with the default charged pair, so the probe forced it '
            'by giving the opponent that move alone -- the damage numbers '
            'are still real engine output, but in the default matchup the '
            'move simply never fires.' % STAGES[-1])
        assert all(c['all_observed_in_closed_form_set']
                   and c['resistance_is_visible']
                   for c in checks if 'skipped' not in c)

    # ---------------------------------------------------------------- emit
    out = {
        'meta': meta,
        'moves': moves_meta,
        'spread_index': {
            FK: {k: T[k] for k in ('atk_values', 'atk_index',
                                   'def_values', 'def_index',
                                   'hp_values', 'hp_index')},
            OK: {k: L[k] for k in ('atk_values', 'atk_index',
                                   'def_values', 'def_index',
                                   'hp_values', 'hp_index')},
            'note': ('*_values are the sorted distinct stat values; '
                     '*_index[r] is the value index for iv_rank row r '
                     '(rank r+1). Every tier table is keyed by value index.'),
        },
        f'{FK}_offense': {'defender': OPPONENT, 'moves': offense},
        f'{OK}_offense': {'defender': FOCAL, 'moves': l_offense},
        'survival': survival,
        'cmp': cmp_block,
        'claims': {A_KEY: claim_a, B_KEY: claim_b},
        'answers': answers,
        'named_spreads': named,
        'verification': ver,
    }
    # round stat value lists for compactness (2dp is well inside the
    # nearest tier boundary; tier tables were computed at full precision)
    for sp_key in (FK, OK):
        for vk in ('atk_values', 'def_values'):
            out['spread_index'][sp_key][vk] = [
                r4(v) for v in out['spread_index'][sp_key][vk]]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(out, separators=(',', ':')))
    os.replace(tmp, OUT)
    size = OUT.stat().st_size
    print(f'wrote {OUT} ({size:,} bytes)')
    print(f'{HA} tiers {sp_tiers}; hi tier {hi_tier} needs {FK} atk >= '
          f'{sp_thr_hi:.4f} vs rank-1 {OS_NICE} (def {rank1_def:.4f}); '
          f'{len(clearing)}/4096 spreads clear')
    print('CMP:', cmp_block['verdict'],
          f"(min {FOCAL} {cmp_block[f'min_{FK}_cmp_atk']} vs "
          f"max {OS_NICE} {cmp_block[f'max_{OK}_cmp_atk']})")
    print(f'{A_LABEL}:', json.dumps(claim_a['spread'], indent=None))
    print('max coverage all/top512:', max_all, max_512,
          f'| {A_LABEL} at max?', claim_a[f'is_{A_SLUG}_at_max_coverage'])


if __name__ == '__main__':
    main()
