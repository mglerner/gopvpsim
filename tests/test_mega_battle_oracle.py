"""Three-charged-move mega battles, against PvPoke ground truth.

This is the end-to-end test for the whole n>=3 port: the shuffle's rotate
primitive, the bandaid loop generalizations, and the Mega Bonus multiplier all
have to be right simultaneously for a cell to match.

Fixture is 10 matchups x 9 shield cells captured from a RUNNING PvPoke
(`scripts/pvpoke_trace.js` at pvpoke 56bc6a8b1), including:

* two ROTATE DISCRIMINATORS -- `raichu_mega_y_vs_medicham` and
  `victreebel_mega_vs_medicham`. A swap-primitive port scores 662 instead of
  205 in the first (2-2 cell) and 361 instead of 163 in the second (1-1),
  so a shuffle regression fails loudly rather than drifting.
* two 2-MOVE CONTROLS -- byte-identical inputs minus the `*_PLUS` move.
  Asserted as a PAIR with their 3-move twin: if the pair ever converges, the
  third charged move is being dropped somewhere (Pokemon build, DP
  enumeration, or bait logic) even when the individual scores look plausible.

Levels are pinned in the fixture because PvPoke's mega GL/UL defaults sit far
below the level cap (Mega Skarmory GL is level 14.5), so an unpinned level
would compare two different Pokemon.
"""
import json
from pathlib import Path

import pytest

from gopvpsim.battle import simulate, pvpoke_dp
from tests.test_battle import _make_battle_pokemon, _extract_battle_log

FIXTURE = Path(__file__).parent / 'fixtures' / 'pvpoke_mega_battles.json'

# 3-move matchup -> its byte-identical 2-move control.
CONTROL_PAIRS = [
    ('skarmory_mega_vs_azumarill', 'skarmory_mega_vs_azumarill_2MOVE_CONTROL'),
    ('raichu_mega_x_vs_azumarill', 'raichu_mega_x_vs_azumarill_2MOVE_CONTROL'),
]


def _load():
    return json.loads(FIXTURE.read_text())['matchups']


def _run(m, s1, s2):
    p1, p2 = m['p1'], m['p2']
    league = m.get('league', 'great')

    def side(p, shields):
        return _make_battle_pokemon(
            _display(p['species']), p['fast'], p['charged'], league, shields,
            *p['ivs'],
            max_level=p['level'] if p.get('level') else 51.0)

    r = simulate(side(p1, s1), side(p2, s2),
                 charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp,
                 log=True)
    return (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)),
            r.winner, _extract_battle_log(r))


def _display(species_id):
    """speciesId -> our display name, via the gamemaster (no hand table)."""
    from gopvpsim.data import load_gamemaster
    global _SID
    try:
        _SID
    except NameError:
        _SID = {p['speciesId']: p['speciesName']
                for p in load_gamemaster()['pokemon']}
    return _SID[species_id]


def _cells(m):
    return sorted(m['cells'].items())


ALL = sorted(_load())


def test_fixture_is_present_and_non_trivial():
    """Guard against the 'both empty' silent failure mode."""
    ms = _load()
    assert len(ms) >= 10, len(ms)
    assert all(len(m['cells']) == 9 for m in ms.values())
    three_move = [k for k, m in ms.items() if len(m['p1']['charged']) == 3]
    assert len(three_move) >= 8, three_move
    # the mega moves must actually appear in some chargedLog, or we are
    # asserting on battles that never exercise the third slot
    logs = [line for m in ms.values() for c in m['cells'].values()
            for line in c['chargedLog']]
    assert any('+' in line for line in logs), 'no *_PLUS move ever thrown'


@pytest.mark.parametrize('label', ALL)
def test_mega_matchup_matches_pvpoke(label):
    """All 9 shield cells: score, winner and chargedLog."""
    m = _load()[label]
    bad = []
    for cell, want in _cells(m):
        s1, s2 = (int(x) for x in cell.split('-'))
        got = _run(m, s1, s2)
        exp = (want['score'][0], want['score'][1], want['winner'],
               want['chargedLog'])
        if got != exp:
            bad.append(f'  [{cell}] got {got[:3]} want {exp[:3]}\n'
                       f'        got log {got[3]}\n'
                       f'        want log {exp[3]}')
    assert not bad, f'{label}: {len(bad)}/9 cells differ\n' + '\n'.join(bad)


@pytest.mark.parametrize('three,two', CONTROL_PAIRS,
                         ids=[p[0] for p in CONTROL_PAIRS])
def test_third_charged_move_actually_changes_the_fight(three, two):
    """Paired assertion: the 3-move and 2-move runs must NOT agree.

    Individually both can look plausible while the third move is silently
    dropped. Only the pair catches that.
    """
    ms = _load()
    m3, m2 = ms[three], ms[two]
    assert len(m3['p1']['charged']) == 3 and len(m2['p1']['charged']) == 2
    # the control is the same build minus the mega move
    assert m3['p1']['charged'][:2] == m2['p1']['charged']
    assert m3['p1']['ivs'] == m2['p1']['ivs']
    assert m3['p1'].get('level') == m2['p1'].get('level')

    differing = 0
    for cell, _ in _cells(m3):
        s1, s2 = (int(x) for x in cell.split('-'))
        if _run(m3, s1, s2)[:3] != _run(m2, s1, s2)[:3]:
            differing += 1
    assert differing >= 3, (
        f'{three}: only {differing}/9 cells differ from the 2-move control -- '
        f'the third charged move is barely affecting the fight, which is what '
        f'a silently-dropped slot 2 looks like')


def test_rotate_discriminator_cells_carry_their_documented_values():
    """The two cells where a swap-primitive port scores very differently.

    Pinned explicitly (not just as part of the 9-cell sweep) so the failure
    message names the mechanism rather than leaving someone to rediscover it.
    """
    ms = _load()
    r = ms['raichu_mega_y_vs_medicham']['cells']['2-2']
    assert r['score'][0] == 205, r['score']
    v = ms['victreebel_mega_vs_medicham']['cells']['1-1']
    assert v['score'][0] == 163, v['score']

    got_r = _run(ms['raichu_mega_y_vs_medicham'], 2, 2)
    assert got_r[0] == 205, (
        f'got {got_r[0]}, want 205. A swap-primitive shuffle scores 662 here; '
        f'see tests/test_priority_shuffle_rotate.py')
    got_v = _run(ms['victreebel_mega_vs_medicham'], 1, 1)
    assert got_v[0] == 163, (
        f'got {got_v[0]}, want 163. A swap-primitive shuffle scores 361 here.')
