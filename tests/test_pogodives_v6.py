"""Sheet v6 (deep re-verification 2026-09-12): the two new tank rules.

Each behaviour fix ships with a cell that FAILS without it, pre-fix value
recorded (testing policy). Cells are built exactly as the dive tensors
are (cramorant_mini_sweep.make_focal / cramorant_policy_lab.make_bp with
the page's opponent IVs), so they are the tensor cells the campaign traced.
"""
import functools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
# ... and tests/, because this module imports test_battle helpers. Without
# it the file only ran when some EARLIER test had already put tests/ on the
# path -- so it was 2/4 red standalone, which is exactly how the Cramorant
# post-bake runbook says to run it. Same form as
# tests/test_deep_dive_builds.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gopvpsim.battle as B  # noqa: E402
from gopvpsim.battle import pogodives_dp, pvpoke_dp, simulate  # noqa: E402
from cramorant_policy_lab import make_bp  # noqa: E402
from cramorant_mini_sweep import make_focal  # noqa: E402

pytestmark = pytest.mark.integration


def _both(cram, opp, shields, bait=True):
    out = []
    for pol in (pvpoke_dp, pogodives_dp):
        cram.reset_for_battle(shields[0], opp)
        opp.reset_for_battle(shields[1], cram)
        cp = pol if bait else functools.partial(pol, bait_shields=False)
        out.append(simulate(cram, opp, charged_policy_0=cp,
                            charged_policy_1=pvpoke_dp).pvpoke_score(0))
    return tuple(out)


def test_2v2_last_shield_chip_guard_gl_corviknight():
    """The 720-cell grid's only bar failure. GL Peck / Hydro Pump + Surf,
    Cramorant 0/0/11 vs Corviknight (page IVs 4/12/14, Sand Attack /
    Air Cutter + Iron Head), 2v2, no-bait. Pre-fix: plain 662, PoGoDives
    300 (the 1.6 loaded-opponent tank declined the T34 Air Cutter on its
    last shield). Sand Attack chips 1 per turn, so the v6 chip guard
    shields there and the line is PvPoke's."""
    cram = make_focal('great', 'PECK', ['HYDRO_PUMP', 'SURF'], (0, 0, 11), 50)
    opp = make_bp('Corviknight', 'great', False, 'SAND_ATTACK',
                  ['AIR_CUTTER', 'IRON_HEAD'], ivs=(4, 12, 14))
    plain, pg = _both(cram, opp, (2, 2), bait=False)
    assert plain == 662
    assert pg == 662, f'pre-fix value was 300, got {pg}'


def test_1v0_terminal_ko_guard_ul_corviknight_cap51():
    """UL 1v0 top-100-SP negative (all Corviknight). Cramorant 0/15/15 at
    the best-buddy cap 51 vs Corviknight (page rank1 IVs 0/15/15), 1v0.
    Pre-fix: plain 765, PoGoDives 632 (declined a 43-damage Air Cutter to
    fire a missile one turn before its own Dive KO'd anyway). Under v6 the
    KO guard shields: our Dive KOs the hitter within two fast moves."""
    cram = make_focal('ultra', 'PECK', ['DIVE', 'FLY'], (0, 15, 15), 51)
    opp = make_bp('Corviknight', 'ultra', False, 'SAND_ATTACK',
                  ['AIR_CUTTER', 'IRON_HEAD'], ivs=(0, 15, 15))
    plain, pg = _both(cram, opp, (1, 0))
    assert plain == 765
    assert pg == 765, f'pre-fix value was 632, got {pg}'


def test_chip_guard_fires_only_on_last_shield_vs_non_chipper():
    """Unit probe of _cram_tank_mult under the (2,2) row: the guard is a
    pure function of (our shields, their fast damage per turn)."""
    from test_battle import make_bp as mk, make_fast, make_charged  # noqa: E402
    def mult(shields, fast_power, energy_after=60):
        cram = mk(atk=110, hp=130, fast=make_fast(power=6, energy_gain=8),
                  charged=[make_charged(power=65, energy=40)])
        opp = mk(atk=110, hp=140, fast=make_fast(power=fast_power, energy_gain=8),
                 charged=[make_charged(power=90, energy=45)])
        cram._pogodives = True
        cram._start_shields = (2, 2)
        cram.shields = shields
        return B._cram_tank_mult(opp, cram, 30, attacker_energy_after=energy_after)
    assert mult(2, 0) == 1.6, 'two shields: guard must not fire'
    assert mult(1, 0) == B._POGODIVES_TANK_CONSERVATIVE, 'last shield vs 1-dmg chip'
    assert mult(1, 40) == 1.6, 'last shield vs a real chipper: still aggressive'
    assert mult(1, 0, energy_after=10) == B._POGODIVES_TANK_CONSERVATIVE, 'unloaded'


def test_ko_guard_fires_only_when_our_charged_move_kos():
    from test_battle import make_bp as mk, make_fast, make_charged  # noqa: E402
    def mult(opp_hp, cram_energy, charged_power):
        cram = mk(atk=140, hp=130, fast=make_fast(power=6, energy_gain=8),
                  charged=[make_charged(power=charged_power, energy=40)])
        opp = mk(atk=110, hp=140, fast=make_fast(power=6, energy_gain=8),
                 charged=[make_charged(power=90, energy=45)])
        cram._pogodives = True
        cram._start_shields = (1, 0)
        cram.energy = cram_energy
        cram.hp = 50          # keep the HP lead under _POGODIVES_TANK_LEAD
        opp.hp = opp_hp       # so the lead rule cannot mask the guard
        return B._cram_tank_mult(opp, cram, 30, attacker_energy_after=60)
    assert mult(140, 40, 65) == 1.9, 'no KO available: loaded-opponent tank'
    assert mult(5, 40, 65) == B._POGODIVES_TANK_CONSERVATIVE, 'affordable KO now'
    assert mult(5, 24, 65) == B._POGODIVES_TANK_CONSERVATIVE, 'KO within two fast moves'
    assert mult(5, 20, 65) == 1.9, 'KO not reachable in two fast moves'


# --- Sheet v7 (2026-09-27): Surf-normalized 0v1 gate ----------------------

def test_0v1_surf_gate_gl_fly_surf_araquanid():
    """The only cramorant_certify GL bar failure after v6: GL Peck / Fly +
    Surf, start 0v1, vs plain Araquanid (page pvpoke-mode IVs 5/15/14 L32,
    Infestation / Water Pulse + Mirror Coat). Cramorant is the page's
    rank-1 spread 0/14/11. Shipped (sheet v6): plain 720, PoGoDives 551 --
    the (0,1) 'cmp' gate's 3.0 (fitted to Fly vs DIVE) admitted a Fly/Surf
    DPE ratio of 2.65, so a resisted Surf fired at T15 into a kept shield
    and two Mirror Coats followed. With the Surf-normalized 2.25 the gate
    stays shut and the line is PvPoke's."""
    cram = make_focal('great', 'PECK', ['FLY', 'SURF'], (0, 14, 11), 50)
    opp = make_bp('Araquanid', 'great', False, 'INFESTATION',
                  ['WATER_PULSE', 'MIRROR_COAT'], ivs=(5, 15, 14))
    plain, pg = _both(cram, opp, (0, 1))
    assert plain == 720
    assert pg == 720, f'shipped (pre-fix) value was 551, got {pg}'


def test_0v1_surf_gate_leaves_dive_pages_alone():
    """Byte-identity control for the v7 fix: a DIVE-gulp 0v1 cell where the
    gate DOES fire. GL Peck / Dive, Fly (index.html), rank-1 spread 0/14/11
    vs Azumarill (page rank1 IVs 0/15/15, Bubble / Ice Beam + Play Rough),
    0v1: the shipped tensor reads plain 346, PoGoDives 500; the fix must
    not move it (a DIVE gulp never reads 'surf_gate_dpe')."""
    cram = make_focal('great', 'PECK', ['DIVE', 'FLY'], (0, 14, 11), 50)
    opp = make_bp('Azumarill', 'great', False, 'BUBBLE',
                  ['ICE_BEAM', 'PLAY_ROUGH'], ivs=(0, 15, 15))
    plain, pg = _both(cram, opp, (0, 1))
    assert (plain, pg) == (346, 500)


def test_surf_gate_dpe_read_only_for_surf_gulp_at_0v1():
    """Unit probe: 'surf_gate_dpe' replaces the 3.0 only when the gulp move
    is SURF and only on the row that carries it ((0,1)); a DIVE gulp or a
    caller passing no id gets the row's usual value."""
    from test_battle import make_bp as mk, make_fast, make_charged  # noqa: E402

    def probe(start, gulp_move_id, cram_atk=120, opp_atk=100):
        cram = mk(atk=cram_atk, hp=130, fast=make_fast(power=6, energy_gain=8),
                  charged=[make_charged(power=65, energy=40)])
        opp = mk(atk=opp_atk, hp=140, fast=make_fast(power=6, energy_gain=8),
                 charged=[make_charged(power=90, energy=45)])
        cram._pogodives = True
        cram._start_shields = start
        return B._cram_dive_gate_dpe(cram, opp, gulp_move_id=gulp_move_id)

    PG, PV = B._POGODIVES_DIVE_GATE_DPE, B._CRAM_DIVE_GATE_DPE
    surf = B._POGODIVES_SHEET[(0, 1)]['surf_gate_dpe']
    assert surf == 2.25
    assert probe((0, 1), 'SURF') == surf
    assert probe((0, 1), 'DIVE') == PG
    assert probe((0, 1), None) == PG
    assert probe((0, 1), 'SURF', cram_atk=90) == PV      # cmp lost: still off
    assert probe((1, 1), 'SURF') == PG                   # other rows untouched
    assert all('surf_gate_dpe' not in row for k, row in B._POGODIVES_SHEET.items()
               if row is not None and k != (0, 1))
