"""The three ActionLogic n=2 semantic changes are knob-gated and default OFF.

pvpoke 574aeb0da / feba66f47 changed behaviour for ORDINARY two-charged-move
Pokemon while adding mega third-move support. Those changes are separable from
the n>=3 loop generalizations (which are adopted unconditionally and are
provably no-ops at n=2), and each is a real decision under CLAUDE.md's
divergence gate rather than something to absorb silently.

The knobs exist so the decision can be MEASURED on our own engine instead of
argued, and so flipping one later is a one-line change with a test that already
describes what it does. Default False = our pre-2026-09-02 behaviour, which is
what every cached sweep column and shipped dive was simmed under.

Precedent for the pattern: the Cramorant policy-lab knobs in the same module.
"""
import itertools

import pytest

from gopvpsim import battle as B
from gopvpsim.battle import BattlePokemon, simulate, pvpoke_dp
from gopvpsim.moves import get_moves
from gopvpsim.pokemon import Pokemon

KNOBS = ('_AL_FARM_BAIT_MERGE', '_AL_SHIELDS_DOWN_ANTI_DEBUFF',
         '_AL_PREFER_NON_DEBUFFING')


@pytest.fixture
def knob():
    """Set one knob for the duration of a test, always restoring it.

    Restoring matters more than usual here: these are module globals the sweep
    cache does NOT key on, so a leaked True would silently mis-sim every later
    test in the session.
    """
    saved = {k: getattr(B, k) for k in KNOBS}

    def _set(name, value):
        assert name in KNOBS, name
        setattr(B, name, value)
    yield _set
    for k, v in saved.items():
        setattr(B, k, v)


def test_all_three_default_to_our_pre_update_behaviour():
    """A flipped default is a cold re-dive; it must never happen by accident."""
    for k in KNOBS:
        assert getattr(B, k) is False, (
            f'{k} is True. These knobs change n=2 scores, so every cached '
            f'sweep column and shipped dive was simmed under False.')


def _build(name, fast, charged, league, shields, ivs=(15, 15, 15)):
    fast_db, chg_db = get_moves()
    pk = Pokemon.at_best_level(name, *ivs, league=league)
    return BattlePokemon.from_pokemon(
        pk, dict(fast_db[fast]), [dict(chg_db[c]) for c in charged],
        shields=shields)


def _sweep(focal, opp, league='master'):
    """All 9 shield cells for one matchup -> [(score0, winner), ...]."""
    out = []
    for s1, s2 in itertools.product((0, 1, 2), (0, 1, 2)):
        r = simulate(_build(*focal, league, s1), _build(*opp, league, s2),
                     charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp)
        out.append((round(r.pvpoke_score(0)), r.winner))
    return out


# Xerneas pairs a self-debuffing cheapest move (Close Combat) with a
# non-debuffing alternative, which is exactly block (e)'s trigger shape. Found
# by the corpus A/B, not hand-picked.
XERNEAS = ('Xerneas', 'GEOMANCY', ['CLOSE_COMBAT', 'MOONBLAST'])
PALKIA_O = ('Palkia (Origin)', 'DRAGON_BREATH',
            ['SPACIAL_REND', 'DRACO_METEOR'])


def test_block_e_actually_changes_something_when_enabled(knob):
    """The knob must be live, not decorative.

    A knob that changes nothing would pass every other test in this file while
    being wired to the wrong place.
    """
    before = _sweep(XERNEAS, PALKIA_O)
    knob('_AL_SHIELDS_DOWN_ANTI_DEBUFF', True)
    after = _sweep(XERNEAS, PALKIA_O)
    assert before != after, (
        'enabling _AL_SHIELDS_DOWN_ANTI_DEBUFF changed nothing on a matchup '
        'chosen because it has the trigger shape -- the block is probably not '
        'reachable from where it was inserted')
    # The gate is `defender.shields == 0` on the LIVE count, not the starting
    # one, so cells that START with shields still reach it once those are
    # spent -- an earlier version of this test wrongly asserted the changed
    # cells all had s2 == 0.
    changed = sum(1 for b, a in zip(before, after) if b != a)
    assert changed >= 2, changed


@pytest.mark.parametrize('name', KNOBS)
def test_disabling_a_knob_restores_the_default_result(knob, name):
    """Round-trip: on then off reproduces the default exactly.

    Guards against a knob that mutates cached state (the frozen dp_init cache
    holds ordering and dpe) rather than only branching.
    """
    base = _sweep(XERNEAS, PALKIA_O)
    knob(name, True)
    _sweep(XERNEAS, PALKIA_O)
    knob(name, False)
    assert _sweep(XERNEAS, PALKIA_O) == base


def test_knobs_are_documented_where_someone_will_look():
    """Each knob names its upstream site, so nobody has to re-derive it."""
    import inspect
    src = inspect.getsource(B)
    head = src[:src.index('_CRAM_DIVE_GATE_DPE')]
    for token in ('574aeb0da', 'feba66f47', 'ActionLogic.js:405',
                  'ActionLogic.js:940', 'ActionLogic.js:954',
                  'cold re-dive', 'sweep cache does NOT key'):
        assert token in head, f'knob docs no longer mention {token!r}'
