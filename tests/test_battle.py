"""
Tests for gopvpsim.battle — simulation loop, policies, BattlePokemon.

Unit tests use hardcoded move/pokemon dicts (no network).
Integration tests (marked 'integration') validate against known PvPoke results.
Run integration tests with: pytest -m integration
"""
import pytest
from gopvpsim.battle import (
    BattlePokemon, BattleResult,
    always_shield, never_shield, pvpoke_shield, use_first_available, bait_with_cheapest,
    no_bait, pvpoke_ai, pvpoke_dp, optimal_timing, simulate, ENERGY_CAP, OPTIMAL_TIMING,
)


# ---------------------------------------------------------------------------
# Helpers — minimal fake move/pokemon data for unit tests
# ---------------------------------------------------------------------------

def make_fast(power=5, energy_gain=5, cooldown_ms=1000, type_='normal'):
    """Return a minimal fast move dict (2-turn move by default)."""
    return {'moveId': 'FAKE_FAST', 'name': 'Fake Fast', 'type': type_,
            'power': power, 'energyGain': energy_gain, 'cooldown': cooldown_ms}

def make_charged(power=50, energy=40, type_='normal'):
    """Return a minimal charged move dict."""
    return {'moveId': 'FAKE_CHARGED', 'name': 'Fake Charged', 'type': type_,
            'power': power, 'energy': energy, 'energyGain': 0}

def make_bp(atk=100.0, def_=100.0, hp=100, types=None,
            fast=None, charged=None, shields=2):
    """Return a BattlePokemon with sensible defaults."""
    return BattlePokemon(
        species       = 'Testmon',
        types         = types or ['normal'],
        atk           = atk,
        def_          = def_,
        max_hp        = hp,
        fast_move     = fast or make_fast(),
        charged_moves = charged or [make_charged()],
        shields       = shields,
    )


# ---------------------------------------------------------------------------
# Shield policies
# ---------------------------------------------------------------------------

def test_always_shield_when_shields_available():
    attacker = make_bp()
    defender = make_bp(shields=2)
    assert always_shield(attacker, defender, make_charged()) is True

def test_always_shield_when_no_shields():
    attacker = make_bp()
    defender = make_bp(shields=0)
    assert always_shield(attacker, defender, make_charged()) is False

def test_never_shield_regardless():
    attacker = make_bp()
    defender = make_bp(shields=2)
    assert never_shield(attacker, defender, make_charged()) is False


# ---------------------------------------------------------------------------
# Charged-move policies
# ---------------------------------------------------------------------------

def test_use_first_available_returns_none_when_no_energy():
    p = make_bp(charged=[make_charged(energy=50)])
    p.energy = 10
    assert use_first_available(p, make_bp()) is None

def test_use_first_available_returns_index_when_enough_energy():
    p = make_bp(charged=[make_charged(energy=50)])
    p.energy = 50
    assert use_first_available(p, make_bp()) == 0

def test_no_bait_uses_best_dpe_regardless_of_shields():
    cheap = make_charged(power=40, energy=35)
    expensive = make_charged(power=100, energy=60)
    p = make_bp(charged=[cheap, expensive])
    p.energy = 60
    defender = make_bp(shields=2)
    # no_bait ignores shields — picks highest actual DPE (expensive has higher power/energy)
    assert no_bait(p, defender) == 1

def test_no_bait_ignores_shields_when_none():
    cheap = make_charged(power=40, energy=35)
    expensive = make_charged(power=100, energy=60)
    p = make_bp(charged=[cheap, expensive])
    p.energy = 60
    defender = make_bp(shields=0)
    assert no_bait(p, defender) == 1

def test_no_bait_returns_none_when_cant_afford():
    p = make_bp(charged=[make_charged(energy=50)])
    p.energy = 10
    assert no_bait(p, make_bp()) is None

def test_bait_with_cheapest_uses_cheap_move_when_defender_has_shields():
    cheap = make_charged(power=40, energy=35)
    expensive = make_charged(power=100, energy=60)
    p = make_bp(charged=[expensive, cheap])
    p.energy = 60
    defender = make_bp(shields=1)
    assert bait_with_cheapest(p, defender) == 1   # cheap move index

def test_bait_with_cheapest_uses_strongest_when_no_shields():
    cheap = make_charged(power=40, energy=35)
    expensive = make_charged(power=100, energy=60)
    p = make_bp(charged=[cheap, expensive])
    p.energy = 60
    defender = make_bp(shields=0)
    assert bait_with_cheapest(p, defender) == 1   # expensive/powerful move index

def test_bait_returns_none_when_cant_afford_any():
    p = make_bp(charged=[make_charged(energy=50)])
    p.energy = 10
    assert bait_with_cheapest(p, make_bp()) is None


# ---------------------------------------------------------------------------
# BattlePokemon state
# ---------------------------------------------------------------------------

def test_battlepokemon_starts_at_full_hp():
    bp = make_bp(hp=120)
    assert bp.hp == 120

def test_battlepokemon_starts_at_zero_energy():
    bp = make_bp()
    assert bp.energy == 0

def test_battlepokemon_starts_with_zero_cooldown():
    bp = make_bp()
    assert bp.cooldown == 0

def test_battlepokemon_initial_energy():
    bp = make_bp()
    bp2 = BattlePokemon(
        species='Testmon', types=['normal'], atk=100.0, def_=100.0, max_hp=100,
        fast_move=make_fast(), charged_moves=[make_charged()],
        shields=2, initial_energy=50,
    )
    assert bp2.energy == 50

def test_battlepokemon_initial_energy_capped():
    bp = BattlePokemon(
        species='Testmon', types=['normal'], atk=100.0, def_=100.0, max_hp=100,
        fast_move=make_fast(), charged_moves=[make_charged()],
        shields=2, initial_energy=200,
    )
    assert bp.energy == ENERGY_CAP

def test_battlepokemon_initial_energy_negative_clamped():
    bp = BattlePokemon(
        species='Testmon', types=['normal'], atk=100.0, def_=100.0, max_hp=100,
        fast_move=make_fast(), charged_moves=[make_charged()],
        shields=2, initial_energy=-10,
    )
    assert bp.energy == 0

def test_simulate_initial_energy_fires_charge_sooner():
    """A pokemon with enough initial energy to afford a charge move fires it turn 1."""
    p0 = make_bp(hp=200, atk=100.0, def_=100.0, shields=0,
                 charged=[make_charged(power=50, energy=40)])
    p0.initial_energy = 40
    p0.energy = 40   # set directly since __post_init__ already ran

    p1 = make_bp(hp=200, atk=100.0, def_=100.0, shields=0,
                 charged=[make_charged(power=50, energy=40)])

    result_early = simulate(p0, p1)

    p0b = make_bp(hp=200, atk=100.0, def_=100.0, shields=0,
                  charged=[make_charged(power=50, energy=40)])
    p1b = make_bp(hp=200, atk=100.0, def_=100.0, shields=0,
                  charged=[make_charged(power=50, energy=40)])
    result_normal = simulate(p0b, p1b)

    assert result_early.turns <= result_normal.turns


# ---------------------------------------------------------------------------
# simulate() — structural properties
# ---------------------------------------------------------------------------

def test_simulate_returns_battle_result():
    p0 = make_bp(hp=100, atk=100.0, def_=100.0)
    p1 = make_bp(hp=100, atk=80.0, def_=80.0)
    result = simulate(p0, p1)
    assert isinstance(result, BattleResult)

def test_pvpoke_score_winner_above_500():
    p0 = make_bp(hp=200, atk=150.0, def_=150.0)
    p1 = make_bp(hp=50,  atk=50.0,  def_=50.0)
    result = simulate(p0, p1)
    assert result.winner == 0
    assert result.pvpoke_score(0) > 500
    assert result.pvpoke_score(1) < 500

def test_pvpoke_score_sums_to_1000():
    """The two scores always sum to exactly 1000."""
    p0 = make_bp(hp=100, atk=100.0, def_=100.0)
    p1 = make_bp(hp=100, atk=80.0,  def_=80.0)
    result = simulate(p0, p1)
    assert result.pvpoke_score(0) + result.pvpoke_score(1) == pytest.approx(1000.0)

def test_pvpoke_score_perfect_win_is_1000():
    """A pokemon that deals full damage and survives at full HP scores 1000."""
    p0 = make_bp(hp=100, atk=100.0, def_=100.0)
    p1 = make_bp(hp=50,  atk=1.0,   def_=1.0, shields=0)
    result = simulate(p0, p1, shield_policy_0=never_shield)
    if result.winner == 0 and result.hp_remaining[0] == result.max_hp[0]:
        assert result.pvpoke_score(0) == pytest.approx(1000.0)

def test_simulate_winner_has_hp_remaining():
    p0 = make_bp(hp=200, atk=150.0, def_=150.0)
    p1 = make_bp(hp=50,  atk=50.0,  def_=50.0)
    result = simulate(p0, p1)
    assert result.winner == 0
    assert result.hp_remaining[0] > 0
    assert result.hp_remaining[1] <= 0

def test_simulate_loser_has_zero_hp():
    p0 = make_bp(hp=50,  atk=50.0,  def_=50.0)
    p1 = make_bp(hp=200, atk=150.0, def_=150.0)
    result = simulate(p0, p1)
    assert result.winner == 1
    assert result.hp_remaining[0] <= 0

def test_simulate_turns_positive():
    p0 = make_bp()
    p1 = make_bp()
    result = simulate(p0, p1)
    assert result.turns > 0

def test_simulate_0_shields_faster_than_2_shields():
    """Fewer shields means charged moves land for full damage → battle ends sooner."""
    def run(shields):
        p0 = make_bp(hp=100, atk=100.0, def_=100.0, shields=shields)
        p1 = make_bp(hp=100, atk=100.0, def_=100.0, shields=shields)
        return simulate(p0, p1).turns
    assert run(0) <= run(2)

def test_simulate_energy_capped():
    """Energy never exceeds ENERGY_CAP."""
    p0 = make_bp(hp=500, atk=50.0, def_=50.0, shields=0,
                 fast=make_fast(energy_gain=30))
    p1 = make_bp(hp=500, atk=50.0, def_=50.0, shields=0,
                 fast=make_fast(energy_gain=30))
    result = simulate(p0, p1)
    assert result.energy_remaining[0] <= ENERGY_CAP
    assert result.energy_remaining[1] <= ENERGY_CAP

def test_simulate_log_produces_events():
    p0 = make_bp()
    p1 = make_bp()
    result = simulate(p0, p1, log=True)
    assert len(result.timeline) > 0

# ---------------------------------------------------------------------------
# Optimal timing
# ---------------------------------------------------------------------------

def test_optimal_timing_table_has_25_entries():
    assert len(OPTIMAL_TIMING) == 25

def test_optimal_timing_same_turns_is_none():
    """Same fast move duration on both sides — timing never matters."""
    for t in range(1, 6):
        assert OPTIMAL_TIMING[(t, t)] is None

def test_optimal_timing_fires_when_pattern_is_none():
    """If timing doesn't matter, optimal_timing behaves like pvpoke_ai."""
    p0 = make_bp(charged=[make_charged(energy=40)])
    p1 = make_bp()
    p0.energy = 40
    # Both use 2-turn fast moves → (2,2) = None → should fire
    p0.fast_move['_turns'] = 2
    p1.fast_move['_turns'] = 2
    assert optimal_timing(p0, p1) == 0

def test_optimal_timing_waits_when_not_on_pattern():
    """With a (start, step) pattern, returns None when not at the right fast-move count."""
    # (2, 3) → (1, 3): fire after fast move 1, 4, 7, ...
    # At fast_move_count=0 (haven't thrown any fast moves yet), should wait.
    p0 = make_bp(charged=[make_charged(energy=40)])
    p1 = make_bp()
    p0.energy = 40
    p0.fast_move['_turns'] = 2
    p1.fast_move['_turns'] = 3
    p0._fm_since_charge = 0  # not at start=1 yet
    assert optimal_timing(p0, p1) is None

def test_optimal_timing_fires_at_start():
    """Fires when fast-move count equals start."""
    # (2, 3) → (1, 3): fire after fast move 1
    p0 = make_bp(charged=[make_charged(energy=40)])
    p1 = make_bp()
    p0.energy = 40
    p0.fast_move['_turns'] = 2
    p1.fast_move['_turns'] = 3
    p0._fm_since_charge = 1  # exactly at start=1
    assert optimal_timing(p0, p1) == 0

def test_optimal_timing_fires_at_subsequent_steps():
    """Fires at start + step, start + 2*step, etc."""
    # (2, 3) → (1, 3): fire at 1, 4, 7, ...
    p0 = make_bp(charged=[make_charged(energy=40)])
    p1 = make_bp()
    p0.energy = 40
    p0.fast_move['_turns'] = 2
    p1.fast_move['_turns'] = 3
    for count in (1, 4, 7, 10):
        p0._fm_since_charge = count
        assert optimal_timing(p0, p1) == 0, f"should fire at fm_count={count}"

def test_optimal_timing_waits_between_steps():
    """Does NOT fire at counts between start and start+step."""
    p0 = make_bp(charged=[make_charged(energy=40)])
    p1 = make_bp()
    p0.energy = 40
    p0.fast_move['_turns'] = 2
    p1.fast_move['_turns'] = 3
    for count in (2, 3, 5, 6):
        p0._fm_since_charge = count
        assert optimal_timing(p0, p1) is None, f"should wait at fm_count={count}"

def test_optimal_timing_fires_when_energy_capped():
    """Never wastes energy above ENERGY_CAP — fires even off-pattern at cap."""
    p0 = make_bp(charged=[make_charged(energy=40)])
    p1 = make_bp()
    p0.energy = ENERGY_CAP
    p0.fast_move['_turns'] = 2
    p1.fast_move['_turns'] = 3
    p0._fm_since_charge = 0  # off-pattern, but energy is capped
    assert optimal_timing(p0, p1) == 0

def test_optimal_timing_returns_none_when_cant_afford():
    """No charged move if can't afford any, regardless of timing."""
    p0 = make_bp(charged=[make_charged(energy=40)])
    p1 = make_bp()
    p0.energy = 10   # can't afford
    p0.fast_move['_turns'] = 2
    p1.fast_move['_turns'] = 3
    p0._fm_since_charge = 1
    assert optimal_timing(p0, p1) is None

def test_simulate_optimal_timing_completes():
    """Battle with optimal_timing policy terminates normally."""
    p0 = make_bp(fast=make_fast(cooldown_ms=1000))  # 2-turn
    p1 = make_bp(fast=make_fast(cooldown_ms=1500))  # 3-turn
    result = simulate(p0, p1,
                      charged_policy_0=optimal_timing,
                      charged_policy_1=optimal_timing)
    assert isinstance(result, BattleResult)
    assert result.turns > 0


def test_simulate_never_shield_means_no_shields_used():
    p0 = make_bp(shields=2)
    p1 = make_bp(shields=2)
    result = simulate(p0, p1,
                      shield_policy_0=never_shield,
                      shield_policy_1=never_shield)
    # Both started with 2 shields and never used any
    assert result.shields_remaining[0] == 2
    assert result.shields_remaining[1] == 2


# ---------------------------------------------------------------------------
# Integration tests — validate against known PvPoke matchup results
# Verify at pvpoke.com/battle/ with the specified Pokemon, moves, IVs, league.
# ---------------------------------------------------------------------------

def _make_battle_pokemon(species, fast_id, charged_ids, league, shields,
                          atk_iv, def_iv, sta_iv, max_level=51.0):
    """Helper: build a BattlePokemon from the real gamemaster."""
    from gopvpsim.pokemon import Pokemon
    from gopvpsim.moves import get_moves
    from gopvpsim.data import load_gamemaster

    pokemon = Pokemon.at_best_level(species, atk_iv, def_iv, sta_iv,
                                    league=league, max_level=max_level)
    fast_moves, charged_moves = get_moves()
    fm  = dict(fast_moves[fast_id])
    cms = [dict(charged_moves[cid]) for cid in charged_ids]

    gm  = load_gamemaster()
    mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
    from gopvpsim.data import parse_types
    types = parse_types(mon)

    return BattlePokemon(
        species=species, types=types,
        atk=pokemon.atk, def_=pokemon.def_, max_hp=pokemon.hp,
        fast_move=fm, charged_moves=cms, shields=shields,
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_med,shields_azu,expected_winner", [
    # Medicham 5/15/15 (PSYCHO_CUT/DYNAMIC_PUNCH/PSYCHIC)
    # vs Azumarill 8/15/15 (BUBBLE/ICE_BEAM/HYDRO_PUMP), Great League
    # Expected results verified at pvpoke.com/battle/
    # PvPoke scores (Azumarill's rating; <500 = Medicham wins):
    #   Azu shields →    0     1     2
    #   Med 0 shields: [579,  671,  764]
    #   Med 1 shields: [492,  544,  637]
    #   Med 2 shields: [253,  513,  605]
    (0, 0, 1),   # Azumarill wins (score 579)
    (0, 1, 1),   # Azumarill wins (score 671)
    (0, 2, 1),   # Azumarill wins (score 764)
    (1, 0, 0),   # Medicham wins (score 492)
    (1, 1, 1),   # Azumarill wins (score 544)
    (1, 2, 1),   # Azumarill wins (score 637)
    (2, 0, 0),   # Medicham wins (score 253)
    pytest.param(2, 1, 1, marks=pytest.mark.xfail(
        reason="Score 513 = Azu barely wins by ~5 HP; requires turnsToLive sub-DP "
               "(ActionLogic.js lines 38-155) to detect when DP plan outlasts survival")),
    (2, 2, 1),   # Azumarill wins (score 605)
])
def test_medicham_vs_azumarill(shields_med, shields_azu, expected_winner):
    bp_med = _make_battle_pokemon('Medicham',  'PSYCHO_CUT',  ['DYNAMIC_PUNCH', 'PSYCHIC'],
                                   'great', shields_med, 5, 15, 15)
    bp_azu = _make_battle_pokemon('Azumarill', 'BUBBLE',   ['ICE_BEAM', 'HYDRO_PUMP'],
                                   'great', shields_azu, 8, 15, 15)
    result = simulate(bp_med, bp_azu,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      shield_policy_0=pvpoke_shield,
                      shield_policy_1=pvpoke_shield)
    assert result.winner == expected_winner, (
        f"{shields_med}v{shields_azu}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
