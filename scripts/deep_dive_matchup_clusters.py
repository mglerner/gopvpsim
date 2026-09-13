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

# NB this section no longer restricts itself to the even-shield scenarios
# (deep_dive_lib.shields.EVEN_SHIELDS, the XehrFelrose convention the ML IV
# guide and the owned-collection breakdown still follow). It clusters every
# scenario the dive baked: on several dives the ODD scenarios carry the
# cleanest structure, and the even-only scope was hiding it. The Methods
# "About these metrics (0v0 / 1v1 / 2v2 delta)" block and the slayer `even`
# metric are separate uses of that set and are unaffected.

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

# Degeneracy floor (2026-09-13, scenario-clusters phase A2). A scenario with
# too few sharp marginals, or too few distinct win patterns among them, does
# not have a clustering problem to solve: every K "succeeds" at silhouette
# ~1.0 on a handful of points, which is a measurement artifact and not
# structure. Separation measured across 9 species x 9 scenarios
# (docs/scenario_clusters_plan.md section 1): every fake-perfect result seen
# (Feraligatr UL 0v1 K=6 sil 1.00 on 4 sharp / 7 patterns; Dondozo 0v2 and
# 2v0 sil 1.00 on 2 sharp) sits below this bar and every real result above
# it. Scenarios under the floor are REPORTED with their counts rather than
# hidden -- the absence is informative ("0v2: every spread wins 0-5 of 76")
# -- and are excluded from the concatenated "all scenarios" fingerprint.
DEGEN_MIN_SHARP = 6
DEGEN_MIN_PATTERNS = 8

# The combined entry's key and display text. The key shares the scenario
# keyspace of scenario_label() ('0v0', '1v1', ...) because it keys the SAME
# payload `scens` map the JS overlay looks scenarios up in; 'all' cannot
# collide with an '{a}v{b}' label.
ALL_SCEN_KEY = "all"
ALL_SCEN_DISPLAY = "all scenarios"

# Decimal places the PAGE's stat arrays carry: deep_dive.py builds
# DATA.ivAtk / ivDef as ``round(m[5], 2)``, and this section's tree is fitted
# on those arrays, so its thresholds are midpoints between 2dp values. Named
# here so a consumer quoting this section's split (scripts/deep_dive_brief.py's
# corroboration line, which starts from the full-precision meta) can land on
# the SAME number instead of one 0.01 off it. tests/test_matchup_clusters.py
# pins deep_dive.py against this constant.
SECTION_STAT_DP = 2


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
        "degen_min_sharp": str(DEGEN_MIN_SHARP),
        "degen_min_patterns": str(DEGEN_MIN_PATTERNS),
        "all_scen_display": ALL_SCEN_DISPLAY,
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

    Computed as ``A.B' + B.A'`` over the 0/1 rows (B = 1 - A) rather than by
    broadcasting to a (u, u, d) comparison array. BIT-IDENTICAL, because
    every product is 0 or 1 and every partial sum is an exact integer well
    under 2**53, so the summation order cannot change the result -- and it
    is what makes the "all scenarios" fingerprint affordable: at the 2117
    unique patterns x 113 bits that Shadow Sableye GL produces, the
    broadcast form allocated a 506 MB bool array and then a 4 GB float64
    temporary inside ``.mean``, for 0.5 s of work that this does in 0.02 s
    and 36 MB. Rows must be 0/1 (they are: every caller passes a win
    matrix's uint8 view).
    """
    a = patterns.astype(np.float64)
    b = 1.0 - a
    return (a @ b.T + b @ a.T) / patterns.shape[1]


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
    accumulation in the Lance-Williams updates.  The nearest active pair is
    found through a per-row minimum cache rather than by re-scanning the
    whole matrix each merge, which is what makes the concatenated
    "all scenarios" fingerprint affordable (12.6 s -> 0.12 s at 2117 unique
    patterns).  The cache reproduces the full-matrix scan EXACTLY:

      * the global minimum is the lowest row index attaining it, and within
        that row the lowest column -- which is row-major first occurrence;
      * average linkage cannot push any row's minimum DOWN past its current
        value (the merged distance lies between the two it averages, both of
        which are at or above that row's minimum), so a cached minimum can
        only go stale upward -- except that a merged distance can TIE a row's
        minimum at a lower column index, so rows where the new column is at
        or below their cached minimum are recomputed too, not only the rows
        that pointed at either merged slot.

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
    # Per-row nearest active neighbour. Inactive slots hold +inf in `dist`
    # (the merge below fills their row and column), so they never win.
    rowmin = dist.min(axis=1)
    rowarg = dist.argmin(axis=1)
    n_active = u
    if n_active in ks:
        out[n_active] = labels.copy()
    while n_active > 2:
        # min distance among active pairs; ties -> lowest (i, j)
        i = int(np.argmin(rowmin))       # lowest row attaining the minimum
        j = int(rowarg[i])               # lowest column within that row
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
        # refresh the cache: the merged slot, the retired slot, and every
        # active row whose cached neighbour was either of them or whose
        # minimum the new column now ties or beats (see the docstring).
        rowmin[j] = np.inf
        rowarg[j] = 0
        rowmin[i] = dist[i].min()
        rowarg[i] = dist[i].argmin()
        stale = ((dist[:, i] <= rowmin) | (rowarg == i) | (rowarg == j)) & active
        stale[i] = False
        idx = np.where(stale)[0]
        if idx.size:
            blk = dist[idx]
            rowmin[idx] = blk.min(axis=1)
            rowarg[idx] = blk.argmin(axis=1)
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


# The tree's feature order, named once: the tree stores an integer feature
# index and three surfaces turn it back into a word (the rule block, the
# legend rule text, the mini-grid titles).
TREE_FEATURES = ["atk", "def", "hp"]
TREE_THR_FMT = "{:.2f}"


def cluster_tree(res, atk, def_, hp, max_depth=TREE_MAX_DEPTH,
                 min_leaf=TREE_MIN_LEAF):
    """Fit the depth-3 tree once. Returns (tree, X, y).

    Split out so ``stat_rules`` (accuracy + printed rule block) and
    ``root_rules`` (the depth-1 rule the legend and the mini-grid titles
    carry) cannot fit two different trees and print two different root
    thresholds for one scenario.
    """
    y = res["labels"].astype(np.int64)
    X = np.column_stack([atk, def_, hp]).astype(np.float64)
    min_leaf = _small_pop_floor(min_leaf, len(y))
    tree = _build_tree(X, y, int(y.max()) + 1, 0, max_depth, min_leaf)
    return tree, X, y


def stat_rules(res, atk, def_, hp, max_depth=TREE_MAX_DEPTH,
               min_leaf=TREE_MIN_LEAF):
    """Depth-3 Gini tree cluster-labels ~ (atk, def, hp).

    Returns (in_sample_acc, rule_lines).  min_leaf is scaled down for small
    populations the same way the cluster floor is.
    """
    tree, X, y = cluster_tree(res, atk, def_, hp, max_depth, min_leaf)
    acc = float((_tree_predict(tree, X) == y).mean())
    return acc, _tree_rules(tree, TREE_FEATURES, TREE_THR_FMT)


def root_rules(res, atk, def_, hp, max_depth=TREE_MAX_DEPTH,
               min_leaf=TREE_MIN_LEAF):
    """The depth-1 split, as headline text and as per-cluster rule text.

    Returns ``(root_text, per_cluster)``:

      * ``root_text`` is the root split written the way the rule block
        writes it (``'atk < 148.06'``), or None when the tree did not split
        at all.
      * ``per_cluster[c]`` is ``'atk >= 148.06'`` when EVERY IV in cluster c
        lies on one side of that single split, and None when the cluster
        straddles it.  "The root separates this cluster cleanly" is the only
        claim a one-line legend can carry honestly: a cluster that needs the
        depth-2/3 splits to be described is left unlabelled rather than
        labelled with a rule that is wrong for some of its members.
    """
    tree, X, y = cluster_tree(res, atk, def_, hp, max_depth, min_leaf)
    k = res["k"]
    if "feat" not in tree:
        return None, [None] * k
    f = tree["feat"]
    thr = tree["thr"]
    name = TREE_FEATURES[f]
    thr_txt = TREE_THR_FMT.format(thr)
    left = X[:, f] < thr
    per = []
    for c in range(k):
        m = y == c
        if not m.any():
            per.append(None)
        elif bool(left[m].all()):
            per.append(f"{name} < {thr_txt}")
        elif bool((~left[m]).all()):
            per.append(f"{name} >= {thr_txt}")
        else:
            per.append(None)
    return f"{name} < {thr_txt}", per


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

def degenerate_reason(n_sharp, n_patterns, wins_lo, wins_hi, nO):
    """Why a scenario is below the degeneracy floor, with its own counts.

    Every reason string in this module carries the numbers it is a claim
    about, so the section can print it verbatim: "not enough structure" on
    its own is the kind of sentence a reader cannot check.
    """
    return (f"degenerate: {n_sharp} sharp marginal "
            f"{'opponent' if n_sharp == 1 else 'opponents'} and {n_patterns} "
            f"distinct win {'pattern' if n_patterns == 1 else 'patterns'}, "
            f"below the {DEGEN_MIN_SHARP} / {DEGEN_MIN_PATTERNS} floor; "
            f"every spread wins {wins_lo}-{wins_hi} of {nO} here")


def fragmented_reason(n_sharp, n_patterns, min_cluster_ivs,
                      what="sharp marginal opponents"):
    """The other honest no-clusters outcome: enough marginals, no partition.

    Distinct from ``degenerate_reason`` on purpose (Feraligatr UL 0v0: 12
    sharp marginals, 61 distinct patterns, and still no K in KMIN..KMAX
    whose smallest cluster clears the anti-speck floor).  That scenario is
    NOT degenerate -- its bits go into the concatenated "all scenarios"
    fingerprint -- it is fragmented, and saying "degenerate" there would be
    a false claim about the data.
    """
    return (f"structure too fragmented: {n_sharp} {what} "
            f"and {n_patterns} distinct win patterns, but no cluster count "
            f"in {KMIN}-{KMAX} keeps every cluster at or above "
            f"{min_cluster_ivs} spreads")


def screen_scenario(W):
    """Degeneracy screen for one scenario's win matrix.

    Returns (sharp, wr, n_sharp, n_patterns, degenerate).  Split out because
    two callers need the SAME verdict: the per-scenario driver, and
    ``concat_fingerprint`` deciding whose bits go into the combined view.
    """
    sharp, wr = sharp_marginals(W)
    n_sharp = int(len(sharp))
    if n_sharp:
        n_patterns = int(len(np.unique(W[:, sharp].astype(np.uint8), axis=0)))
    else:
        n_patterns = 1
    degenerate = (n_sharp < DEGEN_MIN_SHARP or n_patterns < DEGEN_MIN_PATTERNS)
    return sharp, wr, n_sharp, n_patterns, degenerate


def concat_fingerprint(win_by_scen):
    """The "all scenarios" fingerprint: non-degenerate scenarios' bits, joined.

    ``win_by_scen``: [(label, W)] in grid order, W the (nIvs, nO) win matrix.
    Returns a dict with ``W`` (the (nIvs, n_bits) bool array, or None when
    fewer than two scenarios qualify), ``bit_scen`` / ``bit_opp`` (what each
    column is), ``scens`` (included labels), ``excluded`` and ``n_bits``.

    Shared with scripts/deep_dive_brief.py, which prints a one-line
    corroboration of this partition: the brief must cluster the SAME bits the
    section's combined view clusters, or the page and the brief would quote
    two different partitions of one grid under one name.
    """
    cols, bit_scen, bit_opp, included, excluded = [], [], [], [], []
    for lbl, W in win_by_scen:
        sharp, _wr, _ns, _np_, degenerate = screen_scenario(W)
        if degenerate:
            excluded.append(lbl)
            continue
        cols.append(W[:, sharp])
        included.append(lbl)
        bit_scen.extend([lbl] * len(sharp))
        bit_opp.extend(int(o) for o in sharp)
    # One scenario is not a combination; it would be a copy under a second
    # name, with a second silhouette to argue with.
    W_all = np.hstack(cols) if len(cols) >= 2 else None
    return {"W": W_all, "bit_scen": bit_scen, "bit_opp": bit_opp,
            "scens": included, "excluded": excluded,
            "n_bits": 0 if W_all is None else int(W_all.shape[1])}


def _scenario_entry(W, sharp, wr, atk, def_, hp, sp_rank, stats, is_named):
    """Cluster one already-screened scenario (or the combined view)."""
    res = cluster_scenario(W, sharp, atk, def_, hp, sp_rank)
    if res is None:
        return None
    tree_acc, tree_lines = stat_rules(res, atk, def_, hp)
    root, per_cluster = root_rules(res, atk, def_, hp)
    return {
        "res": res,
        "defining": None,   # filled by renderer with display names
        "tree_acc": tree_acc,
        "tree_rules": tree_lines,
        "root_rule": root,
        "cluster_rules": per_cluster,
        "flips": flip_table(W, sharp, wr, stats, is_named),
        "wr": wr,
    }


def compute_matchup_clusters(scores_flat, nIvs, nS, nO, scenarios,
                             atk, def_, hp, is_named,
                             scen_pairs=None):
    """Run the full pipeline for EVERY shield scenario the dive baked, in
    grid order, plus a combined "all scenarios" entry.

    scenarios: list of (my_shields, opp_shields) tuples in grid order.
    scen_pairs: restrict to these pairs (default None = every scenario
    present).  atk/def_/hp: per-IV battle stats (shadow-effective).
    is_named: see flip_table.  Returns {scen_label: result} where result has
    keys res/defining/tree_acc/tree_rules/root_rule/cluster_rules/flips, or
    {'reason': ..., 'degenerate': ...} when the scenario carries no cluster
    view.  Scenario labels are '0v0' style, plus ALL_SCEN_KEY.

    Before 2026-09-13 this ran the three EVEN-shield scenarios only
    (0v0 / 1v1 / 2v2) and had no combined entry.  The odd scenarios turned
    out to be the cleanest ones on several dives (Shadow Sableye GL: 0v1
    silhouette 0.65 and a 100%-accurate depth-1 rule, against 0.55 on 1v1),
    so the section clustered everything except its best material.

    The "all scenarios" entry is the CONCATENATED fingerprint: every
    non-degenerate scenario's sharp-marginal bits side by side, clustered
    with the same Hamming machinery.  It is deliberately not a mean score
    across scenarios -- a mean above 500 is not a fight won, and this
    section's identity is "which fights do you win", here asked across every
    shield state at once.
    """
    atk = np.asarray(atk, dtype=np.float64)
    def_ = np.asarray(def_, dtype=np.float64)
    hp = np.asarray(hp, dtype=np.float64)
    sp = atk * def_ * hp
    order = np.argsort(-sp, kind="stable")
    sp_rank = np.empty(nIvs, dtype=np.int32)
    sp_rank[order] = np.arange(1, nIvs + 1)
    stats = {"atk": atk, "def": def_, "hp": hp, "sp": sp}
    min_cluster_ivs = _small_pop_floor(MIN_CLUSTER_IVS, nIvs)

    out = {}
    scen_list = [tuple(s) for s in scenarios]
    pairs = (scen_list if scen_pairs is None
             else [p for p in scen_list if tuple(p) in
                   {tuple(q) for q in scen_pairs}])
    wins_by_scen = []  # (label, W) in grid order, for concat_fingerprint
    for pair in pairs:
        si = scen_list.index(pair)
        label = scenario_label(pair)
        W = win_matrix(scores_flat, nIvs, nS, nO, si)
        wins_by_scen.append((label, W))
        sharp, wr, n_sharp, n_patterns, degenerate = screen_scenario(W)
        if degenerate:
            tot = W.sum(axis=1)
            out[label] = {
                "reason": degenerate_reason(n_sharp, n_patterns,
                                            int(tot.min()), int(tot.max()), nO),
                "degenerate": True,
                "n_sharp": n_sharp, "n_patterns": n_patterns}
            continue
        entry = _scenario_entry(W, sharp, wr, atk, def_, hp, sp_rank, stats,
                                is_named)
        if entry is None:
            out[label] = {
                "reason": fragmented_reason(n_sharp, n_patterns,
                                            min_cluster_ivs),
                "degenerate": False,
                "n_sharp": n_sharp, "n_patterns": n_patterns}
            continue
        out[label] = entry

    # ---- combined "all scenarios" entry ----
    # Needs at least two scenarios to be a combination rather than a copy of
    # one scenario under a second name.
    #
    # MEASURED, and the one judgement call in this function: degenerate
    # scenarios contribute NO bits. Their bits are real win/loss data, so
    # including them is defensible and was what the plan's offline run did;
    # the two differ on Shadow Sableye GL. With the floor (7 scenarios, 113
    # bits) the combined view is K=3, silhouette 0.395, root atk < 148.67,
    # tree accuracy 0.96. Including 0v2's 5 extra bits (118 bits, the plan's
    # number) gives K=2, silhouette 0.452, root atk < 148.06, accuracy
    # 0.9995 -- i.e. it recovers the 0v1 headline. The floor wins here
    # anyway: a scenario whose own data cannot support a partition should
    # not get a vote in the combined one, and letting it in makes the
    # combined view sensitive to exactly the fake-perfect fingerprints the
    # floor exists to keep out. Flipping this is one predicate.
    cf = concat_fingerprint(wins_by_scen)
    if cf["W"] is not None:
        W_all = cf["W"]
        bit_opp = cf["bit_opp"]
        sharp_all = np.arange(W_all.shape[1], dtype=np.int64)
        wr_all = W_all.mean(axis=0)
        entry = _scenario_entry(
            W_all, sharp_all, wr_all, atk, def_, hp, sp_rank, stats,
            lambda bit, stat: is_named(bit_opp[int(bit)], stat))
        n_bits = cf["n_bits"]
        n_patterns_all = int(len(np.unique(W_all.astype(np.uint8), axis=0)))
        meta = {"scens": list(cf["scens"]),
                "excluded": list(cf["excluded"]),
                "n_bits": n_bits,
                "bit_scen": list(cf["bit_scen"]), "bit_opp": list(bit_opp),
                "n_total": len(pairs)}
        if entry is None:
            out[ALL_SCEN_KEY] = {
                "reason": fragmented_reason(
                    n_bits, n_patterns_all, min_cluster_ivs,
                    what="concatenated marginal-matchup bits"),
                "degenerate": False, "combined": meta,
                "n_sharp": n_bits, "n_patterns": n_patterns_all}
        else:
            entry["combined"] = meta
            out[ALL_SCEN_KEY] = entry
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


def _scen_display(label):
    """Dropdown / headline text for a scenario key.

    One definition for both surfaces, so the selector and the block it
    selects cannot spell the same scenario two ways.
    """
    return ALL_SCEN_DISPLAY if label == ALL_SCEN_KEY else f'{label} shields'


def _scen_option_note(entry):
    """The short "why not" a dropdown option can carry.

    The full reason is printed in the scenario's own block; an <option> long
    enough to hold it is unreadable. This keeps the counts that make the
    absence informative -- "0v2 shields - degenerate (5 marginals / 16
    patterns)" tells a reader why without opening it.
    """
    if "res" in entry:
        return ""
    n, p = entry["n_sharp"], entry["n_patterns"]
    marg = "marginal" if n == 1 else "marginals"
    pat = "pattern" if p == 1 else "patterns"
    if entry.get("degenerate"):
        return f' - degenerate ({n} {marg} / {p} {pat})'
    return f' - no clusters ({n} {marg}, too fragmented)'


def _entry_opp_names(entry, disp):
    """Display names indexed the way THIS entry's opponent indices are.

    A per-scenario entry indexes the opponent pool directly. The combined
    entry's columns are (scenario, opponent) bits, so its names carry the
    scenario they came from -- the flip table would otherwise print one
    opponent several times with no way to tell which shield state each row
    is about.
    """
    comb = entry.get("combined")
    if not comb:
        return disp
    return [f'{disp[o]} [{lbl}]'
            for o, lbl in zip(comb["bit_opp"], comb["bit_scen"])]


def _scen_headline(label, entry, nO):
    disp = _scen_display(label)
    if "reason" in entry:
        # Every reason string carries its own counts (see degenerate_reason
        # / fragmented_reason), so nothing is appended here.
        return (f'<p style="font-size:13px;color:var(--text-muted)">'
                f'<b>{disp}</b>: no cluster view -- '
                f'{_esc(entry["reason"])}.</p>')
    res = entry["res"]
    comb = entry.get("combined")
    if comb:
        excl = (' (' + _esc(', '.join(comb["excluded"])) +
                ' excluded as degenerate)') if comb["excluded"] else ''
        head = (f'{comb["n_bits"]} marginal-matchup bits concatenated across '
                f'{len(comb["scens"])} of {comb["n_total"]} shield '
                f'scenarios{excl}')
    else:
        wr = entry["wr"]
        n_win = int((wr == 1.0).sum())
        n_loss = int((wr == 0.0).sum())
        head = (f'{len(res["sharp"])} sharp marginal opponents '
                f'of {nO} ({n_win} always-win / {n_loss} always-lose at '
                f'every IV)')
    sil = res["silhouette"]
    sil_txt = f'silhouette {sil:.2f}'
    if sil < WEAK_SIL:
        sil_txt += ' - weak separation'
    root = entry.get("root_rule")
    root_txt = f'; splits at {_esc(root)}' if root else ''
    return (f'<p style="font-size:13px">'
            f'<b>{disp}</b>: {head}; '
            f'{res["n_patterns"]} distinct win patterns; '
            f'K={res["k"]} clusters ({sil_txt}){root_txt}.</p>')


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
        return ('<div class="dd-section" id="dd-matchup-clusters">'
                '<!-- matchup-clusters:v1 -->'
                '<h2 class="dd-h2">Matchup clusters</h2>'
                '<p style="font-size:13px;color:var(--text-muted)">Not '
                'available: this dive baked no shield scenarios to cluster.'
                '</p></div>\n')

    scen_labels = list(computed.keys())
    # Default view: the combined entry when it clustered (it is the
    # section's own question -- which fights do you win across every shield
    # state -- asked once), then 1v1 (the status quo default, and the
    # scenario a reader arrives with in mind), then anything that clustered.
    _one_one = scenario_label((1, 1))
    _clustered = [lbl for lbl in scen_labels if "res" in computed[lbl]]
    for _cand in (ALL_SCEN_KEY, _one_one):
        if _cand in _clustered:
            default_scen = _cand
            break
    else:
        default_scen = _clustered[0] if _clustered else scen_labels[0]

    # ---- client payload: per-IV labels + legend meta per scenario ----
    # `scens` holds only scenarios that CLUSTERED: the JS treats presence in
    # that map as "labels exist here". Degenerate / fragmented scenarios go
    # in `degenerate` so the mini-grid can title them honestly without the
    # overlay ever finding a labelless entry.
    payload = {"palette": CLUSTER_PALETTE, "default": default_scen,
               "allKey": ALL_SCEN_KEY, "scens": {}, "degenerate": {}}
    for lbl, entry in computed.items():
        disp_lbl = _scen_display(lbl)
        if "res" not in entry:
            payload["degenerate"][lbl] = {
                "display": disp_lbl, "reason": entry["reason"],
                # the two no-cluster kinds read differently on the page: one
                # says "too little data here", the other "too much variety"
                "degenerate": bool(entry.get("degenerate"))}
            continue
        res = entry["res"]
        payload["scens"][lbl] = {
            "k": res["k"],
            "labels": [int(x) for x in res["labels"]],
            "sizes": [c["size"] for c in res["clusters"]],
            "sil": round(float(res["silhouette"]), 4),
            "root": entry.get("root_rule"),
            # Per-cluster legend text, emitted from Python so the JS never
            # formats a threshold: null where the depth-1 root does not
            # separate that cluster cleanly (see root_rules).
            "rules": list(entry.get("cluster_rules") or []),
            "display": disp_lbl,
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
        '<p style="font-size:13px">Every shield scenario the dive baked is '
        'clustered separately -- including the lopsided ones, which on '
        'several dives carry the cleanest structure -- plus an '
        f'<b>{ALL_SCEN_DISPLAY}</b> view that concatenates every '
        'non-degenerate scenario\'s marginal-matchup bits into one '
        'fingerprint. That combined view is not an average of scores: it is '
        '"which fights do you win across every shield state", asked once. '
        'Scenarios with too little structure to cluster are listed with '
        'their counts rather than hidden.</p>')
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
        f'{_esc(_scen_display(lbl))}'
        f'{_esc(_scen_option_note(computed[lbl]))}</option>'
        for lbl in scen_labels)
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
            names = _entry_opp_names(entry, disp)
            parts.append(_cluster_table(entry, names))
            parts.append(_winrate_grid(entry, names))
            parts.append(_rules_block(entry))
            parts.append(_flip_table_html(entry, names, bool(anchor_opps)))
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
        'that overlap completely in score separate cleanly there. A '
        'scenario is skipped as <b>degenerate</b> when it has fewer than '
        f'{knobs["degen_min_sharp"]} sharp marginals or fewer than '
        f'{knobs["degen_min_patterns"]} distinct win patterns -- on that '
        'little data every candidate K scores near-perfectly, which is a '
        'measurement artifact and not structure -- and its bits are left '
        f'out of the {ALL_SCEN_DISPLAY} fingerprint. A scenario that clears '
        'the floor but has no split keeping every cluster above the minimum '
        'size is reported as fragmented instead, and its bits still count '
        'toward the combined view. Replaces '
        'the retired score-gap cluster heuristic (2026-07), which usually '
        '(~77% of sampled runs) fired on float-level jitter in the '
        'opponent-averaged score, and even when it did catch a real tier '
        'could not name which matchups defined it.</p></details>')

    parts.append('<script type="application/json" class="dd-mc-data">'
                 + json.dumps(payload, separators=(",", ":"))
                 + '</script>')
    parts.append('</div>\n')
    return "\n".join(parts)
