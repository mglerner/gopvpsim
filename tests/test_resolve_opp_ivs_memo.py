"""The process-local memo on ``deep_dive_lib.opponents.resolve_opp_ivs``
(perf plan R1, docs/perf/2026-09-25_bake_attribution_and_cruft_scout.md).

The rank1 branch is a full 4096-combo ``iv_rank`` (63-76 ms) that used to
run for every opponent on every rank-1 sweep and on every rendered split
file. These tests pin that the memo (a) returns exactly what the direct
``_resolve_opp_ivs_uncached`` computation returns, (b) does not recompute on
a repeat call, including composite mode strings that share the base mode,
(c) keys on shadow, (d) is dropped by ``gopvpsim.invalidate_caches()`` so a
MOCK_GAMEMASTER swap (the ``mock_gm`` fixture) cannot leak a stale entry,
and (e) is the ONE function every consumer (sweep, render, deep_dive shim)
calls.

The no-CACHE_VERSION-bump argument rests on output identity: the slow
parity test checks memo == direct over both real opponent pools, both
modes, both shadow states, and the column-key test checks the sweep-cache
column key built from a memoized value is byte-identical to one built from
the direct value.
"""
from pathlib import Path

import pytest

import gopvpsim
from tests.conftest import load_deep_dive
from gopvpsim.pokemon import Pokemon, get_pokemon_entry, iv_rank

dd = load_deep_dive()
# scripts/ is on sys.path now.
from deep_dive_lib import opponents, render, sweep  # noqa: E402
import sweep_cache  # noqa: E402

POOLS_DIR = Path(__file__).resolve().parents[1] / 'opponent_pools'


@pytest.fixture
def counted(monkeypatch):
    """Empty memo + a call counter on the direct computation it wraps."""
    calls = []
    real = opponents._resolve_opp_ivs_uncached

    def _counting(*a):
        calls.append(a)
        return real(*a)

    monkeypatch.setattr(opponents, '_resolve_opp_ivs_uncached', _counting)
    opponents._resolve_opp_ivs_cache_clear()
    yield calls
    opponents._resolve_opp_ivs_cache_clear()


def test_every_consumer_calls_the_memoized_function():
    # Identity, not import-line text: the sweep's opp_cache builder, the
    # render path and the deep_dive shim all bind the memoized function.
    for mod in (dd, sweep, render):
        assert mod.resolve_opp_ivs is opponents.resolve_opp_ivs, mod.__name__


# Real opponents in each shadow state, both opp-IV base modes.
OPPS = [('Azumarill', 'great', False), ('Raikou', 'ultra', False),
        ('Raikou', 'ultra', True), ('Ninetales', 'great', True)]


@pytest.mark.parametrize('mode', ['rank1', 'pvpoke'])
def test_memo_matches_direct_call_and_does_not_recompute(counted, mode):
    for sp, lg, sh in OPPS:
        got = opponents.resolve_opp_ivs(sp, lg, sh, mode)
        assert type(got) is tuple and len(got) == 3
        assert all(type(v) is int and 0 <= v <= 15 for v in got)
    assert len(counted) == len(OPPS)
    # Repeat calls -- bare and composite (bait/energy tags are stripped, so
    # they share the base-mode entry) -- are all hits and equal the direct
    # computation. The counter is read BEFORE the direct comparison calls.
    for sp, lg, sh in OPPS:
        for m in (mode, f'{mode}:nobait', f'{mode}:nobait:e1', f'{mode}:e2'):
            before = len(counted)
            got = opponents.resolve_opp_ivs(sp, lg, sh, m)
            assert len(counted) == before, f'memo recomputed on {m!r}'
            assert got == tuple(
                opponents._resolve_opp_ivs_uncached(sp, lg, sh, mode))
    assert len(opponents._RESOLVE_OPP_IVS_MEMO) == len(OPPS)


def test_composite_mode_first_call_shares_base_entry(counted):
    """A composite mode seen FIRST fills the base-mode entry, and the bare
    mode then hits it (a raw-mode-string key would recompute here)."""
    opponents.resolve_opp_ivs('Azumarill', 'great', False, 'rank1:nobait:e1')
    opponents.resolve_opp_ivs('Azumarill', 'great', False, 'rank1')
    opponents.resolve_opp_ivs('Azumarill', 'great', 0, 'rank1:e2')
    assert len(counted) == 1
    assert list(opponents._RESOLVE_OPP_IVS_MEMO) == [
        ('Azumarill', 'great', False, 'rank1')]


def test_memo_keys_on_shadow_and_mode(counted):
    # Known-divergent shadow defaults (tests/test_shadow_pvpoke_default_ivs.py).
    assert opponents.resolve_opp_ivs('Raikou', 'ultra', False, 'pvpoke') == (5, 13, 13)
    assert opponents.resolve_opp_ivs('Raikou', 'ultra', True, 'pvpoke') == (8, 7, 14)
    r1 = iv_rank('Raikou', league='ultra', shadow=True)[0]
    assert opponents.resolve_opp_ivs('Raikou', 'ultra', True, 'rank1') == (
        r1['atk_iv'], r1['def_iv'], r1['sta_iv'])
    assert len(counted) == 3


def test_invalidate_caches_drops_the_memo(counted):
    opponents.resolve_opp_ivs('Azumarill', 'great', False, 'rank1')
    assert opponents._RESOLVE_OPP_IVS_MEMO
    assert opponents._resolve_opp_ivs_cache_clear in gopvpsim._EXTRA_INVALIDATORS
    gopvpsim.invalidate_caches()
    assert opponents._RESOLVE_OPP_IVS_MEMO == {}


def test_mock_gamemaster_swap_cannot_serve_stale_entry(mock_gm):
    """Under MOCK_GAMEMASTER the memo resolves the fake species from the fake
    data; invalidate_caches() (the fixture's teardown) drops it again."""
    r1 = iv_rank('Testmon', league='great')[0]
    got = opponents.resolve_opp_ivs('Testmon', 'great', False, 'rank1')
    assert got == (r1['atk_iv'], r1['def_iv'], r1['sta_iv'])
    assert ('Testmon', 'great', False, 'rank1') in opponents._RESOLVE_OPP_IVS_MEMO
    gopvpsim.invalidate_caches()
    assert opponents._RESOLVE_OPP_IVS_MEMO == {}


def test_column_key_identical_from_memoized_and_direct_ivs():
    """The opponent-IV part of a sweep-cache column key: the opp_cache
    builder (deep_dive_lib/sweep.py) feeds resolve_opp_ivs's tuple into
    Pokemon.at_best_level (-> 'level') and column_key_fields (-> 'ivs').
    Both must come out byte-identical whether the IVs came from the memo
    or the direct computation."""
    sp, lg, sh, mode = 'Raikou', 'ultra', True, 'rank1'
    fast, charged = 'VOLT_SWITCH', ['WILD_CHARGE', 'SHADOW_BALL']
    opponents._resolve_opp_ivs_cache_clear()
    opponents.resolve_opp_ivs(sp, lg, sh, mode)            # fill
    memo_ivs = opponents.resolve_opp_ivs(sp, lg, sh, mode)  # served
    assert memo_ivs is opponents._RESOLVE_OPP_IVS_MEMO[(sp, lg, sh, mode)]
    direct_ivs = opponents._resolve_opp_ivs_uncached(sp, lg, sh, mode)
    opponents._resolve_opp_ivs_cache_clear()

    def _key(ivs):
        oa, od, os_ = ivs
        lvl = Pokemon.at_best_level(sp, oa, od, os_, league=lg, shadow=sh).level
        fields = sweep_cache.column_key_fields(sp, sh, (oa, od, os_), lvl,
                                               fast, charged)
        return fields, sweep_cache._key_hash(fields)

    (f_memo, h_memo), (f_direct, h_direct) = _key(memo_ivs), _key(direct_ivs)
    assert f_memo == f_direct and h_memo == h_direct
    assert f_memo['ivs'] == list(direct_ivs)


def _pool_species(pool_file):
    """Unique base species from a pool file, parsed the way deep_dive.py's
    --opponents-file loader does (moveset overrides and ' (Shadow)' collapse
    onto the base species; the shadow axis is enumerated separately)."""
    out = []
    for raw in (POOLS_DIR / pool_file).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        _display, base, _is_shadow, _f, _c = opponents._parse_opponent_pool_line(line)
        if base not in out:
            out.append(base)
    return out


def _has_shadow_form(species):
    try:
        get_pokemon_entry(f'{species} (Shadow)')
        return True
    except KeyError:
        return False


def _parity_cases():
    """(species, league, shadow, mode) over both real pools x both modes x
    the shadow states each species has."""
    cases = []
    for pool_file, league in (('gl_top50_plus_cs.txt', 'great'),
                              ('ul_top60.txt', 'ultra')):
        for base in _pool_species(pool_file):
            shadows = (False, True) if _has_shadow_form(base) else (False,)
            for sh in shadows:
                for mode in ('rank1', 'pvpoke'):
                    cases.append((base, league, sh, mode))
    return cases


@pytest.mark.slow
def test_parity_over_real_opponent_pools(monkeypatch):
    """PARITY PROOF (the no-CACHE_VERSION-bump argument): over every species
    in both real pools, both modes, and both shadow states where a shadow
    form exists, the memoized value equals the direct computation, and a
    second pass is served from the dict (the direct computation is replaced
    by a raiser, and each returned object IS the stored entry). Variants the
    direct computation cannot resolve are skipped, with a small ceiling."""
    opponents._resolve_opp_ivs_cache_clear()
    cases, skipped = [], []
    for base, league, sh, mode in _parity_cases():
        try:
            direct = opponents._resolve_opp_ivs_uncached(base, league, sh, mode)
        except (KeyError, ValueError) as e:
            skipped.append((base, league, sh, mode, repr(e)))
            continue
        got = opponents.resolve_opp_ivs(base, league, sh, mode)
        assert got == tuple(direct), (base, league, sh, mode)
        cases.append((base, league, sh, mode))
    # Floors below today's counts (2026-09-26: 306 cases, 0 skipped --
    # GL 58 species, 25 with a shadow form; UL 46 species, 24 with one).
    assert len(cases) >= 280, (len(cases), skipped)
    assert len(skipped) <= 5, skipped
    assert any(c[2] for c in cases) and any(not c[2] for c in cases)
    assert {c[3] for c in cases} == {'rank1', 'pvpoke'}

    def _boom(*a):
        raise AssertionError(f'memo recomputed {a}')
    monkeypatch.setattr(opponents, '_resolve_opp_ivs_uncached', _boom)
    for base, league, sh, mode in cases:
        got = opponents.resolve_opp_ivs(base, league, sh, f'{mode}:nobait')
        assert got is opponents._RESOLVE_OPP_IVS_MEMO[(base, league, sh, mode)]
    opponents._resolve_opp_ivs_cache_clear()
