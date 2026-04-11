"""
Tests for gopvpsim.user_collection and gopvpsim.evolution_lines.

The Poke Genie fixture at ``userdata/fixtures/poke_genie_export.csv``
is gitignored (personal collection data). Tests that need it skip
cleanly when it's absent — CI and other developers get green runs;
the user's local dev has the full coverage.
"""
from pathlib import Path

import pytest

from gopvpsim.evolution_lines import (
    get_final_form, get_final_forms, invalidate_cache,
    load_evolution_lines,
)
from gopvpsim.pokemon import Pokemon, get_pokemon_index, iv_rank
from gopvpsim.user_collection import (
    FORM_MAP, check_thresholds, compute_rank_lookup, get_species_name,
    ivs_to_stats_at_cap, parse_csv,
)


FIXTURE_PATH = (
    Path(__file__).parent.parent / 'userdata' / 'fixtures' / 'poke_genie_export.csv'
)


def _fixture_or_skip():
    """Return the fixture path, or pytest.skip if it's not present."""
    if not FIXTURE_PATH.exists():
        pytest.skip(
            f"Poke Genie fixture not available at {FIXTURE_PATH}. "
            f"See DEVELOPER_NOTES.md for the convention — the fixture "
            f"is gitignored (personal collection data)."
        )
    return FIXTURE_PATH


# ---------------------------------------------------------------------------
# evolution_lines
# ---------------------------------------------------------------------------

def test_evolution_lines_loads_nonempty():
    lines = load_evolution_lines()
    assert len(lines) > 100, f"expected 100+ families, got {len(lines)}"


def test_evolution_lines_tinkaton_chain():
    lines = load_evolution_lines()
    assert lines['Tinkaton'] == ['Tinkatink', 'Tinkatuff', 'Tinkaton']


def test_get_final_form_tinkatink_unambiguous():
    assert get_final_form('Tinkatink') == 'Tinkaton'
    assert get_final_form('Tinkatuff') == 'Tinkaton'
    assert get_final_form('Tinkaton') == 'Tinkaton'


def test_get_final_form_bunnelby():
    assert get_final_form('Bunnelby') == 'Diggersby'


def test_get_final_form_mankey_three_stage():
    # Annihilape was added in gen 9 — confirms the chain includes the new
    # third-stage evolution.
    assert get_final_form('Mankey') == 'Annihilape'
    assert load_evolution_lines()['Annihilape'] == [
        'Mankey', 'Primeape', 'Annihilape',
    ]


def test_get_final_form_eevee_raises_on_branching():
    with pytest.raises(ValueError, match='branching evolutions'):
        get_final_form('Eevee')


def test_get_final_forms_eevee_returns_all_eeveelutions():
    finals = get_final_forms('Eevee')
    # All 8 standard eeveelutions should be present (Sylveon = Gen 6).
    assert 'Vaporeon' in finals
    assert 'Jolteon' in finals
    assert 'Flareon' in finals
    assert 'Espeon' in finals
    assert 'Umbreon' in finals
    assert 'Sylveon' in finals
    # Output is sorted.
    assert finals == sorted(finals)


def test_get_final_forms_slowpoke_branches_to_slowbro_and_slowking():
    assert set(get_final_forms('Slowpoke')) == {'Slowbro', 'Slowking'}


def test_get_final_forms_ditto_passthrough():
    # No evolution, not in any family → returns self.
    assert get_final_forms('Ditto') == ['Ditto']


def test_get_final_forms_final_form_maps_to_self():
    assert get_final_forms('Tinkaton') == ['Tinkaton']
    assert get_final_forms('Annihilape') == ['Annihilape']


def test_invalidate_cache_roundtrip():
    # Ensure the lazy cache rebuilds cleanly after invalidation.
    first = load_evolution_lines()
    invalidate_cache()
    second = load_evolution_lines()
    assert first == second
    assert first is not second  # different dict objects after rebuild


# ---------------------------------------------------------------------------
# Species name resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,form,shadow,expected", [
    ('Tinkaton',   '',              False, 'Tinkaton'),
    ('Tinkaton',   'Normal',        False, 'Tinkaton'),  # Normal → no suffix
    ('Weezing',    'Galar',         False, 'Weezing (Galarian)'),
    ('Muk',        'Alola',         False, 'Muk (Alolan)'),
    ('Sableye',    '',              True,  'Sableye (Shadow)'),
    ('Tauros',     'Paldea Combat', False, 'Tauros (Paldea Combat)'),
    ('Weezing',    'Galar',         True,  'Weezing (Galarian) (Shadow)'),
])
def test_get_species_name(name, form, shadow, expected):
    assert get_species_name(name, form, shadow) == expected


# ---------------------------------------------------------------------------
# ivs_to_stats_at_cap — verify against Pokemon.at_best_level
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("species,ivs", [
    ('Tinkaton',    (0, 12, 11)),
    ('Tinkaton',    (0, 15, 15)),
    ('Tinkaton',    (15, 15, 15)),
    ('Medicham',    (5, 15, 15)),
    ('Azumarill',   (0, 15, 15)),
    ('Corviknight', (0, 15, 2)),
])
def test_ivs_to_stats_at_cap_matches_pokemon_at_best_level(species, ivs):
    """Our stat calc should produce the exact same atk/def/hp/cp/level as
    gopvpsim.pokemon.Pokemon.at_best_level for every IV spread."""
    pokemon_index = get_pokemon_index()
    base = pokemon_index[species]
    p = Pokemon.at_best_level(species, *ivs, league='great')
    stats = ivs_to_stats_at_cap(
        base['atk'], base['def'], base['hp'], *ivs,
        max_level=51.0, max_cp=1500,
    )
    assert stats is not None, f"{species} {ivs}: best_level returned None"
    assert abs(stats['attack'] - p.atk) < 0.001
    assert abs(stats['defense'] - p.def_) < 0.001
    assert stats['stamina'] == p.hp
    assert stats['cp'] == p.cp
    assert stats['level'] == p.level


def test_ivs_to_stats_at_cap_applies_shadow_multipliers():
    """Shadow mons get ×1.2 atk / ×5/6 def; CP unchanged."""
    # Sableye has non-shadow and shadow forms with the same baseStats.
    base = get_pokemon_index()['Sableye']
    normal = ivs_to_stats_at_cap(
        base['atk'], base['def'], base['hp'], 4, 15, 15,
        shadow=False, max_level=47.0, max_cp=1500,
    )
    shadow = ivs_to_stats_at_cap(
        base['atk'], base['def'], base['hp'], 4, 15, 15,
        shadow=True, max_level=47.0, max_cp=1500,
    )
    # Shadow atk ×1.2, def ×5/6, HP and CP unchanged.
    assert abs(shadow['attack']  - normal['attack']  * 1.2) < 0.01
    assert abs(shadow['defense'] - normal['defense'] * 5 / 6) < 0.01
    assert shadow['stamina'] == normal['stamina']
    assert shadow['cp']      == normal['cp']
    assert shadow['level']   == normal['level']


# ---------------------------------------------------------------------------
# compute_rank_lookup
# ---------------------------------------------------------------------------

def test_compute_rank_lookup_matches_iv_rank():
    ranked = iv_rank('Tinkaton', league='great')
    lookup = compute_rank_lookup('Tinkaton', league='great')
    # Every entry from iv_rank should resolve to the same rank via lookup.
    for e in ranked[:50]:
        iv_tuple = (e['atk_iv'], e['def_iv'], e['sta_iv'])
        assert lookup[iv_tuple] == e['rank']
    # Rank 1 should be unique (or tied at rank 1, but the first entry's
    # rank must be 1).
    assert ranked[0]['rank'] == 1
    assert lookup[(ranked[0]['atk_iv'], ranked[0]['def_iv'], ranked[0]['sta_iv'])] == 1


# ---------------------------------------------------------------------------
# parse_csv — fixture-dependent
# ---------------------------------------------------------------------------

def test_parse_csv_returns_nonempty_list():
    path = _fixture_or_skip()
    mons = parse_csv(str(path))
    assert len(mons) > 0
    # Every mon dict must have the required fields populated.
    for m in mons[:10]:
        for field in ('name', 'form', 'cp', 'atk_iv', 'def_iv', 'sta_iv',
                      'level', 'is_shadow', 'lucky'):
            assert field in m, f"mon {m} missing field {field}"
        assert isinstance(m['cp'], int)
        assert 0 <= m['atk_iv'] <= 15
        assert 0 <= m['def_iv'] <= 15
        assert 0 <= m['sta_iv'] <= 15
        assert m['level'] >= 1.0
        assert isinstance(m['is_shadow'], bool)


def test_parse_csv_extracts_tinkatinks_and_tinkatons():
    path = _fixture_or_skip()
    mons = parse_csv(str(path))
    tinkatinks = [m for m in mons if m['name'] == 'Tinkatink']
    tinkatons = [m for m in mons if m['name'] == 'Tinkaton']
    # The fixture is a post-CD Tinkaton dump — both stages should appear.
    assert len(tinkatinks) > 100, (
        f"expected many Tinkatinks post-CD, got {len(tinkatinks)}")
    assert len(tinkatons) >= 1, f"expected at least one Tinkaton, got {len(tinkatons)}"


def test_parse_csv_shadow_flag_parses():
    path = _fixture_or_skip()
    mons = parse_csv(str(path))
    # Any collection will have some shadow mons — check the flag parses
    # as a real bool (not the raw '1'/'0' string).
    shadows = [m for m in mons if m['is_shadow']]
    assert all(m['is_shadow'] is True for m in shadows)


# ---------------------------------------------------------------------------
# check_thresholds — end-to-end
# ---------------------------------------------------------------------------

def test_check_thresholds_finds_tinkatinks_via_evolution_walk():
    """A threshold on 'Tinkaton' should match the user's Tinkatinks via
    pre-evo walkup, not require them to already be evolved."""
    path = _fixture_or_skip()

    # Permissive threshold — any Tinkaton with atk≥90 should match.
    thresholds = {
        'Tinkaton': {
            'Great': {
                'Any': {'attack': 90, 'defense': 0, 'stamina': 0},
            },
        },
    }
    results = check_thresholds(str(path), thresholds, league='great')
    assert 'Tinkaton' in results
    tinkaton_matches = results['Tinkaton']
    assert len(tinkaton_matches) > 0
    # At least some of the matches should be from Tinkatinks (pre-evos)
    # rather than already-evolved Tinkatons.
    pre_evos = [r for r in tinkaton_matches if r['is_pre_evo']]
    assert len(pre_evos) > 50, (
        f"expected Tinkatinks to walk up to Tinkaton, got {len(pre_evos)} "
        f"pre-evo matches out of {len(tinkaton_matches)} total")
    # Verify that pre-evo records carry the resolved stats and the
    # csv_species (pre-evo name) separately from final_species (Tinkaton).
    sample = pre_evos[0]
    assert sample['csv_species'] in ('Tinkatink', 'Tinkatuff')
    assert sample['final_species'] == 'Tinkaton'
    assert sample['mon']['name'] == sample['csv_species']
    assert sample['stats']['attack'] >= 90


def test_check_thresholds_onlytop_rank_cap():
    """The onlytop filter should exclude mons whose SP rank exceeds the
    cap, even when their stat floors match."""
    path = _fixture_or_skip()
    thresholds = {
        'Tinkaton': {
            'Great': {
                'top10': {'attack': 0, 'defense': 0, 'stamina': 0, 'onlytop': 10},
            },
        },
    }
    results = check_thresholds(str(path), thresholds, league='great')
    matches = results.get('Tinkaton', [])
    # Every match should have rank ≤ 10.
    for r in matches:
        assert r['stats']['rank'] <= 10, (
            f"{r['mon']['name']} {r['mon']['atk_iv']}/{r['mon']['def_iv']}/"
            f"{r['mon']['sta_iv']} has rank {r['stats']['rank']} > 10")


def test_check_thresholds_ivs_whitelist():
    """The ivs whitelist should match only the specified IV triples."""
    path = _fixture_or_skip()
    thresholds = {
        'Tinkaton': {
            'Great': {
                'rank1_only': {
                    'attack': 0, 'defense': 0, 'stamina': 0,
                    'ivs': [[0, 14, 14], [0, 15, 15]],
                },
            },
        },
    }
    results = check_thresholds(str(path), thresholds, league='great')
    for r in results.get('Tinkaton', []):
        ivs = (r['mon']['atk_iv'], r['mon']['def_iv'], r['mon']['sta_iv'])
        assert ivs in [(0, 14, 14), (0, 15, 15)]


def test_check_thresholds_include_empty_returns_unmatched_species():
    """With include_empty=True, species that have no matches should
    still appear in results with an empty list."""
    path = _fixture_or_skip()
    thresholds = {
        # Unreasonable floor that no Tinkaton in any collection hits.
        'Tinkaton': {
            'Great': {
                'impossible': {'attack': 999},
            },
        },
    }
    results = check_thresholds(
        str(path), thresholds, league='great', include_empty=True)
    assert 'Tinkaton' in results
    assert results['Tinkaton'] == []
