"""The page-side opponent-IV memo in scripts/deep_dive.py (perf plan R1).

``_opp_link_data`` (the "Comparing builds" battle-link payload) resolves each
opponent's IVs once per opp-IV mode on EVERY split file. The rank1 branch is a
full 4096-combo ``iv_rank`` (63-76 ms), which cost ~1.7 h per bake before
``_memo_resolve_opp_ivs``. These tests pin that the memo (a) returns exactly
what the direct ``opponents.resolve_opp_ivs`` call returns, (b) does not
recompute on a repeat call, including a composite mode that shares the base
mode, (c) keys on shadow, and (d) is dropped by ``gopvpsim.invalidate_caches()``
so a MOCK_GAMEMASTER swap (the ``mock_gm`` fixture) cannot leak a stale entry.

Byte-identity of the rendered pages is proven separately by
scripts/replay_render_diff.py on the five baseline blobs.
"""
import pytest

import gopvpsim
from tests.conftest import load_deep_dive
from gopvpsim.pokemon import iv_rank

dd = load_deep_dive()
from deep_dive_lib import opponents  # noqa: E402  (scripts/ now on sys.path)


@pytest.fixture
def counted(monkeypatch):
    """Empty memo + a call counter on the resolver the memo delegates to."""
    calls = []
    real = opponents.resolve_opp_ivs

    def _counting(*a):
        calls.append(a)
        return real(*a)

    monkeypatch.setattr(dd, 'resolve_opp_ivs', _counting)
    dd._opp_link_ivs_cache_clear()
    yield calls
    dd._opp_link_ivs_cache_clear()


# Two real opponents (one shadow), both opp-IV base modes.
OPPS = [('Azumarill', 'great', False), ('Raikou', 'ultra', True)]


@pytest.mark.parametrize('mode', ['rank1', 'pvpoke'])
def test_memo_matches_direct_call_and_does_not_recompute(counted, mode):
    for sp, lg, sh in OPPS:
        direct = opponents.resolve_opp_ivs(sp, lg, sh, mode)
        assert len(direct) == 3 and all(0 <= v <= 15 for v in direct)
        assert dd._memo_resolve_opp_ivs(sp, lg, sh, mode) == tuple(direct)
    assert len(counted) == len(OPPS)
    # Repeat calls -- bare and composite (bait/energy tags are stripped by
    # resolve_opp_ivs itself, so they share the base-mode entry) -- are hits.
    for sp, lg, sh in OPPS:
        for m in (mode, f'{mode}:nobait', f'{mode}:nobait:e1'):
            assert dd._memo_resolve_opp_ivs(sp, lg, sh, m) == tuple(
                opponents.resolve_opp_ivs(sp, lg, sh, mode))
    assert len(counted) == len(OPPS), 'memo recomputed on a repeat call'


def test_memo_keys_on_shadow_and_mode(counted):
    # Known-divergent shadow defaults (tests/test_shadow_pvpoke_default_ivs.py).
    assert dd._memo_resolve_opp_ivs('Raikou', 'ultra', False, 'pvpoke') == (5, 13, 13)
    assert dd._memo_resolve_opp_ivs('Raikou', 'ultra', True, 'pvpoke') == (8, 7, 14)
    r1 = iv_rank('Raikou', league='ultra', shadow=True)[0]
    assert dd._memo_resolve_opp_ivs('Raikou', 'ultra', True, 'rank1') == (
        r1['atk_iv'], r1['def_iv'], r1['sta_iv'])
    assert len(counted) == 3


def test_invalidate_caches_drops_the_memo(counted):
    dd._memo_resolve_opp_ivs('Azumarill', 'great', False, 'rank1')
    assert dd._OPP_LINK_IVS_MEMO
    assert dd._opp_link_ivs_cache_clear in gopvpsim._EXTRA_INVALIDATORS
    gopvpsim.invalidate_caches()
    assert dd._OPP_LINK_IVS_MEMO == {}


def test_mock_gamemaster_swap_cannot_serve_stale_entry(mock_gm):
    """Under MOCK_GAMEMASTER the memo resolves the fake species from the fake
    data; the fixture's invalidate_caches() on teardown drops it again."""
    r1 = iv_rank('Testmon', league='great')[0]
    got = dd._memo_resolve_opp_ivs('Testmon', 'great', False, 'rank1')
    assert got == (r1['atk_iv'], r1['def_iv'], r1['sta_iv'])
    assert ('Testmon', 'great', False, 'rank1') in dd._OPP_LINK_IVS_MEMO
    gopvpsim.invalidate_caches()
    assert dd._OPP_LINK_IVS_MEMO == {}
