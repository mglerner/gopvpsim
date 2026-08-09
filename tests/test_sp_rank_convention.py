"""DATA.spRanks must use PvPoke's stat-product rank convention (js-parity-3).

The dive baked ``spRanks`` by sorting the 0.1-ROUNDED display array
``ivSp`` with no explicit tiebreak, so ties (real ones, and fake ones
manufactured by the rounding) fell to enumeration order -- the LOWEST
a/d/s spread won. The same page's off-grid column reads
``DATA.collection.rankLookup``, built from ``gopvpsim.pokemon.iv_rank``,
which ranks on the UNROUNDED stat product and breaks ties by IV sum
DESCENDING (PvPoke's convention). One column, two conventions:
Medicham great disagreed on 1354/4096 spreads and the rank-1 marker sat
on 5/15/14 instead of iv_rank's 5/15/15.

``deep_dive.sp_rank_array`` is the extracted, correct ranker; these
tests pin the tiebreak, the parity with ``compute_rank_lookup``, and the
``rank1RefIvIdx`` derivation that the narrative's rank-1 self-check and
the two-#1s explainer read.
"""
import sys

from tests.conftest import load_deep_dive, SCRIPTS_DIR

deep_dive = load_deep_dive()

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from deep_dive_lib.sweep import compute_iv_metadata          # noqa: E402
from gopvpsim.user_collection import compute_rank_lookup     # noqa: E402


def _meta_tuple(a, d, s, atk, def_, hp):
    """A canonical_meta row: (atk_iv, def_iv, sta_iv, level, cp, atk, def, hp)."""
    return (a, d, s, 50.0, 1500, atk, def_, hp)


# ---------------------------------------------------------------------------
# 1. Unit: the two things the old sort key got wrong
# ---------------------------------------------------------------------------

def test_true_stat_product_tie_breaks_toward_higher_iv_sum():
    # The Medicham 5/15/15 vs 5/15/14 shape: floor()-ed HP makes the stat
    # products exactly equal, so the tiebreak decides. PvPoke (and iv_rank)
    # prefer the higher IV sum; enumeration order would have picked 5/15/14.
    meta = [
        _meta_tuple(5, 15, 14, 100.0, 110.0, 130),
        _meta_tuple(5, 15, 15, 100.0, 110.0, 130),
    ]
    assert deep_dive.sp_rank_array(meta) == [2, 1]


def test_sub_tenth_stat_product_difference_is_not_a_tie():
    # A stat-product gap smaller than 0.05 is real but vanishes under
    # round(sp, 1), so the old path saw a tie and took enumeration order
    # (index 0 first) -- the exact inversion this file exists to prevent.
    # `lo` deliberately carries the HIGHER IV sum, so an implementation that
    # rounded first and then applied the IV-sum tiebreak would rank it first
    # and fail here -- this test pins the UNROUNDED half of the contract.
    lo = _meta_tuple(15, 15, 15, 100.0, 110.0, 130)
    hi = _meta_tuple(0, 0, 0, 100.0, 110.000000002, 130)
    sp_lo = lo[5] * lo[6] * lo[7]
    sp_hi = hi[5] * hi[6] * hi[7]
    assert sp_hi > sp_lo                       # truth: hi is strictly better
    assert round(sp_lo, 1) == round(sp_hi, 1)  # old path: indistinguishable
    # Old key, spelled out: round(sp, 1) with no tiebreak, stable sort.
    old = sorted(range(2), key=lambda i: round(sp_lo if i == 0 else sp_hi, 1),
                 reverse=True)
    assert old == [0, 1]                       # old path ranks `lo` first
    assert deep_dive.sp_rank_array([lo, hi]) == [2, 1]


def test_ranks_are_a_permutation_of_1_to_n():
    meta = [_meta_tuple(a, 0, 0, 100.0 + a, 110.0, 130) for a in range(16)]
    assert sorted(deep_dive.sp_rank_array(meta)) == list(range(1, 17))


def test_empty_meta_returns_empty():
    assert deep_dive.sp_rank_array([]) == []


# ---------------------------------------------------------------------------
# 2. Integration: the actual contract -- DATA.spRanks vs DATA.collection.rankLookup
# ---------------------------------------------------------------------------

def _assert_grid_parity(species, league):
    meta = [(m['atk_iv'], m['def_iv'], m['sta_iv'], m['level'], m['cp'],
             m['atk'], m['def_'], m['hp'])
            for m in compute_iv_metadata(species, league)]
    ranks = deep_dive.sp_rank_array(meta)
    lookup = compute_rank_lookup(species, league=league)
    assert len(meta) == len(lookup), f'{species}: grid size differs from iv_rank'
    mismatches = [(m[0], m[1], m[2], r, lookup[(m[0], m[1], m[2])])
                  for m, r in zip(meta, ranks)
                  if lookup[(m[0], m[1], m[2])] != r]
    assert not mismatches, (
        f'{species} {league}: {len(mismatches)}/{len(meta)} spreads rank '
        f'differently on the page than in rankLookup; first: {mismatches[:3]}')


def test_medicham_great_grid_matches_rank_lookup():
    # 1354/4096 mismatched before the fix (max delta 4).
    _assert_grid_parity('Medicham', 'great')


def test_talonflame_ultra_grid_matches_rank_lookup():
    # 1954/4096 mismatched before the fix (max delta 5).
    _assert_grid_parity('Talonflame', 'ultra')


def test_rank1_spread_matches_iv_rank_rank1():
    # The marker itself, not just the column: pre-fix this was 5/15/14.
    meta = [(m['atk_iv'], m['def_iv'], m['sta_iv'], m['level'], m['cp'],
             m['atk'], m['def_'], m['hp'])
            for m in compute_iv_metadata('Medicham', 'great')]
    ranks = deep_dive.sp_rank_array(meta)
    lookup = compute_rank_lookup('Medicham', league='great')
    ours = meta[min(range(len(meta)), key=lambda i: ranks[i])][:3]
    theirs = next(k for k, v in lookup.items() if v == 1)
    assert ours == theirs


# ---------------------------------------------------------------------------
# 3. Guard: rank1RefIvIdx is derived from the same array
# ---------------------------------------------------------------------------

def test_rank1_ref_iv_idx_derivation_points_at_rank_1():
    # Mirrors deep_dive.py's `min(range(n), key=lambda i: sp_ranks[i])`
    # (both the L50 site and the L51 twin). This pins the index the
    # narrative rank-1 self-check and render.py's two-#1s explainer read.
    meta = [
        _meta_tuple(0, 0, 0, 100.0, 110.0, 120),
        _meta_tuple(5, 15, 14, 101.0, 111.0, 130),
        _meta_tuple(5, 15, 15, 101.0, 111.0, 130),
    ]
    ranks = deep_dive.sp_rank_array(meta)
    idx = min(range(len(meta)), key=lambda i: ranks[i])
    assert ranks[idx] == 1
    assert meta[idx][:3] == (5, 15, 15)
