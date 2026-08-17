#!/usr/bin/env python
"""Closed-form breakpoint / mechanism layer for the Thievul-vs-Licki
IV-robustness analysis (one-off, 2026-08-16 Thievul CD).

Runs against either evolution stage of the Licki line:
`--opponent lickitung` (default) or `--opponent lickilicky`.

Companion to `scripts/thievul_licki_bake.py` (which bakes the 4096x4096
simulated joint grids). This script computes the *damage-tier structure*
that explains those grids, and answers the two HSH-discord claims:

  (a) "6/15/5 is the best possible spread for the Sucker Punch bp on Licki"
  (b) "do you not want 15 hp"

Everything here is closed-form: damage comes from `gopvpsim.moves.damage`
(the same function `battle.py` imports as `calc_damage`), stat-stage
multipliers from `gopvpsim.battle._stat_stage_mult`, and IV spreads /
stats from `gopvpsim.pokemon.iv_rank(species, league='great')` -- the same
canonical stat-product order both axes of the bake use.

Output: userdata/thievul_licki/breakpoints.json (lickitung) or
userdata/thievul_lickilicky/breakpoints.json (lickilicky), embeddable
verbatim as `TL_DATA.breakpoints`.

The JSON schema/key names are IDENTICAL for both opponents (the page
renderer reads them positionally), so a handful of keys carry the
Lickitung-era names -- `spread_index.lickitung`, `lickitung_offense`,
`max_lickitung_cmp_atk`, and the `lick_* / body_slam_* / power_whip_*`
survival slots. For Lickilicky those name SLOTS, not moves:
`lick_* = fast move (Rollout)`, `body_slam_* = first charged move`,
`power_whip_* = second charged move (Shadow Ball)`. `meta.move_slots`
and `meta.schema_note` record the real move id behind every slot so a
renderer can relabel instead of mislabelling.

Run:  direnv exec . python scripts/thievul_licki_breakpoints.py
      direnv exec . python scripts/thievul_licki_breakpoints.py --opponent lickilicky
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

REPO = pathlib.Path(__file__).resolve().parent.parent

FOCAL = 'Thievul'
LEAGUE = 'great'

# Thievul's kit under study. SUCKER_PUNCH is the fast move; the three
# charged moves span both baked movesets (ICY_WIND + PLAY_ROUGH and
# NIGHT_SLASH + ICY_WIND).
T_MOVES = [('SUCKER_PUNCH', 'fast'), ('ICY_WIND', 'charged'),
           ('PLAY_ROUGH', 'charged'), ('NIGHT_SLASH', 'charged')]

# Opponent kits are PvPoke's GL rankings default for each species (verified
# against gopvpsim.data.get_default_moveset(species, 'great', shadow=False)).
# Order is [fast, charged_1, charged_2] and IS the slot order the JSON keys
# encode -- see the module docstring.
OPPONENTS = {
    'lickitung': {
        'species': 'Lickitung',
        'outdir': 'thievul_licki',
        'moves': [('LICK', 'fast'), ('BODY_SLAM', 'charged'),
                  ('POWER_WHIP', 'charged')],
    },
    'lickilicky': {
        'species': 'Lickilicky',
        'outdir': 'thievul_lickilicky',
        'moves': [('ROLLOUT', 'fast'), ('BODY_SLAM', 'charged'),
                  ('SHADOW_BALL', 'charged')],
    },
}
# ICY_WIND applies buffs [-1, 0] to the opponent -> opponent attack stages.
STAGES = [0, -1, -2, -3, -4]
COHORTS = {'all': 4096, 'top512': 512, 'top100': 100, 'rank1': 1}


def r2(x):
    return round(float(x), 2)


def r4(x):
    return round(float(x), 4)


# ---------------------------------------------------------------------------
# Spread tables
# ---------------------------------------------------------------------------

def spread_table(species):
    """iv_rank rows plus value/index compaction for atk, def, hp.

    Damage is a function of the *stat value*, and each species has far
    fewer distinct stat values (Thievul: 89 atk, 123 def) than the 4096
    spreads -- so every tier table below is indexed by stat value, and
    `*_index` maps rank order -> value index.
    """
    rows = iv_rank(species, league=LEAGUE)
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--opponent', choices=sorted(OPPONENTS), default='lickitung')
    args = ap.parse_args()
    cfg = OPPONENTS[args.opponent]
    OPPONENT = cfg['species']
    L_MOVES = cfg['moves']
    L_FAST, L_CH1, L_CH2 = (m[0] for m in L_MOVES)
    OUT = REPO / 'userdata' / cfg['outdir'] / 'breakpoints.json'

    gm = load_gamemaster()
    # The opponent kit must BE PvPoke's GL rankings default, never a guess
    # from the gamemaster's legal-move pool (CLAUDE.md testing note).
    _d_fast, _d_charged = get_default_moveset(OPPONENT, LEAGUE, shadow=False)
    assert [_d_fast] + list(_d_charged) == [m[0] for m in L_MOVES], (
        OPPONENT, _d_fast, _d_charged, L_MOVES)
    sp_index = {p['speciesName']: p for p in gm['pokemon']}
    t_types = parse_types(sp_index[FOCAL])
    l_types = parse_types(sp_index[OPPONENT])
    fast_moves, charged_moves = get_moves()

    def move(mid, kind):
        return dict(fast_moves[mid] if kind == 'fast' else charged_moves[mid])

    T = spread_table(FOCAL)
    L = spread_table(OPPONENT)
    t_rows, l_rows = T['rows'], L['rows']
    iv_to_rank_t = {(e['atk_iv'], e['def_iv'], e['sta_iv']): i
                    for i, e in enumerate(t_rows)}

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
                       "gopvpsim.pokemon.iv_rank(species, league='great') "
                       'order; index i = stat-product rank i+1 (same order '
                       'as the baked joint grids)'),
        'cohorts': {k: ('%s iv_rank rows 0..%d' % (OPPONENT, n - 1))
                    for k, n in COHORTS.items()},
        'cohort_sizes': dict(COHORTS),
        'model': ('closed-form damage tiers only. No shields, no energy, '
                  'no timing -- the simulated grids carry the real fight. '
                  'Use this layer to EXPLAIN the grids, not to replace them.'),
    }
    # The JSON key names are the Lickitung-era ones for BOTH opponents so a
    # single renderer reads both files. For Lickitung they happen to be
    # literal; for anyone else they are slots, and reading a move name out
    # of a key would mislabel the tables -- so ship the slot map.
    keys_are_literal = (OPPONENT == 'Lickitung'
                        and (L_FAST, L_CH1, L_CH2)
                        == ('LICK', 'BODY_SLAM', 'POWER_WHIP'))
    # move_slots is emitted ALWAYS, including when the key names happen to
    # be literal: the renderer's only honest alternative to reading it is a
    # hardcoded Lickitung-era move name, and a page that silently falls
    # back to one is a page that can print a confidently wrong move.
    meta['move_slots'] = {'fast': L_FAST, 'charged_1': L_CH1,
                          'charged_2': L_CH2}
    if not keys_are_literal:
        meta['schema_note'] = (
            'key names are held fixed across opponents so one renderer '
            'reads both files. Keys spelled "lickitung" name THE OPPONENT '
            '(meta.opponent = %s), and the survival / claim keys spelled '
            '"lick_*", "body_slam_*", "power_whip_*" name the fast, first-'
            'charged and second-charged SLOTS respectively -- here %s, %s '
            'and %s. Relabel from meta.move_slots; do NOT read a move name '
            'out of a key.' % (OPPONENT, L_FAST, L_CH1, L_CH2))

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

    # --------------------------------------------- Thievul offense (part 1)
    t_atk_vals = T['atk_values']
    l_def_vals = L['def_values']
    l_def_idx = L['def_index']          # licki rank -> def value index
    t_atk_idx = T['atk_index']          # thievul rank -> atk value index
    rank1_licki_def_i = l_def_idx[0]

    offense = {}
    for mid, kind in T_MOVES:
        mv = move(mid, kind)
        mat = dmg_matrix(mv['power'], t_atk_vals, l_def_vals, mv['type'],
                         t_types, l_types)
        tiers = sorted({v for row in mat for v in row})
        # closed-form ratio thresholds: dmg >= tier iff K*atk/def >= tier-1
        K = (0.5 * BONUS * mv['power']
             * type_effectiveness(mv['type'], l_types)
             * stab(mv['type'], t_types))
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
            'dmg_vs_rank1_licki_by_atk_index': [mat[ai][rank1_licki_def_i]
                                                for ai in range(len(t_atk_vals))],
        }
        offense[mid] = entry

    # ------------------------------------------ Sucker Punch: the headline
    sp = offense['SUCKER_PUNCH']
    sp_tiers = sp['tiers']
    sp_mat = sp['dmg_by_atk_index_x_def_index']
    base_tier = sp_tiers[0]
    hi_tier = base_tier + 1          # the breakpoint everyone is chasing
    K_sp = sp['damage_constant_K']
    # `answers.sucker_punch_tier_boundary.pair_tier_note` names tiers 6/7/8
    # literally; fail loudly rather than ship prose that lies.
    assert sp_tiers == [6, 7, 8], sp_tiers

    # per-Thievul-spread counts of Lickitung spreads taking >= hi_tier
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
    sp_tier_vs_rank1_spread = [sp_mat[t_atk_idx[i]][rank1_licki_def_i]
                               for i in range(4096)]

    # exact atk thresholds per Lickitung defense value
    per_licki_def = []
    for di, dv in enumerate(l_def_vals):
        thr = {}
        for t in sp_tiers[1:]:
            need = (t - 1) * dv / (0.5 * BONUS * 8
                                   * type_effectiveness('dark', l_types)
                                   * stab('dark', t_types))
            achievable = [a for a in t_atk_vals if a >= need]
            thr[str(t)] = {
                'min_atk_required': r4(need),
                'reachable_by_thievul': bool(achievable),
                'min_thievul_atk_value_clearing': (r2(achievable[0])
                                                   if achievable else None),
                'n_thievul_spreads_clearing': sum(
                    1 for i in range(4096) if t_atk_vals[t_atk_idx[i]] >= need),
            }
        per_licki_def.append({'def_index': di, 'def_value': r2(dv),
                              'atk_threshold_for_tier': thr})

    # min atk_iv needed to clear the hi tier vs rank-1 Lickitung, per (def_iv, sta_iv)
    min_atk_iv_grid = [[None] * 16 for _ in range(16)]
    for i, e in enumerate(t_rows):
        if sp_tier_vs_rank1_spread[i] >= hi_tier:
            d, s, a = e['def_iv'], e['sta_iv'], e['atk_iv']
            cur = min_atk_iv_grid[d][s]
            if cur is None or a < cur:
                min_atk_iv_grid[d][s] = a

    rank1_def = l_rows[0]['def_']
    sp_thr_hi = (hi_tier - 1) * rank1_def / (0.5 * BONUS * 8 * 1.0
                                             * STAB_MULTIPLIER)
    clearing = [i for i in range(4096) if sp_tier_vs_rank1_spread[i] >= hi_tier]
    sp['breakpoint_vs_rank1_licki'] = {
        'licki_ivs': [l_rows[0]['atk_iv'], l_rows[0]['def_iv'], l_rows[0]['sta_iv']],
        'licki_def': r4(rank1_def),
        'base_tier': base_tier, 'hi_tier': hi_tier,
        'min_thievul_atk_for_hi_tier': r4(sp_thr_hi),
        'lowest_thievul_atk_value_clearing': r2(min(
            t_atk_vals[t_atk_idx[i]] for i in clearing)) if clearing else None,
        'highest_thievul_atk_value_failing': (
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
    sp['tier_vs_rank1_licki_by_spread'] = sp_tier_vs_rank1_spread

    # full-coverage threshold: clearing the hi tier vs EVERY Lickitung means
    # clearing it vs the bulkiest one
    max_l_def = max(l_def_vals)
    # `answers.sucker_punch_tier_boundary.cohort_note` claims the bulkiest
    # opponent sits inside every cohort down to top512 -- check, don't assert
    # it in prose only.
    assert min(i for i in range(4096)
               if l_rows[i]['def_'] == max_l_def) < 512
    full_cov_atk = (hi_tier - 1) * max_l_def / (0.5 * BONUS * 8 * 1.0
                                                * STAB_MULTIPLIER)
    full_cov = [i for i in range(4096)
                if sp_ge_hi_spread['all'][i] == 4096]
    sp['full_coverage_vs_all_licki'] = {
        'bulkiest_licki_def': r4(max_l_def),
        'min_thievul_atk_for_hi_tier_vs_every_licki': r4(full_cov_atk),
        'lowest_thievul_atk_value_achieving': (
            r4(min(t_atk_vals[t_atk_idx[i]] for i in full_cov))
            if full_cov else None),
        'n_spreads': len(full_cov),
        'best_iv_rank': (min(full_cov) + 1) if full_cov else None,
    }
    sp['atk_thresholds_per_licki_def'] = per_licki_def

    # ------------------------------------------------ Lickitung offense (2)
    t_def_vals = T['def_values']
    l_atk_vals = L['atk_values']
    l_atk_idx = L['atk_index']
    t_def_idx = T['def_index']
    t_hp_vals = T['hp_values']
    t_hp_idx = T['hp_index']

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
                rec['dmg_by_licki_atk_index_x_thievul_def_index'] = mat
            per_stage[str(st)] = rec
        l_offense[mid] = {
            'stages_note': ('Thievul ICY_WIND applies buffs [-1, 0] to the '
                            'opponent, so each Icy Wind that lands drops '
                            '%s one attack stage (floor -4)' % OPPONENT),
            'by_stage': per_stage,
        }

    # ----------------------------------------------------- survival / bulk
    def ko_hits(hp, dmg):
        return math.ceil(hp / dmg) if dmg > 0 else None

    survival = {'model': ('additive, no shields, no healing: hits = '
                          'ceil(thievul_hp / per-hit damage). Real fights '
                          'mix moves and shields -- this isolates the bulk '
                          'tiers only.'),
                'refs': {}}
    for ref_name, ref_idx in (('licki_rank1', 0), ('licki_max_atk', None)):
        if ref_idx is None:
            ref_idx = max(range(4096), key=lambda i: l_rows[i]['atk'])
        lr = l_rows[ref_idx]
        ai = l_atk_idx[ref_idx]
        ref = {'licki_rank': ref_idx + 1,
               'licki_ivs': [lr['atk_iv'], lr['def_iv'], lr['sta_iv']],
               'licki_atk': r4(lr['atk']),
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
                # d >= t  iff  thievul_def <= K * licki_atk / (t - 1);
                # so "def strictly above that value" drops you to tier t-1.
                bulk = []
                for t in tiers[1:]:
                    cut = K * lr['atk'] * m / (t - 1)
                    n_at_or_above = sum(1 for i in range(4096)
                                        if dmg_by_def[t_def_idx[i]] >= t)
                    bulk.append({
                        'tier_hi': t, 'tier_lo': t - 1,
                        'max_thievul_def_still_taking_tier_hi': r4(cut),
                        'n_thievul_spreads_taking_ge_tier_hi': n_at_or_above,
                    })
                per_move[mid] = {
                    'tiers': tiers,
                    'dmg_by_thievul_def_index': dmg_by_def,
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
                    # the headline "does 15 HP buy a Body Slam?" array
                    per_move[mid]['hits_to_ko_by_thievul_spread'] = [
                        ko_hits(t_rows[i]['hp'], dmg_by_def[t_def_idx[i]])
                        for i in range(4096)]
            ref['by_stage'][str(st)] = per_move
        survival['refs'][ref_name] = ref

    # per-Thievul-spread convenience arrays vs rank-1 Lickitung, stage 0
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
    # hp still standing after (body_slams_to_ko - 1) body slams: how much of
    # the last hit is "wasted" -- small margin = fragile to a def/hp downgrade
    per_spread['hp_margin_over_prev_bs_tier'] = [
        per_spread['hp'][i]
        - (per_spread['body_slams_to_ko'][i] - 1) * per_spread['body_slam_dmg'][i]
        for i in range(4096)]
    survival['per_thievul_spread_vs_rank1_licki_stage0'] = per_spread

    # mixed kill: licks still needed after k body slams (k = 0..4), stage 0,
    # keyed [thievul_def_index][thievul_hp_index][k]
    survival['licks_after_k_body_slams_vs_rank1_licki_stage0'] = [
        [[(0 if hp - k * bs_dmg_by_def[di] <= 0
           else ko_hits(hp - k * bs_dmg_by_def[di], lk_dmg_by_def[di]))
          for k in range(5)]
         for hp in t_hp_vals]
        for di in range(len(t_def_vals))]
    survival['licks_after_k_body_slams_note'] = (
        'grid[def_index][hp_index][k] = additional %ss needed to KO after '
        'k unshielded %ss (stage 0, rank-1 %s). 0 = already '
        'dead. Additive model only.' % (lk['name'], bs['name'], OPPONENT))

    # cohort-mean body slams to KO (stage 0) by thievul (def_index, hp_index)
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
    max_l_cmp = max(e['atk'] for e in l_rows)
    min_t_cmp = min(e['atk'] for e in t_rows)
    argmax_l = max(range(4096), key=lambda i: l_rows[i]['atk'])
    argmin_t = min(range(4096), key=lambda i: t_rows[i]['atk'])
    cmp_block = {
        'definition': ('BattlePokemon.cmp_atk == atk (neither side is shadow, '
                       'so no x1.2 strip applies); higher cmp_atk resolves '
                       'simultaneous charged moves first',),
        'max_lickitung_cmp_atk': r4(max_l_cmp),
        'max_lickitung_spread': [l_rows[argmax_l]['atk_iv'],
                                 l_rows[argmax_l]['def_iv'],
                                 l_rows[argmax_l]['sta_iv']],
        'max_lickitung_rank': argmax_l + 1,
        'min_thievul_cmp_atk': r4(min_t_cmp),
        'min_thievul_spread': [t_rows[argmin_t]['atk_iv'],
                               t_rows[argmin_t]['def_iv'],
                               t_rows[argmin_t]['sta_iv']],
        'min_thievul_rank': argmin_t + 1,
        'margin': r4(min_t_cmp - max_l_cmp),
        'thievul_always_wins_cmp': bool(min_t_cmp > max_l_cmp),
        'verdict': (('CONFIRMED: every Thievul spread out-CMPs every '
                     '%s spread' % OPPONENT) if min_t_cmp > max_l_cmp else
                    ('REFUTED: some %s spreads out-CMP some Thievul '
                     'spreads' % OPPONENT)),
    }
    cmp_block['definition'] = cmp_block['definition'][0]

    # ------------------------------------------------------ 4. claim checks
    bs_ko_by_stage = {
        st: survival['refs']['licki_rank1']['by_stage'][st][L_CH1][
            'hits_to_ko_by_thievul_spread'] for st in map(str, STAGES)}
    lick_dmg_by_stage = {
        st: survival['refs']['licki_rank1']['by_stage'][st][L_FAST][
            'dmg_by_thievul_def_index'] for st in map(str, STAGES)}

    def spread_card(a, d, s, label=None):
        i = iv_to_rank_t[(a, d, s)]
        e = t_rows[i]
        return {
            'label': label, 'ivs': [a, d, s], 'rank': i + 1,
            'level': e['level'], 'cp': e['cp'],
            'atk': r4(e['atk']), 'def': r4(e['def_']), 'hp': e['hp'],
            'sp_dmg_vs_rank1_licki': sp_tier_vs_rank1_spread[i],
            'sp_ge_hi_count': {ck: sp_ge_hi_spread[ck][i] for ck in COHORTS},
            'sp_ge_hi_frac': {ck: r4(sp_ge_hi_spread[ck][i] / COHORTS[ck])
                              for ck in COHORTS},
            'body_slam_dmg_from_rank1_licki': per_spread['body_slam_dmg'][i],
            'body_slams_to_ko': per_spread['body_slams_to_ko'][i],
            'hp_margin_over_prev_bs_tier': per_spread['hp_margin_over_prev_bs_tier'][i],
            'power_whips_to_ko': per_spread['power_whips_to_ko'][i],
            'lick_dmg_from_rank1_licki': per_spread['lick_dmg'][i],
            'body_slams_to_ko_by_licki_atk_stage': {
                st: bs_ko_by_stage[st][i] for st in map(str, STAGES)},
            'lick_dmg_by_licki_atk_stage': {
                st: lick_dmg_by_stage[st][t_def_idx[i]] for st in map(str, STAGES)},
        }

    max_all = max(sp_ge_hi_spread['all'])
    max_512 = max(sp_ge_hi_spread['top512'])
    best_all = [i for i in range(4096) if sp_ge_hi_spread['all'][i] == max_all]
    best_512 = [i for i in range(4096) if sp_ge_hi_spread['top512'][i] == max_512]
    i_615 = iv_to_rank_t[(6, 15, 5)]

    claim_a = {
        'claim': ('"6/15/5 is the best possible spread for the Sucker Punch '
                  'bp on Licki" (community discussion around the CD)'),
        'spread': spread_card(6, 15, 5, '6/15/5'),
        'clears_bp_vs_rank1_licki': sp_tier_vs_rank1_spread[i_615] >= hi_tier,
        'max_ge_hi_count': {'all': max_all, 'top512': max_512},
        'max_ge_hi_frac': {'all': r4(max_all / 4096), 'top512': r4(max_512 / 512)},
        'n_spreads_at_max_coverage': {'all': len(best_all), 'top512': len(best_512)},
        'is_615_at_max_coverage': {'all': i_615 in best_all,
                                   'top512': i_615 in best_512},
        'n_spreads_strictly_better_than_615': {
            ck: sum(1 for i in range(4096)
                    if sp_ge_hi_spread[ck][i] > sp_ge_hi_spread[ck][i_615])
            for ck in COHORTS},
        'coverage_rank_of_615': {
            ck: 1 + sum(1 for i in range(4096)
                        if sp_ge_hi_spread[ck][i] > sp_ge_hi_spread[ck][i_615])
            for ck in COHORTS},
        # OTHER spreads at the same coverage (excludes 6/15/5 itself --
        # the self-inclusive count rendered as "tied with" reads wrong).
        'n_spreads_tied_with_615': {
            ck: sum(1 for i in range(4096)
                    if sp_ge_hi_spread[ck][i] == sp_ge_hi_spread[ck][i_615])
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
            'best-rank spread clearing the bp vs rank-1 Licki'),
        'verdict_metric': ('"best for the SP bp" read as: number of the 4096 '
                           '%s spreads on which Sucker Punch reaches '
                           'the hi tier (%d). Both a stricter reading '
                           '("clears the bp vs the rank-1 Licki") and the '
                           'coverage reading are reported.'
                           % (OPPONENT, hi_tier)),
    }

    sta15 = [i for i in range(4096) if t_rows[i]['sta_iv'] == 15]
    sta15_clearing = [i for i in sta15 if sp_tier_vs_rank1_spread[i] >= hi_tier]
    claim_b = {
        'claim': ('"do you not want 15 hp" (community discussion) -- i.e. '
                  'prefer sta_iv 15 over the low-sta stat-product-optimal '
                  'spreads'),
        'n_sta15_spreads': len(sta15),
        'n_sta15_clearing_sp_bp_vs_rank1': len(sta15_clearing),
        'best_rank_sta15': min(sta15) + 1,
        'best_rank_sta15_clearing_bp': (min(sta15_clearing) + 1
                                        if sta15_clearing else None),
        'max_sp_coverage_among_sta15': {
            ck: max(sp_ge_hi_spread[ck][i] for i in sta15) for ck in COHORTS},
        'best_sta15_by_iv_rank': [
            spread_card(t_rows[i]['atk_iv'], t_rows[i]['def_iv'],
                        t_rows[i]['sta_iv'])
            for i in sorted(sta15)[:8]],
        'best_sta15_clearing_bp_by_iv_rank': [
            spread_card(t_rows[i]['atk_iv'], t_rows[i]['def_iv'],
                        t_rows[i]['sta_iv'])
            for i in sorted(sta15_clearing)[:8]],
        'direct_comparison_6_15_5_vs_6_15_15': {
            '6/15/5': spread_card(6, 15, 5, '6/15/5'),
            '6/15/15': spread_card(6, 15, 15, '6/15/15'),
        },
        'sta15_max_coverage_spread': spread_card(
            *max(((t_rows[i]['atk_iv'], t_rows[i]['def_iv'], t_rows[i]['sta_iv'])
                  for i in sta15),
                 key=lambda k: sp_ge_hi_spread['all'][iv_to_rank_t[k]]),
            label='best sta15 by SP coverage'),
    }

    named = {}
    for a, d, s, lab in [(6, 15, 5, '6/15/5'),
                         (6, 15, 15, '6/15/15 (15 hp variant)'),
                         (0, 15, 11, 'rank-1 stat product'),
                         (0, 15, 15, '0/15/15'),
                         (15, 15, 15, 'hundo'),
                         # "max atk IV", not "max atk": effective attack
                         # depends on the CP-capped level too, and 15/15/0
                         # is NOT the highest-attack spread in the 4096.
                         (15, 15, 0, 'max atk IV, min sta IV'),
                         (10, 15, 15, '10/15/15')]:
        named[f'{a}/{d}/{s}'] = spread_card(a, d, s, lab)
    # exemplar of the max-coverage set with the highest HP (bulk-friendly)
    best_hp_i = max(best_all, key=lambda i: (t_rows[i]['hp'], -i))
    named['max_coverage_max_hp'] = spread_card(
        t_rows[best_hp_i]['atk_iv'], t_rows[best_hp_i]['def_iv'],
        t_rows[best_hp_i]['sta_iv'], 'max SP coverage, highest HP within set')

    # ------------------------------------------- computed answer summary
    sp_pair_totals = {str(t): 0 for t in sp_tiers}
    for i in range(4096):
        row = sp_mat[t_atk_idx[i]]
        for o in range(4096):
            sp_pair_totals[str(row[l_def_idx[o]])] += 1
    i_61515 = iv_to_rank_t[(6, 15, 15)]
    sta15_full_cov = [i for i in sta15 if sp_ge_hi_spread['all'][i] == 4096]
    answers = {
        'note': ('every number here is computed by this script from the '
                 'arrays above; nothing is asserted without a source array'),
        'sucker_punch_tier_boundary': {
            'tiers': sp_tiers,
            'K': K_sp,
            'identity': 'dmg = floor(K * thievul_atk / licki_def) + 1',
            'hi_tier': hi_tier,
            'vs_rank1_licki': {
                'licki_def': r4(rank1_def),
                'thievul_atk_needed': r4(sp_thr_hi),
                'highest_atk_value_below': r4(max(
                    t_atk_vals[t_atk_idx[i]] for i in range(4096)
                    if sp_tier_vs_rank1_spread[i] < hi_tier)),
                'lowest_atk_value_at_or_above': r4(min(
                    t_atk_vals[t_atk_idx[i]] for i in clearing)),
                'n_spreads_clearing': len(clearing),
                'n_spreads_failing': 4096 - len(clearing),
            },
            'vs_every_licki': sp['full_coverage_vs_all_licki'],
            'pair_tier_totals_over_4096x4096': sp_pair_totals,
            'pair_tier_note': ('tier 8 needs thievul_atk / licki_def >= '
                               '%s, which only the very top-attack Thievul '
                               'spreads reach against the frailest %s '
                               '-- it is a rounding curiosity, not a target. '
                               'The bp everyone means is 6 -> 7.'
                               % (r4(7 / K_sp), OPPONENT)),
            'licki_def_range_by_cohort': {
                ck: {'min': r4(min(l_def_vals[l_def_idx[o]] for o in range(n))),
                     'max': r4(max(l_def_vals[l_def_idx[o]] for o in range(n)))}
                for ck, n in COHORTS.items()},
            'cohort_note': ('the bulkiest %s (def %s) is present in '
                            'every cohort down to top512, so the full-'
                            'coverage set is identical for all and top512'
                            % (OPPONENT, r4(max(l_def_vals)))),
        },
        'cmp': {'verdict': cmp_block['verdict'],
                'min_thievul_cmp_atk': cmp_block['min_thievul_cmp_atk'],
                'max_lickitung_cmp_atk': cmp_block['max_lickitung_cmp_atk'],
                'margin': cmp_block['margin']},
        'claim_a_615': {
            'clears_bp_vs_rank1_licki': bool(sp_tier_vs_rank1_spread[i_615] >= hi_tier),
            'coverage_all': sp_ge_hi_spread['all'][i_615],
            'coverage_all_frac': r4(sp_ge_hi_spread['all'][i_615] / 4096),
            'coverage_top512': sp_ge_hi_spread['top512'][i_615],
            'coverage_top512_frac': r4(sp_ge_hi_spread['top512'][i_615] / 512),
            'coverage_top100': sp_ge_hi_spread['top100'][i_615],
            'max_coverage_all': max_all,
            'n_spreads_strictly_better_all': claim_a['n_spreads_strictly_better_than_615']['all'],
            'n_spreads_at_max_coverage': len(best_all),
            'is_best': False if claim_a['n_spreads_strictly_better_than_615']['all'] else True,
            'best_iv_rank_at_max_coverage': min(best_all) + 1,
            'best_iv_rank_clearing_bp_vs_rank1': min(clearing) + 1,
            'iv_rank_of_615': i_615 + 1,
        },
        'claim_b_15hp': {
            'body_slams_to_ko_is_constant_at_stage0': (
                len(set(per_spread['body_slams_to_ko'])) == 1),
            'body_slams_to_ko_stage0_value': per_spread['body_slams_to_ko'][0],
            'body_slams_to_ko_histogram_by_stage': {
                st: survival['refs']['licki_rank1']['by_stage'][st][
                    L_CH1]['hits_to_ko_histogram'] for st in map(str, STAGES)},
            'power_whips_to_ko_stage0_histogram': {
                str(k): sum(1 for v in per_spread['power_whips_to_ko'] if v == k)
                for k in sorted(set(per_spread['power_whips_to_ko']))},
            'lick_bulkpoint_vs_rank1_licki': survival['refs']['licki_rank1'][
                'by_stage']['0'][L_FAST]['bulkpoints'],
            'n_spreads_taking_1_lick_vs_rank1': sum(
                1 for v in per_spread['lick_dmg'] if v == 1),
            'n_spreads_taking_2_lick_vs_rank1': sum(
                1 for v in per_spread['lick_dmg'] if v == 2),
            '615_vs_61515': {
                'sp_dmg_vs_rank1': [sp_tier_vs_rank1_spread[i_615],
                                    sp_tier_vs_rank1_spread[i_61515]],
                'coverage_all': [sp_ge_hi_spread['all'][i_615],
                                 sp_ge_hi_spread['all'][i_61515]],
                'coverage_all_delta': (sp_ge_hi_spread['all'][i_61515]
                                       - sp_ge_hi_spread['all'][i_615]),
                'coverage_top512': [sp_ge_hi_spread['top512'][i_615],
                                    sp_ge_hi_spread['top512'][i_61515]],
                'coverage_top512_delta': (sp_ge_hi_spread['top512'][i_61515]
                                          - sp_ge_hi_spread['top512'][i_615]),
                'hp': [t_rows[i_615]['hp'], t_rows[i_61515]['hp']],
                'body_slams_to_ko_by_stage': {
                    st: [bs_ko_by_stage[st][i_615], bs_ko_by_stage[st][i_61515]]
                    for st in map(str, STAGES)},
                'lick_dmg_vs_rank1': [per_spread['lick_dmg'][i_615],
                                      per_spread['lick_dmg'][i_61515]],
                'order': ['6/15/5', '6/15/15'],
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
                            'best-rank sta15 at full SP coverage')
                if sta15_full_cov else None),
        },
    }
    # The two legacy `n_spreads_taking_{1,2}_lick_vs_rank1` counters hardcode
    # damage values 1 and 2, which are the only two Lick can do into Thievul.
    # A different fast move lands on different tiers and would leave both
    # counters reading 0 -- a true but silently useless pair. Ship the real
    # histogram whenever the legacy pair does not account for all 4096
    # spreads (it does for Lickitung, so that file is unchanged).
    _cb = answers['claim_b_15hp']
    if (_cb['n_spreads_taking_1_lick_vs_rank1']
            + _cb['n_spreads_taking_2_lick_vs_rank1']) != 4096:
        _cb['fast_move_dmg_histogram_vs_rank1'] = {
            str(k): sum(1 for v in per_spread['lick_dmg'] if v == k)
            for k in sorted(set(per_spread['lick_dmg']))}
        _cb['fast_move_dmg_histogram_note'] = (
            '%s damage taken from the rank-1 %s at stage 0, over all 4096 '
            'Thievul spreads. The n_spreads_taking_1/2_lick_vs_rank1 keys '
            'above are hardcoded to damage 1 and 2 (the only values Lick '
            'reaches) and read 0 here -- use this histogram instead.'
            % (lk['name'], OPPONENT))

    # ------------------------------------------------------- VERIFICATION
    ver = {'formula_samples': [], 'sim_checks': []}

    def independent(power, atk, def_, mtype, atypes, dtypes):
        """Formula re-implemented here from the spec in CLAUDE.md, so the
        check is not just moves.damage compared to itself."""
        eff = 1.0
        for t in dtypes:
            eff *= {('dark', 'normal'): 1.0, ('ice', 'normal'): 1.0,
                    ('fairy', 'normal'): 1.0, ('normal', 'dark'): 1.0,
                    ('grass', 'dark'): 1.0, ('ghost', 'dark'): 0.625,
                    ('rock', 'dark'): 1.0}[(mtype, t)]
        st = STAB_MULTIPLIER if mtype in atypes else 1.0
        return math.floor(0.5 * BONUS * power * atk / def_ * eff * st) + 1

    samples = [
        ('SUCKER_PUNCH', 'fast', t_types, l_types, t_rows[0]['atk'], l_rows[0]['def_'], 1.0),
        ('SUCKER_PUNCH', 'fast', t_types, l_types, t_rows[i_615]['atk'], l_rows[0]['def_'], 1.0),
        ('SUCKER_PUNCH', 'fast', t_types, l_types, max(t_atk_vals), min(l_def_vals), 1.0),
        ('ICY_WIND', 'charged', t_types, l_types, t_rows[i_615]['atk'], l_rows[0]['def_'], 1.0),
        ('PLAY_ROUGH', 'charged', t_types, l_types, t_rows[i_615]['atk'], l_rows[0]['def_'], 1.0),
        ('NIGHT_SLASH', 'charged', t_types, l_types, t_rows[0]['atk'], l_rows[100]['def_'], 1.0),
        (L_FAST, 'fast', l_types, t_types, l_rows[0]['atk'], t_rows[i_615]['def_'], 1.0),
        (L_CH1, 'charged', l_types, t_types, l_rows[0]['atk'], t_rows[i_615]['def_'], 1.0),
        (L_CH1, 'charged', l_types, t_types, l_rows[0]['atk'], t_rows[0]['def_'],
         _stat_stage_mult(-1)),
        (L_CH1, 'charged', l_types, t_types, l_rows[0]['atk'], t_rows[0]['def_'],
         _stat_stage_mult(-2)),
        (L_CH2, 'charged', l_types, t_types, l_rows[0]['atk'], t_rows[0]['def_'],
         _stat_stage_mult(-4)),
    ]
    # Any opponent CHARGED move that is not neutral vs Thievul gets its own
    # unstaged sample. (For Lickitung the only resisted move is the FAST one,
    # Lick/ghost, which sample 7 already covers -- so this adds nothing there
    # and the Lickitung output is unchanged.)
    resisted_charged = [m for m, k in L_MOVES if k == 'charged'
                        and type_effectiveness(move(m, k)['type'], t_types) != 1.0]
    samples += [(m, 'charged', l_types, t_types, l_rows[0]['atk'],
                 t_rows[i_615]['def_'], 1.0) for m in resisted_charged]
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

    def sim_check(t_ivs, l_ivs, t_charged, shields):
        tp = make_battle_pokemon(FOCAL, 'SUCKER_PUNCH', t_charged, LEAGUE,
                                 shields, *t_ivs)
        lp = make_battle_pokemon(OPPONENT, L_FAST, [L_CH1, L_CH2],
                                 LEAGUE, shields, *l_ivs)
        t_atk_engine, t_def_engine, t_hp_engine = tp.atk, tp.def_, tp.hp
        l_atk_engine = lp.atk
        res = simulate(tp, lp, log=True)   # mutates tp/lp (hp, energy, stages)
        seen = {}
        for line in res.timeline:
            if 'Thievul fast' in line and 'sp' not in seen:
                # NB: the arrow is a genuine U+2192 -- battle.py's timeline
                # emits "{species} uses {move} → {dmg} dmg" (see
                # log_event calls around battle.py:2775-2791), so this is
                # the engine's real token, not a stray unicode glyph.
                seen['sp'] = int(line.split('→')[1].split('dmg')[0])
            if OPPONENT + ' fast' in line and 'lick' not in seen:
                seen['lick'] = int(line.split('→')[1].split('dmg')[0])
        # closed-form predictions at stage 0 (first hits, before any Icy Wind)
        ti = iv_to_rank_t[tuple(t_ivs)]
        li = [j for j in range(4096)
              if (l_rows[j]['atk_iv'], l_rows[j]['def_iv'],
                  l_rows[j]['sta_iv']) == tuple(l_ivs)][0]
        pred_sp = sp_mat[t_atk_idx[ti]][l_def_idx[li]]
        pred_lick = damage(lk['power'], l_rows[li]['atk'], t_rows[ti]['def_'],
                           lk['type'], l_types, t_types)
        return {
            'thievul_ivs': list(t_ivs), 'lickitung_ivs': list(l_ivs),
            'thievul_charged': t_charged, 'shields': shields,
            'engine_thievul_atk': r4(t_atk_engine),
            'closed_form_thievul_atk': r4(t_rows[ti]['atk']),
            'engine_thievul_def': r4(t_def_engine), 'engine_thievul_hp': t_hp_engine,
            'closed_form_thievul_hp': t_rows[ti]['hp'],
            'engine_licki_atk': r4(l_atk_engine),
            'closed_form_licki_atk': r4(l_rows[li]['atk']),
            'sim_sucker_punch_dmg': seen.get('sp'), 'closed_form_sucker_punch_dmg': pred_sp,
            'sim_lick_dmg': seen.get('lick'), 'closed_form_lick_dmg': pred_lick,
            'match': (seen.get('sp') == pred_sp and seen.get('lick') == pred_lick
                      and t_hp_engine == t_rows[ti]['hp']
                      and abs(t_atk_engine - t_rows[ti]['atk']) < 1e-9
                      and abs(t_def_engine - t_rows[ti]['def_']) < 1e-9
                      and abs(l_atk_engine - l_rows[li]['atk']) < 1e-9),
        }

    ver['sim_checks'].append(sim_check((6, 15, 5), (8, 14, 15),
                                       ['ICY_WIND', 'PLAY_ROUGH'], 1))
    ver['sim_checks'].append(sim_check((0, 15, 11), (8, 14, 15),
                                       ['NIGHT_SLASH', 'ICY_WIND'], 0))
    ver['sim_checks'].append(sim_check((15, 15, 0), (15, 15, 15),
                                       ['ICY_WIND', 'PLAY_ROUGH'], 2))
    assert all(c['match'] for c in ver['sim_checks'])

    # ---- engine cross-check: Icy Wind debuff -> Body Slam damage drop
    tp = make_battle_pokemon(FOCAL, 'SUCKER_PUNCH', ['ICY_WIND', 'PLAY_ROUGH'],
                             LEAGUE, 0, 6, 15, 5)
    lp = make_battle_pokemon(OPPONENT, L_FAST, [L_CH1, L_CH2],
                             LEAGUE, 0, 8, 14, 15)
    res = simulate(tp, lp, log=True)
    bs_hits = [int(l.split('→')[1].split('dmg')[0])
               for l in res.timeline if bs['name'] + ' →' in l]
    iw_count = sum(1 for l in res.timeline if 'uses Icy Wind' in l)
    ti = iv_to_rank_t[(6, 15, 5)]
    pred_by_stage = {st: damage(bs['power'], l_rows[0]['atk'] * _stat_stage_mult(st),
                                t_rows[ti]['def_'], bs['type'], l_types, t_types)
                     for st in STAGES}
    ver['icy_wind_stage_check'] = {
        'thievul_ivs': [6, 15, 5], 'lickitung_ivs': [8, 14, 15], 'shields': 0,
        'icy_winds_thrown': iw_count,
        'sim_body_slam_damages_in_order': bs_hits,
        'closed_form_body_slam_by_stage': {str(k): v for k, v in pred_by_stage.items()},
        'note': ('each observed Body Slam damage must equal the closed-form '
                 'value at some attack stage 0..-4'),
        'all_observed_in_closed_form_set': all(
            v in set(pred_by_stage.values()) for v in bs_hits),
    }
    assert bs_hits, 'no charged-slot-1 hit landed; the stage check would pass vacuously'
    assert any(v != pred_by_stage[0] for v in bs_hits), (
        'every observed hit is the stage-0 value, so the Icy Wind debuff '
        'itself is untested')
    assert ver['icy_wind_stage_check']['all_observed_in_closed_form_set']

    # ---- engine cross-check: resisted opponent CHARGED moves.
    # The fast-move comparison in sim_check() already pins a resisted move for
    # Lickitung (Lick is ghost), but Lickilicky's resisted move (Shadow Ball,
    # ghost, x0.625 into dark) is CHARGED and never appears there. This block
    # is empty -- and therefore absent from the JSON -- whenever every opponent
    # charged move is neutral, which is exactly the Lickitung case.
    if resisted_charged:
        checks = []
        for mid in resisted_charged:
            mv = move(mid, 'charged')
            t_ivs, l_ivs, shields = (6, 15, 5), (0, 15, 10), 0
            hits, probe_set, thrown_by_default = None, None, None
            # First ask whether the DEFAULT moveset ever throws it; if the
            # engine prefers the other charged move every time, fall back to a
            # single-charged-move build so the damage still gets pinned
            # against a real timeline (and record that it took a forced build).
            for cand in ([L_CH1, L_CH2], [mid]):
                tp = make_battle_pokemon(FOCAL, 'SUCKER_PUNCH',
                                         ['ICY_WIND', 'PLAY_ROUGH'], LEAGUE,
                                         shields, *t_ivs)
                lp = make_battle_pokemon(OPPONENT, L_FAST, cand,
                                         LEAGUE, shields, *l_ivs)
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
            used = {'thievul_ivs': list(t_ivs), 'opponent_ivs': list(l_ivs),
                    'shields': shields, 'probe_opponent_charged': probe_set,
                    'thrown_with_default_moveset': thrown_by_default}
            assert hits, ('%s never landed in any probe matchup; the check '
                          'would pass vacuously' % mid)
            pred = {st: damage(mv['power'],
                               l_rows[li]['atk'] * _stat_stage_mult(st),
                               t_rows[ti]['def_'], mv['type'], l_types, t_types)
                    for st in STAGES}
            neutral = {st: damage(mv['power'],
                                  l_rows[li]['atk'] * _stat_stage_mult(st),
                                  t_rows[ti]['def_'], 'normal', l_types,
                                  t_types) for st in STAGES}
            checks.append(dict(
                used, move=mid, move_type=mv['type'],
                effectiveness_vs_thievul=r4(type_effectiveness(mv['type'],
                                                               t_types)),
                sim_damages_in_order=hits,
                closed_form_by_stage={str(k): v for k, v in pred.items()},
                same_power_neutral_by_stage={str(k): v
                                             for k, v in neutral.items()},
                resistance_is_visible=all(pred[st] < neutral[st]
                                          for st in STAGES),
                all_observed_in_closed_form_set=all(
                    v in set(pred.values()) for v in hits)))
        ver['resisted_charged_sim_checks'] = checks
        ver['resisted_charged_note'] = (
            'each observed damage must equal the closed-form value at some '
            'opponent attack stage 0..-4, and the resisted value must be '
            'strictly below what the same-power NEUTRAL move would do '
            '(otherwise the type resistance would be untested). '
            'thrown_with_default_moveset=false means the engine never chose '
            'the move with the default charged pair, so the probe forced it '
            'by giving the opponent that move alone -- the damage numbers '
            'are still real engine output, but in the default matchup the '
            'move simply never fires.')
        assert all(c['all_observed_in_closed_form_set']
                   and c['resistance_is_visible'] for c in checks)

    # ---------------------------------------------------------------- emit
    out = {
        'meta': meta,
        'moves': moves_meta,
        'spread_index': {
            'thievul': {k: T[k] for k in ('atk_values', 'atk_index',
                                          'def_values', 'def_index',
                                          'hp_values', 'hp_index')},
            'lickitung': {k: L[k] for k in ('atk_values', 'atk_index',
                                            'def_values', 'def_index',
                                            'hp_values', 'hp_index')},
            'note': ('*_values are the sorted distinct stat values; '
                     '*_index[r] is the value index for iv_rank row r '
                     '(rank r+1). Every tier table is keyed by value index.'),
        },
        'thievul_offense': {'defender': OPPONENT, 'moves': offense},
        'lickitung_offense': {'defender': FOCAL, 'moves': l_offense},
        'survival': survival,
        'cmp': cmp_block,
        'claims': {'a_615_best_for_sp_bp': claim_a, 'b_15_hp': claim_b},
        'answers': answers,
        'named_spreads': named,
        'verification': ver,
    }
    # round stat value lists for compactness (2dp is well inside the
    # nearest tier boundary; tier tables were computed at full precision)
    for sp_key in ('thievul', 'lickitung'):
        for vk in ('atk_values', 'def_values'):
            out['spread_index'][sp_key][vk] = [
                r4(v) for v in out['spread_index'][sp_key][vk]]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(out, separators=(',', ':')))
    os.replace(tmp, OUT)
    size = OUT.stat().st_size
    print(f'wrote {OUT} ({size:,} bytes)')
    print(f'SP tiers {sp_tiers}; hi tier {hi_tier} needs thievul atk >= '
          f'{sp_thr_hi:.4f} vs rank-1 Licki (def {rank1_def:.4f}); '
          f'{len(clearing)}/4096 spreads clear')
    print('CMP:', cmp_block['verdict'],
          f"(min Thievul {cmp_block['min_thievul_cmp_atk']} vs "
          f"max Licki {cmp_block['max_lickitung_cmp_atk']})")
    print('6/15/5:', json.dumps(claim_a['spread'], indent=None))
    print('max coverage all/top512:', max_all, max_512,
          '| 6/15/5 at max?', claim_a['is_615_at_max_coverage'])


if __name__ == '__main__':
    main()
