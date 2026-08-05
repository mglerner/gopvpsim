"""One move-id-to-label rule across the dive and article renderers.

Before the DRY fix, ``deep_dive_analysis.pretty_name`` used naive Title
Case while ``generate_article``'s per-form headers and the narrative
renderer used the gamemaster's own ``name`` field. 39 of the 334
gamemaster moves disagree between the two rules, so a single page could
print "Super Power" in one table and "Superpower" in the next.

These tests pin:

* the divergent pairs themselves (Superpower, X-Scissor, Hidden Power,
  Vise Grip, V-Create, Power-Up Punch),
* agreement between all three entry points for EVERY gamemaster move,
* the Title-Case fallback for moves the gamemaster doesn't know, and
* that no open-coded ``.replace('_', ' ').title()`` has crept back into
  the two renderers.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from gopvpsim.data import load_gamemaster  # noqa: E402

import auto_gen_narrative  # noqa: E402
from auto_gen_narrative import (  # noqa: E402
    _gm_move_display,
    _title_case_move,
    move_display,
)
from deep_dive_analysis import pretty_moveset, pretty_name  # noqa: E402

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scripts')

# Move ids whose gamemaster display name disagrees with naive Title Case.
# These are the labels that used to render two ways on one page.
DIVERGENT = [
    ('SUPER_POWER', 'Superpower'),
    ('X_SCISSOR', 'X-Scissor'),
    ('V_CREATE', 'V-Create'),
    ('VICE_GRIP', 'Vise Grip'),
    ('POWER_UP_PUNCH', 'Power-Up Punch'),
    ('ROAR_OF_TIME', 'Roar of Time'),
    ('NATURES_MADNESS', "Nature's Madness"),
    ('HIDDEN_POWER_BUG', 'Hidden Power (Bug)'),
    ('HIDDEN_POWER_NORMAL', 'Hidden Power'),
    ('WEATHER_BALL_FIRE', 'Weather Ball (Fire)'),
]


@pytest.fixture(autouse=True)
def _clear_display_caches():
    auto_gen_narrative._reset_move_display_caches()
    yield
    auto_gen_narrative._reset_move_display_caches()


@pytest.mark.parametrize('move_id,expected', DIVERGENT)
def test_pretty_name_uses_the_gamemaster_label(move_id, expected):
    assert pretty_name(move_id) == expected


@pytest.mark.parametrize('move_id,expected', DIVERGENT)
def test_title_case_really_did_disagree(move_id, expected):
    """Guard the guard: if these ever stop diverging the test is vacuous."""
    assert _title_case_move(move_id) != expected


def test_pretty_moveset_routes_every_segment_through_the_rule():
    label = 'SUPER_POWER / X_SCISSOR, VICE_GRIP'
    assert pretty_moveset(label) == 'Superpower / X-Scissor, Vise Grip'


def test_all_three_entry_points_agree_on_every_gamemaster_move():
    """The DRY guard proper: one rule, three callers, 334 moves."""
    gm = load_gamemaster()
    mismatches = []
    for m in gm['moves']:
        move_id = m['moveId']
        by_default = pretty_name(move_id)
        by_blob = move_display(move_id, gm=gm)
        by_narrative = _gm_move_display(gm, move_id)
        if not (by_default == by_blob == by_narrative == m['name']):
            mismatches.append((move_id, m['name'], by_default, by_blob,
                               by_narrative))
    assert mismatches == []


def test_display_name_is_accepted_as_input():
    """Round-trips a display name (fast_move_class passes these around)."""
    assert pretty_name('Superpower') == 'Superpower'
    assert pretty_name('Dragon Breath') == 'Dragon Breath'


@pytest.mark.parametrize('raw,expected', [
    ('MADE_UP_MOVE', 'Made Up Move'),
    ('mud_slap', 'Mud Slap'),
    ('  SUPER_POWER  ', 'Superpower'),
    ('', ''),
])
def test_unknown_moves_fall_back_to_title_case(raw, expected):
    assert pretty_name(raw) == expected


def test_explicit_empty_gamemaster_forces_the_fallback():
    """`_gm_move_display(None, ...)` must not go load a gamemaster."""
    assert _gm_move_display(None, 'SUPER_POWER') == 'Super Power'
    assert _gm_move_display({}, 'X_SCISSOR') == 'X Scissor'
    assert move_display('SUPER_POWER', gm={}) == 'Super Power'


def test_caller_supplied_blob_wins_over_the_default():
    fake = {'moves': [{'moveId': 'SUPER_POWER', 'name': 'Fake Name'}]}
    assert move_display('SUPER_POWER', gm=fake) == 'Fake Name'
    # Unknown to the fake blob -> fallback, not the real gamemaster.
    assert move_display('X_SCISSOR', gm=fake) == 'X Scissor'


def test_index_cache_is_keyed_on_object_identity():
    fake_a = {'moves': [{'moveId': 'A_MOVE', 'name': 'Alpha'}]}
    assert move_display('A_MOVE', gm=fake_a) == 'Alpha'
    fake_b = {'moves': [{'moveId': 'A_MOVE', 'name': 'Beta'}]}
    assert move_display('A_MOVE', gm=fake_b) == 'Beta'
    assert move_display('A_MOVE', gm=fake_a) == 'Alpha'


def test_entries_without_a_name_do_not_shadow_later_ones():
    gm = {'moves': [{'moveId': 'DUP', 'name': ''},
                    {'moveId': 'OTHER', 'name': 'Dup'}]}
    # Empty-name entries are skipped, so 'dup' resolves via the display
    # name of the second entry -- what the original linear scan did.
    assert move_display('DUP', gm=gm) == 'Dup'


def test_article_per_form_header_uses_the_gamemaster_label():
    """The article's "old default" column header shares the dive's rule.

    This header used to be built with an open-coded
    ``.replace('_', ' ').title()`` while the CD-move header beside it
    read its name out of the gamemaster, so one table printed both
    'Super Power' and 'Superpower'.
    """
    import generate_article as ga

    gm = load_gamemaster()
    form = {
        'label': 'Base', 'league': 'great', 'species_id': '',
        'dive_slug': None, 'default_fast_id': 'SUPER_POWER',
        'opponents': ['Azumarill'],
        'best_cd': {'label': 'X_SCISSOR / VICE_GRIP, SUPER_POWER',
                    'pretty_label': 'X-Scissor / Vise Grip, Superpower',
                    'per_opponent_win_rate': [0.61], 'anchored_opps': set()},
        'best_default': {'label': 'SUPER_POWER / VICE_GRIP',
                         'pretty_label': 'Superpower / Vise Grip',
                         'per_opponent_win_rate': [0.42],
                         'anchored_opps': set()},
    }
    out = ga._render_matchup_delta_per_form_section('X_SCISSOR', [form], gm)
    assert 'Superpower WR' in out
    assert 'Super Power' not in out


@pytest.mark.parametrize('filename', [
    'deep_dive_analysis.py',
    'generate_article.py',
    'auto_gen_narrative.py',
])
def test_no_open_coded_title_case_move_labels(filename):
    """No renderer may re-derive a move label with `.title()`."""
    src = open(os.path.join(SCRIPTS_DIR, filename)).read()
    offenders = re.findall(r"replace\(\s*'_',\s*' '\s*\)\.title\(\)", src)
    assert offenders == [], f'{filename} re-implements the move-label rule'
