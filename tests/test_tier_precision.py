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
from tests.conftest import load_deep_dive

deep_dive = load_deep_dive()

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


# ---------------------------------------------------------------------------
# D14 (DRY review 2026-08-05 entry 12): ONE meets-rule, two thin wrappers.
# The two classifiers used to carry hand-copied >= chains; these pin that
# they cannot drift apart again.
# ---------------------------------------------------------------------------

D14_THRESHOLDS = {
    'sharp': {'attack': 120.0, 'defense': 103.0, 'stamina': 140},
    'atk_only': {'attack': 118.5, 'defense': 0, 'stamina': 0},
    'hp_only': {'attack': 0, 'defense': 0, 'stamina': 145},
}


def _grid():
    """Spreads straddling every cutoff, including exact-equality rows."""
    for atk in (118.4999, 118.5, 120.0, 121.0):
        for dfn in (102.9982, 103.0, 104.0):
            for hp in (139, 140, 145, 146):
                yield atk, dfn, hp


def test_two_classifiers_agree_across_a_boundary_grid():
    for atk, dfn, hp in _grid():
        indices = deep_dive.classify_tier_indices(atk, dfn, hp,
                                                  D14_THRESHOLDS)
        name = deep_dive.classify_iv({'atk': atk, 'def_': dfn, 'hp': hp},
                                     D14_THRESHOLDS)
        expected = list(D14_THRESHOLDS)[indices[0]] if indices else None
        assert name == expected, (atk, dfn, hp, indices, name)


def test_both_wrappers_route_through_the_one_rule(monkeypatch):
    """Swap the rule; BOTH classifiers must change. A wrapper that kept its
    own inline >= chain would keep answering the old way."""
    monkeypatch.setattr(deep_dive, 'meets_threshold',
                        lambda thresh, atk, dfn, hp: False)
    assert deep_dive.classify_tier_indices(999, 999, 999, D14_THRESHOLDS) == []
    assert deep_dive.classify_iv({'atk': 999, 'def_': 999, 'hp': 999},
                                 D14_THRESHOLDS) is None


def test_zero_requirements_always_pass():
    # A zero cutoff means "unset", not "must be >= 0" -- pin it on the rule
    # itself, since both wrappers now inherit the behavior from one place.
    thresh = {'attack': 0, 'defense': 0, 'stamina': 0}
    assert deep_dive.meets_threshold(thresh, 0, 0, 0) is True


def test_no_hand_rolled_meets_chains_survive():
    """Anti-re-fork guard (D14 adversarial verify, 2026-08-06): the
    threshold meets-idiom may exist exactly once -- inside
    meets_threshold itself. A third hand-copied chain survived the
    first unification (the L51 _level_meta_arrays path, still on
    rounded stats); this scan fails if any copy ever comes back."""
    import re
    from pathlib import Path
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    idiom = re.compile(r"\['attack'\]\s*>\s*0\s+and")
    hits = []
    for path in sorted(list(scripts.glob('*.py')) +
                       list((scripts / 'deep_dive_lib').glob('*.py'))):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if idiom.search(line):
                hits.append(f'{path.name}:{n}')
    # Exactly ONE instance, inside meets_threshold's own body (line
    # number left unpinned -- edits above it move the line).
    assert len(hits) == 1 and hits[0].startswith('deep_dive.py:'), hits
