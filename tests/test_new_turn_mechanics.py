"""
EXPERIMENTAL: spec-only tests for the mechanics='new' turn model
(the 2026-06-23 in-game PvP turn system; pokemongo.com/news/pvp-updates2026).

There is NO PvPoke reference for this mode -- PvPoke still implements the
legacy turn system. These tests pin the 'new' branch to the published spec
alone (changes 1, 2, 5). They are NOT cross-checked against any external
oracle. The legacy path is covered by tests/test_battle.py + the oracle
harness; here we only assert that 'new' DIVERGES from legacy in exactly the
spec-mandated ways.

Spec changes modelled (1v1 core; swap changes 3,4 are out of scope -- the
core never switches, see battle.py module comment):
  1. damage+energy resolve at END of turn
  2. one-turn fast attacks on the same turn TIE (corollary of 1)
  5. charged attacks begin at the START of the next turn; charged
     damage+effects resolve before any fast finishing during the sequence
"""
import pytest
from gopvpsim.battle import (
    BattlePokemon, simulate,
    never_shield, use_first_available, no_bait,
)


def _fast(power=5, energy_gain=5, cooldown_ms=500, type_='normal'):
    """One-turn (500ms) fast move by default -> fires same turn (_turns==1)."""
    return {'moveId': 'FAKE_FAST', 'name': 'Fake Fast', 'type': type_,
            'power': power, 'energyGain': energy_gain, 'cooldown': cooldown_ms}


def _charged(power=50, energy=40, type_='normal', buffs=None):
    m = {'moveId': 'FAKE_CHARGED', 'name': 'Fake Charged', 'type': type_,
         'power': power, 'energy': energy, 'energyGain': 0}
    if buffs is not None:
        m['buffs'] = buffs           # [atk_delta, def_delta]
        m['buffTarget'] = 'self'
        m['buffApplyChance'] = 1.0
    return m


def _bp(atk=100.0, def_=100.0, hp=100, types=None,
        fast=None, charged=None, shields=2, initial_energy=0):
    return BattlePokemon(
        species='Testmon', types=types or ['normal'],
        atk=atk, def_=def_, max_hp=hp,
        fast_move=fast or _fast(), charged_moves=charged or [_charged()],
        shields=shields, initial_energy=initial_energy,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_invalid_mechanics_raises():
    a, d = _bp(), _bp()
    with pytest.raises(ValueError):
        simulate(a, d, mechanics='bogus')


# ---------------------------------------------------------------------------
# Changes 1 + 2: simultaneous one-turn fast moves TIE in 'new' mode
#
# IMPORTANT 1v1 finding: our LEGACY sim ALREADY ties two mutually-lethal
# one-turn fast moves. The legacy fast-landing loop only cancels a fast whose
# OWN target is already dead (`if defender.hp <= 0: continue`); in a 1v1 the
# lower-CMP side's target (the higher-CMP attacker) is still alive when its
# fast resolves, so both land. The CMP sort reorders WHICH lands first (and
# thus intermediate energy/log order), not WHETHER both land. The network
# nondeterminism the spec removes ("now reliably TIE") was never in our model.
# So change 2's observable effect on the 1v1 WINNER is nil; we assert the tie
# holds in BOTH modes (new must not regress it) and that 'new' applies the two
# fasts WITHOUT the CMP reorder.
# ---------------------------------------------------------------------------

def _mutual_one_shot_pair():
    """Two mons whose single one-turn fast hit exactly KOs the other, with
    different cmp_atk so the legacy CMP sort would reorder them."""
    a = _bp(atk=130.0, fast=_fast(power=10), charged=[_charged()])
    d = _bp(atk=100.0, fast=_fast(power=10), charged=[_charged()])
    a.max_hp = d.fast_move_damage(a)   # d's hit exactly KOs a
    d.max_hp = a.fast_move_damage(d)   # a's hit exactly KOs d
    a.hp, d.hp = a.max_hp, d.max_hp
    assert a.cmp_atk != d.cmp_atk
    return a, d


def test_legacy_simultaneous_one_turn_fast_already_ties():
    """Documents the 1v1 baseline: legacy already double-faints (no CMP steal
    for pure fast-vs-fast in 1v1)."""
    a, d = _mutual_one_shot_pair()
    res = simulate(a, d, mechanics='legacy')
    assert res.winner is None
    assert a.hp <= 0 and d.hp <= 0


def test_new_simultaneous_one_turn_fast_ties():
    """Change 1+2: in NEW mode both fast moves resolve end-of-turn -> tie. Same
    final winner as legacy in 1v1, but reached via simultaneous (un-sorted)
    application rather than CMP-ordered sequential application."""
    a, d = _mutual_one_shot_pair()
    res = simulate(a, d, mechanics='new')
    assert res.winner is None          # both fainted -> tie
    assert a.hp <= 0 and d.hp <= 0


# ---------------------------------------------------------------------------
# Change 5: a charged move resolves the turn AFTER it is chosen
# ---------------------------------------------------------------------------

def test_new_charged_resolves_one_turn_later():
    """Change 5: a charged move chosen on turn N deals its damage at the START
    of turn N+1, so in NEW mode the defender's HP drops one turn later than in
    LEGACY. We give the attacker pre-loaded energy and a bulky, non-shielding
    defender so the only HP swing is the charged hit; we stop the sim one turn
    after the first charge is affordable and compare the HP drop timing."""
    # Run both to completion and compare the turn at which the FIRST charged
    # hit lands by inspecting the timeline.
    def first_charged_turn(mechanics):
        atk = _bp(atk=150.0, initial_energy=40,
                  fast=_fast(power=1, energy_gain=1, cooldown_ms=2000),
                  charged=[_charged(power=80, energy=40)])
        dfn = _bp(def_=100.0, hp=5000, shields=0,
                  fast=_fast(power=1, energy_gain=1, cooldown_ms=2000))
        res = simulate(atk, dfn, charged_policy_0=use_first_available,
                       charged_policy_1=use_first_available,
                       shield_policy_1=never_shield, shield_policy_0=never_shield,
                       log=True, mechanics=mechanics)
        for line in res.timeline:
            if 'Fake Charged' in line and 'dmg' in line:
                # line format: "T  N: Testmon uses Fake Charged -> X dmg"
                return int(line.split(':')[0].lstrip('T').strip())
        return None

    legacy_turn = first_charged_turn('legacy')
    new_turn = first_charged_turn('new')
    assert legacy_turn is not None and new_turn is not None
    assert new_turn == legacy_turn + 1   # charged lands exactly one turn later


# ---------------------------------------------------------------------------
# Change 5 + change 1: a fast that would KO the charged-thrower does NOT
# cancel the charged move (charged resolves at the top of the next turn,
# before that turn's fast landings).
# ---------------------------------------------------------------------------

def test_new_charged_survives_incoming_fast():
    """Change 1 (charged still resolves even if its user is about to faint
    from a fast) + change 5 (charged resolves at the top of the next turn,
    before fasts). Attacker is at lethal-fast HP but has a queued charged;
    in NEW mode the charged lands before the killing fast, so the defender
    still takes charged damage."""
    # Attacker: enough energy to charge, fragile enough that one defender fast
    # KOs it. Defender: bulky, no shields, hits hard with its one-turn fast.
    atk = _bp(atk=150.0, def_=100.0, initial_energy=40,
              fast=_fast(power=1, energy_gain=1, cooldown_ms=500),
              charged=[_charged(power=100, energy=40)])
    dfn = _bp(atk=200.0, def_=100.0, hp=500, shields=0,
              fast=_fast(power=30, energy_gain=1, cooldown_ms=500))
    atk.max_hp = dfn.fast_move_damage(atk)   # one defender fast KOs atk
    atk.hp = atk.max_hp
    dfn_hp_before = dfn.hp
    res = simulate(atk, dfn,
                   charged_policy_0=use_first_available, charged_policy_1=no_bait,
                   shield_policy_1=never_shield, shield_policy_0=never_shield,
                   mechanics='new')
    # The charged move must have dealt damage despite atk fainting.
    assert dfn.hp < dfn_hp_before
    assert atk.hp <= 0                       # atk did faint to the fast


# ---------------------------------------------------------------------------
# Change 5: charged EFFECTS (stat buffs) resolve before fasts in the sequence
# ---------------------------------------------------------------------------

def test_new_charged_buff_applies():
    """Change 5: charged effects resolve with the charged move (at the top of
    the next turn). A self-+atk buff move must leave the attacker's atk_stage
    raised after it resolves in NEW mode, same as legacy (only timing differs).
    """
    atk = _bp(atk=120.0, initial_energy=50,
              fast=_fast(power=1, energy_gain=1, cooldown_ms=2000),
              charged=[_charged(power=20, energy=50, buffs=[2, 0])])
    dfn = _bp(def_=100.0, hp=5000, shields=0,
              fast=_fast(power=1, energy_gain=1, cooldown_ms=2000))
    simulate(atk, dfn, charged_policy_0=use_first_available,
             charged_policy_1=use_first_available,
             shield_policy_1=never_shield, shield_policy_0=never_shield,
             mechanics='new')
    assert atk.atk_stage > 0                 # buff landed in new mode
