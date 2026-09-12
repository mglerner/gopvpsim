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
ALT_SHARE_REFRAME = 0.40          # a rectangle this wide is not a target
SCORE_STEP_MIN = 60               # stage 10
CMP_NEAR_MISS = 0.50              # G-cmp-fresh WARN window (attack points)
DEGENERATE_SHARP = 6              # G-scenario
DEGENERATE_PATTERNS = 8           # G-scenario
NEAR_EXACT_SHARE = 0.005          # E2: "near-exact" = this share of the grid
GATE_MIN_ABOVE = 0.97             # E2b: a one-sided gate wins this share above
PRIMITIVE_TIE_WINDOW = 0.50       # attack points: kind preference inside this
MERGE_SPREAD_TOL = 0.01           # E3: rungs this close share one printed line
NAME_CAP = 3                      # G-names
LIST_CAP = 12                     # names printed in a field-8 list
SCORE_ROW_CAP = 12                # stage 10 table length
COGATE_ROW_CAP = 2                # co-gate rows printed per rung
SP_FLOOR = 0.95                   # stage 8 example rules
CATCH_TARGETS = (0.50, 0.75)      # D7

# G-caveat. Phase 0 item 3 of the plan moves this to scripts/mechanics_notice.py
# as CAVEAT_SPECIES; it is defined here so v1 is self-contained.
CAVEAT_SPECIES = ('Aegislash',)
CAVEAT_MARK = ' (engine divergence vs PvPoke)'

# D7 acquisition classes. The encounter count is only ever a UNIFORM-IV model;
# what changes per class is the source it is a model OF, and whether that
# source is known to restrict IVs. This table is deliberately short and is NOT
# a complete acquisition database -- every printed line carries the caveat
# sentence, so an unlisted species prints the wild wording with the same
# explicit "not verified" clause rather than a silent claim.
#
# 'none': the species has no wild spawn at all, so "wild catches" would be a
# false sentence (Melmetal comes from Meltan via Mystery Box and 400 candy;
# Deoxys forms are raid/EX only and carry a 10/10/10 research/raid IV floor
# that this uniform model does NOT apply).
ACQUISITION_NOT_WILD = ('Melmetal', 'Meltan', 'Deoxys', 'Genesect', 'Regigigas',
                        'Keldeo', 'Meloetta', 'Victini', 'Jirachi', 'Celebi',
                        'Mew', 'Shaymin', 'Darkrai', 'Cresselia', 'Heatran')
ACQUISITION_IV_FLOOR_NOTE = (
    "a raid, research or trade encounter has a 10/10/10 IV floor, so the "
    "count is taken over the spreads those sources can actually produce and "
    "not over the whole grid")
IV_FLOOR = 10                      # raid / research / trade floor, per IV

SHIELD_LABELS = None  # filled per blob from state['shield_scenarios']

BANNED_WORDS = (
    'recommend', 'recommended', 'best', 'strong', 'solid', 'definitive',
    'reliable', 'consistent', 'worth', 'great', 'good', 'bad', 'should',
)
BANNED_EXEMPT_PHRASES = ('Great League', 'Ultra League', 'Master League')
SHOULD_ALLOWED_PHRASE = 'most builds should clear'
# The second allowed "should": the expert-dive opening sentence. Both are
# scrubbed before the banned-word scan, and between them they may appear at
# most once in a rendered section.
SHOULD_ALLOWED_PATTERNS = (re.escape(SHOULD_ALLOWED_PHRASE),
                           r'most\s+[^.;:]{1,140}?should have at least')

# The three floor primitives, strongest first. A threshold is one of exactly
# these: an EXACT clean cut (nothing below wins, everything at or above does),
# a one-sided GATE (nothing below wins, at least GATE_MIN_ABOVE of the spreads
# at or above do) or a NEAR_EXACT split (at most NEAR_EXACT_SHARE of the grid
# on the wrong side in total). Rounds 1-3 printed the second and third as
# evidence under a headline that said nothing was a line; v2 lets them carry
# the line, badged with which one they are.
PRIMITIVE_RANK = {'exact': 0, 'gate': 1, 'near_exact': 2}
PRIMITIVE_BADGE = {'exact': 'exact', 'gate': 'one-sided gate',
                   'near_exact': 'near-exact'}
PRIMITIVE_HEADLINE_BADGE = {'exact': 'exact', 'gate': 'gate',
                            'near_exact': 'near-exact'}

# G-voice. The headline is written in the voice of an expert dive post, so the
# machinery's own nouns are barred from it (they all still appear, defined, in
# the fields below). Each entry is a regex over the headline block only.
HEADLINE_BANNED = (
    (r'partition\w*', 'say what the line decides, not that it partitions'),
    (r'one-sided gate', 'say what it wins and what it does not'),
    (r'constant rule', 'say "predicting one outcome for every spread"'),
    (r'separab\w+', 'a field-2 measurement, not a headline one'),
    (r'gap \(', 'the interval arithmetic belongs in field 2'),
    (r'carry a floor label', 'say "is a line to hunt for"'),
    (r'\barms?\b', 'say "moveset"'),
    (r'\bcells?\b', 'say "matchup", or "the 0v1 against X"'),
    (r'\bclearers?\b', 'say "spreads at or above the line"'),
)


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
    scores = np.asarray(data[skey][mode], dtype=np.int32).reshape(-1, n_sc, n_opp)
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


def cut_counts(stat, wins, T):
    """Both sides of a threshold, and which of the three primitives it is.

    Every candidate line -- exact, gate or near-exact -- is described by the
    same counts, so the templates that print one print all three.

    A GATE has one clean side and is named for what it then claims:

    - ``necessary``: no spread below the line wins, and most above do. The
      line is a floor you have to clear; clearing it is not a guarantee.
      (Melmetal 1v2 Furret: 0 of 1793 below, 2290 of 2303 above.)
    - ``sufficient``: every spread at or above the line wins, and a few below
      it win as well. Clearing the line is a guarantee; it is not the only
      way through. (Medicham 1v1 Snorlax: 1978 of 1978 above, 56 of 2118
      below.)

    An exact cut is both at once, which is why it outranks them.
    """
    above = stat >= T
    n_above = int(above.sum())
    n_win_above = int(wins[above].sum())
    n_below = int((~above).sum())
    n_win_below = int(wins[~above].sum())
    below_vals = np.unique(stat[stat < T])
    prev = float(below_vals.max()) if below_vals.size else float('-inf')
    n_wrong = (n_above - n_win_above) + n_win_below
    if n_wrong == 0:
        kind, side = 'exact', 'both'
    elif n_win_below == 0:
        kind, side = 'gate', 'necessary'
    elif n_win_above == n_above:
        kind, side = 'gate', 'sufficient'
    else:
        kind, side = 'near_exact', None
    return {'T': float(T), 'kind': kind, 'gate_side': side,
            'n_pass': n_above,
            'prev_attained': prev, 'n_attained_below': int(below_vals.size),
            'n_above': n_above, 'n_win_above': n_win_above,
            'n_below': n_below, 'n_win_below': n_win_below,
            'n_wrong': int(n_wrong),
            'rate_above': (n_win_above / n_above) if n_above else 0.0,
            'rate_below_loss': (1.0 - n_win_below / n_below) if n_below else 0.0}


def near_exact_limit(n_iv):
    """How many misclassified spreads "near-exact" allows (E2)."""
    return max(1, int(round(NEAR_EXACT_SHARE * n_iv)))


def primitive_ok(c, n_iv):
    """Does a candidate clear the bar for the primitive it IS?

    The dirty side has to be at least GATE_MIN_ABOVE pure in the direction the
    line claims: a "necessary" gate whose spreads above win only half the time
    is not a line, and neither is a "sufficient" one that half the grid
    already wins without it.
    """
    if c['kind'] == 'exact':
        return True
    if c['kind'] == 'gate':
        return (c['rate_above'] >= GATE_MIN_ABOVE
                if c['gate_side'] == 'necessary'
                else c['rate_below_loss'] >= GATE_MIN_ABOVE)
    return c['n_wrong'] <= near_exact_limit(n_iv)


def gate_cuts(stat, wins):
    """Both one-sided gates for one cell, each at its own value.

    The NECESSARY gate is ``min(stat[wins])``: every winner is at or above it,
    and any higher value would leave a winner below, so this is the highest
    threshold with a clean lower side. The SUFFICIENT gate is the lowest
    attained value above every loser, so everything at or above it wins. They
    coincide exactly when the cell has an exact clean cut.
    """
    if not wins.any() or wins.all():
        return []
    out = [cut_counts(stat, wins, float(stat[wins].min()))]
    hi_loss = float(stat[~wins].max())
    over = stat[stat > hi_loss]
    if over.size:
        out.append(cut_counts(stat, wins, float(over.min())))
    return out


def best_split(stat, wins):
    """The attained threshold misclassifying the fewest spreads.

    Ties take the LOWEST value, which is the same minimise-the-ask rule D1
    applies to rungs. The "everything on the high side" threshold is excluded:
    it predicts one outcome for the whole grid and is not a threshold.
    """
    n = stat.size
    order = np.argsort(stat, kind='stable')
    s_sorted = stat[order]
    w = wins[order]
    starts = np.concatenate(([0], np.nonzero(np.diff(s_sorted))[0] + 1))
    cum_win = np.concatenate(([0], np.cumsum(w)))
    cum_loss = np.arange(n + 1) - cum_win
    total_win = int(wins.sum())
    correct = cum_loss[starts] + (total_win - cum_win[starts])
    if starts.size < 2:
        return None, n
    j = int(np.argmax(correct[1:])) + 1
    return float(s_sorted[starts[j]]), int(n - correct[j])


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
            cuts.append(dict(cut_counts(stat, wins, got[0]),
                             axis=axis, si=si, oi=oi))
    return cuts


def stage2_primitives(win, planes, triage, axis='atk'):
    """Gate and near-exact candidates on the ATTACK axis (E2).

    The floor is an attack line everywhere else in this module -- the page
    prints "Atk >= X", the clearer mask is ``atk >= T``, rank-1's shortfall is
    in attack and the coverage ladder walks an attack grid -- so widening the
    primitive set widens WHICH ATTACK VALUES may carry the line, not which
    axis carries it. A Def gate still prints as the closest rule on a
    no-floor page; it does not become a floor.

    At most two candidates per cell reach the pool: the gate (a value with no
    winner below it) and the best-classifying split, each kept only when it
    clears the bar for the primitive it is and is not the cell's exact cut.
    """
    out = []
    stat = planes[axis]
    n_iv = win.shape[0]
    for si, oi in zip(*np.nonzero(triage['contested_mask'])):
        si, oi = int(si), int(oi)
        wins = win[:, si, oi]
        seen = set()
        got = clean_cut(stat, wins)
        if got is not None:
            seen.add(got[0])
        cands = list(gate_cuts(stat, wins))
        t_ne, _wrong = best_split(stat, wins)
        if t_ne is not None:
            cands.append(cut_counts(stat, wins, t_ne))
        for c in cands:
            if c['T'] in seen or c['kind'] == 'exact':
                continue
            if not primitive_ok(c, n_iv):
                continue
            seen.add(c['T'])
            out.append(dict(c, axis=axis, si=si, oi=oi))
    return out


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
    """Per-cut mode/arm hold counts, DIRECTION and CLEANLINESS kept apart.

    ``mode_cubes`` / ``arm_cubes`` map name -> (win cube, stat planes).

    THREE different questions, and the first two builds ran two of them
    together:

    - DIRECTION (``modes_ok`` / ``arms_ok``): does the PRINTED cut ``T`` still
      point the right way in another view (win rate at/above >= 0.90, and
      above the rate below it)?
    - PARTITION (``modes_partition`` / ``arms_partition``): does the PRINTED
      cut ``T`` split that view exactly -- ``(stat >= T) == wins``? A
      partition implies the direction test, so this count can never exceed
      the direction count.
    - SEPARABILITY (``modes_clean`` / ``arms_clean``): does that view have a
      clean cut for the cell AT ALL, at ANY value? This says nothing about
      the printed line, and it is NOT comparable with the other two.

    Round 2 printed separability under the word "cleanliness" beside the
    direction count, which produced an arithmetic inversion on Melmetal:
    "exactly clean in 3 of 4 arms" two lines under "points the same way in 2
    of 4 arms". The stricter test cannot pass more often than the weaker one
    -- and it did not: the 3 counted arms whose OWN cut exists (117.97,
    123.97, 122.37), not arms the 122.37 line partitions. All three counts
    are returned, the renderer names each for what it measures, and
    G-recompute re-derives all three and asserts partition <= direction.
    """
    def walk(cubes):
        ok, fail, clean, partition = [], [], [], []
        for name, (w_other, pl_other) in cubes.items():
            stat = pl_other[cut['axis']]
            wins = w_other[:, cut['si'], cut['oi']]
            r_a, r_b = direction_rates(w_other, stat, cut['T'],
                                       cut['si'], cut['oi'])
            (ok if (r_a >= DIRECTION_MIN_ABOVE and r_a > r_b)
             else fail).append((name, r_a, r_b))
            if np.array_equal(stat >= cut['T'], wins):
                partition.append(name)
            if clean_cut(stat, wins) is not None:
                clean.append(name)
        return ok, fail, clean, partition

    modes_ok, modes_fail, modes_clean, modes_part = walk(mode_cubes)
    arms_ok, arms_fail, arms_clean, arms_part = walk(arm_cubes)
    return {
        'modes_ok': len(modes_ok), 'modes_total': len(mode_cubes),
        'modes_fail': [n for n, _, _ in modes_fail],
        'modes_detail': modes_ok + modes_fail,
        'modes_clean': len(modes_clean),
        'modes_partition': len(modes_part),
        'modes_not_partition': [n for n in mode_cubes if n not in modes_part],
        'modes_not_clean': [n for n in mode_cubes if n not in modes_clean],
        'arms_ok': len(arms_ok), 'arms_total': len(arm_cubes),
        'arms_fail': [n for n, _, _ in arms_fail],
        'arms_clean': len(arms_clean),
        'arms_partition': len(arms_part),
        'arms_not_partition': [n for n in arm_cubes if n not in arms_part],
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
    # A gate can sit on the LOWEST attained attack, which leaves no previous
    # value to step from (prev_atk is -inf). There is no damage step to find
    # across an empty interval, and such a cut fails G-material-hi anyway.
    if not math.isfinite(prev_atk):
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
            # A line that lands EXACTLY on the cut is a tie, not a win: a
            # spread sitting on it does not out-prioritise the opponent, and
            # the engine resolves an exact tie by seat. Reachable whenever the
            # opponent is the focal's own mirror entry (Sableye (Shadow) 1v0:
            # 1.2 x 119.6685 is bit-identical to the 143.60219826 cut).
            return {'kind': 'cmp', 'line': line, 'build': build,
                    'on_the_line': bool(line == cut['T'])}
    bp = breakpoint_label(cut, cut['prev_attained'], focal_types, build,
                          opp_types.get(oi, ()), arm_label,
                          opp_charged_moves.get(oi, []))
    if bp is not None:
        return {'kind': 'breakpoint', 'detail': bp, 'build': build}
    # G-cmp-fresh, partial: there is no gamemaster stamp in the blob (the
    # plan's Phase 0), so a CMP label can only ever be emitted when the LIVE
    # line is inside the gap -- a refresh that moves the opponent's attack
    # silently downgrades the label to unattributed instead of printing a
    # stale mechanism. What is still missing is the WARN, so a near miss is
    # recorded here and surfaced in the evidence block.
    line = cmp_line(build, state['shadow']) if build else None
    near = (line is not None
            and abs(line - cut['T']) <= CMP_NEAR_MISS
            and not (cut['prev_attained'] < line <= cut['T']))
    return {'kind': 'unattributed', 'build': build, 'line': line,
            'cmp_near_miss': bool(near)}


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
        # The "line" column is a selector -- "focal clearers" is exactly
        # (atk >= line).sum() -- so it goes through the same print-precision
        # proof every other >= line does instead of round-to-nearest.
        pr, dp = printed_cut(line, atk, field='Coverage line',
                             ctx={'cell': label})
        # cmp_atk is carried, not re-derived as line/mult: the round trip
        # through the shadow multiplier moves the last bits, and the strict
        # share is a STRICT '<' comparison against exactly this value, so a
        # one-ulp drift silently reclassifies every tie.
        return {'label': label, 'line': line, 'printed': pr, 'dp': dp,
                'cmp_atk': float(cmp_atk_val), 'strict': strict,
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
    lines = [r['line'] for r in rows]
    monotone = all(b >= a for a, b in zip(lines, lines[1:]))
    top_iv = int(np.argmax(grid))
    top_ivs = (top_iv // 256, (top_iv // 16) % 16, top_iv % 16)
    return {'opponent': name, 'rows': rows, 'monotone': monotone,
            'max_ivs': top_ivs,
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


def group_rungs(cut_list, n_iv):
    """Cuts sharing one attack VALUE become one rung.

    ``n_pass``, ``pool_share`` and ``prev_attained`` are functions of T alone,
    so cells of different primitives can share a rung; the rung's own kind is
    the strongest one among its eligible cells (the cell that could carry the
    line), falling back to the strongest present when none is eligible.
    """
    rungs = []
    for T in sorted({c['T'] for c in cut_list}):
        group = [c for c in cut_list if c['T'] == T]
        rep = group[0]
        eligible = [c for c in group if c['eligible']]
        kind = min((PRIMITIVE_RANK[c['kind']] for c in (eligible or group)))
        rungs.append({
            'T': T, 'n_pass': rep['n_pass'], 'pool_share': rep['pool_share'],
            'n_attained_below': rep['n_attained_below'],
            'prev_attained': rep['prev_attained'],
            'cells': group,
            'kind': next(k for k, v in PRIMITIVE_RANK.items() if v == kind),
            'eligible': any(c['eligible'] for c in group),
            'gates': {g: any(c['gates'][g] for c in group)
                      for g in rep['gates']},
            # A rung can own several cells whose cross-setting support
            # differs. Printing the MAX alone lets the stronger cell's count
            # stand for the weaker one, so both ends are carried and the
            # renderer prints a range when they differ.
            'modes_ok': max(c['holds']['modes_ok'] for c in group),
            'modes_ok_min': min(c['holds']['modes_ok'] for c in group),
            'modes_total': rep['holds']['modes_total'],
            'arms_ok': max(c['holds']['arms_ok'] for c in group),
            'arms_ok_min': min(c['holds']['arms_ok'] for c in group),
            'arms_total': rep['holds']['arms_total'],
        })
    return rungs


def floor_cell_of(rung):
    """The cell whose claim the floor prints: eligible first, strongest kind.

    With one primitive this was ``the first eligible cell``; with three, two
    eligible cells at one value can make different claims, and the page has to
    print the stronger one.
    """
    eligible = [c for c in rung['cells'] if c['eligible']]
    if not eligible:
        return rung['cells'][0]
    return sorted(eligible, key=lambda c: PRIMITIVE_RANK[c['kind']])[0]


def rung_kind(r):
    """Which primitive a rung carries. Hand-built rungs default to exact."""
    return r.get('kind', 'exact')


def stage6_select(rungs, band=DECISION_BAND, n_iv=None,
                  tol=MERGE_SPREAD_TOL, kinds=None):
    """Lowest eligible rung in ``band`` (D1), MERGED UPWARD where it is free.

    D1 minimises the ask. Taken literally that makes the headline opponent
    flap between arms and between two pages for a difference of 0.08 attack:
    plain Sableye headlined 123.34 for ONE rank-35 cell while the rung 21
    spreads up at 123.41 owns four cells against three top-31 opponents, and
    the four Shadow Sableye arms split between 148.01 (Electrode) and 148.10
    (Annihilape) for what is physically one build target.

    So consecutive eligible in-band rungs whose clearer sets differ by less
    than ``tol`` of the grid are reported as ONE line at the HIGHER value.
    Merging upward is sound in the direction that matters: every spread
    clearing the higher value clears the lower one, so every "it buys X"
    claim survives. It is NOT sound in the other direction -- a cell that
    turns over at the lower value IS won by some spreads below the printed
    line -- so the merged-in cells are carried separately in ``merged_from``
    and the renderer states them with that difference rather than under the
    floor's "and none below it does".
    """
    eligible = [r for r in rungs if r['eligible']
                and band[0] <= r['pool_share'] <= band[1]]
    if kinds is not None:
        eligible = [r for r in eligible if rung_kind(r) in kinds]
    if not eligible:
        return None
    eligible.sort(key=lambda r: r['T'])
    # V2: the pool now holds one-sided gates and near-exact splits beside the
    # exact cuts. D1 still minimises the ask, so the LOWEST eligible rung
    # wins -- except that a stronger primitive within PRIMITIVE_TIE_WINDOW
    # attack of it is taken instead, which is a tie-break and not a
    # preference: half an attack point is inside the rounding a reader does
    # anyway, and an exact cut says strictly more than a gate at the same
    # place.
    lowest = eligible[0]['T']
    window = [r for r in eligible if r['T'] <= lowest + PRIMITIVE_TIE_WINDOW]
    pick = min(window, key=lambda r: (PRIMITIVE_RANK[rung_kind(r)], r['T']))
    start = next(i for i, r in enumerate(eligible) if r is pick)
    merged = []
    limit = tol * (n_iv or 4096)
    # Merging is EXACT-only. The merged-in cell's claim ("every spread at or
    # above the printed line wins it") is proved by its own exact partition;
    # a gate or a near-exact rung cannot prove it, and G-recompute checks it
    # cell by cell, so a non-exact rung is never merged and never merged into.
    if rung_kind(pick) == 'exact':
        for nxt in eligible[start + 1:]:
            if rung_kind(nxt) != 'exact':
                break
            if pick['n_pass'] - nxt['n_pass'] > limit:
                break
            merged.append(pick)
            pick = nxt
    if not merged:
        return pick
    out = dict(pick)
    out['merged_from'] = merged
    return out


def stage6_sensitivity(rungs, bands=SENSITIVITY_BANDS, atk=None, n_iv=None):
    """Which floor each candidate band would select.

    The value printed here is a >= selector like every other, so it goes
    through printed_cut rather than round-to-nearest.
    """
    out = []
    for b in bands:
        pick = stage6_select(rungs, b, n_iv=n_iv)
        row = {'band': b, 'T': (pick['T'] if pick else None),
               'cell': (pick['cells'][0]['label'] if pick else None),
               'printed': None, 'dp': 2}
        if pick is not None and atk is not None:
            row['printed'], row['dp'] = printed_cut(
                pick['T'], atk, field='Sensitivity',
                ctx={'cell': pick['cells'][0]['label']})
        elif pick is not None:
            row['printed'] = pick['T']
        out.append(row)
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
    """Three example spreads by printed rules, dominance-checked.

    With NO floor the baseline becomes the whole grid instead of the
    clearers. Rounds 1 and 2 returned nothing here, so on exactly the pages
    where the verdict is negative -- where the reader most needs "then what do
    I keep" -- field 9 printed a silence sentence and the negative had no
    positive half.
    """
    idx = np.nonzero(floor_mask)[0]
    has_floor = idx.size > 0
    if not has_floor:
        idx = np.arange(meta.shape[0])
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
            # Named 'contested_cells', not 'cells': json_safe strips the key
            # 'cells' (rung cell lists carry numpy), so the first build's
            # example rows lost this number from the JSON dump while the HTML
            # still printed it.
            'contested_cells': int(cells_won[i]),
            'total': int(total_won[i]), 'i': i,
        })

    who = 'clearers' if has_floor else 'the whole grid'
    if has_floor:
        add('highest stat product clearing the floor', idx[np.argmax(sp[idx])])
    else:
        # E5: with no line to clear, the spread that WINS THE MOST CELLS is
        # the comparison rank-1 has to be measured against, and it is the one
        # number the no-floor pages never printed.
        add('most cells won on the whole grid', idx[np.argmax(cells_won[idx])])
        add('highest stat product (the rank-1 spread)', idx[np.argmax(sp[idx])])
    if hi_sp.size:
        add(f"most cells won among {who} with SP >= {int(SP_FLOOR*100)}%",
            hi_sp[np.argmax(cells_won[hi_sp])])
        bulk = meta[hi_sp, 6] * meta[hi_sp, 7]
        add(f"bulkiest (max Def x HP) among {who} with SP >= "
            f"{int(SP_FLOOR*100)}%", hi_sp[np.argmax(bulk)])
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

def stage9b_alternative(win, meta, floor_mask, contested_cells, state,
                        score_ok=None):
    """The (Def >= d) & (HP >= h) rectangle that buys the most, or None.

    With a floor, the plan's rule: rectangles of at least ALT_MIN_MEMBERS
    members that contain no floor clearer, scored by the contested cells every
    member wins that at most ALT_MAX_CLEARER_RATE of the clearers win.

    With no floor there is nothing to be disjoint from, so that score is
    vacuous -- every cell every member wins counts, including the ones almost
    the whole grid wins. The baseline becomes the spreads OUTSIDE the
    rectangle, which is exact and free: if all ``n`` members win a cell, the
    winners outside it are ``total_win - n`` out of ``n_iv - n``.

    ``score_ok`` is the G-rank / G-scenario / G-caveat mask over
    ``contested_cells``, and the caller passes it ONLY when there is no floor.
    The asymmetry is deliberate. With a floor the rectangle is explicitly the
    alternative TO a gated claim, its value is stated relative to that claim,
    and the plan's worked case prints its cells with their ranks inline (three
    of nine are top-50, one is a degenerate scenario) so the reader can weigh
    them -- gating there would silently change the answer the plan pins. With
    no floor the rectangle IS the headline claim, and a headline claim goes
    through the same relevance gate every other headline claim does: ungated,
    Deoxys' rectangle was selected by two rank-110 Wartortle cells.
    Give-ups are never gated: a cost is a cost whoever owns it.
    """
    dfn, hp = meta[:, 6], meta[:, 7]
    cells = np.array(contested_cells)
    if cells.size == 0:
        return None
    if score_ok is None:
        score_ok = np.ones(len(contested_cells), dtype=bool)
    score_ok = np.asarray(score_ok, dtype=bool)
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
            guaranteed_all = wc[mask].all(axis=0) & score_ok
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
            species = parse_opponent_spec(state['opponent_names'][oi])[0]
            rows.append({
                'T': values[j + 1], 'si': si, 'oi': oi,
                'below': below, 'above': above,
                'won': bool(triage['all_win_mask'][si, oi]),
                'rank': ranks[oi], 'label': cell_label(state, si, oi),
                'caveat': any(c in species for c in CAVEAT_SPECIES),
            })
    # A caveat cell (open engine divergence against PvPoke) never leads the
    # table: the first build sorted purely by step size and so topped this
    # field with the one result field 10 says it does not trust.
    # E9: ordered by how close the cell comes to FLIPPING, not by how big the
    # step is. A 75 -> 307 swing inside a fight nobody wins tells a player
    # nothing; a 444 -> 274 step moving away from 500 is the row that matters.
    # Step size stays as the secondary key, and a caveat cell still sorts last.
    for r in rows:
        r['to_win'] = int(min(abs(r['below'] - WIN_RATING),
                              abs(r['above'] - WIN_RATING)))
        r['toward_win'] = bool(abs(r['above'] - WIN_RATING)
                               < abs(r['below'] - WIN_RATING))
    rows.sort(key=lambda r: (r['caveat'], r['to_win'],
                             -abs(r['above'] - r['below']), r['label']))
    return rows


# ---------------------------------------------------------------------------
# Stage 11 -- rank-1 adjudication
# ---------------------------------------------------------------------------

def stage11_rank1(meta, sp, win, rungs, floor, atk, n_iv, atk_cuts=(),
                  contested_cells=()):
    """Which side of the floor rank-1 is on, and what it clears.

    The cut count is over clean attack cuts (CELLS), not over distinct cut
    VALUES: two cells that turn over at the same number are two claims.

    ``total_won`` is printed with its denominator everywhere: "367" alone
    gives a reader no way to tell whether it is a lot, and the same page also
    prints 371 and 382 for the example spreads.
    """
    i = int(np.argmax(sp))
    clears = [c for c in (atk_cuts or rungs) if atk[i] >= c['T']]
    material = [r for r in rungs
                if r['gates']['G-material-lo'] and r['gates']['G-material-hi']]
    missed = [r for r in material if atk[i] < r['T']]
    n_contested_won = int(sum(1 for si, oi in contested_cells
                              if win[i, si, oi]))
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
        'total_cells': int(win[i].size),
        'contested_won': n_contested_won,
        'n_contested': len(contested_cells),
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


def stage12_degradation(triage, cuts, rungs, floor, n_modes, n_arms, n_iv,
                        n_excluded=0):
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
        # ONE denominator, reconciled in the sentence. Round 2 printed three
        # different totals for this quantity on one Furret page (28 in the
        # headline, 26 here, 28 in the gate tally) because G-caveat's
        # exclusion was applied to one of them only.
        excl = (f" ({len(cuts) + n_excluded} less the {n_excluded} excluded "
                f"for an open engine divergence)" if n_excluded else '')
        return {'rung': 'c', 'sentence':
                f"{len(cuts)} clean cuts{excl} exist on this dive and none is "
                f"a floor: no exact cut, one-sided gate or near-exact split "
                f"clears every gate with a pool share inside "
                f"[{pct(DECISION_BAND[0],0)}, {pct(DECISION_BAND[1],0)}] of the "
                f"grid.",
                'counts': dict(reasons, n_excluded=n_excluded)}
    # Rung (d) is unreachable under D1: stage6_select already requires the
    # floor's pool inside DECISION_BAND (0.25, 0.60), so pool_share < 0.02
    # cannot hold for a selected floor. It is kept, and tested on a
    # hand-built state, because the band is a Phase-0 calibration constant --
    # a corpus sweep that admits small pools makes this rung live again.
    if floor['pool_share'] < 0.02:
        return {'rung': 'd', 'sentence':
                f"A clean cut exists at {fmt(floor['T'])} but only "
                f"{floor['n_pass']} of {n_iv} spreads clear it, so it is too "
                f"rare to carry a floor label.",
                'counts': {'n_pass': floor['n_pass']}}
    return {'rung': 'floor', 'sentence': '', 'counts': {}}


# ---------------------------------------------------------------------------
# DEFERRED: plan stages and guards that are deliberately NOT implemented here.
# Named so a reader of this file can tell "considered and deferred" from
# "forgotten".
#
# Stage 13 -- human override (`[Species.League.brief]` with `body` and
#   `target`). Deferred by decision D4: v1 is machine-only, and the block is
#   a threshold-schema change (docs/threshold_schema.md) that has to land with
#   the pre-commit `authored_by = "ai"` scan. The shape it would take:
#   non-empty `body` renders instead of the machine brief with the machine
#   result demoted to one labelled line; non-empty `target` re-runs stages
#   5-11 against the human stat triple and, when it is not a clean cut, prints
#   "not a clean cut in this bake: N of M clearers win" rather than
#   substituting it.
#
# Stage 14 -- cluster corroboration line ("the cluster partition splits at
#   X"). Deferred: it needs `scripts/deep_dive_lib/clusters.py` `choose_k`,
#   and the plan itself marks that number as CITED rather than recomputed, so
#   shipping it here would print a number this module never derived.
#
# G-recompute, the numbers it does NOT re-derive, and why. Round 3 closed
#   the 25 reader-facing leaves a corruption probe found unguarded (rank-1's
#   cut counts and shortfall, the not-claimed denominator, the clean-cut axis
#   breakdown, the whole of field 11, the tail counts, co-gate rates outside,
#   the example rows' contested count / stat-product rank / share, level
#   reach, the rectangle's stat-product and attack ranges and its envelope,
#   the floor's energy pair, the cost diff's four counts, the grid-best
#   spread, the catch model's reachable grid, and both partition counts).
#   Three printed numbers remain out of reach and are named here rather than
#   left silent, because they are LIVE READS and not blob facts:
#     - `floor['rank']` and every rank printed inline, from the rankings
#       snapshot;
#     - `floor['mech']['opp_level']` and the opponent's IVs / attack, from
#       the gamemaster through `resolve_opp_ivs`;
#     - `gate_tally['n_eligible']`, because G-rank is a function of the first
#       of those.
#   Re-deriving them would re-read the same two live sources and so could
#   only catch a corruption between read and print, never a stale source.
#   The provenance field says both are live; a blob gamemaster stamp (plan
#   Phase 0 item 1) is what would make them checkable.
#
# G-scores (no score-kind token outside fields 2, 11 and 12) -- enforced BY
#   CONSTRUCTION rather than by a typed scan: battle scores enter the fact
#   dict only through `floor['score_below'] / ['score_above']` (field 2),
#   `_mirror` (field 11) and `_score_row` (field 12), and nothing else in
#   `facts` carries a score. Field 15 names the win threshold itself
#   ("score > 500"), which is the predicate's definition and not a measured
#   score; the plan's typed-token infrastructure (`Num(kind, value, field)`)
#   is Phase 2 and would have to exempt it.
#
# G-cmp-fresh -- half implemented. The label is only ever emitted when the
#   LIVE priority line lies inside the cut's gap, so a gamemaster refresh that
#   moves the opponent's attack downgrades the mechanism to unattributed
#   instead of printing a stale cause. The missing half is the WARN: a cut
#   whose line is NEAR the gap but outside it is now recorded
#   (`mech['cmp_near_miss']`, window CMP_NEAR_MISS) and surfaced in the
#   evidence block, which is as close as a blob with no gamemaster stamp
#   (plan Phase 0 item 1) can get.
# ---------------------------------------------------------------------------


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

def acquisition_class(species, shadow):
    """Which source sentence the encounter count is a model OF (D7).

    The first build branched on ``state['shadow']`` alone, so every
    non-shadow page said "wild catches" -- including Melmetal, which has no
    wild spawn at any rate (Meltan via Mystery Box, then 400 candy), and
    would have said it for Deoxys (Defense), a raid/EX species whose sources
    carry a 10/10/10 IV floor this uniform model does not apply.
    """
    if shadow:
        return 'grunt'
    if any(species.startswith(s) for s in ACQUISITION_NOT_WILD):
        return 'none'
    return 'wild'


def reachable_mask(meta, acquisition):
    """Which spreads the named source can produce at all (D7).

    A raid, research or trade encounter cannot roll an IV below 10, so a
    uniform-over-4096 count is not a model of that source -- it is a model of
    a source this species does not have. Round 2 printed the 4096-grid count
    under a caveat saying the floor "does NOT apply", which put an
    UNREACHABLE target on the page as the only actionable number Deoxys
    carried: its rectangle (Def >= 232.05, HP >= 94) has 276 members and
    shares exactly 0 of them with the 216 spreads a 10/10/10 floor allows.
    """
    if acquisition != 'none':
        return np.ones(meta.shape[0], dtype=bool), False
    m = ((meta[:, 0] >= IV_FLOOR) & (meta[:, 1] >= IV_FLOOR)
         & (meta[:, 2] >= IV_FLOOR))
    return m, True


def catch_model(target_mask, meta, acquisition, targets=CATCH_TARGETS):
    """Encounter counts over the grid the SOURCE can produce, not over 4096."""
    grid, restricted = reachable_mask(meta, acquisition)
    n_grid = int(grid.sum())
    n_reach = int((np.asarray(target_mask, dtype=bool) & grid).sum())
    share = (n_reach / n_grid) if n_grid else 0.0
    return {'restricted': bool(restricted), 'n_grid': n_grid,
            'n_reachable': n_reach, 'share': float(share),
            'rows': [{'target': t, 'n': n}
                     for t, n in catch_encounters(share, targets)]}


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
    contested cell this reports the attained threshold that classifies the
    grid best, and the win rates on each side of it -- the number the shipped
    75/25 "flips at" engine would quote, said out loud as dirty rather than
    promoted to a floor.

    Two gates keep the row from being worse than saying nothing at all:

    - It must BEAT THE CONSTANT RULE. Ranking by raw accuracy on a lopsided
      column promotes a threshold that misclassifies more spreads than "no
      spread wins this" would. Melmetal 2v2 Jellicent is won by 1 spread of
      4096: the printed HP >= 149.00 split got 7 wrong where the constant rule
      gets 1. Rows are ranked by how many spreads they rescue from the
      constant rule, not by accuracy.
    - It must pass the SAME materiality band the clean-cut ladder enforces.
      A split with 8 spreads on one side is not a build decision, and
      printing it beside a sentence that says nothing separates is the
      contradiction this field exists to avoid.
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
        # What the best CONSTANT rule gets wrong: predict "everyone wins" or
        # "nobody wins", whichever is cheaper. A threshold that does not beat
        # this is worse than printing nothing.
        constant_wrong = min(total_win, n_iv - total_win)
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
                n_above = int(above.sum())
                share = n_above / n_iv
                if not (MATERIAL_LO <= share <= MATERIAL_HI):
                    continue
                r_above = float(wins[above].mean())
                r_below = float(wins[~above].mean())
                if r_above <= r_below:
                    continue
                n_wrong = int(n_iv - correct[j])
                if n_wrong >= constant_wrong:
                    continue
                acc = float(correct[j]) / n_iv
                gain = constant_wrong - n_wrong
                if pick is None or gain > pick['gain']:
                    pick = {'axis': axis, 't': t, 'accuracy': acc,
                            # E2: a threshold with NOTHING winning below it is
                            # a one-sided gate -- a build line by the genre's
                            # standard even when the rate above is under 100%
                            # -- and one that misclassifies a handful of
                            # spreads is near-exact. Round 2 printed both under
                            # a headline that said nothing was a build line.
                            'one_sided': bool(
                                int(wins[~above].sum()) == 0
                                or int(wins[above].sum()) == n_above),
                            'gate_side': ('necessary'
                                          if int(wins[~above].sum()) == 0
                                          else 'sufficient'
                                          if int(wins[above].sum()) == n_above
                                          else None),
                            'n_wrong': n_wrong, 'gain': int(gain),
                            'constant_wrong': int(constant_wrong),
                            'rate_above': r_above, 'rate_below': r_below,
                            'n_above': n_above,
                            'n_win_above': int(wins[above].sum()),
                            'n_win_below': int(wins[~above].sum()),
                            'n_below': int((~above).sum())}
                break
        if pick is None:
            continue
        pr, dp = printed_cut(pick['t'], planes[pick['axis']],
                             field='Dirty threshold',
                             ctx={'cell': cell_label(state, si, oi)})
        # E8: what the value costs at the precision PvPoke and Poke Genie
        # actually display. The exact selector needs the places it needs; a
        # reader hunting the stat sees one decimal, and the difference is a
        # number rather than an argument.
        genre = None
        if dp > 1 and pick['axis'] != 'hp':
            stat_v = planes[pick['axis']]
            g = math.floor(pick['t'] * 10.0) / 10.0
            g_above = stat_v >= g
            genre = {'printed': g, 'n_above': int(g_above.sum()),
                     'n_extra': int((g_above & (stat_v < pick['t'])).sum())}
        pick.update({'genre': genre, 'printed': pr, 'dp': dp, 'rank': rank,
                     'cell': cell_label(state, si, oi),
                     'near_exact': bool(pick['n_wrong']
                                        <= max(1, round(NEAR_EXACT_SHARE * n_iv))),
                     'win_rate': float(wins.mean())})
        rows.append(pick)
    rows.sort(key=lambda r: (-r['gain'], r['cell']))
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
        rate = float(wins.mean())
        if got is None:
            out[name] = {'clean': False, 'rate': rate,
                         'n_win': int(wins.sum())}
        else:
            pr, dp = printed_cut(got[0], stat, field='Cross-view cut',
                                 ctx={'cell': name})
            # The rate is carried for a CLEAN view too: a cell won by 4095 of
            # 4096 spreads on another arm has a clean cut there, and counting
            # it as corroboration without saying so was the round-2 Melmetal
            # over-claim ("clean on the Dynamic Punch arm" -- where the fight
            # is free).
            out[name] = {'clean': True, 'T': got[0], 'printed': pr, 'dp': dp,
                         'n_pass': got[1], 'rate': rate,
                         'n_win': int(wins.sum())}
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
    # V2 (E2): the two inexact primitives, attack axis only. They are kept in
    # their OWN list so that every census on this page -- the clean-cut counts,
    # the rung ladder, the not-claimed denominator, the dirty-threshold table
    # -- keeps meaning "exact clean cut" and only the FLOOR pool widens.
    prims = stage2_primitives(win, planes, triage)
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
    for c in cuts + prims:
        c['label'] = cell_label(state, c['si'], c['oi'])
        c['rank'] = ranks[c['oi']]
        c['mech'] = stage4_mechanism(c, state, mode, builds, focal_types,
                                     arm_label, opp_types, opp_charged)
        c['holds'] = stage3_holds(c, mode_cubes, arm_cubes, planes)
        c['gates'] = rung_gates(c, c['holds'], c['mech'], ranks, triage, state,
                                n_iv)
        c['eligible'] = all(c['gates'].values())
        c['pool_share'] = c['n_pass'] / n_iv
        c['caveat'] = not c['gates']['G-caveat']
        members = triage['dedup_members'].get(triage['dedup_of'][(c['si'], c['oi'])], [])
        c['dedup_members'] = [names[o] for o in members]

    # G-caveat is an EXCLUSION, not only a floor gate. The plan's wording is
    # "cell excluded from floor/rungs/cost totals; named under 'Not claimed'
    # with the caveat"; the first build consulted it only through
    # ``eligible``, so an Aegislash cell with a clean cut printed as an
    # ordinary rung (Furret: "Atk >= 120.83 | 0v0 Aegislash (Shield)") and,
    # being claimed, never reached field 13 either -- the caveat text appeared
    # nowhere on the page.
    cuts_claimed = [c for c in cuts if not c['caveat']]
    cuts_caveat = [c for c in cuts if c['caveat']]
    atk_cuts = [c for c in cuts_claimed if c['axis'] == 'atk']
    prims_claimed = [c for c in prims if not c['caveat']]
    # Two rung lists, and the difference matters on every page. ``rungs`` is
    # the EXACT ladder: it is what fields 5 and 6 print, what rank-1 is scored
    # against, and what the tail sentence counts, and every claim it makes
    # ("every spread at or above it wins") is exact. ``floor_rungs`` is the
    # wider pool the floor is SELECTED from, exact cuts plus gates plus
    # near-exact splits.
    rungs = group_rungs(atk_cuts, n_iv)
    floor_rungs = group_rungs(atk_cuts + prims_claimed, n_iv)

    floor_rung = stage6_select(floor_rungs, n_iv=n_iv)
    sensitivity = stage6_sensitivity(floor_rungs, atk=atk, n_iv=n_iv)
    # E2 audit: what each primitive ALONE would have selected, so a reader can
    # see whether the widened pool moved the line and by how much.
    primitive_picks = {}
    for kind in ('exact', 'gate', 'near_exact'):
        pick = stage6_select(floor_rungs, n_iv=n_iv, kinds=(kind,))
        primitive_picks[kind] = None if pick is None else {
            'T': pick['T'],
            'printed': printed_cut(pick['T'], atk, field='Primitive audit',
                                   ctx={'cell': pick['cells'][0]['label']})[0],
            'dp': printed_cut(pick['T'], atk, field='Primitive audit',
                              ctx={'cell': pick['cells'][0]['label']})[1],
            'cell': floor_cell_of(pick)['label'],
            'n_pass': pick['n_pass'], 'pool_share': pick['pool_share'],
        }

    contested_cells = [(int(si), int(oi))
                       for si, oi in zip(*np.nonzero(triage['contested_mask']))]
    # G-rank / G-scenario / G-caveat over the contested cells: which of them
    # may SELECT a claim (a rung, or the bulk rectangle).
    score_ok = np.array([
        (ranks[oi] is not None and ranks[oi] <= RANK_GATE)
        and not triage['degenerate'][si]
        and not any(c in parse_opponent_spec(names[oi])[0]
                    for c in CAVEAT_SPECIES)
        for si, oi in contested_cells], dtype=bool)
    degradation = stage12_degradation(triage, cuts_claimed, floor_rungs,
                                      floor_rung, len(modes), n_arms, n_iv,
                                      n_excluded=len(cuts_caveat))
    caps = stage12_caps(len(modes), n_arms)
    # A cell the FLOOR claims is claimed, whatever primitive did it: leaving it
    # in the dirty-threshold table would print the page's own line back as
    # "the closest thing to a line", which is the negative-page wording the
    # page no longer carries.
    claimed = {(c['si'], c['oi']) for c in cuts_claimed}
    floor_claimed = ({(c['si'], c['oi']) for c in floor_rung['cells']}
                     if floor_rung is not None else set())
    dirty = stage12b_dirty_thresholds(win, planes, contested_cells,
                                      claimed | floor_claimed,
                                      ranks, triage, state)
    cmp_near_misses = [c['label'] for c in cuts
                       if c['mech'].get('cmp_near_miss')]

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
            'total_cells': n_sc * n_opp,
            'scenarios': [scenario_label(state, si) for si in range(n_sc)],
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
        'clean_excluded': len(cuts_caveat),
        'clean_claimed': len(cuts_claimed),
        'n_distinct_atk_cuts': len({c['T'] for c in atk_cuts}),
        'reverse_cuts': len(reverse_cuts),
        'degradation': degradation,
        'caps': caps,
        'dirty_thresholds': dirty,
        'primitive_picks': primitive_picks,
        'cmp_near_misses': cmp_near_misses,
        'acquisition': acquisition_class(state['species'],
                                         bool(state['shadow'])),
        'sensitivity': sensitivity,
        'constants': {
            'gate_min_above': GATE_MIN_ABOVE,
            'near_exact_share': NEAR_EXACT_SHARE,
            'primitive_tie_window': PRIMITIVE_TIE_WINDOW,
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

    facts['not_claimed'] = _not_claimed(
        win, triage,
        cuts_claimed + [c for c in (floor_rung['cells'] if floor_rung else [])
                        if c['kind'] != 'exact'],
        cuts_caveat, contested_cells, state, ranks, floor_rung, atk)
    # E5: the size of the decision, stated as a measured fact -- how many
    # cells the grid's most-winning spread takes, against rank-1's count. On
    # a no-floor arm this is the whole verdict, and rounds 1 and 2 never
    # computed it.
    _all_won = win.reshape(n_iv, -1).sum(axis=1)
    _gb = int(np.argmax(_all_won))
    facts['grid_best'] = {
        'i': _gb, 'ivs': tuple(int(v) for v in meta[_gb, :3]),
        'level': float(meta[_gb, 3]), 'total': int(_all_won[_gb]),
        'total_cells': int(win[_gb].size),
        'sp_rank': int(sp_rank[_gb]),
        'n_tied': int((_all_won == _all_won[_gb]).sum()),
        'contested': int(sum(1 for si, oi in contested_cells
                             if win[_gb, si, oi])),
    }

    if floor_rung is None:
        facts['floor'] = None
        facts['rungs_above'] = []
        facts['rungs_below'] = [_rung_row(r, state, n_iv, atk) for r in rungs
                                if r['gates']['G-material-lo']
                                and r['gates']['G-material-hi']]
        facts['bulk'] = {'clean_def': facts['clean_counts'].get('def', 0),
                         'clean_hp': facts['clean_counts'].get('hp', 0),
                         'frontier': [], 'cogates': []}
        alt = stage9b_alternative(win, meta, np.zeros(n_iv, bool),
                                  contested_cells, state, score_ok)
        facts['alternative'] = _alt_facts(alt, state, meta, win, n_iv, ranks,
                                          triage, state['opponent_names'])
        facts['examples'] = stage8_examples(meta, win, np.zeros(n_iv, bool),
                                            contested_cells, sp, sp_rank)
        for ex in facts['examples']:
            ex['by_scenario'] = per_scenario_wins(win, ex['i'], n_sc)
        facts['rank1'] = stage11_rank1(meta, sp, win, rungs, None, atk, n_iv,
                                       atk_cuts, contested_cells)
        facts['coverage'] = None
        facts['mirror'] = _mirror(state, win, meta, atk, None, mode_cubes, modes)
        facts['score_only'] = [_score_row(r, atk) for r in
                               stage10_score_only(scores, atk, triage, state, ranks)]
        facts['cost'] = {'reverse_cuts': len(reverse_cuts), 'diff': None}
        facts['catch'] = []
        facts['catch_model'] = None
        facts['rank1']['by_scenario'] = per_scenario_wins(
            win, facts['rank1']['i'], n_sc)
        # Set in BOTH branches. The first build assigned it only where a
        # floor existed, so ``r1.get('in_alternative')`` was None on every
        # no-floor arm and field 4 printed "It is not a member of the
        # Alternative target below" unconditionally -- false on Deoxys, where
        # rank-1 (0/15/15, Def 232.73 / HP 102) is inside the printed
        # Def >= 223.96 & HP >= 89 rectangle.
        facts['rank1']['in_alternative'] = bool(
            alt is not None and alt['mask'][facts['rank1']['i']])
        facts['alt_catch'], facts['alt_catch_model'] = _alt_catch(
            alt, meta, facts['acquisition'])
        return facts

    # --- floor present -------------------------------------------------
    _, meta51 = arm_view(state, arm, mode, 'l51')
    atk51 = meta51[:, 5]
    pp = stage7_print_precision(floor_rung['T'], atk, atk51, field='Floor',
                                ctx=dict(ctx, cell=floor_rung['cells'][0]['label']))
    floor_mask = atk >= floor_rung['T']
    floor_cell = floor_cell_of(floor_rung)
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

    # G-owner is over EVERY cell that turns over at this value after dedup,
    # not only the eligible ones: filtering to the eligible set made
    # "owned by one base species" true by construction whenever exactly one
    # cell passed the gates, and the required "if it leaves the pool the line
    # has no owner" sentence would then print even though another species'
    # cell turns over at the same number and would keep the line alive.
    owners = sorted({
        parse_opponent_spec(names[triage['dedup_of'][(c['si'], c['oi'])][1]])[0]
        for c in floor_rung['cells']})
    facts['floor'] = {
        'T': floor_rung['T'], 'printed': pp['printed'], 'dp': pp['dp'],
        'prev_attained': floor_rung['prev_attained'],
        'n_pass': floor_rung['n_pass'], 'pool_share': floor_rung['pool_share'],
        'axis': 'atk',
        # E2: which primitive carries the line, and both sides of it. An
        # exact cut has n_wrong 0 and n_win_above == n_above; a gate has
        # n_win_below 0 and a rate above at least GATE_MIN_ABOVE; a
        # near-exact has n_wrong at most NEAR_EXACT_SHARE of the grid.
        'kind': floor_cell['kind'],
        'gate_side': floor_cell['gate_side'],
        'badge': PRIMITIVE_BADGE[floor_cell['kind']],
        'n_above': floor_cell['n_above'],
        'n_win_above': floor_cell['n_win_above'],
        'n_win_below': floor_cell['n_win_below'],
        'n_wrong': floor_cell['n_wrong'],
        'rate_above': floor_cell['rate_above'],
        'rate_below_loss': floor_cell['rate_below_loss'],
        'near_exact_limit': near_exact_limit(n_iv),
        'gate_min_above': GATE_MIN_ABOVE,
        'cell': floor_cell['label'], 'rank': floor_cell['rank'],
        'mech': _mech_facts(floor_cell['mech'], floor_cell),
        'dedup_members': floor_cell['dedup_members'],
        'modes_ok': floor_cell['holds']['modes_ok'],
        'modes_total': floor_cell['holds']['modes_total'],
        'arms_ok': floor_cell['holds']['arms_ok'],
        'arms_total': floor_cell['holds']['arms_total'],
        # Direction, partition and separability are three different claims;
        # see stage3_holds.
        'modes_clean': floor_cell['holds']['modes_clean'],
        'arms_clean': floor_cell['holds']['arms_clean'],
        'modes_partition': floor_cell['holds']['modes_partition'],
        'arms_partition': floor_cell['holds']['arms_partition'],
        'modes_not_partition': floor_cell['holds']['modes_not_partition'],
        'arms_not_partition': floor_cell['holds']['arms_not_partition'],
        'modes_not_clean': floor_cell['holds']['modes_not_clean'],
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
        # ONE MECHANISM PER CELL applies to the floor's siblings too: the
        # plain Sableye floor value is a priority line for Annihilape and a
        # FOUL_PLAY damage step for Marowak, and the page named only the
        # floor cell's cause for all of them.
        'siblings_at_T': [
            {'label': c['label'], 'rank': c['rank'],
             'mech': _mech_facts(c['mech'], c)}
            for c in floor_rung['cells'] if c is not floor_cell],
        'other_cells_dropped': [
            {'label': c['label'],
             'failed': [g for g, ok in c['gates'].items() if not ok],
             'modes_ok': c['holds']['modes_ok']}
            for c in floor_rung['cells'] if not c['eligible']],
        # E3: rungs so close to this one that they are the same build target.
        # Their cells are BOUGHT by the printed line (every clearer wins them)
        # but are NOT partitioned by it: they turn over lower down, so some
        # spreads below the line win them too. Both halves are carried.
        'merged_from': [
            {'T': r['T'],
             'printed': printed_cut(r['T'], atk, field='Floor merge',
                                    ctx={'cell': r['cells'][0]['label']})[0],
             'dp': printed_cut(r['T'], atk, field='Floor merge',
                               ctx={'cell': r['cells'][0]['label']})[1],
             'n_pass': r['n_pass'],
             'n_below_floor_win': int(r['n_pass'] - floor_rung['n_pass']),
             'cells': [{'label': c['label'], 'rank': c['rank'],
                        'mech': _mech_facts(c['mech'], c)}
                       for c in r['cells']]}
            for r in floor_rung.get('merged_from', [])],
        'merge_tol': MERGE_SPREAD_TOL,
    }
    _catch = catch_model(floor_mask, meta, facts['acquisition'])
    facts['catch'] = _catch.pop('rows')
    facts['catch_model'] = _catch
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
    facts['rungs_above_tail'] = _tail_sentence(tail, atk)
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
    facts['alternative'] = _alt_facts(alt, state, meta, win, n_iv, ranks,
                                      triage, state['opponent_names'])
    facts['alt_catch'], facts['alt_catch_model'] = _alt_catch(
        alt, meta, facts['acquisition'])

    facts['examples'] = stage8_examples(meta, win, floor_mask, contested_cells,
                                        sp, sp_rank)
    facts['rank1'] = stage11_rank1(meta, sp, win, rungs, floor_rung, atk, n_iv,
                                   atk_cuts, contested_cells)
    facts['rank1']['in_alternative'] = bool(
        alt is not None and alt['mask'][facts['rank1']['i']])
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


def _mech_facts(mech, cut=None):
    if mech['kind'] == 'cmp':
        b = mech['build']
        out = {'kind': 'cmp', 'line': mech['line'],
               'on_the_line': bool(mech.get('on_the_line')),
               'opp_ivs': b['ivs'], 'opp_level': b['level'],
               'opp_cmp_atk': b['cmp_atk'], 'opp_atk': b['atk'],
               'opp_def': b['def'], 'opp_hp': b['hp']}
        if cut is not None:
            # The gap the plan's worked sentence prints and round 2 dropped:
            # "= 148.0531, inside the boundary (148.0106, 148.1040]". Without
            # it a reader sees a product that is not the cut and concludes the
            # page has an arithmetic error.
            out['gap_lo'] = cut['prev_attained']
            out['gap_hi'] = cut['T']
        return out
    if mech['kind'] == 'breakpoint':
        d = mech['detail']
        b = mech.get('build')
        return {'kind': 'breakpoint', 'move': d['move'], 'from': d['from'],
                'to': d['to'], 'def_stage': d['def_stage'],
                'atk_stage': d['atk_stage'],
                # The headline names the build the step was measured against,
                # the same way the priority clause names the one it compared.
                'opp_ivs': (b['ivs'] if b else None),
                'opp_level': (b['level'] if b else None)}
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
    pr, dp = printed_cut(r['T'], atk, field='Rung', ctx={'cell': names[0]})
    return {
        'T': r['T'], 'printed': pr, 'dp': dp,
        'n_pass': r['n_pass'], 'pool_share': r['pool_share'],
        'names': shown, 'omitted': omitted, 'n_cells': len(names),
        'ranks': [c['rank'] for c in r['cells'][:NAME_CAP]],
        'modes_ok': r['modes_ok'], 'modes_ok_min': r['modes_ok_min'],
        'modes_total': r['modes_total'],
        'arms_ok': r['arms_ok'], 'arms_ok_min': r['arms_ok_min'],
        'arms_total': r['arms_total'],
        # ONE MECHANISM PER CELL, not one per rung. A rung is a VALUE, and the
        # cells sharing it need not share a cause: plain Sableye's 123.41 rung
        # owns 0v0 Marowak (a Foul Play 42 -> 43 breakpoint) and 0v1
        # Annihilape (the 1.0 x 123.3776 priority line that the Shadow Sableye
        # page prints as its own floor). Labelling the whole row with cells[0]
        # told the two Sableye pages different stories about the same 2220
        # spreads.
        'mechs': [_mech_facts(c['mech'], c) for c in r['cells'][:NAME_CAP]],
        'mech': _mech_facts(r['cells'][0]['mech'], r['cells'][0]),
        'gates_failed': [g for g, ok in r['gates'].items() if not ok],
        'cogates': [],
    }


def _tail_sentence(tail, atk):
    """Counts and values for the "beyond the last printed rung" sentence.

    The two thresholds it names are >= selectors like every other printed
    line, so they go through printed_cut: the first build rendered them with
    round-to-nearest, which made "the highest at 156.30" select 6 spreads
    where the rung holds 9, and printed the same 150.607 value as "150.61"
    here and "150.60" one arm over.
    """
    if not tail:
        return {'n_rungs': 0, 'n_cells': 0, 'max_T': None, 'max_pool': None,
                'examples': []}
    cells = sum(len(r['cells']) for r in tail)
    top = max(tail, key=lambda r: r['T'])
    fat = max(tail, key=lambda r: r['pool_share'])
    top_pr, top_dp = printed_cut(top['T'], atk, field='Rung tail',
                                 ctx={'cell': top['cells'][0]['label']})
    fat_pr, fat_dp = printed_cut(fat['T'], atk, field='Rung tail',
                                 ctx={'cell': fat['cells'][0]['label']})
    return {
        'n_rungs': len(tail), 'n_cells': cells,
        'max_T': top['T'], 'max_printed': top_pr, 'max_dp': top_dp,
        'max_n_pass': top['n_pass'],
        'max_pool': fat['pool_share'], 'max_pool_T': fat['T'],
        'max_pool_printed': fat_pr, 'max_pool_dp': fat_dp,
        'max_pool_n_pass': fat['n_pass'],
        'max_pool_cell': fat['cells'][0]['label'],
        'examples': [{'T': r['T'], 'label': r['cells'][0]['label'],
                      'pool_share': r['pool_share'],
                      'modes_ok': r['modes_ok']}
                     for r in sorted(tail, key=lambda x: x['T'])[:2]],
    }


def stat_threshold_str(axis, printed, dp=2):
    """'DEF >= 101.40' / 'HP >= 121'.

    HP is an integer in the blob's meta, so it prints as one EVERYWHERE. The
    dirty-threshold table was the one place that did not take this branch,
    which put "HP >= 142" and "HP >= 142.00" on the same Melmetal page and
    claimed a precision the stat does not have.
    """
    value = _n(printed) if axis == 'hp' else fmt(printed, dp)
    return f"{axis.upper()} >= {value}"


def cogate_str(c):
    return stat_threshold_str(c['axis'], c['printed'], c['dp'])


def _cogate_row(r):
    return {'axis': r['axis'], 't': r['t'], 'printed': r['printed'],
            'dp': r['dp'], 'n': r['n'], 'cell': r['label'],
            'rank': r['rank'], 'rate_outside': r['rate_outside'],
            'base_rate': r['base_rate']}


def _alt_facts(alt, state, meta, win, n_iv, ranks=None, triage=None,
               names=None):
    if alt is None:
        return None
    mask = alt['mask']

    def named(cells):
        """Cell labels with the rank inline, as every other field prints them.

        This rectangle's cell list was the one place in the document where an
        opponent appeared with no rank at all -- and on a no-floor arm it is
        the whole positive content of the brief.
        """
        out = []
        for si, oi in cells:
            label = cell_label(state, si, oi)
            rank = ranks[oi] if ranks is not None else None
            tags = []
            if rank is None:
                tags.append('mega; not a floor candidate'
                            if names and '(Mega' in names[oi] else 'unranked')
            else:
                tags.append(f"rank {int(rank)}")
            if triage is not None and triage['degenerate'].get(si):
                tags.append('degenerate scenario')
            out.append(f"{label} ({'; '.join(tags)})")
        return out

    same_hp = meta[:, 7] >= alt['hp_cut']
    def_pr, def_dp = printed_cut(alt['def_cut'], meta[same_hp, 6],
                                 field='Alternative target',
                                 ctx={'cell': 'Def x HP rectangle'})
    sp = meta[:, 5] * meta[:, 6] * meta[:, 7]
    cells_won = win[mask].reshape(int(mask.sum()), -1).sum(axis=1)
    # E12: the step the genre ends on -- "these are the spreads to look out
    # for". 114 members is too many to enumerate, but the envelope is not, and
    # it is what a reader checks a Poke Genie appraisal against.
    ivs = meta[mask, :3].astype(int)
    order = np.argsort(-sp[mask], kind='stable')[:5]
    members = meta[mask]
    envelope = {
        'atk_iv': [int(ivs[:, 0].min()), int(ivs[:, 0].max())],
        'def_iv': [int(ivs[:, 1].min()), int(ivs[:, 1].max())],
        'hp_iv': [int(ivs[:, 2].min()), int(ivs[:, 2].max())],
        'by_atk_iv': [[int(v), int((ivs[:, 0] == v).sum())]
                      for v in np.unique(ivs[:, 0])],
        'top_sp': [{'ivs': (int(members[i, 0]), int(members[i, 1]),
                            int(members[i, 2])),
                    'level': float(members[i, 3]),
                    'sp_share': float(sp[mask][i] / sp.max())}
                   for i in order],
    }
    return {
        'envelope': envelope,
        'def_cut': alt['def_cut'], 'def_printed': def_pr, 'def_dp': def_dp,
        'hp_cut': alt['hp_cut'], 'n': alt['n'],
        'share': alt['n'] / n_iv,
        'sp_share_lo': float((sp[mask] / sp.max()).min()),
        'sp_share_hi': float((sp[mask] / sp.max()).max()),
        'atk_lo': float(meta[mask, 5].min()), 'atk_hi': float(meta[mask, 5].max()),
        'guaranteed': named(alt['guaranteed']),
        'exclusive': named(alt['exclusive']),
        'n_exclusive': len(alt['exclusive']),
        'given_up': named(alt['given_up']),
        'guaranteed_cells': [cell_label(state, si, oi)
                             for si, oi in alt['guaranteed']],
        'n_guaranteed': len(alt['guaranteed']), 'n_given_up': len(alt['given_up']),
        'cells_won': [int(cells_won.min()), int(cells_won.max())],
        # A rectangle this wide is not a target: most of the grid already
        # satisfies it, so the honest reading is which MINORITY loses those
        # cells, not "build for this".
        'too_wide': bool(alt['n'] / n_iv > ALT_SHARE_REFRAME),
    }


def _alt_catch(alt_raw, meta, acquisition):
    """Encounter counts for the bulk rectangle, over the reachable grid (D7).

    The first build printed these only beside the attack floor, so the
    hardest-to-hunt targets -- a 4.2% rectangle on Melmetal, 8.1% on Furret --
    carried no acquisition cost at all, which is exactly where the number
    decides whether the advice is actionable. Round 2 printed them over all
    4096 spreads even for a species whose only sources carry a 10/10/10
    floor.
    """
    if alt_raw is None:
        return [], None
    model = catch_model(alt_raw['mask'], meta, acquisition)
    rows = model.pop('rows')
    return rows, model


def _score_row(r, atk):
    pr, dp = printed_cut(r['T'], atk, field='Score only',
                         ctx={'cell': r['label']})
    return {'T': r['T'], 'printed': pr, 'dp': dp,
            'cell': r['label'], 'below': r['below'], 'above': r['above'],
            'won': r['won'], 'rank': r['rank'], 'caveat': r['caveat'],
            'to_win': r['to_win'], 'toward_win': r['toward_win']}


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
            'has_floor': floor_rung is not None,
            'seat': ('our side is the optimised row; the mirror opponent '
                     'always baits')}


def _not_claimed(win, triage, cuts_claimed, cuts_caveat, contested_cells, state,
                 ranks, floor_rung, atk):
    """Field 13, with the two reasons a cell goes unclaimed kept apart.

    A cell can reach this field two ways: it has no clean single-stat rule at
    all, or it HAS one and G-caveat excluded it (open engine divergence
    against PvPoke). Folding the second into the first sentence would state
    something false about it, so both counts are carried and printed.
    """
    claimed = {(c['si'], c['oi']) for c in cuts_claimed}
    caveat_cells = {(c['si'], c['oi']) for c in cuts_caveat} - claimed
    unclaimed = [c for c in contested_cells if c not in claimed]
    rows = []
    mask = atk >= floor_rung['T'] if floor_rung is not None else np.ones_like(atk, bool)
    for si, oi in unclaimed:
        rate = float(win[mask, si, oi].mean()) if mask.any() else 0.0
        species, _v, _s = parse_opponent_spec(state['opponent_names'][oi])
        rows.append({'cell': cell_label(state, si, oi), 'rank': ranks[oi],
                     'rate_inside_floor': rate,
                     'has_excluded_cut': (si, oi) in caveat_cells,
                     'caveat': any(cv in species for cv in CAVEAT_SPECIES)})
    rows.sort(key=lambda r: (r['rank'] is None, r['rank'] if r['rank'] else 999))
    return {'n': len(unclaimed), 'of': triage['n_contested'], 'rows': rows,
            'n_no_rule': len(unclaimed) - len(caveat_cells),
            'n_excluded_by_caveat': len(caveat_cells)}


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


def cmp_equation(mult, cmp_atk, line, dp_options=(2, 3, 4, 5, 6, 7, 8)):
    """Places at which "mult x operand = product" closes under its OWN digits.

    Round 2 rounded the operand and the product to 2 dp independently, so the
    printed equation did not close: "1.2 x 123.38 = 148.05" (the product of
    the two printed numbers is 148.056, which renders 148.06), and the
    apparent rounding direction flipped from line to line. The fix is to find
    the least precision at which the printed product is BOTH the rendering of
    the true line and the rendering of mult x the printed operand.
    """
    for dp in dp_options:
        operand = round(float(cmp_atk), dp)
        prod = f"{mult * operand:.{dp}f}"
        if prod == f"{float(line):.{dp}f}":
            return dp, f"{operand:.{dp}f}", prod
    dp = dp_options[-1]
    return dp, f"{float(cmp_atk):.{dp}f}", f"{float(line):.{dp}f}"


def cmp_gap_clause(mech, dp):
    """", inside the gap (lo, hi]" at a precision that keeps the line inside.

    The bounds are widened by the rendering (lo floors, hi ceils) so the
    printed interval always CONTAINS the true one; the clause is dropped
    rather than printed narrow if no precision up to 8 places keeps the
    printed line strictly inside it.
    """
    lo, hi = mech.get('gap_lo'), mech.get('gap_hi')
    if lo is None or hi is None or not math.isfinite(float(lo)):
        return ''
    line = float(mech['line'])
    for d in range(dp, 9):
        scale = 10.0 ** d
        plo = math.floor(float(lo) * scale) / scale
        phi = math.ceil(float(hi) * scale) / scale
        pline = float(f"{line:.{d}f}")
        if plo < pline <= phi:
            return (f", which falls in the gap ({plo:.{d}f}, {phi:.{d}f}] "
                    f"between the last attainable attack below the cut and "
                    f"the cut itself")
    return ''


def _mech_sentence(mech, shadow, opponent):
    """One sentence naming the closed-form cause, or saying there is none."""
    if mech['kind'] == 'cmp':
        mult = SHADOW_ATK_BONUS if shadow else 1.0
        dp, operand, product = cmp_equation(mult, mech['opp_cmp_atk'],
                                            mech['line'])
        a, d, s = mech['opp_ivs']
        return (f"Mechanism: charge-move priority against {opponent}. That "
                f"{opponent} is built at {a}/{d}/{s}, "
                f"L{fmt(mech['opp_level'], 1)}, {operand} attack; "
                f"{fmt(mult, 1)} x {operand} = {product}"
                + cmp_gap_clause(mech, dp) + ".")
    if mech['kind'] == 'breakpoint':
        stage = ''
        if mech['def_stage']:
            stage = f" at opponent Def stage {mech['def_stage']:+d}"
        if mech['atk_stage']:
            stage += f" at focal Atk stage {mech['atk_stage']:+d}"
        return (f"Mechanism: {mech['move']} damage steps {mech['from']} -> "
                f"{mech['to']} across the cut{stage}.")
    return "Mechanism unattributed: no priority line and no damage step sits in the gap."


def _cell_names(row, with_rank=False):
    """The row's cells, optionally with the rank tag D3 requires inline.

    A rank-251 rung was typographically identical to a rank-12 one in the
    first build's tables, even though the Dropped line and the co-gate table
    both printed rank -- which made it read as an oversight rather than a
    decision.
    """
    if not with_rank:
        out = list(row['names'])
    else:
        out = []
        for i, name in enumerate(row['names']):
            rank = row['ranks'][i] if i < len(row['ranks']) else None
            if rank is None:
                tag = ('mega; not a floor candidate'
                       if '(Mega' in name else 'unranked')
            else:
                tag = f"rank {int(rank)}"
            out.append(f"{name} ({tag})")
    if row['omitted']:
        out.append(f"+{row['omitted']} more cells")
    return ', '.join(out)


def _rung_mech_text(row, shadow):
    """One mechanism clause PER NAMED CELL, grouped when they agree."""
    groups = []
    for i, name in enumerate(row['names']):
        mech = (row['mechs'][i] if i < len(row.get('mechs') or [])
                else row['mech'])
        text = _mech_sentence(mech, shadow, name.split(' ', 1)[1])
        if mech.get('on_the_line'):
            text += ' ' + TIE_ON_THE_LINE
        if groups and groups[-1][0] == text:
            groups[-1][1].append(name)
        else:
            groups.append([text, [name]])
    if len(groups) == 1:
        return groups[0][0]
    return ' '.join(f"{', '.join(names)}: {text}" for text, names in groups)


def _settings_col(row):
    """'4/4', or '2-4 of 4' when the cells sharing this rung disagree."""
    lo, hi, tot = row['modes_ok_min'], row['modes_ok'], row['modes_total']
    if lo == hi:
        return f"{_n(hi)}/{_n(tot)}"
    return f"{_n(lo)}-{_n(hi)} of {_n(tot)}"


def _rung_line(row, dp_default=2):
    parts = [f"Atk >= {fmt(row['printed'], row['dp'])}",
             f"{_n(row['n_pass'])} spreads ({pct(row['pool_share'])})",
             _cell_names(row)]
    return '  '.join(parts)


# ---------------------------------------------------------------------------
# The headline verdict
# ---------------------------------------------------------------------------

def headline_value(printed, dp):
    """Item 5: two places for reading, the proven selector only when forced.

    The headline is a sentence a reader says out loud, so it prints two
    decimal places. When stage 7 had to escalate past two places the 2-dp
    rendering is NOT a valid ">=" selector -- plain Sableye's 123.42 selects
    a different set from 123.419 -- so the proven value follows in
    parentheses and the field below prints it alone.
    """
    if dp <= 2:
        return fmt(printed, 2)
    return f"{fmt(printed, 2)} ({fmt(printed, dp)})"


def _matchup(label, rank=None):
    """'0v1 Annihilape' -> 'the 0v1 against Annihilape (rank 30)'.

    The parenthetical rather than a comma because the phrase is used mid
    sentence -- "it decides the 0v1 against Annihilape, rank 30, outright"
    reads as a list of three things.
    """
    scen, name = label.split(' ', 1)
    if rank is None:
        return f"the {scen} against {name}"
    # A name that already ends in a parenthesis ("Snorlax (Shadow)") would
    # otherwise collect a second one, which reads as a typo.
    sep = ', rank {}' if name.endswith(')') else ' (rank {})'
    return f"the {scen} against {name}" + sep.format(int(rank))


def _and_list(items):
    """'a', 'a and b', 'a, b and c' -- prose, not a machine list."""
    items = list(items)
    if len(items) <= 1:
        return ''.join(items)
    return ', '.join(items[:-1]) + ' and ' + items[-1]


def _of_n(ok, total):
    """'all 4' / '3 of the 4' -- the count a reader hears."""
    return f"all {_n(total)}" if int(ok) == int(total) else \
        f"{_n(ok)} of the {_n(total)}"


def _stat_phrase(axis, printed, dp=2):
    """'148.29 defense' / '121.83 attack' / '135 HP' -- the spoken form."""
    word = {'atk': 'attack', 'def': 'defense', 'hp': 'HP'}[axis]
    value = _n(printed) if axis == 'hp' else fmt(printed, dp)
    return f"{value} {word}"


def _headline_mech_clause(fl, opp):
    """One clause of cause, and the ONE inline definition of priority."""
    m = fl['mech']
    if m['kind'] == 'cmp':
        return (f"That is the charge-move-priority line against a "
                f"PvPoke-default {opp}, {_ivs(m['opp_ivs'])}: when both sides "
                f"throw a charged move on the same turn, the higher attack "
                f"goes first.")
    if m['kind'] == 'breakpoint':
        build = (f" ({_ivs(m['opp_ivs'])})" if m.get('opp_ivs') else '')
        return (f"That is where {m['move']} starts doing {_n(m['to'])} damage "
                f"to a PvPoke-default {opp}{build} instead of "
                f"{_n(m['from'])}.")
    return ''


def _headline_coverage_clause(facts, fl, opp):
    """The one sentence that says how far the line travels, and to what."""
    cov = facts.get('coverage')
    if cov:
        rows = {r['label']: r for r in cov['rows']}
        row = rows.get('hundo (15/15/15)') or cov['rows'][-1]
        return (f"It is built for the default {opp}; a "
                f"{'hundo' if row['label'].startswith('hundo') else row['label']} "
                f"{opp} moves it to "
                f"{headline_value(row['printed'], row['dp'])}, and the ladder "
                f"further down has the rest.")
    if fl['mech']['kind'] == 'breakpoint':
        return (f"It is built for the default {opp}; a bulkier {opp} moves "
                f"the damage step, and a damage step has no ladder to walk.")
    return f"It is built for the default {opp}, and nothing below walks it."


def _headline_decides(fl, n_iv):
    """What the line actually settles, in the words its primitive allows."""
    m = _matchup(fl['cell'], fl['rank'])
    if fl['kind'] == 'exact':
        return (f"It decides {m} outright: every spread at or above it wins "
                f"that fight, and every spread below it loses.")
    if fl['gate_side'] == 'necessary':
        return (f"No spread below it wins {m}, and it wins that fight for all "
                f"but {_n(fl['n_above'] - fl['n_win_above'])} of the "
                f"{_n(fl['n_above'])} spreads above the line.")
    if fl['gate_side'] == 'sufficient':
        return (f"Every one of the {_n(fl['n_above'])} spreads at or above it "
                f"wins {m}; {_n(fl['n_win_below'])} of the "
                f"{_n(fl['n_below'])} below it {_verb(fl['n_win_below'])} "
                f"that fight too.")
    return (f"It calls {m} right for all but {_n(fl['n_wrong'])} of the "
            f"{_n(n_iv)} spreads: {_n(fl['n_win_above'])} of "
            f"{_n(fl['n_above'])} above it win, against "
            f"{_n(fl['n_win_below'])} of {_n(fl['n_below'])} below.")


def _headline_merged(fl):
    """The matchups a merged line also takes, with the weaker claim kept."""
    merged = fl.get('merged_from') or []
    if not merged:
        return []
    names = _and_list([_matchup(c['label'], c['rank'])
                       for m in merged for c in m['cells']])
    n_cells = sum(len(m['cells']) for m in merged)
    extra = max(m['n_below_floor_win'] for m in merged)
    them = 'them' if n_cells > 1 else 'it'
    return [f"The same line also takes {names}, though up to {_n(extra)} of "
            f"the {_n(fl['n_below'])} builds below it win {them} too."]


def _headline_rungs(rungs):
    """The next one or two steps up, each with what it adds."""
    if not rungs:
        return (f"No higher line keeps {pct(RUNG_POOL_MIN, 0)} of the grid, "
                f"so this is the last step this page names.")
    bits = []
    for r in rungs:
        adds = _and_list([_matchup(n) for n in r['names']]
                         + ([f"{_n(r['omitted'])} more"] if r['omitted']
                            else []))
        bits.append(f"{headline_value(r['printed'], r['dp'])} attack, which "
                    f"adds {adds}")
    if len(bits) == 1:
        return f"The next step up is {bits[0]}."
    return f"The next steps up are {bits[0]}; then {bits[1]}."


def _headline_bulk(alt, facts):
    """The bulk fork as a stat pair and the two counts it trades."""
    reach = _reach_clause(facts.get('alt_catch_model'), noun='pair')
    if alt is None:
        return (f"No defense-and-HP pair of {_n(ALT_MIN_MEMBERS)} spreads or "
                f"more wins a matchup the attack line cannot, so there is no "
                f"second target to name.")
    pair = (f"{fmt(alt['def_printed'], alt['def_dp'])} defense with "
            f"{_n(alt['hp_cut'])} HP")
    return (f"Trading attack for bulk -- {pair}, {_n(alt['n'])} spreads -- "
            f"gives up {_n(alt['n_given_up'])} "
            f"{_noun(alt['n_given_up'], 'matchup')} the line holds and picks "
            f"up {_n(alt['n_guaranteed'])} it gives away." + reach)


def build_headline(facts):
    """One or two paragraphs in the voice of an expert dive post.

    V2. Rounds 1-3 wrote the verdict in the machinery's own vocabulary --
    partition counts, gap intervals, "cells", "clearers", the pool share of a
    "one-sided gate" -- which is the language of the audit and not of a
    reader deciding which Sableye to power up. Every number here is still a
    template over a computed fact, and every one of them is printed again,
    with its arithmetic and its precision, in the fields below; what changed
    is that the arithmetic stays down there. G-voice is the gate that keeps
    it that way.
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

    opp = floor['cell'].split(' ', 1)[1]
    first = [
        f"Most {who} running {h['arm_label']} in {league} should have at "
        f"least {headline_value(floor['printed'], floor['dp'])} attack.",
        f"{_n(floor['n_pass'])} of the {_n(h['n_iv'])} IV spreads "
        f"({pct(floor['pool_share'])}) reach it.",
        _headline_decides(floor, h['n_iv']),
        _headline_mech_clause(floor, opp),
    ]
    first.extend(_headline_merged(floor))
    if floor['arms_total'] == 1:
        movesets = ("the only moveset baked here" if floor['arms_ok']
                    else "not in the only moveset baked here")
    else:
        movesets = (f"{_of_n(floor['arms_ok'], floor['arms_total'])} movesets "
                    f"baked here")
    first.append(
        f"It points the same way in "
        f"{_of_n(floor['modes_ok'], floor['modes_total'])} baked opponent-IV "
        f"settings and in {movesets}.")
    first.append(_headline_coverage_clause(facts, floor, opp))

    if r1['clears_floor']:
        second = [f"The stat-product rank-1 spread, {_ivs(r1['ivs'])}, already "
                  f"clears it, so there is nothing to trade away here."]
    else:
        second = [f"The stat-product rank-1 spread, {_ivs(r1['ivs'])}, misses "
                  f"it by {fmt(r1['shortfall'])} attack, and wins "
                  f"{_n(r1['total_won'])} of its {_n(r1['total_cells'])} "
                  f"matchups."]
    second.append(_headline_rungs(facts['rungs_above'][:2]))
    second.append(_headline_bulk(alt, facts))
    second.append(
        f"{_n(nc['n_no_rule'])} of the {_n(nc['of'])} contested matchups turn "
        f"on no single stat at all, and this page does not claim them.")
    return [' '.join(x for x in first if x), ' '.join(second)]


def _merged_cell_names(m):
    return ', '.join(
        f"{c['label']} (rank {int(c['rank'])})" if c['rank'] is not None
        else f"{c['label']} (unranked)" for c in m['cells'])


def _ivs(t):
    return f"{t[0]}/{t[1]}/{t[2]}"


def _verb(n):
    """'wins' / 'win' -- a template seam a reader notices on a page."""
    return 'wins' if int(n) == 1 else 'win'


def _noun(n, word):
    """'1 cell' / '2 cells' -- a template seam a reader notices on a page."""
    return word if int(n) == 1 else word + 's'


def _reach_clause(model, noun='rectangle'):
    """The rectangle's reachability, wherever the rectangle is named.

    Putting this only in field 8's acquisition line left the HEADLINE telling
    a Deoxys or Melmetal reader to build for a rectangle no encounter can
    produce -- the same defect the acquisition line was fixed for, one field
    up and in the sentence a reader actually reads.
    """
    if not model or not model.get('restricted'):
        return ''
    if model['n_reachable'] == 0:
        return (f" No spread inside it is reachable from a raid, research or "
                f"trade encounter: all {_n(model['n_grid'])} spreads those "
                f"sources can produce have every IV at {_n(IV_FLOOR)} or "
                f"better, and none of them is in the {noun}.")
    return (f" {_n(model['n_reachable'])} of the {_n(model['n_grid'])} "
            f"spreads a raid, research or trade encounter can produce "
            f"({pct(model['share'])}) are inside it.")


def near_line_row(dirty):
    """The top dirty row when it is a ONE-SIDED GATE or NEAR-EXACT (E2).

    A value with nothing winning below it is a build line by the genre's
    standard even when the rate above it is under 100% (Altaria 2v2 Clodsire:
    0 of 2009 below, 1897 of 2087 above), and so is one that misclassifies a
    single spread in 4096 (Furret 1v1 Lapras). Rounds 1 and 2 opened those
    pages with "nothing on this arm is a build line to hunt for" and then
    printed the rule one sentence later, which told the reader the opposite of
    what the numbers say.
    """
    if not dirty:
        return None
    d = dirty[0]
    if d.get('one_sided') or d.get('near_exact'):
        return d
    return None


def _closest_sentence(d, n_iv):
    """The closest rule to a line, in words, with its own numbers (item 3)."""
    where = _matchup(d['cell'], d['rank'])
    rule = _stat_phrase(d['axis'], d['printed'], d['dp'])
    if near_line_row([d]) is not None and d.get('one_sided'):
        if d.get('gate_side') == 'sufficient':
            return (f"The closest thing to a line is {rule} in {where}: every "
                    f"one of the {_n(d['n_above'])} spreads at or above it "
                    f"wins, and {_n(d['n_win_below'])} of the "
                    f"{_n(d['n_below'])} below it "
                    f"{_verb(d['n_win_below'])} too.")
        return (f"The closest thing to a line is {rule} in {where}: nothing "
                f"below it wins, and {_n(d['n_win_above'])} of the "
                f"{_n(d['n_above'])} spreads at or above it do.")
    if d.get('near_exact'):
        return (f"The closest thing to a line is {rule} in {where}, which "
                f"calls that fight right for all but {_n(d['n_wrong'])} of "
                f"the {_n(n_iv)} spreads.")
    return (f"The closest thing to a line is {rule} in {where}: "
            f"{_n(d['n_win_above'])} of the {_n(d['n_above'])} spreads at or "
            f"above it win, against {_n(d['n_win_below'])} of the "
            f"{_n(d['n_below'])} below.")


def _headline_no_floor(facts, who, league):
    """D12 in plain English: the negative, what to do instead, the evidence.

    A "no line" page is a result, not an absence, so it opens by saying what
    it is and what to build for, and follows with the closest rule in its own
    numbers. The census of exact cuts by axis, which rounds 1-3 put in this
    paragraph, is in field 2 -- it answers "why is there no line", which is
    the audit's question and not the reader's.
    """
    h = facts['header']
    r1 = facts['rank1']
    alt = facts['alternative']
    dirty = facts['dirty_thresholds']
    gb = facts['grid_best']
    lead = (f"No single stat threshold decides a matchup for {who} running "
            f"{h['arm_label']} in {league}")
    if gb['total'] - r1['total_won'] <= 0:
        first = [lead + ", and no spread on this grid wins more matchups "
                        "than the stat-product rank-1 one."]
    else:
        first = [lead + "; build for stat product."]
    if dirty:
        first.append(_closest_sentence(dirty[0], h['n_iv']))
    else:
        first.append(
            f"No matchup against a top-{_n(RANK_GATE)} opponent even has a "
            f"rough threshold that beats predicting one outcome for every "
            f"spread.")

    second = []
    if alt is None:
        second.append(
            f"No defense-and-HP pair of {_n(ALT_MIN_MEMBERS)} spreads or more "
            f"wins a matchup the rest of the grid does not, so the answer "
            f"here is stat product.")
    elif alt['too_wide']:
        pair = (f"{fmt(alt['def_printed'], alt['def_dp'])} defense with "
                f"{_n(alt['hp_cut'])} HP")
        second.append(
            f"Bulk does not separate either: the only defense-and-HP pair "
            f"that buys anything, {pair}, is already {pct(alt['share'])} of "
            f"the grid.")
    else:
        pair = (f"{fmt(alt['def_printed'], alt['def_dp'])} defense with "
                f"{_n(alt['hp_cut'])} HP")
        second.append(
            f"What bulk does carry is {pair}: {_n(alt['n'])} spreads "
            f"({pct(alt['share'])}) that win "
            f"{_n(alt['n_exclusive'])} contested "
            f"{_noun(alt['n_exclusive'], 'matchup')} -- "
            + _cap_list(alt['exclusive'])
            + f" -- where at most {pct(ALT_MAX_CLEARER_RATE, 0)} of the "
              f"spreads outside them do."
            + _reach_clause(facts.get('alt_catch_model'), noun='pair'))
    second.append(
        f"The stat-product rank-1 spread, {_ivs(r1['ivs'])} at "
        f"L{fmt(r1['level'], 1)}, wins {_n(r1['total_won'])} of its "
        f"{_n(r1['total_cells'])} matchups"
        + (", and is inside that pair." if r1.get('in_alternative')
           else ", and is outside that pair."
                if alt is not None else "."))
    second.append(_grid_best_sentence(facts))
    return [' '.join(first), ' '.join(second)]


def _grid_best_sentence(facts):
    """E5: the size of the decision, as a measured matchup count.

    This is the best sentence on a no-line page -- it is the one that says
    how much the IV choice is worth at all -- so v2 keeps it verbatim except
    for the two nouns G-voice bars from the headline.
    """
    gb = facts['grid_best']
    r1 = facts['rank1']
    gap = gb['total'] - r1['total_won']
    if gap <= 0:
        return (f"No spread on this grid wins more matchups than rank-1 does, "
                f"so the whole IV decision here is zero matchups wide.")
    tied = (f" ({_n(gb['n_tied'])} spreads tie for that count)"
            if gb['n_tied'] > 1 else '')
    return (f"The spread winning the most matchups on this grid is "
            f"{_ivs(gb['ivs'])} with {_n(gb['total'])} of "
            f"{_n(gb['total_cells'])}{tied}, so the whole IV decision here is "
            f"{_n(gap)} {_noun(gap, 'matchup')} wide.")


# ---------------------------------------------------------------------------
# The at-a-glance strip (item 4): five labelled values above the headline
# ---------------------------------------------------------------------------

STRIP_LABELS_FLOOR = ('Line', 'Decides', 'Rank-1', 'Alternative',
                      'Not claimed')
STRIP_LABELS_NONE = ('Line', 'Closest', 'Rank-1', 'Alternative',
                     'Decision width')


def build_strip(facts):
    """Five short labelled lines: values only, no prose.

    A reader scanning five moveset sections wants the five numbers that
    differ between them before reading a word of any of them. Every value
    here is printed again inside the section, so the strip adds no claim --
    only an index.
    """
    h = facts['header']
    fl = facts['floor']
    r1 = facts['rank1']
    alt = facts['alternative']
    rect = ('none' if alt is None else
            f"Def >= {fmt(alt['def_printed'], alt['def_dp'])}, HP >= "
            f"{_n(alt['hp_cut'])} ({_n(alt['n'])} spreads, "
            f"{pct(alt['share'])})")
    if fl is not None:
        line = (f"Atk >= {headline_value(fl['printed'], fl['dp'])} "
                f"[{PRIMITIVE_HEADLINE_BADGE[fl['kind']]}] -- "
                f"{_n(fl['n_pass'])} of {_n(h['n_iv'])} spreads "
                f"({pct(fl['pool_share'])})")
        decides = f"{fl['cell']}, rank {fl['rank']}"
        rank1 = (f"{_ivs(r1['ivs'])} -- clears it"
                 if r1['clears_floor'] else
                 f"{_ivs(r1['ivs'])} -- {fmt(r1['shortfall'])} attack short")
        nc = facts['not_claimed']
        last = (f"{_n(nc['n_no_rule'])} of {_n(nc['of'])} contested matchups",)
        values = (line, decides, rank1, rect) + last
        return list(zip(STRIP_LABELS_FLOOR, values))
    dirty = facts['dirty_thresholds']
    if dirty:
        d = dirty[0]
        closest = (f"{stat_threshold_str(d['axis'], d['printed'], d['dp'])} "
                   f"-- {d['cell']}, rank {d['rank']}, "
                   f"{_n(d['n_wrong'])} of {_n(h['n_iv'])} spreads on the "
                   f"wrong side")
    else:
        closest = 'none'
    gb = facts['grid_best']
    gap = max(0, gb['total'] - r1['total_won'])
    values = ('none',
              closest,
              f"{_ivs(r1['ivs'])} -- wins {_n(r1['total_won'])} of "
              f"{_n(r1['total_cells'])}",
              rect,
              f"{_n(gap)} {_noun(gap, 'matchup')}")
    return list(zip(STRIP_LABELS_NONE, values))


# ---------------------------------------------------------------------------
# The fifteen fields
# ---------------------------------------------------------------------------

def _field(n, title, lines=None, head=None, rows=None, note=None):
    return {'n': n, 'title': title, 'lines': lines or [], 'head': head,
            'rows': rows or [], 'note': note}


# E11: the fifteen fields in the reader's question order, not in the order
# the stages derive them. Floor + Examples answers "what do I hunt and what
# does it look like"; Rank-1 + Alternative + Cost answers "do I already have
# one and what does it cost"; everything after is the ladder and the audit.
# The contract is the fifteen fields BY NAME, and no field's content changes
# here -- only its position, and the number it is printed with.
FIELD_ORDER = ('_f1_header', '_f2_floor', '_f9_examples', '_f4_rank1',
               '_f8_alternative', '_f10_cost', '_f5_rungs_above',
               '_f6_rungs_below', '_f7_bulk', '_f3_coverage', '_f11_mirror',
               '_f12_score_only', '_f13_not_claimed', '_f14_how_sure',
               '_f15_provenance')
# The stage-derivation order, kept so the reorder above is reviewable as a
# permutation of it rather than as a rewritten list.
FIELD_DERIVATION_ORDER = (
    '_f1_header', '_f2_floor', '_f3_coverage', '_f4_rank1', '_f5_rungs_above',
    '_f6_rungs_below', '_f7_bulk', '_f8_alternative', '_f9_examples',
    '_f10_cost', '_f11_mirror', '_f12_score_only', '_f13_not_claimed',
    '_f14_how_sure', '_f15_provenance')


def build_fields(facts):
    if sorted(FIELD_ORDER) != sorted(FIELD_DERIVATION_ORDER):
        raise GuardError(
            f"G-names: field=all cell=- printed='{len(FIELD_ORDER)} fields' "
            f"recomputed={len(FIELD_DERIVATION_ORDER)} "
            f"(blob=- arm=- mode=-)")
    out = []
    for i, name in enumerate(FIELD_ORDER, start=1):
        field = globals()[name](facts)
        field['n'] = i
        out.append(field)
    return out


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


def _view_cut_bit(name, v, n_iv):
    """'THUNDERBOLT 123.97 (589 spreads)' / 'HYPER_BEAM no clean cut (0.0% win)'.

    The win RATE travels with a clean cut too. A cell that another arm wins
    with 4095 of 4096 spreads has a clean cut there and is not contested at
    all; counting that as corroboration without printing the rate is the
    over-claim the round-2 Melmetal page made.
    """
    if not v['clean']:
        return f"{name}: no clean cut ({pct(v['rate'])} win)"
    free = ''
    if v['n_win'] >= n_iv - 1 or v['n_win'] <= 1:
        free = (f", won by {_n(v['n_win'])} of {_n(n_iv)} spreads -- not a "
                f"contested cell there")
    return (f"{name}: {fmt(v['printed'], v['dp'])} "
            f"({_n(v['n_pass'])} spreads{free})")


def _separability_sentence(fl, n_iv=None):
    """E4: report per-arm robustness as the cut VALUE, not as a bare count.

    Separability ("this cell has a clean cut somewhere on that arm") is a
    different measurement from the two above it and is NOT comparable with
    them, so it is printed with the values it counted rather than as a
    number a reader would read as corroboration of the printed line.
    """
    views = fl.get('per_arm_cuts') or {}
    n_iv = n_iv or 4096
    bits = [_view_cut_bit(a, v, n_iv) for a, v in views.items()]
    head = (f"Separability is a THIRD and non-comparable measurement -- each "
            f"view's OWN cut, at whatever value it sits: "
            f"{_n(fl['arms_clean'])} of {_n(fl['arms_total'])} arms and "
            f"{_n(fl['modes_clean'])} of {_n(fl['modes_total'])} settings "
            f"separate this cell at some value.")
    return head + (' Per arm -- ' + '; '.join(bits) + '.' if bits else '')


def _f2_floor(facts):
    fl = facts['floor']
    h = facts['header']
    if fl is None:
        deg = facts['degradation']
        lines = [deg['sentence'], _clean_census_sentence(facts)]
        if facts['dirty_thresholds']:
            lines.append("The closest dirty thresholds on this dive, printed "
                         "as evidence and not as lines:")
        rows = [[d['cell'], f"rank {d['rank']}",
                 stat_threshold_str(d['axis'], d['printed'], d['dp']),
                 _n(d['n_wrong']), _n(d['constant_wrong']),
                 f"{_n(d['n_win_above'])} of {_n(d['n_above'])}",
                 f"{_n(d['n_win_below'])} of {_n(d['n_below'])}"]
                for d in facts['dirty_thresholds']]
        top = facts['dirty_thresholds'][0] if facts['dirty_thresholds'] else None
        if top and top.get('genre'):
            g = top['genre']
            lines.append(
                f"At the one decimal place PvPoke and Poke Genie display, the "
                f"top row reads "
                f"{stat_threshold_str(top['axis'], g['printed'], 1)}, which "
                f"selects {_n(g['n_above'])} spreads where the exact value "
                f"selects {_n(top['n_above'])}: "
                f"{_n(g['n_extra'])} more {_noun(g['n_extra'], 'spread')} land "
                f"inside a line printed that way. The table prints the exact "
                f"value because it is the one that selects the set the counts "
                f"beside it describe.")
        if rows:
            lines.append(
                "A split is listed only when it puts fewer spreads on the "
                "wrong side than the constant rule does (predict one outcome "
                "for the whole grid) and when it keeps between "
                f"{pct(MATERIAL_LO, 0)} and {pct(MATERIAL_HI, 0)} of the grid "
                "on each side.")
        return _field(2, 'Floor', lines,
                      head=['cell', 'rank', 'closest split',
                            'spreads on the wrong side',
                            'constant rule gets wrong', 'wins at/above',
                            'wins below'],
                      rows=rows)
    lines = [
        f"Atk >= {fmt(fl['printed'], fl['dp'])} -- {_n(fl['n_pass'])} of "
        f"{_n(h['n_iv'])} spreads ({pct(fl['pool_share'])}).",
        _primitive_sentence(fl, h['n_iv']),
        _mech_sentence(fl['mech'], h['shadow'], fl['cell'].split(' ', 1)[1]),
        f"{'Owns' if fl['kind'] == 'exact' else 'Decides'}: {fl['cell']} "
        f"(rank {fl['rank']}).",
    ]
    for m in fl.get('merged_from') or []:
        lines.append(
            f"Also buys: {_merged_cell_names(m)}. Its own clean cut is "
            f"{fmt(m['printed'], m['dp'])} ({_n(m['n_pass'])} spreads), "
            f"within {pct(fl['merge_tol'], 0)} of the grid of the printed "
            f"line, so the two are reported as one build target at the "
            f"higher value. Every clearer of the printed line wins it; "
            f"{_n(m['n_below_floor_win'])} spreads below the printed line "
            f"win it too, which is why it is not part of the partition "
            f"claim above.")
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
        f"win the cell, and {below_txt}. At or above: "
        f"{_n(fl['n_win_above'])} of {_n(fl['n_above'])} win, scoring "
        f"{_n(sa[0])}-{_n(sa[1])}.")
    if fl.get('energy') and fl['energy']['below_single'] and fl['energy']['above_single']:
        lines.append(
            f"Energy at the end of the fight is {_n(fl['energy']['below'][0])} "
            f"below the cut and {_n(fl['energy']['above'][0])} at or above it: "
            f"one fight on each side, not a plan switch.")
    lines.append(
        f"Direction: the cut points the same way in {_n(fl['modes_ok'])} of "
        f"{_n(fl['modes_total'])} opponent-IV settings and "
        f"{_n(fl['arms_ok'])} of {_n(fl['arms_total'])} moveset arms (win "
        f"rate at or above it at least {pct(DIRECTION_MIN_ABOVE, 0)}, and "
        f"above the rate below it)."
        + (f" Fails in: {', '.join(fl['modes_fail'])}." if fl['modes_fail'] else ''))
    lines.append(
        f"Partition is the stricter question, asked of the SAME printed line: "
        f"it splits the cell exactly (everything at or above the line wins, "
        f"everything below it loses) in {_n(fl['modes_partition'])} of "
        f"{_n(fl['modes_total'])} settings and {_n(fl['arms_partition'])} of "
        f"{_n(fl['arms_total'])} arms. A partition implies the direction test, "
        f"never the other way round, so this count can never exceed the one "
        f"above it."
        + (f" Does not partition: {', '.join(fl['modes_not_partition'])}."
           if fl['modes_not_partition'] else ''))
    lines.append(_separability_sentence(fl, h['n_iv']))
    pm = fl.get('per_mode_cuts') or {}
    bits = []
    for m, v in pm.items():
        bits.append(f"{m} {fmt(v['printed'], v['dp'])}" if v['clean']
                    else f"{m} no clean cut ({pct(v['rate'])} win)")
    if bits:
        lines.append("The same cell's cut in each setting: " + '; '.join(bits) + ".")
    if facts['catch']:
        lines.append(_catch_sentence(facts['acquisition'], facts['catch'],
                                     "clear this line",
                                     facts.get('catch_model')))
    if fl['other_cells_at_T']:
        lines.append("Other cells turning over at the same value: "
                     + ', '.join(fl['other_cells_at_T']) + ".")
        for sib in fl.get('siblings_at_T') or []:
            lines.append(
                sib['label'] + ' -- '
                + _mech_sentence(sib['mech'], h['shadow'],
                                 sib['label'].split(' ', 1)[1]))
    if fl['mech']['kind'] == 'cmp':
        lines.append(
            "Caveat: this line exists because charge-move priority ignores the "
            "shadow x1.2 multiplier -- our engine's and PvPoke's convention, "
            "not verified against the live game."
            if h['shadow'] else
            "Caveat: charge-move priority compares the shadow-stripped attack "
            "in our engine and in PvPoke; that convention is not verified "
            "against the live game.")
        if fl['mech'].get('on_the_line'):
            lines.append(TIE_ON_THE_LINE)
    return _field(2, 'Floor', lines)


def _clean_census_sentence(facts):
    """The exact-cut census by axis. V1 opened the negative headline with it.

    It answers "why is there no line", which is the audit's question; the
    headline now answers the reader's. The wording is the round-3 sentence,
    moved verbatim except for the leading count.
    """
    cc = facts['clean_counts']
    n_clean = sum(cc.values())
    n_excl = facts.get('clean_excluded', 0)
    if not n_clean:
        return (f"No single-stat value separates any of the "
                f"{_n(facts['triage']['contested'])} contested cells exactly.")
    excl = (f", {_n(n_excl)} of them excluded for an open engine divergence, "
            f"leaving {_n(n_clean - n_excl)}" if n_excl else '')
    return (f"{_n(n_clean)} single-stat values do separate a cell exactly "
            f"({_n(cc.get('atk', 0))} on attack, {_n(cc.get('def', 0))} on "
            f"Def, {_n(cc.get('hp', 0))} on HP, over "
            f"{_n(facts['triage']['contested'])} contested cells{excl}), but "
            f"none of them clears every gate while splitting between "
            f"{pct(DECISION_BAND[0], 0)} and {pct(DECISION_BAND[1], 0)} of "
            f"the grid, which is what an exact line has to do to carry a "
            f"floor label.")


def _primitive_sentence(fl, n_iv):
    """Which of the three primitives carries the line, with its rate (E2).

    The badge is not decoration: an exact cut, a one-sided gate and a
    near-exact split make three different claims about the spreads on the
    wrong side, and a page that prints all three under one word would be
    over-claiming on two of them.
    """
    if fl['kind'] == 'exact':
        return ("Primitive: EXACT clean cut -- every spread at or above the "
                "line wins the cell and no spread below it does.")
    if fl['kind'] == 'gate' and fl['gate_side'] == 'necessary':
        return (f"Primitive: ONE-SIDED GATE (necessary) -- no spread below "
                f"the line wins the cell, and it wins for all but "
                f"{_n(fl['n_above'] - fl['n_win_above'])} of the "
                f"{_n(fl['n_above'])} spreads above the line "
                f"({pct(fl['rate_above'])} of them win, against a bar of "
                f"{pct(fl['gate_min_above'], 0)}). Clearing the line is "
                f"necessary here, not sufficient.")
    if fl['kind'] == 'gate':
        return (f"Primitive: ONE-SIDED GATE (sufficient) -- every one of the "
                f"{_n(fl['n_above'])} spreads at or above the line wins the "
                f"cell, and {_n(fl['n_win_below'])} of the "
                f"{_n(fl['n_below'])} below it win it too "
                f"({pct(fl['rate_below_loss'])} of the spreads below lose, "
                f"against a bar of {pct(fl['gate_min_above'], 0)}). Clearing "
                f"the line is sufficient here, not necessary.")
    return (f"Primitive: NEAR-EXACT -- {_n(fl['n_wrong'])} of {_n(n_iv)} "
            f"spreads sit on the wrong side of the line in total "
            f"({_n(fl['n_above'] - fl['n_win_above'])} above it that lose, "
            f"{_n(fl['n_win_below'])} below it that win), against a bar of "
            f"{_n(fl['near_exact_limit'])}.")


TIE_ON_THE_LINE = (
    "The priority line falls exactly ON the cut, so a spread sitting on it "
    "ties rather than out-prioritises; see Provenance on how the engine seats "
    "an exact tie.")


def _catch_sentence(acquisition, catch, what, model=None):
    """One acquisition line, with the model named and caveated in every class.

    The first build caveated only the shadow line, which is what made the
    "Wild catches under uniform-random IVs" line read as verified -- on
    Melmetal, a species with no wild spawn at all. Round 2 caveated every
    class but still counted over all 4096 spreads, which printed "10
    encounters" for a Deoxys rectangle no encounter can produce; the count is
    now taken over the reachable grid and the zero case is said out loud.
    """
    if model is not None and model['restricted'] and model['n_reachable'] == 0:
        return (f"No spread that can {what} is reachable from a raid, "
                f"research or trade encounter: every one of them needs an IV "
                f"below {_n(IV_FLOOR)}, and {ACQUISITION_IV_FLOOR_NOTE}. Of "
                f"the {_n(model['n_grid'])} spreads those sources can produce, "
                f"{_n(model['n_reachable'])} do. This target is reachable "
                f"only from a source with no IV floor.")
    parts = [f"{_n(c['n'])} for a {pct(c['target'], 0)} chance"
             for c in catch if c['n'] is not None]
    if not parts:
        return ''
    counts = ', '.join(parts)
    if acquisition == 'grunt':
        source = ("Rocket-grunt encounters (this is a shadow, so it cannot be "
                  "traded)")
        caveat = ("the grunt IV floor is NOT verified here, and the count "
                  "assumes uniform-random IVs over the whole grid")
    elif acquisition == 'none':
        source = ("Encounters, whatever the source (this species has no wild "
                  "spawn)")
        floor_bit = ''
        if model is not None and model['restricted']:
            floor_bit = (f" over the {_n(model['n_grid'])} spreads those "
                         f"sources can produce ({_n(model['n_reachable'])} of "
                         f"them qualify)")
        caveat = (f"the count assumes uniform-random IVs{floor_bit}, because "
                  + ACQUISITION_IV_FLOOR_NOTE)
    else:
        source = "Wild catches"
        caveat = ("the count assumes uniform-random IVs over the whole grid, "
                  "which is a model of a wild encounter and is not verified "
                  "for any other source")
    return (f"{source} needed to {what}: {counts}. Model: {caveat}.")


def _f3_coverage(facts):
    cov = facts['coverage']
    fl = facts['floor']
    if cov is None:
        # The ladder is CMP-specific: it walks the opponent's own IV grid and
        # asks which of its builds the printed line out-prioritises. A damage
        # breakpoint does not move with the opponent's attack at all, so
        # there is no ladder to print -- which is a different sentence from
        # "the mechanism is unattributed", and the first build printed the
        # latter two lines under an attributed SUPER_POWER breakpoint.
        if fl is None:
            why = "there is no floor on this arm, so there is no line to place"
        elif fl['mech']['kind'] == 'breakpoint':
            why = ("the ladder measures a priority line against the "
                   "opponent's own IV grid, and this floor is a damage "
                   "breakpoint, which does not move with the opponent's "
                   "attack")
        else:
            why = ("the floor carries no closed-form mechanism, so there is "
                   "no line to walk across the opponent's grid")
        return _field(3, 'Coverage', [f"Omitted: {why}."])
    lines = [
        f"What the printed line beats over {cov['opponent']}'s own "
        f"{_n(4096)} spreads. Strict: an exact attack tie counts as NOT "
        f"beaten, because the engine decides a priority tie by seat.",
    ]
    # One precision for the whole column: five rows at 2 dp and one at 3
    # reads as a transcription slip, and the escalated row is the one that
    # needs the places to stay a valid selector.
    col_dp = max(r['dp'] for r in cov['rows'])
    rows = [[r['label'], fmt(r['printed'], col_dp), pct(r['strict']),
             _n(r['ties']), _n(r['focal'])] for r in cov['rows']]
    if col_dp > 2:
        lines.append(
            f"The line column prints {_n(col_dp)} decimal places throughout: "
            f"at least one row needs them to stay a valid \">=\" selector "
            f"(two places would select a different set of our spreads), and "
            f"mixing precisions inside one column hides which row that is.")
    if not cov.get('monotone', True):
        hi = cov['rows'][-1]
        lines.append(
            f"The line column is not monotone, and that is a CP-cap effect "
            f"rather than a transcription error: under the cap a hundo sits "
            f"at a lower level than a low-attack spread, so it carries less "
            f"attack. The highest-attack {cov['opponent']} is "
            f"{_ivs(cov['max_ivs'])} at {fmt(hi['printed'], hi['dp'])}.")
    if cov['rows'][-1]['focal'] == 0:
        lines.append(f"No spread of ours reaches that top line at all.")
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
        f"Stat-product rank-1 is {_ivs(r1['ivs'])} "
        f"at L{fmt(r1['level'], 1)}: {fmt(r1['atk'])} attack / "
        f"{fmt(r1['def'])} Def / {_n(r1['hp'])} HP. It wins "
        f"{_n(r1['total_won'])} of {_n(r1['total_cells'])} cells "
        f"({_n(r1['contested_won'])} of the {_n(r1['n_contested'])} contested "
        f"ones)."]
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
        rows.append([f"Atk >= {fmt(r['printed'], r['dp'])}",
                     _cell_names(r, with_rank=True),
                     f"{_n(r['n_pass'])} ({pct(r['pool_share'])})",
                     _settings_col(r),
                     _rung_mech_text(r, facts['header']['shadow']),
                     arm_bits])
    lines = [
        f"A rung is listed here when it keeps {pct(RUNG_POOL_MIN, 0)} of the "
        f"grid and points the same way in at least {_n(MODES_TO_LIST)} of the "
        f"baked opponent-IV settings; the rest are in the tail sentence or "
        f"the Dropped lines below. Being listed is not being eligible as a "
        f"floor -- the floor gates are in the evidence block.",
    ]
    t = facts.get('rungs_above_tail')
    if t and t['n_rungs']:
        lines.append(
            f"Beyond {fmt(rows_src[-1]['printed'], rows_src[-1]['dp'])} there "
            f"are {_n(t['n_rungs'])} more clean rungs covering "
            f"{_n(t['n_cells'])} cells, the highest at "
            f"{fmt(t['max_printed'], t['max_dp'])} "
            f"({_n(t['max_n_pass'])} spreads); the widest of them keeps "
            f"{pct(t['max_pool'])} of the grid ({t['max_pool_cell']} at "
            f"{fmt(t['max_pool_printed'], t['max_pool_dp'])}).")
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
    has_floor = facts['floor'] is not None
    rows_src = [r for r in facts['rungs_below']
                if not has_floor or r['T'] < facts['floor']['T']]
    title = 'Material clean cuts below the floor' if has_floor \
        else 'Material clean cuts'
    if not rows_src:
        return _field(6, title,
                      ["No material rung below the floor." if has_floor
                       else "No clean cut on this arm is material."])
    # The old header said these are cuts that "most builds should clear",
    # which the rows falsify: the band runs down to 10% of the grid, so the
    # same sentence sat over an 89.7% row and a 15.8% one. The share column
    # says which is which; the header no longer claims.
    lines = [f"Clean cuts holding between {pct(MATERIAL_LO, 0)} and "
             f"{pct(MATERIAL_HI, 0)} of the grid, ascending. The widest of "
             f"them are what {SHOULD_ALLOWED_PHRASE} already; the narrow ones "
             f"at the bottom of the table are not."]
    rows = [[f"Atk >= {fmt(r['printed'], r['dp'])}",
             _cell_names(r, with_rank=True),
             f"{_n(r['n_pass'])} ({pct(r['pool_share'])})",
             _settings_col(r),
             _rung_mech_text(r, facts['header']['shadow'])]
            for r in rows_src]
    return _field(6, title, lines,
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
        # Lead with the number the brief will stand behind. The first build
        # opened with the vs-the-floor guarantee and retracted it three lines
        # later; on every floor arm in the corpus the vs-the-grid count is 0.
        if alt['n_exclusive'] == 0:
            lines.append(
                f"This is a trade, not an exclusive claim: "
                f"{_n(alt['n_exclusive'])} of the {_n(alt['n_guaranteed'])} "
                f"cells it wins with every member are won by at most "
                f"{pct(ALT_MAX_CLEARER_RATE, 0)} of the spreads OUTSIDE it, "
                f"so spreads that are in neither the rectangle nor the floor "
                f"win them too. What the rectangle buys is measured against "
                f"the floor's clearers only.")
        else:
            lines.append(
                f"{_n(alt['n_exclusive'])} of the {_n(alt['n_guaranteed'])} "
                f"cells it wins with every member are won by at most "
                f"{pct(ALT_MAX_CLEARER_RATE, 0)} of the spreads outside the "
                f"rectangle: " + _cap_list(alt['exclusive']) + ".")
        lines.append(
            f"Rule: among (Def, HP) rectangles with at least "
            f"{_n(ALT_MIN_MEMBERS)} members and no floor clearer, the one "
            f"winning the most contested cells the floor cannot (won by "
            f"every member, by at most {pct(ALT_MAX_CLEARER_RATE, 0)} of "
            f"clearers); ties broken by member count. Only cells against a "
            f"top-{_n(RANK_GATE)} opponent in a non-degenerate scenario may "
            f"select it. The printed cuts are the least attained values among "
            f"the members.")
        lines.append(
            f"Wins {_n(alt['n_guaranteed'])} "
            f"{_noun(alt['n_guaranteed'], 'cell')} with every member that the "
            f"floor does not: " + _cap_list(alt['guaranteed']) + ".")
        if alt['given_up']:
            lines.append(
                f"Gives up {_n(alt['n_given_up'])} "
                f"{_noun(alt['n_given_up'], 'cell')} the floor guarantees: "
                + _cap_list(alt['given_up']) + ".")
        else:
            lines.append("It gives up no cell the floor guarantees.")
        lines.append("No spread satisfies both this rectangle and the attack "
                     "floor.")
    elif alt['too_wide']:
        lines.append(
            f"{pct(alt['share'])} of the grid already satisfies this, so it is "
            f"not a target to hunt for. Read it the other way round: the "
            f"{pct(1.0 - alt['share'])} of spreads outside it lose "
            f"{_n(alt['n_exclusive'])} contested "
            f"{_noun(alt['n_exclusive'], 'matchup')} that every member wins: "
            + _cap_list(alt['exclusive']) + ".")
        lines.append(
            f"Rule: among (Def, HP) rectangles with at least "
            f"{_n(ALT_MIN_MEMBERS)} members, the one winning the most "
            f"contested cells with EVERY member that at most "
            f"{pct(ALT_MAX_CLEARER_RATE, 0)} of the spreads outside it win, "
            f"counting only cells against a top-{_n(RANK_GATE)} opponent in a "
            f"non-degenerate scenario; ties broken by member count.")
    else:
        lines.append(
            f"There is no attack floor on this arm, so there is nothing for "
            f"the rectangle to be disjoint from. Rule: among (Def, HP) "
            f"rectangles with at least {_n(ALT_MIN_MEMBERS)} members, the one "
            f"winning the most contested cells with EVERY member that at most "
            f"{pct(ALT_MAX_CLEARER_RATE, 0)} of the spreads outside it win, "
            f"counting only cells against a top-{_n(RANK_GATE)} opponent in a "
            f"non-degenerate scenario; ties broken by member count. The "
            f"printed cuts are the least attained values among the members.")
        lines.append(
            f"Wins {_n(alt['n_exclusive'])} contested "
            f"{_noun(alt['n_exclusive'], 'cell')} that way: "
            + _cap_list(alt['exclusive']) + ".")
    acm = facts.get('alt_catch_model')
    if acm and acm.get('restricted'):
        lines.append(_reach_clause(acm).strip())
    if facts.get('alt_catch') and not alt['too_wide']:
        sentence = _catch_sentence(facts['acquisition'], facts['alt_catch'],
                                   "land inside this rectangle", acm)
        if sentence:
            lines.append(sentence)
    lines.append(f"Members win {_n(alt['cells_won'][0])}-"
                 f"{_n(alt['cells_won'][1])} cells in total.")
    env = alt.get('envelope')
    if env:
        counts = ', '.join(f"{_n(v)}: {_n(c)}" for v, c in env['by_atk_iv'])
        lines.append(
            f"IV envelope of the members -- attack IV "
            f"{_n(env['atk_iv'][0])}-{_n(env['atk_iv'][1])}, Def IV "
            f"{_n(env['def_iv'][0])}-{_n(env['def_iv'][1])}, HP IV "
            f"{_n(env['hp_iv'][0])}-{_n(env['hp_iv'][1])}. Members per attack "
            f"IV: {counts}.")
        lines.append(
            "Highest stat product inside it: "
            + ', '.join(f"{_ivs(m['ivs'])} at L{fmt(m['level'], 1)} "
                        f"({pct(m['sp_share'], 2)} of rank-1)"
                        for m in env['top_sp']) + ".")
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
                     _n(e['contested_cells']), _n(e['total'])])
    lines = ["Existence proofs; each selection rule is printed with its spread."]
    if facts['floor'] is None:
        lines.append(
            "There is no attack floor on this arm, so the rules run over the "
            "whole grid rather than over a set of clearers.")
        lines.append(_grid_best_sentence(facts))
    # The scenario labels come from the blob, not from a hardcoded list: a
    # blob with a different scenario order would otherwise mislabel the row
    # silently instead of failing.
    sc = list(facts['header']['scenarios'])
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
    for row in tail_rows:
        if len(row) != len(fields['extra_head']):
            raise GuardError(
                f"G-names: field=Example spreads cell=- "
                f"printed='{len(row)} cells' "
                f"recomputed={len(fields['extra_head'])} header columns "
                f"(blob=- arm=- mode=-)")
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
    # With no floor there is no below/above split, so those two columns are
    # dropped rather than filled with nine rows of "-".
    if m['has_floor']:
        head = ['shields', 'win rate below the floor', 'win rate at/above',
                'win rate over the whole grid']
        for r in m['rows']:
            rows.append([r['scenario'], pct(r['below']), pct(r['above']),
                         pct(r['rate'])])
    else:
        head = ['shields', 'win rate over the whole grid']
        for r in m['rows']:
            rows.append([r['scenario'], pct(r['rate'])])
    for rm in m['rank1_modes']:
        lines.append(
            f"Against a mirror built at {MODE_PROSE.get(rm['mode'], rm['mode'])}, "
            f"the count of our spreads (of {_n(facts['header']['n_iv'])}) that "
            f"win, by shield scenario 0v0 through 2v2: "
            + ' '.join(_n(v) for v in rm['per_scenario']) + ".")
    return _field(11, 'Mirror', lines, head=head, rows=rows)


def _f12_score_only(facts):
    rows_src = facts['score_only']
    if not rows_src:
        return _field(12, 'Changes the score, not the matchup', ["None."])
    lines = [f"Cells won (or lost) by every spread where the battle score "
             f"still steps by at least {_n(SCORE_STEP_MIN)} at one attainable "
             f"attack value.",
             f"Ordered by how close the step comes to the win line "
             f"({_n(WIN_RATING)}), nearest first: the question this field "
             f"answers is how close a cell is to becoming a matchup, not how "
             f"large the swing inside it is."]
    shown = rows_src[:SCORE_ROW_CAP]
    # A caveat cell carries its marker wherever it is named, and sorts last
    # (stage 10). The first build led this table with the Aegislash cell that
    # field 10 excludes from the cost diff as an open engine divergence.
    rows = [[f"Atk >= {fmt(r['printed'], r['dp'])}",
             r['cell'] + (CAVEAT_MARK if r.get('caveat') else ''),
             f"rank {r['rank']}" if r['rank'] else 'unranked',
             f"{_n(r['below'])} -> {_n(r['above'])}",
             _n(r['to_win']) + (' (closing)' if r['toward_win']
                                else ' (widening)'),
             'won on both sides' if r['won'] else 'lost on both sides']
            for r in shown]
    if len(rows_src) > len(shown):
        lines.append(f"{_n(len(shown))} of {_n(len(rows_src))} steps are "
                     f"listed, closest to the win line first; "
                     f"{_n(len(rows_src) - len(shown))} more are not.")
    return _field(12, 'Changes the score, not the matchup', lines,
                  head=['value', 'cell', 'rank', 'score step',
                        f"points from {_n(WIN_RATING)}", 'outcome'],
                  rows=rows)


NOT_CLAIMED_ROW_CAP = 6


def _f13_not_claimed(facts):
    nc = facts['not_claimed']
    fl = facts['floor']
    where = "inside the floor" if fl is not None else "over the whole grid"
    lines = [f"{_n(nc['n_no_rule'])} of {_n(nc['of'])} contested matchups have "
             f"no clean single-stat rule and are not claimed."]
    if nc['n_excluded_by_caveat']:
        lines.append(
            f"A further {_n(nc['n_excluded_by_caveat'])} "
            f"{_noun(nc['n_excluded_by_caveat'], 'matchup')} "
            f"{'has' if nc['n_excluded_by_caveat'] == 1 else 'have'} a clean "
            f"rule that is EXCLUDED rather than printed: "
            f"{', '.join(CAVEAT_SPECIES)} carries an open engine divergence "
            f"against PvPoke (see the mechanics note), so its cuts are kept "
            f"out of the floor, the rungs and the cost totals.")
    eligible = [r for r in nc['rows'] if r['rank'] and r['rank'] <= RANK_GATE]
    # E10: selected by how close the matchup is to a coin flip, deduped to one
    # row per base species. Selecting by rank spent all six slots on three
    # opponents and on cells sitting at 100.0% or 0.0%, which are exactly the
    # matchups an IV spread does not decide. The rows a reader needs named are
    # the ones near 50%.
    by_species = {}
    for r in eligible:
        sp = parse_opponent_spec(r['cell'].split(' ', 1)[1])[0]
        cur = by_species.get(sp)
        if cur is None or (abs(r['rate_inside_floor'] - 0.5)
                           < abs(cur['rate_inside_floor'] - 0.5)):
            by_species[sp] = r
    ranked = sorted(by_species.values(),
                    key=lambda r: (abs(r['rate_inside_floor'] - 0.5), r['rank']))
    top = ranked[:NOT_CLAIMED_ROW_CAP]
    rows = [[r['cell'] + (CAVEAT_MARK if r['caveat'] else ''),
             f"rank {r['rank']}", pct(r['rate_inside_floor']),
             ('a clean rule exists but is excluded; engine divergence'
              if r['has_excluded_cut'] else
              'engine divergence; see the mechanics note' if r['caveat']
              else '')]
            for r in top]
    if rows:
        # Every other capped list in the document discloses its remainder;
        # this one did not.
        lines.append(
            f"{_n(len(top))} of {_n(len(eligible))} top-{_n(RANK_GATE)} "
            f"matchups are listed, one per base species and closest to an "
            f"even split first; {_n(len(eligible) - len(top))} more are not.")
    head = ['cell', 'rank', f"win rate {where}", 'note']
    field = _field(13, 'Not claimed', lines, head=head, rows=rows)
    field['n_listed'] = len(top)
    field['n_listable'] = len(eligible)
    field['n_species'] = len(by_species)
    return field


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
        if fl['kind'] != 'exact':
            lines.append(
                f"The printed floor is a {fl['badge']}, not an exact cut: in "
                f"its own setting it leaves {_n(fl['n_wrong'])} of "
                f"{_n(h['n_iv'])} spreads on the wrong side of it. The "
                f"partition counts below are measured on that same line, so "
                f"they are counts of settings where it happens to be exact.")
        lines.append(
            f"The printed floor partitions its cell exactly in "
            f"{_n(fl['modes_partition'])} of {_n(fl['modes_total'])} "
            f"opponent-IV settings and {_n(fl['arms_partition'])} of "
            f"{_n(fl['arms_total'])} arms; its direction survives in "
            f"{_n(fl['modes_ok'])} and {_n(fl['arms_ok'])} of them. "
            f"Separately, and not comparably, the cell has a clean cut at "
            f"SOME value in {_n(fl['modes_clean'])} settings and "
            f"{_n(fl['arms_clean'])} arms.")
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
                f"strictly beaten), so \"{_n(fl['modes_partition'])} of "
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
        "Every threshold in this section is one of three things, and each is "
        "badged where it is printed. An EXACT clean cut: every spread at or "
        "above it wins the named cell and no spread below it does. A "
        f"ONE-SIDED GATE: one side is pure and the other is at least "
        f"{pct(GATE_MIN_ABOVE, 0)} pure -- either nothing below it wins "
        f"(clearing it is necessary) or everything at or above it wins "
        f"(clearing it is sufficient). A NEAR-EXACT split: at most "
        f"{pct(NEAR_EXACT_SHARE, 1)} of the grid sits on the wrong side of it "
        f"in total. The win predicate is gopvpsim.battle.is_win (score > "
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
    # Two fixed phrases may carry "should" -- the headline's opening sentence
    # and the field-6 header -- and EACH at most once per rendered section, so
    # the word cannot spread by template even though two templates own it.
    for pattern in SHOULD_ALLOWED_PATTERNS:
        scrub, n = re.subn(pattern, 'FIXED_PHRASE', scrub, flags=re.IGNORECASE)
        if n > 1:
            guard_fail('G-words', 'all', '-', pattern,
                       f"an allowed fixed phrase appears {n} times", ctx)
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


def gate_voice(blocks, ctx):
    """G-voice: the headline is written for a reader, not for the audit.

    Michael's round-4 note: the verdict has to read like an expert dive post
    ("most X should have at least Y attack; that is the priority line against
    a typical Annihilape and it decides the 0v1 outright"), not like a
    statistician's abstract. Every word this gate bars still appears -- with
    its definition and its arithmetic -- in the fields below, which is where
    a reader goes when the headline made them want the proof.
    """
    joined = '\n'.join(blocks)
    for pattern, instead in HEADLINE_BANNED:
        m = re.search(pattern, joined, re.IGNORECASE)
        if m:
            guard_fail('G-voice', 'Headline', '-', m.group(0),
                       f"barred from the headline: {instead}", ctx)


def gate_caveat(blocks, ctx):
    """G-caveat, at render time: a caveat species is never named bare.

    Field 10 says the Aegislash cells are excluded from the cost diff as an
    open engine divergence; the first build then led field 12's table with
    one of them and carried no marker across. Any string naming a caveat
    species must also carry the divergence wording.
    """
    for block in blocks:
        for species in CAVEAT_SPECIES:
            if species in block and 'divergence' not in block:
                guard_fail('G-caveat', 'all', species, block.strip()[:80],
                           'named with no engine-divergence marker', ctx)


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
            # The rank tag D3 requires is emitted positionally beside the
            # name, so the two lists have to stay the same length.
            if len(row['ranks']) != len(row['names']):
                guard_fail('G-names', key, row['names'][0],
                           f"{len(row['names'])} names",
                           f"{len(row['ranks'])} ranks", ctx)
            if len(row.get('mechs') or []) != len(row['names']):
                guard_fail('G-names', key, row['names'][0],
                           f"{len(row['names'])} names",
                           f"{len(row.get('mechs') or [])} mechanisms", ctx)
    alt = facts.get('alternative')
    if alt is not None:
        for k, n in (('guaranteed', 'n_guaranteed'), ('given_up', 'n_given_up'),
                     ('exclusive', 'n_exclusive')):
            if len(alt[k]) != alt[n]:
                guard_fail('G-names', 'Alternative target', k,
                           f"{len(alt[k])} names", alt[n], ctx)
    tail = facts.get('rungs_above_tail')
    if tail and tail['n_rungs'] and tail['n_cells'] < tail['n_rungs']:
        guard_fail('G-names', 'Rungs above', 'tail',
                   f"{tail['n_rungs']} rungs", f"{tail['n_cells']} cells", ctx)
    # Field 13 is a capped list like every other, and was the one that did
    # not disclose its remainder.
    f13 = _f13_not_claimed(facts)
    if f13.get('n_listed', 0) > f13.get('n_listable', 0):
        guard_fail('G-names', 'Not claimed', '-',
                   f"{f13['n_listed']} listed",
                   f"{f13['n_listable']} listable", ctx)
    if len(f13['rows']) != f13['n_listed']:
        guard_fail('G-names', 'Not claimed', '-',
                   f"{len(f13['rows'])} rows", f13['n_listed'], ctx)


def gate_recompute(state, arm, blob_path, mode, level, facts, ctx):
    """G-recompute: every printed number re-derived from the arrays again.

    This deliberately re-reads the cube and re-does the arithmetic instead of
    trusting anything in ``facts``, so a corrupted fact -- a wrong count, a
    wrong percentage, a wrong stat value -- is caught here rather than
    rendered.

    The first build covered a curated subset, and a probe that corrupted one
    field at a time found several reader-facing numbers rendering with no
    failure: the coverage ladder's strict share (the field the brief itself
    calls the real robustness measure), the floor's own mechanism arithmetic
    (``1.2 x 123.38 = 99.00`` rendered happily), the not-claimed total, the
    score-step pair in field 12, the L51 count, the catch counts and rank-1's
    IVs. Each of those is re-derived below. G-tie is re-run here too, at
    RENDER time rather than only inside stage 5, so a defect introduced
    between compute and render cannot slip a tie-inclusive 100% onto the page.
    """
    scores, meta = arm_view(state, arm, mode, level)
    win = win_cube(scores)
    atk, dfn, hp = stat_planes(meta)
    n_iv = scores.shape[0]
    league = state['league']

    def check(field, cell, printed, recomputed, tol=0.0):
        if isinstance(printed, float) or isinstance(recomputed, float):
            if abs(float(printed) - float(recomputed)) > tol:
                guard_fail('G-recompute', field, cell, printed, recomputed, ctx)
        elif printed != recomputed:
            guard_fail('G-recompute', field, cell, printed, recomputed, ctx)

    nwin = win.sum(axis=0)
    check('Header', '-', facts['header']['n_iv'], int(n_iv))

    # The clean-cut census, re-derived from the cube rather than carried over.
    # Round 2 left the axis breakdown (which the no-floor headline leads with)
    # and both gate-tally totals unguarded.
    tri_r = stage1_triage(win)
    cuts_r = stage2_clean_cuts(win, {'atk': atk, 'def': dfn, 'hp': hp}, tri_r)
    for c in cuts_r:
        c['caveat'] = any(
            cv in parse_opponent_spec(state['opponent_names'][c['oi']])[0]
            for cv in CAVEAT_SPECIES)
    check('How sure', '-', dict(facts['clean_counts']),
          dict(Counter(c['axis'] for c in cuts_r)))
    check('How sure', '-', facts['gate_tally']['n_cuts'], len(cuts_r))
    check('How sure', '-', facts.get('clean_excluded', 0),
          sum(1 for c in cuts_r if c['caveat']))
    atk_cuts_r = [c for c in cuts_r if c['axis'] == 'atk' and not c['caveat']]
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
        # G-primitive: both sides of the line, and the claim the badge makes,
        # re-derived from the cube. A badge is a CLAIM about the spreads on
        # the wrong side, so a wrong badge is a wrong sentence, not a wrong
        # label: an exact badge over a gate would print "no spread below it
        # wins" over 56 spreads that do.
        wins_col = win[:, si, oi]
        n_above_r = int((~below).sum())
        n_win_above_r = int(wins_col[~below].sum())
        n_win_below_r = int(wins_col[below].sum())
        n_wrong_r = (n_above_r - n_win_above_r) + n_win_below_r
        check('Floor primitive', fl['cell'], fl['n_above'], n_above_r)
        check('Floor primitive', fl['cell'], fl['n_win_above'], n_win_above_r)
        check('Floor primitive', fl['cell'], fl['n_win_below'], n_win_below_r)
        check('Floor primitive', fl['cell'], fl['n_wrong'], int(n_wrong_r))
        check('Floor primitive', fl['cell'], fl['rate_above'],
              n_win_above_r / n_above_r if n_above_r else 0.0, tol=1e-12)
        kind_r = ('exact' if n_wrong_r == 0
                  else 'gate' if (n_win_below_r == 0
                                  or n_win_above_r == n_above_r)
                  else 'near_exact')
        check('Floor primitive', fl['cell'], fl['kind'], kind_r)
        check('Floor primitive', fl['cell'], fl['badge'],
              PRIMITIVE_BADGE[kind_r])
        if fl['kind'] == 'exact' and n_wrong_r != 0:
            guard_fail('G-primitive', 'Floor', fl['cell'], 'exact',
                       f"{n_wrong_r} spreads on the wrong side", ctx)
        if fl['kind'] == 'gate':
            side_r = 'necessary' if n_win_below_r == 0 else 'sufficient'
            check('Floor primitive', fl['cell'], fl['gate_side'], side_r)
            rate = (n_win_above_r / n_above_r if side_r == 'necessary'
                    else 1.0 - n_win_below_r / int(below.sum()))
            if rate < GATE_MIN_ABOVE:
                guard_fail('G-primitive', 'Floor', fl['cell'],
                           f"gate at {rate:.4f}",
                           f"below the bar {GATE_MIN_ABOVE}", ctx)
        if fl['kind'] == 'near_exact' and n_wrong_r > near_exact_limit(n_iv):
            guard_fail('G-primitive', 'Floor', fl['cell'],
                       f"near-exact with {n_wrong_r} wrong",
                       f"limit {near_exact_limit(n_iv)}", ctx)
        check('Floor', fl['cell'], fl['score_below'][0],
              int(scores[below, si, oi].min()))
        check('Floor', fl['cell'], fl['score_above'][0],
              int(scores[~below, si, oi].min()))
        check('Floor', fl['cell'], fl['score_below'][1],
              int(scores[below, si, oi].max()))
        check('Floor', fl['cell'], fl['score_above'][1],
              int(scores[~below, si, oi].max()))
        # The mechanism arithmetic the page prints as "1.2 x A = L".
        m = fl['mech']
        if m['kind'] == 'cmp':
            mult = SHADOW_ATK_BONUS if state['shadow'] else 1.0
            check('Floor mechanism', fl['cell'], m['line'],
                  mult * m['opp_cmp_atk'], tol=1e-9)
            if not (fl['prev_attained'] < m['line'] <= fl['T']):
                guard_fail('G-recompute', 'Floor mechanism', fl['cell'],
                           m['line'],
                           f"outside the gap ({fl['prev_attained']}, {fl['T']}]",
                           ctx)
            check('Floor mechanism', fl['cell'], bool(m.get('on_the_line')),
                  bool(m['line'] == fl['T']))
        # Direction and cleanliness are separate printed counts (see
        # stage3_holds); each is re-derived from the cubes it describes.
        for key, src in (('modes_clean', 'per_mode_cuts'),
                         ('arms_clean', 'per_arm_cuts')):
            views = fl.get(src) or {}
            if views:
                check('Floor', fl['cell'], fl[key],
                      sum(1 for v in views.values() if v['clean']))
        if fl['modes_ok'] > fl['modes_total'] or fl['modes_clean'] > fl['modes_total']:
            guard_fail('G-recompute', 'Floor', fl['cell'],
                       f"{fl['modes_ok']}/{fl['modes_clean']}",
                       f"of {fl['modes_total']} settings", ctx)
        # G-owner, re-derived: dedup the cells at this value first, then take
        # base species. The first build filtered to ELIGIBLE cells, which
        # made "owned by one base species" true by construction in the common
        # case where exactly one cell passed the gates.
        owners = set()
        for lbl in [fl['cell']] + fl['other_cells_at_T']:
            si_o, oi_o = _cell_index(state, lbl)
            key = win[:, si_o, oi_o].tobytes()
            rep = next(o for o in range(win.shape[2])
                       if win[:, si_o, o].tobytes() == key)
            owners.add(parse_opponent_spec(state['opponent_names'][rep])[0])
        if fl.get('merged_from') and fl['kind'] != 'exact':
            guard_fail('G-primitive', 'Floor merge', fl['cell'], fl['badge'],
                       'only an exact rung may carry a merge', ctx)
        for m in fl.get('merged_from') or []:
            check('Floor merge', m['cells'][0]['label'], m['n_pass'],
                  int((atk >= m['T']).sum()))
            check('Floor merge', m['cells'][0]['label'], m['n_pass'],
                  int((atk >= m['printed']).sum()))
            check('Floor merge', m['cells'][0]['label'],
                  m['n_below_floor_win'], int(m['n_pass'] - fl['n_pass']))
            if m['T'] >= fl['T']:
                guard_fail('G-recompute', 'Floor merge',
                           m['cells'][0]['label'], m['T'],
                           f"not below the printed floor {fl['T']}", ctx)
            if (m['n_pass'] - fl['n_pass']) > MERGE_SPREAD_TOL * n_iv:
                guard_fail('G-recompute', 'Floor merge',
                           m['cells'][0]['label'],
                           m['n_pass'] - fl['n_pass'],
                           f"outside the merge tolerance "
                           f"{MERGE_SPREAD_TOL * n_iv}", ctx)
            for c in m['cells']:
                si_m, oi_m = _cell_index(state, c['label'])
                if not np.array_equal(atk >= m['T'], win[:, si_m, oi_m]):
                    guard_fail('G-recompute', 'Floor merge', c['label'],
                               'clean at its own cut',
                               'not a clean partition there', ctx)
                if not win[atk >= fl['T'], si_m, oi_m].all():
                    guard_fail('G-recompute', 'Floor merge', c['label'],
                               'won by every clearer',
                               int(win[atk >= fl['T'], si_m, oi_m].sum()), ctx)
        check('Floor', fl['cell'], fl['single_owner'], len(owners) == 1)
        check('Floor', fl['cell'], sorted(fl['owners']), sorted(owners))
        # Direction and PARTITION on the printed line, in every baked view.
        # Round 2 measured the strict test at each view's own cut, which let
        # it exceed the weak test (Melmetal: 3 of 4 arms "clean" under 2 of 4
        # "points the same way"). Partition implies direction, so the guard
        # asserts the ordering as well as the counts.
        n_part_m = n_ok_m = 0
        for m in state['opp_iv_modes']:
            sc_m, meta_m = arm_view(state, arm, m, level)
            cube_m = win_cube(sc_m)
            a_m = meta_m[:, 5]
            if np.array_equal(a_m >= fl['T'], cube_m[:, si, oi]):
                n_part_m += 1
            r_a, r_b = direction_rates(cube_m, a_m, fl['T'], si, oi)
            if r_a >= DIRECTION_MIN_ABOVE and r_a > r_b:
                n_ok_m += 1
        check('Floor', fl['cell'], fl['modes_partition'], n_part_m)
        check('Floor', fl['cell'], fl['modes_ok'], n_ok_m)
        n_part_a = n_ok_a = 0
        for k in range(len(state['moveset_data'])):
            sc_k, meta_k = arm_view(state, k, mode, level)
            cube_k = win_cube(sc_k)
            a_k = meta_k[:, 5]
            if np.array_equal(a_k >= fl['T'], cube_k[:, si, oi]):
                n_part_a += 1
            r_a, r_b = direction_rates(cube_k, a_k, fl['T'], si, oi)
            if r_a >= DIRECTION_MIN_ABOVE and r_a > r_b:
                n_ok_a += 1
        check('Floor', fl['cell'], fl['arms_partition'], n_part_a)
        check('Floor', fl['cell'], fl['arms_ok'], n_ok_a)
        for strict, weak, what in ((fl['modes_partition'], fl['modes_ok'],
                                    'settings'),
                                   (fl['arms_partition'], fl['arms_ok'],
                                    'arms')):
            if strict > weak:
                guard_fail('G-recompute', 'Floor', fl['cell'],
                           f"partition {strict} of {what}",
                           f"direction only {weak}; a partition implies the "
                           f"direction test", ctx)
        if fl.get('energy'):
            e = state['moveset_data'][arm].get('energy')
            if e is not None and mode in e:
                ea = np.asarray(e[mode], dtype=np.int32).reshape(
                    n_iv, win.shape[1], win.shape[2])[:, si, oi]
                check('Floor', fl['cell'], fl['energy']['below'][0],
                      int(np.unique(ea[below])[0]))
                check('Floor', fl['cell'], fl['energy']['above'][0],
                      int(np.unique(ea[~below])[0]))
                check('Floor', fl['cell'], fl['energy']['below_single'],
                      bool(np.unique(ea[below]).size == 1))

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
        # The strict share and the tie count are re-derived from the
        # opponent's own IV grid, not carried over from stage 5: field 14
        # names this column as the real robustness measure, and the first
        # build would render a corrupted one silently.
        species, _v, opp_shadow = parse_opponent_spec(cov['opponent'])
        grid = opponent_iv_grid(species, league, opp_shadow)
        mult = SHADOW_ATK_BONUS if state['shadow'] else 1.0
        for row in cov['rows']:
            check('Coverage', row['label'], row['focal'],
                  int((atk >= row['line']).sum()))
            check('Coverage', row['label'], row['focal'],
                  int((atk >= row['printed']).sum()))
            cmp_atk_val = row['cmp_atk']
            check('Coverage', row['label'], row['line'],
                  mult * cmp_atk_val, tol=1e-9)
            check('Coverage', row['label'], row['strict'],
                  float((grid < cmp_atk_val).mean()), tol=1e-12)
            check('Coverage', row['label'], row['ties'],
                  int((grid == cmp_atk_val).sum()))
            # G-tie, at render time: a row may read 100.0% only if the strict
            # share really is 100%.
            if row['strict'] >= 1.0 and row['ties'] > 0:
                guard_fail('G-tie', 'Coverage', row['label'], '100.0%',
                           f"{row['strict']:.6f} with {row['ties']} ties", ctx)

    alt = facts.get('alternative')
    if alt is not None:
        mask = (dfn >= alt['def_cut']) & (hp >= alt['hp_cut'])
        sp_a = atk * dfn * hp
        check('Alternative target', 'Def x HP rectangle', alt['sp_share_lo'],
              float((sp_a[mask] / sp_a.max()).min()), tol=1e-12)
        check('Alternative target', 'Def x HP rectangle', alt['sp_share_hi'],
              float((sp_a[mask] / sp_a.max()).max()), tol=1e-12)
        check('Alternative target', 'Def x HP rectangle', alt['atk_lo'],
              float(atk[mask].min()), tol=1e-9)
        check('Alternative target', 'Def x HP rectangle', alt['atk_hi'],
              float(atk[mask].max()), tol=1e-9)
        env = alt.get('envelope')
        if env:
            ivs_a = meta[mask, :3].astype(int)
            check('Alternative target', 'envelope', env['atk_iv'],
                  [int(ivs_a[:, 0].min()), int(ivs_a[:, 0].max())])
            check('Alternative target', 'envelope', env['def_iv'],
                  [int(ivs_a[:, 1].min()), int(ivs_a[:, 1].max())])
            check('Alternative target', 'envelope', env['hp_iv'],
                  [int(ivs_a[:, 2].min()), int(ivs_a[:, 2].max())])
            check('Alternative target', 'envelope',
                  sum(c for _v, c in env['by_atk_iv']), int(mask.sum()))
        for row in facts.get('alt_catch') or []:
            acm = facts.get('alt_catch_model') or {}
            check('Alternative target', 'encounters', row['n'],
                  _encounters(acm.get('share', alt['share']), row['target']))
        check('Alternative target', 'Def x HP rectangle', alt['n'],
              int(mask.sum()))
        pmask = (dfn >= alt['def_printed']) & (hp >= alt['hp_cut'])
        check('Alternative target', 'Def x HP rectangle (printed)', alt['n'],
              int(pmask.sum()))
        check('Alternative target', 'Def x HP rectangle', alt['share'],
              float(mask.sum()) / n_iv, tol=1e-12)
        check('Alternative target', 'Def x HP rectangle', alt['n_guaranteed'],
              len(alt['guaranteed']))
        check('Alternative target', 'Def x HP rectangle', alt['n_exclusive'],
              len(alt['exclusive']))
        check('Alternative target', 'Def x HP rectangle', alt['too_wide'],
              bool(alt['n'] / n_iv > ALT_SHARE_REFRAME))
        won = win[mask].reshape(int(mask.sum()), -1).sum(axis=1)
        check('Alternative target', 'cells won', alt['cells_won'][0],
              int(won.min()))
        check('Alternative target', 'cells won', alt['cells_won'][1],
              int(won.max()))
        for label in alt['guaranteed_cells']:
            si, oi = _cell_index(state, label)
            if not win[mask, si, oi].all():
                guard_fail('G-recompute', 'Alternative target', label,
                           'guaranteed',
                           f"{int(win[mask, si, oi].sum())} of {int(mask.sum())}",
                           ctx)
    contested_r = [(int(a), int(b)) for a, b in
                   zip(*np.nonzero((nwin > 0) & (nwin < n_iv)))]
    sp_v = atk * dfn * hp
    sp_rank_v = np.empty(n_iv, dtype=int)
    sp_rank_v[np.argsort(-sp_v, kind='stable')] = np.arange(1, n_iv + 1)
    for ex in facts.get('examples') or []:
        i = ex['i']
        check('Example spreads', f"{ex['ivs']}", ex['contested_cells'],
              int(sum(1 for si_e, oi_e in contested_r if win[i, si_e, oi_e])))
        check('Example spreads', f"{ex['ivs']}", ex['sp_rank'],
              int(sp_rank_v[i]))
        check('Example spreads', f"{ex['ivs']}", ex['sp_share'],
              float(sp_v[i] / sp_v.max()), tol=1e-12)
        check('Example spreads', f"{ex['ivs']}", ex['atk'], float(meta[i, 5]),
              tol=1e-9)
        check('Example spreads', f"{ex['ivs']}", ex['def'], float(meta[i, 6]),
              tol=1e-9)
        check('Example spreads', f"{ex['ivs']}", ex['hp'], int(meta[i, 7]))
        check('Example spreads', f"{ex['ivs']}", ex['total'],
              int(win[i].sum()))
        check('Example spreads', f"{ex['ivs']}", tuple(int(v) for v in ex['ivs']),
              tuple(int(v) for v in meta[i, :3]))
        check('Example spreads', f"{ex['ivs']}", ex['by_scenario'],
              [int(win[i, si, :].sum()) for si in range(win.shape[1])])

    for row in facts.get('score_only') or []:
        si, oi = _cell_index(state, row['cell'])
        col = scores[:, si, oi]
        above = atk >= row['T']
        if row['above'] > row['below']:
            check('Changes the score, not the matchup', row['cell'],
                  row['above'], int(col[above].min()))
            check('Changes the score, not the matchup', row['cell'],
                  row['below'], int(col[~above].max()))
        else:
            check('Changes the score, not the matchup', row['cell'],
                  row['above'], int(col[above].max()))
            check('Changes the score, not the matchup', row['cell'],
                  row['below'], int(col[~above].min()))

    for row in facts.get('dirty_thresholds') or []:
        si, oi = _cell_index(state, row['cell'])
        stat = {'atk': atk, 'def': dfn, 'hp': hp}[row['axis']]
        above = stat >= row['t']
        wins = win[:, si, oi]
        check('Dirty threshold', row['cell'], bool(row['one_sided']),
              bool(int(wins[~above].sum()) == 0
                   or int(wins[above].sum()) == int(above.sum())))
        check('Dirty threshold', row['cell'], bool(row['near_exact']),
              bool(row['n_wrong'] <= max(1, round(NEAR_EXACT_SHARE * n_iv))))
        if row.get('genre'):
            g_above = stat >= row['genre']['printed']
            check('Dirty threshold', row['cell'], row['genre']['n_above'],
                  int(g_above.sum()))
            check('Dirty threshold', row['cell'], row['genre']['n_extra'],
                  int((g_above & (stat < row['t'])).sum()))
        check('Dirty threshold', row['cell'], row['n_above'], int(above.sum()))
        check('Dirty threshold', row['cell'], row['n_win_above'],
              int(wins[above].sum()))
        check('Dirty threshold', row['cell'], row['n_win_below'],
              int(wins[~above].sum()))
        check('Dirty threshold', row['cell'], row['n_wrong'],
              int((~wins[above]).sum() + wins[~above].sum()))
        check('Dirty threshold', row['cell'], row['constant_wrong'],
              int(min(wins.sum(), n_iv - wins.sum())))
        if row['n_wrong'] >= row['constant_wrong']:
            guard_fail('G-recompute', 'Dirty threshold', row['cell'],
                       row['n_wrong'],
                       f"the constant rule gets {row['constant_wrong']} wrong",
                       ctx)

    for row in (facts.get('bulk') or {}).get('cogates') or []:
        si, oi = _cell_index(state, row['cell'])
        clearers = atk >= fl['T']
        stat = dfn if row['axis'] == 'def' else hp
        sub = clearers & (stat >= row['t'])
        check('Bulk co-gate', row['cell'], row['n'], int(sub.sum()))
        if not win[sub, si, oi].all():
            guard_fail('G-recompute', 'Bulk co-gate', row['cell'], '100%',
                       f"{int(win[sub, si, oi].sum())} of {int(sub.sum())}",
                       ctx)

    bulk = facts.get('bulk') or {}
    if bulk.get('cells_won_range') and fl is not None:
        m = atk >= fl['T']
        won = win[m].reshape(int(m.sum()), -1).sum(axis=1)
        check('Bulk', 'cells won', bulk['cells_won_range'][0], int(won.min()))
        check('Bulk', 'cells won', bulk['cells_won_range'][1], int(won.max()))

    l51 = facts.get('l51')
    if l51:
        _s51, meta51 = arm_view(state, arm, mode, 'l51')
        atk51 = meta51[:, 5]
        check('How sure', 'L51', l51['n_selected_by_l50_literal'],
              int((atk51 >= fl['T']).sum()))
        if l51['clean']:
            check('How sure', 'L51', l51['n_pass'],
                  int((atk51 >= l51['T']).sum()))
            check('How sure', 'L51', l51['n_pass'],
                  int((atk51 >= l51['printed']).sum()))

    for row in facts.get('catch') or []:
        check('Floor', 'encounters', row['n'],
              _encounters((facts.get('catch_model') or {}).get(
                  'share', fl['pool_share']), row['target']))

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
    check('Not claimed', '-', nc['n'], len(nc['rows']))
    check('Not claimed', '-', nc['n'],
          nc['n_no_rule'] + nc['n_excluded_by_caveat'])
    if nc['n'] > nc['of']:
        guard_fail('G-recompute', 'Not claimed', '-', nc['n'],
                   f"of {nc['of']} contested", ctx)

    tail = facts.get('rungs_above_tail')
    if tail and tail['n_rungs']:
        check('Rungs above', 'tail', tail['max_n_pass'],
              int((atk >= tail['max_T']).sum()))
        check('Rungs above', 'tail', tail['max_pool'],
              float((atk >= tail['max_pool_T']).sum()) / n_iv, tol=1e-12)
        check('Rungs above', 'tail', tail['max_pool_n_pass'],
              int((atk >= tail['max_pool_printed']).sum()))
        check('Rungs above', 'tail', tail['max_n_pass'],
              int((atk >= tail['max_printed']).sum()))

    mir = facts.get('mirror')
    if mir is not None:
        oi_m = state['opponent_names'].index(mir['opponent'])
        check('Mirror', mir['opponent'], mir['oi'], int(oi_m))
        m_mask = (atk >= fl['T']) if fl is not None else None
        for si_m, row in enumerate(mir['rows']):
            w = win[:, si_m, oi_m]
            check('Mirror', row['scenario'], row['rate'], float(w.mean()),
                  tol=1e-12)
            if m_mask is not None:
                check('Mirror', row['scenario'], row['above'],
                      float(w[m_mask].mean()), tol=1e-12)
                check('Mirror', row['scenario'], row['below'],
                      float(w[~m_mask].mean()), tol=1e-12)
        for rm in mir['rank1_modes']:
            sc_m, _meta_m = arm_view(state, arm, rm['mode'], level)
            cube_m = win_cube(sc_m)
            check('Mirror', rm['mode'], rm['per_scenario'],
                  [int(cube_m[:, si_m, oi_m].sum())
                   for si_m in range(win.shape[1])])

    for row in (facts.get('bulk') or {}).get('cogates') or []:
        si_c, oi_c = _cell_index(state, row['cell'])
        stat = dfn if row['axis'] == 'def' else hp
        outside = (atk >= fl['T']) & (stat < row['t'])
        check('Bulk co-gate', row['cell'], row['rate_outside'],
              float(win[outside, si_c, oi_c].mean()) if outside.any() else 0.0,
              tol=1e-12)
        check('Bulk co-gate', row['cell'], row['base_rate'],
              float(win[atk >= fl['T'], si_c, oi_c].mean()), tol=1e-12)

    lr = facts.get('level_reach')
    if lr and fl is not None:
        m_in = atk >= fl['T']
        check('Example spreads', 'level reach', lr['median_in'],
              float(np.median(meta[m_in, 3])), tol=1e-9)
        check('Example spreads', 'level reach', lr['median_out'],
              float(np.median(meta[~m_in, 3])), tol=1e-9)
        check('Example spreads', 'level reach', lr['n_in_low'],
              int((meta[m_in, 3] <= 45.0).sum()))
        check('Example spreads', 'level reach', lr['n_out_low'],
              int((meta[~m_in, 3] <= 45.0).sum()))

    gb = facts.get('grid_best')
    if gb is not None:
        all_won = win.reshape(n_iv, -1).sum(axis=1)
        check('Example spreads', 'grid best', gb['total'],
              int(all_won[gb['i']]))
        check('Example spreads', 'grid best', gb['total'], int(all_won.max()))
        check('Example spreads', 'grid best', gb['n_tied'],
              int((all_won == all_won.max()).sum()))
        check('Example spreads', 'grid best',
              tuple(int(v) for v in gb['ivs']),
              tuple(int(v) for v in meta[gb['i'], :3]))

    cm = facts.get('catch_model')
    if cm is not None and fl is not None:
        grid_r, restricted_r = reachable_mask(meta, facts['acquisition'])
        check('Floor', 'encounters', cm['restricted'], bool(restricted_r))
        check('Floor', 'encounters', cm['n_grid'], int(grid_r.sum()))
        check('Floor', 'encounters', cm['n_reachable'],
              int(((atk >= fl['T']) & grid_r).sum()))
        check('Floor', 'encounters', cm['share'],
              float(cm['n_reachable']) / cm['n_grid'], tol=1e-12)

    cd = (facts.get('cost') or {}).get('diff')
    if cd:
        j = facts['rank1']['i']
        want = tuple(int(v) for v in cd['spread'])
        hits = np.nonzero((meta[:, 0] == want[0]) & (meta[:, 1] == want[1])
                          & (meta[:, 2] == want[2]))[0]
        if hits.size != 1:
            guard_fail('G-recompute', 'Cost', str(want), hits.size,
                       'exactly one spread with those IVs', ctx)
        i_c = int(hits[0])
        cav = np.array([any(cv in parse_opponent_spec(nm)[0]
                            for cv in CAVEAT_SPECIES)
                        for nm in state['opponent_names']], dtype=bool)
        diff = win[i_c] != win[j]
        gained = diff & win[i_c]
        lost = diff & win[j]
        check('Cost', str(want), cd['n_gained'],
              int(gained[:, ~cav].sum()))
        check('Cost', str(want), cd['n_lost'], int(lost[:, ~cav].sum()))
        check('Cost', str(want), cd['n_gained_with_caveat'],
              int(gained.sum()))
        check('Cost', str(want), cd['n_lost_with_caveat'], int(lost.sum()))
        check('Cost', str(want), cd['caveat_excluded'],
              int(gained[:, cav].sum() + lost[:, cav].sum()))

    check('Not claimed', '-', nc['of'],
          int(((nwin > 0) & (nwin < n_iv)).sum()))

    r1 = facts['rank1']
    sp = atk * dfn * hp
    check('Rank-1 check', 'rank-1', r1['i'], int(np.argmax(sp)))
    check('Rank-1 check', 'rank-1', r1['n_cuts'], len(atk_cuts_r))
    check('Rank-1 check', 'rank-1', r1['n_cuts_cleared'],
          int(sum(1 for c in atk_cuts_r if atk[r1['i']] >= c['T'])))
    if fl is not None:
        check('Rank-1 check', 'rank-1', r1['shortfall'],
              float(fl['T'] - atk[r1['i']]), tol=1e-9)
        check('Rank-1 check', 'rank-1', r1['clears_floor'],
              bool(atk[r1['i']] >= fl['T']))
    check('Rank-1 check', 'rank-1', tuple(int(v) for v in r1['ivs']),
          tuple(int(v) for v in meta[r1['i'], :3]))
    check('Rank-1 check', 'rank-1', r1['total_won'], int(win[r1['i']].sum()))
    check('Rank-1 check', 'rank-1', r1['total_cells'], int(win[r1['i']].size))
    check('Rank-1 check', 'rank-1', r1['contested_won'],
          int(sum(1 for si, oi in
                  zip(*np.nonzero(((win.sum(axis=0) > 0)
                                   & (win.sum(axis=0) < n_iv))))
                  if win[r1['i'], si, oi])))
    check('Rank-1 check', 'rank-1', r1['atk'], float(meta[r1['i'], 5]),
          tol=1e-9)
    check('Rank-1 check', 'rank-1', r1['def'], float(meta[r1['i'], 6]),
          tol=1e-9)
    check('Rank-1 check', 'rank-1', r1['hp'], int(meta[r1['i'], 7]))
    if alt is not None:
        amask = (dfn >= alt['def_cut']) & (hp >= alt['hp_cut'])
        check('Rank-1 check', 'rank-1', bool(r1['in_alternative']),
              bool(amask[r1['i']]))
    check('Rank-1 check', 'rank-1', r1['by_scenario'],
          [int(win[r1['i'], si, :].sum()) for si in range(win.shape[1])])


def _encounters(share, target):
    for t, n in catch_encounters(share, targets=(target,)):
        return n
    return None


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

def _primitive_audit_sentence(facts):
    """E2 audit: what each primitive ALONE would have chosen, and what won.

    The widened pool is the one v2 change that can move a printed line, so
    the page shows its working: three independent selections under the same
    band and the same gates, and which of them the tie-break took.
    """
    picks = facts.get('primitive_picks') or {}
    bits = []
    for kind in ('exact', 'gate', 'near_exact'):
        p = picks.get(kind)
        label = PRIMITIVE_BADGE[kind]
        bits.append(f"{label} -> " + ('nothing eligible' if p is None else
                                      f"Atk >= {fmt(p['printed'], p['dp'])} "
                                      f"({p['cell']}, {pct(p['pool_share'])})"))
    fl = facts['floor']
    chosen = ('no floor' if fl is None else
              f"the {fl['badge']} at Atk >= {fmt(fl['printed'], fl['dp'])}")
    return (f"Floor pool by primitive, each selected on its own under the "
            f"same band and the same gates: " + '; '.join(bits) + ". "
            f"Selected: {chosen}. Selection takes the lowest eligible rung in "
            f"the band; a stronger primitive within "
            f"{fmt(PRIMITIVE_TIE_WINDOW)} attack of it wins the tie, in the "
            f"order exact, one-sided gate, near-exact. A gate needs "
            f"{pct(GATE_MIN_ABOVE, 0)} of its dirty side pointing the right "
            f"way; a near-exact split needs at most "
            f"{pct(NEAR_EXACT_SHARE, 1)} of the grid on the wrong side. Only "
            f"exact rungs merge, in either direction.")


def build_evidence(facts):
    """Band constants, per-mode cuts, the ladder rung reached, sensitivity."""
    c = facts['constants']
    fl = facts['floor']
    lines = [
        f"Decision band for the floor (D1): the lowest ELIGIBLE rung whose "
        f"clearer pool sits inside [{pct(c['decision_band'][0], 0)}, "
        f"{pct(c['decision_band'][1], 0)}] of the grid. Materiality band for a "
        f"rung: [{pct(c['material'][0], 0)}, {pct(c['material'][1], 0)}].",
        f"To be ELIGIBLE AS THE FLOOR -- not to be listed as a rung -- a cut "
        f"needs at least {_n(c['min_attained_below'])} distinct attainable "
        f"values below it, an opponent of rank {_n(c['rank_gate'])} or better "
        f"outside the caveat list, a non-degenerate shield scenario, a win "
        f"rate at or above the cut of at least "
        f"{pct(c['direction_min_above'], 0)} in every setting, and a "
        f"closed-form mechanism. Listing is a weaker bar: a rung is printed "
        f"when it keeps {pct(c['rung_pool_min'], 0)} of the grid (above the "
        f"floor) or sits in the materiality band (below it) AND points the "
        f"same way in at least {_n(c['modes_to_list'])} settings, so a listed "
        f"rung may be unattributed, low-ranked or 2-of-4.",
        f"A cut can fail several gates at once, so the failure tally below "
        f"sums to more than the number of cuts.",
        f"Co-gate sub-rectangles need {pct(c['cogate_min_share'], 0)} of the "
        f"grid; the alternative target needs {_n(c['alt_min_members'])} "
        f"members; a score-only step needs {_n(c['score_step_min'])} points. "
        f"These constants are calibrated on one species and are parameters of "
        f"the stage that uses them, not tuned per dive.",
        _primitive_audit_sentence(facts),
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
                     fmt(s['printed'], s['dp']) if s['T'] is not None
                     else 'no floor',
                     s['cell'] or '-'])
    if facts.get('cmp_near_misses'):
        lines.append(
            f"G-cmp-fresh (WARN, not a failure): {_n(len(facts['cmp_near_misses']))} "
            f"cut(s) have a live priority line within "
            f"{fmt(CMP_NEAR_MISS)} attack of the cut but outside its gap, so "
            f"they print unattributed: "
            + _cap_list(facts['cmp_near_misses'], cap=6) + ". This blob "
            "carries no gamemaster stamp, so a rebalance since the bake would "
            "look exactly like this.")
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
            + '; '.join(f"{d['cell']} "
                        f"{stat_threshold_str(d['axis'], d['printed'], d['dp'])} "
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
.strip { display: grid; grid-template-columns: 8.5rem 1fr; gap: 2px 12px;
         margin: 14px 0 0; padding: 12px 14px; background: #f2f4f3;
         border: 1px solid #dfe3e1; border-radius: 6px; font-size: .88rem; }
.strip dt { color: #5c6270; font-weight: 600; letter-spacing: .04em;
            text-transform: uppercase; font-size: .74rem; padding-top: 3px; }
.strip dd { margin: 0; }
@media (max-width: 34rem) { .strip { grid-template-columns: 1fr; }
                            .strip dd { margin: 0 0 6px; } }
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


WRAP_COLUMNS = {'Rungs above': (1, 4, 5),
                'Material clean cuts below the floor': (1, 4),
                'Material clean cuts': (1, 4),
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


def strip_html(strip):
    out = ['<dl class="strip">']
    for label, value in strip:
        out.append(f'<dt>{_esc(label)}</dt><dd>{_esc(value)}</dd>')
    out.append('</dl>')
    return ''.join(out)


def arm_html(facts, headline, strip, fields, evidence):
    h = facts['header']
    out = [f'<section class="arm"><h2>Build brief -- {_esc(focal_name(h))}, '
           f'{_esc(league_name(h["league"]))}</h2>',
           f'<p class="sub">{_esc(h["arm_label"])} '
           f'(arm {h["arm"] + 1} of {h["n_arms"]})</p>',
           strip_html(strip),
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


def lead_block(all_facts):
    """Page-level cross-arm lead: which arms carry a line, floor-first.

    The page always renders arms in blob order, so Melmetal opened with "no
    attack, Def or HP value is a build line" for arm 1 of 4 while arm 4 owns a
    real floor, and Furret opened on the weakest of five. A reader choosing a
    moveset needs that comparison, and it is the same fact the sweep row
    already computes.
    """
    rows, lines = [], []
    with_floor = []
    for f in all_facts:
        h = f['header']
        fl = f['floor']
        if fl is not None:
            outcome = (f"Atk >= {fmt(fl['printed'], fl['dp'])} "
                       f"({pct(fl['pool_share'])} of the grid, {fl['cell']}, "
                       f"{fl['badge']})")
            with_floor.append((h['arm'] + 1, fmt(fl['printed'], fl['dp'])))
        else:
            outcome = "no line"
        alt = f['alternative']
        rect = ('-' if alt is None else
                f"Def >= {fmt(alt['def_printed'], alt['def_dp'])}, "
                f"HP >= {_n(alt['hp_cut'])} ({pct(alt['share'])})")
        rows.append([f"arm {h['arm'] + 1} of {h['n_arms']}", h['arm_label'],
                     outcome, rect])
    if not with_floor:
        lines.append(f"None of the {_n(len(all_facts))} arms rendered here "
                     f"carries a build line.")
    elif len(with_floor) == len(all_facts):
        lines.append(f"All {_n(len(all_facts))} arms rendered here carry a "
                     f"build line.")
    else:
        bits = ', '.join(f"arm {a} at Atk >= {v}" for a, v in with_floor)
        lines.append(
            f"{_n(len(with_floor))} of {_n(len(all_facts))} arms rendered here "
            f"carry a build line: {bits}. The others print what separates and "
            f"why none of it is a line.")
    rows.sort(key=lambda r: (r[2] == 'no line', r[0]))
    out = ['<section class="arm"><h2>Arms on this page</h2>']
    for line in lines:
        out.append(f'<p>{_esc(line)}</p>')
    out.append(_table_html(['arm', 'moveset', 'build line', 'bulk rectangle'],
                           rows, wrap_cols=(1, 2, 3)))
    out.append('</section>')
    return ''.join(out), lines + [c for r in rows for c in r]


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
    strip = build_strip(facts)
    fields = build_fields(facts)
    evidence = build_evidence(facts)
    blocks = list(headline)
    for field in fields:
        blocks.extend(field_strings(field))
    blocks.extend(evidence['lines'])
    blocks.extend(evidence['head'])
    for row in evidence['rows']:
        blocks.extend(str(c) for c in row)
    strip_strings = [f"{k}: {v}" for k, v in strip]
    gate_words(blocks + strip_strings, ctx)
    gate_caveat(blocks + strip_strings, ctx)
    gate_voice(list(headline) + strip_strings, ctx)
    return arm_html(facts, headline, strip, fields, evidence)


def blob_slug(path):
    base = os.path.basename(path)
    return base.split('.replay')[0]


JSON_DROP_KEYS = ('mask', 'cells', 'contested_mask', 'all_win_mask',
                  'all_lose_mask', 'nwin', 'dedup_of', 'dedup_members_raw')


def json_safe(obj):
    """Serialisable copy of the fact dict.

    The drop list is by NAME, which is why the example rows' contested-cell
    count is called 'contested_cells' rather than 'cells': a rung's 'cells'
    key holds numpy-bearing cut dicts, and dropping the name dropped the
    example number too, so the JSON stopped being a faithful record of the
    page.
    """
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()
                if k not in JSON_DROP_KEYS}
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
    lead_html, lead_strings = lead_block(all_facts)
    ctx = {'blob': os.path.basename(path), 'arm': '-', 'mode': mode}
    gate_words([title, subtitle] + lead_strings, ctx)
    gate_caveat([title, subtitle] + lead_strings, ctx)
    doc = document_html(title, subtitle, [lead_html] + sections)
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
                   f"({pct(fl['pool_share'])}, {fl['badge']}, "
                   f"{fl['mech']['kind']})")
    else:
        outcome = f"rung {facts['degradation']['rung']}"
    # The page numbers arms 1-based ("arm 3 of 4"); the sweep numbered them
    # 0-based, so a reader picking a row from sweep.md opened the wrong
    # section of the page.
    return [f"{focal_name(h)} {h['league']}",
            f"arm {h['arm'] + 1} of {h['n_arms']}",
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
    wide = ' (wider than 40% of the grid)' if alt['too_wide'] else ''
    if facts['floor'] is None:
        return f"yes ({_plural(alt['n_exclusive'], 'cell')} vs the grid){wide}"
    return (f"yes ({_plural(alt['n_guaranteed'], 'cell')} vs the floor, "
            f"{alt['n_exclusive']} vs the grid){wide}")


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
    # Required, with no default: a forgotten flag used to write the pages and
    # sweep.md into whatever directory the command ran from, which for this
    # script is the repo working tree.
    ap.add_argument('--out', required=True,
                    help='output directory (required; nothing is written to '
                         'the working directory by default)')
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
