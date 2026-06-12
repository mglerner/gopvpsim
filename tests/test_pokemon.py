"""
Tests for gopvpsim.pokemon — stat calculation, CP, level, stat product.

Unit tests use a mock gamemaster (no network required).
Integration tests (marked 'integration') hit the real gamemaster and validate
against known PvPoke values — run with: pytest -m integration
"""
import math
from pathlib import Path

import pytest

REPO_ROOT_FOR_SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'

from gopvpsim.pokemon import (
    CPM, LEAGUE_CAPS, _LEVELS,
    cp, battle_stats, stat_product, best_level,
    get_species, Pokemon, iv_rank,
    pvpoke_default_ivs, compute_default_ivs,
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
    """Shadow status does NOT affect CP — CP is from base stats only, same for shadow and non-shadow."""
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


# ===========================================================================
# pvpoke_default_ivs — integration tests
#
# Ground truth: these values were verified against pvpoke.com by hand.
# pvpoke_default_ivs() reads directly from the gamemaster JSON so it is
# always authoritative.
# ===========================================================================

@pytest.mark.integration
@pytest.mark.parametrize("species,league,level_cap,expected", [
    # Regular Pokemon, Great League
    ("Medicham",  "great", 50.0, (49.0,  7, 15, 14)),
    ("Azumarill", "great", 50.0, (43.0,  4, 15, 13)),
    ("Spidops",   "great", 50.0, (37.5,  4, 13, 14)),
    # Legendary, Great League (rank 32)
    ("Registeel", "great", 50.0, (22.5,  8, 15, 14)),
    ("Cresselia",  "great", 50.0, (20.0,  4, 11,  9)),
    # Ultra League
    ("Swampert",  "ultra", 50.0, (32.0,  4, 15, 14)),
    ("Registeel", "ultra", 50.0, (49.0,  4,  6, 14)),
    # l40 variants (level_cap=40)
    ("Medicham",  "great", 40.0, (40.0, 15, 15, 15)),
    ("Registeel", "ultra", 40.0, (40.0, 15, 15, 15)),
    # Master League always 15/15/15
    ("Medicham",  "master", 50.0, (50.0, 15, 15, 15)),
    ("Registeel", "master", 50.0, (50.0, 15, 15, 15)),
])
def test_pvpoke_default_ivs_known_values(species, league, level_cap, expected):
    result = pvpoke_default_ivs(species, league, level_cap)
    assert result == expected, (
        f"{species} {league} (cap={level_cap}): expected {expected}, got {result}"
    )


@pytest.mark.integration
def test_pvpoke_default_ivs_unknown_league():
    with pytest.raises(ValueError, match="Unknown league"):
        pvpoke_default_ivs("Medicham", "premier")


@pytest.mark.integration
def test_pvpoke_default_ivs_returns_tuple():
    result = pvpoke_default_ivs("Azumarill", "great")
    assert isinstance(result, tuple)
    assert len(result) == 4


@pytest.mark.integration
def test_pvpoke_default_ivs_ivs_in_range():
    """IVs must be in 0–15."""
    level, a, d, s = pvpoke_default_ivs("Azumarill", "great")
    assert 0 <= a <= 15
    assert 0 <= d <= 15
    assert 0 <= s <= 15


@pytest.mark.integration
def test_pvpoke_default_ivs_cp_under_cap():
    """The returned IVs+level must satisfy the CP cap."""
    from gopvpsim.pokemon import get_pokemon_entry, LEAGUE_CP
    for species, league in [("Medicham", "great"), ("Azumarill", "great"),
                             ("Swampert", "ultra"), ("Registeel", "great")]:
        level, a, d, s = pvpoke_default_ivs(species, league)
        entry = get_pokemon_entry(species)
        base = entry['baseStats']
        actual_cp = cp(base['atk'], base['def'], base['hp'], a, d, s, level)
        assert actual_cp <= LEAGUE_CP[league], (
            f"{species} {league}: CP {actual_cp} exceeds cap {LEAGUE_CP[league]}"
        )


# ===========================================================================
# compute_default_ivs — integration tests
#
# This function re-implements PvPoke's generateDefaultIVsByPokemon() dev tool
# from the JavaScript source.  It uses iv_floor=4 matching the *current*
# PvPoke source, but the gamemaster.json was generated with an older version
# of the algorithm (iv_floor appears to have been 2 for many Pokemon).
#
# Consequently, compute_default_ivs() matches pvpoke_default_ivs() for:
#   - legendaries (floor matters less; rank index differs)
#   - near-cap Pokemon (floor=12 overrides the ambiguous baseline)
#   - Pokemon that trivially can't reach the CP cap (always 15/15/15)
#   - Master League (always 15/15/15)
#
# It may differ for common non-legendary Pokemon in older gamemaster entries.
# The broad-match test is marked xfail to document this known limitation.
# ===========================================================================

@pytest.mark.integration
@pytest.mark.parametrize("species,league,level_cap,expected", [
    # Legendary, Great League — floor=4 gives the same answer as the gamemaster
    ("Registeel", "great", 50.0, (22.5,  8, 15, 14)),
    ("Cresselia",  "great", 50.0, (20.0,  4, 11,  9)),
    # l40 variants
    ("Medicham",  "great", 40.0, (40.0, 15, 15, 15)),
    ("Registeel", "ultra", 40.0, (40.0, 15, 15, 15)),
    # Master League
    ("Medicham",  "master", 50.0, (50.0, 15, 15, 15)),
    # Hard-coded exception still applied
    ("Medicham",  "great", 50.0, (49.0,  7, 15, 14)),
])
def test_compute_default_ivs_known_values(species, league, level_cap, expected):
    result = compute_default_ivs(species, league, level_cap)
    assert result == expected, (
        f"{species} {league} (cap={level_cap}): expected {expected}, got {result}"
    )


@pytest.mark.integration
def test_compute_default_ivs_returns_valid_cp():
    """The IVs+level returned must satisfy the CP cap."""
    from gopvpsim.pokemon import get_pokemon_entry, LEAGUE_CP
    for species, league in [("Registeel", "great"), ("Cresselia", "great"),
                             ("Swampert", "ultra")]:
        level, a, d, s = compute_default_ivs(species, league)
        entry = get_pokemon_entry(species)
        base = entry['baseStats']
        actual_cp = cp(base['atk'], base['def'], base['hp'], a, d, s, level)
        assert actual_cp <= LEAGUE_CP[league]


@pytest.mark.integration
def test_compute_default_ivs_result_is_stat_product_rank2_or_higher():
    """
    For regular non-legendary Pokemon, compute_default_ivs() should return
    something near the top of the stat-product ranking (within the top 5).

    Uses Swampert UL as a clean case where floor=4 applies and matches.
    """
    from gopvpsim.pokemon import get_pokemon_entry, LEAGUE_CP, _generate_iv_combinations
    species, league = "Swampert", "ultra"
    entry = get_pokemon_entry(species)
    base = entry['baseStats']
    ba, bd, bs = base['atk'], base['def'], base['hp']
    cap = LEAGUE_CP[league]

    level, a, d, s = compute_default_ivs(species, league)
    combos = _generate_iv_combinations(ba, bd, bs, cap, 50.0, 4, 1.0)
    idx = next((i for i, c in enumerate(combos)
                if c['atk_iv'] == a and c['def_iv'] == d and c['sta_iv'] == s
                and c['level'] == level), None)
    assert idx is not None, "Returned combo not found in generated list"
    assert idx <= 5, f"Expected top-5 combo, got rank {idx + 1}"


@pytest.mark.integration
@pytest.mark.slow  # ~77s — 75% of total suite wall time (2026-06-12)
@pytest.mark.xfail(reason=(
    "compute_default_ivs uses iv_floor=4 (current PvPoke source), but "
    "gamemaster.json was generated with iv_floor≈2 for many Pokemon, so "
    "~3-5% of entries will differ. pvpoke_default_ivs() is always authoritative."
))
def test_compute_default_ivs_matches_gamemaster_broadly():
    """
    Ideally compute_default_ivs() would match pvpoke_default_ivs() for every
    Pokemon.  This test documents that it doesn't due to algorithm evolution.
    """
    from gopvpsim.data import load_gamemaster
    from gopvpsim.pokemon import LEAGUE_CP

    gm = load_gamemaster()
    league_map = {500: 'little', 1500: 'great', 2500: 'ultra'}
    mismatches = 0
    total = 0

    for mon in gm['pokemon']:
        div = mon.get('defaultIVs', {})
        for key, combo in div.items():
            if not key.startswith('cp') or 'l40' in key or len(combo) != 4:
                continue
            cap_s = key[2:]
            if not cap_s.isdigit():
                continue
            cap = int(cap_s)
            league = league_map.get(cap)
            if not league:
                continue
            gm_val = (float(combo[0]), int(combo[1]), int(combo[2]), int(combo[3]))
            alg_val = compute_default_ivs(mon['speciesName'], league, 50.0)
            total += 1
            if gm_val != alg_val:
                mismatches += 1

    # This assertion will fail — that's expected and documented via xfail
    assert mismatches == 0, f"{mismatches}/{total} entries differ from gamemaster"


# ===========================================================================
# Aegislash (Blade) whole-level rounding (regression guard for S1)
#
# Aegislash (Blade) powers up in whole-level increments only — not the
# standard half-level grid — because Pokemon Go's form-change rule
# rounds DOWN to whole levels when transforming from Shield to Blade
# (cascade1185 / Caleb Peng discovery; PvPoke's getFormStats() mirrors
# this via newLevel--).
#
# Our sim was correctly enforcing this in the in-battle transform path
# (gopvpsim.formchange._aegislash_alt_level) but NOT in the focal-
# species path. So Aegislash (Blade) as a dive's focal species was
# computing stats at half levels. Mercuryish caught it in the
# 2026-04-26 review. Patched in commit 1b6c075. These tests ensure
# the patch sticks.
# ===========================================================================

class TestAegislashBladeWholeLevels:
    """Lock in whole-level rounding for Aegislash (Blade) as the focal
    species. The ground-truth values are the ones the Prague Regional
    winner's IVs produce (1/14/11 = L22 / 1454 CP per mercuryish; PvPoke
    confirms)."""

    @pytest.mark.integration
    @pytest.mark.parametrize("ivs,expected_level,expected_cp", [
        # mercuryish's reference: tournament winner's 1/14/11 build.
        # Without the whole-level patch, this would land at L22.5 / 1487.
        ((1, 14, 11), 22.0, 1454),
        # Hundo: already whole-level by chance (the unpatched grid
        # also picks L21.0 here). Patch is a no-op but the test
        # documents that the result is stable.
        ((15, 15, 15), 21.0, 1484),
        # 15/14/15: same — pre-patch and post-patch both land on L21.
        ((15, 14, 15), 21.0, 1477),
        # 15/15/14: same.
        ((15, 15, 14), 21.0, 1479),
    ])
    def test_at_best_level_rounds_down_to_whole(
            self, ivs, expected_level, expected_cp):
        a, d, s = ivs
        mon = Pokemon.at_best_level(
            'Aegislash (Blade)', a, d, s, league='great', shadow=False)
        assert mon.level == expected_level, (
            f'Aegislash (Blade) {a}/{d}/{s} GL: expected L{expected_level} '
            f'(whole-level rule), got L{mon.level}')
        assert mon.cp == expected_cp, (
            f'Aegislash (Blade) {a}/{d}/{s} GL: expected CP {expected_cp}, '
            f'got CP {mon.cp}')
        # Defensive: every Blade-form-as-focal level must be a whole
        # number, no matter the IVs. Test on a wider sweep would be
        # better but is too slow for unit scope; spot-check here.
        assert mon.level % 1.0 == 0, (
            f'Aegislash (Blade) landed on a half level: L{mon.level}')

    @pytest.mark.integration
    def test_at_best_level_does_not_affect_shield_form(self):
        """Aegislash (Shield), Aegislash (Blade)'s in-battle counterpart,
        keeps the standard half-level grid since Shield form does power
        up in half-levels in-game."""
        mon = Pokemon.at_best_level(
            'Aegislash (Shield)', 1, 14, 11, league='great', shadow=False)
        # Pre-existing behavior: Shield form's high def means it caps
        # high on the level grid; expecting a half-level result here is
        # how we know the patch is Blade-specific.
        assert mon.level == 49.5
        assert mon.cp == 1498

    @pytest.mark.integration
    def test_iv_rank_rounds_aegislash_blade_levels(self):
        """iv_rank goes through the same best_level call as
        at_best_level — verify it gets the same whole-level rounding
        applied. Without the patch, half-level entries would slip
        through and break stat-product rankings against PvPoke."""
        ranked = iv_rank('Aegislash (Blade)', league='great')
        half_levels = [e for e in ranked if e['level'] % 1.0 != 0]
        assert half_levels == [], (
            f'iv_rank emitted {len(half_levels)} Aegislash (Blade) entries '
            f'with half-level levels; first offender: {half_levels[0]}')

    @pytest.mark.integration
    def test_iv_rank_does_not_affect_shield_form(self):
        """iv_rank for Aegislash (Shield) keeps half-levels (no patch
        applied) so we know the patch is Blade-specific."""
        ranked = iv_rank('Aegislash (Shield)', league='great')
        half_levels = [e for e in ranked if e['level'] % 1.0 != 0]
        # Should be plenty of half-levels on Shield form — many IV
        # combos land on .5 levels under the CP cap.
        assert len(half_levels) > 100, (
            f'Aegislash (Shield) iv_rank produced only {len(half_levels)} '
            f'half-level entries; either the dataset shrank or the '
            f'Blade-form patch is leaking into Shield form')

    @pytest.mark.integration
    def test_compute_iv_metadata_rounds_aegislash_blade_levels(self):
        """deep_dive.compute_iv_metadata is the third best_level
        call site that needed the same whole-level rounding. The
        first attempt at S1 missed this path; the patch was extended
        in commit 1b6c075's follow-up. Test guards against that
        path silently regressing if a future refactor moves the
        Aegislash check elsewhere."""
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT_FOR_SCRIPTS))
        import deep_dive  # noqa: E402
        meta = deep_dive.compute_iv_metadata('Aegislash (Blade)', 'great')
        half_levels = [m for m in meta if m['level'] % 1.0 != 0]
        assert half_levels == [], (
            f'compute_iv_metadata emitted {len(half_levels)} Aegislash '
            f'(Blade) entries with half-level levels; the focal-species '
            f'whole-level rounding regressed.')


# ===========================================================================
# Aegislash (Blade) -> Shield reverse-level CPM-table overflow
# (regression guard for the 2026-06-11 arc-S6 dive crash)
#
# _aegislash_shield_level mirrors PvPoke getFormStats(): GL start level
# is blade_level * 2 + 2, deliberately overshooting so the caller can
# walk down whole levels until CP fits. A low-IV Blade focal caps at
# level 25 in GL (whole-level rule above), putting the raw start at
# 52.0 — off the end of the CPM table (max 51.0) — so
# build_form_change_state raised KeyError before the walk-down could
# run. PvPoke has the same latent overflow (cpms[index] -> undefined)
# but computes form stats lazily at form-change time; our S1 dive
# plumbing builds per-IV configs eagerly at sweep setup, so the first
# Aegislash (Blade) GL dive after S1 crashed on it. Fix: clamp the
# start to max(CPM) in _aegislash_shield_level.
# ===========================================================================

class TestAegislashShieldLevelOverflow:
    """build_form_change_state must survive every legal Blade focal IV."""

    @staticmethod
    def _entry_and_moveset():
        from gopvpsim.formchange import build_form_change_state
        from gopvpsim.moves import get_moves
        from gopvpsim.pokemon import get_pokemon_entry
        entry = get_pokemon_entry('Aegislash (Blade)')
        all_fast, all_charged = get_moves()
        fm = dict(all_fast['PSYCHO_CUT'])
        cms = [dict(all_charged['SHADOW_BALL']),
               dict(all_charged['GYRO_BALL'])]
        return build_form_change_state, entry, fm, cms

    @pytest.mark.integration
    def test_low_iv_blade_gl_does_not_overflow_cpm_table(self):
        """The exact crash repro: 0/0/0 Blade lands at L25 in GL
        (whole-level rule), raw reverse formula = 25*2+2 = 52.0 ->
        KeyError pre-fix."""
        build, entry, fm, cms = self._entry_and_moveset()
        bs = entry['baseStats']
        lvl = best_level(bs['atk'], bs['def'], bs['hp'], 0, 0, 0,
                         max_cp=1500, max_level=51.0)
        assert lvl == 25.0, (
            f'precondition drifted: 0/0/0 Blade GL expected L25, got {lvl} '
            f'(gamemaster base stats may have changed)')
        cfg = build(entry, 0, 0, 0, lvl, 1500, False, fm, cms)
        assert cfg is not None

    @pytest.mark.integration
    def test_all_blade_ivs_build_form_change_state_both_leagues(self):
        """Exhaustive: every 4096-IV Blade focal in GL and UL builds a
        config without walking off the CPM table."""
        build, entry, fm, cms = self._entry_and_moveset()
        bs = entry['baseStats']
        for league_cp in (1500, 2500):
            for a in range(16):
                for d in range(16):
                    for s in range(16):
                        lvl = best_level(bs['atk'], bs['def'], bs['hp'],
                                         a, d, s, max_cp=league_cp,
                                         max_level=51.0)
                        if lvl is None:
                            continue
                        cfg = build(entry, a, d, s, lvl, league_cp,
                                    False, fm, cms)
                        assert cfg is not None, (league_cp, a, d, s)
