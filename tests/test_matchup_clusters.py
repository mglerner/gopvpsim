"""Unit tests for scripts/deep_dive_matchup_clusters.py (pure-numpy pipeline).

Synthetic-data tests: planted cluster structure, determinism, the parsimony
floor, single-stat flip directions, tree rule extraction, degenerate inputs.
"""
import ast
import importlib.util
import json
import re
from pathlib import Path

import numpy as np
import pytest

from tests.conftest import load_deep_dive

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "deep_dive_matchup_clusters",
    REPO_ROOT / "scripts" / "deep_dive_matchup_clusters.py")
mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mc)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def planted_scores(block_sizes, patterns, nS=9, scen_idx=4, n_opp=None):
    """Build a flat score grid whose scen_idx win matrix has the given
    planted fingerprint blocks (list of pattern rows, one per block)."""
    n_opp = n_opp if n_opp is not None else len(patterns[0])
    nIvs = sum(block_sizes)
    a = np.full((nIvs, nS, n_opp), 200, dtype=np.int32)  # loss everywhere
    r = 0
    for size, pat in zip(block_sizes, patterns):
        for j, bit in enumerate(pat):
            if bit:
                a[r:r + size, scen_idx, j] = 800
        r += size
    return a.ravel().tolist(), nIvs, n_opp


def staircase_scores(n_opp=8, block=40, nS=9, scen_idx=None):
    """A grid that CLEARS the degeneracy floor, for the render fixtures.

    ``n_opp + 1`` blocks of ``block`` IVs; block i wins the first i
    opponents. Every opponent's win rate is then (n_opp - j) / (n_opp + 1),
    i.e. strictly inside the sharp window for every j, and the blocks are
    n_opp + 1 distinct win patterns -- so with the defaults it is 8 sharp
    marginals and 9 patterns, just over the 6 / 8 floor that
    ``planted_scores``'s 2-4 opponent grids sit under.

    ``scen_idx=None`` plants the same staircase in EVERY scenario (so every
    scenario clusters); an int plants it in that one.
    """
    n_iv = block * (n_opp + 1)
    a = np.full((n_iv, nS, n_opp), 200, dtype=np.int32)
    sis = range(nS) if scen_idx is None else [scen_idx]
    for si in sis:
        for i in range(n_opp + 1):
            a[i * block:(i + 1) * block, si, :i] = 800
    return a.ravel().tolist(), n_iv, n_opp


def no_anchors(opp_idx, stat):
    return None


class _Anchor:
    """Stand-in for a resolved anchor (render_section reads .opponent)."""

    def __init__(self, opponent):
        self.opponent = opponent


# ---------------------------------------------------------------------------
# win matrix / sharp marginals
# ---------------------------------------------------------------------------

def test_win_matrix_strict_500():
    flat = [499, 500, 501, 1000]
    W = mc.win_matrix(flat, 1, 1, 4, 0)
    assert W.tolist() == [[False, False, True, True]]


def test_sharp_marginals_window_and_order():
    # 100 IVs, 4 opponents: wr = 0.0 (settled), 0.5, 0.7, 1.0 (settled)
    W = np.zeros((100, 4), dtype=bool)
    W[:50, 1] = True
    W[:70, 2] = True
    W[:, 3] = True
    sharp, wr = mc.sharp_marginals(W)
    assert sharp.tolist() == [1, 2]          # closest to 50% first
    assert wr[0] == 0.0 and wr[3] == 1.0


def test_sharp_marginals_tie_broken_by_index():
    W = np.zeros((10, 3), dtype=bool)
    W[:4, 0] = True   # wr 0.4
    W[:6, 1] = True   # wr 0.6  (same |wr-0.5|)
    W[:4, 2] = True   # wr 0.4  (same |wr-0.5|)
    sharp, _ = mc.sharp_marginals(W)
    assert sharp.tolist() == [0, 1, 2]


# ---------------------------------------------------------------------------
# clustering: planted structure, determinism, parsimony
# ---------------------------------------------------------------------------

def test_choose_k_two_planted_clusters():
    F = np.zeros((200, 6), dtype=np.uint8)
    F[100:, :] = 1                             # two maximally-distant blocks
    k, labels, sil, _ = mc.choose_k(F)
    assert k == 2
    assert len(set(labels[:100])) == 1 and len(set(labels[100:])) == 1
    assert labels[0] != labels[150]
    assert sil > 0.9


def test_choose_k_three_planted_clusters():
    F = np.zeros((300, 9), dtype=np.uint8)
    F[100:200, :3] = 1
    F[200:, :] = 1
    k, labels, sil, _ = mc.choose_k(F)
    assert k == 3
    assert len({labels[0], labels[150], labels[250]}) == 3


def test_parsimony_floor_rejects_specks():
    # 5-IV speck + 495-IV blob: k=2 would carve the speck; floor rejects it.
    F = np.zeros((500, 6), dtype=np.uint8)
    F[:5, :] = 1
    k, labels, sil, sil_by_k = mc.choose_k(F)   # floor = min(40, 500//8) = 40
    assert k is None


def test_min_cluster_floor_scales_for_tiny_populations():
    # 27-IV floor dive: floor becomes max(2, 27//8) = 3; a 13/14 split is OK.
    F = np.zeros((27, 6), dtype=np.uint8)
    F[13:, :] = 1
    k, labels, _, _ = mc.choose_k(F)
    assert k == 2


def test_clustering_is_deterministic():
    rng = np.random.default_rng(7)   # fixed-seed test data, not pipeline RNG
    F = (rng.random((400, 12)) < 0.4).astype(np.uint8)
    r1 = mc.choose_k(F)
    r2 = mc.choose_k(F)
    assert r1[0] == r2[0]
    assert np.array_equal(r1[1], r2[1])
    assert r1[2] == r2[2]


# ---------------------------------------------------------------------------
# cluster_scenario: weak->strong ordering + payload
# ---------------------------------------------------------------------------

def test_cluster_scenario_orders_weak_to_strong():
    # strong block wins both marginals, weak block wins neither; make the
    # strong block FIRST in IV order to prove ordering is by wins, not index.
    W = np.zeros((200, 4), dtype=bool)
    W[:100, 0] = True
    W[:100, 1] = True
    W[:, 2] = True          # settled win (not sharp)
    sharp, wr = mc.sharp_marginals(W)
    atk = np.linspace(100, 110, 200)
    dfn = np.linspace(130, 140, 200)
    hp = np.full(200, 135.0)
    sp_rank = np.arange(1, 201, dtype=np.int32)
    res = mc.cluster_scenario(W, sharp, atk, dfn, hp, sp_rank)
    assert res["k"] == 2
    assert res["labels"][0] == 1 and res["labels"][-1] == 0   # strong = C1
    assert res["clusters"][0]["mean_marginal_wins"] <= \
        res["clusters"][1]["mean_marginal_wins"]
    assert res["clusters"][1]["size"] == 100


def test_defining_matchups_names_the_flip():
    W = np.zeros((200, 3), dtype=bool)
    W[:100, 0] = True
    W[:100, 1] = True
    W[:150, 2] = True
    sharp, wr = mc.sharp_marginals(W)
    atk = np.linspace(100, 110, 200)
    res = mc.cluster_scenario(W, sharp, atk, atk, atk,
                              np.arange(1, 201, dtype=np.int32))
    names = ["OppA", "OppB", "OppC"]
    dm = mc.defining_matchups(res, names)
    gained = {n for step in dm for (n, d, c, p) in step["gained"]}
    assert "OppA" in gained and "OppB" in gained


# ---------------------------------------------------------------------------
# decision tree
# ---------------------------------------------------------------------------

def test_stat_rules_recovers_single_attack_cut():
    n = 400
    atk = np.linspace(100, 112, n)
    dfn = np.full(n, 135.0)
    hp = np.full(n, 135.0)
    labels = (atk >= 106.0).astype(np.int64)
    res = {"labels": labels}
    acc, lines = mc.stat_rules(res, atk, dfn, hp)
    assert acc == 1.0
    assert any("atk" in ln for ln in lines)
    joined = "\n".join(lines)
    assert "def" not in joined and "hp" not in joined


def test_stat_rules_two_axis_split():
    n = 400
    rng = np.random.default_rng(3)
    atk = rng.uniform(100, 112, n)
    hp = rng.uniform(125, 145, n)
    dfn = np.full(n, 135.0)
    labels = ((atk >= 106.0).astype(np.int64) +
              ((atk >= 106.0) & (hp >= 138.0)).astype(np.int64))
    res = {"labels": labels}
    acc, lines = mc.stat_rules(res, atk, dfn, hp)
    assert acc > 0.95
    joined = "\n".join(lines)
    assert "atk" in joined and "hp" in joined


# ---------------------------------------------------------------------------
# single-stat flips
# ---------------------------------------------------------------------------

def test_single_stat_flip_ge_direction():
    atk = np.linspace(100, 110, 100)
    y = atk >= 105.0
    stats = {"atk": atk, "def": np.full(100, 1.0),
             "hp": np.full(100, 1.0), "sp": atk}
    acc, sname, thr, dirn = mc.single_stat_flip(stats, y)
    assert acc == 1.0 and sname == "atk" and dirn == ">="
    assert thr == pytest.approx(atk[y.argmax()])


def test_single_stat_flip_lt_direction():
    # win iff LOW attack — only findable with the '<' scan
    atk = np.linspace(100, 110, 100)
    dfn = np.full(100, 1.0)
    y = atk < 104.0
    stats = {"atk": atk, "def": dfn, "hp": dfn, "sp": dfn}
    acc, sname, thr, dirn = mc.single_stat_flip(stats, y)
    assert acc == 1.0 and sname == "atk" and dirn == "<"


def test_flip_table_flags_uninformative_constant_rules():
    # opponent whose wins have NO single-stat structure: the best "rule" is
    # the constant predictor at the base rate, which must be flagged
    # uninformative (review finding: it rendered as a fake threshold).
    rng = np.random.default_rng(11)
    n = 200
    W = np.zeros((n, 1), dtype=bool)
    W[rng.choice(n, size=120, replace=False), 0] = True   # 60% win, no signal
    stats = {"atk": np.full(n, 5.0), "def": np.full(n, 6.0),
             "hp": np.full(n, 7.0), "sp": np.full(n, 8.0)}
    sharp, wr = mc.sharp_marginals(W)
    rows = mc.flip_table(W, sharp, wr, stats, lambda o, s: None)
    assert rows[0]["informative"] is False
    assert rows[0]["accuracy"] == pytest.approx(0.6)


def test_defining_matchups_reports_losses():
    # stronger cluster gains opp1+opp2 but TRADES AWAY opp0 (win-sets cross)
    W = np.zeros((200, 3), dtype=bool)
    W[:100, 0] = True            # weak block wins opp0
    W[100:, 1] = True            # strong block wins opp1, opp2
    W[100:, 2] = True
    sharp, wr = mc.sharp_marginals(W)
    atk = np.linspace(100, 110, 200)
    res = mc.cluster_scenario(W, sharp, atk, atk, atk,
                              np.arange(1, 201, dtype=np.int32))
    dm = mc.defining_matchups(res, ["OppA", "OppB", "OppC"])
    lost = {n for step in dm for (n, d, c, p) in step["lost"]}
    assert "OppA" in lost


def test_flip_table_named_flags():
    W = np.zeros((100, 2), dtype=bool)
    atk = np.linspace(100, 110, 100)
    W[atk >= 104.0, 0] = True
    W[atk >= 106.0, 1] = True
    sharp, wr = mc.sharp_marginals(W)
    stats = {"atk": atk, "def": np.full(100, 1.0),
             "hp": np.full(100, 1.0), "sp": atk}
    rows = mc.flip_table(W, sharp, wr, stats,
                         lambda o, s: (o == 0))
    by_opp = {r["opp_idx"]: r for r in rows}
    assert by_opp[0]["named"] is True
    assert by_opp[1]["named"] is False
    assert by_opp[1]["accuracy"] == 1.0 and by_opp[1]["stat"] == "atk"


# ---------------------------------------------------------------------------
# top-level driver
# ---------------------------------------------------------------------------

SCENARIOS9 = [(a, b) for a in range(3) for b in range(3)]


def test_compute_covers_every_scenario_plus_the_combined_view():
    """Pre-fix (through 2026-09-12) this returned ONLY the even scenarios:
    ``set(out) <= {"0v0", "1v1", "2v2"}`` was the pinned contract, and there
    was no combined entry. It now runs every scenario the dive baked, in
    grid order, and appends ALL_SCEN_KEY."""
    flat, nIvs, nO = staircase_scores()
    atk = np.linspace(100, 110, nIvs)
    out = mc.compute_matchup_clusters(
        flat, nIvs, 9, nO, SCENARIOS9, atk, atk[::-1].copy(),
        np.full(nIvs, 135.0), no_anchors)
    assert list(out) == [mc.scenario_label(p) for p in SCENARIOS9] + ["all"]
    # the pre-fix key set is a strict subset of what ships now
    assert {"0v0", "1v1", "2v2"} < set(out)
    r = out["1v1"]
    assert r["res"]["k"] >= 2
    assert len(r["flips"]) == nO         # every opponent is a sharp marginal
    assert all(row["named"] is None for row in r["flips"])
    comb = out["all"]["combined"]
    assert comb["n_bits"] == 9 * nO      # 9 scenarios x 8 sharp marginals
    assert comb["excluded"] == []
    assert len(out["all"]["flips"]) == comb["n_bits"]


def test_compute_can_still_be_restricted_to_a_scenario_subset():
    flat, nIvs, nO = staircase_scores()
    atk = np.linspace(100, 110, nIvs)
    out = mc.compute_matchup_clusters(
        flat, nIvs, 9, nO, SCENARIOS9, atk, atk, atk, no_anchors,
        scen_pairs=[(0, 0), (1, 1)])
    assert list(out) == ["0v0", "1v1", "all"]


def test_compute_handles_missing_scenarios():
    # dive run with a single scenario: only that pair is computable, and one
    # scenario is not a combination -- no "all" entry is emitted.
    flat, nIvs, nO = staircase_scores(nS=1, scen_idx=0)
    atk = np.linspace(100, 110, nIvs)
    out = mc.compute_matchup_clusters(
        flat, nIvs, 1, nO, [(1, 1)], atk, atk, atk, no_anchors)
    assert list(out) == ["1v1"]
    assert out["1v1"]["res"]["k"] >= 2


def test_all_settled_scenario_reports_reason():
    flat, nIvs, nO = planted_scores([100], [[1, 0, 1]], scen_idx=4)
    atk = np.linspace(100, 110, nIvs)
    out = mc.compute_matchup_clusters(
        flat, nIvs, 9, nO, SCENARIOS9, atk, atk, atk, no_anchors)
    assert out["1v1"]["n_sharp"] == 0
    assert "reason" in out["1v1"]


def test_degeneracy_floor_reports_counts_and_leaves_the_bits_out_of_all():
    """A too-thin scenario is named with its own numbers, not hidden.

    Scenarios 4 and 8 (1v1, 2v2) get the full staircase; scenario 0 (0v0)
    gets a two-opponent split -- 2 sharp marginals, under the 6 / 8 floor.
    Two clean scenarios, because one is not a combination.
    """
    flat, nIvs, nO = staircase_scores(scen_idx=4)
    arr = np.array(flat, dtype=np.int32).reshape(nIvs, 9, nO)
    arr[:, 8, :] = arr[:, 4, :]             # 2v2: the same staircase
    arr[nIvs // 2:, 0, :2] = 800            # 0v0: 2 sharp, 2 patterns
    atk = np.linspace(100, 110, nIvs)
    out = mc.compute_matchup_clusters(
        arr.ravel().tolist(), nIvs, 9, nO, SCENARIOS9, atk, atk, atk,
        no_anchors)
    d = out["0v0"]
    assert d["degenerate"] is True
    assert d["n_sharp"] == 2 and d["n_patterns"] == 2
    # the reason carries every number it is a claim about, and leads with
    # the FINDING (what the shield state does) rather than the floor
    assert d["reason"].startswith("every spread wins ")
    assert f"of {nO} opponents here" in d["reason"]
    assert "Only 2 opponents are sharp marginals" in d["reason"]
    assert "2 distinct win patterns" in d["reason"]
    assert (f"below the {mc.DEGEN_MIN_SHARP}-opponent / "
            f"{mc.DEGEN_MIN_PATTERNS}-pattern floor") in d["reason"]
    assert mc.ALL_SCEN_DISPLAY in d["reason"]
    # and its bits are NOT in the concatenated fingerprint
    comb = out["all"]["combined"]
    assert "0v0" in comb["excluded"] and "0v0" not in comb["scens"]
    assert comb["scens"] == ["1v1", "2v2"]
    assert comb["n_bits"] == 2 * nO         # 0v0's 2 bits are not in it


def test_fragmented_reason_is_distinct_from_degenerate():
    """Feraligatr UL 0v0's case: plenty of marginals, still no partition.

    Measured there as 12 sharp marginals and 61 distinct win patterns with
    every K in KMIN..KMAX failing the min-cluster floor. Reproduced here
    with 8 tight core patterns (24 IVs each) plus one distant 8-IV outlier:
    the outlier is its own cluster at every K in 2..6 and 8 < the 25-IV
    floor for this population, so no K survives -- while 7 sharp marginals
    and 9 patterns clear the degeneracy floor comfortably.
    """
    nO, nS = 7, 9
    rows = []
    for i in range(8):                       # 8 core patterns, 24 IVs each
        rows += [[(i >> b) & 1 for b in range(3)] + [0] * 4] * 24
    rows += [[0, 0, 0, 1, 1, 1, 1]] * 8      # the distant speck
    W = np.array(rows, dtype=bool)
    nIvs = len(W)
    arr = np.full((nIvs, nS, nO), 200, dtype=np.int32)
    arr[:, 4, :][W] = 800
    atk = np.linspace(100, 110, nIvs)
    out = mc.compute_matchup_clusters(
        arr.ravel().tolist(), nIvs, nS, nO, SCENARIOS9, atk, atk, atk,
        no_anchors, scen_pairs=[(1, 1)])
    e = out["1v1"]
    assert "res" not in e
    assert e["degenerate"] is False              # NOT the degenerate reason
    assert e["n_sharp"] == 7 and e["n_patterns"] == 9
    assert e["reason"].startswith("no clusters here:")
    assert "too fragmented" in e["reason"]
    # and it says the opposite of the degenerate reason about the bits
    assert f"still count toward the {mc.ALL_SCEN_DISPLAY}" in e["reason"]
    assert "7 sharp marginal opponents" in e["reason"]
    assert "9 distinct win patterns" in e["reason"]
    assert str(mc._small_pop_floor(mc.MIN_CLUSTER_IVS, nIvs)) in e["reason"]


# ---------------------------------------------------------------------------
# shared primitives (DRY review 2026-08-05 entry 14)
# ---------------------------------------------------------------------------

def test_hamming_is_the_fraction_of_differing_bits():
    p = np.array([[0, 0, 1], [0, 1, 1], [1, 1, 1]], dtype=np.uint8)
    d = mc._hamming(p)
    assert d[0, 0] == 0.0
    assert d[0, 1] == pytest.approx(1 / 3)
    assert d[0, 2] == pytest.approx(2 / 3)
    assert np.array_equal(d, d.T)


def test_hamming_definition_lives_in_exactly_one_place():
    """The linkage and the silhouette must score the SAME geometry."""
    src = (REPO_ROOT / "scripts" / "deep_dive_matchup_clusters.py").read_text()
    # Pre-2026-09-13 the expression was the broadcast form
    # ``(patterns[:, None, :] != patterns[None, :, :]).mean(axis=2)``; the
    # matmul below replaced it for cost, not for behaviour.
    assert src.count("a @ b.T + b @ a.T") == 1, (
        "the pairwise-distance expression was re-inlined; call _hamming()")
    assert "patterns[None, :, :]" not in src


def _hamming_broadcast(patterns):
    """The pre-2026-09-13 definition, kept HERE as the equivalence oracle."""
    return (patterns[:, None, :] != patterns[None, :, :]).mean(axis=2)


def test_hamming_is_bit_identical_to_the_broadcast_definition():
    """The matmul form is an optimization, so equality is EXACT, not approx.

    Every product is 0 or 1 and every partial sum is an exact integer, so no
    summation order can change the result -- and the linkage's tie-breaks
    ride on exact equality, so `pytest.approx` here would hide the only
    failure that matters.
    """
    rng = np.random.default_rng(0)
    for u, d in ((2, 1), (5, 3), (40, 9), (200, 21), (300, 113)):
        p = (rng.random((u, d)) < 0.5).astype(np.uint8)
        got, want = mc._hamming(p), _hamming_broadcast(p)
        assert np.array_equal(got, want), (u, d)
    # degenerate rows: all-equal and all-opposite
    p = np.array([[1, 1, 1], [1, 1, 1], [0, 0, 0]], dtype=np.uint8)
    assert np.array_equal(mc._hamming(p), _hamming_broadcast(p))


def _linkage_full_scan(patterns, counts, ks, diff):
    """The pre-2026-09-13 merge loop: re-scan the whole active submatrix.

    The row-minimum cache that replaced it must choose the SAME pair at every
    merge, ties included -- which is the whole risk, since Hamming distances
    on short fingerprints tie constantly.
    """
    u = patterns.shape[0]
    out = {}
    ks = sorted(set(int(k) for k in ks if 2 <= k <= u))
    dist = diff.astype(np.float64)
    np.fill_diagonal(dist, np.inf)
    size = counts.astype(np.float64).copy()
    active = np.ones(u, dtype=bool)
    labels = np.arange(u, dtype=np.int32)
    n_active = u
    if n_active in ks:
        out[n_active] = labels.copy()
    while n_active > 2:
        sub = np.where(active)[0]
        block = dist[np.ix_(sub, sub)]
        i_s, j_s = divmod(int(np.argmin(block)), block.shape[1])
        i, j = int(sub[i_s]), int(sub[j_s])
        if i > j:
            i, j = j, i
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
    for k, lab in out.items():
        _, norm = np.unique(lab, return_inverse=True)
        out[k] = norm.astype(np.int32).ravel()
    return out


def test_linkage_cache_picks_the_same_merges_as_a_full_scan():
    ks = [2, 3, 4, 5, 6]
    rng = np.random.default_rng(0)
    checked = 0
    for u, d in ((9, 7), (60, 13), (150, 21), (400, 8), (600, 113)):
        p = np.unique((rng.random((u, d)) < 0.5).astype(np.uint8), axis=0)
        counts = rng.integers(1, 40, len(p)).astype(np.int64)
        diff = mc._hamming(p)
        got = mc._linkage_labels(p, counts, ks, diff)
        want = _linkage_full_scan(p, counts, ks, diff)
        assert set(got) == set(want), (u, d)
        for k in want:
            assert np.array_equal(got[k], want[k]), (u, d, k)
        checked += len(want)
    assert checked >= 20, "the oracle produced almost no partitions to compare"
    # tie-heavy by construction: 8 bits over 400 rows forces duplicate
    # distances everywhere, which is where a tie-break change would show
    p = np.unique((rng.random((400, 8)) < 0.5).astype(np.uint8), axis=0)
    diff = mc._hamming(p)
    assert (np.unique(diff).size < diff.size), "fixture has no tied distances"


def test_linkage_does_not_mutate_a_shared_distance_matrix():
    # choose_k hands the SAME matrix to the linkage and the silhouette; the
    # Lance-Williams update is in-place, so it must work on a copy.
    F = np.zeros((300, 9), dtype=np.uint8)
    F[100:200, :3] = 1
    F[200:, :] = 1
    patterns, _, counts = mc._unique_patterns(F)
    diff = mc._hamming(patterns)
    before = diff.copy()
    mc._linkage_labels(patterns, counts, [2, 3], diff)
    assert np.array_equal(diff, before)


def test_silhouette_precomputed_matrix_matches_recomputed():
    F = np.zeros((300, 9), dtype=np.uint8)
    F[100:200, :3] = 1
    F[200:, :] = 1
    patterns, _, counts = mc._unique_patterns(F)
    lab = mc._linkage_labels(patterns, counts, [3])[3]
    assert (mc._weighted_silhouette(patterns, counts, lab) ==
            mc._weighted_silhouette(patterns, counts, lab,
                                    mc._hamming(patterns)))


def test_small_pop_floor_scales_and_clamps():
    assert mc._small_pop_floor(40, 4096) == 40      # full dive: the cap
    assert mc._small_pop_floor(40, 27) == 3         # floor dive: n // 8
    assert mc._small_pop_floor(40, 8) == 2          # hard floor of 2


# ---------------------------------------------------------------------------
# opponent-name folding
# ---------------------------------------------------------------------------

def test_base_opponent_keeps_form_and_shadow_tags():
    pool = {"Sableye", "Sableye (Shadow)", "Sableye (Shadow) (Foul Play)",
            "Corsola (Galarian)"}
    assert mc.base_opponent("Sableye (Shadow)", pool) == "Sableye (Shadow)"
    assert mc.base_opponent("Corsola (Galarian)", pool) == "Corsola (Galarian)"
    # multi-level: drop the moveset tag, keep the Shadow form
    assert (mc.base_opponent("Sableye (Shadow) (Foul Play)", pool) ==
            "Sableye (Shadow)")


def test_base_opponent_folds_variant_only_when_stem_is_in_the_pool():
    assert mc.base_opponent("Medicham (atk-weighted)", {"Medicham"}) == "Medicham"
    assert (mc.base_opponent("Medicham (atk-weighted)", {"Chansey"}) ==
            "Medicham (atk-weighted)")


# ---------------------------------------------------------------------------
# render_section: named-anchor inheritance, tint tokens, param note
# ---------------------------------------------------------------------------

# Eight opponents, because the section's degeneracy floor needs at least
# six sharp marginals before a scenario gets a cluster view at all. The
# three Sableye rows are the ones the anchor-inheritance test reads; the
# rest are pool filler.
OPP_NAMES = ["Sableye", "Sableye (Shadow)", "Sableye (Bug Bite)",
             "Azumarill", "Medicham", "Registeel", "Bastiodon", "Umbreon"]


def _render(anchor_names):
    """Render a 360-IV / 8-opponent section; every opponent is sharp."""
    flat, nIvs, nO = staircase_scores(n_opp=len(OPP_NAMES))
    atk = np.linspace(100, 110, nIvs)
    data_obj = {"ivAtk": atk.tolist(), "ivDef": atk.tolist(),
                "ivHp": np.full(nIvs, 135.0).tolist()}
    return mc.render_section(
        flat, nIvs, 9, nO, SCENARIOS9, OPP_NAMES, data_obj,
        "rank-1", "Shadow Claw/Foul Play+Power Gem",
        [_Anchor(a) for a in anchor_names])


def _flip_row(html, name):
    import re
    section = html.split("Matchup flip thresholds", 1)[1]
    m = re.search(r"<tr><td>" + re.escape(name) + r"</td>.*?</tr>",
                  section, re.DOTALL)
    assert m, f"no flip row for {name}"
    return m.group(0)


def test_named_anchor_does_not_leak_across_a_shadow_variant():
    html = _render(["Sableye"])
    # the anchored opponent itself
    assert "named" in _flip_row(html, "Sableye")
    # alt-moveset sibling inherits its base's anchor
    assert "named" in _flip_row(html, "Sableye (Bug Bite)")
    # the Shadow form is a DIFFERENT opponent: it must stay UNNAMED
    assert "<b>UNNAMED</b>" in _flip_row(html, "Sableye (Shadow)")


# Winrate-tint CSS, whitespace-tolerant at every join. The originals were
# exact substrings with no space after ``:`` or ``,``; a single reformat of
# the emitter would have broken the positive half and, worse, SILENTLY
# satisfied the negative half (2026-08-09 test-suite review, Phase 3).
_MIX_WIN = re.compile(r"color-mix\(\s*in\s+srgb\s*,\s*var\(\s*--matrix-win-bg\s*\)")
_MIX_LOSS = re.compile(r"color-mix\(\s*in\s+srgb\s*,\s*var\(\s*--matrix-loss-bg\s*\)")
_FG_WIN = re.compile(r"color\s*:\s*var\(\s*--matrix-win-fg\s*\)")
_FG_LOSS = re.compile(r"color\s*:\s*var\(\s*--matrix-loss-fg\s*\)")
# Retired dark-only fills. `rgba?\(` also catches the modern space-separated
# `rgb(57 135 229)` spelling, which the old `"rgba(" not in html` missed.
_LEGACY_RGB = re.compile(r"rgba?\(\s*\d")
_LEGACY_TRIPLE = re.compile(r"\b57\s*[,\s]\s*135\s*[,\s]\s*229\b"
                            r"|\b230\s*[,\s]\s*103\s*[,\s]\s*103\b")
# Outcome TEXT tokens used as a fill. Tolerates `var( --win )`.
_TEXT_TOKEN_FILL = re.compile(r"var\(\s*--(?:win|loss)\s*\)")


def test_winrate_tint_uses_theme_matrix_tokens():
    html = _render(["Sableye"])
    # the matchup-web heatmap lane: fill-role token + its PAIRED text color.
    # These four are also the POSITIVE CONTROL for the three negatives
    # below: a page that emitted no tinted cells at all would satisfy every
    # "must not come back" assertion for free.
    assert _MIX_WIN.search(html)
    assert _MIX_LOSS.search(html)
    assert _FG_WIN.search(html)
    assert _FG_LOSS.search(html)
    # the old dark-only rgb/rgba fills must not come back
    assert not _LEGACY_RGB.findall(html)
    assert not _LEGACY_TRIPLE.findall(html)
    # nor the outcome TEXT tokens used as a fill (fails AA, see governance s3)
    assert not _TEXT_TOKEN_FILL.findall(html)
    assert "Green tint" in html


def test_the_tint_patterns_catch_reformatted_and_respelled_css():
    """Guard the guard. Left column: spellings the exact substrings caught.
    Right: reformattings/respellings that slipped past them."""
    for pat, samples in (
            (_MIX_WIN, ["color-mix(in srgb,var(--matrix-win-bg) 40%,#fff)",
                        "color-mix(in srgb, var(--matrix-win-bg) 40%, #fff)",
                        "color-mix( in  srgb , var( --matrix-win-bg ) 40%)"]),
            (_FG_WIN, ["color:var(--matrix-win-fg)",
                       "color: var(--matrix-win-fg)",
                       "color : var( --matrix-win-fg )"]),
            (_LEGACY_RGB, ["background:rgba(57,135,229,.4)",
                           "background:rgb(57 135 229)",
                           "background: rgba( 230, 103, 103, 0.4 )"]),
            (_LEGACY_TRIPLE, ["rgba(57,135,229,.4)", "rgb(57 135 229)",
                              "rgba(230, 103, 103, .4)"]),
            (_TEXT_TOKEN_FILL, ["background:var(--win)", "color: var( --loss )",
                                "background:var(--win )"]),
    ):
        for s in samples:
            assert pat.search(s), (pat.pattern, s)
    # ...and the survivors must not be false-positived by the tokens that
    # legitimately ship: --matrix-win-fg is not --win.
    assert not _TEXT_TOKEN_FILL.search("color:var(--matrix-win-fg)")
    assert not _LEGACY_RGB.search("color-mix(in srgb,var(--matrix-win-bg) 40%)")


# ---------------------------------------------------------------------------
# retired surfaces (free source scan -- see the blob smoke test below)
# ---------------------------------------------------------------------------

# The alpha-overlay / cluster-gap experiment, retired 2026-07. These four
# ids/vars used to be asserted absent inside the 8.5s blob-gated render
# smoke, i.e. they cost the most and ran on exactly one machine. They are a
# pure source-text property, so they run everywhere for free now
# (2026-08-09 test-suite review, cost-hygiene rec 6).
_RETIRED_SURFACES = ("alpha-chk", "dd-alpha", "clusterGaps", "cluster-chk")

# Every file that contributes body to the rendered dive page. The blob smoke
# this replaced saw the whole page, so anything injected into it belongs here
# or the move is a coverage regression -- deep_dive_user_collection.js
# (injected at deep_dive.py:3043) and the two narrative emitters were missing
# from the first cut (2026-08-09 adversarial review).
_EMITTERS = ("deep_dive.py", "deep_dive_rendering.py", "deep_dive_engine.js",
             "deep_dive_matchup_clusters.py", "cmp_panels.js",
             "deep_dive_user_collection.js", "deep_dive_narrative.py",
             "patch_dive_species_narrative.py")


def _strings_only(path):
    """Source with comments removed, so PROSE naming a retired surface is
    not mistaken for the surface coming back (deep_dive.py:1661 is exactly
    such a comment). Python: keep only string literals. JS: strip // and
    /* */.
    """
    text = path.read_text()
    if path.suffix == ".py":
        # ast, not tokenize: since 3.12 an f-string body is FSTRING_MIDDLE,
        # not STRING, and this repo emits its HTML almost entirely from
        # f-strings -- a STRING-only filter would have scanned nothing that
        # matters. ast folds the literal chunks of a JoinedStr into
        # Constant nodes and drops comments, which is exactly the split
        # this scan wants.
        return "\n".join(
            n.value for n in ast.walk(ast.parse(text))
            if isinstance(n, ast.Constant) and isinstance(n.value, str))
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", text)


def test_retired_alpha_overlay_surfaces_stay_retired():
    for name in _EMITTERS:
        path = REPO_ROOT / "scripts" / name
        assert path.exists(), f"stale emitter list: {name}"
        body = _strings_only(path)
        # Anti-vacuity PER FILE, not as a total: a summed floor lets any one
        # emitter silently scan to zero while the others carry it
        # (2026-08-09 adversarial review). The smallest real emitter is a
        # few kB, so 1000 chars is comfortably below every live file.
        assert len(body) > 1000, (name, len(body))
        for dead in _RETIRED_SURFACES:
            assert dead not in body, (name, dead)
    # ...and the live replacement surfaces must still be findable by the
    # same scan, on both the Python and the JS side.
    assert "dd-matchup-clusters" in _strings_only(
        REPO_ROOT / "scripts" / "deep_dive_matchup_clusters.py")
    assert "dd-" in _strings_only(REPO_ROOT / "scripts" / "deep_dive_engine.js")


def test_the_retired_surface_scan_ignores_prose_but_not_code():
    """Guard the guard: a comment naming the retired surface is fine (that
    is documentation); a string literal or a JS identifier is not."""
    # deep_dive.py names clusterGaps in a COMMENT (:1661) -- that must not
    # read as a resurfacing, or the scan becomes un-landable.
    assert "clusterGaps" not in _strings_only(REPO_ROOT / "scripts" / "deep_dive.py")
    import types
    fake_py = types.SimpleNamespace(
        suffix=".py",
        read_text=lambda: ("# clusterGaps retired\n"
                           "X = 'dd-alpha'\n"
                           "Y = f'<input id=\"alpha-chk\" v={v}>'\n"))
    assert "dd-alpha" in _strings_only(fake_py)
    # f-string bodies MUST be scanned -- this repo emits its HTML from them.
    assert "alpha-chk" in _strings_only(fake_py)
    assert "clusterGaps" not in _strings_only(fake_py)
    fake_js = types.SimpleNamespace(
        suffix=".js",
        read_text=lambda: "// alpha-chk retired\nvar clusterGaps = 1;\n")
    assert "clusterGaps" in _strings_only(fake_js)
    assert "alpha-chk" not in _strings_only(fake_js)


def test_wr_cell_pairs_every_fill_with_its_text_color():
    """No tinted cell may inherit var(--text) over a saturated fill."""
    for wr in (0.0, 0.25, 0.5, 0.5001, 0.75, 1.0):
        cell = mc._wr_cell(wr)
        assert "color:var(--matrix-" in cell, (wr, cell)
        pct = re.search(r"var\(--matrix-\w+-bg\) (\d+)%", cell)
        if wr == 0.5:
            # exact tie: flat, un-ramped tie pair (matchup-web contract)
            assert "var(--matrix-tie-bg)" in cell and pct is None
        else:
            assert mc.WR_RAMP_MIN_PCT <= int(pct.group(1)) <= mc.WR_RAMP_MAX_PCT
    assert "--matrix-win-bg" in mc._wr_cell(1.0)
    assert "--matrix-loss-bg" in mc._wr_cell(0.0)


# --- WCAG AA at the ramp endpoints (docs/palette_governance.md section 3) ---

def _srgb(hexstr):
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb):
    def chan(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg, bg):
    lo, hi = sorted((_luminance(fg), _luminance(bg)))
    return (hi + 0.05) / (lo + 0.05)


def _over(fill, base, alpha):
    return tuple(round(f * alpha + b * (1 - alpha))
                 for f, b in zip(fill, base))


def _cell_paint(wr):
    """(fill token, alpha, text token) as the emitted cell actually paints.

    Unset ``color:`` means the cell inherits the page's var(--text) -- which
    is exactly the failure mode this guards, so it is modelled, not assumed
    away.
    """
    cell = mc._wr_cell(wr)
    ramp = re.search(r"background:color-mix\(in srgb,var\((--[\w-]+)\) "
                     r"(\d+)%, transparent\)", cell)
    flat = re.search(r"background:var\((--[\w-]+)\)", cell)
    txt = re.search(r"color:var\((--[\w-]+)\)", cell)
    fill, alpha = ((ramp.group(1), int(ramp.group(2)) / 100.0) if ramp
                   else (flat.group(1), 1.0))
    return fill, alpha, (txt.group(1) if txt else "--text")


def test_winrate_tint_clears_AA_at_both_ramp_endpoints():
    """The printed percentage must clear 4.5:1 in ALL FOUR themes, at both
    ends of the alpha ramp, over the .dd-section surface it composites on.

    Tokens are read back out of the emitted cell, so this fails if the
    renderer switches lanes -- which is what the first cut of the tint did:
    var(--win) / var(--loss) are outcome TEXT values, and using them as a
    55% fill under the inherited var(--text) gave 4.14 (win) / 3.53 (loss)
    in gruvbox-light, the DEFAULT theme.
    """
    from gopvpsim.theme import _THEME_ORDER, _TOKENS

    # ramp endpoints on both sides, plus the exact-tie cell
    for wr in (0.0, 0.4999, 0.5, 0.5001, 1.0):
        fill_tok, alpha, text_tok = _cell_paint(wr)
        for col, theme in enumerate(_THEME_ORDER):
            surface = _srgb(_TOKENS["--surface"][col])
            painted = _over(_srgb(_TOKENS[fill_tok][col]), surface, alpha)
            ratio = _contrast(_srgb(_TOKENS[text_tok][col]), painted)
            assert ratio >= 4.5, (theme, wr, fill_tok, text_tok,
                                  round(ratio, 2))


def test_winrate_ramp_matches_the_matchup_web_heatmap():
    """The ramp bounds are shared with build_matchup_web.py's cellStyle --
    the --matrix-*-fg values are AA-solved against exactly that ramp.

    They used to be hand-typed there as a JS literal and merely CHECKED for
    agreement here; build_matchup_web now imports them and injects them into
    the generated JS, so this guards the injection instead. The rendered
    bytes are unchanged: the template still formats to `(12 + 55 * t)`.
    """
    js = (REPO_ROOT / "scripts" / "build_matchup_web.py").read_text()
    assert re.search(r"from deep_dive_matchup_clusters import "
                     r"WR_RAMP_MIN_PCT,\s*WR_RAMP_MAX_PCT", js), \
        "matchup-web no longer imports the ramp bounds"
    assert "const pct = ({wr_min} + {wr_span} * t).toFixed(0);" in js
    assert not re.search(r"const pct = \(\d+ \+ \d+ \* t\)", js), \
        "ramp bounds re-typed as a JS literal"

    rendered = ("const pct = ({wr_min} + {wr_span} * t).toFixed(0);"
                .format(wr_min=mc.WR_RAMP_MIN_PCT,
                        wr_span=mc.WR_RAMP_MAX_PCT - mc.WR_RAMP_MIN_PCT))
    assert rendered == "const pct = (12 + 55 * t).toFixed(0);"


def test_in_page_note_quotes_the_module_constants(monkeypatch):
    p = mc.cluster_params()
    html = _render([])
    assert f'between {p["sharp_lo_pct"]}% and {p["sharp_hi_pct"]}%' in html
    assert f'{p["kmin"]}-{p["kmax"]} within {p["sil_epsilon"]}' in html
    # the note follows the constants, it does not restate them
    monkeypatch.setattr(mc, "SHARP_LO", 0.05)
    assert mc.cluster_params()["sharp_lo_pct"] == "5"
    assert "between 5% and 98%" in _render([])


def test_weak_separation_headline_follows_weak_sil(monkeypatch):
    # The HEADLINE form, not the phrase: "How this works" now defines the
    # flag ('below 0.30 the headline says "weak separation"') and so carries
    # the words on every page.
    flag = "- weak separation)"
    monkeypatch.setattr(mc, "WEAK_SIL", 1.5)     # everything reads as weak
    assert flag in _render([])
    monkeypatch.setattr(mc, "WEAK_SIL", 0.0)     # nothing does
    assert flag not in _render([])


# ---------------------------------------------------------------------------
# real-blob render smoke test (slow; skipped when no replay blobs exist)
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.local_artifacts
def test_render_smoke_from_real_blob(tmp_path):
    """Full render_dive_html pass on the smallest local replay blob: the
    section must be present, and the verify_overnight '"opponents": ['
    extraction contract must survive."""
    blobs = sorted((REPO_ROOT / "userdata" / "replay").glob("*.replay.pkl.gz"),
                   key=lambda p: p.stat().st_size)
    if not blobs:
        pytest.skip("no replay blobs on this machine")
    dd = load_deep_dive()
    state = dd.load_replay_state(str(blobs[0]))
    state["html_path"] = str(tmp_path / "index.html")
    state["card_path"] = None
    dd.render_dive_html(state)
    html = (tmp_path / "index.html").read_text()
    assert "matchup-clusters:v1" in html
    assert 'id="dd-matchup-clusters"' in html
    assert html.count('"opponents": [') == 1   # verify_overnight extraction
    # (the retired-surface denylist moved to the free source scan above --
    # it needed no blob, no render and no 8.5s, and it ran on one machine)


# ---------------------------------------------------------------------------
# Pinned reference values: Shadow Sableye GL, moveset 0, PvPoke opponent IVs
# ---------------------------------------------------------------------------
#
# The dive the all-scenario work came from (docs/scenario_clusters_plan.md).
# Pre-fix (through 2026-09-12) this section computed 0v0 / 1v1 / 2v2 only, so
# every number below except 1v1's was UNCOMPUTED, not different.
#
# Ks and root rules are pinned exactly -- they are discrete, load-bearing and
# quoted on the page. Silhouettes are pinned as FLOORS (a linkage tie-break
# can legitimately move the fourth decimal; see the module's fidelity note).

SABLEYE_SHADOW_BLOB = '20260911_005150_Sableye_great_shadow.replay.pkl.gz'


def _find_blob(name):
    """This clone's blob store, then the sibling main checkout's.

    A working clone shares the machine's replay blobs rather than
    duplicating them (same lookup as tests/test_deep_dive_brief.py).
    """
    for d in (REPO_ROOT / "userdata" / "replay",
              REPO_ROOT.parent / "gopvpsim" / "userdata" / "replay"):
        p = d / name
        if p.exists():
            return p
    return None


def _blob_cluster_run(name):
    import gzip
    import pickle
    path = _find_blob(name)
    if path is None:
        pytest.skip(f"{name} is not on this machine")
    with gzip.open(path, "rb") as f:
        st = pickle.load(f)
    m = st["moveset_data"][0]
    opps = st["opponent_names"]
    scen = [tuple(s) for s in st["shield_scenarios"]]
    flat = np.asarray(m["scores"]["pvpoke"], dtype=np.int32)
    nO, nS = len(opps), len(scen)
    nIvs = flat.size // (nS * nO)
    meta = np.array(m["meta"])
    # Rounded the way the PAGE rounds (deep_dive.py's DATA.ivAtk/ivDef), so
    # the thresholds pinned below are the ones a reader sees. Only the
    # 1v1 / all root moves: 148.67 unrounded, 148.68 as shipped.
    dp = mc.SECTION_STAT_DP
    return mc.compute_matchup_clusters(
        flat, nIvs, nS, nO, scen, np.round(meta[:, 5], dp),
        np.round(meta[:, 6], dp), meta[:, 7], no_anchors), nO


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_shadow_sableye_gl_reference_values():
    out, nO = _blob_cluster_run(SABLEYE_SHADOW_BLOB)
    assert list(out)[-1] == "all"

    # 0v1 -- the finding that motivated the whole change: the two bands on
    # the main scatter are one attack line (a CMP line against the default
    # Annihilape), at a HIGHER silhouette than the even scenarios carry.
    e = out["0v1"]
    assert e["res"]["k"] == 2
    assert e["res"]["silhouette"] >= 0.60             # measured 0.654
    assert e["root_rule"] == "atk < 148.06"
    assert e["root_split"] == "atk 148.06"
    assert e["cluster_rules"] == ["atk < 148.06", "atk >= 148.06"]
    assert e["res"]["clusters"][1]["size"] == 2220    # the upper band
    assert e["tree_acc"] == 1.0

    # 1v0 -- the five-band attack ladder. Its root separates no cluster
    # cleanly (tree accuracy 0.84), so NO cluster carries a legend rule:
    # before the iff tightening three of the five were named
    # "atk < 151.20", which is true of all three and identifies none.
    assert out["1v0"]["res"]["k"] == 5
    assert out["1v0"]["cluster_rules"] == [None] * 5
    assert out["1v0"]["root_split"] == "atk 151.20"

    # Both lopsided extremes fall under the degeneracy floor, and say why.
    two_v_zero = out["2v0"]
    assert two_v_zero["degenerate"] is True
    assert two_v_zero["n_sharp"] == 1
    assert f"of {nO} opponents here" in two_v_zero["reason"]
    assert "1 opponent is a sharp marginal" in two_v_zero["reason"]
    zero_v_two = out["0v2"]
    assert zero_v_two["degenerate"] is True
    assert (zero_v_two["n_sharp"], zero_v_two["n_patterns"]) == (5, 16)

    # The combined view. K matches the plan's A3 reading; the line does not
    # (the plan measured atk < 148.06 over ~118 bits in an offline run that
    # predates the degeneracy floor and included 0v2's 5 bits). With the
    # floor the concatenation is 113 bits over 7 scenarios and lands on the
    # 1v1 line. Both readings are recorded in the module comment beside the
    # exclusion; this pins what ships.
    a = out["all"]
    assert a["combined"]["n_bits"] == 113
    assert a["combined"]["excluded"] == ["0v2", "2v0"]
    assert len(a["combined"]["scens"]) == 7
    assert a["res"]["k"] == 2
    assert a["res"]["silhouette"] >= 0.43             # measured 0.451
    assert a["root_rule"] == "atk < 148.68"   # 148.67 on unrounded stats
    assert a["tree_acc"] >= 0.97                      # measured 0.983
    # bits are (scenario, opponent) pairs, and the flip table names both
    assert len(a["combined"]["bit_scen"]) == a["combined"]["n_bits"]
    assert len(a["flips"]) == a["combined"]["n_bits"]


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_combined_bits_are_ordered_most_discriminating_first():
    """The combined column order is a CHOSEN tie-break, not an accident.

    Hamming distance is permutation-invariant in the columns, so the order
    cannot move a point -- but it sets ``np.unique``'s lexicographic order
    of the unique patterns, which is the linkage tie-break, and on this grid
    that moves K. Pinned two ways: the shipped order is |wr - 0.5| ascending
    (what ``sharp_marginals`` hands every per-scenario entry), and the raw
    grid order it replaced really does give a different answer here, so a
    silent revert to collection order cannot pass.
    """
    import gzip
    import pickle
    path = _find_blob(SABLEYE_SHADOW_BLOB)
    if path is None:
        pytest.skip(f"{SABLEYE_SHADOW_BLOB} is not on this machine")
    with gzip.open(path, "rb") as f:
        st = pickle.load(f)
    m = st["moveset_data"][0]
    scen = [tuple(x) for x in st["shield_scenarios"]]
    nO, nS = len(st["opponent_names"]), len(scen)
    flat = np.asarray(m["scores"]["pvpoke"], dtype=np.int32)
    nIvs = flat.size // (nS * nO)
    meta = np.array(m["meta"])
    dp = mc.SECTION_STAT_DP
    atk, dfn, hp = np.round(meta[:, 5], dp), np.round(meta[:, 6], dp), meta[:, 7]

    ws = [(mc.scenario_label(p), mc.win_matrix(flat, nIvs, nS, nO, i))
          for i, p in enumerate(scen)]
    cf = mc.concat_fingerprint(ws)
    W = cf["W"]
    assert W.shape[1] == 113

    # (a) the shipped order is sharpest-first, ties stable
    sharpness = np.abs(W.mean(axis=0) - 0.5)
    assert np.all(np.diff(sharpness) >= -1e-12), "columns are not sharpest-first"

    # (b) it is load-bearing: collection order answers differently
    cols = []
    for lbl, Wi in ws:
        sharp, _wr, _ns, _np_, degen = mc.screen_scenario(Wi)
        if not degen:
            cols.append(Wi[:, sharp])
    grid = np.hstack(cols).astype(np.uint8)
    assert grid.shape == W.shape
    k_ship, lab_ship, sil_ship, _ = mc.choose_k(W.astype(np.uint8))
    k_grid, lab_grid, sil_grid, _ = mc.choose_k(grid)
    assert (k_ship, k_grid) == (2, 3)                 # measured
    assert sil_ship > sil_grid                        # 0.451 vs 0.395
    acc_ship, _ = mc.stat_rules({"k": k_ship, "labels": lab_ship}, atk, dfn, hp)
    acc_grid, _ = mc.stat_rules({"k": k_grid, "labels": lab_grid}, atk, dfn, hp)
    assert acc_ship > acc_grid                        # 0.983 vs 0.961


def test_signpost_names_the_sharpest_single_scenarios_with_their_size():
    """The combined block points at the page's cleanest SINGLE partitions.

    The combined view is the default and is routinely the least separated
    one, so without this the page's best result is an unlabelled click away.
    "Sharpest" is comparative and a silhouette rises as fingerprints get
    shorter, so each entry carries the marginal count it was measured over.
    """
    flat, nIvs, nO = staircase_scores(scen_idx=4)
    arr = np.array(flat, dtype=np.int32).reshape(nIvs, 9, nO)
    arr[:, 8, :] = arr[:, 4, :]
    arr[:, 0, :] = arr[:, 4, :]
    atk = np.linspace(100, 110, nIvs)
    computed = mc.compute_matchup_clusters(
        arr.ravel().tolist(), nIvs, 9, nO, SCENARIOS9, atk, atk, atk,
        no_anchors)
    line = mc._sharpest_signpost(computed)
    assert line.startswith("<p")
    assert "Sharpest single scenarios" in line
    # names real, clustered, NON-combined scenarios, best silhouette first
    # highest silhouette first, ties broken by label -- the function's order
    ranked = sorted(((e["res"]["silhouette"], lbl) for lbl, e
                     in computed.items()
                     if "res" in e and lbl != mc.ALL_SCEN_KEY),
                    key=lambda t: (-t[0], t[1]))
    assert mc.ALL_SCEN_DISPLAY not in line
    assert mc._scen_display(ranked[0][1]) in line
    assert line.index(mc._scen_display(ranked[0][1])) < \
        line.index(mc._scen_display(ranked[1][1]))
    # ... with K, the silhouette and the count it was measured over
    top = computed[ranked[0][1]]
    assert f'K={top["res"]["k"]}' in line
    assert f'silhouette {ranked[0][0]:.2f} over {len(top["res"]["sharp"])} ' \
        'sharp marginal' in line
    # and it only appears in the combined block
    html = mc.render_section(
        arr.ravel().tolist(), nIvs, 9, nO, SCENARIOS9,
        [f"Opp{i}" for i in range(nO)],
        {"ivAtk": atk.tolist(), "ivDef": atk.tolist(),
         "ivHp": atk.tolist()}, "rank-1", "FAST / CM", [])
    assert html.count("Sharpest single scenarios") == 1


def test_root_rule_is_emitted_only_when_the_split_is_an_iff():
    """A legend NAME is read as a definition, so only an iff may be one.

    Three clusters split by two attack lines: the root separates the top
    cluster exactly (every member above it, nothing else above it) and is
    merely NECESSARY for the other two (both lie below it). Before the
    tightening both of those were named "atk < T" -- one rule, two clusters,
    identifying neither. Only the iff side is named now.
    """
    n = 300
    atk = np.linspace(100.0, 130.0, n)
    flat = np.full(n, 0)
    labels = np.zeros(n, dtype=int)
    labels[atk >= 110.0] = 1
    labels[atk >= 120.0] = 2
    res = {"k": 3, "labels": labels}
    root, per, split = mc.root_rules(res, atk, atk, atk, min_leaf=10)
    assert root is not None and split is not None
    assert root.startswith("atk < ") and split.startswith("atk ")
    assert split == root.replace(" < ", " ")
    # exactly one cluster is an iff for the root split; the other two share
    # the other side and so are left unnamed
    named = [i for i, r in enumerate(per) if r]
    assert len(named) == 1, per
    thr = float(root.split("< ")[1])
    rule = per[named[0]]
    # the named cluster IS its side of the root, exactly
    side = atk < thr if rule.startswith("atk < ") else atk >= thr
    assert np.array_equal(side, labels == named[0])
    # sanity: the two unnamed ones share the OTHER side, which is why
    # neither can wear that side's rule as a name
    for c in range(3):
        if c != named[0]:
            assert (~side[labels == c]).all()


def test_section_stat_dp_matches_what_the_page_actually_bakes():
    """The section's tree is fitted on DATA.ivAtk/ivDef, which deep_dive.py
    rounds. SECTION_STAT_DP exists so a consumer quoting the section's split
    (the build brief's corroboration line) can round the same way; if
    deep_dive.py changes places, the two drift by a cent with nothing to
    catch it.

    Tolerant pattern plus a positive control: a rename of ``meta``/``m`` is
    not a contract change, a change of PLACES is.
    """
    src = (REPO_ROOT / "scripts" / "deep_dive.py").read_text()
    dp = mc.SECTION_STAT_DP
    for stat in ("iv_atk", "iv_def"):
        m = re.search(r"%s\s*=\s*\[\s*round\([^,]+,\s*(\d+)\s*\)" % stat, src)
        assert m, f"{stat} is no longer a rounded comprehension; re-pin this"
        assert int(m.group(1)) == dp, (stat, m.group(1), dp)


# ---------------------------------------------------------------------------
# Per-preset combined partitions (2026-09-16, the Build criteria knob)
# ---------------------------------------------------------------------------

_PRESETS = [('flat', 'all shields, equal', None),
            ('even', 'even shields', ('0v0', '1v1', '2v2')),
            ('one_one', '1v1 only', ('1v1',))]


def _render_with_presets():
    flat, nIvs, nO = staircase_scores(n_opp=len(OPP_NAMES))
    atk = np.linspace(100, 110, nIvs)
    data_obj = {"ivAtk": atk.tolist(), "ivDef": atk.tolist(),
                "ivHp": np.full(nIvs, 135.0).tolist()}
    return mc.render_section(
        flat, nIvs, 9, nO, SCENARIOS9, OPP_NAMES, data_obj,
        "rank-1", "Shadow Claw/Foul Play+Power Gem", [], presets=_PRESETS)


def test_a_preset_partition_gets_its_own_key_and_display_name():
    assert mc.all_scen_key() == mc.ALL_SCEN_KEY
    assert mc.all_scen_key('flat') == mc.ALL_SCEN_KEY
    assert mc.all_scen_key('even') == 'all__even'
    assert mc.is_all_scen_key('all__even') and mc.is_all_scen_key('all')
    assert not mc.is_all_scen_key('1v1')
    _render_with_presets()          # fills the preset-tag table
    assert mc._scen_display('all__even') == 'all scenarios (even shields)'


def test_a_single_scenario_preset_resolves_to_that_scenarios_partition():
    """The 1v1-only preset has nothing to combine, so its "all scenarios"
    view IS the 1v1 partition -- never the nine-scenario one under a label
    claiming otherwise."""
    html = _render_with_presets()
    pay = json.loads(re.search(
        r'<script type="application/json" class="dd-mc-data">(.*?)</script>',
        html, re.S).group(1))
    assert pay['allByPreset']['flat'] == mc.ALL_SCEN_KEY
    assert pay['allByPreset']['even'] == 'all__even'
    assert pay['allByPreset']['one_one'] == '1v1'
    assert pay['allLabelByPreset']['one_one'] == '1v1 shields'
    for key, mapped in pay['allByPreset'].items():
        assert mapped in pay['scens'], (key, mapped)


def test_a_preset_block_prints_its_own_clusters_and_says_what_it_omits():
    """The short form is a size decision, so the omission must be stated.

    Printing the default view's per-bit win-rate grid under a different
    partition's clusters would be the dishonest way to save the bytes; this
    pins that the block carries its own cluster table and its own rules, and
    a sentence saying where the omitted tables are.
    """
    html = _render_with_presets()

    def _block(scen):
        i = html.index(f'<div class="dd-mc-scen-block" data-scen="{scen}" ')
        nxt = html.find('<div class="dd-mc-scen-block"', i + 10)
        end = nxt if nxt > 0 else html.index('How this works', i)
        return html[i:end]

    block = _block('all__even')
    assert 'Cluster' in block            # its own cluster table
    assert 'Depth-3 decision tree' in block      # its own stat rules
    assert "Build criteria preset's own combined partition" in block
    assert 'are not repeated here' in block
    # the two heavy tables are NOT in it
    assert 'Matchup flip thresholds' not in block
    assert 'Green tint = the cluster mostly wins' not in block
    # positive control: the DEFAULT combined block still carries both
    full = _block('all')
    assert 'Matchup flip thresholds' in full
    assert 'Green tint = the cluster mostly wins' in full


def test_preset_partitions_do_not_become_dropdown_options():
    html = _render_with_presets()
    opts = re.findall(r'<option value="([^"]+)"', html)
    assert mc.ALL_SCEN_KEY in opts
    assert 'all__even' not in opts
    # but it does get a block, so the option can select it
    assert 'data-scen="all__even"' in html
