"""
Tests for gopvpsim.pokemon — stat calculation, CP, level, stat product.

Unit tests use a mock gamemaster (no network required).
Integration tests (marked 'integration') hit the real gamemaster and validate
against known PvPoke values — run with: pytest -m integration
"""
import math
import pytest

from gopvpsim.pokemon import (
    CPM, LEAGUE_CAPS, _LEVELS,
    cp, battle_stats, stat_product, best_level,
    get_species, Pokemon, iv_rank,
    SHADOW_ATK_BONUS, SHADOW_DEF_MULT,
)
from tests.conftest import FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA


# ===========================================================================
# CPM table sanity
# ===========================================================================

def test_cpm_has_level_1():
    assert 1.0 in CPM

def test_cpm_has_level_51():
    assert 51.0 in CPM

def test_cpm_levels_are_half_steps():
    for level in CPM:
        assert level * 2 == round(level * 2), f"Non-half-step level: {level}"

def test_cpm_strictly_increasing():
    values = [CPM[l] for l in _LEVELS]
    assert all(a < b for a, b in zip(values, values[1:]))


# ===========================================================================
# cp()
# ===========================================================================

def test_cp_known_value_simple():
    """
    cp(100, 100, 100, 0, 0, 0, level=1.0)
    = floor(100 * sqrt(100) * sqrt(100) * 0.094^2 / 10)
    = floor(100 * 10 * 10 * 0.008836 / 10)
    = floor(8.836) = 8 → but min is 10, so cp = 10
    """
    assert cp(100, 100, 100, 0, 0, 0, 1.0) == 10

def test_cp_known_value_non_trivial():
    """
    cp(100, 100, 100, 15, 15, 15, level=40.0)
    = floor(115 * sqrt(115) * sqrt(115) * 0.7903^2 / 10)
    = floor(115 * 115 * 0.624574 / 10)
    = floor(13225 * 0.0624574)
    = floor(825.89) = 825
    """
    assert cp(100, 100, 100, 15, 15, 15, 40.0) == 825

def test_cp_minimum_is_10():
    assert cp(1, 1, 1, 0, 0, 0, 1.0) == 10

def test_cp_increases_with_higher_ivs():
    base = (FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA)
    assert cp(*base, 15, 15, 15, 20.0) > cp(*base, 0, 0, 0, 20.0)

def test_cp_increases_with_higher_level():
    base = (FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA)
    assert cp(*base, 10, 10, 10, 30.0) > cp(*base, 10, 10, 10, 20.0)

def test_cp_is_int():
    assert isinstance(cp(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA, 10, 10, 10, 20.0), int)


# ===========================================================================
# battle_stats()
# ===========================================================================

def test_battle_stats_keys():
    stats = battle_stats(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA, 10, 10, 10, 20.0)
    assert set(stats.keys()) == {'atk', 'def', 'hp'}

def test_battle_stats_atk():
    """atk = (base_atk + atk_iv) * cpm"""
    cpm = CPM[20.0]
    stats = battle_stats(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA, 10, 10, 10, 20.0)
    assert stats['atk'] == pytest.approx((FAKE_BASE_ATK + 10) * cpm)

def test_battle_stats_def():
    """def = (base_def + def_iv) * cpm"""
    cpm = CPM[20.0]
    stats = battle_stats(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA, 10, 10, 10, 20.0)
    assert stats['def'] == pytest.approx((FAKE_BASE_DEF + 10) * cpm)

def test_battle_stats_hp_is_floor():
    """hp = floor((base_sta + sta_iv) * cpm)"""
    cpm = CPM[20.0]
    stats = battle_stats(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA, 10, 10, 10, 20.0)
    assert stats['hp'] == math.floor((FAKE_BASE_STA + 10) * cpm)

def test_battle_stats_hp_is_int():
    stats = battle_stats(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA, 10, 10, 10, 20.0)
    assert isinstance(stats['hp'], int)

def test_battle_stats_known_values():
    """
    battle_stats(100, 100, 100, 0, 0, 0, level=1.0), cpm=0.094
      atk = 100 * 0.094 = 9.4
      def = 100 * 0.094 = 9.4
      hp  = floor(100 * 0.094) = floor(9.4) = 9
    """
    stats = battle_stats(100, 100, 100, 0, 0, 0, 1.0)
    assert stats['atk'] == pytest.approx(9.4)
    assert stats['def'] == pytest.approx(9.4)
    assert stats['hp'] == 9


# ===========================================================================
# stat_product()
# ===========================================================================

def test_stat_product_value():
    assert stat_product(100.0, 200.0, 50) == pytest.approx(1_000_000.0)

def test_stat_product_zero():
    assert stat_product(0.0, 200.0, 50) == 0.0


# ===========================================================================
# best_level()
# ===========================================================================

def test_best_level_result_is_under_cap():
    level = best_level(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA,
                       10, 10, 10, max_cp=500)
    assert level is not None
    assert cp(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA, 10, 10, 10, level) <= 500

def test_best_level_is_the_highest_valid():
    """The next half-level must exceed the cap (or not exist)."""
    level = best_level(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA,
                       10, 10, 10, max_cp=500)
    next_level = level + 0.5
    if next_level in CPM:
        assert cp(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA, 10, 10, 10, next_level) > 500

def test_best_level_respects_max_level():
    level = best_level(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA,
                       0, 0, 0, max_cp=10000, max_level=20.0)
    assert level is not None
    assert level <= 20.0

def test_best_level_none_when_impossible():
    """Returns None when even level 1 with these IVs exceeds max_cp."""
    assert best_level(500, 500, 500, 15, 15, 15, max_cp=1) is None

def test_best_level_exact_cap_is_valid():
    """A CP exactly equal to max_cp should be accepted."""
    # Find a level where cp == some value, then use that as the cap
    level_40_cp = cp(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA, 15, 15, 15, 40.0)
    result = best_level(FAKE_BASE_ATK, FAKE_BASE_DEF, FAKE_BASE_STA,
                        15, 15, 15, max_cp=level_40_cp, max_level=40.0)
    assert result == 40.0


# ===========================================================================
# Pokemon dataclass — unit tests (mock gamemaster)
# ===========================================================================

def test_pokemon_at_best_level_creates_instance(mock_gm):
    p = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great')
    assert isinstance(p, Pokemon)
    assert p.species == 'Testmon'
    assert p.atk_iv == 10
    assert p.def_iv == 10
    assert p.sta_iv == 10

def test_pokemon_cp_under_cap(mock_gm):
    p = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great')
    assert p.cp <= LEAGUE_CAPS['great']

def test_pokemon_atk_property(mock_gm):
    p = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great')
    assert p.atk == pytest.approx((FAKE_BASE_ATK + 10) * CPM[p.level])

def test_pokemon_def_property(mock_gm):
    p = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great')
    assert p.def_ == pytest.approx((FAKE_BASE_DEF + 10) * CPM[p.level])

def test_pokemon_hp_is_floor(mock_gm):
    p = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great')
    assert isinstance(p.hp, int)
    assert p.hp == math.floor((FAKE_BASE_STA + 10) * CPM[p.level])

def test_pokemon_stat_product(mock_gm):
    p = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great')
    assert p.stat_product == pytest.approx(p.atk * p.def_ * p.hp)

def test_pokemon_cp_property_matches_function(mock_gm):
    p = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great')
    assert p.cp == cp(p.base_atk, p.base_def, p.base_sta,
                      p.atk_iv, p.def_iv, p.sta_iv, p.level)

def test_pokemon_at_best_level_raises_for_impossible(mock_gm):
    """Raises ValueError when max_level is too restrictive to find any valid level."""
    with pytest.raises(ValueError):
        Pokemon.at_best_level('Testmon', 15, 15, 15, league='great', max_level=0.0)

def test_pokemon_unknown_species_raises(mock_gm):
    with pytest.raises(KeyError):
        Pokemon.at_best_level('NotARealMon', 10, 10, 10, league='great')

def test_pokemon_ultra_league(mock_gm):
    p = Pokemon.at_best_level('Testmon', 15, 15, 15, league='ultra')
    assert p.cp <= LEAGUE_CAPS['ultra']


# ===========================================================================
# Integration tests — require real gamemaster (network or warm cache)
# Validate against known PvPoke values; run with: pytest -m integration
#
# To verify: open https://pvpoke.com/rankings/ and check each species at the
# listed IVs.  The CP and level should match what PvPoke shows.
# ===========================================================================

pytestmark_integration = pytest.mark.integration


@pytest.mark.integration
@pytest.mark.parametrize("species,atk_iv,def_iv,sta_iv,league,expected_level,expected_cp", [
    # Azumarill 8/15/15 in Great League — lands exactly on the 1500 cap at level 40.
    # Verify at: pvpoke.com/rankings/  (Great League, Azumarill, IVs 8/15/15)
    ("Azumarill", 8, 15, 15, "great", 40.0, 1500),
])
def test_pvpoke_known_cp_values(species, atk_iv, def_iv, sta_iv, league,
                                 expected_level, expected_cp):
    p = Pokemon.at_best_level(species, atk_iv, def_iv, sta_iv, league=league, max_level=51.0)
    assert p.level == expected_level, (
        f"{species} {atk_iv}/{def_iv}/{sta_iv} {league}: "
        f"expected level {expected_level}, got {p.level}"
    )
    assert p.cp == expected_cp, (
        f"{species} {atk_iv}/{def_iv}/{sta_iv} {league}: "
        f"expected CP {expected_cp}, got {p.cp}"
    )


@pytest.mark.integration
def test_gamemaster_has_azumarill():
    """Sanity check that the gamemaster contains a species we expect."""
    base = get_species("Azumarill")
    assert 'atk' in base
    assert 'def' in base
    assert 'hp' in base


# ===========================================================================
# Shadow Pokemon — unit tests
# ===========================================================================

def test_shadow_atk_multiplier(mock_gm):
    normal = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great', shadow=False)
    shadow = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great', shadow=True)
    assert shadow.atk == pytest.approx(normal.atk * SHADOW_ATK_BONUS)

def test_shadow_def_multiplier(mock_gm):
    normal = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great', shadow=False)
    shadow = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great', shadow=True)
    assert shadow.def_ == pytest.approx(normal.def_ * SHADOW_DEF_MULT)

def test_shadow_hp_unchanged(mock_gm):
    normal = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great', shadow=False)
    shadow = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great', shadow=True)
    assert shadow.hp == normal.hp

def test_shadow_cp_unchanged(mock_gm):
    """CP is calculated from base stats only — shadow status doesn't affect it."""
    normal = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great', shadow=False)
    shadow = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great', shadow=True)
    assert shadow.cp == normal.cp

def test_non_shadow_unaffected(mock_gm):
    p = Pokemon.at_best_level('Testmon', 10, 10, 10, league='great')
    assert p.shadow is False
    cpm = CPM[p.level]
    assert p.atk == pytest.approx((FAKE_BASE_ATK + 10) * cpm)


# ===========================================================================
# IV ranking — unit tests
# ===========================================================================

def test_iv_rank_returns_list(mock_gm):
    results = iv_rank('Testmon', league='great')
    assert isinstance(results, list)
    assert len(results) > 0

def test_iv_rank_has_4096_entries(mock_gm):
    results = iv_rank('Testmon', league='great')
    assert len(results) == 4096

def test_iv_rank_sorted_descending(mock_gm):
    results = iv_rank('Testmon', league='great')
    sps = [e['stat_product'] for e in results]
    assert sps == sorted(sps, reverse=True)

def test_iv_rank_rank1_is_1(mock_gm):
    results = iv_rank('Testmon', league='great')
    assert results[0]['rank'] == 1

def test_iv_rank_ranks_sequential(mock_gm):
    results = iv_rank('Testmon', league='great')
    assert [e['rank'] for e in results] == list(range(1, len(results) + 1))

def test_iv_rank_15_15_15_high(mock_gm):
    """15/15/15 should be near the top (often rank 1 for many species)."""
    results = iv_rank('Testmon', league='great')
    r = next(e for e in results if e['atk_iv'] == 15 and e['def_iv'] == 15 and e['sta_iv'] == 15)
    assert r['rank'] <= 5

def test_iv_rank_has_required_keys(mock_gm):
    e = iv_rank('Testmon', league='great')[0]
    for key in ('rank', 'atk_iv', 'def_iv', 'sta_iv', 'level', 'atk', 'def_', 'hp', 'stat_product', 'cp'):
        assert key in e

def test_iv_rank_shadow_stat_product_same(mock_gm):
    """Shadow multipliers (×1.2 atk, ×5/6 def) cancel: atk×def contribution is unchanged."""
    normal = iv_rank('Testmon', league='great', shadow=False)
    shadow = iv_rank('Testmon', league='great', shadow=True)
    assert shadow[0]['stat_product'] == pytest.approx(normal[0]['stat_product'])


# ===========================================================================
# IV ranking — integration tests
# ===========================================================================

@pytest.mark.integration
def test_iv_rank_azumarill_rank1():
    """Azumarill's rank 1 Great League IV combo is well-known: 0/15/14 or similar."""
    results = iv_rank('Azumarill', league='great')
    assert len(results) == 4096
    r1 = results[0]
    assert r1['rank'] == 1
    assert r1['stat_product'] >= results[1]['stat_product']

@pytest.mark.integration
def test_iv_rank_azumarill_0_15_15_rank(mock_gm=None):
    """0/15/15 is a common 'lucky trade' IV spread; verify its rank is reasonable."""
    results = iv_rank('Azumarill', league='great')
    r = next(e for e in results if e['atk_iv'] == 0 and e['def_iv'] == 15 and e['sta_iv'] == 15)
    assert r['rank'] < 50   # well-known high-rank spread
