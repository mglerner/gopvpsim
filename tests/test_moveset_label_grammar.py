"""One moveset-label grammar, on the Python side.

AFK deferral churn 2026-08-08, register item a-moveset-label-splits (DRY
review 2026-08-05 entry 5).

A raw moveset label is ``'FAST / CM1, CM2'``. Entry 5 landed
``parse_moveset_label`` and baked its output into ``DATA.movesets[i]
.fast/.charged`` so page-side readers never re-parse the display string --
but three Python readers kept hand-splitting it:

  * ``deep_dive_analysis.pretty_moveset``   -- ``label.split(' / ')``
  * ``deep_dive_analysis.build_move_tuples`` -- ditto, plus ``split(',')``
  * ``deep_dive_narrative``'s charmer check  -- ``label.split(' / ')[0]``

They now read the baked field where there is one and go through the shared
grammar otherwise. These tests pin the grammar's single definition, the
absence of hand-splits, and the two behaviours that were easy to lose in
the conversion (all-fast labels, and the charmer check preferring the
field over the label).
"""
import os
import re
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
for _p in (os.path.join(REPO_ROOT, 'src'), SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import deep_dive_analysis as analysis  # noqa: E402
import deep_dive_narrative as narrative  # noqa: E402
import deep_dive_rendering as rendering  # noqa: E402

# Every Python file that reads a raw moveset label apart.
LABEL_READERS = [
    'scripts/deep_dive_analysis.py',
    'scripts/deep_dive_narrative.py',
    'scripts/deep_dive_rendering.py',
    'scripts/generate_article.py',
]

# A hand-split of a *label* variable. Deliberately anchored on the variable
# name rather than on the ``' / '`` separator alone: deep_dive_narrative also
# splits FLAVOR NAMES on ' / ' ("Azumarill / Medicham Slayer"), which is a
# different grammar and must not be swept in here.
_HAND_SPLIT = re.compile(r"""\w*label\w*\.split\(""")


# ---------------------------------------------------------------------------
# One definition, several names
# ---------------------------------------------------------------------------

def test_grammar_has_exactly_one_definition():
    hits = [rel for rel in LABEL_READERS
            if 'def parse_moveset_label(' in
            open(os.path.join(REPO_ROOT, rel)).read()]
    assert hits == ['scripts/deep_dive_analysis.py']


def test_rendering_re_exports_the_same_function():
    """``deep_dive_rendering.parse_moveset_label`` is the name the dive bake
    and generate_article import; it must not become a second copy.

    Import-edge and behaviour, NOT ``is`` -- same reason as
    ``test_move_abbr.test_iv_envelope_uses_shared_helper``: sibling test
    modules (``test_move_abbr``, ``test_envelope_positions``) load
    ``deep_dive_analysis`` through ``spec_from_file_location`` and replace
    the ``sys.modules`` entry, so whichever runs first wins and a full-suite
    run can legitimately hold two instances of the module. ``rendering``'s
    re-export is a module-import-time snapshot, so under one collection
    order it snapshots the other instance's function and an identity
    comparison fails on a codebase that is perfectly correct. Production
    imports the module once, so the thing worth pinning is the EDGE -- no
    second definition (see the test above), both names sourced from
    ``deep_dive_analysis``, identical answers.
    """
    rendering_src = open(
        os.path.join(SCRIPTS_DIR, 'deep_dive_rendering.py')).read()
    assert re.search(r'^parse_moveset_label = analysis\.parse_moveset_label$',
                     rendering_src, re.M), \
        'deep_dive_rendering no longer re-exports THE grammar'

    narrative_src = open(
        os.path.join(SCRIPTS_DIR, 'deep_dive_narrative.py')).read()
    imported = re.search(r'^from deep_dive_analysis import \(([^)]*)\)',
                         narrative_src, re.M)
    assert imported and 'parse_moveset_label' in [
        n.strip() for n in imported.group(1).split(',')], \
        'deep_dive_narrative no longer imports THE grammar'

    for mod in (rendering, narrative):
        assert mod.parse_moveset_label.__module__ == 'deep_dive_analysis'
        assert mod.parse_moveset_label.__qualname__ == 'parse_moveset_label'
        for label in ('FAIRY_WIND / BULLDOZE, GIGATON_HAMMER',
                      'COUNTER / DYNAMIC_PUNCH', 'COUNTER', ''):
            assert (mod.parse_moveset_label(label)
                    == analysis.parse_moveset_label(label))


def _grammar_line():
    src = open(os.path.join(SCRIPTS_DIR, 'deep_dive_analysis.py')).read()
    for i, line in enumerate(src.splitlines(), 1):
        if line.strip() == "fast, rest = label.split('/', 1)":
            return i
    raise AssertionError('parse_moveset_label body not found')


def test_no_reader_hand_splits_the_label():
    offenders = []
    for rel in LABEL_READERS:
        src = open(os.path.join(REPO_ROOT, rel)).read()
        for i, line in enumerate(src.splitlines(), 1):
            if line.strip().startswith('#'):
                continue
            if _HAND_SPLIT.search(line):
                offenders.append(f'{rel}:{i}: {line.strip()}')
    # parse_moveset_label's own body is the single exception.
    assert offenders == [
        "scripts/deep_dive_analysis.py:%d: fast, rest = label.split('/', 1)"
        % _grammar_line()
    ], offenders
    # Guard the guard: the pattern matched the sites that were removed, and
    # leaves the flavor-name split alone.
    assert _HAND_SPLIT.search("    parts = label.split(' / ')")
    assert _HAND_SPLIT.search("    parts = moveset_label.split(' / ')")
    assert _HAND_SPLIT.search('fast_part = label.split(" / ")[0]')
    assert not _HAND_SPLIT.search("    for part in stub.split(' / '):")


@pytest.mark.parametrize('label,expected', [
    ('FAIRY_WIND / BULLDOZE, GIGATON_HAMMER',
     ('FAIRY_WIND', ['BULLDOZE', 'GIGATON_HAMMER'])),
    ('COUNTER / DYNAMIC_PUNCH', ('COUNTER', ['DYNAMIC_PUNCH'])),
    ('COUNTER', ('COUNTER', [])),
])
def test_grammar_shape(label, expected):
    assert analysis.parse_moveset_label(label) == expected


# ---------------------------------------------------------------------------
# Behaviours the conversion had to preserve
# ---------------------------------------------------------------------------

def test_pretty_moveset_leaves_an_all_fast_label_alone():
    """No charged half -> the label is returned verbatim, as before."""
    assert analysis.pretty_moveset('SUPER_POWER') == 'SUPER_POWER'


def test_build_move_tuples_yields_nothing_for_an_all_fast_label():
    fast_db = {'COUNTER': {'power': 8, 'type': 'fighting'}}
    assert analysis.build_move_tuples('COUNTER', fast_db, {}) == []


def test_build_move_tuples_keeps_fast_first_then_charged_in_order():
    fast_db = {'COUNTER': {'power': 8, 'type': 'fighting'}}
    charged_db = {'DYNAMIC_PUNCH': {'power': 90, 'type': 'fighting'},
                  'ICE_BEAM': {'power': 90, 'type': 'ice'}}
    got = analysis.build_move_tuples('COUNTER / ICE_BEAM, DYNAMIC_PUNCH',
                                     fast_db, charged_db)
    assert got == [('COUNTER', 8, 'fighting'),
                   ('ICE_BEAM', 90, 'ice'),
                   ('DYNAMIC_PUNCH', 90, 'fighting')]


# ---------------------------------------------------------------------------
# The charmer check reads the baked field
# ---------------------------------------------------------------------------

_CHARMER_LINE = 'Charm-class fast moves'
_FLAVORS = [{'name': 'General', 'is_general': True, 'atk_cut': 0,
             'def_cut': 0, 'hp_cut': 0, 'stat_sig': '0/15/15',
             'members': [0]}]


def _has_charmer_line(moveset):
    data_obj = {'species': 'Altaria', 'league': 'great',
                'movesets': [moveset]}
    html = narrative.render_narrative_zone(_FLAVORS, {}, [], data_obj, 'opp')
    return _CHARMER_LINE in html


def test_charmer_check_prefers_the_baked_fast_field():
    """``fast`` wins over the label in BOTH directions, so a label the dive
    happens to spell differently can't flip the framing."""
    assert _has_charmer_line({'label': 'COUNTER / DYNAMIC_PUNCH',
                              'fast': 'CHARM'})
    assert not _has_charmer_line({'label': 'CHARM / MOONBLAST',
                                  'fast': 'COUNTER'})


def test_charmer_check_falls_back_to_the_shared_grammar():
    """Pre-entry-5 DATA blobs have no ``fast`` field."""
    assert _has_charmer_line({'label': 'CHARM / MOONBLAST'})
    assert _has_charmer_line({'label': 'CHARM'})
    assert not _has_charmer_line({'label': 'COUNTER / DYNAMIC_PUNCH'})
