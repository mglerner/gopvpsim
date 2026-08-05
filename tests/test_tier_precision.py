"""Tier classification must use unrounded stats (DRY review 2026-08-05, js-parity-1).

The dive bake used to classify tier membership on the 2dp
display-rounded ivAtk/ivDef arrays while the shipped page's paste-box
scanner recomputes the user's stats at full precision. A spread whose
true stat sits just under a threshold but rounds up to it was colored
as a tier member the page itself then rejects — shipped repro:
Annihilape 0/9/14, def 102.9982 vs the 103.0 threshold.

classify_tier_indices is the extracted, unrounded classifier; these
tests pin the boundary behavior and its agreement with classify_iv.
"""
import importlib.util
import os
import sys

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, '..', 'scripts'))

DEEP_DIVE_PATH = os.path.join(_HERE, '..', 'scripts', 'deep_dive.py')
_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deep_dive)

THRESHOLDS = {
    'squag_def': {'attack': 0, 'defense': 103.0, 'stamina': 0},
    'bulk_floor': {'attack': 0, 'defense': 100.0, 'stamina': 140},
}


def test_just_under_threshold_is_rejected_even_though_it_rounds_up():
    # def 102.9982 displays as 103.0 but must NOT classify (Annihilape repro).
    assert deep_dive.classify_tier_indices(115.0, 102.9982, 145, THRESHOLDS) == [1]


def test_exactly_at_threshold_is_accepted():
    assert deep_dive.classify_tier_indices(115.0, 103.0, 145, THRESHOLDS) == [0, 1]


def test_rounding_would_have_flipped_the_verdict():
    # The old code compared round(dfn, 2); prove that path gives the
    # wrong answer for the repro value, so a regression reintroducing
    # rounded inputs fails this file.
    dfn = 102.9982
    assert round(dfn, 2) >= THRESHOLDS['squag_def']['defense']  # old path: passes
    assert deep_dive.classify_tier_indices(0, dfn, 0, THRESHOLDS) == []  # truth: fails


def test_agrees_with_classify_iv_naming_rule():
    # classify_iv returns the first (most restrictive) matching NAME;
    # classify_tier_indices' first index must point at the same entry.
    result = {'atk': 115.0, 'def_': 104.2, 'hp': 145}
    name = deep_dive.classify_iv(result, THRESHOLDS)
    indices = deep_dive.classify_tier_indices(
        result['atk'], result['def_'], result['hp'], THRESHOLDS)
    assert list(THRESHOLDS)[indices[0]] == name
