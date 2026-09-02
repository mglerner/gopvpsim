"""Every damage-formula surface must agree with ``gopvpsim.moves.damage``.

Why this file exists
--------------------
The damage formula was spelled out in six places before 2026-09-02: the
canonical scalar ``moves.damage``, a numpy mirror in
``scripts/deep_dive_signature.py``, four "K" (constant-half) forms in the
breakpoint/bulkpoint solvers, and a plain re-implementation in
``scripts/deep_dive_analysis.py``. That is the same unforced-copy shape that
let the JS ``SHADOW_DEF_MULT`` sit at the wrong value for months
(DEVELOPER_NOTES "Engine constant sourcing"), and it is why
``pokemon.effective_stats`` was created. The Mega Bonus was the next constant
that had to land in all of them at once.

The formula's constant half now lives in ONE place,
``moves.damage_constant``. Two mirrors remain on purpose:

* ``deep_dive_signature.damage_vec`` -- vectorized over 4096-IV arrays;
  per-element scalar calls are not viable at sweep scale.
* ``joint_iv_breakpoints.independent`` -- a deliberately INDEPENDENT
  transcription (own type chart) whose whole job is to not be
  ``moves.damage`` compared to itself. Not tested here for that reason.

These tests pin the remaining mirrors to the canonical function, mega path
included, and they carry the floors the testing policy requires so a scanner
that silently stops comparing anything fails loudly.
"""
import math

import numpy as np
import pytest

from gopvpsim.breakpoints import _K, atk_for_damage, def_for_damage
from gopvpsim.moves import (BONUS, MEGA_BONUS, damage, damage_constant,
                            get_moves, mega_multiplier, type_effectiveness,
                            stab)
from gopvpsim.pokemon import mega_level_from_tags

# scripts/ is a directory of scripts, not a package; conftest's shared loader
# puts it on sys.path (same pattern as tests/test_signature_cramorant.py).
from tests.conftest import load_deep_dive

load_deep_dive()
import deep_dive_signature  # noqa: E402
from deep_dive_signature import damage_vec  # noqa: E402


TYPE_PAIRS = [
    ('water',    ['water'],           ['normal']),
    ('fire',     ['fire', 'flying'],  ['grass', 'steel']),
    ('ground',   ['ground'],          ['flying']),          # double resist
    ('fighting', ['normal'],          ['ghost']),           # immunity floor
    ('psychic',  ['psychic'],         ['dark']),
    ('flying',   ['flying', 'steel'], ['water', 'fairy']),
]
POWERS = [1, 6, 9, 35, 60, 65, 80, 90, 110, 130]
STATS = [(93.4, 134.5), (142.4, 123.1), (215.0, 98.7), (60.0, 250.0)]


def _cases():
    for mtype, atypes, dtypes in TYPE_PAIRS:
        for power in POWERS:
            for atk, dfn in STATS:
                for mega_mult in (1.0,) + MEGA_BONUS:
                    yield mtype, atypes, dtypes, power, atk, dfn, mega_mult


def test_damage_is_exactly_floor_of_k_times_ratio():
    """The canonical function IS the shared constant plus atk/def.

    Pins the contract every other surface relies on: if this identity ever
    stops holding, the mirrors below are pinned to the wrong thing.
    """
    n = 0
    for mtype, atypes, dtypes, power, atk, dfn, mm in _cases():
        k = damage_constant(power, mtype, atypes, dtypes, mm)
        assert damage(power, atk, dfn, mtype, atypes, dtypes, mm) == \
            math.floor(k * atk / dfn) + 1
        n += 1
    assert n >= 1000, f'scanner degenerate: only {n} cases'


def test_damage_vec_is_bit_identical_to_scalar_damage():
    """The numpy mirror must match the scalar form element-for-element."""
    n = mism = 0
    for mtype, atypes, dtypes, power, atk, dfn, mm in _cases():
        want = damage(power, atk, dfn, mtype, atypes, dtypes, mm)
        got = damage_vec(power, np.array([atk]), np.array([dfn]),
                         mtype, atypes, dtypes, mm)
        assert got.dtype == np.int64
        if int(got[0]) != want:
            mism += 1
        n += 1
    assert n >= 1000, f'scanner degenerate: only {n} cases'
    assert mism == 0, f'{mism}/{n} damage_vec values differ from moves.damage'


def test_damage_vec_matches_across_a_whole_array():
    """Array-shaped call, not just length-1 -- the real usage shape."""
    atks = np.linspace(50.0, 300.0, 512)
    for mtype, atypes, dtypes in TYPE_PAIRS:
        for mm in (1.0, MEGA_BONUS[3]):
            got = damage_vec_of(atks, mtype, atypes, dtypes, mm)
            want = np.array([damage(80, float(a), 130.0, mtype, atypes,
                                    dtypes, mm) for a in atks])
            assert np.array_equal(got, want)


def damage_vec_of(atks, mtype, atypes, dtypes, mm):
    return damage_vec(80, atks, 130.0, mtype, atypes, dtypes, mm)


def test_breakpoint_solver_round_trips_against_damage():
    """atk_for_damage must return a threshold that damage() agrees with.

    Before the shared constant this held only empirically (the solver used a
    different operand order from damage()); now it is structural. Checked on
    the mega path too, which is where PvPoke's own solvers are inconsistent
    with their own damage function.
    """
    n = 0
    for mtype, atypes, dtypes in TYPE_PAIRS:
        for power in POWERS:
            for lvl in (None, 4):
                move = {'power': power, 'type': mtype,
                        'isMegaMove': lvl is not None}
                mm = mega_multiplier(move, lvl)
                if damage_constant(power, mtype, atypes, dtypes, mm) == 0:
                    continue
                for target in (2, 5, 13, 40):
                    thr = atk_for_damage(target, 130.0, move, atypes,
                                         dtypes, lvl)
                    # Probe just above / just below rather than AT the
                    # threshold: with the float32-truncated constants K is
                    # not a round number, so (D-1)*def/K does not round-trip
                    # exactly through floor(K*atk/def). Same convention as
                    # tests/test_breakpoints.py::test_atk_for_damage_consistency.
                    assert damage(power, thr * 1.001, 130.0, mtype, atypes,
                                  dtypes, mm) == target
                    assert damage(power, thr * 0.999, 130.0, mtype, atypes,
                                  dtypes, mm) < target
                    n += 1
    assert n >= 100, f'scanner degenerate: only {n} cases'


def test_bulkpoint_solver_round_trips_against_damage():
    n = 0
    for mtype, atypes, dtypes in TYPE_PAIRS:
        for power in POWERS:
            for lvl in (None, 4):
                move = {'power': power, 'type': mtype,
                        'isMegaMove': lvl is not None}
                mm = mega_multiplier(move, lvl)
                if damage_constant(power, mtype, atypes, dtypes, mm) == 0:
                    continue
                for target in (2, 5, 13, 40):
                    thr = def_for_damage(target, 150.0, move, atypes,
                                         dtypes, lvl)
                    if thr <= 0:
                        continue
                    # The bulkpoint threshold is EXCLUSIVE: at exactly thr
                    # damage is still target+1, just above it drops to
                    # target. Mirrors tests/test_breakpoints.py::
                    # test_def_for_damage_at_threshold_gives_target_damage.
                    assert damage(power, 150.0, thr * 1.001, mtype, atypes,
                                  dtypes, mm) == target
                    n += 1
    assert n >= 100, f'scanner degenerate: only {n} cases'


def test_K_is_the_shared_constant_not_a_copy():
    """breakpoints._K must BE moves.damage_constant, by identity.

    Identity rather than a value comparison per the testing policy: a value
    check would pass against a re-spelled copy that happens to agree today.
    """
    assert _K is damage_constant


def test_mega_bonus_constants_are_the_float32_expansions():
    """PvPoke DamageCalculator.js:10, ported as exact float32 expansions.

    Writing 1.1/1.2/1.3 instead is the bug class DEVELOPER_NOTES "Engine
    constant sourcing" documents. Indices 2 and 3 coincide exactly with the
    STAB and BONUS constants we already carry, which is the cross-check that
    the expansions are right.
    """
    assert MEGA_BONUS == (
        1.0,
        1.10000002384185791015625,
        1.2000000476837158203125,
        1.2999999523162841796875,
    )
    assert MEGA_BONUS[3] == BONUS
    assert MEGA_BONUS[2] != 1.2, 'must not be the naive decimal'
    assert MEGA_BONUS[1] != 1.1, 'must not be the naive decimal'


def test_mega_multiplier_is_gated_on_both_tag_and_move():
    """hasTag("mega") AND move.isMegaMove -- both halves, per PvPoke."""
    plus = {'moveId': 'OUTRAGE_PLUS', 'isMegaMove': True}
    plain = {'moveId': 'OUTRAGE'}
    assert mega_multiplier(plus, 4) == MEGA_BONUS[3]
    assert mega_multiplier(plus, 3) == MEGA_BONUS[2]
    # a mega throwing an ordinary move gets nothing
    assert mega_multiplier(plain, 4) == 1.0
    # a non-mega can never get the bonus, even on a *_PLUS move
    assert mega_multiplier(plus, None) == 1.0
    assert mega_multiplier(plain, None) == 1.0


def test_mega_multiplier_rejects_an_out_of_range_level():
    """PvPoke indexes unguarded and yields NaN; we raise instead."""
    plus = {'moveId': 'OUTRAGE_PLUS', 'isMegaMove': True}
    for bad in (0, 5, -1):
        with pytest.raises(ValueError):
            mega_multiplier(plus, bad)


def test_mega_level_derives_from_tags_only():
    """4 for supermega, 3 for a plain mega, None otherwise."""
    assert mega_level_from_tags(['mega', 'supermega']) == 4
    assert mega_level_from_tags(['mega']) == 3
    assert mega_level_from_tags(['shadoweligible']) is None
    assert mega_level_from_tags(None) is None
    # extraChargedMoves is NOT a mega proxy -- Cramorant carries it too
    assert mega_level_from_tags([]) is None


def test_the_gamemaster_roster_matches_the_tag_rule():
    """Floor-style census, so a roster change is visible but not brittle.

    Counts are floors set below today's values (61 mega / 13 supermega / 13
    isMegaMove as of pvpoke 56bc6a8b1); Bulbapedia lists more Super Max
    species landing 2026-09-08, so an == here would fail on a data refresh
    that is not a bug.
    """
    from gopvpsim.data import load_gamemaster
    gm = load_gamemaster()
    megas = [p for p in gm['pokemon'] if 'mega' in (p.get('tags') or [])]
    supers = [p for p in megas if 'supermega' in p['tags']]
    mega_moves = [m for m in gm['moves'] if m.get('isMegaMove')]

    assert len(megas) >= 55, len(megas)
    assert len(supers) >= 13, len(supers)
    assert len(mega_moves) >= 13, len(mega_moves)

    # Every supermega is a mega, and carries exactly one extra charged move.
    for p in supers:
        assert mega_level_from_tags(p['tags']) == 4
        assert len(p.get('extraChargedMoves') or []) == 1, p['speciesId']
        assert p['extraChargedMoves'][0].endswith('_PLUS'), p['speciesId']

    # Positive control: the mega roster is not silently empty and the
    # supermega set is a strict subset.
    assert supers, 'no supermega species found -- tag rule may have changed'
    assert len(supers) < len(megas)


def test_only_supermegas_hold_mega_moves():
    """A plain mega has no *_PLUS move, so MEGA_BONUS[2] never fires today.

    Recorded as an observation, not a rule PvPoke states: it means every
    capturable oracle sits at level 4, so a 4-element table cannot be
    distinguished from a scalar 1.3 by fixtures alone. That is why
    test_mega_bonus_constants_are_the_float32_expansions pins all four.
    """
    from gopvpsim.data import load_gamemaster
    gm = load_gamemaster()
    mega_move_ids = {m['moveId'] for m in gm['moves'] if m.get('isMegaMove')}
    holders = [p for p in gm['pokemon']
               if mega_move_ids & set(p.get('extraChargedMoves') or [])]
    assert holders, 'positive control: nobody holds a mega move'
    for p in holders:
        assert 'supermega' in (p.get('tags') or []), p['speciesId']
