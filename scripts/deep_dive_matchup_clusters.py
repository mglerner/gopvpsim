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
below is explicit and there is no RNG anywhere.  Two deliberate
improvements over the offline reference pipeline
(~/coding/reports/gopvpsim-cluster-analysis/cluster_pipeline.py):

  * silhouette is computed exactly over the full population via unique
    patterns + counts, replacing the reference's seed-0 2000-row subsample
    (removes the RNG-stream dependence of the K choice);
  * K selection carries a parsimony floor (min cluster size + smallest-K-
    within-epsilon), the report's own pre-ship caveat for tiny cup pools.

Tree accuracy is IN-SAMPLE (regularized by min_samples_leaf), matching
what the reference code actually computed; do not label it cross-validated.
"""

import numpy as np

WIN_RATING = 500  # strict >; matches src/gopvpsim/battle.py and all consumers

# K-selection knobs (parsimony floor — see module docstring).
KMIN = 2
KMAX = 6
SIL_EPSILON = 0.03          # smallest K within this of the best silhouette
MIN_CLUSTER_IVS = 40        # anti-speck floor at full 4096-IV dives
SHARP_LO, SHARP_HI = 0.02, 0.98
DEFINING_MIN_DELTA = 0.15
TREE_MAX_DEPTH = 3
TREE_MIN_LEAF = 40


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

def _unique_patterns(F):
    """Collapse fingerprint rows to unique patterns.

    Returns (patterns (u, d) uint8, inverse (n,), counts (u,)).
    np.unique sorts patterns lexicographically — deterministic.
    """
    patterns, inverse, counts = np.unique(
        F.astype(np.uint8), axis=0, return_inverse=True, return_counts=True)
    return patterns, inverse.ravel(), counts


def _linkage_labels(patterns, counts, ks):
    """Weighted average-linkage (Hamming) labels for each requested K.

    Average linkage over the full duplicated population is exactly weighted
    average linkage over unique patterns (identical points merge at distance
    zero first, which is the unique-collapse).  Lance-Williams update for
    average linkage: d(i+j, k) = (n_i d(i,k) + n_j d(j,k)) / (n_i + n_j).

    Tie-break on equal merge distances: lowest first index, then lowest
    second index (indices in the current active ordering, which is stable).

    Returns {k: labels(u,)} with arbitrary (but deterministic) label ids.
    """
    u, d = patterns.shape
    ks = sorted(set(int(k) for k in ks if 2 <= k <= u))
    out = {}
    if u == 1:
        return {1: np.zeros(1, dtype=np.int32)} if 1 in ks else out
    # Pairwise Hamming distances between unique patterns.
    diff = (patterns[:, None, :] != patterns[None, :, :]).mean(axis=2)
    dist = diff.astype(np.float64)
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


def _weighted_silhouette(patterns, counts, labels):
    """Exact full-population mean silhouette (Hamming), via unique patterns.

    For a point with pattern p in cluster A:
      a(p) = sum_{q in A} c_q d(p,q) / (n_A - 1)   (d(p,p)=0 excludes self)
      b(p) = min_{B != A} sum_{q in B} c_q d(p,q) / n_B
      s(p) = (b - a) / max(a, b); s = 0 when n_A == 1.
    Overall silhouette = count-weighted mean of s over patterns.
    """
    k = int(labels.max()) + 1
    if k < 2:
        return 0.0
    diff = (patterns[:, None, :] != patterns[None, :, :]).mean(axis=2)
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
        min_cluster_ivs = max(2, min(MIN_CLUSTER_IVS, n // 8))
    patterns, inverse, counts = _unique_patterns(F)
    u = len(counts)
    if u < 2:
        return None, None, None, {}
    ks = list(range(kmin, min(kmax, u) + 1))
    lab_by_k = _linkage_labels(patterns, counts, ks)
    sil_by_k = {}
    ok = []
    for k in ks:
        if k not in lab_by_k:
            continue
        lab = lab_by_k[k]
        sizes = np.array([counts[lab == c].sum() for c in range(k)])
        if sizes.min() < min_cluster_ivs:
            continue
        sil_by_k[k] = _weighted_silhouette(patterns, counts, lab)
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
    """Marginal matchups gained between adjacent (weak -> strong) clusters."""
    sharp = res["sharp"]
    clusters = res["clusters"]
    out = []
    for i in range(1, len(clusters)):
        prev = clusters[i - 1]["winrate_per_sharp"]
        cur = clusters[i]["winrate_per_sharp"]
        delta = cur - prev
        gained_idx = np.argsort(-delta, kind="stable")[:top]
        names = [(opponent_names[sharp[g]], float(delta[g]),
                  float(cur[g]), float(prev[g]))
                 for g in gained_idx if delta[g] > min_delta]
        out.append({"from": i - 1, "to": i, "gained": names})
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
    min_leaf = max(2, min(min_leaf, len(y) // 8))
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
    ties -> earlier stat in insertion order, then '>=' before '<', then
    lower threshold (first boundary scanned).
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
        rows.append({
            "opp_idx": int(o),
            "winrate": float(wr[o]),
            "stat": sname,
            "threshold": thr,
            "direction": dirn,
            "accuracy": acc,
            "named": is_named(int(o), sname),
        })
    return rows


# ---------------------------------------------------------------------------
# Top-level per-scenario driver
# ---------------------------------------------------------------------------

def compute_matchup_clusters(scores_flat, nIvs, nS, nO, scenarios,
                             atk, def_, hp, is_named,
                             scen_pairs=((0, 0), (1, 1), (2, 2))):
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
        label = f"{pair[0]}v{pair[1]}"
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
