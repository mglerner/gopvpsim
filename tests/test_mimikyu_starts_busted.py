"""Mimikyu (Busted) as a starts-busted focal: the permanent -1 def must be
present from turn one.

WHY THERE IS NO DIRECT PvPoke ORACLE HERE
-----------------------------------------
The obvious validation -- build ``mimikyu_busted`` directly in PvPoke
(scripts/pvpoke_trace.js --p1 mimikyu_busted) and compare -- is WRONG and
mismatches by design. PvPoke applies a form's ``nativeStatBuffs`` only via
the in-battle ``changeForm()`` transition (Pokemon.js:2369-2373 calls
``applyStatBuffs([0,-1])`` when the disguise busts mid-battle). Building the
alt form directly never calls ``changeForm``, so PvPoke's direct
``mimikyu_busted`` sits at FULL defense -- a build-path artifact, not the real
post-bust state. (Confirmed 2026-06-27 by reading Battle.js:1555-1558 +
Pokemon.js changeForm.)

The REAL, in-game post-bust state carries -1 def, and OUR in-battle disguise
bust applies exactly that (formchange.apply_form_change, validated against
PvPoke by the Mimikyu cells in test_form_change_oracle.py). So a
"starts busted" focal is validated by EQUIVALENCE: it must equal the state a
normal Mimikyu reaches the instant its disguise busts. That equivalence --
not a direct-build comparison -- is what these tests pin.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon, _extract_battle_log  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402

BUSTED = ('Mimikyu (Busted)', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'], 'great')
DISGUISE = ('Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'], 'great')
AZU = ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], 'great')


def test_starts_busted_stat_state():
    """Busted focal starts at def_stage -1 and survives the scenario reset."""
    bp = _make_battle_pokemon(*BUSTED[:4], 1, 4, 15, 15, max_level=51.0)
    assert (bp.atk_stage, bp.def_stage) == (0, -1)
    assert (bp.initial_atk_stage, bp.initial_def_stage) == (0, -1)
    # reset_for_battle (used per shield scenario by the dive workers) must
    # restore the native -1, not re-zero it.
    bp.reset_for_battle(2)
    assert (bp.atk_stage, bp.def_stage) == (0, -1)


def test_base_mimikyu_unaffected():
    """The Disguise (base) form carries no native stat buff."""
    bp = _make_battle_pokemon(*DISGUISE[:4], 1, 4, 15, 15, max_level=51.0)
    assert (bp.atk_stage, bp.def_stage) == (0, 0)


def test_starts_busted_equals_post_in_battle_bust():
    """A normal Mimikyu that busts in-battle reaches def_stage -1 / 'Mimikyu
    (Busted)' -- the exact state the starts-busted focal begins in."""
    mk = _make_battle_pokemon(*DISGUISE[:4], 2, 4, 15, 15, max_level=51.0)
    az = _make_battle_pokemon(*AZU[:4], 2, 4, 15, 13, max_level=51.0)
    assert mk.def_stage == 0 and mk._form_disguise_active
    simulate(mk, az, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp, log=True)
    assert mk.species == 'Mimikyu (Busted)'
    assert mk._form_is_alt and not mk._form_disguise_active
    assert mk.def_stage == -1
    # ...and the starts-busted focal begins exactly there.
    bust = _make_battle_pokemon(*BUSTED[:4], 2, 4, 15, 15, max_level=51.0)
    assert bust.def_stage == mk.def_stage == -1


def test_minus_one_def_increases_incoming_damage():
    """The -1 def stage must actually feed the damage formula (not be cosmetic)."""
    a = _make_battle_pokemon(*BUSTED[:4], 0, 4, 15, 15, max_level=51.0)
    d = _make_battle_pokemon(*AZU[:4], 0, 4, 15, 13, max_level=51.0)
    dmg_busted = d.charged_move_damage(d.charged_moves[0], a)
    a.def_stage = 0                       # force full defense
    a._dmg_cache_opp = None
    d._dmg_cache_opp = None
    dmg_full = d.charged_move_damage(d.charged_moves[0], a)
    assert dmg_busted > dmg_full          # 48 vs 39 (Ice Beam, 2026-06-27)


# Snapshot of OUR validated engine (equivalence-validated above), NOT a
# PvPoke direct-build comparison. Locks score+winner+chargedLog against
# regressions in the starts-busted path.
@pytest.mark.parametrize("s1,s2,score0,score1,winner,log", [
    (0, 0, 337, 662, 1, ['Mimikyu (Busted): Play Rough', 'Azumarill: Play Rough']),
    (0, 1, 172, 827, 1, ['Mimikyu (Busted): Shadow Sneak (shielded)', 'Azumarill: Play Rough']),
    (0, 2, 172, 827, 1, ['Mimikyu (Busted): Shadow Sneak (shielded)', 'Azumarill: Play Rough']),
    (1, 0, 714, 285, 0, ['Mimikyu (Busted): Play Rough', 'Azumarill: Ice Beam (shielded)', 'Mimikyu (Busted): Play Rough']),
    (1, 1, 337, 662, 1, ['Mimikyu (Busted): Shadow Sneak (shielded)', 'Azumarill: Ice Beam (shielded)', 'Mimikyu (Busted): Shadow Sneak', 'Azumarill: Ice Beam']),
    (1, 2, 188, 811, 1, ['Mimikyu (Busted): Shadow Sneak (shielded)', 'Azumarill: Ice Beam (shielded)', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Azumarill: Ice Beam']),
    (2, 0, 714, 285, 0, ['Mimikyu (Busted): Play Rough', 'Azumarill: Ice Beam (shielded)', 'Mimikyu (Busted): Shadow Sneak']),
    (2, 1, 626, 373, 0, ['Mimikyu (Busted): Shadow Sneak (shielded)', 'Azumarill: Ice Beam (shielded)', 'Mimikyu (Busted): Shadow Sneak', 'Azumarill: Play Rough (shielded)', 'Mimikyu (Busted): Shadow Sneak']),
    (2, 2, 460, 539, 1, ['Mimikyu (Busted): Shadow Sneak (shielded)', 'Azumarill: Ice Beam (shielded)', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Azumarill: Ice Beam (shielded)', 'Mimikyu (Busted): Play Rough', 'Azumarill: Ice Beam']),
])
def test_starts_busted_vs_azumarill_snapshot(s1, s2, score0, score1, winner, log):
    a = _make_battle_pokemon(*BUSTED[:4], s1, 4, 15, 15, max_level=51.0)
    d = _make_battle_pokemon(*AZU[:4], s2, 4, 15, 13, max_level=51.0)
    r = simulate(a, d, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp, log=True)
    assert (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)), r.winner) == (score0, score1, winner)
    assert _extract_battle_log(r) == log
