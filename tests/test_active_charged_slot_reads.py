"""Two engine sites must read the RIGHT slot of activeChargedMoves.

PvPoke exposes three different "first" moves and they are not the same object:

* ``activeChargedMoves[0]``  -- post-shuffle slot 0. What Battle.js:1169 reads
  for the shield decision.
* ``fastestChargedMove``     -- snapshotted BEFORE the shuffle
  (Pokemon.js:750), i.e. the cheapest by energy. What ActionLogic.js:395 reads
  for the farm-down cycle threshold.
* the cheapest move          -- equals ``fastestChargedMove``, and equals slot
  0 only when the shuffle happened to leave it there.

We previously read the cheapest move for the first and post-shuffle slot 0 for
the second -- i.e. exactly backwards on both. Neither is observable on the
243-cell oracle grid (its 27 matchups never reach the selfDefenseDebuffing
0-shield branch, and its movesets never make the two cycle-threshold readings
disagree), which is why both survived so long. These tests pin them directly.

Fixture is real PvPoke ordering; see tests/fixtures/pvpoke_mega_acm_ordering.json.
"""
import json
from pathlib import Path

import pytest

from gopvpsim.battle import BattlePokemon, _priority_cm
from gopvpsim.moves import get_moves
from gopvpsim.pokemon import Pokemon

FIXTURE = (Path(__file__).parent / 'fixtures' /
           'pvpoke_mega_acm_ordering.json')

_LEAGUE_BY_CP = {1500: 'great', 2500: 'ultra', 10000: 'master'}
# speciesId -> our display name, for the handful this file touches.
_DISPLAY = {
    'raichu_mega_x': 'Raichu (Mega X)',
    'raichu_mega_y': 'Raichu (Mega Y)',
    'victreebel_mega': 'Victreebel (Mega)',
}


def _cases_where_slot0_is_not_fastest():
    data = json.loads(FIXTURE.read_text())
    return [c for c in data['cases'] if c['fastest'] != c['final'][0]]


def _build(case, fast_id='THUNDER_SHOCK'):
    """A BattlePokemon for the fixture case, plus a plain opponent."""
    from gopvpsim.pokemon import get_pokemon_entry
    fast_db, charged_db = get_moves()
    name = _DISPLAY.get(case['species'])
    if name is None:
        pytest.skip(f"no display-name mapping for {case['species']}")
    entry = get_pokemon_entry(name)
    league = _LEAGUE_BY_CP[case['cp']]
    fid = entry['fastMoves'][0]
    poke = Pokemon.at_best_level(name, 15, 15, 15, league=league)
    cms = [dict(charged_db[m]) for m in case['input']]
    me = BattlePokemon.from_pokemon(poke, dict(fast_db[fid]), cms,
                                    league_cp=case['cp'])
    opp_poke = Pokemon.at_best_level('Azumarill', 15, 15, 15, league=league)
    opp = BattlePokemon.from_pokemon(
        opp_poke, dict(fast_db['BUBBLE']),
        [dict(charged_db['ICE_BEAM']), dict(charged_db['PLAY_ROUGH'])],
        league_cp=case['cp'])
    return me, opp


def test_fixture_has_cases_where_the_two_readings_differ():
    """Positive control: without these, both tests below are vacuous."""
    cands = _cases_where_slot0_is_not_fastest()
    assert len(cands) >= 20, len(cands)


def test_priority_cm_returns_post_shuffle_slot_zero_not_the_cheapest():
    """_priority_cm is activeChargedMoves[0], which is often NOT the cheapest.

    Pre-fix this function was ``_cheapest_cm``, documented as a proxy; it
    returned the min-energy move. On every case below that is the wrong
    answer, so this test fails against the old implementation.
    """
    cands = [c for c in _cases_where_slot0_is_not_fastest()
             if c['species'] in _DISPLAY]
    assert cands, 'no mapped species among the differing cases'
    checked = 0
    for case in cands:
        me, opp = _build(case)
        got = _priority_cm(me, opp)
        cheapest = min(me.charged_moves, key=lambda m: m['energy'])
        slot0 = me._ensure_dp_init_cache(opp)['cms'][0]
        # true by construction, for every case
        assert got is slot0, case['species']
        # discriminating only when the shuffle actually moved something else
        # into slot 0 for THIS pairing; count those rather than requiring it
        # of every case, since the opponent here is not the fixture's.
        if got is not cheapest:
            checked += 1
    assert checked >= 4, (
        f'only {checked} pairings had slot 0 != cheapest, so this test barely '
        f'discriminates the fixed function from the old proxy')


def test_min_cycle_threshold_reads_the_pre_shuffle_fastest_move():
    """ActionLogic.js:395 compares bestChargedMove against fastestChargedMove.

    We used to compare against activeChargedMoves[0]. Structural test, on
    purpose: the two readings pick different MOVES on many orderings, but no
    case is currently known where they produce a different THRESHOLD (the
    n>=3 spec measured 0/111, and 0/600 at n=2). So asserting a behavioral
    difference would be unsatisfiable with real data, and asserting "they
    always agree" would pass against the bug.

    Instead: recompute the threshold both ways and assert the engine matches
    the fastestChargedMove reading, while REPORTING how many pairings the two
    readings disagree on. If that count ever becomes non-zero, this test
    starts discriminating for free and the comment above needs updating.
    """
    def _thr(cms, cm_energy, cm_dpe, cm_self_debuf, best_idx, first):
        """ActionLogic.js:395, parameterised by which move plays 'first'."""
        if (len(cms) > 1 and cm_self_debuf[best_idx]
                and cm_energy[best_idx] > cm_energy[first]
                and cm_dpe[first] > 0
                and cm_dpe[best_idx] / cm_dpe[first] < 2.0):
            return 1.1
        return 2.0

    cases = [c for c in json.loads(FIXTURE.read_text())['cases']
             if c['species'] in _DISPLAY]
    assert cases
    checked = readings_differ = 0
    for case in cases:
        me, opp = _build(case)
        init = me._ensure_dp_init_cache(opp)
        cms, energies = init['cms'], init['cm_energy']
        fastest_pos = energies.index(min(energies))
        want = _thr(cms, energies, init['cm_dpe'], init['cm_self_debuf'],
                    init['best_idx'], fastest_pos)
        as_slot0 = _thr(cms, energies, init['cm_dpe'], init['cm_self_debuf'],
                        init['best_idx'], 0)
        assert init['min_cycle_thr'] == want, (
            f"{case['species']}@{case['cp']}: engine used "
            f"{init['min_cycle_thr']}, fastestChargedMove reading gives {want}")
        if as_slot0 != want:
            readings_differ += 1
        checked += 1
    assert checked >= 9, checked
    # Not an assertion that they differ on REAL movesets -- see the docstring.
    # The synthetic case below is what actually guards the fix.
    assert readings_differ >= 0


def test_min_cycle_threshold_synthetic_case_where_the_readings_disagree():
    """Fail-first guard for the fastestChargedMove fix, driven through the engine.

    No real moveset in reach makes the two readings produce a different
    threshold (measured 0/111 at n=3, 0/600 at n=2), so without this the fix
    would be untested and a revert silent. This constructs an ordering where
    they DO differ -- found by searching synthetic 3-move sets over the
    properties the shuffle actually reads -- and asserts the value the ENGINE
    computes, not a re-spelling of the formula.

    Shape: energies 35/40/45, the 40 self-buffing and the 45 self-debuffing.
    Clause 8 (close-energy self-buffing move promoted as bait) rotates the
    cheapest move to the END, so activeChargedMoves[0] is the 40 while
    fastestChargedMove is the 35, now sitting at position 2.

        fastestChargedMove reading -> 2.0   (correct, ActionLogic.js:395)
        activeChargedMoves[0]      -> 1.1   (what we used to compute)

    The powers were found by searching THROUGH THE ENGINE, not through a
    re-spelling of the dpe formula -- a first attempt used its own dpe model,
    picked a case where the engine actually agreed both ways, and produced a
    test that passed against the bug.
    """
    fast_db, charged_db = get_moves()

    def _cm(mid, energy, power, **kw):
        return {'moveId': mid, 'name': mid, 'type': 'normal', 'power': power,
                'energy': energy, 'energyGain': 0, 'cooldown': 500,
                'turns': 1, **kw}

    cms = [
        _cm('CHEAP', 35, 10),
        _cm('BUFFER', 40, 20, selfBuffing=True),
        _cm('NUKE', 45, 45, selfDebuffing=True, buffs=[-1, 0],
            buffTarget='self', buffApplyChance='1'),
    ]
    # Normal-type moves into a pure-Normal defender: no STAB, no type
    # effectiveness, so damage is monotone in power and the dpe ordering is
    # exactly the one the search assumed.
    me = BattlePokemon.from_pokemon(
        Pokemon.at_best_level('Snorlax', 15, 15, 15, league='great'),
        dict(fast_db['LICK']), [dict(c) for c in cms])
    opp = BattlePokemon.from_pokemon(
        Pokemon.at_best_level('Snorlax', 15, 15, 15, league='great'),
        dict(fast_db['LICK']), [dict(charged_db['BODY_SLAM'])])

    init = me._ensure_dp_init_cache(opp)
    order = [m['moveId'] for m in init['cms']]
    # Preconditions -- if any of these drift the case stops discriminating,
    # and we want THAT to be the failure message rather than the threshold.
    assert order == ['BUFFER', 'NUKE', 'CHEAP'], order
    assert init['cm_energy'] == [40, 45, 35], init['cm_energy']
    assert init['best_idx'] == 1, init['best_idx']
    assert init['cm_self_debuf'][1] == 1

    # Both readings pass the energy test (45 > 40 and 45 > 35); they split on
    # the dpe ratio, which crosses 2.0 between slot 0 and the cheapest move.
    assert init['min_cycle_thr'] == 2.0, (
        'engine used the activeChargedMoves[0] reading (1.1); '
        'ActionLogic.js:395 reads fastestChargedMove, which gives 2.0')


# NOTE: there is deliberately no end-to-end "our ordering == PvPoke's ordering"
# test here. The shuffle's result depends on each side's damage, i.e. on the
# exact opponent, IVs and level of the captured case, and this file cannot
# reproduce those faithfully. Ordering parity against real PvPoke is pinned
# where it can be exact -- tests/test_priority_shuffle_rotate.py, which feeds
# _priority_shuffle each case's OWN captured damages (111/111).
