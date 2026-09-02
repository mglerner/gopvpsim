"""``_priority_shuffle`` must reproduce PvPoke's activeChargedMoves ordering
at three charged moves, including the rotate-vs-swap distinction.

PvPoke's reorder primitive is ``splice(0, 1)`` + ``push`` (Pokemon.js:760-762
and four sibling sites) -- a ROTATE-LEFT of the whole array, not a swap of
slots 0 and i:

    n=2:  [a, b]    -> [b, a]        (a swap gives the same thing)
    n=3:  [a, b, c] -> [b, c, a]     (a swap would give [c, b, a])

That equivalence at n=2 is why our straight-line swap port was correct for
years and why nothing caught it: three charged moves were unreachable until
PvPoke flipped ``hasThirdChargedMove()`` for megas in 574aeb0da.

The fixture is ORDERING captured from a running PvPoke, not from a
transcription of its algorithm -- an earlier pass at this question reached
the wrong answer precisely by transcribing into Python and reasoning about
the transcription.
"""
import json
from pathlib import Path

import pytest

from gopvpsim.battle import _priority_shuffle

FIXTURE = (Path(__file__).parent / 'fixtures' /
           'pvpoke_mega_acm_ordering.json')


def _load():
    return json.loads(FIXTURE.read_text())


def _build(case):
    """(cms in pre-shuffle order, cm_dmgs, idx_map) for _priority_shuffle."""
    cms = []
    for mid in case['input']:
        m = dict(case['moves'][mid])
        m['moveId'] = mid
        cms.append(m)
    cm_dmgs = [m['damage'] for m in cms]
    idx_map = {id(m): i for i, m in enumerate(cms)}
    return cms, cm_dmgs, idx_map


def _swap_shuffle(cms, cm_dmgs, idx_map):
    """The PRE-2026-09-02 port: straight-line clauses on slot 1, swap primitive.

    Kept here only as the negative control for
    ``test_a_swap_port_would_fail_this_fixture``. If this ever stops
    disagreeing with the real ordering, the fixture has lost its
    discriminating power and the main test below is vacuous.
    """
    def dmg(m):
        return cm_dmgs[idx_map[id(m)]]

    def adj(m):
        raw = dmg(m) / m['energy']
        buffs = m.get('buffs')
        if not buffs:
            return raw
        bt = m.get('buffTarget', '')
        chance = float(m.get('buffApplyChance', 0) or 0)
        eff = 0.0
        if bt == 'self' and buffs[0] > 0:
            eff = buffs[0] * (80 / m['energy'])
        elif bt == 'opponent' and buffs[1] < 0:
            eff = abs(buffs[1]) * (80 / m['energy'])
        return raw * (4 + eff * chance) / 4 if eff > 0 else raw

    def sw():
        cms[0], cms[1] = cms[1], cms[0]

    if (cms[1]['energy'] == cms[0]['energy']
            and not cms[1].get('selfDebuffing', False)):
        if cms[1].get('buffs') or dmg(cms[1]) > dmg(cms[0]):
            sw()
    if (cms[1]['energy'] == cms[0]['energy']
            and cms[0].get('buffs') and cms[1].get('buffs')
            and not cms[1].get('selfDebuffing', False)
            and float(cms[1].get('buffApplyChance', 0) or 0)
            > float(cms[0].get('buffApplyChance', 0) or 0)):
        sw()
    if (cms[1]['energy'] - cms[0]['energy'] <= 10
            and not cms[1].get('selfDebuffing', False)
            and cms[1].get('selfBuffing', False)
            and adj(cms[0]) - adj(cms[1]) < 0.3):
        sw()
    if (cms[1]['energy'] - cms[0]['energy'] <= 10
            and cms[0].get('selfAttackDebuffing', False)
            and not cms[1].get('selfDebuffing', False)):
        sw()
    if (cms[1]['energy'] - cms[0]['energy'] <= 10
            and cms[0].get('selfDebuffing', False)
            and cms[0]['energy'] > 50
            and not cms[1].get('selfDebuffing', False)):
        sw()
    if (cms[1]['energy'] - cms[0]['energy'] <= 5
            and cms[1].get('selfBuffing', False)):
        sw()


def test_fixture_is_present_and_non_trivial():
    """Guard against the 'both empty' silent failure the policy calls out."""
    data = _load()
    cases = data['cases']
    assert len(cases) >= 100, len(cases)
    assert all(len(c['input']) == 3 for c in cases)
    assert len({c['species'] for c in cases}) >= 13
    # the fixture must actually exercise reordering, not just identity
    reordered = [c for c in cases if c['final'] != c['input']]
    assert len(reordered) >= 30, f'only {len(reordered)} cases reorder'


def test_shuffle_reproduces_real_pvpoke_ordering_at_three_moves():
    """The headline pin: 111 real supermega orderings, exact."""
    cases = _load()['cases']
    bad = []
    for c in cases:
        cms, cm_dmgs, idx_map = _build(c)
        _priority_shuffle(cms, cm_dmgs, idx_map)
        got = [m['moveId'] for m in cms]
        if got != c['final']:
            bad.append(f"{c['species']}@{c['cp']} vs {c['opponent']}: "
                       f"got {got} want {c['final']}")
    assert not bad, (f'{len(bad)}/{len(cases)} orderings differ from real '
                     f'PvPoke:\n  ' + '\n  '.join(bad[:12]))


def test_a_swap_port_would_fail_this_fixture():
    """Positive control: the fixture discriminates rotate from swap.

    Without this, a fixture that happened to contain only cases where the two
    agree would let a swap-based regression pass silently. Floor is set below
    today's 54 so a roster/moveset refresh is not a false alarm.
    """
    cases = _load()['cases']
    disagreements = 0
    for c in cases:
        cms, cm_dmgs, idx_map = _build(c)
        _swap_shuffle(cms, cm_dmgs, idx_map)
        if [m['moveId'] for m in cms] != c['final']:
            disagreements += 1
    assert disagreements >= 30, (
        f'the swap port only differs on {disagreements} cases -- this fixture '
        f'no longer discriminates rotate from swap, so the main test is weak')


def test_the_rotate_primitive_alone_is_what_matters_not_the_loop():
    """Isolates the rotate from the loop.

    ``swap_final`` was captured by patching PvPoke's own JS to swap slots 0
    and i while KEEPING the ``for i`` loop. So it differs from the real
    ordering only because of the reorder primitive. That it still disagrees
    on many cases is the evidence that adopting the loop without adopting the
    rotate would have been wrong -- the trap a "just add a loop"
    generalization of our old code would have fallen into.

    (Distinct from ``_swap_shuffle``, which is our actual PRE-2026-09-02 port:
    swap AND no loop. The two disagree with each other on ~11 cases, which is
    why they are separate controls rather than one.)
    """
    cases = [c for c in _load()['cases'] if c.get('swap_final')]
    assert len(cases) >= 100, len(cases)
    loop_plus_swap_wrong = sum(1 for c in cases
                               if c['swap_final'] != c['final'])
    assert loop_plus_swap_wrong >= 30, (
        f'loop+swap only differs from real on {loop_plus_swap_wrong} cases; '
        f'the rotate primitive would then be nearly unobservable here')

    # And our shuffle agrees with real on every one of those, which is the
    # substantive claim: we match because of the rotate, not by luck.
    for c in cases:
        if c['swap_final'] == c['final']:
            continue
        cms, cm_dmgs, idx_map = _build(c)
        _priority_shuffle(cms, cm_dmgs, idx_map)
        assert [m['moveId'] for m in cms] == c['final'], \
            f"{c['species']}@{c['cp']} vs {c['opponent']}"


def test_rotate_and_swap_are_identical_at_two_moves():
    """Why the old port was correct, stated as an executable fact.

    Derived from the fixture's own move data (first two moves of each case),
    so it exercises real gamemaster properties rather than invented ones.
    """
    cases = _load()['cases']
    n = 0
    for c in cases:
        cms_a, d_a, i_a = _build(c)
        cms_b, d_b, i_b = _build(c)
        del cms_a[2], cms_b[2]
        d_a, d_b = d_a[:2], d_b[:2]
        i_a = {id(m): k for k, m in enumerate(cms_a)}
        i_b = {id(m): k for k, m in enumerate(cms_b)}
        _priority_shuffle(cms_a, d_a, i_a)
        _swap_shuffle(cms_b, d_b, i_b)
        assert [m['moveId'] for m in cms_a] == [m['moveId'] for m in cms_b], \
            f"{c['species']}@{c['cp']}"
        n += 1
    assert n >= 100, n


def test_bestChargedMove_and_fastest_are_not_always_slot_zero():
    """Records two facts the bandaid chain depends on, so they cannot rot.

    ``fastestChargedMove`` is snapshotted BEFORE the shuffle (Pokemon.js:750)
    and is therefore frequently NOT the post-shuffle slot 0 -- which is why
    reading slot 0 for it is a bug (battle.py's min_cycle_thr). Floors, not
    equalities, per the testing policy.
    """
    cases = _load()['cases']
    fastest_not_slot0 = sum(1 for c in cases
                            if c['fastest'] != c['final'][0])
    best_not_slot0 = sum(1 for c in cases if c['best'] != c['final'][0])
    assert fastest_not_slot0 >= 20, fastest_not_slot0
    assert best_not_slot0 >= 20, best_not_slot0
    # positive control: not everything is off slot 0 either
    assert fastest_not_slot0 < len(cases)
