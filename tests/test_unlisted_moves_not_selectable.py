"""Moves the gamemaster flags ``unlisted`` are granted, never chosen.

Regression test for the crash that killed the 2026-09-10 website bake ~30
minutes in, on ``cramorant-great-league``::

    File "src/gopvpsim/battle.py", line 2959, in _ensure_dp_init_cache
        cm_dpe = [root_init[i] / cm_energy_l[i] for i in range(n)]
    ZeroDivisionError: division by zero

``get_legal_moves`` reads ``extraChargedMoves`` so that a mega's exclusive
``*_PLUS`` attack is selectable. That read also swept in Cramorant's two Gulp
Missiles, which are NOT selectable -- you do not pick Gulp Missile at the
moveset screen, the form change grants it when Dive or Surf triggers. They
carry ``energy: 0``, so the DP cache divided by zero the moment one landed in
an enumerated moveset.

Pre-fix values, recorded so this test fails without the fix:
  * ``get_legal_moves('Cramorant')[1]`` returned 6 ids (both Gulp Missiles).
  * ``enumerate_movesets('Cramorant')`` returned 42 combinations; 20 is the
    real count (2 fast x [C(4,2) pairs + 4 singles]).

The rebalance added ``unlisted: True`` to both Gulp Missiles, which is what
makes the filter expressible. It is a selectability flag, not a display one.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

from deep_dive import enumerate_movesets, get_legal_moves  # noqa: E402
from gopvpsim.moves import get_moves  # noqa: E402


def _charged_db():
    return get_moves()[1]


def test_gulp_missile_is_not_a_selectable_charged_move():
    """Pre-fix this list had 6 entries, including both Gulp Missiles."""
    charged = get_legal_moves('Cramorant')[1]
    assert charged == ['FLY', 'HYDRO_PUMP', 'SURF', 'DIVE']


def test_cramorant_enumerates_twenty_movesets_not_fortytwo():
    """2 fast x (6 pairs + 4 singles). Pre-fix: 42, from a 6-move pool."""
    assert len(enumerate_movesets('Cramorant')) == 20


def test_mega_exclusive_moves_survive_the_filter():
    """Positive control.

    The wrong fix is to stop reading ``extraChargedMoves`` at all, which would
    make this test fail: every mega-exclusive ``*_PLUS`` attack lives there and
    IS selectable. If this passes while the Cramorant tests pass, the filter is
    discriminating rather than blanket.
    """
    assert 'OUTRAGE_PLUS' in get_legal_moves('Dragonite (Mega)')[1]
    assert 'DYNAMIC_PUNCH_PLUS' in get_legal_moves('Mewtwo (Mega X)')[1]


def test_no_enumerated_charged_move_has_zero_energy():
    """The crash's root cause, stated directly, across every species.

    A zero-energy charged move in an enumerated moveset divides by zero in
    ``_ensure_dp_init_cache``. This is the durable guard: it fails for any
    future species that gains a granted-not-chosen move, not just Cramorant.
    """
    db = _charged_db()
    offenders = []
    for species in ('Cramorant', 'Cramorant (Gulping)', 'Cramorant (Gorging)',
                    'Ditto', 'Dragonite (Mega)'):
        for move_id in get_legal_moves(species)[1]:
            if not db.get(move_id, {}).get('energy'):
                offenders.append((species, move_id))
    assert offenders == []


def test_the_unlisted_flag_picks_out_exactly_the_granted_moves():
    """Scanner self-test: the filter would be vacuous if nothing were flagged.

    If a future gamemaster drops the flag, the filter silently stops filtering
    and the crash returns. Pin the set so that regresses loudly instead.
    """
    flagged = {m for m, d in _charged_db().items() if d.get('unlisted')}
    assert flagged == {'GULP_MISSILE_ARROKUDA', 'GULP_MISSILE_PIKACHU',
                       'TRANSFORM'}


def test_gulp_missile_still_fires_even_though_it_cannot_be_chosen():
    """Excluding it from SELECTION must not remove it from the FIGHT.

    Dive triggers the form change, and the changed form's ``formChange.moveId``
    grants Gulp Missile, which fires on its own. Without this test the fix
    could 'pass' by quietly deleting Cramorant's whole gimmick.
    """
    from deep_dive_lib.sweep import sim_score
    from gopvpsim.data import get_default_moveset

    opp_fast, opp_charged = get_default_moveset('Azumarill', 'great',
                                                shadow=False)
    # Dive as the only charged move, so the form change is forced.
    score = sim_score('Cramorant', 'PECK', ['DIVE'], 'great', 0, 0,
                      15, 15, 15, False,
                      'Azumarill', opp_fast, list(opp_charged),
                      mechanics='new')
    assert score > 0
