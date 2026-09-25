"""
Tests for gopvpsim.battle — simulation loop, policies, BattlePokemon.

Unit tests use hardcoded move/pokemon dicts (no network).
Integration tests (marked 'integration') validate against known PvPoke results.
Run integration tests with: pytest -m integration
"""
import pytest
from gopvpsim.battle import (
    BattlePokemon, BattleResult, is_win,
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
            fast=None, charged=None, shields=2, shadow=False):
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
        shadow        = shadow,
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

def test_cmp_atk_strips_shadow_bonus():
    """CMP / charge-move priority uses the *unboosted* attack. Shadow's
    x1.2 boost damage (.atk) but not priority (.cmp_atk) - live-game
    behavior, matching PvPoke's shadow-free stats.atk."""
    # Non-shadow: cmp_atk is just atk
    base = make_bp(atk=120.0)
    assert base.shadow is False
    assert base.cmp_atk == base.atk

    # Shadow x1.2 stripped for priority, kept in .atk for damage
    shadow = make_bp(atk=144.0, shadow=True) # 144 == 120 * 1.2
    assert shadow.atk == 144.0
    assert shadow.cmp_atk == pytest.approx(120.0)
    assert shadow.cmp_atk < shadow.atk

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

# ---------------------------------------------------------------------------
# Regression: an exact-500 rating is ALWAYS a double-KO tie, never a win/loss.
# Pins the invariant the ML-guide "tie 500" / per-Case "tie" labeling rests on.
# (A 2026-06 fix mislabeled 500 as a loss by conflating it with the
# hundo-relative `drops` set; the root truth is the rating math exercised here.)
# ---------------------------------------------------------------------------

def _score_result(hp_remaining, max_hp, winner):
    """Minimal BattleResult for exercising pvpoke_score's rating math directly."""
    return BattleResult(
        winner=winner, turns=10,
        hp_remaining=hp_remaining, max_hp=max_hp,
        energy_remaining=[0, 0], shields_remaining=[0, 0],
    )

def test_rating_500_is_a_tie_not_a_win():
    """is_win() must reject exactly 500: a 500 rating is a TIE, not a win."""
    assert is_win(501) is True
    assert is_win(500) is False
    assert is_win(499) is False

def test_double_ko_scores_exactly_500_for_both():
    """A double KO (both faint the same turn) is the only end-state that yields
    a 500 rating -- and it yields it for BOTH players, i.e. a genuine tie."""
    r = _score_result(hp_remaining=[0, 0], max_hp=[130, 140], winner=None)
    assert r.pvpoke_score(0) == 500
    assert r.pvpoke_score(1) == 500
    assert not is_win(r.pvpoke_score(0))

def test_live_winner_never_scores_exactly_500():
    """No reachable timeout (MAX_TURNS is an infinite-loop guard), so a winner is
    always alive while the loser has fainted. A live winner with even 1 HP
    scores strictly > 500 for any realistic max_hp (no PvP mon exceeds ~500 HP),
    and a dead loser scores < 500 -- so an exact-500 "thin win" cannot occur
    in-sim: 500 is unambiguously a double-KO tie."""
    for max_hp in (60, 130, 250, 500):   # 500 is above any real PvP HP stat
        win = _score_result(hp_remaining=[1, 0], max_hp=[max_hp, 140], winner=0)
        assert win.pvpoke_score(0) > 500, f"1-HP win at max_hp={max_hp} must be > 500"
        assert is_win(win.pvpoke_score(0))
        loss = _score_result(hp_remaining=[0, 1], max_hp=[max_hp, 140], winner=1)
        assert loss.pvpoke_score(0) < 500
        assert not is_win(loss.pvpoke_score(0))

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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(1).
    (0, 0, 1, 616, ['Medicham: Psychic', 'Azumarill: Hydro Pump', 'Medicham: Psychic', 'Azumarill: Ice Beam']),
    (0, 1, 1, 738, ['Medicham: Psychic (shielded)', 'Azumarill: Hydro Pump', 'Medicham: Psychic', 'Azumarill: Ice Beam']),
    (0, 2, 1, 859, ['Medicham: Psychic (shielded)', 'Azumarill: Hydro Pump', 'Medicham: Psychic (shielded)', 'Azumarill: Ice Beam']),
    (1, 0, 0, 457, ['Medicham: Psychic', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Hydro Pump', 'Medicham: Psychic']),
    (1, 1, 1, 603, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Hydro Pump', 'Medicham: Dynamic Punch']),
    (1, 2, 1, 724, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic (shielded)', 'Azumarill: Hydro Pump', 'Medicham: Dynamic Punch']),
    (2, 0, 0, 218, ['Medicham: Psychic', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Hydro Pump (shielded)', 'Medicham: Psychic']),
    (2, 1, 0, 411, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Ice Beam (shielded)', 'Medicham: Dynamic Punch', 'Azumarill: Ice Beam', 'Medicham: Dynamic Punch']),
    (2, 2, 1, 613, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Dynamic Punch', 'Medicham: Dynamic Punch', 'Azumarill: Hydro Pump']),
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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    (0, 0, 0, 526, ['Forretress: Sand Tomb', 'Azumarill: Hydro Pump', 'Forretress: Sand Tomb', 'Azumarill: Ice Beam']),
    (0, 1, 1, 496, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb', 'Azumarill: Hydro Pump']),
    (0, 2, 1, 242, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb', 'Azumarill: Hydro Pump (shielded)']),
    (1, 0, 0, 636, ['Forretress: Sand Tomb', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Ice Beam']),
    (1, 1, 1, 429, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Sand Tomb']),
    (1, 2, 1, 226, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Sand Tomb']),
    (2, 0, 0, 696, ['Forretress: Sand Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Sand Tomb (shielded)', 'Azumarill: Ice Beam']),
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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    (0, 0, 1, 476, ['Forretress: Rock Tomb', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam']),
    (0, 1, 1, 273, ['Forretress: Rock Tomb', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam']),
    (0, 2, 1, 214, ['Forretress: Rock Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Hydro Pump (shielded)']),
    (1, 0, 1, 476, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam', 'Forretress: Rock Tomb']),
    (1, 1, 1, 273, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam', 'Forretress: Rock Tomb']),
    (1, 2, 1, 214, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb']),
    (2, 0, 0, 575, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Hydro Pump']),
    (2, 1, 1, 441, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb']),
    (2, 2, 1, 316, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam']),
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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    (0, 0, 1, 235, ['Obstagoon: Obstruct', 'Azumarill: Play Rough', 'Obstagoon: Night Slash', 'Azumarill: Ice Beam']),
    (0, 1, 1, 170, ['Obstagoon: Obstruct', 'Azumarill: Play Rough', 'Obstagoon: Night Slash (shielded)', 'Azumarill: Ice Beam']),
    (0, 2, 1, 170, ['Obstagoon: Obstruct', 'Azumarill: Play Rough', 'Obstagoon: Night Slash (shielded)', 'Azumarill: Ice Beam']),
    (1, 0, 1, 361, ['Obstagoon: Obstruct', 'Azumarill: Play Rough (shielded)', 'Obstagoon: Obstruct', 'Azumarill: Play Rough', 'Obstagoon: Night Slash', 'Azumarill: Ice Beam']),
    (1, 1, 1, 282, ['Obstagoon: Obstruct', 'Azumarill: Play Rough (shielded)', 'Obstagoon: Obstruct', 'Azumarill: Play Rough', 'Obstagoon: Night Slash (shielded)', 'Azumarill: Ice Beam']),
    (1, 2, 1, 282, ['Obstagoon: Obstruct', 'Azumarill: Play Rough (shielded)', 'Obstagoon: Obstruct', 'Azumarill: Play Rough', 'Obstagoon: Night Slash (shielded)', 'Azumarill: Ice Beam']),
    (2, 0, None, 500, ['Obstagoon: Obstruct', 'Azumarill: Ice Beam (shielded)', 'Obstagoon: Obstruct', 'Azumarill: Play Rough (shielded)', 'Obstagoon: Night Slash', 'Azumarill: Play Rough', 'Obstagoon: Night Slash']),
    (2, 1, 1, 429, ['Obstagoon: Obstruct', 'Azumarill: Ice Beam (shielded)', 'Obstagoon: Obstruct', 'Azumarill: Play Rough (shielded)', 'Obstagoon: Night Slash (shielded)', 'Azumarill: Play Rough', 'Obstagoon: Night Slash']),
    (2, 2, 1, 350, ['Obstagoon: Obstruct', 'Azumarill: Ice Beam (shielded)', 'Obstagoon: Obstruct', 'Azumarill: Play Rough (shielded)', 'Obstagoon: Night Slash (shielded)', 'Azumarill: Play Rough', 'Obstagoon: Night Slash (shielded)']),
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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    (0, 0, 0, 546, ['Corviknight: Air Cutter', 'Medicham: Dynamic Punch', 'Corviknight: Air Cutter']),
    (0, 1, 1, 496, ['Corviknight: Air Cutter (shielded)', 'Medicham: Dynamic Punch', 'Corviknight: Air Cutter', 'Medicham: Dynamic Punch']),
    (0, 2, 1, 294, ['Corviknight: Air Cutter (shielded)', 'Medicham: Dynamic Punch', 'Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch']),
    (1, 0, 0, 736, ['Corviknight: Air Cutter', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter']),
    (1, 1, 0, 610, ['Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter', 'Medicham: Ice Punch']),
    (1, 2, 1, 326, ['Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter (shielded)', 'Medicham: Dynamic Punch']),
    (2, 0, 0, 736, ['Corviknight: Air Cutter', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter']),
    (2, 1, 0, 713, ['Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter', 'Medicham: Ice Punch (shielded)']),
    (2, 2, 1, 421, ['Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch (shielded)', 'Corviknight: Air Cutter (shielded)', 'Medicham: Ice Punch (shielded)', 'Medicham: Ice Punch']),
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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    (0, 0, 1, 269, ['Mienfoo: High Jump Kick', 'Medicham: Dynamic Punch']),
    (0, 1, 1, 78, ['Mienfoo: High Jump Kick (shielded)', 'Medicham: Dynamic Punch']),
    (0, 2, 1, 78, ['Mienfoo: Low Sweep (shielded)', 'Medicham: Dynamic Punch']),
    (1, 0, 0, 521, ['Mienfoo: High Jump Kick', 'Medicham: Ice Punch (shielded)', 'Mienfoo: High Jump Kick']),
    (1, 1, 1, 347, ['Mienfoo: High Jump Kick (shielded)', 'Medicham: Ice Punch (shielded)', 'Mienfoo: High Jump Kick', 'Medicham: Ice Punch']),
    (1, 2, 1, 145, ['Mienfoo: Low Sweep (shielded)', 'Medicham: Ice Punch (shielded)', 'Mienfoo: Low Sweep (shielded)', 'Medicham: Ice Punch']),
    (2, 0, 1, 414, ['Mienfoo: High Jump Kick', 'Mienfoo: Low Sweep', 'Medicham: Dynamic Punch (shielded)']),
    (2, 1, 1, 212, ['Mienfoo: High Jump Kick (shielded)', 'Mienfoo: Low Sweep']),
    (2, 2, 1, 145, ['Mienfoo: Low Sweep (shielded)', 'Mienfoo: Low Sweep (shielded)']),
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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    (0, 0, 1, 418, ['Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam']),
    (0, 1, 1, 321, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam']),
    (0, 2, 1, 225, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam']),
    (1, 0, 0, 623, ['Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
    (1, 1, 1, 421, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam']),
    (1, 2, 1, 324, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam']),
    (2, 0, 0, 760, ['Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter']),
    (2, 1, 0, 553, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
    (2, 2, 0, 520, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
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
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    (0, 0, 0, 723, ['Registeel: Flash Cannon', 'Swampert: Earthquake']),
    (0, 1, 0, 690, ['Registeel: Flash Cannon', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Earthquake']),
    (0, 2, 1, 200, ['Registeel: Flash Cannon', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Registeel: Flash Cannon']),
    (1, 0, 0, 940, ['Registeel: Focus Blast (shielded)', 'Swampert: Earthquake']),
    (1, 1, 0, 906, ['Registeel: Flash Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Earthquake']),
    (1, 2, 1, 216, ['Registeel: Flash Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Registeel: Focus Blast']),
    (2, 0, 0, 940, ['Registeel: Focus Blast (shielded)', 'Swampert: Earthquake']),
    (2, 1, 0, 906, ['Registeel: Flash Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Earthquake']),
    (2, 2, 0, 865, ['Registeel: Flash Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Swampert: Hydro Cannon (shielded)', 'Registeel: Flash Cannon (shielded)', 'Swampert: Earthquake']),
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
@pytest.mark.parametrize("shields_quag,shields_fera,expected_winner,expected_quag_score,expected_log", [
    # Quagsire (Shadow) MUD_SHOT / [AQUA_TAIL, MUD_BOMB] 4/15/10
    # vs Feraligatr SHADOW_CLAW / [HYDRO_CANNON, ICE_BEAM] 5/11/14, Great League
    # Policy: pvpoke_dp. CMP is decided on the SHADOW-FREE attack: shadow
    # Quagsire's cmp_atk is 108.4 (= 130.1 / 1.2), so it does NOT win the
    # priority race its boosted .atk would imply. Pre-fix (boosted CMP) the
    # [0,0] cell wrongly had Quagsire win 555/444; PvPoke (and now we) give
    # it to Feraligatr 464/536. PvPoke-verified via pvpoke_trace.js.
    (0, 0, 1, 464, ['Feraligatr: Hydro Cannon', 'Quagsire: Mud Bomb', 'Quagsire: Aqua Tail', 'Feraligatr: Hydro Cannon']),
    (0, 1, 1, 344, ['Feraligatr: Hydro Cannon', 'Quagsire: Aqua Tail (shielded)', 'Quagsire: Mud Bomb', 'Feraligatr: Hydro Cannon']),
    (0, 2, 1, 116, ['Feraligatr: Hydro Cannon', 'Quagsire: Aqua Tail (shielded)', 'Quagsire: Mud Bomb (shielded)', 'Feraligatr: Hydro Cannon']),
    (1, 0, 0, 552, ['Feraligatr: Hydro Cannon (shielded)', 'Quagsire: Mud Bomb', 'Feraligatr: Hydro Cannon', 'Quagsire: Mud Bomb']),
    (1, 1, 1, 392, ['Feraligatr: Hydro Cannon (shielded)', 'Quagsire: Aqua Tail (shielded)', 'Quagsire: Mud Bomb', 'Feraligatr: Hydro Cannon']),
    (1, 2, 1, 276, ['Feraligatr: Hydro Cannon (shielded)', 'Quagsire: Aqua Tail (shielded)', 'Quagsire: Aqua Tail (shielded)', 'Feraligatr: Hydro Cannon', 'Quagsire: Aqua Tail']),
    (2, 0, 0, 807, ['Feraligatr: Hydro Cannon (shielded)', 'Quagsire: Mud Bomb', 'Feraligatr: Hydro Cannon (shielded)', 'Quagsire: Mud Bomb']),
    (2, 1, 0, 751, ['Feraligatr: Hydro Cannon (shielded)', 'Quagsire: Aqua Tail (shielded)', 'Quagsire: Mud Bomb', 'Feraligatr: Hydro Cannon (shielded)', 'Quagsire: Aqua Tail']),
    (2, 2, 1, 408, ['Feraligatr: Hydro Cannon (shielded)', 'Quagsire: Aqua Tail (shielded)', 'Quagsire: Aqua Tail (shielded)', 'Feraligatr: Hydro Cannon (shielded)', 'Quagsire: Mud Bomb', 'Feraligatr: Hydro Cannon']),
])
def test_shadow_quagsire_vs_feraligatr_cmp(shields_quag, shields_fera,
                                           expected_winner, expected_quag_score,
                                           expected_log):
    bp_quag = _make_battle_pokemon('Quagsire', 'MUD_SHOT', ['AQUA_TAIL', 'MUD_BOMB'],
                                   'great', shields_quag, 4, 15, 10, shadow=True)
    bp_fera = _make_battle_pokemon('Feraligatr', 'SHADOW_CLAW', ['HYDRO_CANNON', 'ICE_BEAM'],
                                   'great', shields_fera, 5, 11, 14)
    result = simulate(bp_quag, bp_fera,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      log=True)
    assert result.winner == expected_winner, (
        f"{shields_quag}v{shields_fera}: expected winner={expected_winner}, "
        f"got {result.winner}  HP={result.hp_remaining}"
    )
    quag_score = round(result.pvpoke_score(0))
    assert quag_score == expected_quag_score, (
        f"{shields_quag}v{shields_fera}: expected Quag score={expected_quag_score}, "
        f"got {quag_score}  (delta={quag_score - expected_quag_score:+d})"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_quag}v{shields_fera}: battle log mismatch"
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_0,shields_1,expected_winner,expected_score_0,expected_log", [
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    (0, 0, None, 500, ['Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (0, 1, 1, 483, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (0, 2, 1, 406, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (1, 0, 0, 516, ['Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (1, 1, None, 500, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (1, 2, 1, 433, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (2, 0, 0, 593, ['Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
    (2, 1, 0, 566, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter']),
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


def _tinkaton_vs_rank1_shadow_altaria(tink_ivs, bait_shields):
    """Tinkaton (0 shields) vs rank #1 Shadow Altaria (1 shield).

    "The 0-1s" in the reference's shield vocabulary is focal-first,
    opponent-second (docs/concepts.md), so Tinkaton runs 0 shields and
    Altaria 1.  Both sides use PvPoke's default Great League movesets
    via ``get_default_moveset`` (never hardcode move ids -- CLAUDE.md
    "Testing"); rank #1 is the top stat-product spread from
    ``iv_rank(shadow=True)``, which is 0/14/15 @ level 29.
    """
    from functools import partial
    from gopvpsim.pokemon import iv_rank

    tink_fast, tink_charged = get_default_moveset('Tinkaton', 'great')
    alt_fast, alt_charged = get_default_moveset('Altaria', 'great', shadow=True)
    r1 = iv_rank('Altaria', league='great', shadow=True)[0]

    bp_tink = _make_battle_pokemon(
        'Tinkaton', tink_fast, tink_charged, 'great', shields=0,
        atk_iv=tink_ivs[0], def_iv=tink_ivs[1], sta_iv=tink_ivs[2])
    bp_alt = _make_battle_pokemon(
        'Altaria', alt_fast, alt_charged, 'great', shields=1,
        atk_iv=r1['atk_iv'], def_iv=r1['def_iv'], sta_iv=r1['sta_iv'],
        max_level=r1['level'], shadow=True)

    pol = (pvpoke_dp if bait_shields
           else partial(pvpoke_dp, bait_shields=False))
    return simulate(bp_tink, bp_alt,
                    charged_policy_0=pol,
                    charged_policy_1=pvpoke_dp,
                    shield_policy_0=pvpoke_simulate_shield,
                    shield_policy_1=pvpoke_simulate_shield)


# (tink_ivs, def, hp, wins_without_baiting, why)
#
# Stats are asserted alongside the outcome so a CPM/gamemaster shift that
# moves a spread off its reference stat line fails loudly here instead of
# silently re-pointing the oracle at a different Pokemon.
TINKATON_VS_SHADOW_ALTARIA_0_1 = [
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    ((0, 14, 9), 143.04, 141, True, 'reference spread A: "143.04 defense with 141 hp"'),
    ((0, 15, 8), 143.73, 140, True, 'reference spread B: "143.72 defense with 140 hp" (we read 143.73)'),
    ((1, 14, 14), 141.66, 143, True, 'below the def line but +3 hp -- the def/hp trade still clears'),
    ((0, 14, 10), 141.66, 140, False, 'same def as the row above, 3 fewer hp'),
    ((0, 13, 10), 142.36, 141, True,
     'def short of the OLD 143.04 line but wins under the new turn system'),
    ((0, 10, 15), 138.96, 143, True,
     'max hp alone now clears it; under legacy it did not'),
]


@pytest.mark.integration
@pytest.mark.parametrize("tink_ivs,exp_def,exp_hp,wins,why",
                         TINKATON_VS_SHADOW_ALTARIA_0_1)
def test_tinkaton_0v1_vs_rank1_shadow_altaria_bulk_gate_no_bait(
        tink_ivs, exp_def, exp_hp, wins, why):
    """Oracle from `docs/tinkaton_deep_dive_reference.md:31`:

        "143.04 defense with 141 hp (or 143.72 defense with 140 hp)
         lets you win the 0-1s against the rank #1 shadow altaria
         without baiting"

    **Directional bulk-gate test, bait OFF.**  Both reference spreads
    win; three spreads short of the line lose.  Measured 2026-08-08
    (bait-off pvpoke scores): 0/14/9 -> 503, 0/15/8 -> 503,
    1/14/14 -> 506, 0/14/10 -> 269, 0/13/10 -> 251, 0/10/15 -> 251.

    Mechanism (from the logged timeline, so this is a checked claim and
    not a restatement of the reference): the gate is a Flamethrower
    bulkpoint.  At def=143.04 Shadow Altaria's Flamethrower lands for
    80 and Tinkaton survives on 1 HP long enough to fire its second
    Gigaton Hammer; at def=141.66/140 hp it lands for 81 and Tinkaton
    dies one Gigaton Hammer short.

    The 1/14/14 row is deliberate: it sits *below* the reference's
    143.04 defense but carries 3 more HP, and still wins.  So the
    reference number is a sufficient condition on a def/hp pair, not a
    hard defense floor -- the same "more defense/less hp or vice versa"
    trade the Spidops reference states outright
    (`docs/spidops_deep_dive_reference.md:23`).

    This cell is tight: a full 4096-spread sweep finds only 44 winners
    and *none* strictly under reference spread A on both def and hp.
    That does NOT carry over to the Tinkaton-vs-Medicham oracle above,
    whose "more forgiving win threshold" caveat remains OPEN -- the
    same sweep there finds 1127 winners, 508 of them strictly under the
    reference pair, winning through a Gigaton Hammer attack breakpoint
    rather than a def/hp trade.  See
    `docs/validations/2026-08-08_no_bait_altaria_oracles.md`.
    """
    from gopvpsim.pokemon import Pokemon

    tink = Pokemon.at_best_level('Tinkaton', *tink_ivs, league='great')
    assert tink.def_ == pytest.approx(exp_def, abs=0.01), (
        f"{tink_ivs} no longer sits at def={exp_def} ({why})")
    assert tink.hp == exp_hp, f"{tink_ivs} no longer sits at hp={exp_hp} ({why})"

    result = _tinkaton_vs_rank1_shadow_altaria(tink_ivs, bait_shields=False)
    expected_winner = 0 if wins else 1
    assert result.winner == expected_winner, (
        f"{tink_ivs} (def={exp_def}, hp={exp_hp}, {why}): expected "
        f"{'Tinkaton' if wins else 'Shadow Altaria'} to win the 0-1s with "
        f"baiting off, got winner={result.winner}, "
        f"HP={result.hp_remaining}, score={result.pvpoke_score(0):.0f}")
    if wins:
        assert result.pvpoke_score(0) >= 500
    else:
        assert result.pvpoke_score(0) < 500


@pytest.mark.integration
@pytest.mark.parametrize("tink_ivs", [
    ivs for ivs, _d, _h, wins, _w in TINKATON_VS_SHADOW_ALTARIA_0_1 if not wins
])
def test_tinkaton_0v1_vs_rank1_shadow_altaria_baiting_rescues_low_bulk(tink_ivs):
    """The "without baiting" qualifier in the same reference line is
    load-bearing here -- this is the directional half.

    Every spread that LOSES the 0-1s with baiting off WINS it with
    baiting on, because pvpoke_dp then opens with Bulldoze, eats
    Altaria's only shield with the cheap move, and lands Gigaton Hammer
    unshielded (logged T15 Bulldoze SHIELDED -> T26 Gigaton Hammer 83).
    With baiting off, Gigaton Hammer goes into the shield instead.

    So the reference's bulk requirement is a requirement *only* in the
    no-bait branch; with baiting on, even 15/15/15 wins this cell.  A
    regression that quietly ignores ``bait_shields`` would make the
    no-bait gate test above pass for the wrong reason -- this test is
    what catches that.
    """
    result = _tinkaton_vs_rank1_shadow_altaria(tink_ivs, bait_shields=True)
    assert result.winner == 0, (
        f"{tink_ivs} with baiting ON: expected Tinkaton to win the 0-1s, "
        f"got winner={result.winner}, HP={result.hp_remaining}")
    assert result.pvpoke_score(0) >= 500


def _spidops_vs_altaria(spid_ivs, alt_scenario, bait_shields):
    """Spidops vs Altaria, 1 shield each, PvPoke default movesets.

    alt_scenario: 'rank1' (top stat product, 0/14/15 @ 29) or 'default'
    (PvPoke's default IVs + level, 4/12/13 @ 28.5).
    """
    from functools import partial
    from gopvpsim.pokemon import iv_rank, pvpoke_default_ivs

    spid_fast, spid_charged = get_default_moveset('Spidops', 'great')
    alt_fast, alt_charged = get_default_moveset('Altaria', 'great')

    bp_spid = _make_battle_pokemon(
        'Spidops', spid_fast, spid_charged, 'great', shields=1,
        atk_iv=spid_ivs[0], def_iv=spid_ivs[1], sta_iv=spid_ivs[2])

    if alt_scenario == 'rank1':
        r1 = iv_rank('Altaria', league='great')[0]
        lv, a, d, s = r1['level'], r1['atk_iv'], r1['def_iv'], r1['sta_iv']
    else:
        lv, a, d, s = pvpoke_default_ivs('Altaria', league='great')
    bp_alt = _make_battle_pokemon(
        'Altaria', alt_fast, alt_charged, 'great', shields=1,
        atk_iv=a, def_iv=d, sta_iv=s, max_level=lv)

    pol = (pvpoke_dp if bait_shields
           else partial(pvpoke_dp, bait_shields=False))
    return simulate(bp_spid, bp_alt,
                    charged_policy_0=pol,
                    charged_policy_1=pvpoke_dp,
                    shield_policy_0=pvpoke_simulate_shield,
                    shield_policy_1=pvpoke_simulate_shield)


# (spid_ivs, def, hp, wins_the_1s, why)
SPIDOPS_VS_RANK1_ALTARIA_1_1 = [
    ((1, 14, 14), 140.72, 132, True,
     'minimal spread meeting "140.67 defense with 132+ hp"'),
    ((2, 15, 15), 140.99, 132, True,
     'the spread the reference summary recommends'),
    ((1, 13, 15), 139.94, 132, True,
     'hp met, def short of the OLD line -- now wins'),
    ((0, 12, 12), 140.67, 131, True,
     'def on the old line, hp one short -- the hp gate no longer binds'),
    ((1, 11, 15), 138.88, 133, True,
     'def short of the line but +1 hp -- the def/hp trade clears it'),
    # RESTORED 2026-09-09: the new turn system loosened this gate enough
    # that every previously-listed loser now wins, which would leave this
    # test all-True and therefore vacuous. This spread has MORE defense
    # than several winners but only 121 hp, so it still loses -- the gate
    # is now hp-driven at a lower threshold, not gone.
    ((6, 14, 0), 141.23, 121, False,
     'high def, 121 hp -- still short; keeps this test discriminating'),
]


@pytest.mark.integration
@pytest.mark.parametrize("bait_shields", [True, False])
@pytest.mark.parametrize("spid_ivs,exp_def,exp_hp,wins,why",
                         SPIDOPS_VS_RANK1_ALTARIA_1_1)
def test_spidops_1v1_vs_rank1_altaria_bulk_gate(
        spid_ivs, exp_def, exp_hp, wins, why, bait_shields):
    """Oracle from `docs/spidops_deep_dive_reference.md:35`:

        "140.67 defense with 132+ hp flips the 1s vs the rank #1
         altaria without baits by reducing sky attack damage"

    **Directional bulk-gate test.**  The reference's minimal spread and
    its recommended 2/15/15 both win; a spread one def-step below and a
    spread one HP below both lose.  Measured 2026-08-08 (identical in
    both bait modes): winners 503, 503, 404, 404, 503.

    The reference's stated mechanism checks out in our logs.  Spidops'
    Rock Tomb debuffs Altaria's attack first, so the decisive Sky Attack
    lands post-debuff for 54 at def=140.72 and 55 at def=139.94 -- and
    the winner survives on exactly 1 HP.  One point of Sky Attack
    damage is the whole margin.

    Parametrized over both bait modes to record that, unlike the
    Tinkaton/Shadow-Altaria cell above, ``bait_shields`` makes no
    difference here: pvpoke_dp reaches the same throws either way, so
    the reference's "without baits" qualifier is satisfied but not
    directional.  The 1/11/15 row is the reference's own
    "anything here can work with more defense/less hp or vice versa"
    (`docs/spidops_deep_dive_reference.md:23`) showing up in the sim.
    """
    from gopvpsim.pokemon import Pokemon

    spid = Pokemon.at_best_level('Spidops', *spid_ivs, league='great')
    assert spid.def_ == pytest.approx(exp_def, abs=0.01), (
        f"{spid_ivs} no longer sits at def={exp_def} ({why})")
    assert spid.hp == exp_hp, f"{spid_ivs} no longer sits at hp={exp_hp} ({why})"

    result = _spidops_vs_altaria(spid_ivs, 'rank1', bait_shields)
    expected_winner = 0 if wins else 1
    assert result.winner == expected_winner, (
        f"{spid_ivs} (def={exp_def}, hp={exp_hp}, {why}) "
        f"bait_shields={bait_shields}: expected "
        f"{'Spidops' if wins else 'Altaria'} to win the 1s, got "
        f"winner={result.winner}, HP={result.hp_remaining}, "
        f"score={result.pvpoke_score(0):.0f}")
    if wins:
        assert result.pvpoke_score(0) >= 500
    else:
        assert result.pvpoke_score(0) < 500


# (spid_ivs, def, hp, wins_the_1s, why)
SPIDOPS_VS_DEFAULT_ALTARIA_1_1 = [
    ((0, 13, 14), 140.96, 133, True,
     'minimal spread meeting "140.85 defense with 133+ hp"'),
    ((0, 14, 15), 141.23, 133, True,
     'more defense, same 133 hp'),
    ((0, 14, 13), 141.75, 132, True,
     '132 hp was the gate under legacy; it no longer is'),
    ((1, 11, 15), 138.88, 133, True,
     '133 hp met, def well short -- the def gate no longer binds either'),
    # RESTORED 2026-09-09, same reason as the sibling gate above.
    ((3, 14, 0), 143.15, 123, False,
     'more def than every winner here but only 123 hp -- still loses'),
]


@pytest.mark.integration
@pytest.mark.parametrize("bait_shields", [True, False])
@pytest.mark.parametrize("spid_ivs,exp_def,exp_hp,wins,why",
                         SPIDOPS_VS_DEFAULT_ALTARIA_1_1)
def test_spidops_1v1_vs_default_iv_altaria_needs_133_hp(
        spid_ivs, exp_def, exp_hp, wins, why, bait_shields):
    """Second sentence of `docs/spidops_deep_dive_reference.md:35`:

        "140.85 defense with 133+ hp covers the default IV altaria
         (4/12/13)"

    The harder half of the same matchup: default-IV Altaria hits harder
    than the (0-attack, def-weighted) rank #1, so the spreads that beat
    rank #1 at 132 hp lose here.  The 0/14/13 row is the point -- it has
    *more* defense than either winner and still loses on 132 hp, so the
    "133+ hp" half of the reference is doing real work and is not just
    a restatement of the defense number.  Measured 2026-08-08, both bait
    modes: 503, 503, 416, 416.
    """
    from gopvpsim.pokemon import Pokemon

    spid = Pokemon.at_best_level('Spidops', *spid_ivs, league='great')
    assert spid.def_ == pytest.approx(exp_def, abs=0.01), (
        f"{spid_ivs} no longer sits at def={exp_def} ({why})")
    assert spid.hp == exp_hp, f"{spid_ivs} no longer sits at hp={exp_hp} ({why})"

    result = _spidops_vs_altaria(spid_ivs, 'default', bait_shields)
    expected_winner = 0 if wins else 1
    assert result.winner == expected_winner, (
        f"{spid_ivs} (def={exp_def}, hp={exp_hp}, {why}) "
        f"bait_shields={bait_shields}: expected "
        f"{'Spidops' if wins else 'Altaria'} to win the 1s vs default-IV "
        f"Altaria, got winner={result.winner}, HP={result.hp_remaining}, "
        f"score={result.pvpoke_score(0):.0f}")
    if wins:
        assert result.pvpoke_score(0) >= 500
    else:
        assert result.pvpoke_score(0) < 500


# ---------------------------------------------------------------------------
# Form change oracle tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("shields_m,shields_a,expected_morpeko_score,expected_log", [
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    (0, 0, 471, ['Morpeko (Full Belly): Aura Wheel', 'Azumarill: Play Rough']),
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


# Aegislash (1,1) and (2,1): OPEN divergence cells, pinned to OUR value (see
# the test docstring). Value = PvPoke master's Aegislash score for the same
# cell, from docs/validations/2026-09-09_oracle_new_vs_master_raw.txt, carried
# into the assertion message so a failure shows both sides.
_AEGI_OPEN_DIVERGENCE_PVPOKE = {(1, 1): 618, (2, 1): 618}


@pytest.mark.integration
@pytest.mark.parametrize("shields_a,shields_z,expected_aegi_score,expected_log", [
    # Aegislash (Shield) 4/14/15 vs Azumarill 4/15/13, Great League
    # AEGISLASH_CHARGE_PSYCHO_CUT / SHADOW_BALL / GYRO_BALL
    # vs BUBBLE / ICE_BEAM / PLAY_ROUGH
    # Form change: Shield -> Blade on charged move (activate_charged),
    # Blade -> Shield on shield use (activate_shield).
    #
    # RE-DERIVED 2026-09-09 against PvPoke master under the new turn
    # system (docs/validations/2026-09-09_oracle_new_vs_master_raw.txt,
    # `aegislash_vs_azumarill_form_change`). Seven cells are OK there on
    # score AND chargedLog, so score and log below are PvPoke's. Until
    # 2026-09-25 six of the nine were strict xfails asserting April-2026
    # legacy values (Gyro Ball logs, 374/640/376) that neither sim
    # produces any more, so they pinned nothing.
    (0, 0, 751, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    (0, 1, 348, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                 'Aegislash (Blade): Shadow Ball (shielded)',
                 'Aegislash (Blade): Shadow Ball',
                 'Azumarill: Ice Beam']),
    (0, 2, 112, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                 'Aegislash (Blade): Shadow Ball (shielded)',
                 'Aegislash (Blade): Shadow Ball (shielded)',
                 'Azumarill: Ice Beam']),
    (1, 0, 751, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    # DIVERGENCE PIN (ours 564, PvPoke master 618, same winner). Score is
    # OURS; the chargedLog matches PvPoke's (oracle log_ok=True).
    (1, 1, 564, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                 'Aegislash (Blade): Shadow Ball (shielded)',
                 'Aegislash (Blade): Shadow Ball',
                 'Azumarill: Ice Beam (shielded)',
                 'Aegislash (Blade): Shadow Ball']),
    (1, 2, 382, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                 'Aegislash (Blade): Shadow Ball (shielded)',
                 'Aegislash (Blade): Shadow Ball (shielded)',
                 'Aegislash (Blade): Shadow Ball']),
    (2, 0, 751, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam', 'Aegislash (Blade): Shadow Ball', 'Aegislash (Blade): Shadow Ball']),
    # DIVERGENCE PIN (ours 550, PvPoke master 618, same winner). Score AND
    # chargedLog are OURS: the oracle reports log_ok=False for this cell.
    (2, 1, 550, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                 'Aegislash (Blade): Shadow Ball (shielded)',
                 'Aegislash (Blade): Shadow Ball',
                 'Azumarill: Ice Beam (shielded)',
                 'Azumarill: Play Rough (shielded)',
                 'Aegislash (Blade): Shadow Ball']),
    (2, 2, 382, ['Azumarill: Ice Beam', 'Azumarill: Ice Beam',
                 'Aegislash (Blade): Shadow Ball (shielded)',
                 'Aegislash (Blade): Shadow Ball (shielded)',
                 'Aegislash (Blade): Shadow Ball']),
])
def test_aegislash_vs_azumarill_form_change(shields_a, shields_z,
                                            expected_aegi_score, expected_log):
    """
    OPEN DIVERGENCE, 2026-09-09: two of these nine cells pin OUR value
    where PvPoke master says something else -- (1,1) and (2,1), where we
    score 564/435 and 550/449 against PvPoke's 618/381. Both agree on the
    WINNER; the gap is that our Aegislash banks 100 energy in Shield form
    and throws on T44 where PvPoke commits on T30. Which is right is
    unresolved (see scripts/mechanics_notice.py). Those two are pinned so
    a CHANGE is caught, not because the value is certified; PvPoke's
    value rides in the failure message (_AEGI_OPEN_DIVERGENCE_PVPOKE).
    The other seven cells match PvPoke master exactly on score, winner
    and chargedLog (docs/validations/2026-09-09_oracle_new_vs_master_raw.txt).

    Aegislash form change: Shield<->Blade on charged move / shield use.

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
    pvpoke = _AEGI_OPEN_DIVERGENCE_PVPOKE.get((shields_a, shields_z))
    note = ("" if pvpoke is None else
            f" [divergence pin: expected is OUR value; PvPoke master "
            f"scores {pvpoke}]")
    assert score == expected_aegi_score, (
        f"{shields_a}v{shields_z}: expected Aegislash score={expected_aegi_score}, "
        f"got {score} (delta={score - expected_aegi_score:+d}){note}"
    )
    assert _extract_battle_log(result) == expected_log, (
        f"{shields_a}v{shields_z}: chargedLog mismatch vs pinned log{note}"
    )


@pytest.mark.integration
@pytest.mark.parametrize("shields_m,shields_a,expected_mimikyu_score,expected_log", [
    # RE-DERIVED 2026-09-09 against PvPoke master under the NEW turn
    # system. NOT self-pinned: the oracle harness confirms our engine
    # matches PvPoke on 229 of 243 cells, and these values were checked
    # cell-by-cell against it. Score column is pvpoke_score(0).
    (0, 0, 738, ['Azumarill: Ice Beam', 'Mimikyu (Busted): Play Rough', 'Mimikyu (Busted): Shadow Sneak']),
    (0, 1, 350, ['Azumarill: Ice Beam', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Mimikyu (Busted): Shadow Sneak', 'Azumarill: Ice Beam']),
    (0, 2, 214, ['Azumarill: Ice Beam', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Mimikyu (Busted): Play Rough (shielded)', 'Azumarill: Ice Beam']),
    (1, 0, 761, ['Mimikyu: Play Rough', 'Azumarill: Ice Beam (shielded)', 'Mimikyu: Shadow Sneak']),
    (1, 1, 700, ['Mimikyu: Shadow Sneak (shielded)', 'Azumarill: Ice Beam (shielded)', 'Mimikyu: Shadow Sneak', 'Azumarill: Ice Beam', 'Mimikyu (Busted): Shadow Sneak']),
    (1, 2, 460, ['Mimikyu: Shadow Sneak (shielded)', 'Azumarill: Ice Beam (shielded)', 'Azumarill: Ice Beam', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Mimikyu (Busted): Play Rough', 'Azumarill: Ice Beam']),
    (2, 0, 761, ['Mimikyu: Play Rough', 'Azumarill: Ice Beam (shielded)', 'Mimikyu: Shadow Sneak']),
    (2, 1, 710, ['Mimikyu: Shadow Sneak (shielded)', 'Azumarill: Ice Beam (shielded)', 'Mimikyu: Shadow Sneak', 'Azumarill: Play Rough (shielded)', 'Mimikyu: Shadow Sneak']),
    (2, 2, 607, ['Mimikyu: Shadow Sneak (shielded)', 'Azumarill: Ice Beam (shielded)', 'Mimikyu: Shadow Sneak (shielded)', 'Azumarill: Ice Beam (shielded)', 'Mimikyu: Play Rough', 'Azumarill: Ice Beam']),
])
def test_mimikyu_vs_azumarill_form_change(shields_m, shields_a,
                                          expected_mimikyu_score, expected_log):
    """Mimikyu disguise: first unshielded charged hit absorbed, then -1 def stage.

    Assertion checks both PvPoke score AND chargedLog. chargedLog is
    diagnostic: it reveals the actual SS-delay / Azu-IB-timing
    divergences, whereas scores can coincidentally align even when the
    fights play out differently.
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
# UL Moltres-G near-KO plan choice -- RESOLVED 2026-09-25, matches PvPoke
# ---------------------------------------------------------------------------
# Mechanism and history: DEVELOPER_NOTES "Near-KO DP plan choice" and
# docs/pvpoke_divergences.md item 4. PvPoke's post-DP bandaid swaps
# Moltres-G's self-debuffing Brave Bird nuke for a Fly chain in these
# endgames; it reads `move.damage`, which PvPoke sets at battle start and
# refreshes in OMT (every move, no energy gate), wouldShield and form
# change. Our port refreshed the memo only for AFFORDABLE moves, so the
# bandaid silently skipped here and we kept the nuke. That was documented as
# an intentional deviation on 2026-04-15 (ours retained more HP under the
# legacy turn system); the 2026-09-09 re-derivation under the new turn
# system reversed the outcome in every cell, and on 2026-09-25 the memo was
# brought in line with PvPoke's four refresh points (battle.py
# _optimize_move_timing / simulate / would_shield, formchange.py).
#
# Every cell below is now PvPoke master's score AND chargedLog (243-cell
# oracle audit 2026-09-25: the six former divergences VANISHED, nothing else
# moved). Pre-fix values, for the record: Jellicent 531/670/670,
# Corviknight 456/580/689, Lapras 482 (a winner flip: ours lost by 1 HP).
@pytest.mark.integration
@pytest.mark.parametrize("opp_species,opp_fast,opp_charged,opp_ivs,opp_level,"
                         "shields_opp,shields_mg,expected_mg_score", [
    # Ultra League rank-1 IVs. expected_mg_score is PvPoke master's value
    # (docs/validations/2026-09-09_oracle_new_vs_master_raw.txt); ours
    # matches every cell since 2026-09-25.
    ('Jellicent', 'HEX', ['SURF','SHADOW_BALL'], (6,14,15), 50.0, 0, 0, 639),
    ('Jellicent', 'HEX', ['SURF','SHADOW_BALL'], (6,14,15), 50.0, 0, 1, 779),
    ('Jellicent', 'HEX', ['SURF','SHADOW_BALL'], (6,14,15), 50.0, 0, 2, 779),
    ('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER','PAYBACK'],
     (0,15,15), 48.5, 0, 0, 456),
    ('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER','PAYBACK'],
     (0,15,15), 48.5, 0, 1, 652),
    ('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER','PAYBACK'],
     (0,15,15), 48.5, 0, 2, 760),
    # Pre-fix this cell was a winner flip (ours 482, MG lost by 1 HP).
    ('Lapras', 'PSYWAVE', ['SPARKLING_ARIA','ICE_BEAM'],
     (0,15,15), 42.5, 1, 2, 611),
])
def test_moltres_g_nearKO_plan_divergence_pinned(
        opp_species, opp_fast, opp_charged, opp_ivs, opp_level,
        shields_opp, shields_mg, expected_mg_score):
    """Pin the UL Moltres-G near-KO plan choice to PvPoke master.

    Fails on the pre-2026-09-25 engine (the memo the post-DP bandaid
    reads was only set for affordable moves): six of the seven cells then
    scored 72-129 points lower for MG, and Lapras [1,2] flipped winner.
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
        f"expected MG score={expected_mg_score} (PvPoke master), got "
        f"{mg_score} (delta={mg_score - expected_mg_score:+d})"
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
    # The OTHER Aegislash start (found 2026-09-12): Blade starts pristine
    # and becomes Shield mid-battle, where priority-shuffle clause 4 stamps
    # every charged-move dict selfDebuffing/buffs=[0,0]/sentinel buffTarget
    # in place. Pre-fix, reset_for_battle never undid that, so scenarios
    # after the first shield burn ran Blade with self-debuffing Shadow Ball
    # and Gyro Ball: 5/9 scenarios diverged (winner flips at 1v1), and every
    # baked Aegislash (Blade) column since 9fe11e2 (2026-09-02) carried it.
    # The Shield param above is the fixed point of that stamp and passed.
    pytest.param(
        ('Aegislash (Blade)', 'PSYCHO_CUT', ['SHADOW_BALL', 'GYRO_BALL'],
         'great', 4, 14, 15, False),
        ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
         'great', 4, 15, 13, False),
        id='aegislash-blade-azumarill'),
    # Stateful one-shot form mechanics (review finding T7): the disguise
    # is consumed once per battle and leaves a permanent -1 def stage
    # after busting — exactly the state most likely to leak across the
    # 9-scenario reuse loop.
    pytest.param(
        ('Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'],
         'great', 5, 13, 15, False),
        ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
         'great', 4, 15, 13, False),
        id='mimikyu-azumarill'),
    # Hunger toggle: Morpeko must re-enter every battle in Full Belly
    # (verified in-game 2026-06-06) and toggle per charged move.
    pytest.param(
        ('Morpeko (Full Belly)', 'THUNDER_SHOCK',
         ['AURA_WHEEL_ELECTRIC', 'PSYCHIC_FANGS'], 'great', 5, 14, 15, False),
        ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'],
         'great', 4, 15, 13, False),
        id='morpeko-azumarill'),
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
    # JIT-COV-1: the three matchups above hit none of the TTL-cmp-bonus,
    # dedup-same-energy-keep, or near-KO atk-stage-clamp kernel branches. These
    # two default-moveset GL meta battles do (settrace-verified against the
    # pure-Python mirror, kernels-off): Azumarill vs Bastiodon fires
    # ttl_cmp_bonus + dedup_keep at (1,1); Azumarill vs Annihilape fires
    # atk-stage clamp +4 at (2,2). Without them a future edit to either side of
    # those hand-mirrored kernel/Python pairs desyncs silently.
    pytest.param(('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (0, 15, 15), False,
                  'Bastiodon', 'SMACK_DOWN', ['STONE_EDGE', 'FLAMETHROWER'], (15, 15, 15), False),
                 id='azumarill-bastiodon'),
    pytest.param(('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (0, 15, 15), False,
                  'Annihilape', 'LOW_KICK', ['RAGE_FIST', 'ICE_PUNCH'], (0, 15, 15), False),
                 id='azumarill-annihilape'),
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
    # [1,2]: matches PvPoke exactly since the 2026-06-11 bait-wait fix
    # (the hold wrongly excluded self-debuffing cms[1], so we used to
    # throw a second Fly here where PvPoke holds and then fires Brave
    # Bird under TTL pressure).
    (1, 2, 1, 199, ["Florges: Disarming Voice", "Moltres (Galarian): Fly (shielded)", "Florges: Chilling Water (shielded)", "Moltres (Galarian): Brave Bird (shielded)", "Florges: Chilling Water"]),
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


def test_cm_buff_delta_is_signed_both_axes():
    """ActionLogic.js:519-536: the DP's attackMult tracking is SIGNED —
    chance-1 self-target moves contribute buffs[0] (Superpower -1,
    Draco Meteor -2, Power-Up Punch +1) and chance-1 opponent-target
    moves contribute -buffs[1]. 'both'-target moves and chance<1 moves
    contribute nothing.
    """
    from gopvpsim.battle import _cm_buff_delta

    def cm(buffs, target, chance='1'):
        return {'moveId': 'X', 'buffs': buffs, 'buffTarget': target,
                'buffApplyChance': chance}

    assert _cm_buff_delta(cm([-1, -1], 'self')) == -1      # Superpower
    assert _cm_buff_delta(cm([-2, 0], 'self')) == -2       # Draco Meteor
    assert _cm_buff_delta(cm([1, 0], 'self')) == 1         # Power-Up Punch
    assert _cm_buff_delta(cm([0, -1], 'opponent')) == 1    # def debuff
    assert _cm_buff_delta(cm([0, -2], 'opponent')) == 2    # Acid Spray
    assert _cm_buff_delta(cm([-1, 0], 'opponent')) == 0    # Icy Wind (atk side)
    assert _cm_buff_delta(cm([0, 1], 'both')) == 0         # Obstruct: no DP clause
    assert _cm_buff_delta(cm([-1, -1], 'self', chance='0.5')) == 0
    assert _cm_buff_delta({'moveId': 'X'}) == 0


# ---------------------------------------------------------------------------
# Disguise-break move selection (ActionLogic.js:236-251)
# ---------------------------------------------------------------------------

def test_disguise_break_uses_only_pre_shuffle_cheapest_move():
    """PvPoke breaks a disguise ONLY with poke.fastestChargedMove (the
    pre-shuffle cheapest-by-energy move) — when that move is unaffordable
    or self-debuffing there is NO early throw, even if another charged
    move qualifies. We previously fired the first qualifying shuffled
    slot instead.
    """
    from types import SimpleNamespace
    import gopvpsim.battle as B

    def build(cheap_debuffs: bool):
        cheap = {'moveId': 'CHEAP', 'name': 'Cheap', 'type': 'normal',
                 'power': 40, 'energy': 35, 'energyGain': 0}
        if cheap_debuffs:
            cheap.update({'buffs': [-1, -1], 'buffTarget': 'self',
                          'buffApplyChance': '1', 'selfDebuffing': True})
        pricey = {'moveId': 'PRICEY', 'name': 'Pricey', 'type': 'normal',
                  'power': 90, 'energy': 55, 'energyGain': 0}
        att = make_bp(charged=[cheap, pricey])
        att.energy = 60   # both affordable
        dfn = make_bp(hp=200, shields=0)
        # Minimal protect-form stub: the disguise branch reads
        # _form_change.effect and _form_disguise_active; since the
        # Cramorant port, _holding_prey also reads forms[_form_idx]
        # .species_id on any defender carrying a _form_change.
        dfn._form_change = SimpleNamespace(
            effect='protect',
            forms=(SimpleNamespace(species_id='mimikyu'),))
        dfn._form_disguise_active = True
        return att, dfn

    orig_debug = B._policy_debug
    B._policy_debug = True
    try:
        # Cheapest move is clean: it (and only it) breaks the disguise.
        B._policy_log.clear()
        att, dfn = build(cheap_debuffs=False)
        idx = B.pvpoke_dp(att, dfn)
        assert att.charged_moves[idx]['moveId'] == 'CHEAP'
        assert any('DP[break_disguise]' in line for line in B._policy_log)

        # Cheapest move is self-debuffing: NO early disguise throw —
        # PvPoke does not substitute the pricier clean move.
        B._policy_log.clear()
        att, dfn = build(cheap_debuffs=True)
        B.pvpoke_dp(att, dfn)
        assert not any('DP[break_disguise]' in line for line in B._policy_log)
    finally:
        B._policy_debug = orig_debug
        B._policy_log.clear()


# ---------------------------------------------------------------------------
# from_pokemon's gamemaster lookup (DRY review 2026-08-05 entry 13 / L11)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_from_pokemon_uses_the_cached_entry_index():
    """The species lookup is the cached speciesName index, not a linear scan
    of gm['pokemon'] -- a sweep builds millions of BattlePokemon."""
    from gopvpsim.moves import parse_types
    from gopvpsim.pokemon import Pokemon, get_pokemon_entry, get_entry_index

    bp = _make_battle_pokemon_default('Azumarill', 'great', shields=1)
    entry = get_pokemon_entry('Azumarill')
    assert bp.types == parse_types(entry)
    assert get_entry_index()['Azumarill'] is entry

    pokemon = Pokemon.at_best_level('Azumarill', 15, 15, 15, league='great')
    pokemon.species = 'NotARealMon'
    with pytest.raises(KeyError):
        BattlePokemon.from_pokemon(pokemon, bp.fast_move, list(bp.charged_moves))
