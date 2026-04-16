"""Tests for the charmer-class fast-move classifier.

Locks in the post-S5 S5a item 4 contract: the narrative renderer uses
``is_charmer_fast_move()`` to decide whether to prepend the
"charm-class fast moves favor stat product" framing sentence.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from fast_move_class import (  # noqa: E402
    CHARMER_FAST_MOVES,
    charmer_context_line,
    is_charmer_fast_move,
)


@pytest.mark.parametrize('name', [
    'CHARM',
    'RAZOR_LEAF',
    'WATERFALL',
    'DRAGON_BREATH',
    'FAIRY_WIND',
])
def test_charmer_moves_classified_correctly(name):
    assert is_charmer_fast_move(name)


@pytest.mark.parametrize('raw,pretty', [
    ('CHARM', 'Charm'),
    ('RAZOR_LEAF', 'Razor Leaf'),
    ('DRAGON_BREATH', 'Dragon Breath'),
    ('FAIRY_WIND', 'Fairy Wind'),
])
def test_pretty_names_classified_the_same(raw, pretty):
    assert is_charmer_fast_move(raw) == is_charmer_fast_move(pretty) is True


@pytest.mark.parametrize('name', [
    'MUD_SLAP',
    'TACKLE',
    'COUNTER',
    'INCINERATE',
    'POWDER_SNOW',
    '',
    None,
])
def test_non_charmer_moves_rejected(name):
    assert not is_charmer_fast_move(name)


def test_charmer_context_line_includes_species():
    line = charmer_context_line('Altaria')
    assert 'Altaria' in line
    # No em-dashes per feedback_no_em_dashes
    assert '\u2014' not in line
    # Must say something about stat product > breakpoint tradeoff
    assert 'stat product' in line.lower()


def test_charmer_set_is_non_empty():
    assert len(CHARMER_FAST_MOVES) >= 4
