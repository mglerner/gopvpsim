"""The "PoGoDives strat" overlay (tier 3): per-side semantics, the
non-Cramorant fallback invariant, and the adaptive tank rule.

Design: docs/cramorant_policy_plan.md; evidence:
docs/validations/cramorant_policy_lab_2026_08_24.md. The overlay is a
marker on the policy callables -- simulate() sets each side's
`_pogodives` flag at battle start, and the Cramorant-gated rules read
the DECIDING side's flag (dive gate: the attacker; tank rule: the
shield-deciding defender, in both the actual decision and would_shield's
model).

FAILING-FIRST RECORD: against the pre-overlay tree these tests fail on
import (`pogodives_dp` does not exist).
"""
import functools

import pytest

from gopvpsim.battle import (
    _has_pogodives_marker,
    pogodives_dp,
    pogodives_shield,
    pvpoke_dp,
    pvpoke_simulate_shield,
    simulate,
    would_shield,
)

from .test_battle import _extract_battle_log, _make_battle_pokemon, make_bp, \
    make_charged, make_fast


def _pair(spec1, spec2, s1, s2):
    sp, fast, charged, ivs = spec1
    a = _make_battle_pokemon(sp, fast, charged, 'great', s1, *ivs)
    sp, fast, charged, ivs = spec2
    b = _make_battle_pokemon(sp, fast, charged, 'great', s2, *ivs)
    return a, b


# Non-Cramorant pairs -- includes an Aegislash pair on purpose: it is in
# the port's MIGRATION predicate family but is NOT a pogodives case, so
# it must alias too.
_FALLBACK_PAIRS = [
    (('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13)),
     ('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], (7, 15, 14))),
    (('Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST'], (15, 15, 15)),
     ('Lickitung', 'LICK', ['BODY_SLAM', 'POWER_WHIP'], (8, 15, 14))),
    (('Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT',
      ['SHADOW_BALL', 'GYRO_BALL'], (0, 15, 15)),
     ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13))),
]


@pytest.mark.parametrize("pair_idx", range(len(_FALLBACK_PAIRS)))
def test_fallback_invariant_non_cramorant_pairs(pair_idx):
    """THE load-bearing invariant (it is also the cache-aliasing
    correctness proof): with no Cramorant on either side, pogodives
    policies produce byte-identical battles to PvPoke-default -- score,
    winner, and full timeline -- across all 9 shield cells and both
    bait modes."""
    spec1, spec2 = _FALLBACK_PAIRS[pair_idx]
    for bait in (True, False):
        pv_charged = (pvpoke_dp if bait
                      else functools.partial(pvpoke_dp, bait_shields=False))
        pg_charged = (pogodives_dp if bait
                      else functools.partial(pogodives_dp, bait_shields=False))
        for s1 in (0, 1, 2):
            for s2 in (0, 1, 2):
                a, b = _pair(spec1, spec2, s1, s2)
                ref = simulate(a, b, charged_policy_0=pv_charged,
                               charged_policy_1=pv_charged, log=True)
                a, b = _pair(spec1, spec2, s1, s2)
                got = simulate(a, b, charged_policy_0=pg_charged,
                               charged_policy_1=pg_charged,
                               shield_policy_0=pogodives_shield,
                               shield_policy_1=pogodives_shield, log=True)
                assert (got.pvpoke_score(0), got.winner, got.timeline) == \
                       (ref.pvpoke_score(0), ref.winner, ref.timeline), (
                    f"pair {pair_idx} {s1}v{s2} bait={bait}: pogodives "
                    f"diverged on a non-Cramorant battle")


def test_marker_detection():
    assert _has_pogodives_marker(pogodives_dp)
    assert _has_pogodives_marker(pogodives_shield)
    assert _has_pogodives_marker(
        functools.partial(pogodives_dp, bait_shields=False))
    assert not _has_pogodives_marker(pvpoke_dp)
    assert not _has_pogodives_marker(pvpoke_simulate_shield)
    assert not _has_pogodives_marker(
        functools.partial(pvpoke_dp, bait_shields=False))


def test_simulate_marks_per_side_and_clears():
    """simulate() sets each side's flag from ITS OWN policies before any
    decision, and re-derives (clears) on reuse under plain policies."""
    cram1 = _make_battle_pokemon('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'],
                                 'great', 1, 5, 15, 15)
    cram2 = _make_battle_pokemon('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'],
                                 'great', 1, 5, 15, 15)
    simulate(cram1, cram2, charged_policy_0=pogodives_dp,
             charged_policy_1=pvpoke_dp)
    assert cram1._pogodives is True
    assert cram2._pogodives is False
    # Reuse the same objects under plain policies: flags must clear.
    cram1.reset_for_battle(1, cram2)
    cram2.reset_for_battle(1, cram1)
    simulate(cram1, cram2, charged_policy_0=pvpoke_dp,
             charged_policy_1=pvpoke_dp)
    assert cram1._pogodives is False
    assert cram2._pogodives is False


def test_adaptive_tank_rule_three_way():
    """The adaptive rule discriminates: with a hit in the window where
    1.4 tanks but 2.2 shields, a pogodives prey-holder TANKS at even HP
    (lead 0 < 0.40) and SHIELDS once clearly ahead (lead > 0.40), while
    a plain prey-holder always shields it."""
    def setup(striker_hp_frac=1.0):
        cram = _make_battle_pokemon('Cramorant', 'PECK',
                                    ['DIVE', 'HYDRO_PUMP'],
                                    'great', 2, 5, 15, 15)
        striker = make_bp(atk=110.0, hp=200,
                          fast=make_fast(power=10, energy_gain=5),
                          charged=[make_charged(power=95, energy=45)])
        striker.hp = int(striker.max_hp * striker_hp_frac)
        cram.change_form(striker, 1)              # Gulping
        mv = striker.charged_moves[0]
        dmg = striker.charged_move_damage(mv, cram)
        # The discriminating window: 1.4 tanks it, 2.2 shields it.
        assert dmg * 1.4 < cram.hp <= dmg * 2.2, (
            f'setup drift: dmg={dmg} hp={cram.hp} is outside the window')
        return cram, striker, mv

    # Plain PvPoke prey-holder: shields (2.2 threshold).
    cram, striker, mv = setup()
    assert pvpoke_simulate_shield(striker, cram, mv) is True
    assert would_shield(striker, cram, mv) is True

    # PoGoDives at even HP (lead 0): tanks (1.4 threshold), in both the
    # actual decision and the model. Since the start-scenario sheet
    # (2026-08-26) the tank rule row is selected by _start_shields;
    # (1, 1) is a 'lead'-rule row with the default 1.4 aggressive.
    cram, striker, mv = setup()
    cram._pogodives = True
    cram._start_shields = (1, 1)
    assert pvpoke_simulate_shield(striker, cram, mv) is False
    assert would_shield(striker, cram, mv) is False

    # PoGoDives clearly ahead (striker at 30% -> lead 0.7 > 0.40):
    # back to conservative -- shields.
    cram, striker, mv = setup(striker_hp_frac=0.30)
    cram._pogodives = True
    cram._start_shields = (1, 1)
    assert pvpoke_simulate_shield(striker, cram, mv) is True
    assert would_shield(striker, cram, mv) is True


def test_dive_gate_reads_attacker_tier():
    """Vs Azumarill the PvPoke gate blocks the dive (Fly dpe ratio >=
    1.5) while the pogodives 3.0 gate fires it -- keyed on the ATTACKER's
    flag only."""
    azu = _make_battle_pokemon('Azumarill', 'BUBBLE',
                               ['ICE_BEAM', 'PLAY_ROUGH'], 'great', 1, 4, 15, 13)
    cram = _make_battle_pokemon('Cramorant', 'PECK', ['DIVE', 'FLY'],
                                'great', 1, 5, 15, 15)
    cram.energy = 40
    azu.cooldown = 1
    dive_idx = next(i for i, m in enumerate(cram.charged_moves)
                    if m['moveId'] == 'DIVE')
    assert pvpoke_dp(cram, azu) != dive_idx      # PvPoke tier: no dive
    cram._pogodives = True
    # Sheet row (1, 1) has gate 'always' -> the plain 3.0 gate.
    cram._start_shields = (1, 1)
    cram._dp_cache = None                        # decision-state reset
    assert pvpoke_dp(cram, azu) == dive_idx      # pogodives tier: dives

# ---------------------------------------------------------------------------
# Cache key normalization (sweep_cache)
# ---------------------------------------------------------------------------

def test_cache_policy_normalization_and_key_compat():
    """(a) The base tier adds NO column-key field -- byte-compat with
    every existing cached column; (b) pogodives normalizes to 'pvpoke'
    for pairs no registered case touches, stays distinct when Cramorant
    (any form) is on either side; (c) unknown tiers never alias
    (fail-safe); (d) the applicability registry lives in the
    engine-hashed module, so registry growth invalidates the cache
    through the standard migration machinery."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import sweep_cache as swc
    import gopvpsim.battle as B

    legacy = swc.column_key_fields('Azumarill', False, (4, 15, 13), 25.0,
                                   'BUBBLE', ['ICE_BEAM'])
    base = swc.column_key_fields('Azumarill', False, (4, 15, 13), 25.0,
                                 'BUBBLE', ['ICE_BEAM'], policy='pvpoke')
    assert base == legacy and 'policy' not in base
    pg = swc.column_key_fields('Azumarill', False, (4, 15, 13), 25.0,
                               'BUBBLE', ['ICE_BEAM'], policy='pogodives')
    assert pg['policy'] == 'pogodives'
    assert {k: v for k, v in pg.items() if k != 'policy'} == legacy

    norm = swc.normalize_policy_for_pair
    assert norm('pogodives', 'Azumarill', 'Medicham') == 'pvpoke'   # aliases
    assert norm('pogodives', 'Cramorant', 'Azumarill') == 'pogodives'
    assert norm('pogodives', 'Azumarill', 'Cramorant (Gulping)') == 'pogodives'
    assert norm('pvpoke', 'Cramorant', 'Azumarill') == 'pvpoke'
    assert norm(None, 'Cramorant', 'Azumarill') == 'pvpoke'
    assert norm('sometier', 'Azumarill', 'Medicham') == 'sometier'  # fail-safe

    # (d) the registry's home is hashed: battle.py is in _ENGINE_FILES.
    assert 'battle.py' in swc._ENGINE_FILES
    assert B.POGODIVES_CASE_SPECIES_PREFIXES == ('Cramorant',)


def test_sweep_policy_tier_aliasing_and_liveness(tmp_path, monkeypatch):
    """End-to-end cache semantics of the strategy tier through iv_sweep:
    (a) a NON-Cramorant focal swept under the pogodives tier aliases to
    the base-tier columns -- the second sweep sims NOTHING and returns
    bit-identical scores; (b) a Cramorant focal under pogodives gets
    DISTINCT columns (re-simmed) and genuinely different scores."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import sweep_cache as swc
    from deep_dive_lib.sweep import iv_sweep
    monkeypatch.setattr(swc, 'CACHE_DIR', tmp_path)

    opp = ['Medicham']
    movesets = [('COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'])]
    scen = [(1, 1)]

    # (a) Non-Cramorant focal: base-tier sweep populates the cache...
    r1 = iv_sweep('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
                  'great', False, opp, movesets, scen,
                  opp_iv_mode='pvpoke', use_sweep_cache=True)
    assert r1[1] > 0
    # ...and the pogodives-tier sweep serves ENTIRELY warm via aliasing.
    r2 = iv_sweep('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
                  'great', False, opp, movesets, scen,
                  opp_iv_mode='pvpoke:pogodives', use_sweep_cache=True)
    assert r2[1] == 0, 'aliasing failed: non-Cram pogodives sweep re-simmed'
    assert r1[2] == r2[2]

    # (b) Cramorant focal: the tiers are distinct columns AND distinct
    # results.
    c1 = iv_sweep('Cramorant', 'PECK', ['DIVE', 'FLY'],
                  'great', False, opp, movesets, scen,
                  opp_iv_mode='pvpoke', use_sweep_cache=True)
    c2 = iv_sweep('Cramorant', 'PECK', ['DIVE', 'FLY'],
                  'great', False, opp, movesets, scen,
                  opp_iv_mode='pvpoke:pogodives', use_sweep_cache=True)
    assert c2[1] > 0, 'Cram pogodives sweep wrongly aliased to base tier'
    assert c1[2] != c2[2], (
        'pogodives tier produced identical Cramorant scores -- the tier '
        'is not live through the sweep path')
    # And both tiers now serve warm from their own columns.
    c1b = iv_sweep('Cramorant', 'PECK', ['DIVE', 'FLY'],
                   'great', False, opp, movesets, scen,
                   opp_iv_mode='pvpoke', use_sweep_cache=True)
    c2b = iv_sweep('Cramorant', 'PECK', ['DIVE', 'FLY'],
                   'great', False, opp, movesets, scen,
                   opp_iv_mode='pvpoke:pogodives', use_sweep_cache=True)
    assert c1b[1] == 0 and c2b[1] == 0
    assert c1b[2] == c1[2] and c2b[2] == c2[2]


def test_start_scenario_sheet_exemptions():
    """Start-scenario SHEET (2026-08-26 strict-bar campaign, generalizing
    the round-7 2-0 exemption): a side whose _POGODIVES_SHEET row is None
    plays plain PvPoke (the flag stays False); every other start keeps
    the strat. Exempt today: (2, 0) only (round 7). The (2, 1) row was
    briefly exempt mid-campaign (pre-sheet it was strat-on and
    net-NEGATIVE: GL -1175 win-cells / -27.6 rating) until the
    ready-nuke gate rule was discovered and full-tensor verified.
    Start-scenario, not live-state -- the flag is set at battle start
    and does NOT flip when shields are consumed mid-fight."""
    def flags_for(s1, s2):
        c1 = _make_battle_pokemon('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'],
                                  'great', s1, 5, 15, 15)
        c2 = _make_battle_pokemon('Registeel', 'LOCK_ON',
                                  ['FLASH_CANNON', 'FOCUS_BLAST'],
                                  'great', s2, 15, 15, 15)
        simulate(c1, c2, charged_policy_0=pogodives_dp,
                 charged_policy_1=pvpoke_dp,
                 shield_policy_0=pogodives_shield)
        assert c1._start_shields == (s1, s2)
        return c1._pogodives

    import gopvpsim.battle as B
    exempt = {s for s, row in B._POGODIVES_SHEET.items() if row is None}
    assert exempt == {(2, 0)}
    for s1 in (0, 1, 2):
        for s2 in (0, 1, 2):
            expected = (s1, s2) not in exempt
            assert flags_for(s1, s2) is expected, (s1, s2)
    # The exemption is per-SIDE: a pogodives side starting 0 shields vs a
    # 2-shield opponent keeps the strat (it is BEHIND, not ahead).
    c1 = _make_battle_pokemon('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'],
                              'great', 0, 5, 15, 15)
    c2 = _make_battle_pokemon('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'],
                              'great', 2, 5, 15, 15)
    simulate(c1, c2, charged_policy_0=pogodives_dp, charged_policy_1=pogodives_dp)
    assert c1._pogodives is True
    assert c2._pogodives is False        # the 2-0 side reverts


def test_sheet_gate_conditions():
    """Per-start-scenario gate conditions (2026-08-26 sheet). Direct unit
    probes of _cram_dive_gate_dpe: at (1,0) the gate is OFF (pre-sheet:
    3.0 fired and 1v0 ran GL -15.8 rating); at (0,0) it needs CMP won
    AND low opponent fast DPT; at (0,1) CMP alone; at (2,2) additionally
    the opponent's cheapest charged move under 55 energy."""
    import gopvpsim.battle as B

    def probe(start, cram_atk, opp_atk, opp_fast_power=6, opp_cheapest=45):
        cram = make_bp(atk=cram_atk, hp=130,
                       fast=make_fast(power=6, energy_gain=8),
                       charged=[make_charged(power=65, energy=40)])
        opp = make_bp(atk=opp_atk, hp=140,
                      fast=make_fast(power=opp_fast_power, energy_gain=8),
                      charged=[make_charged(power=90, energy=opp_cheapest)])
        cram._pogodives = True
        cram._start_shields = start
        opp.fast_move['_turns'] = 2
        return B._cram_dive_gate_dpe(cram, opp)

    PG, PV = B._POGODIVES_DIVE_GATE_DPE, B._CRAM_DIVE_GATE_DPE
    assert probe((1, 0), 120, 100) == PV          # gate off at 1v0
    assert probe((1, 1), 100, 120) == PG          # 'always' ignores cmp
    assert probe((0, 0), 120, 100) == PG          # cmp won, low dpt
    assert probe((0, 0), 100, 120) == PV          # cmp lost
    assert probe((0, 0), 120, 100, opp_fast_power=40) == PV   # high dpt
    assert probe((0, 1), 120, 100, opp_fast_power=40) == PG   # 0v1: cmp only
    assert probe((2, 2), 120, 100, opp_cheapest=45) == PG
    assert probe((2, 2), 120, 100, opp_cheapest=55) == PV     # nuke moves


def test_sheet_tank_rules():
    """Per-start-scenario tank rules (2026-08-26 sheet). Direct unit
    probes of _cram_tank_mult: (1,0) uses the lead rule at aggressive
    2.0 (pre-sheet: 1.4); (2,2) is tank-PLAIN (aggr 2.2 both branches,
    v3 -- the v1 cheap tank was vacuous and the v2 cheap_frac 0.30
    broke Dive+Surf); the 'cheap' rule mechanism itself is probed via
    a synthetic sheet row."""
    import gopvpsim.battle as B

    def mults(start, damage):
        cram = make_bp(atk=110, hp=130,
                       fast=make_fast(power=6, energy_gain=8),
                       charged=[make_charged(power=65, energy=40)])
        opp = make_bp(atk=110, hp=140,
                      fast=make_fast(power=6, energy_gain=8),
                      charged=[make_charged(power=90, energy=45)])
        cram._pogodives = True
        cram._start_shields = start
        return B._cram_tank_mult(opp, cram, damage)

    assert mults((1, 0), 30) == 2.0               # lead rule, aggr 2.0
    assert mults((1, 1), 30) == B._POGODIVES_TANK_AGGRESSIVE   # default 1.4
    assert mults((2, 2), 20) == 2.2               # v3: tank plain PvPoke
    assert mults((2, 2), 60) == 2.2
    # The 'cheap' tank mechanism (kept for future rows): synthetic row.
    saved = B._POGODIVES_SHEET
    try:
        B._POGODIVES_SHEET = dict(saved)
        B._POGODIVES_SHEET[(2, 2)] = {'gate': 'always', 'tank_aggr': 1.8,
                                      'tank_rule': 'cheap',
                                      'cheap_frac': 0.30}
        cap = int(0.30 * 130)
        assert mults((2, 2), cap) == 1.8
        assert mults((2, 2), cap + 5) == B._POGODIVES_TANK_CONSERVATIVE
    finally:
        B._POGODIVES_SHEET = saved


def test_sheet_2v1_ready_nuke_gate():
    """The 2v1 'cmp_ready_dpt' gate (discovery rule 2026-08-26): fires
    only when CMP is won AND the opponent's cheapest charged move costs
    >= 40 energy AND they hold that energy RIGHT NOW AND their fast DPT
    is under the row's tighter 0.0155 cap. Pre-rule this start was a
    full exemption (delta exactly 0)."""
    import gopvpsim.battle as B

    def probe(cram_atk=120, opp_atk=100, opp_energy=45, opp_cost=45,
              opp_fast_power=4):
        cram = make_bp(atk=cram_atk, hp=130,
                       fast=make_fast(power=6, energy_gain=8),
                       charged=[make_charged(power=65, energy=40)])
        opp = make_bp(atk=opp_atk, hp=140,
                      fast=make_fast(power=opp_fast_power, energy_gain=8),
                      charged=[make_charged(power=90, energy=opp_cost)])
        opp.energy = opp_energy
        cram._pogodives = True
        cram._start_shields = (2, 1)
        opp.fast_move['_turns'] = 2
        return B._cram_dive_gate_dpe(cram, opp)

    PG, PV = B._POGODIVES_DIVE_GATE_DPE, B._CRAM_DIVE_GATE_DPE
    assert probe() == PG                              # all conditions met
    assert probe(cram_atk=90) == PV                   # cmp lost
    assert probe(opp_cost=35, opp_energy=45) == PV    # cheap moves
    assert probe(opp_energy=30) == PV                 # not ready to throw
    assert probe(opp_fast_power=30) == PV             # dpt over the cap
    # The tank side of the 2v1 row is plain PvPoke: aggr 2.2 == both
    # branches == the PvPoke multiplier.
    cram = make_bp(atk=110, hp=130, fast=make_fast(power=6, energy_gain=8),
                   charged=[make_charged(power=65, energy=40)])
    opp = make_bp(atk=110, hp=140, fast=make_fast(power=6, energy_gain=8),
                  charged=[make_charged(power=90, energy=45)])
    cram._pogodives = True
    cram._start_shields = (2, 1)
    assert B._cram_tank_mult(opp, cram, 30) == B._CRAM_TANK_MULT
