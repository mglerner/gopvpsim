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
        steps.append((float(h), d, int(sel.sum())))
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
        'atk_floor': aT, 'steps': [[a, b, c] for a, b, c in steps],
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
    return dict(other_modes=other, state=state, arm=arm, mode=mode, meta=meta,
                scores=scores, win=win, win2=win2, planes=planes, atk=atk,
                dfn=dfn, hp=hp, sp=sp, sp_rank=sp_rank, n_iv=n_iv, n_sc=n_sc,
                n_opp=n_opp, triage=triage, cells=cells, names=names,
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
        out.append({'ci': ci, 'cell': c['label'], 'scenario': c['scenario'],
                    'rank': c['rank'], 'grid_wr': round(float(c['wr']), 4),
                    'outside_wr': round(ow, 4), 'material': c['material'],
                    'modes_ok': modes_ok})
    # Ascending outside rate: the rarest guarantee -- the one the rest of the
    # grid is least likely to hand a reader anyway -- reads first.
    out.sort(key=lambda r: (r['outside_wr'], r['rank']))
    return out


def region_block(L, ctx, inter, role, others, weights):
    """Everything the page prints about one selected build."""
    n = ctx['n_iv']
    frame = L['frame']
    m, g = inter['mask'], inter['g']
    win2 = ctx['win2']
    ids = np.nonzero(m)[0]
    tot = win2[m].sum(axis=1)
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
    descs = describe(m, ctx['planes'], ctx['sc'], n)
    d95 = pick_descriptions(descs)['d95']
    dblock = None
    if d95 is not None:
        dblock = {'family': d95['family'], 'rule': d95['rule'],
                  'jaccard': round(float(d95['jaccard']), 4),
                  'n_rule': d95['n_rule'], 'n_extra': d95['n_extra'],
                  'n_missing': d95['n_missing']}
        if d95.get('steps') is not None:
            dblock['steps'] = [[float(a), float(b), int(c)]
                               for a, b, c in d95['steps']]
            dblock['atk_floor'] = float(d95['atk_floor'])
        if d95.get('trade_terms') is not None:
            dblock['trade_terms'] = d95['trade_terms']
    n_modes = 1 + len(ctx['other_modes'])
    wcell = cell_weights(frame['cells'], weights)
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
                                'wins': int(tot.max())},
        'best_sp_members': [{'iv': iv_str(ctx['meta'], int(i)),
                             'idx': int(i),
                             'sp_rank': int(ctx['sp_rank'][i]),
                             'wins': int(win2[i].sum())} for i in best_sp],
        'rank1_in': bool(m[r1]),
        'wins_per_member': [int(tot.min()), int(np.median(tot)), int(tot.max())],
        'description': dblock,
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


def objectives_block(ctx, builds, weights):
    """The two objectives, plus the grid's own most-winning spread."""
    if not builds:
        return None
    wins_all = ctx['win2'].sum(axis=1)
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
        'cell_gap': (by_cells['n_guaranteed_weighted']
                     - by_wins['n_guaranteed_weighted']),
        'rank1_iv': iv_str(ctx['meta'], r1),
        'rank1_idx': r1,
        'rank1_wins': int(wins_all[r1]),
        'rank1_in_any_build': any(b['rank1_in'] for b in builds),
        'global_most_winning': {'iv': iv_str(ctx['meta'], gmw), 'idx': gmw,
                                'sp_rank': int(ctx['sp_rank'][gmw]),
                                'wins': int(wins_all.max())},
        'global_most_winning_in': [b['combo'] for b in builds
                                   if b.get('_holds_gmw')],
    }


def run_preset(ctx, sets, frame, preset):
    """Select and describe the builds for one preset."""
    weights = preset_weights(preset, ctx['scen_labels'])
    L = arm_lattice(ctx, sets, frame, weights)
    kept, r1_status, fork_info = select_builds(ctx, L)
    gmw = int(np.argmax(ctx['win2'].sum(axis=1)))
    builds = []
    for role, b in kept:
        others = [o for _r, o in kept if o is not b]
        blk = region_block(L, ctx, b, role, others, weights)
        blk['_holds_gmw'] = bool(b['mask'][gmw])
        blk['_mask'] = b['mask']
        builds.append(blk)
    singles = [d for d in L['inters'] if len(d['combo']) == 1]
    best_single = max(singles, key=lambda d: (d['wg'], d['size'])) if singles else None
    return {
        'preset': preset,
        'weights': [float(x) for x in weights],
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
        'objectives': objectives_block(ctx, builds, weights),
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
    return dict(ctx=ctx, sets=sets, frame=frame, presets=presets,
                clusters_result=clusters_result,
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
    """The build's description, or "list of N" when no 95% rule fits it."""
    d = build['description']
    if d is None:
        return f"list of {build['size']} spreads", None
    return d['rule'], d


def _region_key(inter):
    """Identity of a region: WHICH SPREADS it holds.

    Not the combo string: the lattice's letters are per-preset labels (set
    "A" under the 1v1 preset is a different set from "A" under the default),
    so keying on the combo would merge two different regions into one payload
    entry and hand the browser the wrong mask.
    """
    return inter['mask'].tobytes()


def set_short_label(name):
    """A reader-facing name for one lattice set.

    The generator names are audit vocabulary ("S4 frontier (atk >= 148.1 ->
    1v2 Corviknight)"); the UpSet panel's rows sit under reader prose and get
    the page's own words. The full name stays in the hover.
    """
    import re as _re
    m = _re.match(r"S1 (\S+) cluster (\d+)$", name)
    if m:
        scen = 'all scenarios' if m.group(1) == clusters.ALL_SCEN_KEY else m.group(1)
        return f"matchup cluster {int(m.group(2)) + 1} ({scen})"
    m = _re.match(r"S2 floor \((\w+) >= ([0-9.]+)\)$", name)
    if m:
        return f"the line ({m.group(1)} >= {m.group(2)})"
    m = _re.match(r"S2 rung \((\w+) >= ([0-9.]+)\)$", name)
    if m:
        return f"rung ({m.group(1)} >= {m.group(2)})"
    if name == 'S2 alternative rectangle':
        return 'the bulk rectangle'
    m = _re.match(r"S3 package \[(.*)\]$", name)
    if m:
        return 'wins ' + m.group(1)
    m = _re.match(r"S4 frontier \(atk >= ([0-9.]+) -> (.*)\)$", name)
    if m:
        return f"atk {m.group(1)} + defense staircase for {m.group(2)}"
    m = _re.match(r"S5 box -> (.*)$", name)
    if m:
        return f"two-stat box for {m.group(1)}"
    return name


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
        for d in block['inters']:
            if extra >= n_col:
                break
            if d['combo'] in sel_combos:
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
        for b in block['builds']:
            inter = next(d for d in block['inters'] if d['combo'] == b['combo'])
            text, d = _desc_text(b)
            pb.append({
                'role': b['role'], 'combo': b['combo'],
                'col': col_of[b['combo']],
                'region': region_idx[_region_key(inter)],
                'size': b['size'], 'desc': text, 'shape': b['description_shape'],
                'fidelity': (None if d is None else d['jaccard']),
                'nG': b['n_guaranteed'], 'nGw': b['n_guaranteed_weighted'],
                'nGmat': b['n_guaranteed_material'],
                'nScen': b['n_scenarios_covered'],
                'nGivesUp': b['n_gives_up'],
                'nNearFree': b['honesty']['n_cells_outside_wr_over_90'],
                'nAllModes': b['honesty']['n_guaranteed_all_modes'],
                'nModes': b['honesty']['n_modes'],
                'mostWinning': {'iv': b['most_winning_member']['iv'],
                                'idx': b['most_winning_member']['idx'],
                                'wins': b['most_winning_member']['wins'],
                                'spRank': b['most_winning_member']['sp_rank']},
                'rank1In': b['rank1_in'],
            })
        obj = block['objectives'] or {}
        pay_presets[key] = dict(
            (prose or {}).get(key, {}),
            label=PRESET_LABEL[key], tag=PRESET_TAG[key],
            weights=[int(x) for x in block['weights']],
            scens=[ctx['scen_labels'][i]
                   for i, w in enumerate(block['weights']) if w > 0],
            builds=pb, cols=col_rows,
            lattice=[{'key': p['key'], 'short': set_short_label(p['name']),
                      'name': p['name'], 'size': p['size'],
                      'nG': p['n_guaranteed'], 'nGw': p['n_guaranteed_weighted'],
                      'nGmat': p['n_guaranteed_material']}
                     for p in block['lattice_sets']],
            rank1Status=block['rank1_status'], hasFork=block['has_fork'],
            objectives=({'split': bool(obj.get('split')),
                         'winGap': int(obj.get('win_gap', 0)),
                         'cellGap': int(obj.get('cell_gap', 0)),
                         'bestCells': obj.get('best_cells_build'),
                         'bestWins': obj.get('best_wins_build')}
                        if obj else None))
    r1 = int(np.argmin(ctx['sp_rank']))
    wins_all = ctx['win2'].sum(axis=1)
    gmw = int(np.argmax(wins_all))
    return {
        'mi': int(moveset_idx), 'mode': mode,
        'presetKeys': [k for k in PRESET_KEYS if k in pay_presets],
        'default': (PRESET_FLAT if PRESET_FLAT in pay_presets
                    else next(iter(pay_presets), None)),
        'scenLabels': list(ctx['scen_labels']),
        'nDecision': len(cells), 'nMaterial': int(frame['mat'].sum()),
        'nOpp': int(ctx['n_opp']),
        'cells': cells, 'regions': regions, 'presets': pay_presets,
        'rank1': {'iv': iv_str(ctx['meta'], r1), 'idx': r1,
                  'wins': int(wins_all[r1])},
        'gridBest': {'iv': iv_str(ctx['meta'], gmw), 'idx': gmw,
                     'wins': int(wins_all[gmw]),
                     'spRank': int(ctx['sp_rank'][gmw])},
    }
