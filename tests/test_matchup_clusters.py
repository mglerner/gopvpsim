"""Unit tests for scripts/deep_dive_matchup_clusters.py (pure-numpy pipeline).

Synthetic-data tests: planted cluster structure, determinism, the parsimony
floor, single-stat flip directions, tree rule extraction, degenerate inputs.
"""
import importlib.util
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
    assert src.count("patterns[None, :, :]") == 1, (
        "the pairwise-distance expression was re-inlined; call _hamming()")


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

OPP_NAMES = ["Sableye", "Sableye (Shadow)", "Sableye (Bug Bite)"]


def _render(anchor_names):
    """Render a 100-IV / 3-opponent section; every opponent is sharp."""
    flat, nIvs, nO = planted_scores(
        [50, 50], [[0, 0, 0], [1, 1, 1]], scen_idx=4)
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


def test_winrate_tint_uses_theme_matrix_tokens():
    html = _render(["Sableye"])
    # the matchup-web heatmap lane: fill-role token + its PAIRED text color
    assert "color-mix(in srgb,var(--matrix-win-bg)" in html
    assert "color-mix(in srgb,var(--matrix-loss-bg)" in html
    assert "color:var(--matrix-win-fg)" in html
    assert "color:var(--matrix-loss-fg)" in html
    # the old dark-only rgba triples must not come back
    assert "rgba(" not in html
    assert "57,135,229" not in html and "230,103,103" not in html
    # nor the outcome TEXT tokens used as a fill (fails AA, see governance s3)
    assert "var(--win)" not in html and "var(--loss)" not in html
    assert "Green tint" in html


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
    monkeypatch.setattr(mc, "WEAK_SIL", 1.5)     # everything reads as weak
    assert "weak separation" in _render([])
    monkeypatch.setattr(mc, "WEAK_SIL", 0.0)     # nothing does
    assert "weak separation" not in _render([])


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
    dd = load_deep_dive()
    state = dd.load_replay_state(str(blobs[0]))
    state["html_path"] = str(tmp_path / "index.html")
    state["card_path"] = None
    dd.render_dive_html(state)
    html = (tmp_path / "index.html").read_text()
    assert "matchup-clusters:v1" in html
    assert 'id="dd-matchup-clusters"' in html
    assert html.count('"opponents": [') == 1   # verify_overnight extraction
    # retired surfaces must not resurface
    for dead in ("alpha-chk", "dd-alpha", "clusterGaps", "cluster-chk"):
        assert dead not in html, dead
