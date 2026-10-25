"""``--no-single-charged`` drops the one-charged-move candidates (2026-10-25).

Minior (Core) has three legal charged moves, so with Rollout pinned the
default enumeration is three pairs plus three singles; the flag keeps the
pairs only. Michael did not want the one-move pages on the Minior UL dives.
Pre-fix value: ``enumerate_movesets`` had no such knob and returned 6.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from deep_dive import enumerate_movesets  # noqa: E402


def test_default_keeps_singles():
    ms = enumerate_movesets('Minior (Core)', user_fast='ROLLOUT')
    assert len(ms) == 6
    assert sum(1 for _, ch in ms if len(ch) == 1) == 3


def test_flag_drops_singles_only():
    ms = enumerate_movesets('Minior (Core)', user_fast='ROLLOUT',
                            no_single_charged=True)
    assert len(ms) == 3
    assert all(len(ch) == 2 for _, ch in ms)
    pairs = {tuple(ch) for _, ch in ms}
    assert pairs == {('ACROBATICS', 'ANCIENT_POWER'),
                     ('ACROBATICS', 'POWER_GEM'),
                     ('ANCIENT_POWER', 'POWER_GEM')}


def test_flag_is_inert_with_explicit_charged():
    # --charged given: the flag has nothing to drop.
    a = enumerate_movesets('Minior (Core)', user_fast='ROLLOUT',
                           user_charged=['POWER_GEM'])
    b = enumerate_movesets('Minior (Core)', user_fast='ROLLOUT',
                           user_charged=['POWER_GEM'], no_single_charged=True)
    assert a == b and len(a) == 2
