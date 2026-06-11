"""
Tests for gopvpsim.battle — simulation loop, policies, BattlePokemon.

Unit tests use hardcoded move/pokemon dicts (no network).
Integration tests (marked 'integration') validate against known PvPoke results.
Run integration tests with: pytest -m integration
"""
import pytest
from gopvpsim.battle import (
    BattlePokemon, BattleResult,
    always_shield, never_shield, pvpoke_shield, pvpoke_simulate_shield,
    use_first_available, bait_with_cheapest,
    no_bait, pvpoke_ai, pvpoke_dp, optimal_timing, simulate, ENERGY_CAP, OPTIMAL_TIMING,
)
from gopvpsim.data import get_default_moveset


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
# pvpoke_dp bait_shields gate (farm-down path)
# ---------------------------------------------------------------------------

def _make_farm_down_attacker():
    """Attacker with enough HP that farm-down triggers, two charged moves,
    energy enough to fire either. cms are sorted energy-asc internally, so
    the cheap move is the bait target."""
    cheap     = make_charged(power=50,  energy=35)
    expensive = make_charged(power=100, energy=60)
    a = make_bp(atk=150.0, hp=300,
                charged=[cheap, expensive])
    a.energy = 100  # can afford either move
    return a

def test_pvpoke_dp_baits_cheapest_when_bait_shields_on():
    attacker = _make_farm_down_attacker()
    defender = make_bp(atk=100.0, def_=100.0, hp=300, shields=2)
    # Farm-down path: defender hp large, bait_shields default True →
    # picks cms[0] (cheap) because would_shield is true for the big move.
    idx = pvpoke_dp(attacker, defender)
    assert idx == 0, f"expected bait to cheap move (index 0), got {idx}"

def test_pvpoke_dp_no_bait_fires_best_when_bait_shields_off():
    attacker = _make_farm_down_attacker()
    defender = make_bp(atk=100.0, def_=100.0, hp=300, shields=2)
    # Same setup but bait_shields=False → picks best move (expensive, index 1).
    idx = pvpoke_dp(attacker, defender, bait_shields=False)
    assert idx == 1, f"expected max-DPE expensive move (index 1), got {idx}"

def test_pvpoke_dp_no_bait_matches_default_when_no_shields():
    attacker = _make_farm_down_attacker()
    defender = make_bp(atk=100.0, def_=100.0, hp=300, shields=0)
    # Without shields, bait_shields is irrelevant — both modes pick the best.
    idx_on  = pvpoke_dp(attacker, defender, bait_shields=True)
    idx_off = pvpoke_dp(attacker, defender, bait_shields=False)
    assert idx_on == idx_off == 1


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
                          atk_iv, def_iv, sta_iv, max_level=51.0, shadow=False):
    """Helper: build a BattlePokemon from the real gamemaster."""
    from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS
    from gopvpsim.moves import get_moves

    pokemon = Pokemon.at_best_level(species, atk_iv, def_iv, sta_iv,
                                    league=league, max_level=max_level,
                                    shadow=shadow)
    fast_moves, charged_moves = get_moves()
    fm  = dict(fast_moves[fast_id])
    cms = [dict(charged_moves[cid]) for cid in charged_ids]

    return BattlePokemon.from_pokemon(
        pokemon, fm, cms, shields=shields,
        league_cp=LEAGUE_CAPS[league],
    )


def _extract_battle_log(result):
    """Extract compact charged-move sequence from a BattleResult timeline.

    Returns a list like:
        ['Mienfoo: High Jump Kick (shielded)', 'Medicham: Ice Punch']
    """
    log = []
    for line in result.timeline:
        if ('uses' not in line or '→' not in line
                or 'fast' in line.lower() or 'floating' in line.lower()):
            continue
        body = line.strip().split(': ', 1)[1]  # strip "T xx: "
        who, rest = body.split(' uses ', 1)
        move_name = rest.split(' →')[0]
        if 'SHIELDED' in line:
            log.append(f'{who}: {move_name} (shielded)')
        else:
            log.append(f'{who}: {move_name}')
    return log


@pytest.mark.integration
@pytest.mark.parametrize("shields_med,shields_azu,expected_winner,expected_azu_score,expected_log", [
    # Medicham 5/15/15 (PSYCHO_CUT/DYNAMIC_PUNCH/PSYCHIC)
    # vs Azumarill 8/15/15 (BUBBLE/ICE_BEAM/HYDRO_PUMP), Great League
    # Expected results verified at pvpoke.com/battle/
    # PvPoke scores (Azumarill's rating; <500 = Medicham wins):
    #   Azu shields →    0     1     2
    #   Med 0 shields: [608,  730,  851]
    #   Med 1 shields: [475,  603,  724]
    #   Med 2 shields: [235,  411,  605]
    (0, 0, 1, 608, ['Medicham: Psychic', 'Azumarill: Hydro Pump', 'Medicham: Psychic', 'Azumarill: Ice Beam']),
    (0, 1, 1, 730, ['Medicham: Psychic (shielded)', 'Azumarill: Hydro Pump', 'Medicham: Psychic', 'Azumarill: Ice Beam']),
    (0, 2, 1, 851, ['Medicham: Psychic (shielded)', 'Azumarill: Hydro Pump', 'Medicham: Psychic (shielded)', 'Azumarill: Ice Beam']),
    (1, 0, 0, 475, ['Medicham: Psychic', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Hydro Pump', 'Medicham: Psychic']),
    (1, 1, 1, 603, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Hydro Pump', 'Medicham: Dynamic Punch']),
    (1, 2, 1, 724, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic (shielded)', 'Azumarill: Hydro Pump', 'Medicham: Dynamic Punch']),
    (2, 0, 0, 235, ['Medicham: Psychic', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Hydro Pump (shielded)', 'Medicham: Psychic']),
    (2, 1, 0, 411, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Ice Beam (shielded)', 'Medicham: Dynamic Punch', 'Azumarill: Ice Beam', 'Medicham: Dynamic Punch']),
    (2, 2, 1, 605, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Dynamic Punch', 'Medicham: Dynamic Punch', 'Azumarill: Hydro Pump']),
])
def test_medicham_vs_azumarill(shields_med, shields_azu, expected_winner, expected_azu_score,
                               expected_log):
    bp_med = _make_battle_pokemon('Medicham',  'PSYCHO_CUT',  ['DYNAMIC_PUNCH', 'PSYCHIC'],
                                   'great', shields_med, 5, 15, 15)
    bp_azu = _make_battle_pokemon('Azumarill', 'BUBBLE',   ['ICE_BEAM', 'HYDRO_PUMP'],
                                   'great', shields_azu, 8, 15, 15)
    result = simulate(bp_med, bp_azu,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      shield_policy_0=always_shield,
                      shield_policy_1=always_shield,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_med}v{shields_azu}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    azu_score = round(result.pvpoke_score(1))
    assert azu_score == expected_azu_score, (
        f"{shields_med}v{shields_azu}: expected Azu score={expected_azu_score}, "
        f"got {azu_score}  (delta={azu_score - expected_azu_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_med}v{shields_azu}: battle log mismatch"
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_azu,shields_forr,expected_winner,expected_azu_score,expected_log", [
    # Azumarill 4/15/13 (BUBBLE/ICE_BEAM/HYDRO_PUMP)
    # vs Forretress 5/15/13 (VOLT_SWITCH/SAND_TOMB/ROCK_TOMB), Great League
    # Policy: pvpoke_dp + always_shield (PvPoke simulate-mode default)
    #
    # PvPoke scores (pvpoke.com/battle/):
    #                 Forr 0s  Forr 1s  Forr 2s
    #   Azu 0s:        492      312      222
    #   Azu 1s:        657      429      226
    #   Azu 2s:        612      496      242
    #
    # After the atk_stage DP fix (2026-04-15), our scores match PvPoke
    # exactly in all 9 shield scenarios: the near-KO DP now accumulates
    # chance-1 opp-def-debuffs (Sand Tomb) as attacker atk-stage and
    # recognises stacked-ST plans that KO faster than bestChargedMove.
    #
    # Our scores:        Forr 0s  Forr 1s  Forr 2s
    #   Azu 0 shields:    492      312      222
    #   Azu 1 shields:    657      429      226
    #   Azu 2 shields:    612      496      242
    (0, 0, 1, 492, ['Forretress: Sand Tomb', 'Azumarill: Hydro Pump', 'Forretress: Sand Tomb', 'Forretress: Sand Tomb']),
    (0, 1, 1, 312, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb', 'Azumarill: Ice Beam', 'Forretress: Sand Tomb']),
    (0, 2, 1, 222, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb']),
    (1, 0, 0, 657, ['Forretress: Sand Tomb', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Ice Beam']),
    (1, 1, 1, 429, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb']),
    (1, 2, 1, 226, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb']),
    (2, 0, 0, 612, ['Forretress: Sand Tomb (shielded)', 'Azumarill: Hydro Pump',
                    'Forretress: Sand Tomb (shielded)', 'Forretress: Sand Tomb',
                    'Azumarill: Ice Beam']),
    (2, 1, 1, 496, ['Forretress: Sand Tomb (shielded)', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb']),
    (2, 2, 1, 242, ['Forretress: Sand Tomb (shielded)', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb']),
])
def test_azumarill_vs_forretress_sand_rock(shields_azu, shields_forr,
                                           expected_winner, expected_azu_score,
                                           expected_log):
    bp_azu  = _make_battle_pokemon('Azumarill',  'BUBBLE',       ['ICE_BEAM', 'HYDRO_PUMP'],
                                   'great', shields_azu,  4, 15, 13)
    bp_forr = _make_battle_pokemon('Forretress', 'VOLT_SWITCH',  ['SAND_TOMB', 'ROCK_TOMB'],
                                   'great', shields_forr, 5, 15, 13)
    result = simulate(bp_azu, bp_forr,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_azu}v{shields_forr}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    azu_score = round(result.pvpoke_score(0))
    assert azu_score == expected_azu_score, (
        f"{shields_azu}v{shields_forr}: expected Azu score={expected_azu_score}, "
        f"got {azu_score}  (delta={azu_score - expected_azu_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_azu}v{shields_forr}: battle log mismatch"
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_azu,shields_forr,expected_winner,expected_azu_score,expected_log", [
    # Azumarill 4/15/13 (BUBBLE/ICE_BEAM/HYDRO_PUMP)
    # vs Forretress 5/15/13 (VOLT_SWITCH/ROCK_TOMB only), Great League
    # Policy: pvpoke_dp + always_shield (PvPoke simulate-mode default)
    #
    # PvPoke verified scores (pvpoke.com/battle/):
    #              Forr 0s  Forr 1s  Forr 2s
    #   Azu 0s:     480      277      218
    #   Azu 1s:     480      277      218
    #   Azu 2s:     575      445      265
    #
    (0, 0, 1, 480, ['Forretress: Rock Tomb', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam']),
    (0, 1, 1, 277, ['Forretress: Rock Tomb', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam']),
    (0, 2, 1, 218, ['Forretress: Rock Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Hydro Pump (shielded)']),
    (1, 0, 1, 480, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam', 'Forretress: Rock Tomb']),
    (1, 1, 1, 277, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam', 'Forretress: Rock Tomb']),
    (1, 2, 1, 218, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb']),
    (2, 0, 0, 575, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Hydro Pump']),
    (2, 1, 1, 445, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb']),
    (2, 2, 1, 265, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb']),
])
def test_azumarill_vs_forretress_rt_only(shields_azu, shields_forr,
                                         expected_winner, expected_azu_score,
                                         expected_log):
    bp_azu  = _make_battle_pokemon('Azumarill',  'BUBBLE',      ['ICE_BEAM', 'HYDRO_PUMP'],
                                   'great', shields_azu,  4, 15, 13)
    bp_forr = _make_battle_pokemon('Forretress', 'VOLT_SWITCH', ['ROCK_TOMB'],
                                   'great', shields_forr, 5, 15, 13)
    result = simulate(bp_azu, bp_forr,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_azu}v{shields_forr}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    azu_score = round(result.pvpoke_score(0))
    assert azu_score == expected_azu_score, (
        f"{shields_azu}v{shields_forr}: expected Azu score={expected_azu_score}, "
        f"got {azu_score}  (delta={azu_score - expected_azu_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_azu}v{shields_forr}: battle log mismatch"
    )


# ---------------------------------------------------------------------------
# buffTarget == 'both' (Obstruct) — per-target buff arrays
# ---------------------------------------------------------------------------

def make_both_target_move():
    """Minimal Obstruct-shaped charged move: buffTarget='both' with distinct
    buffsSelf / buffsOpponent arrays (gamemaster OBSTRUCT: self +1 def,
    opponent -1 def, guaranteed)."""
    return {'moveId': 'FAKE_OBSTRUCT', 'name': 'Fake Obstruct', 'type': 'dark',
            'power': 15, 'energy': 40, 'energyGain': 0,
            'buffs': [0, 1], 'buffsSelf': [0, 1], 'buffsOpponent': [0, -1],
            'buffTarget': 'both', 'buffApplyChance': '1'}


class TestBuffTargetBoth:
    """PvPoke Battle.js:1406-1442: for buffTarget 'both', the attacker gets
    buffsSelf and the defender gets buffsOpponent — the generic 'buffs'
    array must not be applied to the defender."""

    def test_apply_move_buffs_uses_per_target_arrays(self):
        from gopvpsim.battle import _apply_move_buffs
        attacker = make_bp()
        defender = make_bp()
        _apply_move_buffs(attacker, defender, make_both_target_move())
        assert attacker.atk_stage == 0
        assert attacker.def_stage == 1    # buffsSelf [0, +1]
        assert defender.atk_stage == 0
        assert defender.def_stage == -1   # buffsOpponent [0, -1]

    def test_shield_policy_routes_both_move_through_would_shield(self):
        # Battle.js:1097-1100: a 'both' move with buffsSelf[0] > 0 or
        # buffsOpponent[1] < 0 routes through wouldShield instead of the
        # always-shield default. With a weak attacker, wouldShield says
        # don't shield — so the policy must return False here.
        move = make_both_target_move()
        move['selfBuffing'] = True   # PvPoke GameMaster.js:873 'both' clause
        # The move must be the attacker's own dict (charged_move_damage
        # resolves moves by identity).
        attacker = make_bp(atk=80.0, charged=[move])
        defender = make_bp(shields=2)
        assert pvpoke_simulate_shield(attacker, defender, move) is False

    @pytest.mark.integration
    def test_obstruct_gamemaster_flags(self):
        from gopvpsim.moves import get_moves
        _, charged = get_moves()
        m = charged['OBSTRUCT']
        # buffsSelf [0, +1] is a guaranteed positive self-buff →
        # selfBuffing per GameMaster.js:873 'both' clause.
        assert m['selfBuffing'] is True
        # selfDebuffing only applies to buffTarget == 'self' moves.
        assert m['selfDebuffing'] is False


@pytest.mark.integration
@pytest.mark.parametrize("shields_obs,shields_azu,expected_winner,expected_obs_score,expected_log", [
    # Obstagoon 5/15/12 L21 (COUNTER / OBSTRUCT + NIGHT_SLASH)
    # vs Azumarill 4/15/13 L43 (BUBBLE / ICE_BEAM + PLAY_ROUGH), Great League.
    # Fixture generated 2026-06-11 from scripts/pvpoke_trace.js (PvPoke clone
    # bc532fbda; OBSTRUCT/COUNTER/NIGHT_SLASH/BUBBLE/ICE_BEAM/PLAY_ROUGH and
    # both species' baseStats verified identical between the clone and the
    # live gamemaster). Pins the buffTarget='both' per-target arrays fix:
    # each Obstruct gives Obstagoon +1 def and Azumarill -1 def.
    (0, 0, 1, 235, ["Obstagoon: Obstruct", "Azumarill: Play Rough", "Obstagoon: Night Slash", "Azumarill: Ice Beam"]),
    (0, 1, 1, 170, ["Obstagoon: Obstruct", "Azumarill: Play Rough", "Obstagoon: Night Slash (shielded)", "Azumarill: Ice Beam"]),
    (0, 2, 1, 170, ["Obstagoon: Obstruct", "Azumarill: Play Rough", "Obstagoon: Night Slash (shielded)", "Azumarill: Ice Beam"]),
    (1, 0, 1, 374, ["Obstagoon: Obstruct", "Azumarill: Play Rough (shielded)", "Obstagoon: Obstruct", "Azumarill: Play Rough", "Obstagoon: Night Slash", "Azumarill: Ice Beam"]),
    (1, 1, 1, 295, ["Obstagoon: Obstruct", "Azumarill: Play Rough (shielded)", "Obstagoon: Obstruct", "Azumarill: Play Rough", "Obstagoon: Night Slash (shielded)", "Azumarill: Ice Beam"]),
    (1, 2, 1, 295, ["Obstagoon: Obstruct", "Azumarill: Play Rough (shielded)", "Obstagoon: Obstruct", "Azumarill: Play Rough", "Obstagoon: Night Slash (shielded)", "Azumarill: Ice Beam"]),
    (2, 0, None, 500, ["Obstagoon: Obstruct", "Azumarill: Ice Beam (shielded)", "Obstagoon: Obstruct", "Azumarill: Play Rough (shielded)", "Obstagoon: Night Slash", "Azumarill: Play Rough", "Obstagoon: Night Slash"]),
    (2, 1, 1, 429, ["Obstagoon: Obstruct", "Azumarill: Ice Beam (shielded)", "Obstagoon: Obstruct", "Azumarill: Play Rough (shielded)", "Obstagoon: Night Slash (shielded)", "Azumarill: Play Rough", "Obstagoon: Night Slash"]),
    (2, 2, 1, 350, ["Obstagoon: Obstruct", "Azumarill: Ice Beam (shielded)", "Obstagoon: Obstruct", "Azumarill: Play Rough (shielded)", "Obstagoon: Night Slash (shielded)", "Azumarill: Play Rough", "Obstagoon: Night Slash (shielded)"]),
])
def test_obstagoon_obstruct_vs_azumarill(shields_obs, shields_azu, expected_winner,
                                         expected_obs_score, expected_log):
    bp_obs = _make_battle_pokemon('Obstagoon', 'COUNTER', ['OBSTRUCT', 'NIGHT_SLASH'],
                                  'great', shields_obs, 5, 15, 12)
    bp_azu = _make_battle_pokemon('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
                                  'great', shields_azu, 4, 15, 13)
    result = simulate(bp_obs, bp_azu,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      shield_policy_0=pvpoke_simulate_shield,
                      shield_policy_1=pvpoke_simulate_shield,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_obs}v{shields_azu}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    obs_score = round(result.pvpoke_score(0))
    assert obs_score == expected_obs_score, (
        f"{shields_obs}v{shields_azu}: expected Obstagoon score={expected_obs_score}, "
        f"got {obs_score}  (delta={obs_score - expected_obs_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_obs}v{shields_azu}: battle log mismatch"
    )


# ---------------------------------------------------------------------------
# Buff/debuff matchups — verified at pvpoke.com/battle/
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("shields_bee,shields_med,expected_winner,expected_bee_score,expected_log", [
    # Beedrill 4/15/15 (POISON_JAB / FELL_STINGER + X_SCISSOR)
    # vs Medicham 7/15/14 (COUNTER / DYNAMIC_PUNCH + ICE_PUNCH), Great League
    # Policy: pvpoke_dp + always_shield
    #
    # Fell Stinger: guaranteed +1 atk buff on the user every activation.
    #
    # PvPoke verified scores (pvpoke.com/battle/):
    #              Med 0s   Med 1s   Med 2s
    #   Bee 0s:     707      471      507
    #   Bee 1s:     857      646      657
    #   Bee 2s:     857      796      807
    (0, 0, 0, 707, ['Beedrill: X-Scissor', 'Medicham: Ice Punch', 'Beedrill: X-Scissor']),
    (0, 1, 1, 471, ['Beedrill: X-Scissor (shielded)', 'Medicham: Ice Punch', 'Beedrill: X-Scissor', 'Medicham: Ice Punch']),
    (0, 2, 0, 507, ['Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch', 'Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch', 'Beedrill: X-Scissor']),
    (1, 0, 0, 857, ['Beedrill: X-Scissor', 'Medicham: Ice Punch (shielded)', 'Beedrill: X-Scissor']),
    (1, 1, 0, 646, ['Beedrill: X-Scissor (shielded)', 'Medicham: Ice Punch (shielded)', 'Beedrill: X-Scissor', 'Medicham: Ice Punch', 'Beedrill: Fell Stinger']),
    (1, 2, 0, 657, ['Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch (shielded)', 'Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch', 'Beedrill: X-Scissor']),
    (2, 0, 0, 857, ['Beedrill: X-Scissor', 'Medicham: Ice Punch (shielded)', 'Beedrill: X-Scissor']),
    (2, 1, 0, 796, ['Beedrill: X-Scissor (shielded)', 'Medicham: Ice Punch (shielded)', 'Beedrill: X-Scissor', 'Medicham: Ice Punch (shielded)', 'Beedrill: Fell Stinger']),
    (2, 2, 0, 807, ['Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch (shielded)', 'Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch (shielded)', 'Beedrill: X-Scissor']),
])
def test_beedrill_vs_medicham_fell_stinger(shields_bee, shields_med,
                                           expected_winner, expected_bee_score,
                                           expected_log):
    bp_bee = _make_battle_pokemon('Beedrill', 'POISON_JAB', ['FELL_STINGER', 'X_SCISSOR'],
                                  'great', shields_bee, 4, 15, 15)
    bp_med = _make_battle_pokemon('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'],
                                  'great', shields_med, 7, 15, 14)
    result = simulate(bp_bee, bp_med,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_bee}v{shields_med}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    bee_score = round(result.pvpoke_score(0))
    assert bee_score == expected_bee_score, (
        f"{shields_bee}v{shields_med}: expected Bee score={expected_bee_score}, "
        f"got {bee_score}  (delta={bee_score - expected_bee_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_bee}v{shields_med}: battle log mismatch"
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_cor,shields_med,expected_winner,expected_cor_score,expected_log", [
    # Corviknight 4/12/14 (AIR_SLASH / AIR_CUTTER + PAYBACK)
    # vs Medicham 7/15/14 (COUNTER / DYNAMIC_PUNCH + ICE_PUNCH), Great League
    # Policy: pvpoke_dp + always_shield
    #
    # Air Cutter: 30% chance (+1 atk buff to user); deterministic meter fires every ~3 uses.
    #
    # PvPoke verified scores (pvpoke.com/battle/):
    #              Med 0s   Med 1s   Med 2s
    #   Cor 0s:     566      478      326
    #   Cor 1s:     756      478      326
    #   Cor 2s:     756      693      633
    (0, 0, 0, 566, ['Corviknight: Air Cutter', 'Medicham: Dynamic Punch', 'Corviknight: Air Cutter']),
    (0, 1, 1, 478, ['Corviknight: Air Cutter (shielded)', 'Medicham: Dynamic Punch', 'Corviknight: Air Cutter', 'Medicham: Ice Punch']),
    (0, 2, 1, 326, ['Corviknight: Air Cutter (shielded)', 'Medicham: Dynamic Punch', 'Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch']),
    (1, 0, 0, 756, ['Corviknight: Air Cutter', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter']),
    (1, 1, 1, 478, ['Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter', 'Medicham: Dynamic Punch']),
    (1, 2, 1, 326, ['Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter (shielded)', 'Medicham: Dynamic Punch']),
    (2, 0, 0, 756, ['Corviknight: Air Cutter', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter']),
    (2, 1, 0, 693, ['Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch (shielded)', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter']),
    (2, 2, 0, 633, ['Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter']),
])
def test_corviknight_vs_medicham_air_cutter(shields_cor, shields_med,
                                            expected_winner, expected_cor_score,
                                            expected_log):
    bp_cor = _make_battle_pokemon('Corviknight', 'AIR_SLASH', ['AIR_CUTTER', 'PAYBACK'],
                                  'great', shields_cor, 4, 12, 14)
    bp_med = _make_battle_pokemon('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'],
                                  'great', shields_med, 7, 15, 14)
    result = simulate(bp_cor, bp_med,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_cor}v{shields_med}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    cor_score = round(result.pvpoke_score(0))
    assert cor_score == expected_cor_score, (
        f"{shields_cor}v{shields_med}: expected Cor score={expected_cor_score}, "
        f"got {cor_score}  (delta={cor_score - expected_cor_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_cor}v{shields_med}: battle log mismatch"
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_mie,shields_med,expected_winner,expected_mie_score,expected_log", [
    # Mienfoo 13/15/15 (LOW_KICK / HIGH_JUMP_KICK + LOW_SWEEP)
    # vs Medicham 7/15/14 (COUNTER / DYNAMIC_PUNCH + ICE_PUNCH), Great League
    # Policy: pvpoke_dp + always_shield
    #
    # High Jump Kick: 10% self-debuff (-2 def stages); deterministic meter fires every 10 uses.
    # In a typical GL battle HJK fires <10 times so the debuff does not trigger here.
    # These tests cover normal HJK behavior; the self-debuff code path is exercised
    # only in longer battles.
    #
    # PvPoke verified scores (pvpoke.com/battle/):
    #              Med 0s   Med 1s   Med 2s
    #   Mie 0s:     269       78       78
    #   Mie 1s:     521      347      145
    #   Mie 2s:     414      212      145
    (0, 0, 1, 269, ['Mienfoo: High Jump Kick', 'Medicham: Dynamic Punch']),
    (0, 1, 1,  78, ['Mienfoo: High Jump Kick (shielded)', 'Medicham: Dynamic Punch']),
    (0, 2, 1,  78, ['Mienfoo: Low Sweep (shielded)', 'Medicham: Dynamic Punch']),
    (1, 0, 0, 521, ['Mienfoo: High Jump Kick', 'Medicham: Ice Punch (shielded)', 'Mienfoo: High Jump Kick']),
    (1, 1, 1, 347, ['Mienfoo: High Jump Kick (shielded)', 'Medicham: Ice Punch (shielded)', 'Mienfoo: High Jump Kick', 'Medicham: Ice Punch']),
    (1, 2, 1, 145, ['Mienfoo: Low Sweep (shielded)', 'Medicham: Ice Punch (shielded)', 'Mienfoo: High Jump Kick (shielded)', 'Medicham: Ice Punch']),
    (2, 0, 1, 414, ['Mienfoo: High Jump Kick', 'Mienfoo: Low Sweep', 'Medicham: Dynamic Punch (shielded)']),
    (2, 1, 1, 212, ['Mienfoo: High Jump Kick (shielded)', 'Mienfoo: Low Sweep']),
    (2, 2, 1, 145, ['Mienfoo: Low Sweep (shielded)', 'Mienfoo: High Jump Kick (shielded)']),
])
def test_mienfoo_vs_medicham_high_jump_kick(shields_mie, shields_med,
                                            expected_winner, expected_mie_score,
                                            expected_log):
    bp_mie = _make_battle_pokemon('Mienfoo', 'LOW_KICK', ['HIGH_JUMP_KICK', 'LOW_SWEEP'],
                                  'great', shields_mie, 13, 15, 15)
    bp_med = _make_battle_pokemon('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'],
                                  'great', shields_med, 7, 15, 14)
    result = simulate(bp_mie, bp_med,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_mie}v{shields_med}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    mie_score = round(result.pvpoke_score(0))
    assert mie_score == expected_mie_score, (
        f"{shields_mie}v{shields_med}: expected Mie score={expected_mie_score}, "
        f"got {mie_score}  (delta={mie_score - expected_mie_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_mie}v{shields_med}: battle log mismatch"
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_cor,shields_azu,expected_winner,expected_cor_score,expected_log", [
    # Corviknight 4/12/14 (AIR_SLASH / AIR_CUTTER + PAYBACK)
    # vs Azumarill 4/15/13 (BUBBLE / ICE_BEAM + PLAY_ROUGH), Great League
    # Policy: pvpoke_dp + always_shield
    #
    # Corviknight throws 3 Air Cutters; deterministic buff meter fires on the 3rd.
    # Tests chance-buff firing mid-battle affecting subsequent damage.
    #
    # PvPoke verified scores (pvpoke.com/battle/):
    #              Azu 0s   Azu 1s   Azu 2s
    #   Cor 0s:     426      356      285
    #   Cor 1s:     445      374      303
    #   Cor 2s:     586      586      536
    (0, 0, 1, 426, ['Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
    (0, 1, 1, 356, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
    (0, 2, 1, 285, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
    (1, 0, 1, 445, ['Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam']),
    (1, 1, 1, 374, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam']),
    (1, 2, 1, 303, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam']),
    (2, 0, 0, 586, ['Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
    (2, 1, 0, 586, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
    (2, 2, 0, 536, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Payback']),
])
def test_corviknight_vs_azumarill_air_cutter_buff(shields_cor, shields_azu,
                                                   expected_winner, expected_cor_score,
                                                   expected_log):
    bp_cor = _make_battle_pokemon('Corviknight', 'AIR_SLASH', ['AIR_CUTTER', 'PAYBACK'],
                                  'great', shields_cor, 4, 12, 14)
    bp_azu = _make_battle_pokemon('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
                                  'great', shields_azu, 4, 15, 13)
    result = simulate(bp_cor, bp_azu,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_cor}v{shields_azu}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    cor_score = round(result.pvpoke_score(0))
    assert cor_score == expected_cor_score, (
        f"{shields_cor}v{shields_azu}: expected Cor score={expected_cor_score}, "
        f"got {cor_score}  (delta={cor_score - expected_cor_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_cor}v{shields_azu}: battle log mismatch"
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_swam,shields_regi,expected_winner,expected_swam_score,expected_log", [
    # Shadow Swampert 15/15/15 (MUD_SHOT / HYDRO_CANNON + EARTHQUAKE)
    # vs Registeel 15/15/15 (LOCK_ON / FLASH_CANNON + FOCUS_BLAST), Great League
    # Policy: pvpoke_dp + always_shield
    #
    # Tests shadow multipliers: Shadow Swampert deals ×1.2 damage, takes ×1.2 damage.
    #
    # PvPoke verified scores (Swampert's perspective):
    #              Regi 0s  Regi 1s  Regi 2s
    #   Swam 0s:    720      686      216
    #   Swam 1s:    936      902      232
    #   Swam 2s:    936      902      861
    #
    # Re-vetted 2026-06-06 via scripts/pvpoke_trace.js against pvpoke
    # bc532fbda after the June-2026 move rebalance (Flash Cannon 70->65
    # energy, Earthquake 110->120 power). The 0v0/0v1/0v2/1v2 cells shifted
    # vs the pre-rebalance fixture (Registeel now throws Flash Cannon first
    # at the cheaper cost); our sim matches PvPoke exactly on all 9 cells
    # (score, winner, chargedLog).
    (0, 0, 0, 720, ['Registeel: Flash Cannon', 'Swampert: Earthquake']),
    (0, 1, 0, 686, ['Registeel: Flash Cannon', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Earthquake']),
    (0, 2, 1, 216, ['Registeel: Flash Cannon', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Registeel: Flash Cannon']),
    (1, 0, 0, 936, ['Registeel: Focus Blast (shielded)', 'Swampert: Earthquake']),
    (1, 1, 0, 902, ['Registeel: Flash Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Earthquake']),
    (1, 2, 1, 232, ['Registeel: Flash Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Registeel: Focus Blast']),
    (2, 0, 0, 936, ['Registeel: Focus Blast (shielded)', 'Swampert: Earthquake']),
    (2, 1, 0, 902, ['Registeel: Flash Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Earthquake']),
    (2, 2, 0, 861, ['Registeel: Flash Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Registeel: Flash Cannon (shielded)', 'Swampert: Earthquake']),
])
def test_shadow_swampert_vs_registeel(shields_swam, shields_regi, expected_winner,
                                      expected_swam_score, expected_log):
    bp_swam = _make_battle_pokemon('Swampert', 'MUD_SHOT', ['HYDRO_CANNON', 'EARTHQUAKE'],
                                    'great', shields_swam, 15, 15, 15, shadow=True)
    bp_regi = _make_battle_pokemon('Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST'],
                                    'great', shields_regi, 15, 15, 15)
    result = simulate(bp_swam, bp_regi,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_swam}v{shields_regi}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    swam_score = round(result.pvpoke_score(0))
    assert swam_score == expected_swam_score, (
        f"{shields_swam}v{shields_regi}: expected Swam score={expected_swam_score}, "
        f"got {swam_score}  (delta={swam_score - expected_swam_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_swam}v{shields_regi}: battle log mismatch"
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_0,shields_1,expected_winner,expected_score_0,expected_log", [
    # Corviknight mirror: 4/12/14 vs 4/12/14 (AIR_SLASH / AIR_CUTTER only), Great League
    # Policy: pvpoke_dp + always_shield
    #
    # Tests both mons with chance-based buff (Air Cutter: 30% +1 ATK).
    # Deterministic buffApplyMeter fires on the 4th Air Cutter for each mon.
    # Non-shielded damage: 18 (unbuffed) → 23 (buffed, after 4th lands).
    # The 3rd non-shielded Air Cutter triggers the buff; the 4th hits for 23.
    #
    # PvPoke verified scores (pvpoke.com/battle/, Corv0's perspective):
    #              Corv1 0s  Corv1 1s  Corv1 2s
    #   Corv0 0s:    500       443       386
    #   Corv0 1s:    556       500       500
    #   Corv0 2s:    613       500       500
    (0, 0, None, 500, ['Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (0, 1, 1, 443, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (0, 2, 1, 386, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (1, 0, 0, 556, ['Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (1, 1, None, 500, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (1, 2, None, 500, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (2, 0, 0, 613, ['Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (2, 1, None, 500, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (2, 2, None, 500, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
])
def test_corviknight_mirror_both_buff(shields_0, shields_1,
                                      expected_winner, expected_score_0,
                                      expected_log):
    bp0 = _make_battle_pokemon('Corviknight', 'AIR_SLASH', ['AIR_CUTTER'],
                                'great', shields_0, 4, 12, 14)
    bp1 = _make_battle_pokemon('Corviknight', 'AIR_SLASH', ['AIR_CUTTER'],
                                'great', shields_1, 4, 12, 14)
    result = simulate(bp0, bp1,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    if expected_winner is None:
        assert result.winner is None, (
            f"{shields_0}v{shields_1}: expected tie, "
            f"got winner={result.winner}  HP={result.hp_remaining}"
        )
    else:
        assert result.winner == expected_winner, (
            f"{shields_0}v{shields_1}: expected winner={expected_winner}, "
            f"got {result.winner}  HP={result.hp_remaining}"
        )
    score_0 = round(result.pvpoke_score(0))
    assert score_0 == expected_score_0, (
        f"{shields_0}v{shields_1}: expected Corv0 score={expected_score_0}, "
        f"got {score_0}  (delta={score_0 - expected_score_0:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_0}v{shields_1}: battle log mismatch"
    )


# ---------------------------------------------------------------------------
# Default moveset integration tests
# ---------------------------------------------------------------------------

def _make_battle_pokemon_default(species, league, shields, shadow=False):
    """Build a BattlePokemon using PvPoke's default moveset and default IVs (15/15/15)."""
    from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS
    from gopvpsim.moves import get_moves
    from gopvpsim.data import get_default_moveset

    fast_id, charged_ids = get_default_moveset(species, league=league, shadow=shadow)
    pokemon = Pokemon.at_best_level(species, 15, 15, 15,
                                    league=league, shadow=shadow)
    fast_moves, charged_moves = get_moves()
    fm  = dict(fast_moves[fast_id])
    cms = [dict(charged_moves[cid]) for cid in charged_ids]

    return BattlePokemon.from_pokemon(
        pokemon, fm, cms, shields=shields,
        league_cp=LEAGUE_CAPS[league],
    )


@pytest.mark.integration
def test_default_moveset_medicham_vs_azumarill_runs():
    """Smoke test: default movesets produce a valid battle result."""
    bp_med = _make_battle_pokemon_default('Medicham', 'great', shields=1)
    bp_azu = _make_battle_pokemon_default('Azumarill', 'great', shields=1)
    result = simulate(bp_med, bp_azu,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp)
    assert result.winner in (0, 1, -1)
    assert 0 < result.pvpoke_score(0) < 1000
    assert 0 < result.pvpoke_score(1) < 1000


@pytest.mark.integration
def test_default_moveset_medicham_uses_psycho_cut():
    """Medicham's default fast move should be PSYCHO_CUT in Great League."""
    bp = _make_battle_pokemon_default('Medicham', 'great', shields=2)
    assert bp.fast_move['moveId'] == 'PSYCHO_CUT'


@pytest.mark.integration
def test_default_moveset_shadow_runs():
    """Shadow Pokemon default movesets should work too."""
    bp_shadow = _make_battle_pokemon_default('Quagsire', 'great', shields=1, shadow=True)
    bp_normal = _make_battle_pokemon_default('Medicham', 'great', shields=1)
    result = simulate(bp_shadow, bp_normal,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp)
    assert result.winner in (0, 1, -1)


# ---------------------------------------------------------------------------
# No-bait oracle tests — sourced from HSH #iv-tech deep dive references
# ---------------------------------------------------------------------------

def _corvi_vs_shadow_sableye(shields, bait_shields):
    """Build and simulate max-def Corvi vs default Shadow Sableye.

    Both sides use PvPoke's default move sets for Great League, fetched
    via ``get_default_moveset`` so the test tracks PvPoke's rankings
    automatically (never hardcode move IDs — see CLAUDE.md "Testing").
    """
    from functools import partial
    corvi_fast, corvi_charged = get_default_moveset('Corviknight', 'great')
    sab_fast, sab_charged = get_default_moveset('Sableye', 'great', shadow=True)
    bp_corvi = _make_battle_pokemon(
        'Corviknight', corvi_fast, corvi_charged,
        'great', shields=shields, atk_iv=0, def_iv=15, sta_iv=2)
    # Shadow Sableye PvPoke default IVs: [47, 4, 15, 15]
    bp_sab = _make_battle_pokemon(
        'Sableye', sab_fast, sab_charged,
        'great', shields=shields, atk_iv=4, def_iv=15, sta_iv=15,
        max_level=47.0, shadow=True)

    focal_policy = (pvpoke_dp if bait_shields
                    else partial(pvpoke_dp, bait_shields=False))
    return simulate(bp_corvi, bp_sab,
                    charged_policy_0=focal_policy,
                    charged_policy_1=pvpoke_dp,
                    shield_policy_0=pvpoke_simulate_shield,
                    shield_policy_1=pvpoke_simulate_shield)


@pytest.mark.integration
@pytest.mark.parametrize("bait_shields", [True, False])
def test_corviknight_max_def_wins_1v1_vs_default_shadow_sableye(bait_shields):
    """Oracle test from `docs/corviknight_deep_dive_reference.md:58`:

        "135.46 defense (max defense) ... flips the 1 without baiting"

    Max-def Corviknight (0/15/2, def=135.47) vs default-IV Shadow Sableye
    (4/15/15 @ level 47) wins the 1-shield scenario in both bait modes.
    The reference specifically calls out that the win is achievable
    *without* baiting — bait_shields=False tests that directly.

    Parametrized over both modes to document that bait_shields=True also
    wins here — the two modes differ in first-throw choice (Air Cutter
    bait vs Payback best-DPE) but converge to the same winner. Expected
    scores (2026-04-12): bait_on=603, bait_off=551.
    """
    result = _corvi_vs_shadow_sableye(shields=1, bait_shields=bait_shields)
    assert result.winner == 0, (
        f"bait_shields={bait_shields}: expected Corviknight to win the 1s, "
        f"got winner={result.winner}, HP left: {result.hp_remaining}")
    corvi_score = result.pvpoke_score(0)
    assert corvi_score >= 500, (
        f"bait_shields={bait_shields}: Corvi score {corvi_score:.1f} < 500 "
        f"(matchup not flipped)")


def _tinkaton_vs_medicham(tink_ivs, med_scenario, shields, bait_shields):
    """Build and simulate Tinkaton vs Medicham using PvPoke default movesets.

    med_scenario: 'rank1' (non-best-buddy rank 1 by stat product, max_level=50)
                  or 'default' (PvPoke default IVs + level).
    """
    from functools import partial
    from gopvpsim.pokemon import iv_rank, pvpoke_default_ivs

    tink_fast, tink_charged = get_default_moveset('Tinkaton', 'great')
    med_fast, med_charged = get_default_moveset('Medicham', 'great')

    bp_tink = _make_battle_pokemon(
        'Tinkaton', tink_fast, tink_charged,
        'great', shields=shields,
        atk_iv=tink_ivs[0], def_iv=tink_ivs[1], sta_iv=tink_ivs[2])

    if med_scenario == 'rank1':
        r1 = iv_rank('Medicham', league='great', max_level=50)[0]
        bp_med = _make_battle_pokemon(
            'Medicham', med_fast, med_charged,
            'great', shields=shields,
            atk_iv=r1['atk_iv'], def_iv=r1['def_iv'], sta_iv=r1['sta_iv'],
            max_level=50.0)
    else:  # 'default'
        lv, a, d, s = pvpoke_default_ivs('Medicham', league='great')
        bp_med = _make_battle_pokemon(
            'Medicham', med_fast, med_charged,
            'great', shields=shields,
            atk_iv=a, def_iv=d, sta_iv=s, max_level=lv)

    focal_policy = (pvpoke_dp if bait_shields
                    else partial(pvpoke_dp, bait_shields=False))
    return simulate(bp_tink, bp_med,
                    charged_policy_0=focal_policy,
                    charged_policy_1=pvpoke_dp,
                    shield_policy_0=pvpoke_simulate_shield,
                    shield_policy_1=pvpoke_simulate_shield)


@pytest.mark.integration
@pytest.mark.parametrize("med_scenario", ['rank1', 'default'])
@pytest.mark.parametrize("bait_shields", [True, False])
def test_tinkaton_wins_1v1_vs_medicham_no_bait(med_scenario, bait_shields):
    """Oracle from `docs/tinkaton_deep_dive_reference.md:25`:

        "141.66 defense with 138 hp lets you shield a dynamic punch &
         survive two more against the rank #1 medicham (non best buddy)
         and default iv medicham to win the 1s without baiting"

    Tinkaton 1/14/14 (def=141.66 exactly, hp=143, atk=105.23) wins the
    1-shield scenario against both rank #1 non-best-buddy Medicham
    (5/15/15 @ lvl 50) and PvPoke-default Medicham (7/15/14 @ lvl 49)
    in both bait modes. The reference's "win the 1s without baiting"
    claim is tested via bait_shields=False.

    Note: bait_shields has no observable effect in this matchup (same
    score 520 regardless) because pvpoke_dp enters near-KO DP phase
    early — Tinkaton's Gigaton Hammer (130 power / 60 energy) dominates
    actual-DPE, so there's no farm-down baiting opportunity. This test
    exercises the no-bait code path but doesn't demonstrate directional
    difference; for that see `test_corviknight_2v2_...`.

    Caveat: our sim has a more forgiving win threshold than the
    reference implies — many Tinkaton spreads below def=141.66 also
    win the 1v1. That's not tested here but is worth follow-up. The
    reference asserts SUFFICIENT conditions, which is what we test.
    """
    result = _tinkaton_vs_medicham(
        tink_ivs=(1, 14, 14), med_scenario=med_scenario,
        shields=1, bait_shields=bait_shields)
    assert result.winner == 0, (
        f"med_scenario={med_scenario} bait_shields={bait_shields}: "
        f"expected Tinkaton to win the 1s, got winner={result.winner}, "
        f"HP={result.hp_remaining}")
    assert result.pvpoke_score(0) >= 500


@pytest.mark.integration
@pytest.mark.parametrize("bait_shields", [True, False])
def test_tinkaton_def_143_flips_1v2_vs_rank1_azumarill(bait_shields):
    """Oracle from `docs/tinkaton_deep_dive_reference.md:27`:

        "143.03 defense gives a bulkpoint vs rank #1 azu which flips
         the 1-2s (no baiting required)"

    **Directional def bulkpoint test.** Same Tinkaton vs same rank #1
    Azumarill (0/15/15 @ lvl 45.5), same moves (Fairy Wind / Gigaton
    Hammer + Bulldoze vs Bubble / Ice Beam + Play Rough), same 1-2
    shield scenario — only the Tinkaton defense changes:

      - Tink 1/14/14 (def=141.66): LOSES 1v2 (score 397 < 500)
      - Tink 0/14/9  (def=143.04): WINS  1v2 (score 535 ≥ 500)

    Crossing def=143.03 flips the matchup outcome. Parametrized over
    bait modes to verify the "no baiting required" qualifier — bait-off
    produces the same flip as bait-on, because pvpoke_dp enters near-KO
    DP immediately in this matchup and doesn't use farm-down baiting.
    """
    from gopvpsim.pokemon import iv_rank
    from functools import partial

    tink_fast, tink_charged = get_default_moveset('Tinkaton', 'great')
    azu_fast, azu_charged = get_default_moveset('Azumarill', 'great')
    azu_r1 = iv_rank('Azumarill', league='great')[0]

    def run(tink_ivs):
        bp_tink = _make_battle_pokemon(
            'Tinkaton', tink_fast, tink_charged, 'great', shields=1,
            atk_iv=tink_ivs[0], def_iv=tink_ivs[1], sta_iv=tink_ivs[2])
        bp_azu = _make_battle_pokemon(
            'Azumarill', azu_fast, azu_charged, 'great', shields=2,
            atk_iv=azu_r1['atk_iv'], def_iv=azu_r1['def_iv'],
            sta_iv=azu_r1['sta_iv'], max_level=azu_r1['level'])
        pol = (pvpoke_dp if bait_shields
               else partial(pvpoke_dp, bait_shields=False))
        return simulate(bp_tink, bp_azu,
                        charged_policy_0=pol,
                        charged_policy_1=pvpoke_dp,
                        shield_policy_0=pvpoke_simulate_shield,
                        shield_policy_1=pvpoke_simulate_shield)

    # Below the def=143.03 threshold: Tinkaton loses 1v2
    r_below = run((1, 14, 14))  # def=141.66
    assert r_below.winner == 1, (
        f"bait_shields={bait_shields}: expected Tinkaton (def=141.66) "
        f"to LOSE 1v2 below the bulkpoint, got winner={r_below.winner}, "
        f"HP={r_below.hp_remaining}")
    assert r_below.pvpoke_score(0) < 500

    # At/above the def=143.03 threshold: Tinkaton wins 1v2
    r_at = run((0, 14, 9))  # def=143.04
    assert r_at.winner == 0, (
        f"bait_shields={bait_shields}: expected Tinkaton (def=143.04) "
        f"to WIN 1v2 at the bulkpoint, got winner={r_at.winner}, "
        f"HP={r_at.hp_remaining}")
    assert r_at.pvpoke_score(0) >= 500


@pytest.mark.integration
def test_corviknight_2v2_vs_default_shadow_sableye_flips_with_bait():
    """Oracle test from `docs/corviknight_deep_dive_reference.md:58`:

        "135.46 defense ... flips the 2s if you bait twice"

    This is the *directional* half of the Corvi vs Shadow Sableye oracle:
    in the 2-shield scenario, the matchup outcome FLIPS with bait mode.
    With baiting enabled, Corvi wins (throws Air Cutter twice to burn
    both Sableye shields, then lands Payback for the KO). Without
    baiting, Corvi throws Payback twice into shields and dies before
    reaching a third charge.

    This is the strongest oracle we have for the ``bait_shields``
    parameter: if the gate regresses or pvpoke_dp's farm-down bait
    branch stops firing, this test will flip and catch it.

    Expected scores (2026-04-12): bait_on=531, bait_off=288.
    """
    # With baiting: Corvi wins (Air Cutter x2 bait → Payback lands)
    result_bait = _corvi_vs_shadow_sableye(shields=2, bait_shields=True)
    assert result_bait.winner == 0, (
        f"bait_on 2v2: expected Corviknight to win via bait-twice, "
        f"got winner={result_bait.winner}, HP={result_bait.hp_remaining}")
    assert result_bait.pvpoke_score(0) >= 500

    # Without baiting: Sableye wins (Corvi throws Payback into shields)
    result_nobait = _corvi_vs_shadow_sableye(shields=2, bait_shields=False)
    assert result_nobait.winner == 1, (
        f"bait_off 2v2: expected Sableye to win, got "
        f"winner={result_nobait.winner}, HP={result_nobait.hp_remaining}")
    assert result_nobait.pvpoke_score(0) < 500


# ---------------------------------------------------------------------------
# Form change oracle tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("shields_m,shields_a,expected_morpeko_score,expected_log", [
    # Morpeko (Full Belly) 5/14/15 vs Azumarill 4/15/13, Great League
    # THUNDER_SHOCK / AURA_WHEEL_ELECTRIC / PSYCHIC_FANGS
    # vs BUBBLE / ICE_BEAM / PLAY_ROUGH
    # Scores verified at pvpoke.com/battle/ 2026-04-14.
    # Form change: Morpeko enters in Full Belly (always, at battle start
    # and on switch-in) and toggles Full Belly <-> Hangry after EACH
    # charged move, swapping AURA_WHEEL_ELECTRIC <-> AURA_WHEEL_DARK.
    # The two-way toggle + Full-Belly-on-entry were verified in-game by
    # Michael 2026-06-06.
    #
    # expected_log is OUR (correct) chargedLog, NOT PvPoke's. PvPoke has a
    # form-toggle bug (DEVELOPER_NOTES "PvPoke bugs found" #8): its
    # Battle.js:1536 guard `activeFormId != alternativeFormId` makes
    # Morpeko stick in Hangry after the FIRST charged move instead of
    # toggling back, so PvPoke's chargedLog disagrees with ours on cells
    # 1v1/1v2/2v1/2v2 (a Morpeko throw tagged Hangry where it should be
    # Full Belly). Scores still match because every label-differing throw
    # is form-independent (Psychic Fangs) or a shielded Aura Wheel (1 dmg).
    # This assertion pins our correct two-way behavior so a regression
    # toward PvPoke's one-way bug fails here.
    (0, 0, 489, ['Morpeko (Full Belly): Aura Wheel', 'Azumarill: Play Rough']),
    (0, 1, 219, ['Morpeko (Full Belly): Psychic Fangs (shielded)', 'Morpeko (Hangry): Psychic Fangs', 'Azumarill: Play Rough']),
    (0, 2, 219, ['Morpeko (Full Belly): Psychic Fangs (shielded)', 'Morpeko (Hangry): Psychic Fangs', 'Azumarill: Play Rough']),
    (1, 0, 817, ['Morpeko (Full Belly): Aura Wheel', 'Azumarill: Play Rough (shielded)', 'Morpeko (Hangry): Psychic Fangs']),
    (1, 1, 728, ['Morpeko (Full Belly): Psychic Fangs (shielded)', 'Azumarill: Ice Beam (shielded)', 'Morpeko (Hangry): Aura Wheel', 'Morpeko (Full Belly): Psychic Fangs']),
    (1, 2, 348, ['Morpeko (Full Belly): Psychic Fangs (shielded)', 'Morpeko (Hangry): Psychic Fangs', 'Azumarill: Ice Beam (shielded)', 'Morpeko (Full Belly): Aura Wheel (shielded)', 'Azumarill: Ice Beam']),
    (2, 0, 817, ['Morpeko (Full Belly): Aura Wheel', 'Azumarill: Play Rough (shielded)', 'Morpeko (Hangry): Psychic Fangs']),
    (2, 1, 728, ['Morpeko (Full Belly): Psychic Fangs (shielded)', 'Azumarill: Ice Beam (shielded)', 'Morpeko (Hangry): Aura Wheel', 'Morpeko (Full Belly): Psychic Fangs']),
    (2, 2, 665, ['Morpeko (Full Belly): Psychic Fangs (shielded)', 'Morpeko (Hangry): Psychic Fangs', 'Azumarill: Ice Beam (shielded)', 'Morpeko (Full Belly): Psychic Fangs (shielded)', 'Azumarill: Play Rough (shielded)', 'Morpeko (Hangry): Psychic Fangs']),
])
def test_morpeko_vs_azumarill_form_change(shields_m, shields_a, expected_morpeko_score, expected_log):
    """Morpeko form change: Aura Wheel toggles Electric/Dark type each charged move."""
    bp_m = _make_battle_pokemon(
        'Morpeko (Full Belly)', 'THUNDER_SHOCK',
        ['AURA_WHEEL_ELECTRIC', 'PSYCHIC_FANGS'],
        'great', shields_m, 5, 14, 15,
    )
    bp_a = _make_battle_pokemon(
        'Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
        'great', shields_a, 4, 15, 13,
    )
    result = simulate(bp_m, bp_a,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    score = round(result.pvpoke_score(0))
    assert score == expected_morpeko_score, (
        f"{shields_m}v{shields_a}: expected Morpeko score={expected_morpeko_score}, "
        f"got {score} (delta={score - expected_morpeko_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_m}v{shields_a}: chargedLog mismatch (pins our correct "
        f"two-way toggle; see PvPoke bug #8)"
    )


# Aegislash bandaid-triage xfails. Each reason pins the specific
# divergence the chargedLog reveals, not just "scores don't match".
# Captured 2026-04-15 from scripts/pvpoke_trace.js harness.
_AEGI_XFAIL_GB_SHIELD_FIRST = pytest.mark.xfail(
    strict=True,   # XPASS must be loud: it means PvPoke fixed bug #3 upstream
    reason=(
        "PvPoke bug #3: picks Gyro Ball over Shadow Ball for the first "
        "(shielded) throw. GB and SB cost the same energy; SB does "
        "strictly more damage. Since the first throw is shielded, both "
        "score the same, but the chargedLog disagrees on which move was "
        "thrown. Our Aegislash correctly picks SB."))
_AEGI_XFAIL_GB_CASCADE = pytest.mark.xfail(
    strict=True,   # XPASS must be loud: it means PvPoke fixed bugs #2/#3
    reason=(
        "PvPoke bug #3 + #2: Aegislash throws 3x Gyro Ball where we "
        "throw 3x Shadow Ball (with a Play Rough shielded in between). "
        "Root cause: PvPoke picks GB over SB for Aegislash AND keeps "
        "Azu's bestChargedMove cached against Shield-form def (IB), so "
        "Azu never switches to PR after Aegi goes Blade. Our 510 vs "
        "PvPoke's 376."))


@pytest.mark.integration
@pytest.mark.parametrize("shields_a,shields_z,expected_aegi_score,expected_log", [
    # Aegislash (Shield) 4/14/15 vs Azumarill 4/15/13, Great League
    # AEGISLASH_CHARGE_PSYCHO_CUT / SHADOW_BALL / GYRO_BALL
    # vs BUBBLE / ICE_BEAM / PLAY_ROUGH
    # Verified at pvpoke.com/battle/ 2026-04-14
    # Form change: Shield -> Blade on charged move (activate_charged),
    # Blade -> Shield on shield use (activate_shield).
    #
    # Expected chargedLog is the PvPoke harness ground truth. Cases
    # where our log disagrees with PvPoke's log get an xfail with a
    # concrete reason describing the mechanical difference.
    (0, 0, 773, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    pytest.param(0, 1, 374, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                             'Aegislash (Blade): Gyro Ball (shielded)',
                             'Aegislash (Blade): Shadow Ball',
                             'Azumarill: Ice Beam'],
                 marks=_AEGI_XFAIL_GB_SHIELD_FIRST),
    pytest.param(0, 2, 112, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                             'Aegislash (Blade): Gyro Ball (shielded)',
                             'Aegislash (Blade): Shadow Ball (shielded)',
                             'Azumarill: Ice Beam'],
                 marks=_AEGI_XFAIL_GB_SHIELD_FIRST),
    (1, 0, 773, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    pytest.param(1, 1, 640, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                             'Aegislash (Blade): Gyro Ball (shielded)',
                             'Aegislash (Blade): Shadow Ball (shielded)',
                             'Azumarill: Ice Beam (shielded)',
                             'Aegislash (Blade): Shadow Ball'],
                 marks=_AEGI_XFAIL_GB_SHIELD_FIRST),
    pytest.param(1, 2, 376, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                             'Aegislash (Blade): Gyro Ball (shielded)',
                             'Aegislash (Blade): Gyro Ball (shielded)',
                             'Aegislash (Blade): Gyro Ball'],
                 marks=_AEGI_XFAIL_GB_CASCADE),
    (2, 0, 773, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    pytest.param(2, 1, 640, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                             'Aegislash (Blade): Gyro Ball (shielded)',
                             'Aegislash (Blade): Shadow Ball (shielded)',
                             'Azumarill: Ice Beam (shielded)',
                             'Aegislash (Blade): Shadow Ball'],
                 marks=_AEGI_XFAIL_GB_SHIELD_FIRST),
    pytest.param(2, 2, 376, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                             'Aegislash (Blade): Gyro Ball (shielded)',
                             'Aegislash (Blade): Gyro Ball (shielded)',
                             'Aegislash (Blade): Gyro Ball'],
                 marks=_AEGI_XFAIL_GB_CASCADE),
])
def test_aegislash_vs_azumarill_form_change(shields_a, shields_z,
                                            expected_aegi_score, expected_log):
    """Aegislash form change: Shield<->Blade on charged move / shield use.

    Assertion checks both PvPoke score AND chargedLog (turn-by-turn
    charged-move sequence). chargedLog is what diagnoses actual
    behavioral divergence; the score can coincidentally match even when
    the fights play out differently (e.g. GB vs SB both get shielded).
    """
    bp_a = _make_battle_pokemon(
        'Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT',
        ['SHADOW_BALL', 'GYRO_BALL'],
        'great', shields_a, 4, 14, 15,
    )
    bp_z = _make_battle_pokemon(
        'Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
        'great', shields_z, 4, 15, 13,
    )
    result = simulate(bp_a, bp_z,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    score = round(result.pvpoke_score(0))
    assert score == expected_aegi_score, (
        f"{shields_a}v{shields_z}: expected Aegislash score={expected_aegi_score}, "
        f"got {score} (delta={score - expected_aegi_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_a}v{shields_z}: chargedLog mismatch vs PvPoke harness"
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_m,shields_a,expected_mimikyu_score,expected_log", [
    # Mimikyu 5/13/15 vs Azumarill 4/15/13, Great League
    # SHADOW_CLAW / SHADOW_SNEAK / PLAY_ROUGH
    # vs BUBBLE / ICE_BEAM / PLAY_ROUGH
    # Verified at pvpoke.com/battle/ 2026-04-14
    # Form change: Disguise absorbs first unshielded charged hit (dmg=1),
    # then Mimikyu becomes Busted with permanent -1 def stage.
    #
    # Expected chargedLog is the PvPoke harness ground truth. All 9
    # cases now match PvPoke exactly. The previously-suspected "PvPoke
    # bug #4" (Mimi delays first SS by 1 SC) turned out to be a
    # phantom — our disguise-bust branch was just missing the
    # "Azumarill uses Ice Beam → 1 dmg" log line, so chargedLog
    # appeared to disagree on Azu's IB timing when the underlying sim
    # was correct. Fixed 2026-04-15; xfails removed.
    (0, 0, 738, ['Azumarill: Ice Beam',
                 'Mimikyu (Busted): Play Rough',
                 'Mimikyu (Busted): Shadow Sneak']),
    (0, 1, 350, ['Azumarill: Ice Beam',
                 'Mimikyu (Busted): Shadow Sneak (shielded)',
                 'Mimikyu (Busted): Shadow Sneak',
                 'Azumarill: Ice Beam']),
    (0, 2, 214, ['Azumarill: Ice Beam',
                 'Mimikyu (Busted): Shadow Sneak (shielded)',
                 'Mimikyu (Busted): Play Rough (shielded)',
                 'Azumarill: Ice Beam']),
    (1, 0, 761, ['Mimikyu: Play Rough',
                 'Azumarill: Ice Beam (shielded)',
                 'Mimikyu: Shadow Sneak']),
    (1, 1, 672, ['Mimikyu: Shadow Sneak (shielded)',
                 'Azumarill: Ice Beam (shielded)',
                 'Mimikyu: Shadow Sneak',
                 'Azumarill: Ice Beam',
                 'Mimikyu (Busted): Shadow Sneak']),
    (1, 2, 473, ['Mimikyu: Shadow Sneak (shielded)',
                 'Azumarill: Ice Beam (shielded)',
                 'Azumarill: Ice Beam',
                 'Mimikyu (Busted): Shadow Sneak (shielded)',
                 'Mimikyu (Busted): Play Rough',
                 'Azumarill: Ice Beam']),
    (2, 0, 761, ['Mimikyu: Play Rough',
                 'Azumarill: Ice Beam (shielded)',
                 'Mimikyu: Shadow Sneak']),
    (2, 1, 686, ['Mimikyu: Shadow Sneak (shielded)',
                 'Azumarill: Ice Beam (shielded)',
                 'Mimikyu: Shadow Sneak',
                 'Azumarill: Play Rough (shielded)',
                 'Mimikyu: Shadow Sneak']),
    (2, 2, 607, ['Mimikyu: Shadow Sneak (shielded)',
                 'Azumarill: Ice Beam (shielded)',
                 'Mimikyu: Shadow Sneak (shielded)',
                 'Azumarill: Ice Beam (shielded)',
                 'Mimikyu: Play Rough',
                 'Azumarill: Ice Beam']),
])
def test_mimikyu_vs_azumarill_form_change(shields_m, shields_a,
                                          expected_mimikyu_score, expected_log):
    """Mimikyu disguise: first unshielded charged hit absorbed, then -1 def stage.

    Assertion checks both PvPoke score AND chargedLog. chargedLog is
    diagnostic: it reveals the actual SS-delay / Azu-IB-timing
    divergences, whereas scores can coincidentally align even when the
    fights play out differently (as they do in the score-match / log-mismatch
    xfail cases below).
    """
    bp_m = _make_battle_pokemon(
        'Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'],
        'great', shields_m, 5, 13, 15,
    )
    bp_a = _make_battle_pokemon(
        'Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
        'great', shields_a, 4, 15, 13,
    )
    result = simulate(bp_m, bp_a,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    score = round(result.pvpoke_score(0))
    assert score == expected_mimikyu_score, (
        f"{shields_m}v{shields_a}: expected Mimikyu score={expected_mimikyu_score}, "
        f"got {score} (delta={score - expected_mimikyu_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_m}v{shields_a}: chargedLog mismatch vs PvPoke harness"
    )


# ---------------------------------------------------------------------------
# UL Moltres-G near-KO DP plan-choice divergence (intentional, mostly)
# ---------------------------------------------------------------------------
# Captured 2026-04-15. PvPoke's near-KO DP returns the slow multi-Fly plan
# for Moltres-G vs Water-defender cases; ours returns the fast single-
# BraveBird-nuke plan. In 6 of 7 cases (Jellicent/Corviknight clear wins)
# ours retains 23-30pp more attacker HP and KOs 6-12 turns earlier with
# the same winner — we keep our behavior.
#
# CAVEAT: 1 of 7 cases (Lapras [1,2]) is a winner-flip edge case. In that
# close fight PvPoke's slower plan wins (MG 608) while ours loses (MG
# 497, by a 1-HP margin). This is real evidence that PvPoke's plan is
# better for close/bulky fights. The overall decision to keep our plan
# rests on the 6:1 weight of clear-win cases; revisit if the flip
# frequency grows (e.g. if wider harness sampling adds more bulky
# opponents).
#
# Per CLAUDE.md "When our sim diverges from PvPoke" policy: we document
# and xfail; XPASS on any of these alerts us to re-evaluate.
_MG_NEARKO_PLAN = pytest.mark.xfail(
    strict=True,   # XPASS must be loud: the divergence pin vanished — re-vet
    reason=(
        "Intentional divergence: our near-KO DP returns [Brave Bird] (fast "
        "self-debuffing nuke); PvPoke returns [Fly, Fly, ...] (slow non-"
        "debuffing serial). In 6 of 7 UL cases ours retains 23-30pp more "
        "MG HP with same winner; 1 case (Lapras [1,2]) is a 1-HP winner "
        "flip where PvPoke's slower plan is correct. See DEVELOPER_NOTES "
        "'Known divergences: Near-KO DP plan choice'."))
_MG_NEARKO_PLAN_FLIP = pytest.mark.xfail(
    strict=True,   # XPASS must be loud: the winner flip resolved — re-vet
    reason=(
        "Same root cause as _MG_NEARKO_PLAN but this case is a WINNER "
        "FLIP: PvPoke's Fly-Fly-Fly plan correctly predicts MG wins "
        "(608), ours' BB-nuke predicts Lapras barely wins (497, 1-HP "
        "margin). PvPoke is demonstrably better HERE. Kept as a cluster "
        "xfail because the overall decision favors our plan across the "
        "6:1 majority of cluster cases; this flip is the cost we pay."))


@pytest.mark.integration
@pytest.mark.parametrize("opp_species,opp_fast,opp_charged,opp_ivs,opp_level,"
                         "shields_opp,shields_mg,expected_mg_score", [
    # Ultra League rank-1 IVs; PvPoke harness ground truth captured
    # 2026-04-15 from scripts/pvpoke_trace.js. In clear-win cases MG
    # wins in both sims; the xfail pins the score margin (loser HP
    # carry-over) where our retained HP diverges from PvPoke's.
    pytest.param('Jellicent', 'HEX', ['SURF','SHADOW_BALL'], (6,14,15), 50.0,
                 0, 0, 639, marks=_MG_NEARKO_PLAN),
    pytest.param('Jellicent', 'HEX', ['SURF','SHADOW_BALL'], (6,14,15), 50.0,
                 0, 1, 779, marks=_MG_NEARKO_PLAN),
    pytest.param('Jellicent', 'HEX', ['SURF','SHADOW_BALL'], (6,14,15), 50.0,
                 0, 2, 779, marks=_MG_NEARKO_PLAN),
    pytest.param('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER','PAYBACK'],
                 (0,15,15), 48.5, 0, 0, 521, marks=_MG_NEARKO_PLAN),
    pytest.param('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER','PAYBACK'],
                 (0,15,15), 48.5, 0, 1, 602, marks=_MG_NEARKO_PLAN),
    pytest.param('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER','PAYBACK'],
                 (0,15,15), 48.5, 0, 2, 683, marks=_MG_NEARKO_PLAN),
    # Winner-flip edge case: PvPoke is correct here (MG wins 608), ours
    # loses by 1 HP (MG 497). Same root cause as the cluster.
    pytest.param('Lapras', 'PSYWAVE', ['SPARKLING_ARIA','ICE_BEAM'],
                 (0,15,15), 42.5, 1, 2, 608,
                 marks=_MG_NEARKO_PLAN_FLIP),
])
def test_moltres_g_nearKO_plan_divergence_pinned(
        opp_species, opp_fast, opp_charged, opp_ivs, opp_level,
        shields_opp, shields_mg, expected_mg_score):
    """Pin the UL Moltres-G near-KO DP plan-choice divergence.

    Asserts PvPoke harness score for MG. Currently xfails because our
    DP picks Brave Bird (faster KO, more HP retained in 6/7 cases; 1
    winner-flip edge case where PvPoke's plan is correct).
    """
    a, d, s = opp_ivs
    bp_opp = _make_battle_pokemon(
        opp_species, opp_fast, opp_charged,
        'ultra', shields_opp, a, d, s,
    )
    bp_mg = _make_battle_pokemon(
        'Moltres (Galarian)', 'SUCKER_PUNCH', ['FLY', 'BRAVE_BIRD'],
        'ultra', shields_mg, 1, 15, 15,
    )
    result = simulate(bp_opp, bp_mg,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp)
    mg_score = round(result.pvpoke_score(1))
    assert mg_score == expected_mg_score, (
        f"opp={opp_species} sh=[{shields_opp},{shields_mg}]: "
        f"expected MG score={expected_mg_score}, got {mg_score} "
        f"(delta={mg_score - expected_mg_score:+d})"
    )


# ---------------------------------------------------------------------------
# reset_for_battle: reuse across shield scenarios must match fresh objects
# ---------------------------------------------------------------------------

_REUSE_MATCHUPS = [
    # Buff/debuff-heavy mirror (Close Combat self-debuff -> stage changes,
    # so the damage/DP caches go through invalidation cycles mid-battle)
    pytest.param(
        ('Annihilape', 'COUNTER', ['RAGE_FIST', 'CLOSE_COMBAT'],
         'great', 0, 15, 15, False),
        ('Annihilape', 'COUNTER', ['RAGE_FIST', 'CLOSE_COMBAT'],
         'great', 15, 1, 5, False),
        id='annihilape-mirror'),
    # Zap Cannon priority-shuffle clause (mutates move dicts) + the
    # bandaid[866] _cached_damage path that reset must clear
    pytest.param(
        ('Swampert', 'MUD_SHOT', ['HYDRO_CANNON', 'EARTHQUAKE'],
         'great', 15, 15, 15, True),
        ('Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST'],
         'great', 15, 15, 15, False),
        id='swampert-registeel'),
    # Form change: reset must restore Shield form and invalidate the
    # opponent's caches too
    pytest.param(
        ('Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT',
         ['SHADOW_BALL', 'GYRO_BALL'], 'great', 4, 14, 15, False),
        ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
         'great', 4, 15, 13, False),
        id='aegislash-azumarill'),
]


@pytest.mark.parametrize("p0_spec, p1_spec", _REUSE_MATCHUPS)
def test_reset_for_battle_reuse_matches_fresh(p0_spec, p1_spec):
    """Reusing one BattlePokemon pair across all 9 shield scenarios via
    reset_for_battle must be battle-for-battle identical to constructing
    fresh objects per scenario (the sweep/slayer workers rely on this).
    Timelines are compared too, so any state leak that changes a single
    move or damage value fails loudly.
    """
    all_nine = [(a, b) for a in range(3) for b in range(3)]

    def build(spec, shields):
        sp, fast, charged, league, a, d, s, shadow = spec
        return _make_battle_pokemon(sp, fast, charged, league, shields,
                                    a, d, s, shadow=shadow)

    fresh = []
    for s0, s1 in all_nine:
        r = simulate(build(p0_spec, s0), build(p1_spec, s1),
                     charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp,
                     log=True)
        fresh.append(r)

    bp0 = build(p0_spec, 0)
    bp1 = build(p1_spec, 0)
    for (s0, s1), expected in zip(all_nine, fresh):
        bp0.reset_for_battle(s0, opponent=bp1)
        bp1.reset_for_battle(s1, opponent=bp0)
        got = simulate(bp0, bp1,
                       charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp,
                       log=True)
        assert (got.winner, got.turns, got.hp_remaining,
                got.energy_remaining, got.shields_remaining,
                got.timeline) == (
            expected.winner, expected.turns, expected.hp_remaining,
            expected.energy_remaining, expected.shields_remaining,
            expected.timeline), f"{s0}v{s1}: reuse diverged from fresh"


# ---------------------------------------------------------------------------
# JIT ↔ pure-Python DP parity
# ---------------------------------------------------------------------------

_JIT_PARITY_MATCHUPS = [
    pytest.param(('Medicham', 'PSYCHO_CUT', ['DYNAMIC_PUNCH', 'PSYCHIC'], (5, 15, 15), False,
                  'Azumarill', 'BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], (8, 15, 15), False),
                 id='medicham-azumarill'),
    pytest.param(('Swampert', 'MUD_SHOT', ['HYDRO_CANNON', 'EARTHQUAKE'], (15, 15, 15), True,
                  'Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST'], (15, 15, 15), False),
                 id='shadow-swampert-registeel'),
    pytest.param(('Obstagoon', 'COUNTER', ['OBSTRUCT', 'NIGHT_SLASH'], (5, 15, 12), False,
                  'Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), False),
                 id='obstagoon-azumarill'),
]


@pytest.mark.integration
@pytest.mark.parametrize("spec", _JIT_PARITY_MATCHUPS)
@pytest.mark.parametrize("shields", [(1, 1), (2, 2)])
def test_jit_and_python_dp_paths_agree(monkeypatch, spec, shields):
    """The numba kernels (_near_ko_dp_jit / _calc_ttl_jit) and the pure-
    Python fallbacks in battle.py are hand-mirrored implementations with no
    other automated parity check: the full suite only ever exercises
    whichever path the running machine takes. Run the same battle with the
    kernels enabled and forcibly disabled and require identical outcomes.
    (On a machine without numba both runs take the Python path and this
    pins nothing — acceptable; dev machines install [perf].)
    """
    import gopvpsim.battle as B

    def run():
        sp0, f0, c0, iv0, sh0, sp1, f1, c1, iv1, sh1 = spec
        bp0 = _make_battle_pokemon(sp0, f0, c0, 'great', shields[0], *iv0, shadow=sh0)
        bp1 = _make_battle_pokemon(sp1, f1, c1, 'great', shields[1], *iv1, shadow=sh1)
        result = simulate(bp0, bp1,
                          charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp,
                          shield_policy_0=pvpoke_simulate_shield,
                          shield_policy_1=pvpoke_simulate_shield,
                          log=True)
        return (round(result.pvpoke_score(0)), result.winner,
                result.hp_remaining, _extract_battle_log(result))

    jit_outcome = run()
    monkeypatch.setattr(B, '_NEAR_KO_DP_JIT', None)
    monkeypatch.setattr(B, '_CALC_TTL_JIT', None)
    py_outcome = run()
    assert py_outcome == jit_outcome, (
        f"JIT and pure-Python DP paths disagree at {shields}: "
        f"jit={jit_outcome} py={py_outcome}"
    )


# ---------------------------------------------------------------------------
# Defender-bestCM selfDefenseDebuffing shield gate (Battle.js:1105-1124 port)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("shields_mg,shields_flo,expected_winner,expected_mg_score,expected_log", [
    # Moltres (Galarian) 4/11/11 L29.5 (SUCKER_PUNCH / FLY + BRAVE_BIRD)
    # vs Florges 4/13/15 L28.5 (FAIRY_WIND / CHILLING_WATER + DISARMING_VOICE),
    # Ultra League. Fixture generated 2026-06-11 from scripts/pvpoke_trace.js
    # (all six moves + both baseStats verified identical between the clone
    # and the live gamemaster).
    #
    # This is the PASSING pin for the defender-bestCM-selfDefenseDebuffing
    # shield gate (ported 2026-04-15, commit 359e693): MG's bestChargedMove
    # is Brave Bird ([0,-3] self-def-debuff), so every cell where MG holds
    # shields routes Florges' incoming charged moves through wouldShield
    # instead of always-shield. Until now the only tests through that path
    # were the MG near-KO xfails, where a gate regression would stay
    # invisible (a different wrong score still XFAILs). The Florges matchup
    # has no near-KO-plan divergence, so these cells pin the gate green.
    (0, 0, 1, 318, ["Florges: Disarming Voice", "Moltres (Galarian): Fly", "Florges: Chilling Water"]),
    (0, 1, 1, 143, ["Florges: Disarming Voice", "Moltres (Galarian): Fly (shielded)", "Florges: Chilling Water"]),
    (0, 2, 1, 143, ["Florges: Disarming Voice", "Moltres (Galarian): Fly (shielded)", "Florges: Chilling Water"]),
    (1, 0, 0, 563, ["Florges: Disarming Voice (shielded)", "Moltres (Galarian): Fly", "Florges: Disarming Voice", "Moltres (Galarian): Fly"]),
    (1, 1, 1, 339, ["Florges: Disarming Voice", "Moltres (Galarian): Fly (shielded)", "Florges: Chilling Water (shielded)", "Moltres (Galarian): Fly", "Florges: Chilling Water"]),
    # [1,2]: score/winner/HP match PvPoke exactly (199, Florges wins, 0/86);
    # the only difference is which move MG throws into Florges' SECOND
    # shield — ours Fly (45e), PvPoke Brave Bird (55e). Both are shielded
    # for 1 damage and MG dies before throwing again, so the divergence is
    # cosmetic; per the CLAUDE.md divergence policy we pin OUR log. Open
    # lead for the engine-fidelity round: shielded-throw move choice
    # (review findings E5/E15 family).
    (1, 2, 1, 199, ["Florges: Disarming Voice", "Moltres (Galarian): Fly (shielded)", "Florges: Chilling Water (shielded)", "Moltres (Galarian): Fly (shielded)", "Florges: Chilling Water"]),
    (2, 0, 0, 772, ["Florges: Chilling Water (shielded)", "Moltres (Galarian): Fly", "Florges: Chilling Water (shielded)", "Moltres (Galarian): Brave Bird"]),
    (2, 1, 1, 318, ["Florges: Chilling Water (shielded)", "Moltres (Galarian): Fly (shielded)", "Florges: Chilling Water (shielded)", "Moltres (Galarian): Fly", "Florges: Disarming Voice"]),
    (2, 2, 1, 202, ["Florges: Chilling Water (shielded)", "Moltres (Galarian): Fly (shielded)", "Florges: Chilling Water (shielded)", "Moltres (Galarian): Fly (shielded)", "Florges: Disarming Voice"]),
])
def test_moltres_galarian_vs_florges_shield_gate(shields_mg, shields_flo, expected_winner,
                                                 expected_mg_score, expected_log):
    bp_mg = _make_battle_pokemon('Moltres (Galarian)', 'SUCKER_PUNCH', ['FLY', 'BRAVE_BIRD'],
                                 'ultra', shields_mg, 4, 11, 11)
    bp_flo = _make_battle_pokemon('Florges', 'FAIRY_WIND', ['CHILLING_WATER', 'DISARMING_VOICE'],
                                  'ultra', shields_flo, 4, 13, 15)
    result = simulate(bp_mg, bp_flo,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      shield_policy_0=pvpoke_simulate_shield,
                      shield_policy_1=pvpoke_simulate_shield,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_mg}v{shields_flo}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    mg_score = round(result.pvpoke_score(0))
    assert mg_score == expected_mg_score, (
        f"{shields_mg}v{shields_flo}: expected MG score={expected_mg_score}, "
        f"got {mg_score}  (delta={mg_score - expected_mg_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_mg}v{shields_flo}: battle log mismatch"
    )


# ---------------------------------------------------------------------------
# Deterministic buff-meter proc schedule (PvPoke accumulator port)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("chance,expected_procs", [
    # PvPoke Battle.js:1389-1397 + Pokemon.js:686-706: float accumulator
    # initialized to the chance (0.0 for exactly 0.5), += chance per use,
    # fires on whole-number crossings, never reset. Schedules below are
    # the bit-exact IEEE-754 outcomes (note 0.3's gap pattern 3,6,10 and
    # 0.1 proc'ing on use 10 only via float drift).
    (0.5, [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]),
    (0.3, [3, 6, 10, 13, 16, 20]),
    (0.2, [4, 10, 14, 19]),
    (0.125, [7, 15]),
    (0.1, [10, 19]),
    (1.0, list(range(1, 21))),
])
def test_buff_meter_proc_schedule(chance, expected_procs):
    from gopvpsim.battle import _apply_move_buffs
    move = {'moveId': 'FAKE_CHANCE_BUFF', 'power': 50, 'energy': 40,
            'energyGain': 0, 'type': 'normal',
            'buffs': [0, -1], 'buffTarget': 'opponent',
            'buffApplyChance': str(chance)}
    attacker = make_bp(charged=[move])
    defender = make_bp()
    procs = []
    for use in range(1, 21):
        defender.def_stage = 0
        _apply_move_buffs(attacker, defender, move)
        if defender.def_stage != 0:
            procs.append(use)
    assert procs == expected_procs


# ---------------------------------------------------------------------------
# wouldShield selfAttackDebuffing final-override clause (ActionLogic.js:1186)
# ---------------------------------------------------------------------------

def test_would_shield_self_attack_debuff_override():
    """PvPoke's final wouldShield clause: 'Shield the first in a series of
    Attack debuffing moves like Superpower' — selfAttackDebuffing AND
    damage/hp > 0.55 forces a shield even when every other clause says no.
    The numbers below sit in the window where no other clause fires
    (damage 67 vs hp 120: 0.558 > 0.55, but < hp/1.4 and < hp - cycle),
    so the flag alone flips the decision.
    """
    def make_superpower(atk_debuff: bool):
        return {'moveId': 'FAKE_SUPERPOWER', 'name': 'Fake Superpower',
                'type': 'normal', 'power': 85, 'energy': 40, 'energyGain': 0,
                'buffs': [-1, -1], 'buffTarget': 'self',
                'buffApplyChance': '1', 'selfDebuffing': True,
                'selfAttackDebuffing': atk_debuff,
                'selfDefenseDebuffing': True}

    from gopvpsim.battle import would_shield
    move_on = make_superpower(True)
    att_on = make_bp(charged=[move_on])
    assert would_shield(att_on, make_bp(hp=120, shields=1), move_on) is True

    move_off = make_superpower(False)
    att_off = make_bp(charged=[move_off])
    assert would_shield(att_off, make_bp(hp=120, shields=1), move_off) is False


# ---------------------------------------------------------------------------
# Early lethal-throw slot gate (ActionLogic.js:221)
# ---------------------------------------------------------------------------

def test_lethal_throw_slot1_gated_on_bait_shields():
    """PvPoke's pre-OMT lethal throw checks `n == 0 || (n == 1 &&
    !poke.baitShields)`: with baiting ON, slot 1 (the pricier move after
    the energy sort) is NOT eligible for the early lethal fire — the
    decision falls through to OMT / the DP. Pinned via the DP[lethal]
    debug log, since downstream logic may converge to the same move.
    """
    import gopvpsim.battle as B

    def build():
        cheap = {'moveId': 'WEAK_CHEAP', 'name': 'Weak Cheap', 'type': 'normal',
                 'power': 30, 'energy': 35, 'energyGain': 0}
        strong = {'moveId': 'STRONG_PRICY', 'name': 'Strong Pricy', 'type': 'normal',
                  'power': 80, 'energy': 45, 'energyGain': 0}
        att = make_bp(charged=[cheap, strong])
        att.energy = 50
        dfn = make_bp(hp=50, shields=0)
        return att, dfn

    orig_debug = B._policy_debug
    B._policy_debug = True
    try:
        B._policy_log.clear()
        att, dfn = build()
        idx_nobait = B.pvpoke_dp(att, dfn, bait_shields=False)
        log_nobait = list(B._policy_log)

        B._policy_log.clear()
        att, dfn = build()
        B.pvpoke_dp(att, dfn, bait_shields=True)
        log_bait = list(B._policy_log)
    finally:
        B._policy_debug = orig_debug
        B._policy_log.clear()

    # bait OFF: slot 1 is eligible — the strong move fires via the early
    # lethal path (it KOs hp=50; the cheap one doesn't).
    assert idx_nobait is not None
    assert att.charged_moves[idx_nobait]['moveId'] == 'STRONG_PRICY'
    assert any('DP[lethal]' in line for line in log_nobait)
    # bait ON: slot 1 is NOT eligible — no early lethal fire.
    assert not any('DP[lethal]' in line for line in log_bait)
