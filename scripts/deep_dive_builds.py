#!/usr/bin/env python
"""BUILDS for the dive page's "Which one to build?" section.

A render-time port of the two 2026-09 analysis rounds that established the
section's v4 object:

- ``userdata/analysis/2026-09-15_spread_sets/spread_sets.py`` -- the five
  generators (S1-S5) that name SETS of IV spreads worth building.
- ``userdata/analysis/2026-09-16_builds/builds_lattice.py`` -- the lattice of
  intersections over those sets, and the 2-3 BUILDS selected from it.

Those two scripts are the reference implementation and stay where they are;
this module reproduces their numbers (``tests/test_deep_dive_builds.py`` pins
the Sableye figures against them) with one parameter added: the selection
ranking is driven by a per-shield-scenario WEIGHT VECTOR, so the page can
offer the reader a "Build criteria" preset. The default preset weights all
nine scenarios 1 and is, by construction, the reference behaviour.

Vocabulary (docs style rule, per document):

- Spread: one of the 4096 (attack IV, defense IV, stamina IV) combinations at
  its own best level for the league cap. Written ``a/d/s@level``.
- SP (stat product): attack x defense x HP; SP rank 1 is the bulkiest spread.
- Arm: one moveset of the blob. Reader-facing text says "moveset".
- Cell: one (shield scenario, opponent) pair, e.g. ``0v1 Annihilape``.
- Decision cell: a cell whose opponent ranks in PvPoke's top
  :data:`RANK_GATE` for the league and whose win rate over the whole
  4096-spread grid is strictly inside :data:`WR_LO`..:data:`WR_HI` -- the IV
  choice, not the matchup, decides it.
- Material cell: a decision cell where the best single-stat threshold rule
  (attack / defense / HP / SP, either direction, >= :data:`MIN_SET` members)
  wins at no more than :data:`MATERIAL_BAR`. Non-material cells are ones a
  one-line rule almost claims already.
- Guaranteed (for a set or a region): EVERY member wins that cell.
- Outside rate: the win rate on that cell among the spreads NOT in the region
  -- how special the guarantee is.
- Build: an intersection of 1..4 named sets with at least :data:`MIN_BUILD`
  members, i.e. a region of the IV grid a player can actually aim at.
- Fork: a build disjoint from the primary whose guaranteed decision cells are
  also materially different (Jaccard < :data:`FORK_CELL_J`).
- Preset: one of the three Build-criteria weight vectors in :data:`PRESETS`.
- Jaccard: |A and B| / |A or B|.

NOTHING here simulates. Every number comes out of the blob's already-baked
score grid.
"""
from __future__ import annotations

import itertools
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deep_dive_brief as brief  # noqa: E402
import deep_dive_matchup_clusters as clusters  # noqa: E402
from deep_dive_lib.opponents import parse_opponent_spec  # noqa: E402

# ---------------------------------------------------------------------------
# Knobs. Every one is the reference implementation's value; changing one is a
# change to the shipped numbers, so they are named rather than inlined.
# ---------------------------------------------------------------------------
# --- spread_sets.py ---
MIN_SET = 100          # a set smaller than this is not a build target
DEDUP_J = 0.90         # sets this close by Jaccard are the same set
RANK_GATE = 50         # opponents beyond this rank do not decide a build
TOPK_CELLS = 12        # S3 / S5: how many contested cells to package
MAX_SETS = 18          # named sets kept per arm
CLUSTER_SCEN_KEEP = 3  # S1: best-silhouette scenarios kept, plus "all"
TYPICAL = 0.90
EXACT_J, J99, J95 = 1.0, 0.99, 0.95
MAX_BOX_CAND = 600
AXES = ('atk', 'def', 'hp')
MATERIAL_BAR = 0.95
FAMILY_ORDER = {'single': 1, 'two_box': 2, 'three_box': 3,
                'atk_floor_trade': 4, 'atk_floor_frontier': 5}
TRADE_KS = [round(float(x), 4) for x in np.arange(0.25, 3.0001, 0.125)]
EVAL_CAP = 25          # guaranteed rows kept by the set-ranking evaluation

# --- builds_lattice.py ---
TOPK = 8               # named sets entering the lattice
MAX_ORDER = 4          # intersections of up to this many sets
MIN_BUILD = 50         # a region smaller than this is not a build target
WR_LO, WR_HI = 0.02, 0.98
NEAR_FORK = 25
FORK_CELL_J = 0.80
NEAR_GUARANTEE = 0.90
BUILD_DEDUP = 0.90
# --- the nested wide build (2026-09-17 round 5, item 4) ---
# The lattice routinely holds a region that contains almost all of the
# primary's members in several times the spreads -- suppressed by the dedup
# and the fork rule, so the page never showed it although it is the obvious
# "how much can I relax Build 1?" answer. At most ONE is surfaced, next to
# the primary and never as a build of its own.
WIDE_MIN_FACTOR = 2     # times the primary's size it must be
# Round 6 (the reviews of the round-5 render) replaced the original
# "contains 90% of the primary's members" share test with FULL containment,
# and made a printable rule a filter rather than a preference. Ranked on
# guaranteed cells alone the rule picked, on Shadow Sableye, a region that
# dropped two of Build 1's own members and that no two- or three-stat rule
# fits: a row headed "Build 1 wide" that was neither wide around Build 1 nor
# a target a reader could aim at.
# Round 6b puts the region's PURPOSE ahead of its cell count in the ranking
# key: the standouts a build cannot reach are why the region is surfaced at
# all ("the standouts as ordinary members of Build 1 wide"), and the round-6
# key, which kept ranking on cells alone, picked a Shadow Sableye region that
# held neither standout over three supersets that held both. See
# :func:`wide_build`.

# ---------------------------------------------------------------------------
# The three Build-criteria presets (Michael's 2026-09-16 decision: three
# fixed presets, no free weights). ``scens`` is None for "every baked
# scenario, weight 1"; otherwise the scenario labels carrying weight 1.
# ---------------------------------------------------------------------------
PRESET_FLAT = 'flat'
PRESET_EVEN = 'even'
PRESET_ONE = 'one_one'
PRESETS = (
    (PRESET_FLAT, 'All shields, equal', None, 'all shields, equal'),
    (PRESET_EVEN, 'Even shields (0v0, 1v1, 2v2)', ('0v0', '1v1', '2v2'),
     'even shields'),
    (PRESET_ONE, '1v1 only (open GBL lead)', ('1v1',), '1v1 only'),
)
PRESET_KEYS = tuple(p[0] for p in PRESETS)
PRESET_LABEL = {p[0]: p[1] for p in PRESETS}
PRESET_SCENS = {p[0]: p[2] for p in PRESETS}
PRESET_TAG = {p[0]: p[3] for p in PRESETS}


def preset_weights(key, scen_labels):
    """The per-scenario weight vector for one preset, in grid order.

    A preset naming scenarios this dive did not bake weights nothing, which
    is a real possibility (a dive can bake the three even scenarios only).
    :func:`preset_is_live` is the caller's check; this function never
    silently substitutes another preset's weights.
    """
    want = PRESET_SCENS[key]
    if want is None:
        return np.ones(len(scen_labels), dtype=np.float64)
    return np.array([1.0 if lbl in want else 0.0 for lbl in scen_labels],
                    dtype=np.float64)


def preset_is_live(key, scen_labels):
    """Does this preset weight at least one scenario this dive baked?"""
    return bool(preset_weights(key, scen_labels).sum() > 0)


# ---------------------------------------------------------------------------
# small helpers (ported verbatim from spread_sets.py)
# ---------------------------------------------------------------------------

def jac(a_n, b_n, inter):
    u = a_n + b_n - inter
    return (inter / u) if u else 0.0


def mask_jac(m1, m2):
    inter = int((m1 & m2).sum())
    return jac(int(m1.sum()), int(m2.sum()), inter)


def cell_jac(g1, g2):
    """Jaccard over two guaranteed-cell boolean vectors (0.0 when both empty).

    Deliberately UNWEIGHTED, on every decision cell, even under a preset that
    zeroes six scenarios: it answers "are these two regions the same build",
    which is a property of the regions and not of the reader's shield prior.
    A weighted version would call two regions that differ only in 0v1 the
    same build under the 1v1 preset and name one of them a fork under the
    default -- the same page describing one geometry two ways.
    """
    u = int((g1 | g2).sum())
    return (int((g1 & g2).sum()) / u) if u else 0.0


def iv_str(meta, i):
    a, d, s, lv = meta[i, 0], meta[i, 1], meta[i, 2], meta[i, 3]
    return f"{int(a)}/{int(d)}/{int(s)}@{lv:g}"


def print_thr(t, vals, op):
    """Shortest decimal that selects exactly the same spreads as ``t``."""
    want = int((vals >= t).sum()) if op == '>=' else int((vals <= t).sum())
    for dp in (0, 1, 2, 3, 4, 5):
        f = 10 ** dp
        p = (np.floor(t * f) / f) if op == '>=' else (np.ceil(t * f) / f)
        got = int((vals >= p).sum()) if op == '>=' else int((vals <= p).sum())
        if got == want:
            return float(p), dp
    return float(t), 6


class Scanner:
    """Pre-sorted per-(axis, direction) order so a threshold sweep is O(n)."""

    def __init__(self, planes):
        self.planes = planes
        self.ord = {}
        self.sorted = {}
        self.blocks = {}
        for ax in AXES:
            for op in ('>=', '<='):
                s = planes[ax] if op == '>=' else -planes[ax]
                o = np.argsort(-s, kind='stable')
                sd = s[o]
                idx = np.nonzero(np.r_[sd[1:] != sd[:-1], True])[0]
                self.ord[(ax, op)] = o
                self.sorted[(ax, op)] = sd
                self.blocks[(ax, op)] = idx

    def best_cut(self, ax, op, target, sel=None):
        """Best threshold on one axis (others fixed by ``sel``), by Jaccard."""
        o = self.ord[(ax, op)]
        idx = self.blocks[(ax, op)]
        t = target[o]
        if sel is None:
            n_cum = np.arange(1, t.size + 1)
            tp_cum = np.cumsum(t)
        else:
            m = sel[o]
            n_cum = np.cumsum(m)
            tp_cum = np.cumsum(m & t)
        n = n_cum[idx].astype(np.float64)
        tp = tp_cum[idx].astype(np.float64)
        T = float(target.sum())
        u = T + n - tp
        j = np.where(u > 0, tp / np.maximum(u, 1e-12), 0.0)
        b = int(np.argmax(j))
        v = float(self.sorted[(ax, op)][idx[b]])
        thr = v if op == '>=' else -v
        return thr, float(j[b]), int(n[b])


def rule_mask(rule, planes, n):
    m = np.ones(n, dtype=bool)
    for ax, op, t in rule:
        m &= (planes[ax] >= t) if op == '>=' else (planes[ax] <= t)
    return m


def rule_str(rule, planes):
    bits = []
    for ax, op, t in rule:
        p, _dp = print_thr(t, planes[ax], op)
        word = {'atk': 'atk', 'def': 'def', 'hp': 'HP'}[ax]
        bits.append(f"{word} {op} {p:g}")
    return ' and '.join(bits)


# One spelling per stat on the PAGE ("Atk", "Def", "HP") and at least two
# decimals on every threshold, so the section's fact strip and its builds
# table cannot print one rectangle two ways. Applied at DISPLAY time only:
# the ``rule`` field itself stays byte-identical to the reference
# implementation's, which is what tests/test_deep_dive_builds.py compares
# against ``*_builds.json`` field for field.
_STAT_CASE = {'atk': 'Atk', 'def': 'Def', 'hp': 'HP'}
_STAT_WORD = re.compile(r'\b(atk|def|hp)\b', re.IGNORECASE)
_STAT_THRESH = re.compile(r'\b(atk|def)(\s*(?:>=|<=)\s*)(\d+)(\.\d+)?\b',
                          re.IGNORECASE)


def _two_dp(text):
    """Pad a bare number to two decimals, never TRUNCATING one.

    ``print_thr`` returns the shortest decimal that selects exactly the same
    spreads, so 345.067 is load-bearing to three places and must survive;
    only 101.4 -> 101.40 and 125 -> 125.00 are padded.
    """
    whole, _, frac = str(text).partition('.')
    if len(frac) >= 2:
        return str(text)
    return whole + '.' + (frac + '00')[:2]


def display_rule(text):
    """A rule string as the page prints it.

    Two decimals on the CONTINUOUS stats only. HP is an integer stat and the
    page's fact strip has always printed it as one ("Def >= 101.40, HP >=
    125"); padding it to 125.00 would make the two surfaces disagree the
    other way round.
    """
    if not text:
        return text
    out = _STAT_THRESH.sub(
        lambda m: (_STAT_CASE[m.group(1).lower()] + m.group(2)
                   + _two_dp(m.group(3) + (m.group(4) or ''))), text)
    return _STAT_WORD.sub(lambda m: _STAT_CASE[m.group(0).lower()], out)


def fit_box(target, planes, sc, axes, ops, n):
    """Coordinate ascent; each per-axis step is exact given the rest."""
    rule = []
    for ax, op in zip(axes, ops):
        v = planes[ax][target]
        rule.append((ax, op, float(v.min() if op == '>=' else v.max())))
    best_j = -1.0
    for _ in range(8):
        improved = False
        for k in range(len(rule)):
            others = [r for i, r in enumerate(rule) if i != k]
            sel = rule_mask(others, planes, n) if others else None
            ax, op, _t = rule[k]
            thr, j, _nn = sc.best_cut(ax, op, target, sel)
            if j > best_j + 1e-12:
                best_j = j
                rule[k] = (ax, op, thr)
                improved = True
        if not improved:
            break
    m = rule_mask(rule, planes, n)
    return rule, mask_jac(m, target), m


def best_cut_vals(vals, op, target, sel=None, order=None):
    """Exact best single threshold on an ARBITRARY value vector, by Jaccard."""
    s = vals if op == '>=' else -vals
    if order is None:
        order = np.argsort(-s, kind='stable')
    sd = s[order]
    idx = np.nonzero(np.r_[sd[1:] != sd[:-1], True])[0]
    t = target[order]
    if sel is None:
        n_cum = np.arange(1, t.size + 1)
        tp_cum = np.cumsum(t)
    else:
        m = sel[order]
        n_cum = np.cumsum(m)
        tp_cum = np.cumsum(m & t)
    nn = n_cum[idx].astype(np.float64)
    tp = tp_cum[idx].astype(np.float64)
    T = float(target.sum())
    u = T + nn - tp
    j = np.where(u > 0, tp / np.maximum(u, 1e-12), 0.0)
    b = int(np.argmax(j))
    v = float(sd[idx[b]])
    return (v if op == '>=' else -v), float(j[b])


def _desc_entry(fam, text, m, target, rule=None, extra=None):
    nr = int(m.sum())
    inter = int((m & target).sum())
    e = {'family': fam, 'rule': text, 'n_rule': nr,
         'jaccard': jac(int(target.sum()), nr, inter),
         'n_missing': int(target.sum()) - inter, 'n_extra': nr - inter}
    if rule is not None:
        e['terms'] = [[ax, op, float(t)] for ax, op, t in rule]
    if extra:
        e.update(extra)
    return e


def fit_linear_trade(target, planes, n):
    """``atk >= a and Def + k*HP >= c`` -- the genre's sentence in two numbers."""
    if target.sum() < 2:
        return None
    atk, dfn, hp = planes['atk'], planes['def'], planes['hp']
    a_ord = np.argsort(-atk, kind='stable')

    def scan(k):
        v = dfn + float(k) * hp
        v_ord = np.argsort(-v, kind='stable')
        aT = float(atk[target].min())
        cT = float(v[target].min())
        jb = -1.0
        for _ in range(5):
            improved = False
            t_new, j_new = best_cut_vals(atk, '>=', target, v >= cT, a_ord)
            if j_new > jb + 1e-12:
                jb, aT, improved = j_new, t_new, True
            c_new, j_new = best_cut_vals(v, '>=', target, atk >= aT, v_ord)
            if j_new > jb + 1e-12:
                jb, cT, improved = j_new, c_new, True
            if not improved:
                break
        return jb, float(k), aT, cT, v

    best = None
    for k in TRADE_KS:
        r = scan(k)
        if best is None or r[0] > best[0]:
            best = r
    k0 = best[1]
    for k in np.arange(max(0.05, k0 - 0.125), k0 + 0.1251, 0.025):
        r = scan(float(k))
        if r[0] > best[0] + 1e-12:
            best = r
    _jb, k, aT, cT, v = best
    pa, _ = print_thr(aT, atk, '>=')
    pc, _ = print_thr(cT, v, '>=')
    m = (atk >= pa) & (v >= pc)
    text = f"atk >= {pa:g} and Def + {k:g}*HP >= {pc:g}"
    return _desc_entry('atk_floor_trade', text, m, target, extra={
        'trade_terms': {'atk_floor': float(pa), 'k': float(k), 'c': float(pc)},
        'trade_k': float(k),
        'trade': f"1 HP buys ~{k:g} Def (linear fit, not a staircase)"})


def fit_frontier(target, planes, n):
    """atk >= T and Def >= d(HP): a staircase that covers every member."""
    if target.sum() < 2:
        return None
    atk, dfn, hp = planes['atk'], planes['def'], planes['hp']
    aT = float(atk[target].min())
    steps = []
    need = np.full(n, np.inf)
    for h in np.unique(hp[target]):
        sel = target & (hp == h)
        d = float(dfn[sel].min())
        need[hp == h] = d
        # The 4th field is the decimal the PAGE prints for this step: the
        # shortest one that selects exactly the same spreads at this HP row.
        # Formatting the raw float rounds half-up, which lands ABOVE the
        # true floor and excludes the boundary member of the step, so a
        # reader applying the printed rule literally rebuilt a smaller
        # build than the one it claimed to describe (2026-09-16 round-3
        # review: 61 members, 57 selected).
        steps.append((float(h), d, int(sel.sum()),
                      print_thr(d, dfn[hp == h], '>=')[0]))
    m = (atk >= aT) & (dfn >= need)
    hs = np.array([s[0] for s in steps])
    ds = np.array([s[1] for s in steps])
    slope = r2 = None
    monotone = bool(np.all(np.diff(ds) <= 1e-9))
    if hs.size >= 3 and np.ptp(hs) > 0:
        A = np.vstack([hs, np.ones_like(hs)]).T
        coef, *_ = np.linalg.lstsq(A, ds, rcond=None)
        slope = float(coef[0])
        pred = A @ coef
        ss_res = float(((ds - pred) ** 2).sum())
        ss_tot = float(((ds - ds.mean()) ** 2).sum())
        r2 = (1.0 - ss_res / ss_tot) if ss_tot > 0 else None
    pa, _ = print_thr(aT, atk, '>=')
    text = f"atk >= {pa:g} and Def >= d(HP) [{len(steps)} steps]"
    return _desc_entry('atk_floor_frontier', text, m, target, extra={
        'atk_floor': aT, 'steps': [[a, b, c, e] for a, b, c, e in steps],
        'slope_def_per_hp': slope, 'slope_r2': r2, 'monotone': monotone,
        'trade': (None if slope is None or slope >= 0
                  else f"1 HP buys ~{-slope:.2f} Def")})


def describe(target, planes, sc, n):
    """Every candidate description of one set, simplest family first."""
    T = int(target.sum())
    if T == 0:
        return []
    cands = []
    best = None
    for ax in AXES:
        for op in ('>=', '<='):
            thr, j, _ = sc.best_cut(ax, op, target)
            if best is None or j > best[1]:
                best = ([(ax, op, thr)], j)
    cands.append(('single', best[0]))
    pairs = (('atk', 'def'), ('atk', 'hp'), ('def', 'hp'))
    b2 = None
    for pa in pairs:
        for o1 in ('>=', '<='):
            for o2 in ('>=', '<='):
                r, j, _m = fit_box(target, planes, sc, pa, (o1, o2), n)
                if b2 is None or j > b2[1]:
                    b2 = (r, j)
    cands.append(('two_box', b2[0]))
    b3 = None
    for o1 in ('>=', '<='):
        for o2 in ('>=', '<='):
            for o3 in ('>=', '<='):
                r, j, _m = fit_box(target, planes, sc, AXES, (o1, o2, o3), n)
                if b3 is None or j > b3[1]:
                    b3 = (r, j)
    cands.append(('three_box', b3[0]))
    out = []
    for fam, rule in cands:
        m = rule_mask(rule, planes, n)
        out.append(_desc_entry(fam, rule_str(rule, planes), m, target, rule))
    lt = fit_linear_trade(target, planes, n)
    if lt is not None:
        out.append(lt)
    fr = fit_frontier(target, planes, n)
    if fr is not None:
        out.append(fr)
    return out


def pick_descriptions(descs):
    """Simplest family reaching exact / 99% / 95% fidelity."""
    def simplest(bar):
        ok = [d for d in descs if d['jaccard'] >= bar - 1e-12]
        if not ok:
            return None
        ok.sort(key=lambda d: (FAMILY_ORDER[d['family']], -d['jaccard']))
        return ok[0]
    return {'exact': simplest(EXACT_J), 'd99': simplest(J99),
            'd95': simplest(J95)}


# ---------------------------------------------------------------------------
# per-arm context
# ---------------------------------------------------------------------------

def build_ctx(state, arm, mode='pvpoke', level='l50'):
    """Everything both halves of the port read, computed once per arm."""
    scores, meta = brief.arm_view(state, arm, mode, level=level)
    n_iv = scores.shape[0]
    win = brief.win_cube(scores)
    n_sc, n_opp = win.shape[1], win.shape[2]
    atk, dfn, hp = brief.stat_planes(meta)
    planes = {'atk': atk, 'def': dfn, 'hp': hp}
    sp = atk * dfn * hp
    order = np.argsort(-sp, kind='stable')
    sp_rank = np.empty(n_iv, int)
    sp_rank[order] = np.arange(1, n_iv + 1)
    triage = brief.stage1_triage(win)
    names = state['opponent_names']
    ranks = brief.build_opp_meta_ranks(names, state['league'],
                                       cup=state.get('cup'))
    win2 = win.reshape(n_iv, n_sc * n_opp)
    scen_labels = [brief.scenario_label(state, si) for si in range(n_sc)]
    cells = []
    for si in range(n_sc):
        for oi in range(n_opp):
            k = si * n_opp + oi
            rep = triage['dedup_of'][(si, oi)][1]
            cells.append({
                'k': k, 'si': si, 'oi': oi,
                'label': brief.cell_label(state, si, oi),
                'scenario': scen_labels[si],
                'rank': ranks[oi],
                'contested': bool(triage['contested_mask'][si, oi]),
                'degenerate': bool(triage['degenerate'][si]),
                'rep': rep == oi,
                'wr': float(win2[:, k].mean()),
            })
    other = {}
    for m in state['opp_iv_modes']:
        if m == mode:
            continue
        sc_m, _meta_m = brief.arm_view(state, arm, m, level=level)
        other[m] = brief.win_cube(sc_m).reshape(n_iv, n_sc * n_opp)
    # The scatter's DEFAULT y axis, recomputed here on the same numbers the
    # page draws: mean battle score over every (scenario, opponent) cell.
    # ``deep_dive_rendering.scenario_ranks`` computes the identical quantity
    # from the page's own flat score array, and its argmax -- the spread the
    # scatter puts highest -- is one of the section's two standouts, so the
    # two surfaces must be reading one number. Measured equal on Shadow
    # Sableye GL arm 0 (534.2090643274854, spread 9/6/13@47.5).
    avg_score = scores.reshape(n_iv, -1).mean(axis=1)
    return dict(other_modes=other, state=state, arm=arm, mode=mode, meta=meta,
                scores=scores, win=win, win2=win2, planes=planes, atk=atk,
                dfn=dfn, hp=hp, sp=sp, sp_rank=sp_rank, n_iv=n_iv, n_sc=n_sc,
                n_opp=n_opp, triage=triage, cells=cells, names=names,
                avg_score=avg_score, best_score=int(np.argmax(avg_score)),
                scen_labels=scen_labels, sc=Scanner(planes),
                label=state['moveset_data'][arm]['label'])


def strict_decision_cells(ctx, rank_gate=RANK_GATE):
    """Contested, rank-gated, non-degenerate, deduplicated cells.

    ``spread_sets.decision_cells``. This is the stricter definition, used for
    the SET-ranking evaluation only; the builds half uses
    :func:`lattice_decision_cells`, which is the definition the page prints.
    """
    return [c for c in ctx['cells']
            if c['contested'] and not c['degenerate'] and c['rep']
            and c['rank'] is not None and c['rank'] <= rank_gate]


def lattice_decision_cells(ctx):
    """``builds_lattice``'s decision cells: rank gate + contest band."""
    return [c for c in ctx['cells']
            if c['rank'] is not None and c['rank'] <= RANK_GATE
            and WR_LO < c['wr'] < WR_HI]


def species_cell(ctx, c):
    """The (scenario, opponent SPECIES) a cell belongs to."""
    sp, _v, sh = parse_opponent_spec(ctx['names'][c['oi']])
    return f"{c['scenario']} {sp}{' (Shadow)' if sh else ''}"


def _plane(ctx, ax):
    return ctx['sp'] if ax == 'sp' else ctx['planes'][ax]


def single_stat_guarantee(ctx):
    """Per cell: the largest single-stat rule whose every member wins it."""
    win2 = ctx['win2']
    n_cells = win2.shape[1]
    res = {}
    for key, axlist in (('adh', AXES), ('sp', ('sp',))):
        best = np.zeros(n_cells, dtype=int)
        for ax in axlist:
            base = _plane(ctx, ax)
            for op in ('>=', '<='):
                s = base if op == '>=' else -base
                top_loser = np.where(win2, -np.inf, s[:, None]).max(axis=0)
                n_c = (s[:, None] > top_loser[None, :]).sum(axis=0)
                best = np.maximum(best, n_c)
        res[key] = best
    res['any'] = np.maximum(res['adh'], res['sp'])
    return res


def single_stat_best_rate(ctx, ks, min_set=MIN_SET):
    """Best win RATE on each cell reachable by one single-stat threshold."""
    ks = list(ks)
    if not ks:
        return {}
    W = ctx['win2'][:, ks]
    n = W.shape[0]
    sizes = np.arange(1, n + 1, dtype=np.float64)
    big = sizes >= min_set
    best = np.zeros(len(ks))
    for ax in AXES + ('sp',):
        base = _plane(ctx, ax)
        for op in ('>=', '<='):
            s = base if op == '>=' else -base
            o = np.argsort(-s, kind='stable')
            sd = s[o]
            cum = np.cumsum(W[o], axis=0, dtype=np.int32)
            valid = big & np.r_[sd[1:] != sd[:-1], True]
            if not valid.any():
                continue
            rates = cum[valid] / sizes[valid][:, None]
            best = np.maximum(best, rates.max(axis=0))
    return {int(k): round(float(b), 4) for k, b in zip(ks, best)}


# ---------------------------------------------------------------------------
# set evaluation (only the parts the set RANKING needs)
# ---------------------------------------------------------------------------

def rank_interest(mask, ctx, single_n, dec, cap=EVAL_CAP):
    """``spread_sets``' ranking score for one named set.

    The reference computes a full evaluation block and ranks on three of its
    numbers; only those three are needed here, and they are computed the same
    way -- including the cap. The cap is load-bearing, not cosmetic: the
    reference reads its guaranteed list AFTER truncating it to the 25
    best-ranked rows, so a set guaranteeing 40 cells scores as 25.
    """
    n = int(mask.sum())
    sub = ctx['win2'][mask]
    rate = sub.sum(axis=0) / n
    rows = [c for c in dec if rate[c['k']] >= 1.0]
    rows.sort(key=lambda c: c['rank'])
    rows = rows[:cap]
    hard = sum(1 for c in rows if single_n[c['k']] < MIN_SET)
    return hard * 1000 + len({c['label'] for c in rows}) * 10 + n / ctx['n_iv']


# ---------------------------------------------------------------------------
# generators S1-S5
# ---------------------------------------------------------------------------

def gen_S1(ctx, computed=None):
    """Fingerprint clusters, from the Matchup clusters module.

    ``computed`` lets the caller hand in the page's own already-computed
    clusters result for the arm the clusters section was baked on -- the
    labels, silhouettes and root rules this generator reads do not depend on
    the ``is_named`` callback (it feeds ``flip_table`` only), so the shared
    result is the same partition the section draws, not a second one.
    """
    out = []
    if computed is None:
        flat = np.asarray(ctx['scores']).reshape(-1)
        computed = clusters.compute_matchup_clusters(
            flat, ctx['n_iv'], ctx['n_sc'], ctx['n_opp'],
            [tuple(s) for s in ctx['state']['shield_scenarios']],
            ctx['atk'], ctx['dfn'], ctx['hp'], lambda b, s: False)
    # The per-preset combined entries (``all__even``, ...) are EXCLUDED: the
    # generators are a property of the arm, not of the reader's preset, and
    # letting one compete for the three per-scenario seats would make the
    # named sets -- and so every preset's builds -- depend on which extra
    # partitions the clusters section happened to bake.
    live = [(k, v) for k, v in computed.items()
            if 'res' in v and (k == clusters.ALL_SCEN_KEY
                               or not clusters.is_all_scen_key(k))]
    live.sort(key=lambda kv: -kv[1]['res']['silhouette'])
    keep = [k for k, _v in live if k == clusters.ALL_SCEN_KEY]
    keep += [k for k, _v in live if k != clusters.ALL_SCEN_KEY][:CLUSTER_SCEN_KEEP]
    for k in keep:
        r = computed[k]['res']
        for c in range(r['k']):
            m = r['labels'] == c
            if m.sum() < MIN_SET:
                continue
            out.append({'generator': 'S1', 'name': f"S1 {k} cluster {c}",
                        'mask': m,
                        'provenance': {'scenario': k, 'cluster': c,
                                       'k': r['k']}})
    return out, computed


def gen_S2(ctx, facts):
    """Verdict sets: the brief's floor, its printed rungs, its rectangle."""
    out = []
    planes = ctx['planes']
    fl = facts.get('floor')
    if fl:
        ax = fl['axis']
        out.append({'generator': 'S2',
                    'name': f"S2 floor ({ax} >= {fl['printed']:g})",
                    'mask': planes[ax] >= fl['T'],
                    'provenance': {'kind': 'floor', 'axis': ax,
                                   'printed': fl['printed']}})
        for r in facts.get('rungs_above', []):
            out.append({'generator': 'S2',
                        'name': f"S2 rung ({ax} >= {r['printed']:g})",
                        'mask': planes[ax] >= r['T'],
                        'provenance': {'kind': 'rung', 'axis': ax,
                                       'printed': r['printed']}})
    alt = facts.get('alternative')
    if alt and alt.get('n'):
        a, b = alt['axes']
        out.append({'generator': 'S2', 'name': 'S2 alternative rectangle',
                    'mask': (planes[a] >= alt['cut_a']) & (planes[b] >= alt['cut_b']),
                    'provenance': {'kind': 'alternative',
                                   'axes': list(alt['axes'])}})
    return [o for o in out if o['mask'].sum() >= MIN_SET]


def top_cells(ctx, dec, k=TOPK_CELLS):
    d = sorted(dec, key=lambda c: (abs(c['wr'] - 0.5), c['rank']))
    return d[:k]


def gen_S3(ctx, cells):
    """Packages: intersections of the most contested cells' winner sets."""
    out = []
    singles = {c['k']: ctx['win2'][:, c['k']] for c in cells}
    for r in (2, 3):
        for combo in itertools.combinations(cells, r):
            m = np.ones(ctx['n_iv'], bool)
            for c in combo:
                m &= singles[c['k']]
            if m.sum() < MIN_SET:
                continue
            if any(mask_jac(m, s) >= DEDUP_J for s in singles.values()):
                continue
            out.append({'generator': 'S3',
                        'name': "S3 package [" + " & ".join(c['label'] for c in combo) + "]",
                        'mask': m,
                        'provenance': {'kind': 'package', 'r': r,
                                       'cells': [c['label'] for c in combo]}})
    out.sort(key=lambda o: -int(o['mask'].sum()))
    return out[:8]


def gen_S4(ctx, facts, cells):
    """Frontier sets: inside an attack floor, the least Def per attained HP."""
    out = []
    fl = facts.get('floor')
    floors = []
    if fl and fl['axis'] == 'atk':
        floors.append((fl['T'], fl['printed']))
        for r in facts.get('rungs_above', [])[:2]:
            floors.append((r['T'], r['printed']))
    if not floors:
        return out
    atk, dfn, hp = ctx['atk'], ctx['dfn'], ctx['hp']
    for T, printed in floors:
        clear = atk >= T
        if clear.sum() < MIN_SET:
            continue
        for c in cells:
            w = ctx['win2'][:, c['k']]
            rate = float(w[clear].mean())
            if rate >= 0.999 or rate < 0.10:
                continue
            need = np.full(ctx['n_iv'], np.inf)
            steps = []
            for h in np.unique(hp[clear]):
                hi = clear & (hp >= h)
                lose_d = dfn[hi & ~w]
                if lose_d.size == 0:
                    d = float(dfn[hi].min())
                else:
                    above = np.unique(dfn[dfn > lose_d.max()])
                    if above.size == 0:
                        continue
                    d = float(above.min())
                need[hp == h] = d
                steps.append((float(h), d))
            m = clear & (dfn >= need)
            if m.sum() < MIN_SET or not ctx['win2'][m, c['k']].all():
                continue
            out.append({'generator': 'S4',
                        'name': f"S4 frontier (atk >= {printed:g} -> {c['label']})",
                        'mask': m,
                        'provenance': {'kind': 'frontier', 'atk_printed': printed,
                                       'cell': c['label'],
                                       'steps': [[a, b] for a, b in steps]}})
    out.sort(key=lambda o: -int(o['mask'].sum()))
    return out[:6]


def _cands(vals, losers, cap=MAX_BOX_CAND):
    uv = np.unique(vals)
    lv = np.unique(losers)
    idx = np.searchsorted(uv, lv, side='right')
    idx = idx[idx < uv.size]
    cand = np.unique(np.r_[uv[:1], uv[idx]])
    if cand.size > cap:
        cand = cand[np.linspace(0, cand.size - 1, cap).astype(int)]
    return cand, bool(cand.size > cap)


def largest_box(w, ctx, pair, ops):
    """Largest two-stat box every member of which wins the cell (w)."""
    planes = ctx['planes']
    a = planes[pair[0]] if ops[0] == '>=' else -planes[pair[0]]
    b = planes[pair[1]] if ops[1] == '>=' else -planes[pair[1]]
    cand, _sub = _cands(a, a[~w])
    A = a[:, None] >= cand[None, :]
    lose = (A & ~w[:, None])
    top = np.where(lose, b[:, None], -np.inf).max(axis=0)
    n = (A & (b[:, None] > top[None, :])).sum(axis=0)
    i = int(np.argmax(n))
    if n[i] < MIN_SET:
        return None
    ta = float(cand[i])
    sel = a >= ta
    lb = b[sel & ~w]
    if lb.size == 0:
        tb = float(b[sel].min())
    else:
        ab = np.unique(b[b > lb.max()])
        if ab.size == 0:
            return None
        tb = float(ab.min())
    rule = [(pair[0], ops[0], ta if ops[0] == '>=' else -ta),
            (pair[1], ops[1], tb if ops[1] == '>=' else -tb)]
    return rule, rule_mask(rule, planes, ctx['n_iv'])


def probe_cells(ctx, dec, single_n, k=TOPK_CELLS, extra=20):
    top = top_cells(ctx, dec, k)
    have = {c['label'] for c in top}
    hard = [c for c in dec
            if c['label'] not in have and single_n[c['k']] < MIN_SET]
    hard.sort(key=lambda c: (c['rank'], -abs(c['wr'] - 0.5)))
    return top + hard[:extra]


def gen_S5(ctx, cells):
    """Largest two-stat box inside one cell's winner set."""
    out = []
    pairs = (('atk', 'def'), ('atk', 'hp'), ('def', 'hp'))
    for c in cells:
        w = ctx['win2'][:, c['k']]
        best = None
        for pa in pairs:
            for o1 in ('>=', '<='):
                for o2 in ('>=', '<='):
                    r = largest_box(w, ctx, pa, (o1, o2))
                    if r is None:
                        continue
                    rule, m = r
                    if not w[m].all():
                        continue
                    if best is None or m.sum() > best[1].sum():
                        best = (rule, m)
        if best is None:
            continue
        rule, m = best
        if mask_jac(m, w) >= DEDUP_J:
            continue          # the box IS the winner set; not two-stat structure
        out.append({'generator': 'S5', 'name': f"S5 box -> {c['label']}",
                    'mask': m,
                    'provenance': {'kind': 'guarantee_box', 'cell': c['label'],
                                   'rule': rule_str(rule, ctx['planes'])}})
    out.sort(key=lambda o: -int(o['mask'].sum()))
    return out[:8]


def named_sets(ctx, facts, computed=None):
    """Every generator, deduplicated by member overlap, ranked, capped.

    Returns ``(sets, clusters_result)``; each set carries ``mask``, ``name``,
    ``generator``, ``provenance`` and ``aliases``.
    """
    sg = single_stat_guarantee(ctx)
    single_n = sg['adh']
    dec_strict = strict_decision_cells(ctx)
    cells = top_cells(ctx, dec_strict)
    s1, computed = gen_S1(ctx, computed)
    s2 = gen_S2(ctx, facts)
    s3 = gen_S3(ctx, cells)
    s4 = gen_S4(ctx, facts, cells)
    s5 = gen_S5(ctx, probe_cells(ctx, dec_strict, single_n))
    raw = s2 + s1 + s3 + s4 + s5          # dedup keeps the earliest generator
    kept = []
    for cand in raw:
        if cand['mask'].sum() < MIN_SET:
            continue
        hit = None
        for k in kept:
            if mask_jac(cand['mask'], k['mask']) >= DEDUP_J:
                hit = k
                break
        if hit is not None:
            hit['aliases'].append({'name': cand['name'],
                                   'generator': cand['generator']})
            continue
        cand['aliases'] = []
        kept.append(cand)
    for s in kept:
        s['_interest'] = rank_interest(s['mask'], ctx, single_n, dec_strict)
    kept.sort(key=lambda s: -s['_interest'])
    return kept[:MAX_SETS], computed


# ---------------------------------------------------------------------------
# the lattice, parameterised by a shield-scenario weight vector
# ---------------------------------------------------------------------------

def cell_frame(ctx):
    """The decision cells the builds half prints, with their material flag.

    Computed ONCE per arm and shared by all three presets: the cells are a
    property of the grid, not of the reader's shield prior. A preset changes
    only how the guaranteed ones are COUNTED.
    """
    cells = lattice_decision_cells(ctx)
    ks = [c['k'] for c in cells]
    rates = single_stat_best_rate(ctx, ks)
    for c in cells:
        c['best_single_rate'] = rates.get(c['k'])
        c['material'] = bool((c['best_single_rate'] or 0.0) <= MATERIAL_BAR)
    kidx = np.array(ks, dtype=int)
    mat = np.array([c['material'] for c in cells], dtype=bool)
    Wd = ctx['win2'][:, kidx] if len(kidx) else np.zeros((ctx['n_iv'], 0), bool)
    return dict(cells=cells, kidx=kidx, mat=mat, Wd=Wd)


def cell_weights(cells, weights):
    """Per-decision-cell weight, from the preset's per-scenario vector."""
    return np.array([float(weights[c['si']]) for c in cells],
                    dtype=np.float64)


def arm_lattice(ctx, sets, frame, weights):
    """Lattice + ranked intersections for one arm under one weight vector.

    The ranking key is (weighted guaranteed decision cells, weighted
    guaranteed MATERIAL cells, size), all descending -- the reference's
    (cells, material, size) key with the weight vector folded into the two
    counts. With every weight 1 it IS the reference key, which is what makes
    the default preset reproduce ``builds_lattice.py`` exactly.
    """
    n = ctx['n_iv']
    cells, mat, Wd = frame['cells'], frame['mat'], frame['Wd']
    w = cell_weights(cells, weights)
    wmat = w * mat

    def key(g, size):
        return (-float((g * w).sum()), -float((g * wmat).sum()), -int(size))

    named = []
    for s in sets:
        m = s['mask']
        g = Wd[m].all(axis=0) if Wd.shape[1] else np.zeros(0, bool)
        named.append({'name': s['name'], 'generator': s['generator'],
                      'aliases': s.get('aliases', []), 'mask': m,
                      'size': int(m.sum()), 'g': g,
                      'g_dec': int(g.sum()), 'g_mat': int((g & mat).sum()),
                      'wg': float((g * w).sum()),
                      'wg_mat': float((g * wmat).sum())})
    named.sort(key=lambda d: key(d['g'], d['size']))
    uniq = []
    for d in named:
        if any(mask_jac(d['mask'], p['mask']) >= 0.99 for p in uniq):
            continue
        uniq.append(d)
    pick = uniq[:TOPK]
    # ONE reserved seat for the highest-ranked set containing stat-product
    # rank-1 (the reference's deliberate deviation): the bulk side is the
    # whole point of the fork finding, and a cells-first ranking drops it
    # when it is small.
    if uniq and len(uniq) > TOPK:
        r1 = int(np.argmin(ctx['sp_rank']))
        r1set = next((d for d in uniq if d['mask'][r1]), None)
        if r1set is not None and not any(x is r1set for x in pick):
            pick[-1] = r1set
        pick.sort(key=lambda d: key(d['g'], d['size']))
    for i, p in enumerate(pick):
        p['key'] = chr(65 + i)

    pairs = []
    for a, b in itertools.combinations(pick, 2):
        sz = int((a['mask'] & b['mask']).sum())
        pairs.append({'a': a['key'], 'b': b['key'], 'size': sz,
                      'incompatible': sz == 0,
                      'near_fork': 0 < sz < NEAR_FORK})

    inters = []
    seen = set()
    for r in range(1, MAX_ORDER + 1):
        for combo in itertools.combinations(range(len(pick)), r):
            m = np.ones(n, bool)
            for c in combo:
                m &= pick[c]['mask']
            sz = int(m.sum())
            if sz < MIN_BUILD:
                continue
            sig = m.tobytes()
            if sig in seen:          # same region, longer recipe: keep shorter
                continue
            seen.add(sig)
            sub = Wd[m]
            g = sub.all(axis=0)
            rate = sub.mean(axis=0)
            inters.append({'combo': ''.join(pick[c]['key'] for c in combo),
                           'sets': [pick[c]['name'] for c in combo],
                           'size': sz, 'mask': m, 'g': g, 'rate': rate,
                           'n_g': int(g.sum()), 'n_g_mat': int((g & mat).sum()),
                           'wg': float((g * w).sum()),
                           'wg_mat': float((g * wmat).sum()),
                           'n_g90': int((rate >= NEAR_GUARANTEE).sum()),
                           'n_g90_mat': int(((rate >= NEAR_GUARANTEE) & mat).sum())})
    inters.sort(key=lambda d: key(d['g'], d['size']))
    return dict(frame=frame, w=w, wmat=wmat, pick=pick, pairs=pairs,
                inters=inters, key=key)


def bulk_box(ctx, L):
    """A (Def, HP) box anchored on rank-1, CONSTRUCTED rather than found."""
    frame = L['frame']
    dfn, hp, mat, Wd = ctx['planes']['def'], ctx['planes']['hp'], frame['mat'], frame['Wd']
    w, wmat = L['w'], L['wmat']
    r1 = int(np.argmin(ctx['sp_rank']))
    hv = np.unique(hp[hp <= hp[r1]])[::-1]
    best = None
    for h0 in hv[:32]:
        sel = hp >= h0
        if int(sel.sum()) < MIN_BUILD:
            continue
        dv = np.unique(dfn[sel & (dfn <= dfn[r1])])[::-1]
        d0 = next((d for d in dv if int((sel & (dfn >= d)).sum()) >= MIN_BUILD), None)
        if d0 is None:
            continue
        m = sel & (dfn >= d0)
        g = Wd[m].all(axis=0) if Wd.shape[1] else np.zeros(0, bool)
        rate = Wd[m].mean(axis=0) if Wd.shape[1] else np.zeros(0)
        score = (float((g * w).sum()), float((g * wmat).sum()), -int(m.sum()))
        if best is None or score > best[0]:
            best = (score, dict(
                combo='BULK',
                sets=[f"constructed (Def, HP) box on rank-1 "
                      f"(def >= {float(d0):g} and HP >= {float(h0):g})"],
                size=int(m.sum()), mask=m, g=g, rate=rate, constructed=True,
                n_g=int(g.sum()), n_g_mat=int((g & mat).sum()),
                wg=float((g * w).sum()), wg_mat=float((g * wmat).sum()),
                n_g90=int((rate >= NEAR_GUARANTEE).sum()),
                n_g90_mat=int(((rate >= NEAR_GUARANTEE) & mat).sum()),
                box=[float(d0), float(h0)]))
    return None if best is None else best[1]


def select_builds(ctx, L):
    """(a) primary, (b) fork, (c) the rank-1 / bulk build. Reference order."""
    r1 = int(np.argmin(ctx['sp_rank']))
    chosen = []
    fork_info = {'n_disjoint_candidates': 0, 'fork_cell_jaccard': None,
                 'rejected_variant': False}
    if L['inters']:
        a_build = L['inters'][0]
        chosen.append(('primary', a_build))
        disj = [d for d in L['inters'] if not (d['mask'] & a_build['mask']).any()]
        fork_info['n_disjoint_candidates'] = len(disj)
        fork = next((d for d in disj
                     if d['n_g'] >= 1 and cell_jac(d['g'], a_build['g']) < FORK_CELL_J),
                    None)
        if fork is not None:
            fork_info['fork_cell_jaccard'] = round(cell_jac(fork['g'], a_build['g']), 4)
            chosen.append(('fork', fork))
        elif disj:
            fork_info['rejected_variant'] = True

    def is_dup(b, kept):
        return any(int((b['mask'] & k['mask']).sum())
                   >= BUILD_DEDUP * min(b['size'], k['size']) for _, k in kept)

    kept = []
    for role, b in chosen:
        if not is_dup(b, kept):
            kept.append((role, b))
    r1_status = 'none'
    if kept:
        if any(b['mask'][r1] for _, b in kept):
            r1_status = 'in_' + next(ro for ro, b in kept if b['mask'][r1])
        else:
            r1b = next((d for d in L['inters']
                        if d['mask'][r1] and not is_dup(d, kept)), None)
            r1_status = 'found'
            if r1b is None:
                r1b = bulk_box(ctx, L)
                r1_status = 'constructed'
                if r1b is not None and is_dup(r1b, kept):
                    r1b, r1_status = None, 'suppressed_duplicate'
                elif r1b is not None:
                    L['inters'].append(r1b)
                else:
                    r1_status = 'none'
            if r1b is not None:
                kept.append(('rank1', r1b))
    return kept, r1_status, fork_info


# ---------------------------------------------------------------------------
# per-build facts
# ---------------------------------------------------------------------------

def region_rule(ctx, mask):
    """The rule the page would PRINT for a region, or None when none fits.

    One definition of "describable", used by :func:`region_block` (which
    prints it) and by :func:`wide_build` (which requires it), so the wide
    region can never be selected on a rule the table then declines to show.
    """
    return pick_descriptions(
        describe(mask, ctx['planes'], ctx['sc'], ctx['n_iv']))['d95']


def wide_build(L, primary, ctx=None, standout_idx=()):
    """The one region the page presents as "Build 1 wide", or None.

    A candidate is a region of the SAME lattice that

    * contains EVERY member of the primary -- "Build 1 wide" is a claim
      about Build 1, and a region missing two of its spreads is at best next
      to it (2026-09-17 round 6 review);
    * is at least :data:`WIDE_MIN_FACTOR` times its size; and
    * carries a rule at the fidelity the table prints (:func:`region_rule`),
      because the row exists to give a reader a LOOSER TARGET and "a list of
      157 spreads that no two- or three-stat rule fits" is not one.

    Among those, the ranking key is

    1. how many of ``standout_idx`` -- the preset's standouts that sit in no
       build -- the region holds (2 > 1 > 0); then
    2. the preset-weighted guaranteed-cell count; then
    3. size, ties to the larger region.

    Clauses 2 and 3 are the lattice's own ranking key minus its material
    tie-break, so among regions equal on the standouts the wide region is
    chosen by the same quantity the builds were. Clause 1 is what the region
    is FOR (2026-09-17 round 6b): Michael's stated purpose for surfacing it
    is "the standouts as ordinary members of Build 1 wide", and ranked on
    cells alone it picked, on Shadow Sableye, a region holding NEITHER
    standout over three supersets holding both -- a row whose paragraph had
    to end "it is not a route to them". With no outside standouts the key
    reduces to the round-6 one exactly.

    ``ctx`` is the arm context; passing None skips the rule filter (the
    synthetic-lattice tests, which carry no planes).

    The constructed bulk box is excluded: it is not an intersection of named
    sets, so "Build 1 without <set>" could never describe it and its rule is
    already printed as its own build's.

    Returns the ``inters`` dict, not a region block; the caller describes it.
    """
    pm = primary['mask']
    n_p = int(pm.sum())
    if not n_p:
        return None
    cands = []
    for d in L['inters']:
        if d.get('constructed'):
            continue
        size = int(d['size'])
        if size < WIDE_MIN_FACTOR * n_p:
            continue
        if int((pm & ~d['mask']).sum()):        # drops a member of Build 1
            continue
        held = sum(1 for i in standout_idx if bool(d['mask'][i]))
        cands.append(((held, float(d['wg']), size), d))
    # Best first, and the rule fitted LAZILY: describe() is a full search
    # over rule families and the first candidate carrying one is the answer.
    cands.sort(key=lambda kv: kv[0], reverse=True)
    for _key, d in cands:
        if ctx is None or region_rule(ctx, d['mask']) is not None:
            return d
    return None


def cell_rows(L, region_mask, g, ctx):
    """Evidence rows for the cells a region guarantees, by cell index."""
    frame = L['frame']
    cells, Wd = frame['cells'], frame['Wd']
    outside = ~region_mask
    n_out = int(outside.sum())
    out = []
    for ci, c in enumerate(cells):
        if not g[ci]:
            continue
        ow = float(Wd[outside, ci].mean()) if n_out else 0.0
        modes_ok = 1 + sum(1 for w in ctx['other_modes'].values()
                           if bool(w[region_mask, c['k']].all()))
        # RAW rates, not rounded here. The renderer rounds once, at print
        # time, and the emphasis band + the near-free test read the same raw
        # value: storing 4 dp double-rounded the printed percent (a true
        # 0.3749632677 stored as 0.375 printed 38% where the data says 37%)
        # and put a rate within 1e-4 of a band edge in the wrong band
        # (2026-09-16 round-3 review).
        out.append({'ci': ci, 'cell': c['label'], 'scenario': c['scenario'],
                    'rank': c['rank'], 'grid_wr': float(c['wr']),
                    'outside_wr': float(ow), 'material': c['material'],
                    'modes_ok': modes_ok})
    # Ascending outside rate: the rarest guarantee -- the one the rest of the
    # grid is least likely to hand a reader anyway -- reads first.
    out.sort(key=lambda r: (r['outside_wr'], r['rank']))
    return out


def region_block(L, ctx, inter, role, others, weights, wsum=None):
    """Everything the page prints about one selected build.

    ``wsum`` is :func:`weighted_wins` for this preset, computed once by the
    caller. The most-winning member is chosen ON THAT WEIGHTED COUNT, not on
    the all-nine total: the section's plot draws the weighted count on its y
    axis and marks this spread as its build's most-winning one, so a member
    picked by a quantity the axis is not showing would sit visibly below
    another member of its own build (the 2026-09-16 review measured exactly
    that: 8/7/5@50 marked at y=38 with 11/4/4@49.5 of the same build at 39).
    Under the default preset every weight is 1 and this IS the reference
    implementation's all-nine argmax.
    """
    n = ctx['n_iv']
    frame = L['frame']
    m, g = inter['mask'], inter['g']
    win2 = ctx['win2']
    if wsum is None:
        wsum = weighted_wins(ctx, weights)
    ids = np.nonzero(m)[0]
    tot = wsum[m]
    mw = int(ids[int(np.argmax(tot))])
    best_sp = ids[np.argsort(ctx['sp_rank'][ids])[:5]]
    r1 = int(np.argmin(ctx['sp_rank']))
    rows = cell_rows(L, m, g, ctx)
    by_scen = {}
    for r in rows:
        by_scen.setdefault(r['scenario'], []).append(r)
    gave = np.zeros(len(frame['cells']), bool)
    for o in others:
        gave |= o['g']
    gave &= ~g
    gave_rows = [{'ci': ci, 'cell': c['label'], 'rank': c['rank'],
                  'scenario': c['scenario'], 'material': c['material']}
                 for ci, c in enumerate(frame['cells']) if gave[ci]]
    d95 = region_rule(ctx, m)
    dblock = None
    if d95 is not None:
        dblock = {'family': d95['family'], 'rule': d95['rule'],
                  'jaccard': round(float(d95['jaccard']), 4),
                  'n_rule': d95['n_rule'], 'n_extra': d95['n_extra'],
                  'n_missing': d95['n_missing']}
        # The rule's own (axis, op, threshold) triples, for the stats view:
        # a box is only DRAWABLE as a rectangle if the panel can read its
        # per-axis cuts, and re-parsing the printed sentence in JS would be
        # a second implementation of the rule grammar.
        if d95.get('terms') is not None:
            dblock['terms'] = [[ax, op, float(t)] for ax, op, t in
                               d95['terms']]
        if d95.get('steps') is not None:
            dblock['steps'] = [[float(a), float(b), int(c), float(e)]
                               for a, b, c, e in d95['steps']]
            dblock['atk_floor'] = float(d95['atk_floor'])
        if d95.get('trade_terms') is not None:
            dblock['trade_terms'] = d95['trade_terms']
    # No rule fits: give the reader the IV box the members live in, with the
    # count of spreads inside that box that are NOT members -- an envelope
    # sold as a rule would be the one dishonesty this section cannot afford.
    env = None
    if dblock is None:
        meta = ctx['meta']
        lo = meta[m, :3].min(axis=0)
        hi = meta[m, :3].max(axis=0)
        box = np.ones(n, bool)
        for ax in range(3):
            box &= (meta[:, ax] >= lo[ax]) & (meta[:, ax] <= hi[ax])
        env = {'atk': [int(lo[0]), int(hi[0])],
               'def': [int(lo[1]), int(hi[1])],
               'hp': [int(lo[2]), int(hi[2])],
               'n_box': int(box.sum()),
               'n_outside': int((box & ~m).sum())}
    n_modes = 1 + len(ctx['other_modes'])
    wcell = cell_weights(frame['cells'], weights)
    # Denominator for the most-winning member's count: the matchups the
    # preset actually counts (weighted scenarios x opponents). Printed with
    # the count everywhere, so "378 matchups" can never be read against the
    # wrong scale.
    wden = int(round(float(np.sum(weights)) * ctx['n_opp']))
    return {
        'role': role, 'combo': inter['combo'], 'sets': list(inter['sets']),
        'constructed': bool(inter.get('constructed')),
        'size': inter['size'], 'share': round(inter['size'] / n, 5),
        'n_guaranteed': inter['n_g'],
        'n_guaranteed_material': inter['n_g_mat'],
        'n_guaranteed_weighted': int(round(float((g * wcell).sum()))),
        'n_guaranteed_90': inter['n_g90'],
        'guaranteed': rows,
        'guaranteed_by_scenario': by_scen,
        'n_scenarios_covered': len(by_scen),
        'n_guaranteed_distinct_species': len(
            {species_cell(ctx, frame['cells'][r['ci']]) for r in rows}),
        'gives_up': gave_rows,
        'n_gives_up': int(gave.sum()),
        'n_gives_up_material': int((gave & frame['mat']).sum()),
        'most_winning_member': {'iv': iv_str(ctx['meta'], mw),
                                'idx': mw,
                                'sp_rank': int(ctx['sp_rank'][mw]),
                                'wins': int(tot.max()),
                                'wins_all': int(win2[mw].sum()),
                                'denominator': wden},
        'best_sp_members': [{'iv': iv_str(ctx['meta'], int(i)),
                             'idx': int(i),
                             'sp_rank': int(ctx['sp_rank'][i]),
                             'wins': int(wsum[int(i)]),
                             'wins_all': int(win2[i].sum())} for i in best_sp],
        'rank1_in': bool(m[r1]),
        'wins_denominator': wden,
        'wins_per_member': [int(tot.min()), int(np.median(tot)), int(tot.max())],
        'description': dblock,
        'iv_envelope': env,
        'description_shape': ('list' if d95 is None else d95['family']),
        'honesty': {
            'n_guaranteed_all_modes': sum(1 for r in rows
                                          if r['modes_ok'] == n_modes),
            'n_modes': n_modes,
            'median_outside_wr': (round(float(np.median(
                [r['outside_wr'] for r in rows])), 4) if rows else None),
            'n_cells_outside_wr_over_90': sum(1 for r in rows
                                              if r['outside_wr'] > 0.90),
        },
    }


def weighted_wins(ctx, weights):
    """Per-IV weighted matchups won: sum over scenarios of weight x wins.

    The y axis of the section plot and of the scatter's "All (by build
    criteria)" entry. Integer-valued for every shipped preset (all weights
    are 0 or 1), so the axis never prints a fractional matchup.
    """
    per_scen = ctx['win'].sum(axis=2)          # (n_iv, n_sc)
    return per_scen @ np.asarray(weights, dtype=np.float64)


def objectives_block(ctx, builds, weights, wsum=None):
    """The two objectives, plus the grid's own most-winning spread.

    ``win_gap`` is over the PRESET-weighted win count (the section plot's y
    axis and the same number ``most_winning_member`` was picked on);
    ``cell_gap`` is over the preset-weighted guaranteed-cell count (the
    number the ranking used). ``cell_gap_all`` is the same gap over all nine
    scenarios -- the number the builds table prints -- so the sentence can
    quote both with their scopes and a reader subtracting the table's
    columns lands on a number the sentence actually contains.
    """
    if not builds:
        return None
    wins_all = ctx['win2'].sum(axis=1)
    if wsum is None:
        wsum = weighted_wins(ctx, weights)
    r1 = int(np.argmin(ctx['sp_rank']))
    gmw = int(np.argmax(wins_all))
    by_cells = max(builds, key=lambda b: (b['n_guaranteed_weighted'],
                                          b['n_guaranteed_material'],
                                          b['size']))
    by_wins = max(builds, key=lambda b: b['most_winning_member']['wins'])
    return {
        'best_cells_build': by_cells['combo'],
        'best_cells_count': by_cells['n_guaranteed'],
        'best_cells_count_weighted': by_cells['n_guaranteed_weighted'],
        'best_wins_build': by_wins['combo'],
        'best_wins_value': by_wins['most_winning_member']['wins'],
        'best_wins_build_cells_weighted': by_wins['n_guaranteed_weighted'],
        'split': by_cells['combo'] != by_wins['combo'],
        'win_gap': (by_wins['most_winning_member']['wins']
                    - by_cells['most_winning_member']['wins']),
        'win_denominator': int(round(float(np.sum(weights)) * ctx['n_opp'])),
        'best_wins_value_weighted': by_wins['most_winning_member']['wins'],
        'best_cells_wins_weighted': by_cells['most_winning_member']['wins'],
        'cell_gap': (by_cells['n_guaranteed_weighted']
                     - by_wins['n_guaranteed_weighted']),
        'cell_gap_all': (by_cells['n_guaranteed']
                         - by_wins['n_guaranteed']),
        'best_cells_count_all': by_cells['n_guaranteed'],
        'best_wins_build_cells_all': by_wins['n_guaranteed'],
        'rank1_iv': iv_str(ctx['meta'], r1),
        'rank1_idx': r1,
        'rank1_wins': int(wins_all[r1]),
        'rank1_wins_weighted': int(wsum[r1]),
        'rank1_in_any_build': any(b['rank1_in'] for b in builds),
        'global_most_winning': {'iv': iv_str(ctx['meta'], gmw), 'idx': gmw,
                                'sp_rank': int(ctx['sp_rank'][gmw]),
                                'wins': int(wins_all.max())},
        'global_most_winning_in': [b['combo'] for b in builds
                                   if b.get('_holds_gmw')],
    }


def top_tie(L):
    """How the top-ranked region won, when it did not win outright.

    A tie on the weighted guaranteed-cell count is the normal case under a
    narrow preset (nine candidate regions tie at 13 of the 16 1v1 cells on
    Shadow Sableye arm 0), and a page that prints only the winner reads as
    though one region dominated. Returns None on an outright win.

    Counted over the LATTICE's candidate regions, before select_builds
    appends its constructed bulk box: the tie is about what the ranking
    chose between.
    """
    if not L['inters']:
        return None
    top = L['inters'][0]
    tied = [d for d in L['inters'] if d['wg'] == top['wg']]
    if len(tied) < 2:
        return None
    mat_max = max(d['wg_mat'] for d in tied)
    n_at_mat = sum(1 for d in tied if d['wg_mat'] == mat_max)
    return {'n': len(tied), 'weighted': int(round(float(top['wg']))),
            'by': ('material' if (n_at_mat == 1
                                  and top['wg_mat'] == mat_max) else 'size'),
            'size': int(top['size'])}


def standout_block(ctx, frame, builds, kind, idx, weights, wsum):
    """One exceptional single spread, and its relationship to the builds.

    A build is a REGION of at least ``MIN_SET`` spreads that all guarantee
    the same matchups, so the single spread that wins the most matchups --
    and the single spread with the highest average battle score -- can both
    sit outside every build. That is not a defect of the selection and it is
    not a reason to shrink a build; it is what "region" costs. The page says
    so, marks both on the plot, and prints the two numbers a reader needs to
    tell the two plans apart:

    * ``n_own_decision_wins`` -- how many DECISION matchups this one spread
      wins; and
    * ``n_from_nearest`` -- how many of those the nearest build guarantees
      to every one of its members; and
    * ``n_lost_from_nearest`` -- how many matchups that build guarantees
      this spread does NOT win, which is what the hunt costs.

    The difference between the first two is the part the region does not
    guarantee. It is NOT the part nobody else wins -- most of those cells
    are won by a thousand other spreads; what they lack is a region-wide
    guarantee (2026-09-16 round-3 review, which found the page claiming
    exclusivity it had not measured).

    2026-09-17 round 5 item 3 adds the two cell LISTS behind those counts,
    because the counts alone never said WHICH matchups:

    * ``beyond_cells`` -- the cells this spread wins that the nearest build
      does not guarantee, each with ``share``: the fraction of that build's
      own members that win the same cell. Ascending by share, so the cells
      essentially no member wins read first and the ones most members win
      (which are the least interesting) sort to the tail.
    * ``lost_cells`` -- the cells the build guarantees to every member and
      this spread does not win. Descending rarity (ascending grid rate), the
      same order the guarantee lists use.

    Both carry the cell's GRID win rate, which is the honest rate for a
    single spread (a build's "outside rate" is a property of a region).
    """
    cells = frame['cells']
    won = ctx['win2'][idx]
    own = np.array([bool(won[c['k']]) for c in cells], dtype=bool)
    n_own = int(own.sum())
    in_build = next((i for i, b in enumerate(builds)
                     if bool(b['_mask'][idx])), None)
    nearest, n_from, n_lost = None, 0, 0
    if builds:
        if in_build is not None:
            nearest = in_build
            n_from = int((builds[in_build]['_g'] & own).sum())
        else:
            scored = [(int((b['_g'] & own).sum()), -i)
                      for i, b in enumerate(builds)]
            best = max(scored)
            nearest, n_from = -best[1], best[0]
        n_lost = int((builds[nearest]['_g'] & ~own).sum())
    beyond_cells, lost_cells = [], []
    if nearest is not None:
        nb = builds[nearest]
        g, m = nb['_g'], nb['_mask']
        sub = frame['Wd'][m]           # members x decision cells
        for ci, c in enumerate(cells):
            if own[ci] and not g[ci]:
                beyond_cells.append({
                    'cell': c['label'], 'rank': c['rank'] or 0,
                    'grid_wr': float(c['wr']),
                    'share': (float(sub[:, ci].mean()) if sub.shape[0]
                              else 0.0)})
            elif g[ci] and not own[ci]:
                lost_cells.append({'cell': c['label'], 'rank': c['rank'] or 0,
                                   'grid_wr': float(c['wr'])})
        beyond_cells.sort(key=lambda r: (r['share'], r['grid_wr'], r['rank']))
        lost_cells.sort(key=lambda r: (r['grid_wr'], r['rank']))
    # How many OTHER spreads on this grid win every decision matchup this one
    # wins. The standouts note argues that no REGION reproduces this spread's
    # profile; this is the stronger measured fact behind it, and it is the
    # one a careful reader would otherwise doubt (2026-09-17 round 6
    # review). 0 = nothing else on the grid covers what it covers.
    n_peers = (int(frame['Wd'][:, own].all(axis=1).sum()) - 1 if n_own else 0)
    meta = ctx['meta']
    return {
        'kind': kind, 'idx': int(idx), 'iv': iv_str(meta, idx),
        'sp_rank': int(ctx['sp_rank'][idx]),
        'atk': float(ctx['planes']['atk'][idx]),
        'def': float(ctx['planes']['def'][idx]),
        'hp': float(ctx['planes']['hp'][idx]),
        'cp': int(meta[idx, 4]),
        'avg_score': float(ctx['avg_score'][idx]),
        'wins_all': int(ctx['win2'][idx].sum()),
        'wins_weighted': int(wsum[idx]),
        'denominator': int(round(float(np.sum(weights)) * ctx['n_opp'])),
        'denominator_all': int(ctx['n_sc'] * ctx['n_opp']),
        'in_build': in_build,
        'nearest_build': nearest,
        'n_own_decision_wins': n_own,
        'n_from_nearest': n_from,
        'n_lost_from_nearest': n_lost,
        'beyond_cells': beyond_cells,
        'lost_cells': lost_cells,
        'n_profile_peers': n_peers,
    }


def standouts(ctx, frame, builds, weights, wsum):
    """The two spreads the section marks outside the builds, deduplicated.

    Order is fixed -- most wins first, then highest battle score -- so the
    block, the plot legend and the card set name them the same way every
    time. When one spread is both, it is printed once and says so.
    """
    gmw = int(np.argmax(ctx['win2'].sum(axis=1)))
    best = int(ctx['best_score'])
    out = [standout_block(ctx, frame, builds, 'wins', gmw, weights, wsum)]
    if best == gmw:
        out[0]['kind'] = 'both'
    else:
        out.append(standout_block(ctx, frame, builds, 'score', best,
                                  weights, wsum))
    return out


# ---------------------------------------------------------------------------
# NOTABLE SPREADS (round 8 item 2)
# ---------------------------------------------------------------------------
# Through round 7 the page named single spreads in TWO places, on two
# different rankings: the section's Standouts block (the most-winning spread
# and the highest-average-score spread, chosen off the decision grid) and the
# dive's "Top Picks" cards (the top three of a composite of average-score
# rank, matchup flips and rank stability). Neither ranking knew about the
# other, so a reader met "Top Picks" whose three entries all read "in no
# build" beside a section recommending builds, and the page had to print a
# paragraph explaining why its two lists disagreed.
#
# Round 8 item 2 (Michael, 2026-09-17) replaces both with ONE list. Its
# entries are the spreads the page already has a reason to name:
#
#   * the most-winning spread and the highest-average-score spread (the two
#     standouts);
#   * SP1, the stat-product rank-1 spread; and
#   * each build's most-winning member, which moves with the preset.
#
# The composite-score ranking is retired -- it was the one selection rule on
# the page no other surface used.
#
# The entries are then DEDUPLICATED BY PROFILE, because the interesting
# question about two named spreads is whether they win different matchups,
# not whether their IVs differ: two entries sharing at least
# ``NOTABLE_DEDUP_J`` of their decision-cell wins (Jaccard) collapse to one,
# the first in the fixed order above named and the rest listed as variants
# with how many matchups separate them. A list of five spreads that all win
# the same 60 matchups is one offer printed five times.
NOTABLE_DEDUP_J = 0.90

# The fixed order. First wins the naming when two entries merge, so the two
# standouts -- the spreads the plot marks and the cards headline -- lead.
NOTABLE_ROLE_ORDER = ('wins', 'both', 'score', 'sp1', 'build')


def notable_spreads(ctx, frame, builds, standouts_out, weights, wsum):
    """The one list of single spreads the section names, deduplicated.

    Returns one :func:`standout_block` per surviving entry, with two extra
    keys:

    * ``roles`` -- every reason this spread is on the list, as
      ``(kind, build index or None)`` pairs, in the fixed order. One spread
      can hold several (the most-winning spread IS often Build 1's
      most-winning member), and an entry that holds several says so rather
      than appearing once per reason.
    * ``variants`` -- the entries that merged into it, each with ``n_diff``:
      how many decision matchups separate the two win sets (the symmetric
      difference). That is the number a reader needs -- "differs by two
      matchups" is actionable, "Jaccard 0.94" is not.
    """
    Wd = frame['Wd']
    cands = [{'kind': t['kind'], 'build': None, 'idx': int(t['idx'])}
             for t in standouts_out]
    cands.append({'kind': 'sp1', 'build': None,
                  'idx': int(np.argmin(ctx['sp_rank']))})
    for i, b in enumerate(builds):
        cands.append({'kind': 'build', 'build': i,
                      'idx': int(b['most_winning_member']['idx'])})
    # (a) exact dedup: the same SPREAD reached by two reasons is one entry.
    order, by_idx = [], {}
    for c in cands:
        e = by_idx.get(c['idx'])
        if e is None:
            e = {'idx': c['idx'], 'roles': []}
            by_idx[c['idx']] = e
            order.append(e)
        if (c['kind'], c['build']) not in e['roles']:
            e['roles'].append((c['kind'], c['build']))
    # (b) profile dedup: near-identical decision-win sets are one offer.
    kept = []
    for e in order:
        w = Wd[e['idx']] if Wd.shape[1] else np.zeros(0, bool)
        hit = None
        for prev in kept:
            pw = Wd[prev['idx']] if Wd.shape[1] else np.zeros(0, bool)
            union = int((w | pw).sum())
            if union and int((w & pw).sum()) / union >= NOTABLE_DEDUP_J:
                hit = prev
                break
        if hit is None:
            e['variants'] = []
            kept.append(e)
        else:
            hit['variants'].append(
                {'idx': e['idx'], 'iv': iv_str(ctx['meta'], e['idx']),
                 'roles': e['roles'],
                 'sp_rank': int(ctx['sp_rank'][e['idx']]),
                 'n_diff': int((w ^ Wd[hit['idx']]).sum())})
    out = []
    for e in kept:
        blk = standout_block(ctx, frame, builds, e['roles'][0][0], e['idx'],
                             weights, wsum)
        blk['roles'] = e['roles']
        blk['variants'] = e['variants']
        out.append(blk)
    return out


# ---------------------------------------------------------------------------
# FAMILIES (round 8 item 1) -- the region around a standout that no build is
# ---------------------------------------------------------------------------
# A build is an INTERSECTION OF NAMED SETS, so the grid structure the five
# set generators see decides what can be a build at all. A standout -- the
# spread winning the most decision matchups, or the one with the highest
# average battle score -- routinely sits in none of them, and the section
# could say only "it is outside every build" and list what that costs.
#
# There IS a region around such a spread: drop the standout's rarest
# guarantees one at a time until the spreads winning ALL the remaining ones
# number at least MIN_BUILD, and what is left is a describable set of spreads
# that guarantee most of what the standout guarantees. The 2026-09-17 corpus
# run (userdata/analysis/2026-09-17_seeded_lattice/v2/summary.md) measured
# these regions on every arm of the corpus and found they must NOT enter the
# lattice: seeded primaries are tight (median 60 spreads against 128), the
# fork loses cells on 19 of the comparisons and vanishes on 16. Michael's
# call, 2026-09-17: they are shown as FAMILIES around the standouts,
# alongside the builds, and the lattice stays unseeded.
#
# A family is therefore NOT a build. It never enters the lattice, it takes no
# UpSet column, it gets no card, and the builds table labels its row "family
# (not a build)". It is a pure function of (grid, seed spread): the growth
# reads only the seed's own decision-cell wins, so the same seed gives the
# same family under every preset. What the PRESET changes is which standouts
# are outside every build, and so which families are drawn -- which is why
# the cache below is keyed on the seed alone.
FAMILY_MIN = MIN_BUILD


def _family_grow(Wd, own, min_members, order, wr):
    """Greedily drop cells from ``own`` until >= ``min_members`` spreads win all.

    ``order`` is the greedy rule:

    * ``'rate'`` -- drop the cell with the lowest GRID win rate first (the
      rarest guarantee, which is the one fewest spreads can be asked to
      hold);
    * ``'members'`` -- drop the cell whose removal admits the most members.

    Member counting is incremental: with ``cnt`` the number of kept cells each
    spread wins, the members after dropping cell ``c`` are the current members
    plus the spreads missing exactly one kept cell, that one being ``c``. That
    turns the ``'members'`` rule from a quadratic pile of ``all()`` reductions
    into one pass per candidate.
    """
    keep = list(own)
    cnt = Wd[:, keep].sum(axis=1).astype(np.int32)
    while True:
        K = len(keep)
        mem = cnt == K
        n_mem = int(mem.sum())
        if n_mem >= min_members:
            break
        if K <= 1:
            return None
        if order == 'rate':
            drop = min(keep, key=lambda ci: (wr[ci], ci))
        else:
            near = np.nonzero(cnt == K - 1)[0]
            sub = Wd[near] if near.size else None
            best = None
            for ci in keep:
                gain = 0 if sub is None else int((~sub[:, ci]).sum())
                score = (gain, -wr[ci], -ci)
                if best is None or score > best[0]:
                    best = (score, ci)
            drop = best[1]
        cnt -= Wd[:, drop]
        keep.remove(drop)
    g = Wd[mem].all(axis=0)
    return dict(mask=mem, keep=list(keep), order=order, n_mem=n_mem,
                n_g=int(g.sum()))


def family_region(ctx, frame, idx, min_members=FAMILY_MIN, cache=None):
    """The family around one spread, or None.

    Both greedy orders are run and the one ending with more guaranteed cells
    is kept (ties: more members) -- the same two-order search the 2026-09-17
    seeded-lattice prototype used, so the numbers on the page are the corpus
    run's numbers.

    None when the spread wins no decision cell, when no region of
    ``min_members`` can be grown, or when NO RULE FITS the region at 95%
    fidelity. The last is deliberate: every surface that shows a family names
    its rule (the legend key, the table row, the standout's paragraph), and a
    region the page cannot describe is a region a reader cannot aim at. The
    honest output there is silence, not an outline with no sentence.
    """
    if cache is not None and idx in cache:
        return cache[idx]

    def _done(v):
        if cache is not None:
            cache[idx] = v
        return v

    cells = frame['cells']
    Wd = frame['Wd']
    if not cells or not Wd.shape[1]:
        return _done(None)
    wr = np.array([c['wr'] for c in cells], dtype=np.float64)
    own = np.nonzero(Wd[idx])[0]
    if own.size == 0:
        return _done(None)
    cands = [r for r in (_family_grow(Wd, own, min_members, 'rate', wr),
                         _family_grow(Wd, own, min_members, 'members', wr))
             if r is not None]
    if not cands:
        return _done(None)
    cands.sort(key=lambda r: (-r['n_g'], -r['n_mem']))
    r = cands[0]
    mask = r['mask']
    d95 = region_rule(ctx, mask)
    if d95 is None:
        return _done(None)
    # The same description block a BUILD carries, so every surface that
    # prints a rule -- the legend's short form, the table's stepped-out
    # staircase, the paragraph -- renders a family through the build
    # renderers rather than through a second copy of the rule grammar.
    dblock = {'family': d95['family'], 'rule': d95['rule'],
              'jaccard': round(float(d95['jaccard']), 4),
              'n_rule': d95['n_rule'], 'n_extra': d95['n_extra'],
              'n_missing': d95['n_missing']}
    if d95.get('terms') is not None:
        dblock['terms'] = [[ax, op, float(t)] for ax, op, t in d95['terms']]
    if d95.get('steps') is not None:
        dblock['steps'] = [[float(a), float(b), int(c), float(e)]
                           for a, b, c, e in d95['steps']]
        dblock['atk_floor'] = float(d95['atk_floor'])
    if d95.get('trade_terms') is not None:
        dblock['trade_terms'] = d95['trade_terms']
    g = Wd[mask].all(axis=0)
    r1 = int(np.argmin(ctx['sp_rank']))
    return _done({
        'seed_idx': int(idx),
        'rank1_in': bool(mask[r1]),
        'seed_iv': iv_str(ctx['meta'], idx),
        'description': dblock,
        'rule': _desc_text({'description': dblock})[0],
        'rule_family': d95['family'],
        'rule_fidelity': round(float(d95['jaccard']), 4),
        'size': int(mask.sum()),
        'n_guaranteed': int(g.sum()),
        'n_decision_cells': len(cells),
        'n_seed_cells': int(own.size),
        'n_cells_dropped': int(own.size) - len(r['keep']),
        'order': r['order'],
        'orders': {c['order']: [c['n_mem'], c['n_g']] for c in cands},
        '_mask': mask,
        '_g': g,
    })


def families(ctx, frame, standouts_out, cache=None):
    """One family per standout that sits in no build, deduplicated by mask.

    Standouts INSIDE a build get no family: the build is already the region
    around them, and a second outline over the same points would be two names
    for one answer. Each standout gets ``family`` -- the index of its family
    in the returned list, or None.
    """
    out = []
    for t in standouts_out:
        t['family'] = None
        if t['in_build'] is not None:
            continue
        fam = family_region(ctx, frame, t['idx'], cache=cache)
        if fam is None:
            continue
        hit = next((i for i, f in enumerate(out)
                    if np.array_equal(f['_mask'], fam['_mask'])), None)
        if hit is None:
            hit = len(out)
            fam = dict(fam, seed_kind=t['kind'])
            out.append(fam)
        t['family'] = hit
    return out


def run_preset(ctx, sets, frame, preset):
    """Select and describe the builds for one preset."""
    weights = preset_weights(preset, ctx['scen_labels'])
    wsum = weighted_wins(ctx, weights)
    L = arm_lattice(ctx, sets, frame, weights)
    # BEFORE select_builds, which appends the constructed bulk box to
    # L['inters']: the tie is about the lattice's own candidate regions.
    tie = top_tie(L)
    kept, r1_status, fork_info = select_builds(ctx, L)
    gmw = int(np.argmax(ctx['win2'].sum(axis=1)))
    builds = []
    for role, b in kept:
        others = [o for _r, o in kept if o is not b]
        blk = region_block(L, ctx, b, role, others, weights, wsum=wsum)
        blk['_holds_gmw'] = bool(b['mask'][gmw])
        blk['_mask'] = b['mask']
        blk['_g'] = b['g']
        builds.append(blk)
    # The standouts are computed BEFORE the wide region, because the wide
    # region's ranking key reads them: its first clause is how many of the
    # standouts that sit in no build it holds (2026-09-17 round 6b). They
    # depend only on ``builds``, which is already final here; ``in_wide`` is
    # filled in below, once there is a wide region to ask about.
    standouts_out = standouts(ctx, frame, builds, weights, wsum)
    # The nested wide build: computed from the SAME lattice, kept OUT of
    # ``builds`` on purpose. It is not a build a reader picks -- it is the
    # context around Build 1 -- so the objectives, the card set, the standouts'
    # nearest-build search and the UpSet columns all go on seeing two or three
    # builds, and only the surfaces that opt in print it (2026-09-17 round 5,
    # item 4). Never for the fork or the rank-1 build: "wide" is a statement
    # about the PRIMARY's rule.
    wide = None
    prim = next((b for role, b in kept if role == 'primary'), None)
    if prim is not None:
        outside_idx = [t['idx'] for t in standouts_out
                       if t['in_build'] is None]
        w = wide_build(L, prim, ctx, outside_idx)
        if w is not None:
            wide = region_block(L, ctx, w, 'wide', [], weights, wsum=wsum)
            wide['_mask'] = w['mask']
            wide['_g'] = w['g']
            wide['_in_primary'] = int((w['mask'] & prim['mask']).sum())
            wide['_primary_size'] = int(prim['mask'].sum())
            # The named sets the primary has and this region does not, and
            # vice versa: "Build 1 without the Atk >= 150.24 rung" is only
            # sayable when the difference is exactly one dropped set.
            wide['_dropped'] = [s for s in prim['sets'] if s not in w['sets']]
            wide['_added'] = [s for s in w['sets'] if s not in prim['sets']]
            # How many of its spreads no SELECTED build already holds -- the
            # only ones its plot trace can draw, since every build claims its
            # own members first. Zero is a real case (the table row and the
            # paragraph still print), and the paragraph says so rather than
            # leaving a named region with no points and no legend entry
            # (2026-09-17 round 6 review).
            sel = np.zeros_like(w['mask'])
            for _r, b in kept:
                sel |= b['mask']
            wide['_own'] = int((w['mask'] & ~sel).sum())
    for t in standouts_out:
        t['in_wide'] = (None if wide is None
                        else bool(wide['_mask'][t['idx']]))
    # The families, LAST: they are drawn only around standouts that sit in no
    # build, and which standouts those are is what the preset changes. The
    # regions themselves are preset-independent, so the cache on ``ctx``
    # means a family is grown once per arm however many presets show it.
    fam_cache = ctx.setdefault('_family_cache', {})
    fams = families(ctx, frame, standouts_out, cache=fam_cache)
    # The one list of single spreads (round 8 item 2). Computed AFTER the
    # builds, the wide region and the families, because every entry says
    # where it sits relative to all three.
    notable = notable_spreads(ctx, frame, builds, standouts_out, weights,
                              wsum)
    fam_masks = [f['_mask'] for f in fams]
    for t in notable:
        t['in_wide'] = (None if wide is None
                        else bool(wide['_mask'][t['idx']]))
        t['family'] = next((i for i, m in enumerate(fam_masks)
                            if bool(m[t['idx']])), None)
    wcell = cell_weights(frame['cells'], weights)
    counted = wcell > 0
    singles = [d for d in L['inters'] if len(d['combo']) == 1]
    best_single = max(singles, key=lambda d: (d['wg'], d['size'])) if singles else None
    return {
        'preset': preset,
        'weights': [float(x) for x in weights],
        # The denominator the ranking's own count is out of: decision cells
        # in the scenarios this preset weights. The all-nine total is on the
        # result dict as ``n_decision_cells``.
        'n_decision_weighted': int(counted.sum()),
        'n_decision_weighted_material': int((counted & frame['mat']).sum()),
        'top_tie': tie,
        'builds': builds,
        'lattice_sets': [{'key': p['key'], 'name': p['name'],
                          'generator': p['generator'], 'size': p['size'],
                          'n_guaranteed': p['g_dec'],
                          'n_guaranteed_weighted': int(round(p['wg'])),
                          'n_guaranteed_material': p['g_mat']}
                         for p in L['pick']],
        'pairs': L['pairs'],
        'n_incompatible_pairs': sum(1 for p in L['pairs'] if p['incompatible']),
        'best_single_buildable': (None if best_single is None else
                                  {'combo': best_single['combo'],
                                   'size': best_single['size'],
                                   'n_guaranteed': best_single['n_g'],
                                   'n_guaranteed_weighted': int(round(best_single['wg']))}),
        'inters': L['inters'],
        'rank1_status': r1_status,
        'fork_detail': fork_info,
        'objectives': objectives_block(ctx, builds, weights, wsum=wsum),
        'standouts': standouts_out,
        'notable': notable,
        'families': fams,
        'wide': wide,
        'has_fork': any(b['role'] == 'fork' for b in builds),
    }


def compute_builds(state, arm, mode='pvpoke', level='l50', facts=None,
                   clusters_result=None):
    """Every preset's builds for one arm. The module's entry point.

    ``facts`` is ``deep_dive_brief.compute_brief``'s output for the same arm
    (S2 reads the brief's floor / rungs / rectangle); it is recomputed here
    only when the caller has not already got it.
    """
    ctx = build_ctx(state, arm, mode=mode, level=level)
    if facts is None:
        facts = brief.compute_brief(state, arm, None, mode=mode, level=level)
    sets, clusters_result = named_sets(ctx, facts, clusters_result)
    frame = cell_frame(ctx)
    presets = {}
    for key in PRESET_KEYS:
        if not preset_is_live(key, ctx['scen_labels']):
            continue
        presets[key] = run_preset(ctx, sets, frame, key)
    # Do all three presets land on the same regions? On a moveset where they
    # do, a knob that visibly changes nothing reads as broken; the section's
    # lead says so instead. Compared on the MEMBER MASKS, not the combo
    # letters, which are per-preset labels.
    sigs = {tuple((b['role'], b['_mask'].tobytes()) for b in p['builds'])
            for p in presets.values()}
    return dict(ctx=ctx, sets=sets, frame=frame, presets=presets,
                clusters_result=clusters_result,
                presets_identical=(len(presets) > 1 and len(sigs) == 1),
                n_decision_cells=len(frame['cells']),
                n_material_cells=int(frame['mat'].sum()),
                label=ctx['label'], arm=arm)


# ---------------------------------------------------------------------------
# the section's payload
# ---------------------------------------------------------------------------

def pack_mask(flags):
    """Pack a per-spread boolean into base64, LSB-first inside each byte.

    The one packing implementation on the page: ``deep_dive_which_build
    .mask_b64`` is this function under the name its own tests pin, and the
    browser half is ``_wbMask`` / ``_wbBit`` in deep_dive_engine.js.

    512 bytes per 4096-spread mask, ~684 base64 characters -- far smaller
    than the equivalent index list, and the form the section's panel already
    reads. (The v4 brief asked for member INDICES; masks carry exactly the
    same information at about an eighth the bytes, and the expander builds
    its member list from the mask in the browser.)
    """
    import base64
    buf = bytearray((len(flags) + 7) // 8)
    for i, flag in enumerate(flags):
        if flag:
            buf[i >> 3] |= 1 << (i & 7)
    return base64.b64encode(bytes(buf)).decode('ascii')


def _desc_text(build):
    """The build's description for the PLOT LEGEND (short form).

    The legend wraps at 34 characters, so a staircase cannot carry its steps
    or its defense band here -- but it must not carry "Def >= d(HP)" either,
    which is notation nothing on the page defines. It says what the shape is
    and leaves the numbers to the table. A build no rule fits says so rather
    than repeating the size the trace name already prints.
    """
    d = build['description']
    if d is None:
        return 'no two- or three-stat rule fits it', None
    if d.get('steps'):
        head = display_rule(d['rule']).split(' and Def >= d(HP)')[0]
        n = len(d['steps'])
        return f"{head} + a defense staircase ({n} steps)", d
    return display_rule(d['rule']), d


def _region_key(inter):
    """Identity of a region: WHICH SPREADS it holds.

    Not the combo string: the lattice's letters are per-preset labels (set
    "A" under the 1v1 preset is a different set from "A" under the default),
    so keying on the combo would merge two different regions into one payload
    entry and hand the browser the wrong mask.
    """
    return inter['mask'].tobytes()


def set_short_label(name):
    """A reader-facing name for one lattice set: its TARGET, in few words.

    The generator names are audit vocabulary ("S4 frontier (atk >= 148.1 ->
    1v2 Corviknight)"); the UpSet panel's rows sit under reader prose and get
    the page's own words. The full name stays in the hover.

    Short on purpose (2026-09-16 review): these strings are the UpSet panel's
    y tick labels, drawn into a left margin, and the long forms -- "two-stat
    box for 0v1 Empoleon", "Atk 148.10 + defense staircase for 1v2
    Corviknight" -- ran off the left edge of the plot. Each row now names the
    set's TARGET plus the shape word ("0v1 Empoleon box"), and the panel
    wraps the counts onto a second line.
    """
    import re as _re
    m = _re.match(r"S1 (\S+) cluster (\d+)$", name)
    if m:
        scen = 'all scenarios' if m.group(1) == clusters.ALL_SCEN_KEY else m.group(1)
        # The Matchup clusters section names its clusters C0..C(K-1); an
        # off-by-one relabelling here made the UpSet row "matchup cluster 5"
        # point at what that section calls C4 (2026-09-16 review).
        return f"matchup cluster C{int(m.group(2))} ({scen})"
    m = _re.match(r"S2 floor \((\w+) >= ([0-9.]+)\)$", name)
    if m:
        return f"the line ({display_rule(m.group(1) + ' >= ' + m.group(2))})"
    m = _re.match(r"S2 rung \((\w+) >= ([0-9.]+)\)$", name)
    if m:
        return f"rung ({display_rule(m.group(1) + ' >= ' + m.group(2))})"
    # "Box", not "rectangle": the page's own prose calls this build the bulk
    # box, and the section plot's stats view draws it as a rectangle only on
    # the Def/HP axes -- one name for it everywhere (2026-09-16 review).
    if name == 'S2 alternative rectangle':
        return 'the bulk box'
    m = _re.match(r"S3 package \[(.*)\]$", name)
    if m:
        return 'wins ' + m.group(1)
    m = _re.match(r"S4 frontier \(atk >= ([0-9.]+) -> (.*)\)$", name)
    if m:
        return f"{m.group(2)} staircase"
    m = _re.match(r"S5 box -> (.*)$", name)
    if m:
        return f"{m.group(1)} box"
    return name


def stair_atk_head(d):
    """A staircase's attack floor, as the page PRINTS it ("Atk >= 150.24").

    Not ``f"{d['atk_floor']:.2f}"``: ``atk_floor`` is the raw selected value
    (150.245638...), and two-place formatting rounds it UP to 150.25 -- a bar
    0.01 above the cut the build is actually made at, which excludes members
    of the build being described. ``rule`` already carries ``print_thr``'s
    shortest-exact decimal, so the head of the printed rule is the one
    number every surface may quote.
    """
    return display_rule(d['rule']).split(' and Def >= d(HP)')[0]


def build_plane(build):
    """One build's shape on the stats view's Def (x) / HP (y) axes.

    The section plot's own axes are stat-product rank and matchups won, on
    which a rectangle is not a rectangle -- "the bulk box (Def >= 101.40, HP
    >= 125)" was a phrase nothing on the page ever drew (2026-09-16 review).
    The stats view draws each build where it IS a region:

    * ``box``   -- axis-aligned cuts: a rectangle outline, clipped to the
      grid by the panel. Cuts on ATTACK are invisible on these axes, so they
      travel as ``atk_note`` and the caption says so.
    * ``stair`` -- an attack floor plus a defense staircase: the staircase
      polyline (Def needed at each HP), same caveat about the floor.
    * ``line``  -- an attack floor plus a linear trade ``Def + k*HP >= c``:
      the straight boundary that trade names.
    * ``none``  -- no rule fits (or the rule cuts on attack alone), so the
      build is drawn as its member POINTS and nothing else. An outline the
      members do not fill would be the one dishonesty this view cannot
      afford.
    """
    d = build['description']
    if d is None:
        return {'kind': 'none'}
    fam = d['family']
    if fam == 'atk_floor_frontier' and d.get('steps'):
        return {'kind': 'stair',
                'steps': [[float(h), float(dd)] for h, dd, _n, _p in d['steps']],
                'atkNote': stair_atk_head(d)}
    if fam == 'atk_floor_trade' and d.get('trade_terms'):
        t = d['trade_terms']
        # The printed cut, for the same reason as the box branch below.
        head = re.search(r'Atk >= [0-9.]+', display_rule(d['rule']))
        return {'kind': 'line', 'k': float(t['k']), 'c': float(t['c']),
                'atkNote': (head.group(0) if head
                            else f"Atk >= {float(t['atk_floor']):.2f}")}
    terms = d.get('terms')
    if not terms:
        return {'kind': 'none'}
    box = {'def': [None, None], 'hp': [None, None]}
    # The attack cuts as the RULE prints them, in rule order. Not
    # ``f"{float(t):.2f}"``: two-place formatting rounds a 150.245638 cut UP
    # to 150.25, a bar 0.01 above the cut the build is actually made at, so
    # the stats-view legend read "Atk >= 150.24 [Atk >= 150.25, not on these
    # axes]" -- two spellings of one number in one string, one of them
    # excluding real members (2026-09-17 round 5, seen on the wide region of
    # the 1v1 preset). ``stair_atk_head`` makes the same point for the
    # staircase family.
    printed_atk = re.findall(r'Atk (?:>=|<=) [0-9.]+',
                             display_rule(d['rule']))
    atk_bits = []
    for ax, op, t in terms:
        if ax == 'atk':
            atk_bits.append(printed_atk[len(atk_bits)]
                            if len(atk_bits) < len(printed_atk)
                            else f"Atk {op} {float(t):.2f}")
            continue
        slot = 0 if op == '>=' else 1
        box[ax][slot] = float(t)
    if box['def'] == [None, None] and box['hp'] == [None, None]:
        return {'kind': 'none',
                'atkNote': ' and '.join(atk_bits) if atk_bits else None}
    return {'kind': 'box', 'def': box['def'], 'hp': box['hp'],
            'atkNote': (' and '.join(atk_bits) if atk_bits else None)}


def builds_payload(res, moveset_idx, mode='pvpoke', n_col=6, prose=None):
    """The inline JSON the section's client half reads.

    Deliberately SMALL. Every table the section prints -- the builds table,
    the per-scenario guarantee lists, the "gives up" lists, the members
    expanders -- is rendered server-side once per preset by
    ``deep_dive_which_build``, so the payload carries only what the BROWSER
    needs: the plot's and the UpSet panel's numbers, the membership masks the
    scatter and the collection overlay colour by, and the per-preset
    sentences (authored and word-gated in Python, never formatted in JS).

    - ``cells``: one compact ``[scenario index, opponent rank, material]``
      row per decision cell -- the axis the guarantee bits are over.
    - ``regions``: every region any preset draws, identified by the SPREADS
      it holds (not by the per-preset lattice letter), with its guarantee
      bits over ``cells`` and, when a preset selects it, a packed membership
      mask.
    - ``presets``: per preset, its lattice rows, its UpSet columns, its
      builds' facts and its sentences.

    ``prose`` is ``{preset key: {...strings}}`` from the renderer, already
    gated; it is merged in rather than authored here so that every
    reader-facing sentence on the page has passed the brief's word gates.
    """
    ctx = res['ctx']
    frame = res['frame']
    si_of = {lbl: i for i, lbl in enumerate(ctx['scen_labels'])}
    cells = [[si_of[c['scenario']], (c['rank'] or 0),
              1 if c['material'] else 0] for c in frame['cells']]
    regions, region_idx = [], {}

    def add_region(inter, selected):
        key = _region_key(inter)
        if key not in region_idx:
            region_idx[key] = len(regions)
            regions.append({
                'size': int(inter['size']),
                'constructed': bool(inter.get('constructed')),
                'nG': int(inter['n_g']),
                'nGmat': int(inter['n_g_mat']),
                'bits': pack_mask([bool(x) for x in inter['g']]),
                'mask': None})
        ri = region_idx[key]
        if selected and regions[ri]['mask'] is None:
            regions[ri]['mask'] = pack_mask([bool(x) for x in inter['mask']])
        return ri

    fam_rows, fam_idx = [], {}

    def add_family(f):
        key = int(f['seed_idx'])
        if key not in fam_idx:
            fam_idx[key] = len(fam_rows)
            fam_rows.append({
                'iv': f['seed_iv'], 'kind': f['seed_kind'],
                'rule': f['rule'], 'size': f['size'],
                'nG': f['n_guaranteed'], 'nDec': f['n_decision_cells'],
                'seedIdx': key,
                'mask': pack_mask([bool(x) for x in f['_mask']])})
        return fam_idx[key]

    pay_presets = {}
    for key, block in res['presets'].items():
        keys = [p['key'] for p in block['lattice_sets']]
        sel_combos = {b['combo'] for b in block['builds']}
        role_of = {b['combo']: b['role'] for b in block['builds']}
        cols = []
        for b in block['builds']:
            cols.append((next(d for d in block['inters']
                              if d['combo'] == b['combo']), True))
        extra = 0
        # The wide region takes no UpSet column of its own (it is not a
        # build), and it must not come back as an anonymous EXTRA candidate
        # column either: the table directly above the panel names that same
        # region "Build 1 wide" (2026-09-17 round 6 review).
        wide_combo = (block.get('wide') or {}).get('combo')
        for d in block['inters']:
            if extra >= n_col:
                break
            if d['combo'] in sel_combos or d['combo'] == wide_combo:
                continue
            cols.append((d, False))
            extra += 1
        col_rows, col_of = [], {}
        for inter, selected in cols:
            ri = add_region(inter, selected)
            col_of[inter['combo']] = len(col_rows)
            col_rows.append({
                'r': ri, 'combo': inter['combo'],
                'role': role_of.get(inter['combo'], ''),
                'size': int(inter['size']),
                'nG': int(inter['n_g']),
                'nGw': int(round(float(inter['wg']))),
                'nGmat': int(inter['n_g_mat']),
                # Membership over the lattice rows. The constructed bulk box
                # is not an intersection of named sets, so its row is empty
                # by construction and must not be matched letterwise.
                'memb': ('' if inter.get('constructed')
                         else ''.join(k for k in keys if k in inter['combo']))})
        pb = []
        # The wide build travels LAST in this array and carries ``col: null``:
        # _wbBuildOf colours a spread by the FIRST build holding it, so every
        # real build claims its own members before the wide region does, and
        # the UpSet panel gains no column for it (2026-09-17 round 5, item 4).
        # The panel draws its trace first (below Build 1's) by role, not by
        # position.
        for b in ([x for x in block['builds']]
                  + ([block['wide']] if block.get('wide') else [])):
            inter = next((d for d in block['inters']
                          if d['combo'] == b['combo']
                          and d['size'] == b['size']), None)
            if inter is None:                      # pragma: no cover
                continue
            text, d = _desc_text(b)
            pb.append({
                'role': b['role'], 'combo': b['combo'],
                # The wide region never takes an UpSet column, even when the
                # lattice happens to have listed the same region as one of
                # the unselected candidates: the panel colours a column by
                # the build that owns it, and it is not a build.
                'col': (None if b['role'] == 'wide'
                        else col_of.get(b['combo'])),
                'region': add_region(inter, True),
                'size': b['size'], 'desc': text, 'shape': b['description_shape'],
                'fidelity': (None if d is None else d['jaccard']),
                'nG': b['n_guaranteed'], 'nGw': b['n_guaranteed_weighted'],
                'nGmat': b['n_guaranteed_material'],
                'nScen': b['n_scenarios_covered'],
                'nGivesUp': b['n_gives_up'],
                'nNearFree': b['honesty']['n_cells_outside_wr_over_90'],
                'nAllModes': b['honesty']['n_guaranteed_all_modes'],
                'nModes': b['honesty']['n_modes'],
                'plane': build_plane(b),
                'mostWinning': {'iv': b['most_winning_member']['iv'],
                                'idx': b['most_winning_member']['idx'],
                                'wins': b['most_winning_member']['wins'],
                                'winsAll': b['most_winning_member']['wins_all'],
                                'den': b['most_winning_member']['denominator'],
                                'spRank': b['most_winning_member']['sp_rank']},
                'rank1In': b['rank1_in'],
            })
        obj = block['objectives'] or {}
        pay_presets[key] = dict(
            (prose or {}).get(key, {}),
            label=PRESET_LABEL[key], tag=PRESET_TAG[key],
            weights=[int(x) for x in block['weights']],
            # Decision cells IN THE SCENARIOS THIS PRESET COUNTS: the
            # denominator of every ``nGw``, and the number the page's prose
            # leads with under a narrow preset.
            nDecW=block['n_decision_weighted'],
            nDecWMat=block['n_decision_weighted_material'],
            tie=block['top_tie'],
            scens=[ctx['scen_labels'][i]
                   for i, w in enumerate(block['weights']) if w > 0],
            builds=pb, cols=col_rows,
            wide=bool(block.get('wide')),
            # Families are NOT builds: no UpSet column, no card, no lattice
            # row. A preset carries only INDICES into the payload's one
            # family table -- a family is a pure function of (grid, seed), so
            # the three presets show the same regions and shipping a 684-byte
            # membership mask once per preset would have been 2.7 KB of the
            # same bytes three times (the payload's size cap caught exactly
            # that).
            families=[add_family(f) for f in block.get('families') or []],
            standouts=[{'kind': t['kind'], 'iv': t['iv'],
                        'family': t.get('family'),
                        'inBuild': t['in_build'],
                        'inWide': t.get('in_wide'),
                        'nearest': t['nearest_build'],
                        'winsAll': t['wins_all'],
                        'winsW': t['wins_weighted'],
                        'den': t['denominator'],
                        'denAll': t['denominator_all'],
                        'spRank': t['sp_rank'],
                        'avgScore': round(t['avg_score'], 4)}
                       for t in block['standouts']],
            lattice=[{'key': p['key'], 'short': set_short_label(p['name']),
                      'name': p['name'], 'size': p['size'],
                      'nG': p['n_guaranteed'], 'nGw': p['n_guaranteed_weighted'],
                      'nGmat': p['n_guaranteed_material']}
                     for p in block['lattice_sets']],
            rank1Status=block['rank1_status'], hasFork=block['has_fork'],
            objectives=({'split': bool(obj.get('split')),
                         'winGap': int(obj.get('win_gap', 0)),
                         'winDen': int(obj.get('win_denominator', 0)),
                         'cellGap': int(obj.get('cell_gap', 0)),
                         'cellGapAll': int(obj.get('cell_gap_all', 0)),
                         'bestCells': obj.get('best_cells_build'),
                         'bestWins': obj.get('best_wins_build')}
                        if obj else None))
    r1 = int(np.argmin(ctx['sp_rank']))
    wins_all = ctx['win2'].sum(axis=1)
    gmw = int(np.argmax(wins_all))
    bsi = int(ctx['best_score'])
    return {
        'mi': int(moveset_idx), 'mode': mode,
        'presetKeys': [k for k in PRESET_KEYS if k in pay_presets],
        'default': (PRESET_FLAT if PRESET_FLAT in pay_presets
                    else next(iter(pay_presets), None)),
        'scenLabels': list(ctx['scen_labels']),
        'nDecision': len(cells), 'nMaterial': int(frame['mat'].sum()),
        'nOpp': int(ctx['n_opp']),
        'cells': cells, 'regions': regions, 'presets': pay_presets,
        # One row per family, referenced by index from every preset that
        # draws it (see ``add_family``).
        'families': fam_rows,
        'rank1': {'iv': iv_str(ctx['meta'], r1), 'idx': r1,
                  'wins': int(wins_all[r1])},
        'gridBest': {'iv': iv_str(ctx['meta'], gmw), 'idx': gmw,
                     'wins': int(wins_all[gmw]),
                     'spRank': int(ctx['sp_rank'][gmw])},
        # The scatter's default y axis, at its maximum: the spread the main
        # plot puts highest. Carried so the stats view, the standouts block
        # and the card set all mark the SAME spread.
        # ``avgStr`` is the PRINTED form, formatted here. The panel's own
        # test bars wbRenderRoot from formatting a number (a caption that
        # formats a threshold is a second implementation of the page's
        # rounding rules), so the string travels rather than the JS making
        # one.
        'bestScore': {'iv': iv_str(ctx['meta'], bsi), 'idx': bsi,
                      'wins': int(wins_all[bsi]),
                      'avg': round(float(ctx['avg_score'][bsi]), 4),
                      'avgStr': f"{float(ctx['avg_score'][bsi]):.1f}",
                      'spRank': int(ctx['sp_rank'][bsi])},
    }
