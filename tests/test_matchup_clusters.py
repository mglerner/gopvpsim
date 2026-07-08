"""Unit tests for scripts/deep_dive_matchup_clusters.py (pure-numpy pipeline).

Synthetic-data tests: planted cluster structure, determinism, the parsimony
floor, single-stat flip directions, tree rule extraction, degenerate inputs.
"""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

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


def no_anchors(opp_idx, stat):
    return None


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


def test_compute_matchup_clusters_end_to_end():
    flat, nIvs, nO = planted_scores(
        [100, 100], [[1, 1, 0, 0], [1, 1, 1, 1]], scen_idx=4)
    atk = np.linspace(100, 110, nIvs)
    out = mc.compute_matchup_clusters(
        flat, nIvs, 9, nO, SCENARIOS9, atk, atk[::-1].copy(),
        np.full(nIvs, 135.0), no_anchors)
    assert set(out) <= {"0v0", "1v1", "2v2"}
    r = out["1v1"]
    assert r["res"]["k"] == 2
    assert len(r["flips"]) == 2          # opponents 2,3 sharp; 0,1 settled
    assert all(row["named"] is None for row in r["flips"])
    # 0v0 has zero sharp marginals -> honest reason, no clusters
    assert "reason" in out["0v0"]


def test_compute_handles_missing_scenarios():
    # dive run with a single scenario: only that pair is computable
    flat, nIvs, nO = planted_scores([50, 50], [[0, 0], [1, 1]],
                                    nS=1, scen_idx=0)
    atk = np.linspace(100, 110, nIvs)
    out = mc.compute_matchup_clusters(
        flat, nIvs, 1, nO, [(1, 1)], atk, atk, atk, no_anchors)
    assert list(out) == ["1v1"]
    assert out["1v1"]["res"]["k"] == 2


def test_all_settled_scenario_reports_reason():
    flat, nIvs, nO = planted_scores([100], [[1, 0, 1]], scen_idx=4)
    atk = np.linspace(100, 110, nIvs)
    out = mc.compute_matchup_clusters(
        flat, nIvs, 9, nO, SCENARIOS9, atk, atk, atk, no_anchors)
    assert out["1v1"]["n_sharp"] == 0
    assert "reason" in out["1v1"]


# ---------------------------------------------------------------------------
# real-blob render smoke test (slow; skipped when no replay blobs exist)
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_render_smoke_from_real_blob(tmp_path):
    """Full render_dive_html pass on the smallest local replay blob: the
    section must be present, and the verify_overnight '"opponents": ['
    extraction contract must survive."""
    blobs = sorted((REPO_ROOT / "userdata" / "replay").glob("*.replay.pkl.gz"),
                   key=lambda p: p.stat().st_size)
    if not blobs:
        pytest.skip("no replay blobs on this machine")
    dd_spec = importlib.util.spec_from_file_location(
        "deep_dive", REPO_ROOT / "scripts" / "deep_dive.py")
    dd = importlib.util.module_from_spec(dd_spec)
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        dd_spec.loader.exec_module(dd)
        state = dd.load_replay_state(str(blobs[0]))
        state["html_path"] = str(tmp_path / "index.html")
        state["card_path"] = None
        dd.render_dive_html(state)
    finally:
        sys.path.remove(str(REPO_ROOT / "scripts"))
    html = (tmp_path / "index.html").read_text()
    assert "matchup-clusters:v1" in html
    assert 'id="dd-matchup-clusters"' in html
    assert html.count('"opponents": [') == 1   # verify_overnight extraction
    # retired surfaces must not resurface
    for dead in ("alpha-chk", "dd-alpha", "clusterGaps", "cluster-chk"):
        assert dead not in html, dead
