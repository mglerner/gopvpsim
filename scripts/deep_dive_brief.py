#!/usr/bin/env python
"""Build brief: an auto-derived IV recommendation computed from a replay blob.

Implements the compute core and a standalone HTML renderer for the design in
``docs/expert_verdict_plan.md`` (sections 2-4): a per-moveset-arm block whose
every claim is a CLEAN CUT -- a stat value T for one (shield scenario,
opponent) cell where every spread with ``stat >= T`` wins and no spread below
it does -- carried by a closed-form mechanism label where one exists.

Vocabulary (defined once here, per the docs style rule):

- CMP (Charge Move Priority): when both sides throw a charged move on the same
  turn the higher attack stat goes first. Our engine and PvPoke compare the
  shadow-STRIPPED attack (``src/gopvpsim/battle.py`` ``cmp_atk``), so for a
  shadow focal the CMP line sits at ``SHADOW_ATK_BONUS x opponent cmp_atk``.
- Clean cut: see above. Win is ``gopvpsim.battle.is_win`` (score > 500).
- Rung: a clean cut on the attack axis, named by the cell(s) it owns.
- Co-gate: a second-stat condition (Def >= d or HP >= h) that, INSIDE the
  spreads clearing a rung, wins one named cell 100% of the time.
- Alternative target: a (Def, HP) rectangle containing no spread that clears
  the floor, printed with the cells it guarantees that the floor cannot.
- Mode: one of the four baked opponent-IV x bait settings.
- SP: stat product.

Nothing here simulates. The only live reads are the gamemaster (opponent
stats, for the CMP line and breakpoint labels) and the rankings (opponent
ranks); both are stamped in the provenance field (guard G-purity).

CLI::

    deep_dive_brief.py BLOB [--out DIR] [--arms all|0]
    deep_dive_brief.py --sweep BLOB [BLOB ...] [--out DIR]
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import math
import os
import pickle
import re
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gopvpsim.battle import is_win, WIN_RATING, SHADOW_ATK_BONUS, _stat_stage_mult
from gopvpsim.moves import damage, get_moves, parse_types
from gopvpsim.pokemon import Pokemon, find_pokemon_entry
from deep_dive_lib.opponents import (
    resolve_opp_ivs, parse_opponent_spec, build_opp_meta_ranks,
    rankings_snapshot_date,
)

# ---------------------------------------------------------------------------
# Selection constants. Every one is a parameter of the stage that uses it and
# is printed in the evidence block; the plan's Phase 0 sweep is what sets them
# corpus-wide (today they are calibrated on one species -- said out loud in
# the evidence block).
# ---------------------------------------------------------------------------

DECISION_BAND = (0.25, 0.60)      # D1: floor pool share must sit inside this
SENSITIVITY_BANDS = ((0.25, 0.60), (0.25, 0.55), (0.25, 0.50),
                     (0.20, 0.60), (0.30, 0.60), (0.25, 0.70))
MATERIAL_LO = 0.10                # G-material-lo: a rung is a build decision
MATERIAL_HI = 0.90                # G-material-hi
MIN_ATTAINED_BELOW = 20           # G-material-gap
RANK_GATE = 50                    # G-rank / D3
DIRECTION_MIN_ABOVE = 0.90        # G-direction
MODES_TO_LIST = 2                 # a rung needs this many passing modes to list
RUNG_POOL_MIN = 0.25              # "rungs above" keeps this share of the grid
COGATE_MIN_SHARE = 0.05           # stage 9 sub-rectangle floor
COGATE_MAX_BASE_RATE = 0.90       # a co-gate must buy something
ALT_MIN_MEMBERS = 100             # stage 9b
ALT_MAX_CLEARER_RATE = 0.01       # "won by at most 1% of floor clearers"
SCORE_STEP_MIN = 60               # stage 10
DEGENERATE_SHARP = 6              # G-scenario
DEGENERATE_PATTERNS = 8           # G-scenario
NAME_CAP = 3                      # G-names
LIST_CAP = 12                     # names printed in a field-8 list
SCORE_ROW_CAP = 12                # stage 10 table length
COGATE_ROW_CAP = 2                # co-gate rows printed per rung
SP_FLOOR = 0.95                   # stage 8 example rules
CATCH_TARGETS = (0.50, 0.75)      # D7

# G-caveat. Phase 0 item 3 of the plan moves this to scripts/mechanics_notice.py
# as CAVEAT_SPECIES; it is defined here so v1 is self-contained.
CAVEAT_SPECIES = ('Aegislash',)

SHIELD_LABELS = None  # filled per blob from state['shield_scenarios']

BANNED_WORDS = (
    'recommend', 'recommended', 'best', 'strong', 'solid', 'definitive',
    'reliable', 'consistent', 'worth', 'great', 'good', 'bad', 'should',
)
BANNED_EXEMPT_PHRASES = ('Great League', 'Ultra League', 'Master League')
SHOULD_ALLOWED_PHRASE = 'most builds should clear'


class GuardError(RuntimeError):
    """A build-breaking guard failed. Message format is fixed by the plan."""


def guard_fail(guard, field, cell, printed, recomputed, ctx):
    raise GuardError(
        f"{guard}: field={field} cell={cell} printed='{printed}' "
        f"recomputed={recomputed} (blob={ctx.get('blob')} arm={ctx.get('arm')} "
        f"mode={ctx.get('mode')})"
    )


# ---------------------------------------------------------------------------
# Blob access
# ---------------------------------------------------------------------------

def load_blob(path):
    """Read a deep-dive replay blob (gzip + pickle) into its state dict."""
    with gzip.open(path, 'rb') as fh:
        return pickle.load(fh)


def arm_view(state, arm, mode, level='l50'):
    """Return (scores, meta) for one arm x mode x level view.

    ``scores`` is (4096, 9, nO) int32; ``meta`` is the per-IV tuple array
    (aiv, div, hiv, level, cp, atk, def, hp) with atk/def already
    shadow-effective. ``level`` is 'l50' or 'l51' (D8: one view per call).
    """
    n_opp = len(state['opponent_names'])
    n_sc = len(state['shield_scenarios'])
    data = state['moveset_data'][arm]
    skey = 'scores' if level == 'l50' else 'scores_l51'
    mkey = 'meta' if level == 'l50' else 'meta_l51'
    flat = data[skey][mode] if level == 'l50' else data[skey][mode]
    scores = np.asarray(flat, dtype=np.int32).reshape(-1, n_sc, n_opp)
    meta = np.asarray(data[mkey], dtype=float)
    return scores, meta


def stat_planes(meta):
    """(atk, def, hp) float arrays from the per-IV meta table."""
    return meta[:, 5].copy(), meta[:, 6].copy(), meta[:, 7].copy()


def win_cube(scores):
    """Boolean win cube for a score array.

    ``gopvpsim.battle.is_win`` is the win predicate contract; the vectorized
    comparison below is it, spelled once against the same constant. The
    assertion is the identity check, so a change to ``is_win`` breaks here
    rather than silently re-defining "win" for the whole brief.
    """
    assert is_win(WIN_RATING + 1) and not is_win(WIN_RATING)
    return scores > WIN_RATING


def scenario_label(state, si):
    a, b = state['shield_scenarios'][si]
    return f"{a}v{b}"


def cell_label(state, si, oi):
    return f"{scenario_label(state, si)} {state['opponent_names'][oi]}"


# ---------------------------------------------------------------------------
# Stage 1 -- triage, dedup, degenerate scenarios
# ---------------------------------------------------------------------------

def stage1_triage(win):
    """Per-cell all-win / all-lose / contested, dedup groups, degenerate rows.

    ``win`` is (n_iv, n_sc, n_opp) bool. Dedup is per scenario over
    byte-identical opponent columns (G-dedup); the group representative is the
    lowest opponent index.
    """
    n_iv, n_sc, n_opp = win.shape
    nwin = win.sum(axis=0)
    all_win = nwin == n_iv
    all_lose = nwin == 0
    contested = ~all_win & ~all_lose

    dedup_of = {}
    dedup_members = {}
    degenerate = {}
    for si in range(n_sc):
        seen = {}
        for oi in range(n_opp):
            key = win[:, si, oi].tobytes()
            rep = seen.setdefault(key, oi)
            dedup_of[(si, oi)] = (si, rep)
            dedup_members.setdefault((si, rep), []).append(oi)
        n_sharp = int(contested[si].sum())
        n_patterns = len(seen)
        degenerate[si] = (n_sharp < DEGENERATE_SHARP
                          or n_patterns < DEGENERATE_PATTERNS)
    return {
        'n_iv': n_iv, 'n_sc': n_sc, 'n_opp': n_opp,
        'n_all_win': int(all_win.sum()),
        'n_all_lose': int(all_lose.sum()),
        'n_contested': int(contested.sum()),
        'contested_mask': contested,
        'all_win_mask': all_win,
        'all_lose_mask': all_lose,
        'nwin': nwin,
        'dedup_of': dedup_of,
        'dedup_members': dedup_members,
        'degenerate': degenerate,
        'n_patterns': {si: len({win[:, si, oi].tobytes() for oi in range(n_opp)})
                       for si in range(n_sc)},
    }


# ---------------------------------------------------------------------------
# Stage 2 -- clean cuts
# ---------------------------------------------------------------------------

def clean_cut(stat, wins):
    """Least T with (stat >= T) == wins elementwise, or None.

    Returns (T, n_pass, prev_attained, n_attained_below).
    """
    if not wins.any() or wins.all():
        return None
    T = float(stat[wins].min())
    if not np.array_equal(stat >= T, wins):
        return None
    below = np.unique(stat[stat < T])
    prev = float(below.max()) if below.size else float('-inf')
    return T, int(wins.sum()), prev, int(below.size)


def stage2_clean_cuts(win, planes, triage):
    """Clean cuts on atk/def/hp for every contested cell."""
    cuts = []
    contested = triage['contested_mask']
    for si, oi in zip(*np.nonzero(contested)):
        si, oi = int(si), int(oi)
        wins = win[:, si, oi]
        for axis, stat in planes.items():
            got = clean_cut(stat, wins)
            if got is None:
                continue
            T, n_pass, prev, n_below = got
            cuts.append({
                'axis': axis, 'si': si, 'oi': oi, 'T': T,
                'n_pass': n_pass, 'prev_attained': prev,
                'n_attained_below': n_below,
            })
    return cuts


def stage2_reverse_cuts(win, planes, triage):
    """Reverse clean cuts: (stat <= T) == win. Used by the cost field."""
    out = []
    for si, oi in zip(*np.nonzero(triage['contested_mask'])):
        si, oi = int(si), int(oi)
        wins = win[:, si, oi]
        for axis, stat in planes.items():
            T = float(stat[wins].max())
            if np.array_equal(stat <= T, wins):
                out.append({'axis': axis, 'si': si, 'oi': oi, 'T': T,
                            'n_pass': int(wins.sum())})
    return out


# ---------------------------------------------------------------------------
# Stage 3 -- does the cut hold in the other modes and the other arms
# ---------------------------------------------------------------------------

def direction_rates(win_other, stat, T, si, oi):
    """(rate at/above T, rate below T) for one cell in another cube."""
    wins = win_other[:, si, oi]
    above = stat >= T
    r_above = float(wins[above].mean()) if above.any() else 0.0
    r_below = float(wins[~above].mean()) if (~above).any() else 0.0
    return r_above, r_below


def stage3_holds(cut, mode_cubes, arm_cubes, planes):
    """Per-cut mode/arm hold counts under G-direction.

    ``mode_cubes`` / ``arm_cubes`` map name -> (win cube, stat planes).
    """
    stat = planes[cut['axis']]
    modes_ok, modes_fail = [], []
    for name, (w_other, pl_other) in mode_cubes.items():
        r_a, r_b = direction_rates(w_other, pl_other[cut['axis']], cut['T'],
                                   cut['si'], cut['oi'])
        (modes_ok if (r_a >= DIRECTION_MIN_ABOVE and r_a > r_b)
         else modes_fail).append((name, r_a, r_b))
    arms_ok, arms_fail = [], []
    for name, (w_other, pl_other) in arm_cubes.items():
        r_a, r_b = direction_rates(w_other, pl_other[cut['axis']], cut['T'],
                                   cut['si'], cut['oi'])
        (arms_ok if (r_a >= DIRECTION_MIN_ABOVE and r_a > r_b)
         else arms_fail).append((name, r_a, r_b))
    return {
        'modes_ok': len(modes_ok), 'modes_total': len(mode_cubes),
        'modes_fail': [n for n, _, _ in modes_fail],
        'modes_detail': modes_ok + modes_fail,
        'arms_ok': len(arms_ok), 'arms_total': len(arm_cubes),
        'arms_fail': [n for n, _, _ in arms_fail],
    }


# ---------------------------------------------------------------------------
# Stage 4 -- mechanism labels (CMP, breakpoint, unattributed)
# ---------------------------------------------------------------------------

def opponent_build(name, league, mode):
    """Build one pool opponent exactly as the bake did. None when unbuildable."""
    species, variant, shadow = parse_opponent_spec(name)
    try:
        ivs = resolve_opp_ivs(species, league, shadow, mode)
        pk = Pokemon.at_best_level(species, *ivs, league=league, shadow=shadow)
    except Exception:
        return None
    cmp_atk = pk.atk / SHADOW_ATK_BONUS if shadow else pk.atk
    return {'species': species, 'shadow': shadow, 'ivs': tuple(int(v) for v in ivs),
            'level': float(pk.level), 'atk': float(pk.atk), 'def': float(pk.def_),
            'hp': int(pk.hp), 'cmp_atk': float(cmp_atk)}


def cmp_line(build, focal_shadow):
    """The focal attack value at which focal CMP overtakes this opponent."""
    mult = SHADOW_ATK_BONUS if focal_shadow else 1.0
    return mult * build['cmp_atk']


def _move_dicts(label):
    """(fast move dict, [charged move dicts]) for a moveset-arm label."""
    fast_moves, charged_moves = get_moves()
    fast_name, rest = label.split('/', 1)
    fast = fast_moves.get(fast_name.strip())
    charged = []
    for token in rest.replace('+', ',').split(','):
        cm = charged_moves.get(token.strip())
        if cm is not None:
            charged.append(cm)
    return fast, charged


def breakpoint_label(cut, prev_atk, focal_types, opp_build, opp_types,
                     arm_label, opp_charged):
    """Is there a damage-integer step across the cut, at a reachable stage?

    Def stages the OPPONENT's own kit can reach: 0 always; +1/+2 only if it
    carries a guaranteed self-Def buff. Focal atk stages an opponent debuff can
    impose are searched the same way.
    """
    fast, charged = _move_dicts(arm_label)
    moves = [m for m in ([fast] + charged) if m]
    if not moves or opp_build is None:
        return None
    def_stages = [0]
    atk_stages = [0]
    for cm in opp_charged:
        buffs = cm.get('buffs')
        if not buffs or float(cm.get('buffApplyChance', 0) or 0) != 1:
            continue
        if cm.get('buffTarget') == 'self' and buffs[1] > 0:
            def_stages.append(int(buffs[1]))
        if cm.get('buffTarget') == 'opponent' and buffs[0] < 0:
            atk_stages.append(int(buffs[0]))
    for ds in sorted(set(def_stages)):
        opp_def = opp_build['def'] * _stat_stage_mult(ds)
        for as_ in sorted(set(atk_stages)):
            mult = _stat_stage_mult(as_)
            for m in moves:
                lo = damage(m['power'], prev_atk * mult, opp_def, m['type'],
                            focal_types, opp_types)
                hi = damage(m['power'], cut['T'] * mult, opp_def, m['type'],
                            focal_types, opp_types)
                if hi != lo:
                    return {'move': m['moveId'], 'from': int(lo), 'to': int(hi),
                            'def_stage': ds, 'atk_stage': as_}
    return None


def stage4_mechanism(cut, state, mode, builds, focal_types, arm_label,
                     opp_types, opp_charged_moves):
    """CMP / BREAKPOINT / UNATTRIBUTED for one attack cut."""
    if cut['axis'] != 'atk':
        return {'kind': 'unattributed'}
    oi = cut['oi']
    build = builds.get(oi)
    if build is not None:
        line = cmp_line(build, state['shadow'])
        if cut['prev_attained'] < line <= cut['T']:
            return {'kind': 'cmp', 'line': line, 'build': build}
    bp = breakpoint_label(cut, cut['prev_attained'], focal_types, build,
                          opp_types.get(oi, ()), arm_label,
                          opp_charged_moves.get(oi, []))
    if bp is not None:
        return {'kind': 'breakpoint', 'detail': bp, 'build': build}
    return {'kind': 'unattributed', 'build': build,
            'line': (cmp_line(build, state['shadow']) if build else None)}


# ---------------------------------------------------------------------------
# Stage 5 -- coverage ladder over the opponent's own IV grid
# ---------------------------------------------------------------------------

def opponent_iv_grid(species, league, shadow):
    """cmp_atk for all 4096 IV spreads of one opponent, at its league level."""
    lines = np.empty(4096, dtype=float)
    k = 0
    for a in range(16):
        for d in range(16):
            for s in range(16):
                pk = Pokemon.at_best_level(species, a, d, s, league=league,
                                           shadow=shadow)
                lines[k] = pk.atk / SHADOW_ATK_BONUS if shadow else pk.atk
                k += 1
    return lines


COVERAGE_ROWS = ('rank-1', 'PvPoke default', '10/10/10', 'grid median',
                 'hundo (15/15/15)', '12/12/12', 'max attack')


def stage5_coverage(cut, state, mode, atk, league):
    """Strict coverage ladder for a CMP rung (G-tie: strict '<' only)."""
    name = state['opponent_names'][cut['oi']]
    species, _variant, shadow = parse_opponent_spec(name)
    try:
        grid = opponent_iv_grid(species, league, shadow)
    except Exception:
        return None
    mult = SHADOW_ATK_BONUS if state['shadow'] else 1.0
    focal_shadow_mult = mult

    def row(label, cmp_atk_val, note=None):
        line = focal_shadow_mult * cmp_atk_val
        strict = float((grid < cmp_atk_val).mean())
        ties = int((grid == cmp_atk_val).sum())
        clearers = int((atk >= line).sum())
        return {'label': label, 'line': line, 'strict': strict,
                'ties': ties, 'focal': clearers, 'note': note}

    def build_cmp(ivs):
        pk = Pokemon.at_best_level(species, *ivs, league=league, shadow=shadow)
        return pk.atk / SHADOW_ATK_BONUS if shadow else pk.atk

    rows = []
    try:
        r1 = resolve_opp_ivs(species, league, shadow, 'rank1')
        rows.append(row(f"rank-1 ({r1[0]}/{r1[1]}/{r1[2]})", build_cmp(r1)))
        dflt = resolve_opp_ivs(species, league, shadow, 'pvpoke')
        rows.append(row(f"PvPoke default ({dflt[0]}/{dflt[1]}/{dflt[2]})",
                        build_cmp(dflt), note='floor line'))
        rows.append(row('10/10/10 (raid/research floor)', build_cmp((10, 10, 10))))
        rows.append(row('grid median', float(np.median(grid))))
        rows.append(row('hundo (15/15/15)', build_cmp((15, 15, 15))))
        rows.append(row('12/12/12 (lucky trade)', build_cmp((12, 12, 12))))
    except Exception:
        return None
    top = float(grid.max())
    n_top = int((grid == top).sum())
    rows.append(row(f"ties the max-attack {species} ({n_top} spreads)", top))
    for r in rows:
        if r['strict'] >= 1.0 and r['ties'] > 0:
            raise GuardError(
                f"G-tie: field=Coverage cell={name} printed='100.0%' "
                f"recomputed={r['strict']:.4f} with {r['ties']} ties "
                f"(blob=- arm=- mode={mode})")
    return {'opponent': name, 'rows': rows,
            'grid_min': float(grid.min()) * focal_shadow_mult,
            'grid_max': top * focal_shadow_mult}


# ---------------------------------------------------------------------------
# Stage 6 -- rung eligibility and floor selection
# ---------------------------------------------------------------------------

def rung_gates(cut, holds, mech, ranks, triage, state, n_iv):
    """Every stage-6 gate for one cut, as a dict of booleans + reasons."""
    name = state['opponent_names'][cut['oi']]
    species, _v, _s = parse_opponent_spec(name)
    rank = ranks[cut['oi']]
    pool = cut['n_pass'] / n_iv
    gates = {
        'G-material-hi': pool <= MATERIAL_HI,
        'G-material-lo': pool >= MATERIAL_LO,
        'G-material-gap': cut['n_attained_below'] >= MIN_ATTAINED_BELOW,
        'G-rank': rank is not None and rank <= RANK_GATE,
        'G-attributed': mech['kind'] in ('cmp', 'breakpoint'),
        'G-direction': holds['modes_ok'] == holds['modes_total'],
        'G-scenario': not triage['degenerate'][cut['si']],
        'G-caveat': not any(c in species for c in CAVEAT_SPECIES),
    }
    return gates


def stage6_select(rungs, band=DECISION_BAND):
    """Lowest eligible rung whose pool share sits inside ``band`` (D1)."""
    eligible = [r for r in rungs if r['eligible']
                and band[0] <= r['pool_share'] <= band[1]]
    if not eligible:
        return None
    return min(eligible, key=lambda r: r['T'])


def stage6_sensitivity(rungs, bands=SENSITIVITY_BANDS):
    out = []
    for b in bands:
        pick = stage6_select(rungs, b)
        out.append({'band': b, 'T': (pick['T'] if pick else None),
                    'cell': (pick['cells'][0]['label'] if pick else None)})
    return out


# ---------------------------------------------------------------------------
# Stage 7 -- print precision
# ---------------------------------------------------------------------------

def stage7_print_precision(T, stat, stat_other=None, field='Floor', ctx=None,
                           dp_options=(2, 3)):
    """Printed = floor(T*100)/100 when that is unambiguous, else 3 dp, else abort.

    The 2-dp rendering is refused if any attained value in the L50 grid falls
    in [printed, T), or (when a second level view is supplied) if any attained
    value there whose own 2-dp rendering equals ``printed`` lies below T.
    """
    ctx = ctx or {}
    for dp in dp_options:
        printed = math.floor(T * (10 ** dp)) / (10 ** dp)
        bad = ((stat >= printed) & (stat < T)).any()
        if not bad and stat_other is not None:
            other_2dp = np.floor(stat_other * (10 ** dp)) / (10 ** dp)
            bad = bool(((other_2dp == printed) & (stat_other < T)).any())
        if not bad:
            return {'printed': printed, 'dp': dp,
                    'n_selected': int((stat >= printed).sum())}
    guard_fail('G-print', field, ctx.get('cell', '-'), f"{T:.3f}", T, ctx)


def printed_cut(T, attained, field, ctx=None, dp_options=(2, 3, 4, 5, 6)):
    """2-dp (or 3-dp) rendering of a >= threshold that selects the same set.

    Every threshold the brief prints goes through here, not only the floor.
    Rounding to nearest is NOT safe for a ``>=`` line: the Sableye 1v1
    Hippowdon rung is 149.689078, and "Atk >= 149.69" selects 1519 spreads
    where the rung holds 1538 -- it cuts off the 19 spreads sitting exactly
    on the cut. Flooring keeps the printed line a valid selector, and
    stage 7's check is what proves it.

    The FLOOR keeps the plan's strict two-rung rule (2 dp, then 3 dp, then
    abort) because an unprintable floor is a bug worth stopping for. Every
    other threshold may use more places instead: the Def axis packs attained
    values closer than a thousandth (2v2 Lapras wants 102.37156897), and
    refusing to print an evidence row is worse than printing it at the
    precision it needs.
    """
    pp = stage7_print_precision(T, np.asarray(attained, dtype=float),
                                field=field, ctx=ctx, dp_options=dp_options)
    return pp['printed'], pp['dp']


def fmt(value, dp=2):
    return f"{value:.{dp}f}"


def pct(x, dp=1):
    """Percentage that never reads as an exact 0 or 100 unless it is one.

    2v2 Azumarill's closest split classifies 4095 of 4096 spreads, which at
    one decimal place renders "100.0%" -- a clean cut's claim, made by a
    number that is not one. Escalate places until the rendering stops
    claiming exactness.
    """
    s = f"{100.0 * x:.{dp}f}%"
    if 0.0 < x < 1.0:
        for d in range(dp, 9):
            s = f"{100.0 * x:.{d}f}%"
            if float(s[:-1]) not in (0.0, 100.0):
                break
    return s


# ---------------------------------------------------------------------------
# Stage 8 -- example spreads
# ---------------------------------------------------------------------------

def stage8_examples(meta, win, floor_mask, contested_cells, sp, sp_rank):
    """Three example spreads by printed rules, dominance-checked."""
    idx = np.nonzero(floor_mask)[0]
    if idx.size == 0:
        return []
    cells_won = win[:, [c[0] for c in contested_cells],
                    [c[1] for c in contested_cells]].sum(axis=1)
    total_won = win.reshape(win.shape[0], -1).sum(axis=1)
    sp_share = sp / sp.max()
    hi_sp = idx[sp_share[idx] >= SP_FLOOR]

    picks = []

    def add(rule, i):
        i = int(i)
        picks.append({
            'rule': rule, 'ivs': tuple(int(v) for v in meta[i, :3]),
            'level': float(meta[i, 3]), 'atk': float(meta[i, 5]),
            'def': float(meta[i, 6]), 'hp': int(meta[i, 7]),
            'sp_share': float(sp_share[i]), 'sp_rank': int(sp_rank[i]),
            'cells': int(cells_won[i]), 'total': int(total_won[i]), 'i': i,
        })

    add('highest stat product clearing the floor', idx[np.argmax(sp[idx])])
    if hi_sp.size:
        add(f"most cells won among clearers with SP >= {int(SP_FLOOR*100)}%",
            hi_sp[np.argmax(cells_won[hi_sp])])
        bulk = meta[hi_sp, 6] * meta[hi_sp, 7]
        add(f"bulkiest (max Def x HP) among clearers with SP >= {int(SP_FLOOR*100)}%",
            hi_sp[np.argmax(bulk)])
    seen, out = set(), []
    for p in picks:
        if p['i'] in seen:
            continue
        seen.add(p['i'])
        out.append(p)
    return out


def per_scenario_wins(win, i, n_sc):
    return [int(win[i, si, :].sum()) for si in range(n_sc)]


# ---------------------------------------------------------------------------
# Stage 9 -- bulk: frontier and co-gates
# ---------------------------------------------------------------------------

def stage9_frontier(meta, floor_mask):
    """HP -> max attained Def among floor clearers. No means anywhere."""
    hp = meta[floor_mask, 7]
    dfn = meta[floor_mask, 6]
    out = []
    for h in np.unique(hp):
        out.append({'hp': int(h), 'max_def': float(dfn[hp == h].max()),
                    'n': int((hp == h).sum())})
    return out


def stage9_cogates(win, meta, floor_mask, contested_cells, ranks, triage, state,
                   n_iv):
    """Least attained Def / HP threshold inside the floor that wins a cell 100%."""
    clearers = np.nonzero(floor_mask)[0]
    out = []
    for axis, col in (('def', 6), ('hp', 7)):
        stat = meta[:, col]
        for (si, oi) in contested_cells:
            species, _v, _s = parse_opponent_spec(state['opponent_names'][oi])
            if any(c in species for c in CAVEAT_SPECIES):
                continue
            if triage['degenerate'][si]:
                continue
            rank = ranks[oi]
            if rank is None or rank > RANK_GATE:
                continue
            w = win[clearers, si, oi]
            base_rate = float(w.mean())
            if base_rate >= COGATE_MAX_BASE_RATE or base_rate == 0.0:
                continue
            losing = stat[clearers][~w]
            if losing.size == 0:
                continue
            above = np.unique(stat[clearers][stat[clearers] > losing.max()])
            if above.size == 0:
                continue
            t = float(above.min())
            sub = clearers[stat[clearers] >= t]
            if sub.size / n_iv < COGATE_MIN_SHARE:
                continue
            if not win[sub, si, oi].all():
                continue
            outside = clearers[stat[clearers] < t]
            rate_out = float(win[outside, si, oi].mean()) if outside.size else 0.0
            pr, dp = printed_cut(t, stat[clearers], field='Bulk co-gate',
                                 ctx={'cell': cell_label(state, si, oi)})
            out.append({'axis': axis, 't': t, 'printed': pr, 'dp': dp,
                        'n': int(sub.size),
                        'si': si, 'oi': oi, 'rank': rank,
                        'rate_outside': rate_out, 'base_rate': base_rate,
                        'label': cell_label(state, si, oi)})
    out.sort(key=lambda r: (r['axis'], r['t']))
    return out


# ---------------------------------------------------------------------------
# Stage 9b -- alternative (bulk) target
# ---------------------------------------------------------------------------

def stage9b_alternative(win, meta, floor_mask, contested_cells, state):
    """The (Def >= d) & (HP >= h) rectangle that buys the most, or None.

    With a floor, the plan's rule: rectangles of at least ALT_MIN_MEMBERS
    members that contain no floor clearer, scored by the contested cells every
    member wins that at most ALT_MAX_CLEARER_RATE of the clearers win.

    With no floor there is nothing to be disjoint from, so that score is
    vacuous -- every cell every member wins counts, including the ones almost
    the whole grid wins. The baseline becomes the spreads OUTSIDE the
    rectangle, which is exact and free: if all ``n`` members win a cell, the
    winners outside it are ``total_win - n`` out of ``n_iv - n``.
    """
    dfn, hp = meta[:, 6], meta[:, 7]
    cells = np.array(contested_cells)
    if cells.size == 0:
        return None
    n_iv = win.shape[0]
    wc = win[:, cells[:, 0], cells[:, 1]]           # (n_iv, n_cells)
    total_win = wc.sum(axis=0)
    has_floor = bool(floor_mask.any())
    if has_floor:
        clearer_rate = wc[floor_mask].mean(axis=0)
        allowed_vs_floor = clearer_rate <= ALT_MAX_CLEARER_RATE
        floor_guaranteed = wc[floor_mask].all(axis=0)
    else:
        allowed_vs_floor = np.ones(wc.shape[1], dtype=bool)
        floor_guaranteed = np.zeros(wc.shape[1], dtype=bool)

    def exclusive_mask(n):
        """Cells that at most ALT_MAX_CLEARER_RATE of the non-members win."""
        outside = n_iv - n
        if outside <= 0:
            return np.zeros(wc.shape[1], dtype=bool)
        return (total_win - n) <= ALT_MAX_CLEARER_RATE * outside

    best = None
    for h in np.unique(hp):
        hmask = hp >= h
        if hmask.sum() < ALT_MIN_MEMBERS:
            continue
        for d in np.unique(dfn[hmask]):
            mask = hmask & (dfn >= d)
            n = int(mask.sum())
            if n < ALT_MIN_MEMBERS:
                break                                # monotone in d
            if has_floor and (mask & floor_mask).any():
                continue
            guaranteed_all = wc[mask].all(axis=0)
            excl = guaranteed_all & exclusive_mask(n)
            guaranteed = guaranteed_all & (allowed_vs_floor if has_floor
                                           else exclusive_mask(n))
            score = int(guaranteed.sum())
            key = (score, n)
            if best is None or key > best['key']:
                given_up = floor_guaranteed & ~wc[mask].any(axis=0)
                best = {
                    'key': key, 'score': score, 'n': n,
                    'def_cut': float(dfn[mask].min()),
                    'hp_cut': int(hp[mask].min()),
                    'guaranteed': [contested_cells[i]
                                   for i in np.nonzero(guaranteed)[0]],
                    'exclusive': [contested_cells[i]
                                  for i in np.nonzero(excl)[0]],
                    'given_up': [contested_cells[i]
                                 for i in np.nonzero(given_up)[0]],
                    'has_floor': has_floor,
                    'mask': mask,
                }
    if best is None or best['score'] == 0:
        return None
    return best


# ---------------------------------------------------------------------------
# Stage 10 -- changes the score, not the matchup
# ---------------------------------------------------------------------------

def stage10_score_only(scores, atk, triage, state, ranks):
    """Clean score steps >= SCORE_STEP_MIN on all-win / all-lose cells."""
    order = np.argsort(atk, kind='stable')
    a_sorted = atk[order]
    bounds = np.nonzero(np.diff(a_sorted))[0] + 1
    groups = np.split(np.arange(a_sorted.size), bounds)
    values = [float(a_sorted[g[0]]) for g in groups]
    if len(groups) < 2:
        return []
    n_sc, n_opp = scores.shape[1], scores.shape[2]
    flat = scores[order].reshape(scores.shape[0], -1)
    gmin = np.stack([flat[g].min(axis=0) for g in groups])
    gmax = np.stack([flat[g].max(axis=0) for g in groups])
    suffix_min = np.minimum.accumulate(gmin[::-1], axis=0)[::-1]
    suffix_max = np.maximum.accumulate(gmax[::-1], axis=0)[::-1]
    prefix_max = np.maximum.accumulate(gmax, axis=0)
    prefix_min = np.minimum.accumulate(gmin, axis=0)
    # A CLEAN step, both ways round. Upward: the lowest score at or above the
    # value beats the highest score below it. Downward: the lowest score BELOW
    # beats the highest score at or above. Using (suffix_min - prefix_max) for
    # the downward case is not a cleanliness test at all -- it only says some
    # spread above scores less than some spread below, which was true on 334
    # cells of the Sableye dive and is true on almost any noisy column.
    up = suffix_min[1:] - prefix_max[:-1]             # (n_groups-1, n_cells)
    down = prefix_min[:-1] - suffix_max[1:]
    degenerate = (triage['all_win_mask'] | triage['all_lose_mask']).reshape(-1)
    rows = []
    for ci in np.nonzero(degenerate)[0]:
        si, oi = divmod(int(ci), n_opp)
        # Both directions, because both are real: a cell can pay more score for
        # more attack, or lose score for it.
        for col, lo, hi in ((up, prefix_max, suffix_min),
                            (down, suffix_max, prefix_min)):
            j = int(np.argmax(col[:, ci]))
            if int(col[j, ci]) < SCORE_STEP_MIN:
                continue
            if col is up:
                below, above = int(prefix_max[j, ci]), int(suffix_min[j + 1, ci])
            else:
                below, above = int(prefix_min[j, ci]), int(suffix_max[j + 1, ci])
            rows.append({
                'T': values[j + 1], 'si': si, 'oi': oi,
                'below': below, 'above': above,
                'won': bool(triage['all_win_mask'][si, oi]),
                'rank': ranks[oi], 'label': cell_label(state, si, oi),
            })
    rows.sort(key=lambda r: (-abs(r['above'] - r['below']), r['label']))
    return rows


# ---------------------------------------------------------------------------
# Stage 11 -- rank-1 adjudication
# ---------------------------------------------------------------------------

def stage11_rank1(meta, sp, win, rungs, floor, atk, n_iv, atk_cuts=()):
    """Which side of the floor rank-1 is on, and what it clears.

    The cut count is over clean attack cuts (CELLS), not over distinct cut
    VALUES: two cells that turn over at the same number are two claims.
    """
    i = int(np.argmax(sp))
    clears = [c for c in (atk_cuts or rungs) if atk[i] >= c['T']]
    material = [r for r in rungs
                if r['gates']['G-material-lo'] and r['gates']['G-material-hi']]
    missed = [r for r in material if atk[i] < r['T']]
    return {
        'i': i, 'ivs': tuple(int(v) for v in meta[i, :3]),
        'level': float(meta[i, 3]), 'atk': float(meta[i, 5]),
        'def': float(meta[i, 6]), 'hp': int(meta[i, 7]),
        'clears_floor': bool(floor is not None and atk[i] >= floor['T']),
        'shortfall': (float(floor['T'] - atk[i]) if floor is not None else None),
        'n_cuts_cleared': len(clears), 'n_cuts': len(atk_cuts or rungs),
        'lowest_missed': _missed_row(min(missed, key=lambda r: r['T']), atk)
                          if missed else None,
        'total_won': int(win[i].sum()),
    }


def _missed_row(rung, atk):
    pr, dp = printed_cut(rung['T'], atk, field='Rank-1 check',
                         ctx={'cell': rung['cells'][0]['label']})
    return {'T': rung['T'], 'printed': pr, 'dp': dp,
            'cell': rung['cells'][0]['label'],
            'n_pass': rung['n_pass']}


# ---------------------------------------------------------------------------
# Stage 12 -- degradation ladder
# ---------------------------------------------------------------------------

DEGRADATION_RUNGS = ('a', 'b', 'c', 'd', 'e', 'floor')


def stage12_degradation(triage, cuts, rungs, floor, n_modes, n_arms, n_iv):
    """First rung that fires, with its printed sentence and its counts."""
    if triage['n_contested'] == 0:
        return {'rung': 'a', 'sentence':
                "No contested matchup on this dive: every cell in the pool is "
                "won by all 4096 spreads or lost by all of them, so no IV "
                "choice changes an outcome.",
                'counts': {'contested': 0}}
    if not cuts:
        return {'rung': 'b', 'sentence':
                f"No floor: 0 of {triage['n_contested']} contested matchups "
                f"separate cleanly on any single stat. Build for stat product.",
                'counts': {'contested': triage['n_contested'], 'clean': 0}}
    if floor is None:
        reasons = Counter()
        for r in rungs:
            for g, ok in r['gates'].items():
                if not ok:
                    reasons[g] += 1
        return {'rung': 'c', 'sentence':
                f"{len(cuts)} clean cuts exist on this dive and none is a floor: "
                f"no cut clears every gate with a pool share inside "
                f"[{pct(DECISION_BAND[0],0)}, {pct(DECISION_BAND[1],0)}] of the "
                f"grid.",
                'counts': dict(reasons)}
    if floor['pool_share'] < 0.02:
        return {'rung': 'd', 'sentence':
                f"A clean cut exists at {fmt(floor['T'])} but only "
                f"{floor['n_pass']} of {n_iv} spreads clear it, so it is too "
                f"rare to carry a floor label.",
                'counts': {'n_pass': floor['n_pass']}}
    return {'rung': 'floor', 'sentence': '', 'counts': {}}


def stage12_caps(n_modes, n_arms):
    """Rung (e) of the ladder: G-trivial.

    Deviation from the plan's "first rung that fires" wording: (e) is
    orthogonal to (a)-(d) -- a dive can have a floor AND only one arm baked
    (plain Sableye is exactly that) -- so it is reported as its own caveat
    instead of short-circuiting the ladder and hiding the floor.
    """
    if n_modes >= 2 and n_arms >= 2:
        return None
    return {'rung': 'e', 'sentence':
            f"{n_modes} opponent-IV setting(s) and {n_arms} moveset arm(s) "
            f"are baked here, so the modes and arms columns are capped and "
            f"cross-setting robustness is not measured.",
            'counts': {'modes': n_modes, 'arms': n_arms}}


# ---------------------------------------------------------------------------
# D7 -- catch odds under uniform-random IVs
# ---------------------------------------------------------------------------

def catch_encounters(pool_share, targets=CATCH_TARGETS):
    out = []
    for t in targets:
        if pool_share <= 0:
            out.append((t, None))
        elif pool_share >= 1:
            out.append((t, 1))
        else:
            out.append((t, int(math.ceil(math.log(1 - t) / math.log(1 - pool_share)))))
    return out


# ---------------------------------------------------------------------------
# Stage 12b -- the dirtiest-but-closest thresholds, for the negative brief
# ---------------------------------------------------------------------------

def stage12b_dirty_thresholds(win, planes, contested_cells, claimed, ranks,
                              triage, state, top_n=4):
    """Closest single-stat split on cells that have no CLEAN cut (D12).

    A "no floor" result still has to carry evidence. For each unclaimed
    contested cell this reports the attained threshold with the highest
    elementwise agreement with the win column, and the win rates on each
    side of it -- the number the shipped 75/25 "flips at" engine would
    quote, said out loud as dirty rather than promoted to a floor.
    """
    sorted_by = {}
    for axis, stat in planes.items():
        order = np.argsort(stat, kind='stable')
        s = stat[order]
        starts = np.concatenate(([0], np.nonzero(np.diff(s))[0] + 1))
        sorted_by[axis] = (order, s, starts)
    n_iv = win.shape[0]
    rows = []
    for (si, oi) in contested_cells:
        if (si, oi) in claimed:
            continue
        if triage['degenerate'][si]:
            continue
        rank = ranks[oi]
        if rank is None or rank > RANK_GATE:
            continue
        wins = win[:, si, oi]
        total_win = int(wins.sum())
        pick = None
        for axis, (order, s, starts) in sorted_by.items():
            w = wins[order]
            cum_win = np.concatenate(([0], np.cumsum(w)))
            cum_loss = np.arange(n_iv + 1) - cum_win
            correct = cum_loss[starts] + (total_win - cum_win[starts])
            # starts[0] puts every spread on the high side, which classifies
            # an almost-all-lose column at 99.9% while predicting nothing.
            # A threshold has to cut the grid in two to be a threshold.
            order_j = np.argsort(-correct[1:])
            for jj in order_j:
                j = int(jj) + 1
                t = float(s[starts[j]])
                above = planes[axis] >= t
                r_above = float(wins[above].mean())
                r_below = float(wins[~above].mean())
                if r_above <= r_below:
                    continue
                acc = float(correct[j]) / n_iv
                if pick is None or acc > pick['accuracy']:
                    pick = {'axis': axis, 't': t, 'accuracy': acc,
                            'n_wrong': int(n_iv - correct[j]),
                            'rate_above': r_above, 'rate_below': r_below,
                            'n_above': int(above.sum()),
                            'n_win_above': int(wins[above].sum()),
                            'n_win_below': int(wins[~above].sum()),
                            'n_below': int((~above).sum())}
                break
        if pick is None:
            continue
        pr, dp = printed_cut(pick['t'], planes[pick['axis']],
                             field='Dirty threshold',
                             ctx={'cell': cell_label(state, si, oi)})
        pick.update({'printed': pr, 'dp': dp, 'rank': rank,
                     'cell': cell_label(state, si, oi),
                     'win_rate': float(wins.mean())})
        rows.append(pick)
    rows.sort(key=lambda r: -r['accuracy'])
    return rows[:top_n]


def cell_cuts_by_view(si, oi, cubes, axis='atk'):
    """The same cell's clean cut in every other mode / arm view (D5).

    ``cubes`` maps a view name to (win cube, stat planes). A view with no
    clean cut for that cell reports its win rate instead, so a rung row can
    say "dirty on the other arms (47%)" rather than going silent.
    """
    out = {}
    for name, (w_other, planes_other) in cubes.items():
        stat = planes_other[axis]
        wins = w_other[:, si, oi]
        got = clean_cut(stat, wins)
        if got is None:
            out[name] = {'clean': False, 'rate': float(wins.mean())}
        else:
            pr, dp = printed_cut(got[0], stat, field='Cross-view cut',
                                 ctx={'cell': name})
            out[name] = {'clean': True, 'T': got[0], 'printed': pr, 'dp': dp,
                         'n_pass': got[1]}
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _species_types(name):
    """Type list for a species, for STAB and effectiveness in stage 4b.

    ``get_species`` returns only the baseStats dict, which carries no
    ``types`` key, so ``parse_types`` fell back to ``['normal']`` for every
    species and silently gave every breakpoint test the wrong damage
    constant (the Sableye mirror's Foul Play read 61 -> 61 instead of
    58 -> 59). ``find_pokemon_entry`` returns the full gamemaster entry.
    """
    entry = find_pokemon_entry(name)
    return tuple(parse_types(entry)) if entry else ()


def compute_brief(state, arm, blob_path, mode='pvpoke', level='l50'):
    """Run stages 1-12 for one moveset arm and return a plain-dict fact set."""
    league = state['league']
    names = state['opponent_names']
    n_opp = len(names)
    n_sc = len(state['shield_scenarios'])
    modes = list(state['opp_iv_modes'])
    n_arms = len(state['moveset_data'])
    arm_label = state['moveset_data'][arm]['label']
    ctx = {'blob': os.path.basename(blob_path), 'arm': arm, 'mode': mode}

    scores, meta = arm_view(state, arm, mode, level)
    n_iv = scores.shape[0]
    win = win_cube(scores)
    atk, dfn, hp = stat_planes(meta)
    planes = {'atk': atk, 'def': dfn, 'hp': hp}
    sp = atk * dfn * hp
    sp_order = np.argsort(-sp, kind='stable')
    sp_rank = np.empty(n_iv, dtype=int)
    sp_rank[sp_order] = np.arange(1, n_iv + 1)

    triage = stage1_triage(win)
    cuts = stage2_clean_cuts(win, planes, triage)
    reverse_cuts = stage2_reverse_cuts(win, planes, triage)

    mode_cubes = {}
    for m in modes:
        sc_m, meta_m = arm_view(state, arm, m, level)
        a_m, d_m, h_m = stat_planes(meta_m)
        mode_cubes[m] = (win_cube(sc_m), {'atk': a_m, 'def': d_m, 'hp': h_m})
    arm_cubes = {}
    for k in range(n_arms):
        sc_k, meta_k = arm_view(state, k, mode, level)
        a_k, d_k, h_k = stat_planes(meta_k)
        arm_cubes[state['moveset_data'][k]['label']] = (
            win_cube(sc_k), {'atk': a_k, 'def': d_k, 'hp': h_k})

    ranks = build_opp_meta_ranks(names, league, cup=state.get('cup'))
    builds = {}
    for oi, nm in enumerate(names):
        builds[oi] = opponent_build(nm, league, mode)
    opp_types = {}
    opp_charged = {}
    _fast, charged_all = get_moves()
    for oi, nm in enumerate(names):
        species, _v, _s = parse_opponent_spec(nm)
        opp_types[oi] = _species_types(species)
        ms = state['opp_movesets'][oi] if oi < len(state['opp_movesets']) else None
        opp_charged[oi] = [charged_all[c] for c in (ms[1] if ms else [])
                           if c in charged_all]
    focal_types = _species_types(state['species'])

    # per-cut mechanism, holds, gates
    for c in cuts:
        c['label'] = cell_label(state, c['si'], c['oi'])
        c['rank'] = ranks[c['oi']]
        c['mech'] = stage4_mechanism(c, state, mode, builds, focal_types,
                                     arm_label, opp_types, opp_charged)
        c['holds'] = stage3_holds(c, mode_cubes, arm_cubes, planes)
        c['gates'] = rung_gates(c, c['holds'], c['mech'], ranks, triage, state,
                                n_iv)
        c['eligible'] = all(c['gates'].values())
        c['pool_share'] = c['n_pass'] / n_iv
        members = triage['dedup_members'].get(triage['dedup_of'][(c['si'], c['oi'])], [])
        c['dedup_members'] = [names[o] for o in members]

    atk_cuts = [c for c in cuts if c['axis'] == 'atk']
    rungs = []
    for T in sorted({c['T'] for c in atk_cuts}):
        group = [c for c in atk_cuts if c['T'] == T]
        rep = group[0]
        rungs.append({
            'T': T, 'n_pass': rep['n_pass'], 'pool_share': rep['pool_share'],
            'n_attained_below': rep['n_attained_below'],
            'prev_attained': rep['prev_attained'],
            'cells': group,
            'eligible': any(c['eligible'] for c in group),
            'gates': {g: any(c['gates'][g] for c in group)
                      for g in rep['gates']},
            'modes_ok': max(c['holds']['modes_ok'] for c in group),
            'modes_total': rep['holds']['modes_total'],
            'arms_ok': max(c['holds']['arms_ok'] for c in group),
            'arms_total': rep['holds']['arms_total'],
        })

    floor_rung = stage6_select(rungs)
    sensitivity = stage6_sensitivity(rungs)

    contested_cells = [(int(si), int(oi))
                       for si, oi in zip(*np.nonzero(triage['contested_mask']))]
    degradation = stage12_degradation(triage, cuts, rungs, floor_rung,
                                      len(modes), n_arms, n_iv)
    caps = stage12_caps(len(modes), n_arms)
    claimed = {(c['si'], c['oi']) for c in cuts}
    dirty = stage12b_dirty_thresholds(win, planes, contested_cells, claimed,
                                      ranks, triage, state)

    facts = {
        'header': {
            'species': state['species'], 'shadow': bool(state['shadow']),
            'league': league, 'arm': arm, 'arm_label': arm_label,
            'n_arms': n_arms, 'level_view': level,
            'level_cap': state.get('best_buddy', {}).get('default_cap'),
            'pool_size': n_opp, 'pool_label': state.get('opponent_label'),
            'modes': modes, 'blob': os.path.basename(blob_path),
            'blob_date': _blob_date(blob_path),
            'rankings_snapshot': rankings_snapshot_date(league,
                                                        cup=state.get('cup')),
            'n_iv': n_iv, 'n_sc': n_sc,
        },
        'triage': {
            'all_win': triage['n_all_win'], 'all_lose': triage['n_all_lose'],
            'contested': triage['n_contested'],
            'degenerate': [scenario_label(state, si)
                           for si, bad in triage['degenerate'].items() if bad],
            'degenerate_detail': {scenario_label(state, si):
                                  (int(triage['contested_mask'][si].sum()),
                                   triage['n_patterns'][si])
                                  for si in range(n_sc)},
        },
        'clean_counts': dict(Counter(c['axis'] for c in cuts)),
        'n_distinct_atk_cuts': len({c['T'] for c in atk_cuts}),
        'reverse_cuts': len(reverse_cuts),
        'degradation': degradation,
        'caps': caps,
        'dirty_thresholds': dirty,
        'sensitivity': sensitivity,
        'constants': {
            'decision_band': list(DECISION_BAND),
            'material': [MATERIAL_LO, MATERIAL_HI],
            'min_attained_below': MIN_ATTAINED_BELOW,
            'rank_gate': RANK_GATE, 'direction_min_above': DIRECTION_MIN_ABOVE,
            'rung_pool_min': RUNG_POOL_MIN, 'cogate_min_share': COGATE_MIN_SHARE,
            'alt_min_members': ALT_MIN_MEMBERS, 'score_step_min': SCORE_STEP_MIN,
            'sp_floor': SP_FLOOR, 'modes_to_list': MODES_TO_LIST,
            'caveat_species': list(CAVEAT_SPECIES),
        },
    }

    tally = Counter()
    for c in cuts:
        for g, ok in c['gates'].items():
            if not ok:
                tally[g] += 1
    facts['gate_tally'] = {'n_cuts': len(cuts),
                           'n_eligible': sum(1 for c in cuts if c['eligible']),
                           'failed': dict(tally)}

    facts['not_claimed'] = _not_claimed(win, triage, cuts, contested_cells,
                                        state, ranks, floor_rung, atk)

    if floor_rung is None:
        facts['floor'] = None
        facts['rungs_above'] = []
        facts['rungs_below'] = [_rung_row(r, state, n_iv, atk) for r in rungs
                                if r['gates']['G-material-lo']
                                and r['gates']['G-material-hi']]
        facts['bulk'] = {'clean_def': facts['clean_counts'].get('def', 0),
                         'clean_hp': facts['clean_counts'].get('hp', 0),
                         'frontier': [], 'cogates': []}
        facts['alternative'] = _alt_facts(
            stage9b_alternative(win, meta, np.zeros(n_iv, bool),
                                contested_cells, state), state, meta, win, n_iv)
        facts['examples'] = []
        facts['rank1'] = stage11_rank1(meta, sp, win, rungs, None, atk, n_iv, atk_cuts)
        facts['coverage'] = None
        facts['mirror'] = _mirror(state, win, meta, atk, None, mode_cubes, modes)
        facts['score_only'] = [_score_row(r, atk) for r in
                               stage10_score_only(scores, atk, triage, state, ranks)]
        facts['cost'] = {'reverse_cuts': len(reverse_cuts), 'diff': None}
        facts['catch'] = []
        return facts

    # --- floor present -------------------------------------------------
    _, meta51 = arm_view(state, arm, mode, 'l51')
    atk51 = meta51[:, 5]
    pp = stage7_print_precision(floor_rung['T'], atk, atk51, field='Floor',
                                ctx=dict(ctx, cell=floor_rung['cells'][0]['label']))
    floor_mask = atk >= floor_rung['T']
    floor_cell = next((c for c in floor_rung['cells'] if c['eligible']),
                      floor_rung['cells'][0])
    below = ~floor_mask
    below_scores = scores[below, floor_cell['si'], floor_cell['oi']]
    above_scores = scores[floor_mask, floor_cell['si'], floor_cell['oi']]
    energy = state['moveset_data'][arm].get('energy')
    energy_note = None
    if energy is not None and mode in energy:
        e = np.asarray(energy[mode], dtype=np.int32).reshape(-1, n_sc, n_opp)
        e_below = np.unique(e[below, floor_cell['si'], floor_cell['oi']])
        e_above = np.unique(e[floor_mask, floor_cell['si'], floor_cell['oi']])
        energy_note = {'below': [int(v) for v in e_below[:4]],
                       'above': [int(v) for v in e_above[:4]],
                       'below_single': bool(e_below.size == 1),
                       'above_single': bool(e_above.size == 1)}

    owners = sorted({parse_opponent_spec(c['label'].split(' ', 1)[1])[0]
                     for c in floor_rung['cells'] if c['eligible']})
    facts['floor'] = {
        'T': floor_rung['T'], 'printed': pp['printed'], 'dp': pp['dp'],
        'n_pass': floor_rung['n_pass'], 'pool_share': floor_rung['pool_share'],
        'axis': 'atk',
        'cell': floor_cell['label'], 'rank': floor_cell['rank'],
        'mech': _mech_facts(floor_cell['mech']),
        'dedup_members': floor_cell['dedup_members'],
        'modes_ok': floor_rung['modes_ok'], 'modes_total': floor_rung['modes_total'],
        'arms_ok': floor_rung['arms_ok'], 'arms_total': floor_rung['arms_total'],
        'modes_fail': floor_cell['holds']['modes_fail'],
        'n_below': int(below.sum()), 'n_below_win': int(win[below, floor_cell['si'],
                                                            floor_cell['oi']].sum()),
        'score_below': [int(below_scores.min()), int(below_scores.max())],
        'score_above': [int(above_scores.min()), int(above_scores.max())],
        'energy': energy_note,
        'owners': owners,
        'single_owner': len(owners) == 1,
        'other_cells_at_T': [c['label'] for c in floor_rung['cells']
                             if c is not floor_cell],
        'other_cells_dropped': [
            {'label': c['label'],
             'failed': [g for g, ok in c['gates'].items() if not ok],
             'modes_ok': c['holds']['modes_ok']}
            for c in floor_rung['cells'] if not c['eligible']],
    }
    facts['catch'] = [{'target': t, 'n': n}
                      for t, n in catch_encounters(floor_rung['pool_share'])]
    facts['floor']['per_mode_cuts'] = cell_cuts_by_view(
        floor_cell['si'], floor_cell['oi'], mode_cubes)
    facts['floor']['per_arm_cuts'] = cell_cuts_by_view(
        floor_cell['si'], floor_cell['oi'], arm_cubes)

    cov = None
    if floor_cell['mech']['kind'] == 'cmp':
        cov = stage5_coverage(floor_cell, state, mode, atk, league)
    facts['coverage'] = cov

    above_rungs = [r for r in rungs
                   if r['T'] > floor_rung['T']
                   and r['pool_share'] >= RUNG_POOL_MIN
                   and r['modes_ok'] >= MODES_TO_LIST]
    # The tail is what lies BEYOND the last printed rung. A rung that sits
    # between the floor and the last printed one but fails the listing filter
    # is "dropped", not "beyond" -- lumping the two together made the tail
    # sentence quote a bait-only Wartortle rung as the widest one beyond.
    top_printed = max((r['T'] for r in above_rungs), default=floor_rung['T'])
    tail = [r for r in rungs if r['T'] > top_printed and r not in above_rungs]
    dropped = [r for r in rungs if floor_rung['T'] < r['T'] <= top_printed
               and r not in above_rungs]
    facts['rungs_above'] = [_rung_row(r, state, n_iv, atk) for r in above_rungs]
    facts['rungs_above_tail'] = _tail_sentence(above_rungs, tail, state, n_iv)
    facts['rungs_dropped'] = [
        {'printed': _rung_row(r, state, n_iv, atk)['printed'],
         'dp': _rung_row(r, state, n_iv, atk)['dp'],
         'cell': r['cells'][0]['label'], 'rank': r['cells'][0]['rank'],
         'pool_share': r['pool_share'],
         'modes_ok': r['modes_ok'], 'modes_total': r['modes_total']}
        for r in dropped]
    facts['rungs_below'] = [_rung_row(r, state, n_iv, atk) for r in rungs
                            if r['T'] < floor_rung['T']
                            and MATERIAL_LO <= r['pool_share'] <= MATERIAL_HI]

    facts['bulk'] = {
        'clean_def': facts['clean_counts'].get('def', 0),
        'clean_hp': facts['clean_counts'].get('hp', 0),
        'contested': triage['n_contested'],
        'clean_atk': facts['clean_counts'].get('atk', 0),
        'frontier': stage9_frontier(meta, floor_mask),
        'cogates': [_cogate_row(r) for r in
                    stage9_cogates(win, meta, floor_mask, contested_cells,
                                   ranks, triage, state, n_iv)],
        'cells_won_range': [
            int(win[floor_mask].reshape(int(floor_mask.sum()), -1).sum(axis=1).min()),
            int(win[floor_mask].reshape(int(floor_mask.sum()), -1).sum(axis=1).max())],
    }
    for r in facts['rungs_above']:
        rung = next(x for x in above_rungs if x['T'] == r['T'])
        rep = rung['cells'][0]
        r['per_arm_cuts'] = cell_cuts_by_view(rep['si'], rep['oi'], arm_cubes)
        r['per_mode_cuts'] = cell_cuts_by_view(rep['si'], rep['oi'], mode_cubes)
        r['cogates'] = [_cogate_row(x) for x in
                        stage9_cogates(win, meta, atk >= rung['T'],
                                       contested_cells, ranks, triage, state,
                                       n_iv)]

    alt = stage9b_alternative(win, meta, floor_mask, contested_cells, state)
    facts['alternative'] = _alt_facts(alt, state, meta, win, n_iv)

    facts['examples'] = stage8_examples(meta, win, floor_mask, contested_cells,
                                        sp, sp_rank)
    facts['rank1'] = stage11_rank1(meta, sp, win, rungs, floor_rung, atk, n_iv, atk_cuts)
    if alt is not None:
        facts['rank1']['in_alternative'] = bool(alt['mask'][facts['rank1']['i']])
    else:
        facts['rank1']['in_alternative'] = False
    for ex in facts['examples']:
        ex['by_scenario'] = per_scenario_wins(win, ex['i'], n_sc)
    facts['rank1']['by_scenario'] = per_scenario_wins(win, facts['rank1']['i'], n_sc)
    facts['level_reach'] = _level_reach(meta, floor_mask)

    facts['mirror'] = _mirror(state, win, meta, atk, floor_rung, mode_cubes, modes)
    facts['score_only'] = [_score_row(r, atk) for r in
                           stage10_score_only(scores, atk, triage, state, ranks)]
    facts['cost'] = _cost(win, meta, facts, state, ranks, contested_cells,
                          reverse_cuts)
    facts['l51'] = _l51_view(state, arm, mode, floor_rung, floor_cell)
    return facts


# ---------------------------------------------------------------------------
# Fact-shaping helpers (small, pure, no blob globals)
# ---------------------------------------------------------------------------

def _blob_date(path):
    base = os.path.basename(path)
    m = re.match(r'(\d{4})(\d{2})(\d{2})_', base)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _mech_facts(mech):
    if mech['kind'] == 'cmp':
        b = mech['build']
        return {'kind': 'cmp', 'line': mech['line'],
                'opp_ivs': b['ivs'], 'opp_level': b['level'],
                'opp_cmp_atk': b['cmp_atk'], 'opp_atk': b['atk'],
                'opp_def': b['def'], 'opp_hp': b['hp']}
    if mech['kind'] == 'breakpoint':
        d = mech['detail']
        return {'kind': 'breakpoint', 'move': d['move'], 'from': d['from'],
                'to': d['to'], 'def_stage': d['def_stage'],
                'atk_stage': d['atk_stage']}
    return {'kind': 'unattributed',
            'line': mech.get('line')}


def _rung_row(r, state, n_iv, atk):
    names = [c['label'] for c in r['cells']]
    shown = names[:NAME_CAP]
    omitted = len(names) - len(shown)
    if len(shown) + omitted != len(names):
        raise GuardError(
            f"G-names: field=Rungs cell={names[0]} printed='{shown}' "
            f"recomputed={len(names)} (blob=- arm=- mode=-)")
    rep = r['cells'][0]
    pr, dp = printed_cut(r['T'], atk, field='Rung', ctx={'cell': names[0]})
    return {
        'T': r['T'], 'printed': pr, 'dp': dp,
        'n_pass': r['n_pass'], 'pool_share': r['pool_share'],
        'names': shown, 'omitted': omitted, 'n_cells': len(names),
        'ranks': [c['rank'] for c in r['cells'][:NAME_CAP]],
        'modes_ok': r['modes_ok'], 'modes_total': r['modes_total'],
        'arms_ok': r['arms_ok'], 'arms_total': r['arms_total'],
        'mech': _mech_facts(rep['mech']),
        'gates_failed': [g for g, ok in r['gates'].items() if not ok],
        'cogates': [],
    }


def _tail_sentence(above_rungs, tail, state, n_iv):
    if not tail:
        return {'n_rungs': 0, 'n_cells': 0, 'max_T': None, 'max_pool': None,
                'examples': []}
    cells = sum(len(r['cells']) for r in tail)
    top = max(tail, key=lambda r: r['T'])
    fat = max(tail, key=lambda r: r['pool_share'])
    return {
        'n_rungs': len(tail), 'n_cells': cells, 'max_T': top['T'],
        'max_pool': fat['pool_share'], 'max_pool_T': fat['T'],
        'max_pool_cell': fat['cells'][0]['label'],
        'examples': [{'T': r['T'], 'label': r['cells'][0]['label'],
                      'pool_share': r['pool_share'],
                      'modes_ok': r['modes_ok']}
                     for r in sorted(tail, key=lambda x: x['T'])[:2]],
    }


def cogate_str(c):
    """'DEF >= 101.40' / 'HP >= 121' -- HP is an integer stat, so print it as one."""
    value = (_n(c['printed']) if c['axis'] == 'hp'
             else fmt(c['printed'], c['dp']))
    return f"{c['axis'].upper()} >= {value}"


def _cogate_row(r):
    return {'axis': r['axis'], 't': r['t'], 'printed': r['printed'],
            'dp': r['dp'], 'n': r['n'], 'cell': r['label'],
            'rank': r['rank'], 'rate_outside': r['rate_outside'],
            'base_rate': r['base_rate']}


def _alt_facts(alt, state, meta, win, n_iv):
    if alt is None:
        return None
    mask = alt['mask']
    same_hp = meta[:, 7] >= alt['hp_cut']
    def_pr, def_dp = printed_cut(alt['def_cut'], meta[same_hp, 6],
                                 field='Alternative target',
                                 ctx={'cell': 'Def x HP rectangle'})
    sp = meta[:, 5] * meta[:, 6] * meta[:, 7]
    cells_won = win[mask].reshape(int(mask.sum()), -1).sum(axis=1)
    return {
        'def_cut': alt['def_cut'], 'def_printed': def_pr, 'def_dp': def_dp,
        'hp_cut': alt['hp_cut'], 'n': alt['n'],
        'share': alt['n'] / n_iv,
        'sp_share_lo': float((sp[mask] / sp.max()).min()),
        'sp_share_hi': float((sp[mask] / sp.max()).max()),
        'atk_lo': float(meta[mask, 5].min()), 'atk_hi': float(meta[mask, 5].max()),
        'guaranteed': [cell_label(state, si, oi) for si, oi in alt['guaranteed']],
        'exclusive': [cell_label(state, si, oi) for si, oi in alt['exclusive']],
        'n_exclusive': len(alt['exclusive']),
        'given_up': [cell_label(state, si, oi) for si, oi in alt['given_up']],
        'n_guaranteed': len(alt['guaranteed']), 'n_given_up': len(alt['given_up']),
        'cells_won': [int(cells_won.min()), int(cells_won.max())],
    }


def _score_row(r, atk):
    pr, dp = printed_cut(r['T'], atk, field='Score only',
                         ctx={'cell': r['label']})
    return {'T': r['T'], 'printed': pr, 'dp': dp,
            'cell': r['label'], 'below': r['below'], 'above': r['above'],
            'won': r['won'], 'rank': r['rank']}


def _mirror(state, win, meta, atk, floor_rung, mode_cubes, modes):
    """Field 11: per shield count against the focal's own pool entry."""
    focal = state['species']
    want = f"{focal} (Shadow)" if state['shadow'] else focal
    names = state['opponent_names']
    if want not in names:
        return None
    oi = names.index(want)
    n_sc = len(state['shield_scenarios'])
    rows = []
    for si in range(n_sc):
        w = win[:, si, oi]
        if floor_rung is None:
            rows.append({'scenario': scenario_label(state, si),
                         'below': None, 'above': None,
                         'rate': float(w.mean())})
            continue
        m = atk >= floor_rung['T']
        rows.append({'scenario': scenario_label(state, si),
                     'below': float(w[~m].mean()) if (~m).any() else 0.0,
                     'above': float(w[m].mean()) if m.any() else 0.0,
                     'rate': float(w.mean())})
    rank1_rows = []
    for m in modes:
        if not m.startswith('rank1'):
            continue
        w_other = mode_cubes[m][0]
        rank1_rows.append({'mode': m,
                           'per_scenario': [int(w_other[:, si, oi].sum())
                                            for si in range(n_sc)]})
    return {'opponent': want, 'oi': oi, 'rows': rows, 'rank1_modes': rank1_rows,
            'seat': ('our side is the optimised row; the mirror opponent '
                     'always baits')}


def _not_claimed(win, triage, cuts, contested_cells, state, ranks, floor_rung,
                 atk):
    claimed = {(c['si'], c['oi']) for c in cuts}
    unclaimed = [c for c in contested_cells if c not in claimed]
    rows = []
    mask = atk >= floor_rung['T'] if floor_rung is not None else np.ones_like(atk, bool)
    for si, oi in unclaimed:
        rate = float(win[mask, si, oi].mean()) if mask.any() else 0.0
        species, _v, _s = parse_opponent_spec(state['opponent_names'][oi])
        rows.append({'cell': cell_label(state, si, oi), 'rank': ranks[oi],
                     'rate_inside_floor': rate,
                     'caveat': any(cv in species for cv in CAVEAT_SPECIES)})
    rows.sort(key=lambda r: (r['rank'] is None, r['rank'] if r['rank'] else 999))
    return {'n': len(unclaimed), 'of': triage['n_contested'], 'rows': rows}


def _cost(win, meta, facts, state, ranks, contested_cells, reverse_cuts):
    """Field 10: reverse cuts, the give-up list, and one exact cell diff."""
    ex = facts['examples']
    if not ex:
        return {'reverse_cuts': len(reverse_cuts), 'diff': None}
    pick = ex[1] if len(ex) > 1 else ex[0]
    i, j = pick['i'], facts['rank1']['i']
    caveat_oi = {oi for oi in range(len(state['opponent_names']))
                 if any(c in parse_opponent_spec(state['opponent_names'][oi])[0]
                        for c in CAVEAT_SPECIES)}
    gained, lost, gained_cav, lost_cav = [], [], [], []
    for si in range(win.shape[1]):
        for oi in range(win.shape[2]):
            a, b = bool(win[i, si, oi]), bool(win[j, si, oi])
            if a == b:
                continue
            row = {'cell': cell_label(state, si, oi), 'rank': ranks[oi]}
            if oi in caveat_oi:
                (gained_cav if a else lost_cav).append(row)
            else:
                (gained if a else lost).append(row)
    key = lambda r: (r['rank'] is None, r['rank'] if r['rank'] else 999)
    gained.sort(key=key)
    lost.sort(key=key)
    return {
        'reverse_cuts': len(reverse_cuts),
        'diff': {'spread': pick['ivs'], 'rule': pick['rule'],
                 'n_gained': len(gained), 'n_lost': len(lost),
                 'n_gained_with_caveat': len(gained) + len(gained_cav),
                 'n_lost_with_caveat': len(lost) + len(lost_cav),
                 'gained': gained, 'lost': lost,
                 'caveat_excluded': len(gained_cav) + len(lost_cav)},
    }


def _level_reach(meta, floor_mask):
    lv_in = meta[floor_mask, 3]
    lv_out = meta[~floor_mask, 3]
    return {
        'median_in': float(np.median(lv_in)) if lv_in.size else None,
        'median_out': float(np.median(lv_out)) if lv_out.size else None,
        'n_in_low': int((lv_in <= 45.0).sum()), 'n_in': int(lv_in.size),
        'n_out_low': int((lv_out <= 45.0).sum()), 'n_out': int(lv_out.size),
    }


def _l51_view(state, arm, mode, floor_rung, floor_cell):
    """D8: the level-51 grid prints its OWN cut for the same cell."""
    try:
        scores51, meta51 = arm_view(state, arm, mode, 'l51')
    except Exception:
        return None
    atk51 = meta51[:, 5]
    w = win_cube(scores51[:, floor_cell['si'], floor_cell['oi']])
    got = clean_cut(atk51, w)
    if got is None:
        return {'clean': False,
                'n_selected_by_l50_literal': int((atk51 >= floor_rung['T']).sum())}
    T51, n51, _prev, _nb = got
    pp = stage7_print_precision(T51, atk51, field='Floor (L51)',
                                ctx={'cell': floor_cell['label']})
    return {'clean': True, 'T': T51, 'printed': pp['printed'], 'dp': pp['dp'],
            'n_pass': n51,
            'n_selected_by_l50_literal': int((atk51 >= floor_rung['T']).sum())}


# ---------------------------------------------------------------------------
# Rendering: small pure helpers that turn the fact dict into ASCII strings.
# Nothing below reads the blob; everything is a template over `facts`.
# ---------------------------------------------------------------------------

MODE_PROSE = {
    'pvpoke': 'PvPoke-default opponent IVs',
    'pvpoke:nobait': 'PvPoke-default opponent IVs, focal never baits',
    'rank1': 'stat-product rank-1 opponent IVs',
    'rank1:nobait': 'stat-product rank-1 opponent IVs, focal never baits',
}


def league_name(league):
    return {'great': 'Great League', 'ultra': 'Ultra League',
            'master': 'Master League', 'little': 'Little League'}.get(
                league, f"{league} league")


def focal_name(header):
    return f"{header['species']} (Shadow)" if header['shadow'] else header['species']


def _n(x):
    return f"{int(x):d}"


def _mech_sentence(mech, shadow, opponent):
    """One sentence naming the closed-form cause, or saying there is none."""
    if mech['kind'] == 'cmp':
        mult = '1.2' if shadow else '1.0'
        a, d, s = mech['opp_ivs']
        return (f"Mechanism: charge-move priority against {opponent}. That "
                f"{opponent} is built at {a}/{d}/{s}, L{fmt(mech['opp_level'], 1)}, "
                f"{fmt(mech['opp_cmp_atk'])} attack; {mult} x "
                f"{fmt(mech['opp_cmp_atk'])} = {fmt(mech['line'])} lands inside "
                f"the boundary.")
    if mech['kind'] == 'breakpoint':
        stage = ''
        if mech['def_stage']:
            stage = f" at opponent Def stage {mech['def_stage']:+d}"
        if mech['atk_stage']:
            stage += f" at focal Atk stage {mech['atk_stage']:+d}"
        return (f"Mechanism: {mech['move']} damage steps {mech['from']} -> "
                f"{mech['to']} across the cut{stage}.")
    return "Mechanism unattributed: no priority line and no damage step sits in the gap."


def _cell_names(row):
    out = list(row['names'])
    if row['omitted']:
        out.append(f"+{row['omitted']} more cells")
    return ', '.join(out)


def _rung_line(row, dp_default=2):
    parts = [f"Atk >= {fmt(row['printed'], row['dp'])}",
             f"{_n(row['n_pass'])} spreads ({pct(row['pool_share'])})",
             _cell_names(row)]
    return '  '.join(parts)


# ---------------------------------------------------------------------------
# The headline verdict
# ---------------------------------------------------------------------------

def build_headline(facts):
    """One or two paragraphs, assembled from computed fields only.

    Every clause is a template over a number already in ``facts``; there is
    no sentence here that is not also a printed field below.
    """
    h = facts['header']
    who = focal_name(h)
    league = league_name(h['league'])
    floor = facts['floor']
    r1 = facts['rank1']
    alt = facts['alternative']
    nc = facts['not_claimed']

    if floor is None:
        return _headline_no_floor(facts, who, league)

    first = []
    first.append(
        f"On this bake of {who} in {league} with {h['arm_label']}, "
        f"{_n(floor['n_pass'])} of {_n(h['n_iv'])} IV spreads "
        f"({pct(floor['pool_share'])} of the grid) reach "
        f"Atk >= {fmt(floor['printed'], floor['dp'])}, and that line is where "
        f"{floor['cell']} turns over: below it "
        f"{_n(floor['n_below_win'])} of {_n(floor['n_below'])} spreads win the "
        f"cell, at or above it all {_n(floor['n_pass'])} do.")
    first.append(_mech_sentence(floor['mech'], h['shadow'],
                                floor['cell'].split(' ', 1)[1]))
    if floor['single_owner']:
        first.append(
            f"After collapsing pool variants this line is owned by one base "
            f"species ({floor['owners'][0]}, rank {floor['rank']}); if it "
            f"leaves the pool the line has no owner.")
    first.append(
        f"It holds in {_n(floor['modes_ok'])} of {_n(floor['modes_total'])} "
        f"opponent-IV settings and {_n(floor['arms_ok'])} of "
        f"{_n(floor['arms_total'])} moveset arms.")

    second = []
    if r1['clears_floor']:
        second.append(
            f"The stat-product rank-1 spread {r1['ivs'][0]}/{r1['ivs'][1]}/"
            f"{r1['ivs'][2]} already clears the line, so there is no trade to "
            f"make at this rung.")
    else:
        second.append(
            f"The stat-product rank-1 spread {r1['ivs'][0]}/{r1['ivs'][1]}/"
            f"{r1['ivs'][2]} at L{fmt(r1['level'], 1)} sits "
            f"{fmt(r1['shortfall'])} attack under it and clears "
            f"{_n(r1['n_cuts_cleared'])} of {_n(r1['n_cuts'])} clean attack "
            f"cuts on this dive; it wins {_n(r1['total_won'])} cells in total.")
    named = facts['rungs_above'][:2]
    if named:
        bits = [f"Atk >= {fmt(r['printed'], r['dp'])} for {_cell_names(r)} "
                f"({_n(r['n_pass'])} spreads, {pct(r['pool_share'])})"
                for r in named]
        second.append("The next clean rungs above it are " + '; '.join(bits) + '.')
    else:
        second.append(
            f"No clean rung above it keeps {pct(RUNG_POOL_MIN, 0)} of the grid.")
    if alt is not None:
        second.append(
            f"The bulk fork is Def >= {fmt(alt['def_printed'], alt['def_dp'])} "
            f"with HP >= {_n(alt['hp_cut'])}: {_n(alt['n'])} spreads "
            f"({pct(alt['share'])}), none of which clears the attack line. It "
            f"guarantees {_n(alt['n_guaranteed'])} contested cells the line "
            f"cannot and gives up {_n(alt['n_given_up'])} the line holds.")
    else:
        second.append(
            f"No Def-and-HP rectangle of {_n(ALT_MIN_MEMBERS)} or more spreads "
            f"guarantees a cell the attack line cannot, so this dive has no "
            f"second target to state.")
    second.append(
        f"{_n(nc['n'])} of {_n(nc['of'])} contested matchups have no clean "
        f"single-stat rule and are not claimed here.")
    return [' '.join(first), ' '.join(second)]


def _headline_no_floor(facts, who, league):
    """D12: a negative that carries its evidence."""
    h = facts['header']
    deg = facts['degradation']
    cc = facts['clean_counts']
    r1 = facts['rank1']
    alt = facts['alternative']
    dirty = facts['dirty_thresholds']

    first = [
        f"On this bake of {who} in {league} with {h['arm_label']}, no attack, "
        f"Def or HP value is a build line: of {_n(facts['triage']['contested'])} "
        f"contested matchups (the rest of the {_n(h['n_iv'])}-spread grid is "
        f"decided the same way by every spread), "
        f"{_n(cc.get('atk', 0))} separate cleanly on attack, "
        f"{_n(cc.get('def', 0))} on Def and {_n(cc.get('hp', 0))} on HP, and "
        f"{deg['sentence']}"]
    if deg['rung'] == 'c':
        failed = ', '.join(f"{g} {v}" for g, v in
                           sorted(deg['counts'].items(), key=lambda kv: -kv[1])[:3])
        first.append(f"The gates that removed the most candidate rungs were "
                     f"{failed}.")

    second = []
    if dirty:
        bits = [f"{d['cell']} at {d['axis'].upper()} >= "
                f"{fmt(d['printed'], d['dp'])}, which misclassifies "
                f"{_n(d['n_wrong'])} of {_n(h['n_iv'])} spreads "
                f"({_n(d['n_win_above'])} of {_n(d['n_above'])} at or above it "
                f"win, {_n(d['n_win_below'])} of {_n(d['n_below'])} below)"
                for d in dirty[:3]]
        second.append("The closest dirty thresholds, which this brief does not "
                      "print as lines, are " + '; '.join(bits) + '.')
    else:
        second.append("No contested cell in the top " + _n(RANK_GATE) +
                      " has a threshold that classifies the grid at all.")
    second.append(
        f"The stat-product rank-1 spread {r1['ivs'][0]}/{r1['ivs'][1]}/"
        f"{r1['ivs'][2]} at L{fmt(r1['level'], 1)} wins "
        f"{_n(r1['total_won'])} cells.")
    if alt is not None:
        second.append(
            f"What the bulk axis does carry is a Def >= "
            f"{fmt(alt['def_printed'], alt['def_dp'])} and HP >= "
            f"{_n(alt['hp_cut'])} rectangle ({_n(alt['n'])} spreads, "
            f"{pct(alt['share'])}), which wins {_n(alt['n_exclusive'])} "
            f"contested cells with every one of its members where at most "
            f"{pct(ALT_MAX_CLEARER_RATE, 0)} of the spreads outside it do: "
            + _cap_list(alt['exclusive']) + ".")
    else:
        second.append(
            f"No Def-and-HP rectangle of {_n(ALT_MIN_MEMBERS)} or more spreads "
            f"guarantees a contested cell either. Build for stat product.")
    return [' '.join(first), ' '.join(second)]


# ---------------------------------------------------------------------------
# The fifteen fields
# ---------------------------------------------------------------------------

def _field(n, title, lines=None, head=None, rows=None, note=None):
    return {'n': n, 'title': title, 'lines': lines or [], 'head': head,
            'rows': rows or [], 'note': note}


def build_fields(facts):
    f = []
    f.append(_f1_header(facts))
    f.append(_f2_floor(facts))
    f.append(_f3_coverage(facts))
    f.append(_f4_rank1(facts))
    f.append(_f5_rungs_above(facts))
    f.append(_f6_rungs_below(facts))
    f.append(_f7_bulk(facts))
    f.append(_f8_alternative(facts))
    f.append(_f9_examples(facts))
    f.append(_f10_cost(facts))
    f.append(_f11_mirror(facts))
    f.append(_f12_score_only(facts))
    f.append(_f13_not_claimed(facts))
    f.append(_f14_how_sure(facts))
    f.append(_f15_provenance(facts))
    return f


def _f1_header(facts):
    h = facts['header']
    lines = [
        f"{focal_name(h)} -- {league_name(h['league'])}",
        f"{h['arm_label']} (arm {h['arm'] + 1} of {h['n_arms']})",
        f"Level view: L{50 if h['level_view'] == 'l50' else 51}. "
        f"Bake {h['blob_date']}. Blob {h['blob']}.",
        f"Opponent pool: {_n(h['pool_size'])} entries"
        + (f" ({h['pool_label']})" if h.get('pool_label') else '') + ". "
        f"Grid: {_n(h['n_iv'])} IV spreads x {_n(h['n_sc'])} shield scenarios.",
        "Opponent-IV settings baked: "
        + '; '.join(MODE_PROSE.get(m, m) for m in h['modes']) + ".",
        f"Rankings snapshot {h['rankings_snapshot']}.",
    ]
    if h['shadow']:
        lines.append("Stats are shadow-effective (attack x1.2 applied); the "
                     "charge-move priority line is not (see Provenance).")
    if facts.get('caps'):
        lines.append(facts['caps']['sentence'])
    return _field(1, 'Header', lines)


def _f2_floor(facts):
    fl = facts['floor']
    h = facts['header']
    if fl is None:
        deg = facts['degradation']
        lines = [deg['sentence']]
        if facts['dirty_thresholds']:
            lines.append("The closest dirty thresholds on this dive, printed "
                         "as evidence and not as lines:")
        rows = [[d['cell'], f"rank {d['rank']}",
                 f"{d['axis'].upper()} >= {fmt(d['printed'], d['dp'])}",
                 _n(d['n_wrong']),
                 f"{_n(d['n_win_above'])} of {_n(d['n_above'])}",
                 f"{_n(d['n_win_below'])} of {_n(d['n_below'])}"]
                for d in facts['dirty_thresholds']]
        return _field(2, 'Floor', lines,
                      head=['cell', 'rank', 'closest split',
                            'spreads on the wrong side', 'wins at/above',
                            'wins below'],
                      rows=rows)
    lines = [
        f"Atk >= {fmt(fl['printed'], fl['dp'])} -- {_n(fl['n_pass'])} of "
        f"{_n(h['n_iv'])} spreads ({pct(fl['pool_share'])}).",
        _mech_sentence(fl['mech'], h['shadow'], fl['cell'].split(' ', 1)[1]),
        f"Owns: {fl['cell']} (rank {fl['rank']}).",
    ]
    if len(fl['dedup_members']) > 1:
        others = [m for m in fl['dedup_members']
                  if m != fl['cell'].split(' ', 1)[1]]
        lines.append("Pool variants collapsing into the same column: "
                     + ', '.join(others) + ".")
    if fl['single_owner']:
        lines.append(
            f"After collapsing pool variants, this cut is owned by one base "
            f"species ({fl['owners'][0]}, rank {fl['rank']}); if it leaves the "
            f"pool the cut has no owner.")
    sb, sa = fl['score_below'], fl['score_above']
    below_txt = (f"every one scores {_n(sb[0])}" if sb[0] == sb[1]
                 else f"they score {_n(sb[0])}-{_n(sb[1])}")
    lines.append(
        f"Below the cut: {_n(fl['n_below_win'])} of {_n(fl['n_below'])} spreads "
        f"win the cell, and {below_txt}. At or above: {_n(fl['n_pass'])} of "
        f"{_n(fl['n_pass'])} win, scoring {_n(sa[0])}-{_n(sa[1])}.")
    if fl.get('energy') and fl['energy']['below_single'] and fl['energy']['above_single']:
        lines.append(
            f"Energy at the end of the fight is {_n(fl['energy']['below'][0])} "
            f"below the cut and {_n(fl['energy']['above'][0])} at or above it: "
            f"one fight on each side, not a plan switch.")
    lines.append(
        f"Holds: clean in {_n(fl['modes_ok'])} of {_n(fl['modes_total'])} "
        f"opponent-IV settings and {_n(fl['arms_ok'])} of "
        f"{_n(fl['arms_total'])} moveset arms."
        + (f" Fails in: {', '.join(fl['modes_fail'])}." if fl['modes_fail'] else ''))
    pm = fl.get('per_mode_cuts') or {}
    bits = []
    for m, v in pm.items():
        bits.append(f"{m} {fmt(v['printed'], v['dp'])}" if v['clean']
                    else f"{m} no clean cut ({pct(v['rate'])} win)")
    if bits:
        lines.append("The same cell's cut in each setting: " + '; '.join(bits) + ".")
    if facts['catch']:
        model = ("Rocket-grunt encounters (this is a shadow; it cannot be "
                 "traded, and the grunt IV floor is NOT verified here -- the "
                 "count below assumes uniform-random IVs over the whole grid)"
                 if h['shadow'] else
                 "Wild catches under uniform-random IVs over the whole grid")
        parts = [f"{_n(c['n'])} for a {pct(c['target'], 0)} chance"
                 for c in facts['catch'] if c['n'] is not None]
        lines.append(f"{model}: " + ', '.join(parts) + ".")
    if fl['other_cells_at_T']:
        lines.append("Other cells turning over at the same value: "
                     + ', '.join(fl['other_cells_at_T']) + ".")
    if fl['mech']['kind'] == 'cmp':
        lines.append(
            "Caveat: this line exists because charge-move priority ignores the "
            "shadow x1.2 multiplier -- our engine's and PvPoke's convention, "
            "not verified against the live game."
            if h['shadow'] else
            "Caveat: charge-move priority compares the shadow-stripped attack "
            "in our engine and in PvPoke; that convention is not verified "
            "against the live game.")
    return _field(2, 'Floor', lines)


def _f3_coverage(facts):
    cov = facts['coverage']
    fl = facts['floor']
    if cov is None:
        why = ("mechanism unattributed; no coverage ladder"
               if fl is not None else "no floor; no coverage ladder")
        return _field(3, 'Coverage', [f"Omitted: {why}."])
    lines = [
        f"What the printed line beats over {cov['opponent']}'s own "
        f"{_n(4096)} spreads. Strict: an exact attack tie counts as NOT "
        f"beaten, because the engine decides a priority tie by seat.",
    ]
    rows = [[r['label'], fmt(r['line']), pct(r['strict']), _n(r['ties']),
             _n(r['focal'])] for r in cov['rows']]
    note = (f"\"focal\" is the count of our spreads clearing that line. The "
            f"printed floor is the PvPoke-default row; it is the line every "
            f"reference tool quotes, not a guarantee against every build of "
            f"that species.")
    return _field(3, 'Coverage', lines,
                  head=['opponent build', 'line', 'beaten (strict)', 'ties',
                        'focal clearers'], rows=rows, note=note)


def _f4_rank1(facts):
    r1 = facts['rank1']
    fl = facts['floor']
    lines = [
        f"Stat-product rank-1 is {r1['ivs'][0]}/{r1['ivs'][1]}/{r1['ivs'][2]} "
        f"at L{fmt(r1['level'], 1)}: {fmt(r1['atk'])} attack / "
        f"{fmt(r1['def'])} Def / {_n(r1['hp'])} HP. It wins "
        f"{_n(r1['total_won'])} cells."]
    if fl is None:
        lines.append("There is no floor on this arm, so there is no line for "
                     "it to be on one side of.")
    elif r1['clears_floor']:
        lines.append("It already clears the floor; there is no trade to make.")
    else:
        lines.append(
            f"It misses the floor by {fmt(r1['shortfall'])} attack and clears "
            f"{_n(r1['n_cuts_cleared'])} of {_n(r1['n_cuts'])} clean attack "
            f"cuts on this dive.")
    lm = r1.get('lowest_missed')
    if lm:
        lines.append(
            f"The lowest material rung it misses is "
            f"{fmt(lm['printed'], lm['dp'])} ({lm['cell']}).")
    lines.append("It is a member of the Alternative target below."
                 if r1.get('in_alternative') else
                 "It is not a member of the Alternative target below.")
    return _field(4, 'Rank-1 check', lines)


def _f5_rungs_above(facts):
    rows_src = facts['rungs_above']
    if facts['floor'] is None:
        return _field(5, 'Rungs above', ["No floor on this arm, so no ladder "
                                         "above one."])
    if not rows_src:
        return _field(5, 'Rungs above',
                      [f"No further clean rung above the floor keeps "
                       f"{pct(RUNG_POOL_MIN, 0)} of the grid."])
    rows = []
    for r in rows_src:
        arm_bits = _other_arm_bits(r.get('per_arm_cuts'), facts['header'])
        rows.append([f"Atk >= {fmt(r['printed'], r['dp'])}", _cell_names(r),
                     f"{_n(r['n_pass'])} ({pct(r['pool_share'])})",
                     f"{_n(r['modes_ok'])}/{_n(r['modes_total'])}",
                     _mech_sentence(r['mech'], facts['header']['shadow'],
                                    r['names'][0].split(' ', 1)[1]),
                     arm_bits])
    lines = []
    t = facts.get('rungs_above_tail')
    if t and t['n_rungs']:
        lines.append(
            f"Beyond {fmt(rows_src[-1]['printed'], rows_src[-1]['dp'])} there "
            f"are {_n(t['n_rungs'])} more clean rungs covering "
            f"{_n(t['n_cells'])} cells, the highest at {fmt(t['max_T'])}; the "
            f"widest of them keeps {pct(t['max_pool'])} of the grid "
            f"({t['max_pool_cell']} at {fmt(t['max_pool_T'])}).")
    cogate_rows, omitted_cg = [], 0
    for r in rows_src:
        for c in r['cogates'][:COGATE_ROW_CAP]:
            cogate_rows.append([f"Atk >= {fmt(r['printed'], r['dp'])}",
                                cogate_str(c), c['cell'],
                                f"rank {c['rank']}" if c['rank'] else 'unranked',
                                _n(c['n']), pct(c['rate_outside'])])
        omitted_cg += max(0, len(r['cogates']) - COGATE_ROW_CAP)
    for d in facts.get('rungs_dropped') or []:
        lines.append(
            f"Dropped from the ladder: {fmt(d['printed'], d['dp'])} "
            f"({d['cell']}, rank {d['rank']}, {pct(d['pool_share'])} of the "
            f"grid) holds in {_n(d['modes_ok'])} of {_n(d['modes_total'])} "
            f"opponent-IV settings.")
    if cogate_rows:
        lines.append(
            f"Co-gates inside a rung: a second-stat condition that, among the "
            f"spreads clearing that rung, wins the named cell every time. "
            f"Sufficient, never necessary -- the last column is what the "
            f"spreads without it still win."
            + (f" {_n(omitted_cg)} further co-gates are not listed."
               if omitted_cg else ''))
    field = _field(5, 'Rungs above', lines,
                   head=['cut', 'cells owned', 'spreads', 'settings',
                         'mechanism', 'other arms'], rows=rows)
    if cogate_rows:
        field['extra_title'] = 'Co-gates inside a rung'
        field['extra_head'] = ['rung', 'co-gate', 'cell', 'rank',
                               'spreads holding it', 'win rate without it']
        field['extra_rows'] = cogate_rows
    return field


def _other_arm_bits(per_arm, header):
    if not per_arm:
        return '-'
    bits = []
    for name, v in per_arm.items():
        if name == header['arm_label']:
            continue
        bits.append(fmt(v['printed'], v['dp']) if v['clean']
                    else f"dirty ({pct(v['rate'])})")
    return '; '.join(bits) if bits else '-'


def _f6_rungs_below(facts):
    rows_src = [r for r in facts['rungs_below']
                if facts['floor'] is None or r['T'] < facts['floor']['T']]
    if not rows_src:
        return _field(6, 'Rungs below', ["No material rung below the floor."])
    lines = [f"Clean cuts that {SHOULD_ALLOWED_PHRASE}: they hold between "
             f"{pct(MATERIAL_LO, 0)} and {pct(MATERIAL_HI, 0)} of the grid."]
    rows = [[f"Atk >= {fmt(r['printed'], r['dp'])}", _cell_names(r),
             f"{_n(r['n_pass'])} ({pct(r['pool_share'])})",
             f"{_n(r['modes_ok'])}/{_n(r['modes_total'])}",
             _mech_sentence(r['mech'], facts['header']['shadow'],
                            r['names'][0].split(' ', 1)[1])]
            for r in rows_src]
    return _field(6, 'Rungs below', lines,
                  head=['cut', 'cells owned', 'spreads', 'settings',
                        'mechanism'], rows=rows)


def _f7_bulk(facts):
    b = facts['bulk']
    lines = []
    if b['clean_def'] == 0 and b['clean_hp'] == 0:
        lines.append(
            f"No clean Def or HP cut exists on this dive "
            f"({_n(b.get('clean_def', 0))} of "
            f"{_n(b.get('contested', facts['triage']['contested']))} contested "
            f"cells on Def, {_n(b.get('clean_hp', 0))} on HP; "
            f"{_n(b.get('clean_atk', facts['clean_counts'].get('atk', 0)))} "
            f"are attack cuts).")
    else:
        lines.append(
            f"Clean cuts by axis: {_n(facts['clean_counts'].get('atk', 0))} on "
            f"attack, {_n(b['clean_def'])} on Def, {_n(b['clean_hp'])} on HP.")
    if not b['frontier']:
        return _field(7, 'Bulk', lines)
    lines.append("Inside the floor the trade is HP against Def -- the highest "
                 "Def attained at each HP among the clearers:")
    rows = [[_n(x['hp']), fmt(x['max_def']), _n(x['n'])] for x in b['frontier']]
    if b.get('cells_won_range'):
        lines.append(f"Within the clearers, cells won in total run "
                     f"{_n(b['cells_won_range'][0])}-"
                     f"{_n(b['cells_won_range'][1])}.")
    note = None
    if b['cogates']:
        note = ("Co-gates inside the floor (every clearer in the sub-rectangle "
                "wins the cell; the rate outside it is printed beside): "
                + '; '.join(
                    f"{cogate_str(c)} ({_n(c['n'])} clearers) wins "
                    f"{c['cell']} rank {c['rank']}, "
                    f"against {pct(c['rate_outside'])} without it"
                    for c in b['cogates']) + ". These are sufficient "
                "conditions, never necessary ones.")
    return _field(7, 'Bulk', lines, head=['HP', 'highest Def attained',
                                          'spreads'], rows=rows, note=note)


def _f8_alternative(facts):
    alt = facts['alternative']
    has_floor = facts['floor'] is not None
    if alt is None:
        return _field(8, 'Alternative target',
                      [f"No bulk rectangle of {_n(ALT_MIN_MEMBERS)} or more "
                       f"spreads guarantees a contested cell that "
                       f"{'the floor' if has_floor else 'the rest of the grid'} "
                       f"cannot."])
    lines = [
        f"Def >= {fmt(alt['def_printed'], alt['def_dp'])} and HP >= "
        f"{_n(alt['hp_cut'])}: {_n(alt['n'])} spreads ({pct(alt['share'])}), "
        f"stat product {pct(alt['sp_share_lo'])} to {pct(alt['sp_share_hi'])} "
        f"of rank-1, attack {fmt(alt['atk_lo'])}-{fmt(alt['atk_hi'])}."]
    if has_floor:
        lines.append(
            f"Rule: among (Def, HP) rectangles with at least "
            f"{_n(ALT_MIN_MEMBERS)} members and no floor clearer, the one "
            f"guaranteeing the most contested cells the floor cannot (won by "
            f"every member, by at most {pct(ALT_MAX_CLEARER_RATE, 0)} of "
            f"clearers); ties broken by member count. The printed cuts are the "
            f"least attained values among the members.")
        lines.append(
            f"Guarantees {_n(alt['n_guaranteed'])} cells the floor does not: "
            + _cap_list(alt['guaranteed']) + ".")
        if alt['given_up']:
            lines.append(
                f"Gives up {_n(alt['n_given_up'])} cells the floor guarantees: "
                + _cap_list(alt['given_up']) + ".")
        else:
            lines.append("It gives up no cell the floor guarantees.")
        lines.append(
            f"Measured against the whole grid instead of against the floor, "
            f"{_n(alt['n_exclusive'])} of those cells are won by at most "
            f"{pct(ALT_MAX_CLEARER_RATE, 0)} of the spreads outside the "
            f"rectangle" + (": " + _cap_list(alt['exclusive']) + "."
                            if alt['exclusive'] else "; the "
                            f"{_n(alt['n_guaranteed'])}-cell claim above is "
                            "against the floor clearers, not against every "
                            "spread."))
        lines.append("No spread satisfies both this rectangle and the attack "
                     "floor.")
    else:
        lines.append(
            f"There is no attack floor on this arm, so there is nothing for "
            f"the rectangle to be disjoint from. Rule: among (Def, HP) "
            f"rectangles with at least {_n(ALT_MIN_MEMBERS)} members, the one "
            f"winning the most contested cells with EVERY member that at most "
            f"{pct(ALT_MAX_CLEARER_RATE, 0)} of the spreads outside it win; "
            f"ties broken by member count. The printed cuts are the least "
            f"attained values among the members.")
        lines.append(
            f"Wins {_n(alt['n_exclusive'])} contested cells that way: "
            + _cap_list(alt['exclusive']) + ".")
    lines.append(f"Members win {_n(alt['cells_won'][0])}-"
                 f"{_n(alt['cells_won'][1])} cells in total.")
    return _field(8, 'Alternative target', lines)


def _cap_list(names, cap=LIST_CAP):
    """Comma list, truncated with an exact remainder count (G-names)."""
    if len(names) <= cap:
        return ', '.join(names)
    return ', '.join(names[:cap]) + f", and {len(names) - cap} more"


def _f9_examples(facts):
    ex = facts['examples']
    if not ex:
        return _field(9, 'Example spreads', ["No floor on this arm, so there "
                                             "is no set of clearers to draw "
                                             "examples from."])
    rows = []
    for e in ex:
        rows.append([e['rule'],
                     f"{e['ivs'][0]}/{e['ivs'][1]}/{e['ivs'][2]}",
                     f"L{fmt(e['level'], 1)}",
                     f"{fmt(e['atk'])} / {fmt(e['def'])} / {_n(e['hp'])}",
                     f"{pct(e['sp_share'], 2)} (#{_n(e['sp_rank'])})",
                     _n(e['cells']), _n(e['total'])])
    lines = ["Existence proofs; each selection rule is printed with its spread."]
    sc = ['0v0', '0v1', '0v2', '1v0', '1v1', '1v2', '2v0', '2v1', '2v2']
    tail_rows = []
    r1 = facts['rank1']
    tail_rows.append([f"rank-1 {r1['ivs'][0]}/{r1['ivs'][1]}/{r1['ivs'][2]}"]
                     + [_n(v) for v in r1['by_scenario']] + [_n(r1['total_won'])])
    for e in ex:
        tail_rows.append([f"{e['ivs'][0]}/{e['ivs'][1]}/{e['ivs'][2]}"]
                         + [_n(v) for v in e['by_scenario']] + [_n(e['total'])])
    lr = facts.get('level_reach')
    note = None
    if lr and lr['median_in'] is not None:
        note = (f"Clearers reach the CP cap at a median level of "
                f"L{fmt(lr['median_in'], 1)} ({_n(lr['n_in_low'])} of "
                f"{_n(lr['n_in'])} at L45.0 or below) against "
                f"L{fmt(lr['median_out'], 1)} below the floor "
                f"({_n(lr['n_out_low'])} of {_n(lr['n_out'])}).")
    fields = _field(9, 'Example spreads', lines,
                    head=['rule', 'IVs', 'level', 'Atk / Def / HP',
                          'stat product', 'contested cells', 'all cells'],
                    rows=rows, note=note)
    fields['extra_head'] = ['spread'] + sc + ['total']
    fields['extra_rows'] = tail_rows
    fields['extra_title'] = 'Cells won by shield scenario'
    return fields


def _f10_cost(facts):
    c = facts['cost']
    lines = []
    if c['reverse_cuts'] == 0:
        lines.append("This test finds no reverse single-stat clean cut: no "
                     "cell on this dive is won by every LOW spread and lost by "
                     "every high one.")
    else:
        lines.append(f"{_n(c['reverse_cuts'])} reverse single-stat clean cuts "
                     f"exist (cells won by the low side of a stat).")
    d = c.get('diff')
    if not d:
        return _field(10, 'Cost', lines)
    lines.append(
        f"The cost as an exact cell diff -- {d['spread'][0]}/{d['spread'][1]}/"
        f"{d['spread'][2]} ({d['rule']}) against rank-1: "
        f"{_n(d['n_gained'])} cells gained, {_n(d['n_lost'])} lost.")
    if d['caveat_excluded']:
        lines.append(
            f"{_n(d['caveat_excluded'])} cells are excluded from that diff "
            f"({', '.join(CAVEAT_SPECIES)}: open engine divergence against "
            f"PvPoke, see the mechanics note); with them the diff is "
            f"{_n(d['n_gained_with_caveat'])} / "
            f"{_n(d['n_lost_with_caveat'])}.")
    top_lost = [r for r in d['lost'] if r['rank'] and r['rank'] <= 20]
    top_gain = [r for r in d['gained'] if r['rank'] and r['rank'] <= 20]
    if top_lost:
        lines.append("Lost, top-20 opponents: "
                     + ', '.join(f"{r['cell']} (rank {r['rank']})"
                                 for r in top_lost) + ".")
    if top_gain:
        lines.append("Gained, top-20 opponents: "
                     + ', '.join(f"{r['cell']} (rank {r['rank']})"
                                 for r in top_gain) + ".")
    return _field(10, 'Cost', lines)


def _f11_mirror(facts):
    m = facts['mirror']
    if m is None:
        return _field(11, 'Mirror', ["Mirror not in pool."])
    lines = [f"Against the pool's own {m['opponent']} entry. Seat: {m['seat']}."]
    rows = []
    for r in m['rows']:
        if r['below'] is None:
            rows.append([r['scenario'], '-', '-', pct(r['rate'])])
        else:
            rows.append([r['scenario'], pct(r['below']), pct(r['above']),
                         pct(r['rate'])])
    for rm in m['rank1_modes']:
        lines.append(
            f"Against a mirror built at {MODE_PROSE.get(rm['mode'], rm['mode'])}, "
            f"the count of our spreads (of {_n(facts['header']['n_iv'])}) that "
            f"win, by shield scenario 0v0 through 2v2: "
            + ' '.join(_n(v) for v in rm['per_scenario']) + ".")
    return _field(11, 'Mirror', lines,
                  head=['shields', 'win rate below the floor',
                        'win rate at/above', 'win rate over the whole grid'],
                  rows=rows)


def _f12_score_only(facts):
    rows_src = facts['score_only']
    if not rows_src:
        return _field(12, 'Changes the score, not the matchup', ["None."])
    lines = [f"Cells won (or lost) by every spread where the battle score "
             f"still steps by at least {_n(SCORE_STEP_MIN)} at one attainable "
             f"attack value."]
    shown = rows_src[:SCORE_ROW_CAP]
    rows = [[f"Atk >= {fmt(r['printed'], r['dp'])}", r['cell'],
             f"rank {r['rank']}" if r['rank'] else 'unranked',
             f"{_n(r['below'])} -> {_n(r['above'])}",
             'won on both sides' if r['won'] else 'lost on both sides']
            for r in shown]
    if len(rows_src) > len(shown):
        lines.append(f"{_n(len(shown))} of {_n(len(rows_src))} steps are "
                     f"listed, largest first; {_n(len(rows_src) - len(shown))} "
                     f"more are not.")
    return _field(12, 'Changes the score, not the matchup', lines,
                  head=['value', 'cell', 'rank', 'score step', 'outcome'],
                  rows=rows)


def _f13_not_claimed(facts):
    nc = facts['not_claimed']
    fl = facts['floor']
    where = "inside the floor" if fl is not None else "over the whole grid"
    lines = [f"{_n(nc['n'])} of {_n(nc['of'])} contested matchups have no "
             f"clean single-stat rule and are not claimed."]
    top = [r for r in nc['rows'] if r['rank'] and r['rank'] <= RANK_GATE][:6]
    rows = [[r['cell'], f"rank {r['rank']}", pct(r['rate_inside_floor']),
             'engine divergence; see the mechanics note' if r['caveat'] else '']
            for r in top]
    head = ['cell', 'rank', f"win rate {where}", 'note']
    return _field(13, 'Not claimed', lines, head=head, rows=rows)


def _f14_how_sure(facts):
    h = facts['header']
    fl = facts['floor']
    cc = facts['clean_counts']
    lines = [
        f"{_n(cc.get('atk', 0))} clean attack cuts, {_n(cc.get('def', 0))} on "
        f"Def, {_n(cc.get('hp', 0))} on HP, over "
        f"{_n(facts['triage']['contested'])} contested cells "
        f"({_n(facts['triage']['all_win'])} cells are won by every spread, "
        f"{_n(facts['triage']['all_lose'])} lost by every spread).",
    ]
    if facts['triage']['degenerate']:
        dd = facts['triage']['degenerate_detail']
        bits = [f"{s} ({_n(dd[s][0])} contested, {_n(dd[s][1])} distinct "
                f"win patterns)" for s in facts['triage']['degenerate']]
        lines.append("Scenarios flagged degenerate and barred from carrying a "
                     "floor: " + ', '.join(bits) + ".")
    if fl is not None:
        lines.append(
            f"The floor's partition is exact in {_n(fl['modes_ok'])} of "
            f"{_n(fl['modes_total'])} opponent-IV settings and "
            f"{_n(fl['arms_ok'])} of {_n(fl['arms_total'])} arms.")
        if fl['single_owner']:
            lines.append(
                f"It is owned by one base species ({fl['owners'][0]}); if it "
                f"leaves the pool the floor has no owner.")
        cov = facts['coverage']
        if cov:
            r1row = cov['rows'][0]
            dflt = cov['rows'][1]
            lines.append(
                f"Both baked opponent cohorts sit low in "
                f"{cov['opponent']}'s own attack grid "
                f"({pct(r1row['strict'])} and {pct(dflt['strict'])} of it "
                f"strictly beaten), so \"{_n(fl['modes_ok'])} of "
                f"{_n(fl['modes_total'])} settings\" is not robustness against "
                f"attack-weighted opponent builds; the coverage ladder is.")
    l51 = facts.get('l51')
    if l51:
        if l51['clean']:
            lines.append(
                f"The level-51 view has its own cut for the same cell: "
                f"{fmt(l51['printed'], l51['dp'])} with {_n(l51['n_pass'])} "
                f"spreads clearing, where the L50 literal applied to the L51 "
                f"grid would select {_n(l51['n_selected_by_l50_literal'])}.")
        else:
            lines.append("The same cell has no clean cut in the level-51 view.")
    lines.append(
        "Not measured here: opponent IVs outside the baked cohorts, "
        "post-match HP and shields, XL or dust cost, and any live-game check "
        "of the priority convention.")
    return _field(14, 'How sure', lines)


def _f15_provenance(facts):
    h = facts['header']
    lines = [
        "Every number in this section is a clean cut: a stat value where every "
        "spread at or above it wins the named cell and no spread below it "
        "does. The win predicate is gopvpsim.battle.is_win (score > "
        f"{_n(WIN_RATING)}; {_n(WIN_RATING)} itself is a tie, not a win).",
        "That is stricter than the two numbers the dive page prints for the "
        "same opponent: the Threats \"flips at\" boundary (a 75/25 gate, so "
        "spreads on the passing side can still lose) and the Matchup clusters "
        "single-stat split (the most accurate one, misclassifications "
        "allowed).",
        "Priority ties: the coverage ladder counts an exact attack tie as NOT "
        "beaten. The engine is seat-dependent on an exact tie, so a tied line "
        "is not a guarantee in either direction.",
        f"Ranks and opponent builds are read live from the "
        f"{h['rankings_snapshot']} rankings snapshot and the current "
        f"gamemaster; this blob carries no gamemaster stamp, so the render is "
        f"a function of the blob plus those two live reads.",
        "Auto-derived: this section is generated by scripts/deep_dive_brief.py "
        "from the replay blob. No human prose is in it.",
    ]
    return _field(15, 'Provenance', lines)


# ---------------------------------------------------------------------------
# Stage 15 -- render gates. Three of these are build-breakers and raise
# GuardError in the message format the plan fixes, so an overnight corpus
# render says exactly what broke and where.
# ---------------------------------------------------------------------------

MEANS_WORDS = ('mean', 'means', 'average', 'averages', 'averaged')


def field_strings(field):
    """Every reader-facing string in one rendered field."""
    out = [field['title']] + list(field['lines'])
    for key in ('head', 'extra_head'):
        if field.get(key):
            out.extend(field[key])
    for key in ('rows', 'extra_rows'):
        for row in field.get(key) or []:
            out.extend(str(c) for c in row)
    if field.get('note'):
        out.append(field['note'])
    if field.get('extra_title'):
        out.append(field['extra_title'])
    return out


def gate_words(blocks, ctx):
    """G-words: banned adjectives and comparatives, ASCII only. G-means too."""
    joined = '\n'.join(blocks)
    if not joined.isascii():
        bad = next(ch for ch in joined if not ch.isascii())
        guard_fail('G-words', 'all', '-', bad, f"U+{ord(bad):04X} is not ASCII",
                   ctx)
    scrub = joined
    for phrase in BANNED_EXEMPT_PHRASES:
        scrub = scrub.replace(phrase, 'LEAGUE_NAME')
    n_fixed = scrub.count(SHOULD_ALLOWED_PHRASE)
    if n_fixed > 1:
        guard_fail('G-words', 'all', '-', SHOULD_ALLOWED_PHRASE,
                   f"the one allowed fixed phrase appears {n_fixed} times", ctx)
    scrub = scrub.replace(SHOULD_ALLOWED_PHRASE, 'FIXED_PHRASE')
    for word in BANNED_WORDS:
        m = re.search(r'\b' + word + r'\b', scrub, re.IGNORECASE)
        if m:
            guard_fail('G-words', 'all', '-', m.group(0),
                       f"banned word '{word}'", ctx)
    for word in MEANS_WORDS:
        m = re.search(r'\b' + word + r'\b', scrub, re.IGNORECASE)
        if m:
            guard_fail('G-means', 'all', '-', m.group(0),
                       f"banned word '{word}'", ctx)


def gate_names(facts, ctx):
    """G-names: names printed + '+N more' add up to the cells a row owns."""
    for key in ('rungs_above', 'rungs_below'):
        for row in facts.get(key) or []:
            total = len(row['names']) + row['omitted']
            if total != row['n_cells']:
                guard_fail('G-names', key, row['names'][0] if row['names'] else '-',
                           f"{len(row['names'])} names + {row['omitted']} more",
                           row['n_cells'], ctx)
            if len(row['names']) > NAME_CAP:
                guard_fail('G-names', key, row['names'][0],
                           f"{len(row['names'])} names", f"cap {NAME_CAP}", ctx)
    alt = facts.get('alternative')
    if alt is not None:
        for k, n in (('guaranteed', 'n_guaranteed'), ('given_up', 'n_given_up')):
            if len(alt[k]) != alt[n]:
                guard_fail('G-names', 'Alternative target', k,
                           f"{len(alt[k])} names", alt[n], ctx)
    tail = facts.get('rungs_above_tail')
    if tail and tail['n_rungs'] and tail['n_cells'] < tail['n_rungs']:
        guard_fail('G-names', 'Rungs above', 'tail',
                   f"{tail['n_rungs']} rungs", f"{tail['n_cells']} cells", ctx)


def gate_recompute(state, arm, blob_path, mode, level, facts, ctx):
    """G-recompute: every printed number re-derived from the arrays again.

    This deliberately re-reads the cube and re-does the arithmetic instead of
    trusting anything in ``facts``, so a corrupted fact -- a wrong count, a
    wrong percentage, a wrong stat value -- is caught here rather than
    rendered.
    """
    scores, meta = arm_view(state, arm, mode, level)
    win = win_cube(scores)
    atk, dfn, hp = stat_planes(meta)
    n_iv = scores.shape[0]

    def check(field, cell, printed, recomputed, tol=0.0):
        if isinstance(printed, float) or isinstance(recomputed, float):
            if abs(float(printed) - float(recomputed)) > tol:
                guard_fail('G-recompute', field, cell, printed, recomputed, ctx)
        elif printed != recomputed:
            guard_fail('G-recompute', field, cell, printed, recomputed, ctx)

    nwin = win.sum(axis=0)
    check('Header', '-', facts['header']['n_iv'], int(n_iv))
    check('How sure', '-', facts['triage']['all_win'], int((nwin == n_iv).sum()))
    check('How sure', '-', facts['triage']['all_lose'], int((nwin == 0).sum()))
    check('How sure', '-', facts['triage']['contested'],
          int(((nwin > 0) & (nwin < n_iv)).sum()))

    fl = facts['floor']
    if fl is not None:
        si, oi = _cell_index(state, fl['cell'])
        check('Floor', fl['cell'], fl['n_pass'], int((atk >= fl['T']).sum()))
        check('Floor', fl['cell'], fl['pool_share'],
              float((atk >= fl['T']).sum()) / n_iv, tol=1e-12)
        check('Floor', fl['cell'], fl['n_pass'],
              int((atk >= fl['printed']).sum()))
        below = atk < fl['T']
        check('Floor', fl['cell'], fl['n_below'], int(below.sum()))
        check('Floor', fl['cell'], fl['n_below_win'],
              int(win[below, si, oi].sum()))
        check('Floor', fl['cell'], fl['score_below'][0],
              int(scores[below, si, oi].min()))
        check('Floor', fl['cell'], fl['score_above'][0],
              int(scores[~below, si, oi].min()))

    for key in ('rungs_above', 'rungs_below'):
        for row in facts.get(key) or []:
            check(key, row['names'][0], row['n_pass'],
                  int((atk >= row['T']).sum()))
            check(key, row['names'][0], row['n_pass'],
                  int((atk >= row['printed']).sum()))
            check(key, row['names'][0], row['pool_share'],
                  float((atk >= row['T']).sum()) / n_iv, tol=1e-12)

    cov = facts.get('coverage')
    if cov:
        for row in cov['rows']:
            check('Coverage', row['label'], row['focal'],
                  int((atk >= row['line']).sum()))

    alt = facts.get('alternative')
    if alt is not None:
        mask = (dfn >= alt['def_cut']) & (hp >= alt['hp_cut'])
        check('Alternative target', 'Def x HP rectangle', alt['n'],
              int(mask.sum()))
        pmask = (dfn >= alt['def_printed']) & (hp >= alt['hp_cut'])
        check('Alternative target', 'Def x HP rectangle (printed)', alt['n'],
              int(pmask.sum()))
        check('Alternative target', 'Def x HP rectangle', alt['share'],
              float(mask.sum()) / n_iv, tol=1e-12)
        for label in alt['guaranteed']:
            si, oi = _cell_index(state, label)
            if not win[mask, si, oi].all():
                guard_fail('G-recompute', 'Alternative target', label,
                           'guaranteed',
                           f"{int(win[mask, si, oi].sum())} of {int(mask.sum())}",
                           ctx)

    for ex in facts.get('examples') or []:
        i = ex['i']
        check('Example spreads', f"{ex['ivs']}", ex['atk'], float(meta[i, 5]),
              tol=1e-9)
        check('Example spreads', f"{ex['ivs']}", ex['def'], float(meta[i, 6]),
              tol=1e-9)
        check('Example spreads', f"{ex['ivs']}", ex['hp'], int(meta[i, 7]))
        check('Example spreads', f"{ex['ivs']}", ex['total'],
              int(win[i].sum()))

    for fr in (facts.get('bulk') or {}).get('frontier') or []:
        sel = (atk >= fl['T']) & (hp == fr['hp'])
        check('Bulk', f"HP {fr['hp']}", fr['max_def'], float(dfn[sel].max()),
              tol=1e-9)
        check('Bulk', f"HP {fr['hp']}", fr['n'], int(sel.sum()))

    nc = facts['not_claimed']
    mask = (atk >= fl['T']) if fl is not None else np.ones(n_iv, bool)
    for row in nc['rows'][:8]:
        si, oi = _cell_index(state, row['cell'])
        check('Not claimed', row['cell'], row['rate_inside_floor'],
              float(win[mask, si, oi].mean()), tol=1e-12)

    r1 = facts['rank1']
    check('Rank-1 check', 'rank-1', r1['total_won'], int(win[r1['i']].sum()))
    check('Rank-1 check', 'rank-1', r1['atk'], float(meta[r1['i'], 5]),
          tol=1e-9)


def _cell_index(state, label):
    """('0v1 Annihilape') -> (scenario index, opponent index)."""
    scen, name = label.split(' ', 1)
    si = [i for i, p in enumerate(state['shield_scenarios'])
          if f"{p[0]}v{p[1]}" == scen][0]
    oi = state['opponent_names'].index(name)
    return si, oi


# ---------------------------------------------------------------------------
# The evidence-and-guards block (collapsed on the page)
# ---------------------------------------------------------------------------

def build_evidence(facts):
    """Band constants, per-mode cuts, the ladder rung reached, sensitivity."""
    c = facts['constants']
    fl = facts['floor']
    lines = [
        f"Decision band for the floor (D1): the lowest eligible rung whose "
        f"clearer pool sits inside [{pct(c['decision_band'][0], 0)}, "
        f"{pct(c['decision_band'][1], 0)}] of the grid. Materiality band for a "
        f"rung: [{pct(c['material'][0], 0)}, {pct(c['material'][1], 0)}]. A "
        f"rung needs at least {_n(c['min_attained_below'])} distinct attainable "
        f"values below it, an opponent of rank {_n(c['rank_gate'])} or better, "
        f"a win rate at or above the cut of at least "
        f"{pct(c['direction_min_above'], 0)} in every setting, and a "
        f"closed-form mechanism.",
        f"Co-gate sub-rectangles need {pct(c['cogate_min_share'], 0)} of the "
        f"grid; the alternative target needs {_n(c['alt_min_members'])} "
        f"members; a score-only step needs {_n(c['score_step_min'])} points. "
        f"These constants are calibrated on one species and are parameters of "
        f"the stage that uses them, not tuned per dive.",
        f"Degradation ladder: rung reached = {facts['degradation']['rung']}."
        + (f" {facts['degradation']['sentence']}"
           if facts['degradation']['sentence'] else ''),
    ]
    if facts.get('caps'):
        lines.append("G-trivial: " + facts['caps']['sentence'])
    gt = facts['gate_tally']
    if gt['failed']:
        lines.append(
            f"Of {_n(gt['n_cuts'])} clean cuts, {_n(gt['n_eligible'])} clear "
            f"every gate. Gate failures: "
            + ', '.join(f"{g} {_n(v)}" for g, v in
                        sorted(gt['failed'].items(), key=lambda kv: -kv[1]))
            + ".")
    rows = []
    for s in facts['sensitivity']:
        rows.append([f"[{pct(s['band'][0], 0)}, {pct(s['band'][1], 0)}]",
                     fmt(s['T']) if s['T'] is not None else 'no floor',
                     s['cell'] or '-'])
    if fl is not None:
        pm = fl.get('per_mode_cuts') or {}
        for m, v in pm.items():
            lines.append(
                f"Floor cell in {m}: "
                + (f"clean cut {fmt(v['printed'], v['dp'])}, "
                     f"{_n(v['n_pass'])} spreads"
                   if v['clean'] else f"no clean cut, {pct(v['rate'])} win"))
        pa = fl.get('per_arm_cuts') or {}
        for a, v in pa.items():
            lines.append(
                f"Floor cell on arm '{a}': "
                + (f"clean cut {fmt(v['printed'], v['dp'])}, "
                     f"{_n(v['n_pass'])} spreads"
                   if v['clean'] else f"no clean cut, {pct(v['rate'])} win"))
    if facts['dirty_thresholds']:
        lines.append(
            "Closest dirty thresholds on cells with no clean rule: "
            + '; '.join(f"{d['cell']} {d['axis'].upper()} >= "
                        f"{fmt(d['printed'], d['dp'])} "
                        f"({_n(d['n_wrong'])} spreads on the wrong side)"
                        for d in facts['dirty_thresholds']) + ".")
    return {'lines': lines,
            'head': ['band', 'floor it selects', 'cell'], 'rows': rows}


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

CSS = """
:root { color-scheme: light; }
body { margin: 0; background: #f7f7f5; color: #16181d;
       font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
       Helvetica, Arial, sans-serif; }
.wrap { max-width: 61rem; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 1.45rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 0 0 2px; }
.sub { color: #5c6270; margin: 0 0 20px; font-size: .9rem; }
.arm { background: #fff; border: 1px solid #dcdee3; border-radius: 8px;
       padding: 20px 22px; margin: 0 0 28px; }
.headline p { font-size: 1.02rem; margin: 0 0 12px; }
.headline { border-left: 3px solid #2f6f4f; padding-left: 14px;
            margin: 14px 0 22px; }
.field { margin: 0 0 18px; }
.field h3 { font-size: .78rem; letter-spacing: .09em; text-transform: uppercase;
            color: #5c6270; margin: 0 0 6px; font-weight: 600; }
.field p { margin: 0 0 6px; }
.note { color: #5c6270; font-size: .9rem; }
.tw { overflow-x: auto; margin: 8px 0; }
table { border-collapse: collapse; font-size: .88rem; min-width: 100%; }
th, td { text-align: left; padding: 4px 10px 4px 0; vertical-align: top;
         border-bottom: 1px solid #eceef1; white-space: nowrap; }
th { color: #5c6270; font-weight: 600; }
td.wrapcell, th.wrapcell { white-space: normal; min-width: 16rem; }
details { margin-top: 18px; border-top: 1px solid #dcdee3; padding-top: 12px; }
summary { cursor: pointer; font-size: .82rem; color: #5c6270;
          letter-spacing: .05em; text-transform: uppercase; font-weight: 600; }
details p { font-size: .9rem; margin: 8px 0; }
code { font: 13px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; }
"""


def _esc(s):
    return html.escape(str(s), quote=True)


def _table_html(head, rows, wrap_cols=()):
    if not rows:
        return ''
    out = ['<div class="tw"><table>']
    if head:
        cells = ''.join(
            f'<th class="wrapcell">{_esc(h)}</th>' if i in wrap_cols
            else f'<th>{_esc(h)}</th>' for i, h in enumerate(head))
        out.append(f'<thead><tr>{cells}</tr></thead>')
    out.append('<tbody>')
    for row in rows:
        cells = ''.join(
            f'<td class="wrapcell">{_esc(c)}</td>' if i in wrap_cols
            else f'<td>{_esc(c)}</td>' for i, c in enumerate(row))
        out.append(f'<tr>{cells}</tr>')
    out.append('</tbody></table></div>')
    return ''.join(out)


WRAP_COLUMNS = {'Rungs above': (1, 4, 5), 'Rungs below': (1, 4),
                'Example spreads': (0,), 'Not claimed': (0, 3),
                'Changes the score, not the matchup': (1,),
                'Floor': (0, 2)}


def field_html(field):
    out = [f'<div class="field"><h3>{field["n"]}. {_esc(field["title"])}</h3>']
    for line in field['lines']:
        out.append(f'<p>{_esc(line)}</p>')
    out.append(_table_html(field.get('head'), field.get('rows'),
                           WRAP_COLUMNS.get(field['title'], ())))
    if field.get('extra_rows'):
        out.append(f'<p class="note">{_esc(field["extra_title"])}</p>')
        out.append(_table_html(field.get('extra_head'), field['extra_rows']))
    if field.get('note'):
        out.append(f'<p class="note">{_esc(field["note"])}</p>')
    out.append('</div>')
    return ''.join(out)


def arm_html(facts, headline, fields, evidence):
    h = facts['header']
    out = [f'<section class="arm"><h2>Build brief -- {_esc(focal_name(h))}, '
           f'{_esc(league_name(h["league"]))}</h2>',
           f'<p class="sub">{_esc(h["arm_label"])} '
           f'(arm {h["arm"] + 1} of {h["n_arms"]})</p>',
           '<div class="headline">']
    for para in headline:
        out.append(f'<p>{_esc(para)}</p>')
    out.append('</div>')
    for field in fields:
        out.append(field_html(field))
    out.append('<details><summary>Evidence and guards</summary>')
    for line in evidence['lines']:
        out.append(f'<p>{_esc(line)}</p>')
    out.append(_table_html(evidence['head'], evidence['rows']))
    out.append('</details></section>')
    return ''.join(out)


def document_html(title, subtitle, sections):
    """Self-contained page. No render timestamp: two renders are byte-equal."""
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{_esc(title)}</title><style>{CSS}</style></head><body>'
        f'<div class="wrap"><h1>{_esc(title)}</h1>'
        f'<p class="sub">{_esc(subtitle)}</p>'
        + ''.join(sections) +
        '</div></body></html>\n')


# ---------------------------------------------------------------------------
# One arm, end to end
# ---------------------------------------------------------------------------

def render_arm(state, arm, blob_path, mode='pvpoke', level='l50'):
    """Compute + render one arm. Returns (facts, html fragment)."""
    ctx = {'blob': os.path.basename(blob_path), 'arm': arm, 'mode': mode}
    facts = compute_brief(state, arm, blob_path, mode=mode, level=level)
    return facts, render_facts(state, arm, blob_path, facts, mode, level)


def render_facts(state, arm, blob_path, facts, mode='pvpoke', level='l50'):
    """Render an already-computed fact set, running every stage-15 gate."""
    ctx = {'blob': os.path.basename(blob_path), 'arm': arm, 'mode': mode}
    gate_recompute(state, arm, blob_path, mode, level, facts, ctx)
    gate_names(facts, ctx)
    headline = build_headline(facts)
    fields = build_fields(facts)
    evidence = build_evidence(facts)
    blocks = list(headline)
    for field in fields:
        blocks.extend(field_strings(field))
    blocks.extend(evidence['lines'])
    blocks.extend(evidence['head'])
    for row in evidence['rows']:
        blocks.extend(str(c) for c in row)
    gate_words(blocks, ctx)
    return arm_html(facts, headline, fields, evidence)


def blob_slug(path):
    base = os.path.basename(path)
    return base.split('.replay')[0]


def json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()
                if k not in ('mask', 'cells', 'contested_mask', 'all_win_mask',
                             'all_lose_mask', 'nwin', 'dedup_of',
                             'dedup_members_raw')}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def run_blob(path, out_dir, arms='all', mode='pvpoke', level='l50'):
    """Write <slug>_brief.html and <slug>_brief.json for one blob."""
    state = load_blob(path)
    n_arms = len(state['moveset_data'])
    indices = range(n_arms) if arms == 'all' else [int(arms)]
    sections, all_facts = [], []
    for arm in indices:
        facts, frag = render_arm(state, arm, path, mode=mode, level=level)
        sections.append(frag)
        all_facts.append(facts)
    h = all_facts[0]['header']
    title = f"Build brief -- {focal_name(h)}, {league_name(h['league'])}"
    subtitle = (f"Auto-derived from {h['blob']} (bake {h['blob_date']}), "
                f"{MODE_PROSE.get(mode, mode)}, level view "
                f"L{50 if level == 'l50' else 51}. "
                f"{len(sections)} of {n_arms} moveset arms.")
    doc = document_html(title, subtitle, sections)
    os.makedirs(out_dir, exist_ok=True)
    slug = blob_slug(path)
    html_path = os.path.join(out_dir, f"{slug}_brief.html")
    json_path = os.path.join(out_dir, f"{slug}_brief.json")
    with open(html_path, 'w') as fh:
        fh.write(doc)
    with open(json_path, 'w') as fh:
        json.dump(json_safe({'blob': path, 'mode': mode, 'level': level,
                             'arms': all_facts}), fh, indent=1, sort_keys=True)
        fh.write('\n')
    return html_path, json_path, all_facts


def sweep_row(facts):
    """One sweep line: floor or degradation rung, clean counts, alt target."""
    h = facts['header']
    fl = facts['floor']
    cc = facts['clean_counts']
    if fl is not None:
        outcome = (f"floor {fmt(fl['printed'], fl['dp'])} "
                   f"({pct(fl['pool_share'])}, {fl['mech']['kind']})")
    else:
        outcome = f"rung {facts['degradation']['rung']}"
    return [f"{focal_name(h)} {h['league']}", f"arm {h['arm']}",
            h['arm_label'], outcome,
            f"{cc.get('atk', 0)}/{cc.get('def', 0)}/{cc.get('hp', 0)}",
            str(facts['triage']['contested']),
            _sweep_rectangle(facts)]


def _sweep_rectangle(facts):
    """What the bulk rectangle buys, against whichever baseline applies.

    With a floor the claim is against the floor's clearers (the plan's rule);
    with no floor it is against every spread outside the rectangle. Printing
    only one of the two would read as "the rectangle buys nothing" on a dive
    where it buys nine cells the floor cannot.
    """
    alt = facts['alternative']
    if alt is None:
        return 'no'
    if facts['floor'] is None:
        return f"yes ({_plural(alt['n_exclusive'], 'cell')} vs the grid)"
    return (f"yes ({_plural(alt['n_guaranteed'], 'cell')} vs the floor, "
            f"{alt['n_exclusive']} vs the grid)")


def _plural(n, noun):
    return f"{int(n)} {noun}" + ('' if int(n) == 1 else 's')


SWEEP_HEAD = ['species', 'arm', 'moveset', 'outcome',
              'clean atk/def/hp', 'contested', 'bulk rectangle']


def write_sweep(rows, out_dir):
    """sweep.md, columns padded so the raw file lines up (repo md style)."""
    table = [SWEEP_HEAD] + rows
    widths = [max(len(r[i]) for r in table) for i in range(len(SWEEP_HEAD))]
    def line(cells, fill=' '):
        return '| ' + ' | '.join(c.ljust(w, fill)
                                 for c, w in zip(cells, widths)) + ' |'
    body = [line(SWEEP_HEAD),
            '| ' + ' | '.join('-' * w for w in widths) + ' |']
    body += [line(r) for r in rows]
    text = ("# Build-brief sweep\n\n"
            "One row per (blob, moveset arm). `outcome` is the selected floor "
            "or the degradation-ladder rung reached when no cut clears every "
            "gate. Floors print at the precision stage 7 proves is a valid "
            "`>=` selector. `bulk rectangle` counts the contested cells the "
            "(Def, HP) rectangle wins with every member where at most 1% of "
            "the spreads outside it do.\n\n" + '\n'.join(body) + '\n')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'sweep.md')
    with open(path, 'w') as fh:
        fh.write(text)
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('blobs', nargs='+', help='replay blob path(s)')
    ap.add_argument('--out', default='.', help='output directory')
    ap.add_argument('--arms', default='all',
                    help="'all' or a single arm index (default: all)")
    ap.add_argument('--mode', default='pvpoke', help='opponent-IV mode')
    ap.add_argument('--level', default='l50', choices=('l50', 'l51'),
                    help='level view (D8: one view per run)')
    ap.add_argument('--sweep', action='store_true',
                    help='write sweep.md over every blob instead of pages')
    args = ap.parse_args(argv)

    if args.sweep:
        rows = []
        for path in args.blobs:
            state = load_blob(path)
            for arm in range(len(state['moveset_data'])):
                facts = compute_brief(state, arm, path, mode=args.mode,
                                      level=args.level)
                rows.append(sweep_row(facts))
            del state
        print(write_sweep(rows, args.out))
        return 0

    for path in args.blobs:
        html_path, json_path, _ = run_blob(path, args.out, arms=args.arms,
                                           mode=args.mode, level=args.level)
        print(html_path)
        print(json_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
