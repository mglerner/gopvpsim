"""Tests for the mechanics='new' turn model -- the system the live game runs.

CORRECTED 2026-09-03. These used to pin our reading of the published spec
alone, with no reference to check against, and one of them pinned a MISREADING:
we took "charged attacks begin at the start of the next turn" literally and
deferred the charged move by a turn.

The live game does not work that way. Its order of operations is

    swaps > charged attacks (including their buffs/debuffs) > fast attacks

-- a priority ordering WITHIN a turn. Ground truth, with side-by-side footage
of both systems, is recorded in
docs/validations/2026-09-03_new_turn_system_ground_truth.md. PvPoke made and
then reverted the identical mistake (041d8c722 -> 442a4afe8).

Modelled here (1v1 core; the swap rules are out of scope -- the core never
switches, see the battle.py module comment):
  1. damage+energy resolve at END of turn
  2. one-turn fast attacks on the same turn TIE (corollary of 1)
  5. charged attacks resolve BEFORE fast damage, same turn, buffs included
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

def test_new_charged_resolves_the_same_turn_as_legacy_not_a_turn_later():
    """Charged priority is an ORDERING within a turn, not a deferral.

    Fail-first record: this test previously asserted
    ``new_turn == legacy_turn + 1`` and passed against the deferral model.
    That model was our misreading of the spec; the live game resolves the
    charged move on the turn it is thrown, ahead of fast damage.
    """
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
                return int(line.split(':')[0].lstrip('T').strip())
        return None

    legacy_turn = first_charged_turn('legacy')
    new_turn = first_charged_turn('new')
    assert legacy_turn is not None and new_turn is not None
    assert new_turn == legacy_turn, (
        f'charged landed on turn {new_turn} under new vs {legacy_turn} under '
        f'legacy; the live game resolves it the same turn, only ahead of fast '
        f'damage rather than after it')


def test_new_charged_debuff_applies_before_incoming_fast_damage():
    """THE discriminator between the two models, and what the footage shows.

    A self-DEFENCE-debuffing charged move thrown on the same turn an opposing
    fast lands: the live game applies the debuff first, so the fast hits the
    lowered defence. Under legacy the fast is computed against the un-debuffed
    defence.

    Tuned so the ordering decides an OUTCOME rather than a total. With this
    defender the same fast move deals 63 un-debuffed and 94 after -2 defence,
    so an attacker on exactly 94 HP is killed by the debuffed hit and survives
    the un-debuffed one with 31 left. A deferral model cannot produce this --
    it applies the debuff a turn after that fast has already landed.
    """
    LETHAL_IF_DEBUFFED = 94          # fast damage at -2 def (63 un-debuffed)

    def run(mechanics):
        atk = _bp(atk=150.0, def_=100.0, hp=LETHAL_IF_DEBUFFED,
                  initial_energy=40, shields=0,
                  fast=_fast(power=1, energy_gain=1, cooldown_ms=2000),
                  charged=[_charged(power=10, energy=40, buffs=[0, -2])])
        dfn = _bp(atk=200.0, def_=100.0, hp=5000, shields=0,
                  fast=_fast(power=40, energy_gain=1, cooldown_ms=500))
        res = simulate(atk, dfn,
                       charged_policy_0=use_first_available,
                       charged_policy_1=no_bait,
                       shield_policy_1=never_shield, shield_policy_0=never_shield,
                       log=True, mechanics=mechanics)
        return res, atk

    # sanity: the two damage figures the tuning rests on
    from gopvpsim.battle import _stat_stage_mult
    from gopvpsim.moves import damage as _dmg
    assert _dmg(40, 200.0, 100.0, 'normal', ['normal'], ['normal']) == 63
    assert _dmg(40, 200.0, 100.0 * _stat_stage_mult(-2), 'normal',
                ['normal'], ['normal']) == LETHAL_IF_DEBUFFED

    new_res, new_atk = run('new')
    leg_res, leg_atk = run('legacy')

    # the debuff landed in both, so this is about ORDER, not whether it fired
    assert new_atk.def_stage < 0 and leg_atk.def_stage < 0

    # new: debuff first -> the same fast now deals 94 into 94 HP -> dead.
    # legacy: fast first at 63 -> survives that turn. The battle ends sooner
    # under the live game's ordering.
    assert len(new_res.timeline) < len(leg_res.timeline), (
        f'new timeline {len(new_res.timeline)} vs legacy '
        f'{len(leg_res.timeline)}: applying the charged move\'s debuff BEFORE '
        f'the same-turn fast should make that fast lethal (94 >= 94 HP) where '
        f'legacy computes it un-debuffed (63) and the attacker survives')


# ---------------------------------------------------------------------------
# A fast that would KO the charged-thrower does NOT cancel the charged move:
# the charged resolves FIRST, while its user is still alive.
# ---------------------------------------------------------------------------

def test_new_charged_survives_incoming_fast():
    """Caleb's claim 1, and what the footage shows: throw on the turn a fast
    would KO you and the charged still lands, because it resolves ahead of the
    fast. If it does not KO, you faint immediately after -- which is asserted
    here too."""
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
# Charged EFFECTS (stat buffs) resolve with the charged move, ahead of fasts
# ---------------------------------------------------------------------------

def test_new_charged_buff_applies():
    """A self-+atk buff move leaves atk_stage raised in NEW mode, as in legacy.
    Ordering, not presence, is what differs between the models -- the sibling
    test above is the one that pins the ordering."""
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


# ---------------------------------------------------------------------------
# Scaffold invariant: the new-mechanics DECISION layer is PURE PLUMBING.
#
# Phase 1 (2026-06-24) threaded `mechanics` through the decision functions but
# ships new == legacy DECISIONS. Corpus-testing (3 workflows, ~20 focals x full
# GL pool x 9 shields) found legacy decisions are near-optimal on the new clock:
# the post-mortem-charged-survival RESOLUTION property already delivers the one
# edge a decision change would chase, and every aggressive early-commit lever
# either washed out or broke the non-regression floor. Full writeup +the one
# known deferred sub-optimality (a single Aegislash-Shield edge cell) live in
# docs/validations/new_mechanics_decision_layer_2026_06_24.md.
#
# These tests PIN that pure-plumbing guarantee: every decision function returns
# identical results for mechanics='new' vs 'legacy'. They are the TRIPWIRE for
# the deferred re-optimization -- if a future grounded change makes new
# decisions diverge, they fail ON PURPOSE, forcing that change to be
# corpus-floor-verified and these fixtures consciously updated.
# ---------------------------------------------------------------------------
from gopvpsim.battle import (pvpoke_dp, _calc_turns_to_live,
                             _optimize_move_timing, would_shield)


def _decision_pair(energy, hp, a_shields, d_shields):
    a = BattlePokemon(
        species='Atk', types=['normal'], atk=130.0, def_=120.0, max_hp=160,
        fast_move=_fast(power=3, energy_gain=8, cooldown_ms=500),
        charged_moves=[_charged(power=50, energy=40),
                       _charged(power=90, energy=55)],
        shields=a_shields, initial_energy=0,
    )
    d = BattlePokemon(
        species='Def', types=['normal'], atk=120.0, def_=110.0, max_hp=170,
        fast_move=_fast(power=6, energy_gain=7, cooldown_ms=1000),
        charged_moves=[_charged(power=60, energy=45)],
        shields=d_shields, initial_energy=30,
    )
    a.energy, a.hp = energy, hp
    for p in (a, d):   # simulate() normally stamps _turns; do it for the helpers
        p.fast_move['_turns'] = p.fast_move.get('cooldown', 500) // 500
    return a, d


# The cells below replace an itertools.product grid of
# energy[0,40,55,100] x hp[12,80,160] x a_sh[0,2] x d_sh[0,1,2] = 72 cells.
# Measured 2026-08-09: all 72 collapse to exactly THREE distinct output
# signatures over the four decision functions, and the partition depends
# only on (energy, d_sh) -- hp and a_sh never change any output here.
#
#   54 cells -> (pvpoke_dp=None, ttl=inf, timing=True,  shield=False)  energy < 100
#   12 cells -> (pvpoke_dp=0,    ttl=inf, timing=False, shield=False)  energy=100, d_sh>=1
#    6 cells -> (pvpoke_dp=1,    ttl=inf, timing=False, shield=False)  energy=100, d_sh=0
#
# Per-function distinct outputs: pvpoke_dp 3, _calc_turns_to_live 1,
# _optimize_move_timing 2, would_shield 1. Two representatives per signature
# (varying hp and a_sh across them, so the collapse claim itself stays
# spot-checked) preserve the full tripwire signal at 7 cells instead of 72.
#
# The signature collapse is an argument about OUTPUT VALUES, not about which
# code paths the inputs exercise -- so signature coverage alone is not enough
# for a tripwire aimed at a FUTURE re-optimization. Every distinct value of
# every axis is therefore kept, in particular energy=40: the attacker's
# charged moves cost 40 and 55, so 40 is the only state where it can afford
# EXACTLY ONE of them (0 = neither, 55/100 = both). A grounded bait /
# affordability change would diverge there and nowhere else, and dropping it
# made exactly that mutation invisible (caught in adversarial review
# 2026-08-09 -- it failed 18 of the original 72 cells and 0 of 6).
@pytest.mark.parametrize("energy,hp,a_sh,d_sh", [
    # signature A (54 cells): energy < 100
    (0, 12, 0, 0),
    (40, 80, 0, 1),    # the only "exactly one charged move affordable" state
    (55, 160, 2, 2),
    # signature B (12 cells): energy = 100, defender has shields
    (100, 80, 0, 1),
    (100, 12, 2, 2),
    # signature C (6 cells): energy = 100, defender unshielded
    (100, 12, 0, 0),
    (100, 160, 2, 0),
])
def test_new_decisions_identical_to_legacy(energy, hp, a_sh, d_sh):
    """Pure-plumbing invariant: new == legacy for every decision function.
    Rebuild a fresh pair before each call so one function's caching/temporary
    stat-stage mutation can't leak into the next."""
    a, d = _decision_pair(energy, hp, a_sh, d_sh)
    assert pvpoke_dp(a, d, mechanics='new') == pvpoke_dp(a, d, mechanics='legacy')
    a, d = _decision_pair(energy, hp, a_sh, d_sh)
    assert (_calc_turns_to_live(a, d, mechanics='new')
            == _calc_turns_to_live(a, d, mechanics='legacy'))
    a, d = _decision_pair(energy, hp, a_sh, d_sh)
    assert (_optimize_move_timing(a, d, mechanics='new')
            == _optimize_move_timing(a, d, mechanics='legacy'))
    a, d = _decision_pair(energy, hp, a_sh, d_sh)
    assert (would_shield(a, d, a.charged_moves[0], mechanics='new')
            == would_shield(a, d, a.charged_moves[0], mechanics='legacy'))
