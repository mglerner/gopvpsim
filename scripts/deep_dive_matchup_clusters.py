"""Matchup-fingerprint clustering for the deep-dive "Dive Analysis" section.

Replaces the retired experimental banding / 1-D gap-cluster block (2026-07).
Methodology: the cluster-methodology re-evaluation report
(reports repo, gopvpsim-cluster-methodology-2026-07-05.html) — an IV's
identity is the set of MARGINAL matchups it wins.  Per shield scenario:

  1. Win matrix W[iv, opp] = score > 500 (strict; 500 = tie = loss).
  2. "Sharp marginal" opponents: IV-population win-rate in [0.02, 0.98],
     ordered by discriminating power (closeness to 50%).
  3. Fingerprint = each IV's binary win vector over the sharp marginals.
  4. Agglomerative clustering (Hamming distance, average linkage) on the
     fingerprints; K chosen by silhouette with a parsimony floor.
  5. Clusters explained by (a) the marginal matchups that flip between
     adjacent clusters, (b) a depth-3 decision tree over (atk, def, hp),
     (c) a per-opponent single-stat threshold ("flips at") table.

Pure numpy — deliberately NO sklearn/scipy.  Clustering operates on the
matrix of UNIQUE win patterns (typically a few hundred distinct patterns
from <= 4096 IVs), where weighted average-linkage and a full-population
silhouette are exact and fast.  Determinism is load-bearing: replay
re-renders must be byte-identical (arc S4 invariant), so every tie-break
below is explicit and there is no RNG anywhere.

Fidelity note (adversarially verified 2026-07-07): Hamming distances on
short fingerprints tie constantly, and under ties this linkage's merge
order legitimately differs from sklearn's/scipy's (which use their own
tie resolution).  Cross-checked on 4 real dives x 3 scenarios: sharp
marginals identical everywhere; at matching K the partitions agree at
ARI 0.76-1.00; on tie-heavy scenarios the dendrogram can differ enough
that a reference partition is unreachable (worst case Sableye-Shadow GL
2v2: shipped K=2 at silhouette 0.42 vs the reference K=3 at 0.44 -- the
shipped partition is a valid average-linkage clustering, its silhouette
is displayed honestly in the section, and its stat-rule agreement was
HIGHER than the reference's there).  Two deliberate improvements over
the offline reference pipeline
(~/coding/reports/gopvpsim-cluster-analysis/cluster_pipeline.py):

  * silhouette is computed exactly over the full population via unique
    patterns + counts, replacing the reference's seed-0 2000-row subsample
    (removes the RNG-stream dependence of the K choice);
  * K selection carries a parsimony floor (min cluster size + smallest-K-
    within-epsilon), the report's own pre-ship caveat for tiny cup pools.

Tree accuracy is IN-SAMPLE (regularized by min_samples_leaf), matching
what the reference code actually computed; do not label it cross-validated.
"""

import html as _html
import json
import os
import re
import sys

import numpy as np

# Single source of truth for the win/tie boundary (strict >; 500 = tie).
# Imported, not re-declared: the boundary drifted three times when copies of
# the literal lived in more than one place. See tests/test_win_boundary.py.
from gopvpsim.battle import WIN_RATING

# Sibling scripts/ modules are imported by bare name (deep_dive_analysis.py
# does the same). Done here too so this module keeps working when a test or
# build_guides.py loads it straight from its path with scripts/ off sys.path.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# One shield-scenario vocabulary for the whole page: the '0v0' family
# (DRY review 2026-08-05 entry 12, register item R11). Imported, not
# re-formed: these labels key this section's payload `scens` map, and the
# JS overlay looks them up in DATA.scenarioLabels -- a divergent form does
# not error, it just renders neutral points.
#
# BEST_RULE_TIP is the other half of the cross-label the same review asked
# for: this section's flip table and the "flips at" boundary bullets print
# two different numbers for one opponent, and the wording that tells them
# apart is defined once, next to its BOUNDARY_RULE_TIP twin.
from deep_dive_rendering import BEST_RULE_TIP, scenario_label  # noqa: E402

# Categorical cluster colors (dark-surface steps of the validated reference
# palette; checked against the dive's hard-coded Plotly surface #16213e with
# the dataviz six-checks validator: lightness band, chroma floor, CVD
# separation, contrast all pass). Identity is never color-alone: the legend,
# table swatches, and hover text all carry the cluster id.
CLUSTER_PALETTE = ["#3987e5", "#199e70", "#c98500",
                   "#008300", "#9085e9", "#e66767"]

# The even-shield scenarios this section clusters. Named once so the
# "not available" prose spells the same three labels the driver iterates,
# and imported (not re-declared) so the guide/owned-breakdown surfaces that
# follow the same XehrFelrose convention cannot drift from it.
from deep_dive_lib.shields import EVEN_SHIELDS as EVEN_SHIELD_PAIRS  # noqa: E402

# K-selection knobs (parsimony floor — see module docstring).
KMIN = 2
KMAX = 6
SIL_EPSILON = 0.03          # smallest K within this of the best silhouette
MIN_CLUSTER_IVS = 40        # anti-speck floor at full 4096-IV dives
SHARP_LO, SHARP_HI = 0.02, 0.98
DEFINING_MIN_DELTA = 0.15
TREE_MAX_DEPTH = 3
TREE_MIN_LEAF = 40
WEAK_SIL = 0.30             # headlines below this say "weak separation"


def cluster_params():
    """Display strings for the knobs above, for prose that quotes them.

    Every reader-facing surface that names one of these numbers renders it
    from HERE: the in-page "How this works" note below, and
    ``guides/matchup-clusters/body.md`` via the ``{{mc:...}}`` tokens
    resolved in ``scripts/build_guides.py``.  Hand-typing the numbers into
    prose is the drift this closes -- a knob change must not leave two
    documents claiming the old value.
    """
    return {
        "sharp_lo_pct": f"{SHARP_LO * 100:g}",
        "sharp_hi_pct": f"{SHARP_HI * 100:g}",
        "sil_epsilon": f"{SIL_EPSILON:g}",
        "weak_sil": f"{WEAK_SIL:.2f}",
        "kmin": str(KMIN),
        "kmax": str(KMAX),
    }


# Form/shadow parentheticals that mark a genuinely distinct opponent and must
# NEVER be folded into a base species. Anything else in a trailing
# parenthetical (Bug Bite, Close Combat+Rage Fist, atk-weighted, ...) is an
# alt-moveset / weighting variant and IS foldable -- but only when stripping
# it yields a name that another opponent in the same pool actually uses.
_FORM_SHADOW_TAGS = frozenset({
    'Shadow', 'Blade', 'Shield', 'Galarian', 'Female', 'Male', 'Super',
    'Alolan', 'Hisuian', 'Origin', 'Altered', 'Incarnate', 'Therian',
    'Standard', 'Zen',
})
_VARIANT_TAG_RE = re.compile(r'^(.*) \(([^()]+)\)$')


def base_opponent(opp, all_opps):
    """Fold trailing alt-moveset/weighting parentheticals off an opponent
    name, but only when the stripped stem is itself a present opponent.

    ``Medicham (atk-weighted)`` -> ``Medicham`` (when plain ``Medicham`` is in
    the pool); ``Aegislash (Blade)`` stays put (form tag); ``Quagsire (Shadow)
    (Aqua Tail+Stone Edge)`` -> ``Quagsire (Shadow)`` (keeps the Shadow form,
    drops the moveset tag).

    Lives here rather than in deep_dive.py because deep_dive.py imports THIS
    module (a backwards import would be circular); deep_dive.py still carries
    an identical private copy that should be retired in favour of this one.
    """
    cur = opp
    while True:
        m = _VARIANT_TAG_RE.match(cur)
        if not m:
            break
        stem, tag = m.group(1), m.group(2)
        if tag in _FORM_SHADOW_TAGS:
            break
        if stem in all_opps:
            cur = stem
            continue
        break
    return cur


# ---------------------------------------------------------------------------
# Win matrix + sharp marginals
# ---------------------------------------------------------------------------

def win_matrix(scores_flat, nIvs, nS, nO, scen_idx):
    """Binary win matrix (nIvs, nO) for one scenario. Win = score > 500."""
    a = np.asarray(scores_flat, dtype=np.int32).reshape(nIvs, nS, nO)
    return (a[:, scen_idx, :] > WIN_RATING)


def sharp_marginals(W, lo=SHARP_LO, hi=SHARP_HI):
    """Opponent indices with win-rate in [lo, hi], most-discriminating first.

    Returns (sharp, wr): sharp sorted by |wr-0.5| ascending, ties broken by
    opponent index (stable sort — deterministic).
    """
    wr = W.mean(axis=0)
    cand = np.where((wr >= lo) & (wr <= hi))[0]
    order = np.argsort(np.abs(wr[cand] - 0.5), kind="stable")
    return cand[order], wr


# ---------------------------------------------------------------------------
# Weighted average-linkage agglomeration on unique fingerprints
# ---------------------------------------------------------------------------

def _hamming(patterns):
    """Pairwise Hamming distance (fraction of differing bits) between rows.

    The distance definition lives in exactly one place on purpose: the
    linkage and the silhouette must score the SAME geometry, or the K choice
    would be measuring a different space than the merges it is judging.
    Returns a fresh (u, u) float array; callers that mutate it in place
    (the Lance-Williams update) must copy first.
    """
    return (patterns[:, None, :] != patterns[None, :, :]).mean(axis=2)


def _small_pop_floor(cap, n):
    """Scale a minimum-size floor down for small populations.

    Both floors in this module (the anti-speck minimum cluster size and the
    tree's minimum leaf) want ``cap`` at a full 4096-IV dive but must not
    lock out tiny floor dives, so they fall back to n/8 with a hard floor
    of 2. One definition, so the two can't drift apart.
    """
    return max(2, min(cap, n // 8))


def _unique_patterns(F):
    """Collapse fingerprint rows to unique patterns.

    Returns (patterns (u, d) uint8, inverse (n,), counts (u,)).
    np.unique sorts patterns lexicographically — deterministic.
    """
    patterns, inverse, counts = np.unique(
        F.astype(np.uint8), axis=0, return_inverse=True, return_counts=True)
    return patterns, inverse.ravel(), counts


def _linkage_labels(patterns, counts, ks, diff=None):
    """Weighted average-linkage (Hamming) labels for each requested K.

    Average linkage over the full duplicated population equals weighted
    average linkage over unique patterns for merge heights, and for
    partitions whenever merge distances are distinct (identical points
    merge at distance zero first, which is the unique-collapse).  Under
    TIED merge distances -- routine for Hamming on short fingerprints --
    the result is one valid average-linkage clustering chosen
    deterministically, which may differ from other implementations'
    equally-valid choices (see the module docstring fidelity note).
    Lance-Williams update for average linkage:
    d(i+j, k) = (n_i d(i,k) + n_j d(j,k)) / (n_i + n_j).

    Tie-break on equal merge distances: first occurrence in the active
    ordering (argmin scan order), i.e. lowest (i, j) up to float64
    accumulation in the Lance-Williams updates.

    ``diff`` is an optional precomputed ``_hamming(patterns)`` matrix (the
    caller shares one with the silhouette); it is never mutated -- the
    Lance-Williams update runs on a copy.

    Returns {k: labels(u,)} with arbitrary (but deterministic) label ids.
    """
    u, d = patterns.shape
    ks = sorted(set(int(k) for k in ks if 2 <= k <= u))
    out = {}
    if u == 1:
        return {1: np.zeros(1, dtype=np.int32)} if 1 in ks else out
    # Pairwise Hamming distances between unique patterns.
    if diff is None:
        diff = _hamming(patterns)
    dist = diff.astype(np.float64)   # copy: the update below is in-place
    np.fill_diagonal(dist, np.inf)
    size = counts.astype(np.float64).copy()
    active = np.ones(u, dtype=bool)
    # cluster id per pattern; merged clusters adopt the lower slot index.
    labels = np.arange(u, dtype=np.int32)
    n_active = u
    if n_active in ks:
        out[n_active] = labels.copy()
    while n_active > 2:
        # find min distance among active pairs; ties -> lowest (i, j)
        sub = np.where(active)[0]
        block = dist[np.ix_(sub, sub)]
        flat = np.argmin(block)          # first occurrence = lowest (i, j)
        i_s, j_s = divmod(flat, block.shape[1])
        i, j = int(sub[i_s]), int(sub[j_s])
        if i > j:
            i, j = j, i
        # Lance-Williams average-linkage update into slot i
        ni, nj = size[i], size[j]
        new_row = (ni * dist[i, :] + nj * dist[j, :]) / (ni + nj)
        dist[i, :] = new_row
        dist[:, i] = new_row
        dist[i, i] = np.inf
        dist[j, :] = np.inf
        dist[:, j] = np.inf
        size[i] = ni + nj
        active[j] = False
        labels[labels == j] = i
        n_active -= 1
        if n_active in ks:
            out[n_active] = labels.copy()
    if 2 in ks and 2 not in out:
        out[2] = labels.copy()
    # normalize label ids to 0..k-1 in first-appearance order (deterministic)
    for k, lab in out.items():
        _, norm = np.unique(lab, return_inverse=True)
        out[k] = norm.astype(np.int32).ravel()
    return out


def _weighted_silhouette(patterns, counts, labels, diff=None):
    """Exact full-population mean silhouette (Hamming), via unique patterns.

    For a point with pattern p in cluster A:
      a(p) = sum_{q in A} c_q d(p,q) / (n_A - 1)   (d(p,p)=0 excludes self)
      b(p) = min_{B != A} sum_{q in B} c_q d(p,q) / n_B
      s(p) = (b - a) / max(a, b); s = 0 when n_A == 1.
    Overall silhouette = count-weighted mean of s over patterns.

    ``diff`` is an optional precomputed ``_hamming(patterns)`` matrix, shared
    with the linkage so both score the same geometry (and so it is built
    once per choose_k instead of once per candidate K).
    """
    k = int(labels.max()) + 1
    if k < 2:
        return 0.0
    if diff is None:
        diff = _hamming(patterns)
    n_total = counts.sum()
    cluster_sizes = np.array(
        [counts[labels == c].sum() for c in range(k)], dtype=np.float64)
    # weighted distance sums from each pattern to each cluster
    # sums[p, c] = sum over patterns q in cluster c of counts[q]*diff[p, q]
    onehot = np.zeros((len(counts), k))
    onehot[np.arange(len(counts)), labels] = counts
    sums = diff @ onehot                     # (u, k)
    s_total = 0.0
    for p in range(len(counts)):
        A = labels[p]
        nA = cluster_sizes[A]
        if nA <= 1:
            continue  # singleton cluster: s = 0
        a = sums[p, A] / (nA - 1)            # own count excluded via d=0 & nA-1
        b = np.inf
        for c in range(k):
            if c == A:
                continue
            b = min(b, sums[p, c] / cluster_sizes[c])
        denom = max(a, b)
        if denom > 0:
            s_total += counts[p] * (b - a) / denom
    return float(s_total / n_total)


def choose_k(F, kmin=KMIN, kmax=KMAX, min_cluster_ivs=None,
             epsilon=SIL_EPSILON):
    """Pick K with a parsimony floor. Returns (k, labels(n,), sil, sil_by_k).

    Candidates k in [kmin, min(kmax, #unique patterns)].  A candidate is
    dropped when its smallest cluster holds fewer than min_cluster_ivs IVs
    (anti-speck floor; scaled down for small-nIvs floor dives).  Among the
    survivors, take the SMALLEST k whose silhouette is within epsilon of the
    best (parsimony).  Returns (None, None, None, sil_by_k) when no candidate
    passes — the honest "no robust cluster structure" outcome.
    """
    n = F.shape[0]
    if min_cluster_ivs is None:
        min_cluster_ivs = _small_pop_floor(MIN_CLUSTER_IVS, n)
    patterns, inverse, counts = _unique_patterns(F)
    u = len(counts)
    if u < 2:
        return None, None, None, {}
    ks = list(range(kmin, min(kmax, u) + 1))
    diff = _hamming(patterns)        # one geometry for linkage + silhouette
    lab_by_k = _linkage_labels(patterns, counts, ks, diff)
    sil_by_k = {}
    ok = []
    for k in ks:
        if k not in lab_by_k:
            continue
        lab = lab_by_k[k]
        sizes = np.array([counts[lab == c].sum() for c in range(k)])
        if sizes.min() < min_cluster_ivs:
            continue
        sil_by_k[k] = _weighted_silhouette(patterns, counts, lab, diff)
        ok.append(k)
    if not ok:
        return None, None, None, sil_by_k
    best_sil = max(sil_by_k[k] for k in ok)
    for k in ok:                      # ascending — smallest k within epsilon
        if sil_by_k[k] >= best_sil - epsilon:
            return k, lab_by_k[k][inverse], sil_by_k[k], sil_by_k
    raise AssertionError("unreachable")


# ---------------------------------------------------------------------------
# Scenario-level clustering
# ---------------------------------------------------------------------------

def cluster_scenario(W, sharp, atk, def_, hp, sp_rank):
    """Cluster one scenario's fingerprints. Returns res dict or None.

    Clusters are relabeled weak -> strong by mean marginal wins (ties by
    original label id — deterministic).
    """
    if len(sharp) < 2:
        return None
    F = W[:, sharp].astype(np.uint8)
    k, labels, sil, sil_by_k = choose_k(F)
    if k is None:
        return None
    strength = np.array([F[labels == c].sum(axis=1).mean() for c in range(k)])
    order = np.argsort(strength, kind="stable")
    remap = np.empty(k, dtype=np.int32)
    remap[order] = np.arange(k, dtype=np.int32)
    labels = remap[labels]
    clusters = []
    for c in range(k):
        m = labels == c
        clusters.append({
            "id": c,
            "size": int(m.sum()),
            "atk": (float(atk[m].min()), float(atk[m].mean()), float(atk[m].max())),
            "def": (float(def_[m].min()), float(def_[m].mean()), float(def_[m].max())),
            "hp": (float(hp[m].min()), float(hp[m].mean()), float(hp[m].max())),
            "sp_rank": (int(sp_rank[m].min()), int(sp_rank[m].max())),
            "mean_marginal_wins": float(F[m].sum(axis=1).mean()),
            "winrate_per_sharp": W[m][:, sharp].mean(axis=0),
        })
    return {
        "k": k,
        "labels": labels,
        "sharp": sharp,
        "silhouette": sil,
        "clusters": clusters,
        "n_patterns": int(len(np.unique(F, axis=0))),
    }


def defining_matchups(res, opponent_names, top=4, min_delta=DEFINING_MIN_DELTA):
    """Marginal matchups gained AND lost between adjacent (weak -> strong)
    clusters. Win-sets can cross rather than nest, so naming only the gains
    would misread the ordering as strict upgrades."""
    sharp = res["sharp"]
    clusters = res["clusters"]
    out = []
    for i in range(1, len(clusters)):
        prev = clusters[i - 1]["winrate_per_sharp"]
        cur = clusters[i]["winrate_per_sharp"]
        delta = cur - prev
        gained_idx = np.argsort(-delta, kind="stable")[:top]
        gained = [(opponent_names[sharp[g]], float(delta[g]),
                   float(cur[g]), float(prev[g]))
                  for g in gained_idx if delta[g] > min_delta]
        lost_idx = np.argsort(delta, kind="stable")[:top]
        lost = [(opponent_names[sharp[g]], float(delta[g]),
                 float(cur[g]), float(prev[g]))
                for g in lost_idx if delta[g] < -min_delta]
        out.append({"from": i - 1, "to": i, "gained": gained, "lost": lost})
    return out


# ---------------------------------------------------------------------------
# Depth-3 Gini decision tree over (atk, def, hp)  [in-sample accuracy]
# ---------------------------------------------------------------------------

def _gini(label_counts):
    n = label_counts.sum()
    if n == 0:
        return 0.0
    p = label_counts / n
    return 1.0 - float((p * p).sum())


def _best_split(X, y, n_classes, min_leaf):
    """Best (feature, threshold) by weighted Gini. Deterministic tie-breaks:
    lowest feature index, then lowest threshold. Split rule: x < thr -> left.
    Thresholds are midpoints between adjacent distinct sorted values."""
    n = len(y)
    best = None  # (impurity, feat, thr)
    for f in range(X.shape[1]):
        order = np.argsort(X[:, f], kind="stable")
        xs, ys = X[order, f], y[order]
        left = np.zeros(n_classes)
        right = np.bincount(ys, minlength=n_classes).astype(np.float64)
        for i in range(n - 1):
            left[ys[i]] += 1
            right[ys[i]] -= 1
            if xs[i + 1] == xs[i]:
                continue
            nl, nr = i + 1, n - i - 1
            if nl < min_leaf or nr < min_leaf:
                continue
            imp = (nl * _gini(left) + nr * _gini(right)) / n
            thr = (xs[i] + xs[i + 1]) / 2.0
            if best is None or imp < best[0] - 1e-12:
                best = (imp, f, thr)
    return best


def _build_tree(X, y, n_classes, depth, max_depth, min_leaf):
    counts = np.bincount(y, minlength=n_classes)
    node = {"n": int(len(y)), "counts": counts,
            "pred": int(np.argmax(counts))}   # argmax ties -> lowest label
    if depth >= max_depth or len(np.unique(y)) < 2 or len(y) < 2 * min_leaf:
        return node
    split = _best_split(X, y, n_classes, min_leaf)
    if split is None or split[0] >= _gini(counts.astype(np.float64)) - 1e-12:
        return node
    _, f, thr = split
    mask = X[:, f] < thr
    node["feat"] = int(f)
    node["thr"] = float(thr)
    node["left"] = _build_tree(X[mask], y[mask], n_classes,
                               depth + 1, max_depth, min_leaf)
    node["right"] = _build_tree(X[~mask], y[~mask], n_classes,
                                depth + 1, max_depth, min_leaf)
    return node


def _tree_predict(node, X):
    out = np.empty(len(X), dtype=np.int64)
    idx = np.arange(len(X))
    stack = [(node, idx)]
    while stack:
        nd, ii = stack.pop()
        if "feat" not in nd:
            out[ii] = nd["pred"]
            continue
        mask = X[ii, nd["feat"]] < nd["thr"]
        stack.append((nd["left"], ii[mask]))
        stack.append((nd["right"], ii[~mask]))
    return out


def _tree_rules(node, feature_names, fmt="{:.2f}"):
    """Flatten to indented rule lines (ASCII only)."""
    lines = []

    def walk(nd, depth):
        pad = "  " * depth
        if "feat" not in nd:
            lines.append(f"{pad}-> cluster C{nd['pred']} (n={nd['n']})")
            return
        name = feature_names[nd["feat"]]
        thr = fmt.format(nd["thr"])
        lines.append(f"{pad}{name} < {thr}:")
        walk(nd["left"], depth + 1)
        lines.append(f"{pad}{name} >= {thr}:")
        walk(nd["right"], depth + 1)

    walk(node, 0)
    return lines


def stat_rules(res, atk, def_, hp, max_depth=TREE_MAX_DEPTH,
               min_leaf=TREE_MIN_LEAF):
    """Depth-3 Gini tree cluster-labels ~ (atk, def, hp).

    Returns (in_sample_acc, rule_lines).  min_leaf is scaled down for small
    populations the same way the cluster floor is.
    """
    y = res["labels"].astype(np.int64)
    X = np.column_stack([atk, def_, hp]).astype(np.float64)
    min_leaf = _small_pop_floor(min_leaf, len(y))
    tree = _build_tree(X, y, int(y.max()) + 1, 0, max_depth, min_leaf)
    acc = float((_tree_predict(tree, X) == y).mean())
    return acc, _tree_rules(tree, ["atk", "def", "hp"])


# ---------------------------------------------------------------------------
# Single-stat flip thresholds (the "flips at" / unnamed-breakpoints table)
# ---------------------------------------------------------------------------

def single_stat_flip(stats, y):
    """Best single-stat threshold rule for one matchup's win column.

    stats: dict name -> array (insertion order is the tie-break order).
    y: bool/0-1 win vector.  Scans BOTH directions ('win iff stat >= t' and
    'win iff stat < t'), evaluating thresholds only at boundaries between
    distinct sorted values (stable sort).  Returns (acc, stat, threshold,
    direction) with direction in {'>=', '<'}; threshold is the attained
    stat value at the boundary.  Deterministic tie-breaks: higher acc wins;
    ties -> earlier stat in insertion order, then lower threshold (the
    boundary scan is outside the direction loop), then '>=' before '<' at
    the same boundary.  NB the k=0 boundary yields the CONSTANT rules
    (always-win for '>=', always-lose for '<') at the base rate -- callers
    presenting the result must check it beats max(p, 1-p) (see flip_table's
    'informative' flag).
    """
    y = np.asarray(y, dtype=np.int64)
    n = len(y)
    tot = y.sum()
    best = None  # (acc, stat, thr, dir)
    for sname, x in stats.items():
        order = np.argsort(x, kind="stable")
        xs, ys = np.asarray(x)[order], y[order]
        cum = np.cumsum(ys)
        for k in range(n):
            if k > 0 and xs[k] == xs[k - 1]:
                continue  # not a distinct-value boundary
            lp = cum[k - 1] if k > 0 else 0   # wins strictly below boundary
            rp = tot - lp                      # wins at/above boundary
            acc_ge = ((k - lp) + rp) / n       # rule: win iff x >= xs[k]
            acc_lt = (lp + (n - k) - rp) / n   # rule: win iff x < xs[k]
            for acc, dirn in ((acc_ge, ">="), (acc_lt, "<")):
                if best is None or acc > best[0] + 1e-12:
                    best = (float(acc), sname, float(xs[k]), dirn)
    return best


def flip_table(W, sharp, wr, stats, is_named):
    """Rows for the unnamed-breakpoints table, one per sharp marginal.

    is_named: callable(opp_idx, stat_name) -> bool | None
      True  -> an authored anchor names this opponent (+stat family)
      False -> no anchor names it (render 'UNNAMED')
      None  -> no authored anchors exist at all (render neutrally)
    Rows come out in sharp order (most-discriminating first).
    """
    rows = []
    for o in sharp:
        acc, sname, thr, dirn = single_stat_flip(stats, W[:, o])
        baseline = max(float(wr[o]), 1.0 - float(wr[o]))
        rows.append({
            "opp_idx": int(o),
            "winrate": float(wr[o]),
            "stat": sname,
            "threshold": thr,
            "direction": dirn,
            "accuracy": acc,
            # A constant rule (always-win / always-lose) scores the base
            # rate; only a rule that BEATS it carries information. Rows
            # failing this are rendered without a threshold claim.
            "informative": acc > baseline + 1e-9,
            "named": is_named(int(o), sname),
        })
    return rows


# ---------------------------------------------------------------------------
# Top-level per-scenario driver
# ---------------------------------------------------------------------------

def compute_matchup_clusters(scores_flat, nIvs, nS, nO, scenarios,
                             atk, def_, hp, is_named,
                             scen_pairs=EVEN_SHIELD_PAIRS):
    """Run the full pipeline for the even-shield scenarios present.

    scenarios: list of (my_shields, opp_shields) tuples in grid order.
    atk/def_/hp: per-IV battle stats (shadow-effective).  is_named: see
    flip_table.  Returns {scen_label: result} where result has keys
    res/defining/tree_acc/tree_rules/flips or {'reason': ...} when the
    scenario has no robust structure.  Scenario labels are '0v0' style.
    """
    atk = np.asarray(atk, dtype=np.float64)
    def_ = np.asarray(def_, dtype=np.float64)
    hp = np.asarray(hp, dtype=np.float64)
    sp = atk * def_ * hp
    order = np.argsort(-sp, kind="stable")
    sp_rank = np.empty(nIvs, dtype=np.int32)
    sp_rank[order] = np.arange(1, nIvs + 1)
    stats = {"atk": atk, "def": def_, "hp": hp, "sp": sp}

    out = {}
    scen_list = [tuple(s) for s in scenarios]
    for pair in scen_pairs:
        if pair not in scen_list:
            continue
        si = scen_list.index(pair)
        label = scenario_label(pair)
        W = win_matrix(scores_flat, nIvs, nS, nO, si)
        sharp, wr = sharp_marginals(W)
        if len(sharp) < 2:
            out[label] = {"reason": "fewer than 2 marginal matchups",
                          "n_sharp": int(len(sharp))}
            continue
        res = cluster_scenario(W, sharp, atk, def_, hp, sp_rank)
        if res is None:
            out[label] = {"reason": "no robust cluster structure "
                                    "(all candidate splits fail the "
                                    "minimum-cluster-size floor)",
                          "n_sharp": int(len(sharp))}
            continue
        tree_acc, tree_lines = stat_rules(res, atk, def_, hp)
        out[label] = {
            "res": res,
            "defining": None,   # filled by renderer with display names
            "tree_acc": tree_acc,
            "tree_rules": tree_lines,
            "flips": flip_table(W, sharp, wr, stats, is_named),
            "wr": wr,
        }
    return out


# ---------------------------------------------------------------------------
# HTML section renderer ("Matchup clusters", first block in Dive Analysis)
# ---------------------------------------------------------------------------
# Emits server-side tables (cluster summary, win-rate grid, stat rules, flip
# thresholds) plus three EMPTY panel divs (atk/def, atk/hp, def/hp) and one
# inline <script type="application/json"> payload. The panels are drawn
# client-side by initMatchupClusters() in deep_dive_engine.js from the
# payload's per-IV cluster labels + the stat arrays already embedded in DATA
# (ivAtk/ivDef/ivHp) -- so the section adds only ~10-60 KB to a ~25 MB page.
# The inline-JSON-in-section pattern (rather than a DATA key) is deliberate:
# the best-buddy L51 pass renders this section into an inert <template>, and
# carrying the payload inside the section keeps the L50/L51 variants
# self-contained across the innerHTML swap.

def _esc(s):
    return _html.escape(str(s), quote=True)


def _fmt_thr(stat, value):
    """Threshold formatting: hp is integral, sp is huge, atk/def are 2dp."""
    if stat == "hp":
        return f"{value:.0f}"
    if stat == "sp":
        return f"{value:,.0f}"
    return f"{value:.2f}"


# Alpha-ramp bounds for the win-rate tint, shared with the matchup-web
# heatmap (build_matchup_web.py cellStyle uses the same 12%..67% ramp over
# the same tokens). Keep the two in step: the --matrix-*-fg text values are
# AA-solved against their own -bg fill ACROSS THIS RAMP, so widening it is
# a palette-governance change, not a cosmetic one.
WR_RAMP_MIN_PCT = 12
WR_RAMP_MAX_PCT = 67


def _wr_cell(wr):
    """Win-rate table cell with a diverging win/loss tint.

    Uses the matchup-web heatmap lane wholesale: the fill-role tokens
    (--matrix-win-bg / --matrix-loss-bg) alpha-ramped with |wr - 0.5| via
    color-mix, ALWAYS paired with that token's text color
    (--matrix-*-fg); an exact 50% gets the flat, un-ramped tie pair.
    This replaces a pair of hard-coded rgba triples (the categorical
    CLUSTER_PALETTE's blue and red), which were dark-theme values baked
    into a light-default site and which overloaded the cluster-identity
    palette with outcome meaning.

    The fill/text pairing is not optional. docs/palette_governance.md
    section 3 classifies --win/--loss as outcome TEXT tokens, solved
    against the page bg and the --cell-*-bg tints -- NOT as fills. Using
    them as a saturated fill under the inherited var(--text) drops the
    printed percentage to 3.5:1 (--loss) / 4.1:1 (--win) over --surface
    in gruvbox-light, the default theme, i.e. below the AA floor at the
    common 0%/100% endpoint. The --matrix-* pairs clear 4.5:1 at both
    ramp endpoints in all four themes; test_winrate_tint_* pins that.

    The number is always printed, so nothing rides on color alone.
    """
    if wr == 0.5:
        style = "background:var(--matrix-tie-bg);color:var(--matrix-tie-fg)"
    else:
        side = "win" if wr > 0.5 else "loss"
        t = min(abs(wr - 0.5) * 2.0, 1.0)
        pct = round(WR_RAMP_MIN_PCT + (WR_RAMP_MAX_PCT - WR_RAMP_MIN_PCT) * t)
        style = (f'background:color-mix(in srgb,var(--matrix-{side}-bg) '
                 f'{pct}%, transparent);color:var(--matrix-{side}-fg)')
    return f'<td style="text-align:right;{style}">{wr * 100:.0f}%</td>'


def _swatch(c):
    return (f'<span style="display:inline-block;width:10px;height:10px;'
            f'border-radius:2px;background:{CLUSTER_PALETTE[c]};'
            f'margin-right:4px"></span>')


def _scen_headline(label, entry, nO):
    if "reason" in entry:
        return (f'<p style="font-size:13px;color:var(--text-muted)">'
                f'<b>{label}</b>: no cluster view -- {_esc(entry["reason"])} '
                f'({entry["n_sharp"]} sharp marginal opponents of {nO}).</p>')
    res = entry["res"]
    wr = entry["wr"]
    n_win = int((wr == 1.0).sum())
    n_loss = int((wr == 0.0).sum())
    sil = res["silhouette"]
    sil_txt = f'silhouette {sil:.2f}'
    if sil < WEAK_SIL:
        sil_txt += ' - weak separation'
    return (f'<p style="font-size:13px">'
            f'<b>{label}</b>: {len(res["sharp"])} sharp marginal opponents '
            f'of {nO} ({n_win} always-win / {n_loss} always-lose at every '
            f'IV); {res["n_patterns"]} distinct win patterns; '
            f'K={res["k"]} clusters ({sil_txt}).</p>')


def _cluster_table(entry, opp_names):
    res = entry["res"]
    rows = []
    defining = defining_matchups(res, opp_names)
    steps_by_to = {d["to"]: d for d in defining}
    for c in res["clusters"]:
        cid = c["id"]
        step = steps_by_to.get(cid, {})
        gtxt = ", ".join(f"{_esc(n)} (+{d * 100:.0f}pp)"
                         for n, d, cur, prev in step.get("gained", [])) or "-"
        lost = step.get("lost", [])
        if lost:
            gtxt += ('; trades away ' +
                     ", ".join(f"{_esc(n)} ({d * 100:.0f}pp)"
                               for n, d, cur, prev in lost))
        rows.append(
            f'<tr><td>{_swatch(cid)}C{cid}</td>'
            f'<td style="text-align:right">{c["size"]}</td>'
            f'<td style="text-align:right">{c["atk"][1]:.1f}</td>'
            f'<td style="text-align:right">{c["def"][1]:.1f}</td>'
            f'<td style="text-align:right">{c["hp"][1]:.0f}</td>'
            f'<td style="text-align:right">#{c["sp_rank"][0]}-'
            f'#{c["sp_rank"][1]}</td>'
            f'<td style="text-align:right">{c["mean_marginal_wins"]:.1f}</td>'
            f'<td>{gtxt}</td></tr>')
    return (
        '<table class="dd-table dd-narrow"><thead><tr>'
        '<th>Cluster</th><th>IVs</th><th>atk (mean)</th><th>def (mean)</th>'
        '<th>hp (mean)</th><th>SP rank</th><th>marginal wins (mean)</th>'
        '<th>gains vs previous cluster</th>'
        '</tr></thead><tbody>' + "".join(rows) + "</tbody></table>")


def _winrate_grid(entry, opp_names):
    res = entry["res"]
    sharp = res["sharp"]
    k = res["k"]
    head = "".join(f"<th>{_swatch(c)}C{c}</th>" for c in range(k))
    rows = []
    for j, o in enumerate(sharp):
        cells = "".join(
            _wr_cell(float(res["clusters"][c]["winrate_per_sharp"][j]))
            for c in range(k))
        rows.append(f"<tr><td>{_esc(opp_names[o])}</td>{cells}</tr>")
    return (
        '<details style="margin:6px 0"><summary style="cursor:pointer;'
        'font-size:13px">Per-cluster win rates vs each marginal opponent'
        '</summary>'
        '<table class="dd-table dd-narrow"><thead>'
        f'<tr><th>Marginal opponent</th>{head}</tr></thead><tbody>'
        + "".join(rows) +
        '</tbody></table>'
        '<p style="font-size:12px;color:var(--text-muted)">Green tint = the '
        'cluster mostly wins that matchup, red tint = mostly loses; the '
        'percentage is the share of the cluster\'s IVs that win.</p>'
        '</details>')


def _rules_block(entry):
    lines = "\n".join(_esc(ln) for ln in entry["tree_rules"])
    return (
        '<details style="margin:6px 0"><summary style="cursor:pointer;'
        'font-size:13px">Stat rules that reproduce the clusters '
        f'(in-sample accuracy {entry["tree_acc"] * 100:.1f}%)</summary>'
        f'<pre style="font-size:12px;line-height:1.5">{lines}</pre>'
        '<p style="font-size:12px;color:var(--text-muted)">Depth-3 decision '
        'tree over (atk, def, hp). Accuracy is in-sample (regularized by a '
        'minimum leaf size), not cross-validated -- read it as "how well '
        'the clusters reduce to stat regions", not a prediction claim.</p>'
        '</details>')


def _flip_table_html(entry, opp_names, has_anchors):
    rows = []
    for r in entry["flips"]:
        if r.get("informative", True):
            rule = _esc(f'wins iff {r["stat"]} {r["direction"]} '
                        f'{_fmt_thr(r["stat"], r["threshold"])}')
            acc_cell = f'{r["accuracy"] * 100:.0f}%'
        else:
            rule = ('<span style="color:var(--text-muted)">no single-stat '
                    'rule beats the base rate</span>')
            acc_cell = '-'
        if r["named"] is True:
            named = '<td style="color:var(--text-muted)">named</td>'
        elif r["named"] is False:
            named = '<td><b>UNNAMED</b></td>'
        else:
            named = '<td style="color:var(--text-muted)">-</td>'
        rows.append(
            f'<tr><td>{_esc(opp_names[r["opp_idx"]])}</td>'
            f'<td style="text-align:right">{r["winrate"] * 100:.0f}%</td>'
            f'<td>{rule}</td>'
            f'<td style="text-align:right">{acc_cell}</td>'
            f'{named}</tr>')
    foot = ('Rows are ordered by discriminating power (win rate closest to '
            '50%). "Rule accuracy" is how well that single stat threshold '
            'predicts the win/loss across all IVs, and is only shown when '
            'it beats always-predicting the majority outcome; '
            'high-accuracy UNNAMED rows are candidate new anchors. '
            '"Named" means an authored anchor names that opponent '
            '(alt-moveset / IV-variant rows inherit their base opponent\'s '
            'anchor).')
    if not has_anchors:
        foot += (' This dive has no authored anchors, so no row can be '
                 'marked named.')
    return (
        # Summary text is quoted by name in guides/matchup-clusters/body.md;
        # the cross-label lives in the note + column header below so the
        # guide's section list stays accurate.
        '<details style="margin:6px 0"><summary style="cursor:pointer;'
        'font-size:13px">Matchup flip thresholds (candidate anchors)'
        '</summary>'
        '<p style="font-size:12px;color:var(--text-muted)">'
        f'{_esc(BEST_RULE_TIP)}</p>'
        '<table class="dd-table dd-narrow"><thead><tr>'
        '<th>Marginal opponent</th><th>Win rate</th>'
        f'<th title="{_esc(BEST_RULE_TIP)}">Best single-stat rule</th>'
        '<th>Rule accuracy</th><th>Named anchor?</th>'
        '</tr></thead><tbody>' + "".join(rows) + "</tbody></table>"
        f'<p style="font-size:12px;color:var(--text-muted)">{foot}</p>'
        '</details>')


def render_section(scores_flat, nIvs, nS, nO, scenarios, opponents,
                   data_obj, opp_label, moveset_label, resolved_anchors,
                   bait_label='bait-selective'):
    """Render the Matchup clusters section (HTML string).

    Replaces the retired experimental banding/gap-cluster block as the first
    block inside the "Dive Analysis" collapsible. All heavy computation
    happens here at render time from the score grid; the client only draws
    the three stat-plane scatter panels from the embedded labels.
    """
    disp = data_obj.get('opponentsDisplay') or list(opponents)
    anchor_opps = {getattr(a, 'opponent', None)
                   for a in (resolved_anchors or [])} - {None}
    pool_names = set(opponents)

    def is_named(opp_idx, stat):
        if not anchor_opps:
            return None
        name = opponents[opp_idx]
        if name in anchor_opps:
            return True
        # Alt-moveset / IV-variant rows ("Medicham (atk-weighted)",
        # "Forretress (Shadow) (Bug Bite)") count as named when an anchor
        # names their base opponent. base_opponent() strips only foldable
        # tags, and only when the stem is itself in this pool: a form/shadow
        # tag ("Sableye (Shadow)", "Corsola (Galarian)") is a genuinely
        # different opponent and must NOT inherit the base species' anchor,
        # which the old single-level strip here got wrong.
        if base_opponent(name, pool_names) in anchor_opps:
            return True
        return False

    computed = compute_matchup_clusters(
        scores_flat, nIvs, nS, nO, scenarios,
        data_obj['ivAtk'], data_obj['ivDef'], data_obj['ivHp'], is_named)
    if not computed:
        _even = ' / '.join(scenario_label(p) for p in EVEN_SHIELD_PAIRS)
        return ('<div class="dd-section" id="dd-matchup-clusters">'
                '<!-- matchup-clusters:v1 -->'
                '<h2 class="dd-h2">Matchup clusters</h2>'
                '<p style="font-size:13px;color:var(--text-muted)">Not '
                'available: this dive ran without the even-shield scenarios '
                f'({_even}).</p></div>\n')

    scen_labels = list(computed.keys())
    _one_one = scenario_label((1, 1))
    default_scen = _one_one if _one_one in computed else scen_labels[0]
    # prefer a scenario that actually clustered for the default view
    if "res" not in computed[default_scen]:
        for lbl in scen_labels:
            if "res" in computed[lbl]:
                default_scen = lbl
                break

    # ---- client payload: per-IV labels + legend meta per scenario ----
    payload = {"palette": CLUSTER_PALETTE, "default": default_scen,
               "scens": {}}
    for lbl, entry in computed.items():
        if "res" not in entry:
            continue
        res = entry["res"]
        payload["scens"][lbl] = {
            "k": res["k"],
            "labels": [int(x) for x in res["labels"]],
            "sizes": [c["size"] for c in res["clusters"]],
        }

    parts = ['<div class="dd-section dd-mc-root" id="dd-matchup-clusters">',
             '<!-- matchup-clusters:v1 -->',
             '<h2 class="dd-h2">Matchup clusters</h2>']
    parts.append(
        '<p style="font-size:13px">IVs grouped by <b>which marginal '
        'matchups they win</b> (their win/loss fingerprint over the '
        'opponents that some IVs beat and others don\'t), instead of by '
        'average score. Clusters largely correspond to stat-threshold '
        'regions (see each scenario\'s stat-rules accuracy below): '
        'crossing a breakpoint or bulkpoint typically moves an IV to the '
        'next cluster, gaining a named set of matchups and sometimes '
        'trading others away.</p>')
    parts.append(
        f'<p style="font-size:12px;color:var(--text-muted)">Computed at '
        f'bake time for moveset <b>{_esc(moveset_label)}</b> with '
        f'{_esc(opp_label)} opponent IVs and {_esc(bait_label)} shield '
        f'play, over the full opponent pool; this section does not follow '
        f'the scatter\'s moveset / opponent-IV / bait dropdowns or the '
        f'opponent filter.</p>')

    # scenario selector (server-side blocks + client panels both follow it)
    opts = "".join(
        f'<option value="{lbl}"{" selected" if lbl == default_scen else ""}>'
        f'{lbl} shields</option>' for lbl in scen_labels)
    parts.append(
        '<label style="font-size:13px">Shield scenario: '
        '<select class="dd-mc-scen" onchange="if(window.mcSelectScenario)'
        'mcSelectScenario(this)">' + opts + '</select></label>')

    # three stat-plane panels (client-rendered)
    parts.append(
        '<div class="dd-mc-panels" style="display:flex;flex-wrap:wrap;'
        'gap:8px;margin:8px 0">'
        '<div class="dd-mc-panel" data-proj="atk,def" '
        'style="flex:1 1 300px;min-width:280px;height:320px"></div>'
        '<div class="dd-mc-panel" data-proj="atk,hp" '
        'style="flex:1 1 300px;min-width:280px;height:320px"></div>'
        '<div class="dd-mc-panel" data-proj="def,hp" '
        'style="flex:1 1 300px;min-width:280px;height:320px"></div>'
        '</div>')

    # Level-capped ("lattice") note. When this species can't reach the
    # league CP cap, almost every spread pins at the max power-up level, so
    # each battle stat becomes a function of a single IV and the panels
    # collapse onto a 16x16x16 IV lattice -- a sparse grid, not missing data.
    # Fires only when >90% of spreads share the ceiling level (measured
    # separation: Mimikyu UL ~100% vs Registeel UL ~31% and CP-capped GL
    # dives <1%); when it doesn't fire the section is byte-identical to before.
    levels = data_obj.get('ivLv')
    if levels:
        ceiling = max(levels)
        frac = sum(1 for lv in levels if lv == ceiling) / len(levels)
        if frac >= 0.90:
            parts.append(
                '<p style="font-size:12px;color:var(--text-muted)">'
                f'<b>Lattice view:</b> {frac * 100:.0f}% of this dive\'s IV '
                f'spreads sit at the same level (L{ceiling:g}) -- this species '
                'does not reach the league CP cap, so it is pinned at the max '
                'power-up level. At a fixed level each battle stat tracks a '
                'single IV, so attack / defense / HP each take only ~16 values '
                'and the panels look like a sparse grid: each visible point '
                'stacks the spreads that share a stat pair (up to 16, one per '
                'remaining IV). This is expected, not missing data -- the '
                'clustering still runs on the full set of win/loss '
                'fingerprints.</p>')

    # per-scenario server-side blocks
    for lbl, entry in computed.items():
        vis = "block" if lbl == default_scen else "none"
        parts.append(f'<div class="dd-mc-scen-block" data-scen="{lbl}" '
                     f'style="display:{vis}">')
        parts.append(_scen_headline(lbl, entry, nO))
        if "res" in entry:
            parts.append(_cluster_table(entry, disp))
            parts.append(_winrate_grid(entry, disp))
            parts.append(_rules_block(entry))
            parts.append(_flip_table_html(entry, disp, bool(anchor_opps)))
        parts.append('</div>')

    knobs = cluster_params()   # every number quoted below comes from them
    parts.append(
        '<details style="margin:6px 0"><summary style="cursor:pointer;'
        'font-size:13px">How this works</summary>'
        '<p style="font-size:12px;color:var(--text-muted)">'
        'Per shield scenario: an opponent is a <b>sharp marginal</b> when '
        f'between {knobs["sharp_lo_pct"]}% and {knobs["sharp_hi_pct"]}% of '
        'this dive\'s IV spreads beat it (everyone '
        'else is settled and can\'t distinguish IVs). Each IV\'s '
        'fingerprint is its win/loss vector over those opponents; '
        'fingerprints are clustered bottom-up (agglomerative, Hamming '
        'distance, average linkage), with the cluster count chosen by '
        'silhouette under a parsimony floor (a split must keep every '
        'cluster above a minimum size, and the smallest K in '
        f'{knobs["kmin"]}-{knobs["kmax"]} within {knobs["sil_epsilon"]} '
        'of the best silhouette wins). Clusters are ordered weakest to '
        'strongest by mean marginal wins. The scatter panels project the '
        f'same {nIvs:,} IV spreads onto each pair of battle stats; clusters '
        'that overlap completely in score separate cleanly there. Replaces '
        'the retired score-gap cluster heuristic (2026-07), which usually '
        '(~77% of sampled runs) fired on float-level jitter in the '
        'opponent-averaged score, and even when it did catch a real tier '
        'could not name which matchups defined it.</p></details>')

    parts.append('<script type="application/json" class="dd-mc-data">'
                 + json.dumps(payload, separators=(",", ":"))
                 + '</script>')
    parts.append('</div>\n')
    return "\n".join(parts)
