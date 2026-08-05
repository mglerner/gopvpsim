"""One move-ABBREVIATION rule, and it is derived from the move ID.

Companion to ``test_move_display_names.py``. Entry 7 of the 2026-08-05 DRY
review routed ``deep_dive_analysis.pretty_name`` through the gamemaster's
display label. The compare widget's short energy tags must NOT follow that
label: the gamemaster label carries punctuation and is not one-to-one with
the move id, so abbreviating it both truncates and collides ::

    WEATHER_BALL_FIRE   'Weather Ball (Fire)'  -> 'WB('   (was 'WBF')
    WEATHER_BALL_WATER  'Weather Ball (Water)' -> 'WB('   (was 'WBW')
    TECHNO_BLAST_DOUSE  'Techno Blast (Douse)' -> 'TB('   (was 'TBD')
    HIDDEN_POWER_BUG    'Hidden Power (Bug)'   -> 'HP('   (was 'HPB')
    X_SCISSOR           'X-Scissor'            -> 'X-S'   (was 'XS')
    AURA_WHEEL_DARK     'Aura Wheel'           -> 'AW'  } collision
    AURA_WHEEL_ELECTRIC 'Aura Wheel'           -> 'AW'  }

``deep_dive_analysis.move_abbr`` is the shared rule, kept on the id so its
output is byte-identical to the tags already baked into shipped pages
(userdata/website/ninetales-great-league: fast EMB, charged EB / WBF).

These tests pin:

* the shipped tags, and equality with the id-derived rule for EVERY
  gamemaster move (so adopting the helper changes no baked page);
* that no tag ever carries a display label's punctuation, and that
  same-family variants stay distinct;
* the concrete label-derived regression, so nobody "simplifies"
  ``move_abbr`` into ``pretty_name`` later;
* both open-coded copies of the rule -- ``iv_envelope_analysis._move_abbr``
  (agrees today) and ``deep_dive.py``'s nested ``_mv_abbr`` (does NOT; the
  call-site swap is out of this lane's file set, so it is an xfail with the
  deferral spelled out).
"""
import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(SCRIPTS))

from gopvpsim.data import load_gamemaster  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "deep_dive_analysis", SCRIPTS / "deep_dive_analysis.py")
deep_dive_analysis = importlib.util.module_from_spec(_spec)
sys.modules["deep_dive_analysis"] = deep_dive_analysis
_spec.loader.exec_module(deep_dive_analysis)

move_abbr = deep_dive_analysis.move_abbr
pretty_name = deep_dive_analysis.pretty_name


def _legacy_id_rule(mid):
    """The rule both call sites open-coded before the shared helper existed."""
    w = mid.replace('_', ' ').title().split()
    return (''.join(x[0] for x in w).upper() if len(w) > 1
            else (w[0][:3].upper() if w else '?'))


def _label_rule(mid):
    """What abbreviating the DISPLAY label gives -- the regression to avoid."""
    w = pretty_name(mid).split()
    return (''.join(x[0] for x in w).upper() if len(w) > 1
            else (w[0][:3].upper() if w else '?'))


def _all_move_ids():
    return [m['moveId'] for m in load_gamemaster()['moves']]


# ---- the tags themselves ----

SHIPPED_TAGS = [
    # (move id, tag). The first three are read straight off the shipped
    # Ninetales Great League bake's "energyMoves" blob (EMB fast; EB and
    # WBF charged), i.e. the tags a re-render must not change.
    ('EMBER', 'EMB'),
    ('ENERGY_BALL', 'EB'),
    ('WEATHER_BALL_FIRE', 'WBF'),
    ('WEATHER_BALL_WATER', 'WBW'),
    ('TECHNO_BLAST_DOUSE', 'TBD'),
    ('HIDDEN_POWER_BUG', 'HPB'),
    ('AURA_WHEEL_DARK', 'AWD'),
    ('AURA_WHEEL_ELECTRIC', 'AWE'),
    ('SPRINGTIDE_STORM', 'SS'),
    ('SHADOW_SNEAK', 'SS'),
    ('SUPER_POWER', 'SP'),
    ('X_SCISSOR', 'XS'),
    ('VICE_GRIP', 'VG'),
    ('CRUNCH', 'CRU'),
    ('ROAR_OF_TIME', 'ROT'),
]


@pytest.mark.parametrize('mid,tag', SHIPPED_TAGS)
def test_move_abbr_reproduces_shipped_tags(mid, tag):
    assert move_abbr(mid) == tag


def test_move_abbr_matches_id_rule_for_every_gamemaster_move():
    """No baked page changes when a call site adopts the helper."""
    bad = [(mid, move_abbr(mid), _legacy_id_rule(mid))
           for mid in _all_move_ids() if move_abbr(mid) != _legacy_id_rule(mid)]
    assert bad == []


def test_move_abbr_never_carries_display_punctuation():
    for mid in _all_move_ids():
        tag = move_abbr(mid)
        assert re.fullmatch(r"[A-Z0-9?]+", tag), (mid, tag)


@pytest.mark.parametrize('a,b', [
    ('WEATHER_BALL_FIRE', 'WEATHER_BALL_WATER'),
    ('AURA_WHEEL_DARK', 'AURA_WHEEL_ELECTRIC'),
    ('HIDDEN_POWER_BUG', 'HIDDEN_POWER_FIRE'),
])
def test_move_abbr_keeps_variants_distinct(a, b):
    assert move_abbr(a) != move_abbr(b)


def test_label_derived_abbreviation_is_the_regression_we_avoid():
    """Documents WHY move_abbr may not be folded into pretty_name."""
    assert _label_rule('WEATHER_BALL_FIRE') == 'WB('
    assert _label_rule('WEATHER_BALL_WATER') == 'WB('
    assert _label_rule('AURA_WHEEL_DARK') == _label_rule('AURA_WHEEL_ELECTRIC')
    assert move_abbr('WEATHER_BALL_FIRE') == 'WBF'
    assert move_abbr('WEATHER_BALL_WATER') == 'WBW'


def test_move_abbr_edge_cases():
    assert move_abbr('') == '?'
    assert move_abbr('_') == '?'
    assert move_abbr('X') == 'X'


# ---- the two open-coded copies ----

def test_iv_envelope_mirror_agrees_with_shared_helper():
    """iv_envelope_analysis._move_abbr claims to mirror the dive's tags.

    It still open-codes the id rule, so it agrees with the helper by value
    today; this pins that agreement until it is routed through move_abbr.
    """
    if "deep_dive" not in sys.modules:
        _dd = importlib.util.spec_from_file_location(
            "deep_dive", SCRIPTS / "deep_dive.py")
        _m = importlib.util.module_from_spec(_dd)
        sys.modules["deep_dive"] = _m
        _dd.loader.exec_module(_m)
    import iv_envelope_analysis as iva

    bad = [(mid, iva._move_abbr(mid), move_abbr(mid))
           for mid in _all_move_ids() if iva._move_abbr(mid) != move_abbr(mid)]
    assert bad == []


@pytest.mark.xfail(strict=True, reason=(
    "DEFERRED: deep_dive.py's nested _mv_abbr abbreviates _pretty_name(mid), "
    "so gamemaster labels with a parenthetical truncate (WBF -> 'WB(') and "
    "the two Weather Ball variants collide. The one-line fix is to call "
    "deep_dive_analysis.move_abbr, but scripts/deep_dive.py is outside the "
    "file set of the lane that added the helper. Flip this to a plain "
    "assertion when that call site lands."))
def test_deep_dive_energy_tag_uses_shared_helper():
    src = (SCRIPTS / "deep_dive.py").read_text()
    m = re.search(r"def _mv_abbr\(mid\):(?:\n.*){0,6}", src)
    assert m, "_mv_abbr no longer exists in deep_dive.py -- update this test"
    body = m.group(0)
    assert "move_abbr(" in body and "_pretty_name(" not in body


def test_no_new_open_coded_move_abbreviators():
    """Monotone guard: the initials idiom may leave scripts/, never spread.

    Removing a copy (by routing it through move_abbr) keeps this green;
    adding a fourth copy trips it.
    """
    canonical = "deep_dive_analysis.py"          # move_abbr itself lives here
    known = {"deep_dive.py", "iv_envelope_analysis.py"}
    found = set()
    for path in sorted(SCRIPTS.glob("*.py")):
        name = os.path.basename(str(path))
        if name == canonical:
            continue
        if re.search(r"join\(\w+\[0\] for \w+ in ", path.read_text()):
            found.add(name)
    assert found <= known, f"new open-coded move abbreviator: {found - known}"
