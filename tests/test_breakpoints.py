"""
Tests for gopvpsim.breakpoints — breakpoint/bulkpoint analysis.

Unit tests use hardcoded stats (no network).
Integration tests (marked 'integration') use the real gamemaster.
"""
import math
import pytest

from gopvpsim.breakpoints import (
    atk_for_damage, def_for_damage,
    breakpoints, bulkpoints,
    iv_breakpoints, iv_bulkpoints,
    Breakpoint, Bulkpoint,
)
from gopvpsim.moves import BONUS, damage as calc_damage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_move(power=10, type_='normal'):
    return {'moveId': 'TEST', 'power': power, 'type': type_, 'energyGain': 5}


# ---------------------------------------------------------------------------
# atk_for_damage
# ---------------------------------------------------------------------------

def test_atk_for_damage_formula():
    """
    D = floor(K * atk / def) + 1  where K = 0.5 * BONUS * power * stab * eff
    Neutral, no STAB: K = 0.5 * 1.3 * 10 = 6.5
    atk_for_damage(7, def=100) = (7-1)*100 / 6.5 = 92.307...
    """
    move = make_move(power=10)
    thresh = atk_for_damage(7, 100.0, move, ['water'], ['normal'])
    k = 0.5 * BONUS * 10 * 1.0 * 1.0   # neutral, no stab
    assert thresh == pytest.approx((7 - 1) * 100.0 / k)

def test_atk_for_damage_consistency():
    """calc_damage at the threshold should give exactly the target damage."""
    move = make_move(power=10)
    for dmg in range(2, 12):
        thresh = atk_for_damage(dmg, 100.0, move, ['normal'], ['normal'])
        # At exactly the threshold, damage should be dmg (floor(k*atk/def) = dmg-1)
        assert calc_damage(10, thresh, 100.0, 'normal', ['normal'], ['normal']) == dmg

def test_atk_for_damage_increases_with_damage():
    move = make_move(power=10)
    thresholds = [atk_for_damage(d, 100.0, move, ['normal'], ['normal'])
                  for d in range(1, 10)]
    assert thresholds == sorted(thresholds)

def test_atk_for_damage_with_stab():
    """STAB reduces the attack threshold needed for a given damage."""
    move = make_move(power=10, type_='water')
    no_stab  = atk_for_damage(7, 100.0, move, ['fire'],  ['normal'])
    with_stab = atk_for_damage(7, 100.0, move, ['water'], ['normal'])
    assert with_stab < no_stab


# ---------------------------------------------------------------------------
# def_for_damage
# ---------------------------------------------------------------------------

def test_def_for_damage_formula():
    """
    def_for_damage(D, atk=100) = K * atk / D
    K = 0.5 * BONUS * 10 = 6.5  (no STAB: fire attacker, normal move)
    def_for_damage(7, atk=100) = 6.5 * 100 / 7 = 92.857...
    """
    move = make_move(power=10)
    thresh = def_for_damage(7, 100.0, move, ['fire'], ['normal'])
    k = 0.5 * BONUS * 10   # no STAB
    assert thresh == pytest.approx(k * 100.0 / 7)

def test_def_for_damage_at_threshold_gives_target_damage():
    """The threshold is exclusive: at exactly thresh, damage = dmg+1; just above, damage = dmg."""
    move = make_move(power=10)
    for dmg in range(2, 12):
        thresh = def_for_damage(dmg, 100.0, move, ['fire'], ['normal'])
        # At exactly the threshold, damage is still dmg+1 (threshold is exclusive)
        assert calc_damage(10, 100.0, thresh, 'normal', ['fire'], ['normal']) == dmg + 1
        # Just above the threshold, damage drops to dmg
        assert calc_damage(10, 100.0, thresh * 1.001, 'normal', ['fire'], ['normal']) == dmg

def test_def_for_damage_with_stab():
    """STAB increases K, so less defense is needed to reduce damage to the same value."""
    move = make_move(power=10, type_='water')
    no_stab   = def_for_damage(7, 100.0, move, ['fire'],  ['normal'])
    with_stab = def_for_damage(7, 100.0, move, ['water'], ['normal'])
    assert with_stab > no_stab

def test_def_for_damage_increases_with_lower_damage():
    """More defense is needed to achieve lower incoming damage."""
    move = make_move(power=10)
    thresholds = [def_for_damage(d, 100.0, move, ['normal'], ['normal'])
                  for d in range(10, 1, -1)]
    assert thresholds == sorted(thresholds)


# ---------------------------------------------------------------------------
# breakpoints()
# ---------------------------------------------------------------------------

def test_breakpoints_returns_list_of_breakpoint():
    move = make_move(power=10)
    result = breakpoints(move, ['normal'], 100.0, ['normal'], 50.0, 200.0)
    assert all(isinstance(b, Breakpoint) for b in result)

def test_breakpoints_sorted_by_threshold():
    move = make_move(power=10)
    result = breakpoints(move, ['normal'], 100.0, ['normal'], 50.0, 200.0)
    thresholds = [b.atk_threshold for b in result]
    assert thresholds == sorted(thresholds)

def test_breakpoints_damage_increases():
    """Each successive breakpoint should deal one more damage."""
    move = make_move(power=10)
    result = breakpoints(move, ['normal'], 100.0, ['normal'], 50.0, 200.0)
    for i in range(1, len(result)):
        assert result[i].damage == result[i-1].damage + 1

def test_breakpoints_all_in_range():
    move = make_move(power=10)
    atk_min, atk_max = 80.0, 160.0
    result = breakpoints(move, ['normal'], 100.0, ['normal'], atk_min, atk_max)
    for b in result:
        assert atk_min <= b.atk_threshold <= atk_max

def test_breakpoints_empty_when_no_change():
    """A very narrow range with no breakpoint in it should return empty."""
    move = make_move(power=10)
    # Find the current damage at a specific atk, then check a tiny range inside one tier
    atk = 100.0
    dmg = calc_damage(10, atk, 100.0, 'normal', ['normal'], ['normal'])
    # The next breakpoint is at atk_for_damage(dmg+1, ...)
    from gopvpsim.breakpoints import atk_for_damage
    next_thresh = atk_for_damage(dmg + 1, 100.0, move, ['normal'], ['normal'])
    # Range that doesn't include next_thresh
    result = breakpoints(move, ['normal'], 100.0, ['normal'], atk, next_thresh - 0.01)
    assert result == []


# ---------------------------------------------------------------------------
# bulkpoints()
# ---------------------------------------------------------------------------

def test_bulkpoints_returns_list_of_bulkpoint():
    move = make_move(power=10)
    result = bulkpoints(move, 100.0, ['normal'], ['normal'], 50.0, 200.0)
    assert all(isinstance(b, Bulkpoint) for b in result)

def test_bulkpoints_sorted_by_threshold():
    move = make_move(power=10)
    result = bulkpoints(move, 100.0, ['normal'], ['normal'], 50.0, 200.0)
    thresholds = [b.def_threshold for b in result]
    assert thresholds == sorted(thresholds)

def test_bulkpoints_damage_decreases_with_defense():
    """Higher defense thresholds correspond to lower incoming damage."""
    move = make_move(power=10)
    result = bulkpoints(move, 100.0, ['normal'], ['normal'], 50.0, 200.0)
    for i in range(1, len(result)):
        assert result[i].damage < result[i-1].damage

def test_bulkpoints_all_in_range():
    move = make_move(power=10)
    def_min, def_max = 70.0, 150.0
    result = bulkpoints(move, 100.0, ['normal'], ['normal'], def_min, def_max)
    for b in result:
        assert def_min <= b.def_threshold <= def_max


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_iv_breakpoints_returns_list():
    results = iv_breakpoints('Medicham', 'COUNTER', 'Azumarill')
    assert isinstance(results, list)
    assert len(results) > 0

@pytest.mark.integration
def test_iv_breakpoints_sorted_damage_desc():
    results = iv_breakpoints('Medicham', 'COUNTER', 'Azumarill')
    damages = [r['damage'] for r in results]
    assert damages == sorted(damages, reverse=True)

@pytest.mark.integration
def test_iv_breakpoints_all_within_cp_cap():
    from gopvpsim.pokemon import LEAGUE_CAPS, cp as calc_cp, get_species
    cap = LEAGUE_CAPS['great']
    base = get_species('Medicham')
    results = iv_breakpoints('Medicham', 'COUNTER', 'Azumarill')
    for r in results:
        c = calc_cp(base['atk'], base['def'], base['hp'],
                    r['atk_iv'], r['def_iv'], r['sta_iv'], r['level'])
        assert c <= cap, f"IV {r['atk_iv']}/{r['def_iv']}/{r['sta_iv']} CP {c} > {cap}"

@pytest.mark.integration
def test_iv_breakpoints_higher_atk_iv_higher_or_equal_damage():
    """Within the same def_iv/sta_iv row, higher atk_iv gives >= damage."""
    results = iv_breakpoints('Medicham', 'COUNTER', 'Azumarill')
    # Build a lookup: (atk_iv, def_iv, sta_iv) -> damage
    lookup = {(r['atk_iv'], r['def_iv'], r['sta_iv']): r['damage'] for r in results}
    for def_iv in range(16):
        for sta_iv in range(16):
            for atk_iv in range(1, 16):
                d_hi = lookup.get((atk_iv,     def_iv, sta_iv))
                d_lo = lookup.get((atk_iv - 1, def_iv, sta_iv))
                if d_hi is not None and d_lo is not None:
                    assert d_hi >= d_lo

@pytest.mark.integration
def test_iv_bulkpoints_returns_list():
    results = iv_bulkpoints('Azumarill', 'COUNTER', 'Medicham')
    assert isinstance(results, list)
    assert len(results) > 0

@pytest.mark.integration
def test_iv_bulkpoints_sorted_damage_asc():
    results = iv_bulkpoints('Azumarill', 'COUNTER', 'Medicham')
    damages = [r['damage'] for r in results]
    assert damages == sorted(damages)

@pytest.mark.integration
def test_iv_bulkpoints_higher_def_iv_lower_or_equal_damage():
    """Within the same atk_iv/sta_iv row, higher def_iv gives <= damage received."""
    results = iv_bulkpoints('Azumarill', 'COUNTER', 'Medicham')
    lookup = {(r['atk_iv'], r['def_iv'], r['sta_iv']): r['damage'] for r in results}
    for atk_iv in range(16):
        for sta_iv in range(16):
            for def_iv in range(1, 16):
                d_hi = lookup.get((atk_iv, def_iv,     sta_iv))
                d_lo = lookup.get((atk_iv, def_iv - 1, sta_iv))
                if d_hi is not None and d_lo is not None:
                    assert d_hi <= d_lo
