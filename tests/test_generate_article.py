"""CD-move-kind handling in scripts/generate_article.py.

Pins the 2026-07-04 change that lets the CD-article generator handle CD
moves that are *charged* (starter nukes: Hydro Cannon / Blast Burn /
Frenzy Plant) as well as the *fast*-move CDs (Mud Slap) it was written
for. The generator's cd/default moveset partition used to be keyed on
the fast move only (``_moveset_fast_move(label) == cd_id``), so a
charged CD move never matched any moveset and every scored section
(Meta Coverage / Verdict / Matchup Delta) emitted a TODO placeholder.

Two properties matter and are tested here:
  1. FAST-move CDs behave exactly as before (Oinkologne regression) --
     the new helpers' fast branch is logically identical to the old
     inline filters.
  2. CHARGED-move CDs partition by "features the CD charged move" vs
     "does not" (the pre-CD charged pool we compare against).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "generate_article", REPO_ROOT / "scripts" / "generate_article.py")
ga = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ga)


# ---- move-kind discriminator (energy cost distinguishes charged) ----

def test_cd_move_is_fast():
    # Fast move: no energy cost, positive energy gain (e.g. Water Gun).
    assert ga._cd_move_is_fast({'energy': 0, 'energyGain': 3}) is True
    # Charged move: positive energy cost (e.g. Hydro Cannon).
    assert ga._cd_move_is_fast({'energy': 40, 'energyGain': 0}) is False
    # Missing keys default to fast (no cost known).
    assert ga._cd_move_is_fast({}) is True


def test_moveset_charged_moves():
    assert ga._moveset_charged_moves(
        'WATER_GUN / HYDRO_CANNON, SHADOW_BALL') == \
        ['HYDRO_CANNON', 'SHADOW_BALL']
    # Single charged move.
    assert ga._moveset_charged_moves('WATER_GUN / HYDRO_CANNON') == \
        ['HYDRO_CANNON']


# ---- FAST-move CD: Oinkologne regression (behavior unchanged) ----

@pytest.mark.parametrize("label,is_cd,is_default", [
    # Mud Slap build IS the CD build, NOT the (Tackle) default.
    ('MUD_SLAP / BODY_SLAM, TRAILBLAZE', True, False),
    # Tackle build is NOT the CD build, IS the default.
    ('TACKLE / BODY_SLAM, TRAILBLAZE', False, True),
])
def test_fast_cd_partition_matches_legacy(label, is_cd, is_default):
    cd_id, default_fast_id, cd_is_fast = 'MUD_SLAP', 'TACKLE', True
    assert ga._moveset_matches_cd(label, cd_id, cd_is_fast) is is_cd
    assert ga._moveset_is_default(
        label, cd_id, cd_is_fast, default_fast_id) is is_default
    # The legacy inline filter this replaced, asserted equivalent:
    assert ga._moveset_matches_cd(label, cd_id, cd_is_fast) == \
        (ga._moveset_fast_move(label) == cd_id)
    assert ga._moveset_is_default(label, cd_id, cd_is_fast, default_fast_id) \
        == (ga._moveset_fast_move(label) == default_fast_id)


# ---- CHARGED-move CD: Inteleon / Hydro Cannon (new behavior) ----

@pytest.mark.parametrize("label,is_cd,is_default", [
    # Any build featuring Hydro Cannon is a CD build, not a default.
    ('WATER_GUN / HYDRO_CANNON, SHADOW_BALL', True, False),
    ('WATER_GUN / HYDRO_CANNON, SNIPE_SHOT', True, False),
    ('WATER_GUN / HYDRO_CANNON', True, False),           # single charged
    # The pre-CD build (no Hydro Cannon) is the default we compare against.
    ('WATER_GUN / SHADOW_BALL, SNIPE_SHOT', False, True),
])
def test_charged_cd_partition(label, is_cd, is_default):
    # default_fast_id is irrelevant for a charged CD; pass the shared fast.
    cd_id, default_fast_id, cd_is_fast = 'HYDRO_CANNON', 'WATER_GUN', False
    assert ga._moveset_matches_cd(label, cd_id, cd_is_fast) is is_cd
    assert ga._moveset_is_default(
        label, cd_id, cd_is_fast, default_fast_id) is is_default
