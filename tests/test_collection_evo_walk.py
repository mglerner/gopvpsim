"""Gender-aware, level-guarded evolution walk (DRY review 2026-08-05, entry 2).

user_collection's Genie-row -> final-forms walk applies a gender filter
(a male Lechonk cannot become Oinkologne (Female)) and a min_level
guard (power-ups are one-way, so a row above the league-capped level
for its spread cannot exist in that league). bottle_cap_advisor and
owned_breakdown hand-copied the walk WITHOUT either rule -- verified on
the checked-in fixture: every Lechonk-line spread mapped to both
Oinkologne forms, so the Gold-Bottle-Cap advisor could recommend a
target the user cannot build.

The rules now live in user_collection (gender_allows /
eligible_final_forms) and both scripts route through them.
"""
import os
import sys

import pytest

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, '..', 'src'))
sys.path.insert(0, os.path.join(_HERE, '..', 'scripts'))

from gopvpsim.pokemon import Pokemon, get_pokemon_index  # noqa: E402
from gopvpsim.user_collection import (  # noqa: E402
    eligible_final_forms, gender_allows, parse_csv,
)

FIXTURE = os.path.join(_HERE, 'fixtures', 'poke_genie_export.csv')


def _mon(name, form='', gender='', level=6.0, ivs=(0, 15, 15)):
    return {'name': name, 'form': form, 'gender': gender, 'level': level,
            'atk_iv': ivs[0], 'def_iv': ivs[1], 'sta_iv': ivs[2],
            'is_shadow': False}


# --- the shared rule ----------------------------------------------------

def test_gender_allows_rule():
    idx = get_pokemon_index()
    # Female target needs a female row.
    assert gender_allows('female', 'Oinkologne (Female)', idx)
    assert not gender_allows('male', 'Oinkologne (Female)', idx)
    # Bare target with a (Female) sibling is the male form.
    assert gender_allows('male', 'Oinkologne', idx)
    assert not gender_allows('female', 'Oinkologne', idx)
    # Unknown gender is permissive (older Genie exports lack the column).
    assert gender_allows('', 'Oinkologne (Female)', idx)
    # Non-gender-differentiated species never filter.
    assert gender_allows('male', 'Tinkaton', idx)
    assert gender_allows('female', 'Tinkaton', idx)


def test_eligible_final_forms_lechonk():
    assert eligible_final_forms(_mon('Lechonk', gender='male')) == ['Oinkologne']
    assert eligible_final_forms(_mon('Lechonk', gender='female')) == [
        'Oinkologne (Female)']
    # Blank gender keeps both branches.
    assert eligible_final_forms(_mon('Lechonk')) == [
        'Oinkologne', 'Oinkologne (Female)']


# --- bottle_cap_advisor's walk -----------------------------------------

def test_bottle_cap_collect_owned_is_gender_aware():
    from bottle_cap_advisor import collect_owned
    owned = collect_owned(FIXTURE)
    female = owned[('Oinkologne (Female)', False)]
    male = owned[('Oinkologne', False)]
    assert female and male
    # The fixture's male-gendered spreads must not appear in the female
    # bucket and vice versa. 0/15/15 L6 is the fixture's male Oinkologne;
    # 0/15/13 L23 is a female one.
    assert (0, 15, 15) not in female
    assert (0, 15, 13) not in male


def test_bottle_cap_collect_owned_keeps_min_level_per_spread():
    from bottle_cap_advisor import collect_owned
    owned = collect_owned(FIXTURE)
    female = owned[('Oinkologne (Female)', False)]
    # Values are the lowest owned level per spread (most usable copy):
    # 0/15/4 exists as an L12 Oinkologne (Female) AND an L12 Lechonk.
    assert female[(0, 15, 4)] == pytest.approx(12.0)


def test_bottle_cap_usable_respects_capped_level():
    from bottle_cap_advisor import usable

    class _Tbl:
        rank_of = {(0, 15, 13): 1}
        level_of = {(0, 15, 13): 25.0}

    # Copy below the capped level fits; copy above it cannot exist there.
    assert usable(_Tbl, {(0, 15, 13): 23.0}, (0, 15, 13))
    assert not usable(_Tbl, {(0, 15, 13): 40.0}, (0, 15, 13))
    # Spread not in the table (over-CP at L1) never fits.
    assert not usable(_Tbl, {(1, 1, 1): 5.0}, (1, 1, 1))


# --- owned_breakdown's walk --------------------------------------------

def test_owned_breakdown_spreads_are_gender_aware():
    from owned_breakdown import collect_owned_spreads
    mons = parse_csv(FIXTURE)
    spreads, gskip, oskip = collect_owned_spreads(
        mons, 'Oinkologne (Female)', False, 'great', 51.0)
    assert spreads, 'fixture has female Oinkologne-line rows'
    assert (0, 15, 15) not in spreads  # the male copy
    assert gskip > 0


def test_owned_breakdown_min_level_guard():
    from owned_breakdown import collect_owned_spreads
    ivs = (0, 15, 13)
    cap_level = Pokemon.at_best_level(
        'Oinkologne (Female)', *ivs, league='great').level
    ok = _mon('Oinkologne', form='Female', gender='female',
              level=cap_level, ivs=ivs)
    over = _mon('Oinkologne', form='Female', gender='female',
                level=cap_level + 1.0, ivs=ivs)
    spreads, _, oskip = collect_owned_spreads(
        [ok, over], 'Oinkologne (Female)', False, 'great', 51.0)
    assert spreads == [ivs]
    assert oskip == 1
