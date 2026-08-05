"""Opponent-color hash parity: narrative vs rendering (DRY review 2026-08-05).

Both modules hash the opponent name into the shared --opp-1..--opp-12
palette so one opponent reads as one hue everywhere on a dive page.
deep_dive_rendering._opp_color hashes name.lower(); the narrative copy
originally hashed the raw name, so any capitalized name (i.e. all of
them) could land on a different hue in prose than in tables — shipped
example: Altaria was --opp-3 in tables and --opp-10 in narrative on
the Azumarill GL page. This pins the two paths to each other.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from deep_dive_narrative import _opp_colored  # noqa: E402
from deep_dive_rendering import _opp_color  # noqa: E402

NAMES = [
    'Altaria',
    'Altaria (Shadow)',
    'Azumarill',
    'Galarian Corsola',
    'Oinkologne (Female)',
    'Ninetales (Alolan) (Shadow)',
    'registeel',  # already-lower input must agree too
]


def _span_color(html):
    m = re.search(r'color:(var\(--opp-\d+\))', html)
    assert m, f'no palette color in {html!r}'
    return m.group(1)


def test_narrative_and_rendering_agree_on_every_name():
    for name in NAMES:
        assert _span_color(_opp_colored(name)) == _opp_color(name), name


def test_case_insensitive_within_narrative():
    # The rename convention means the same opponent can arrive cased
    # differently; hue must not depend on it.
    assert _span_color(_opp_colored('Altaria')) == _span_color(_opp_colored('ALTARIA'))
