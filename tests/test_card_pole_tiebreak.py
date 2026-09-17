"""The card's three stat-extreme POLES are retired; this pins the retirement.

History. The card used to headline three poles -- a balanced lead (battle-score
#1), an attack pole (max effective attack) and a bulk pole (max effective
defense) -- selected in ``deep_dive_lib/render.py`` and labelled by a style
taxonomy ("Attack Weight", "High Defense", "High HP", "Matchup Hunter",
"Generalist", "Balanced", "Bait Robust", "Max Bulk"). This file guarded the
2026-06-24 UL Mimikyu bug in the two pole-selection keys: a below-cap species
ties ``0/15/15`` and ``1/15/15`` on def+hp at max level, and keys maxed on
``(coverage, def, hp)`` / ``(coverage, hp, def)`` with no attack tie-break
returned the FIRST maximal index -- the lower-atk, strictly-dominated spread.
The fix (810f53c) appended ``data_obj['ivAtk'][iv]``; the two source tripwires
here asserted exactly that:

    assert _pole_key_last_element("atk_iv") == "data_obj['ivAtk'][iv]"
    assert _pole_key_last_element("bulk_iv") == "data_obj['ivAtk'][iv]"

On 2026-09-17 the poles were retired page-wide (round 5, item 1): the card, the
scatter's "Spec Card Spreads" overlay and the opponent-threat chips are all fed
by the "Which one to build?" builds instead, so the selection those tie-breaks
guarded no longer exists and neither does the taxonomy that named it. A pole
that came back would silently re-open the Mimikyu bug (its tie-break lives
nowhere now), so the absence is pinned here rather than the file deleted.

Each absence pin carries a positive control: the scan reads the module that
really does select the card's spreads, so a moved or renamed helper fails here
instead of making the absence vacuous.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_RENDER = REPO_ROOT / "scripts" / "deep_dive_lib" / "render.py"
_RENDERING = REPO_ROOT / "scripts" / "deep_dive_rendering.py"

# The retired style vocabulary. "Balanced" and "Generalist" are ordinary
# English and appear in unrelated prose, so the pin is on the assignment form
# the classifier used, not on the bare word.
_RETIRED_STYLES = ('Attack Weight', 'High Defense', 'High HP',
                   'Matchup Hunter', 'Max Bulk', 'Bait Robust')


def test_the_pole_selection_is_gone_from_the_card_path():
    """Neither pole key survives in the module that picks the card's spreads."""
    text = _RENDER.read_text()
    assert not re.search(r"\batk_iv\b", text), 'the attack pole is back'
    assert not re.search(r"\bbulk_iv\b", text), 'the bulk pole is back'
    assert not re.search(r"max\(range\(nIvs\),\s*key=lambda iv:", text), \
        'a stat-extreme max() over the whole grid is back'
    # positive control: this IS the module that selects the card's spreads
    assert "data_obj['recIvs'] = [rc['iv'] for rc in chosen_recs]" in text
    assert "for _spec in (card_builds or []):" in text


def test_the_style_taxonomy_is_gone_from_both_renderers():
    """No renderer assigns or prints a pole style name any more."""
    for path in (_RENDER, _RENDERING):
        text = path.read_text()
        for style in _RETIRED_STYLES:
            assert f"'{style}'" not in text, (path.name, style)
    # the renderer that PRINTED the style no longer reads the field at all
    assert "rc['style']" not in _RENDERING.read_text()
    render = _RENDER.read_text()
    # render.py still SETS a style -- it is the card's own title now, either
    # the build's ("Build 1: ...") or the fallback's ("Top pick #N").
    assert "_rc['style'] = _spec['title']" in render
    assert 'rc[\'style\'] = f"Top pick #{len(chosen_recs) + 1}"' in render
    # positive control: the card model still reads the field
    card = (REPO_ROOT / 'scripts' / 'deep_dive_card.py').read_text()
    assert "style=rc.get('style', '')" in card


def test_the_chips_read_the_card_names_not_the_retired_styles():
    """``recStyles`` (the pole labels) is gone; ``recNames`` replaces it.

    Pinned on the two CODE forms, not the bare word: both modules still
    mention the retired key in a comment saying what replaced it.
    """
    assert "data_obj['recStyles']" not in _RENDER.read_text()
    assert "get('recStyles')" not in _RENDERING.read_text()
    assert "data_obj['recNames'] = list(chosen_names)" in _RENDER.read_text()
    assert "data_obj.get('recNames')" in _RENDERING.read_text()


# ---------------------------------------------------------------------------
# What replaced them: the three surfaces the poles used to feed, re-keyed to
# the dive card's own spreads.
# ---------------------------------------------------------------------------
import sys                                                        # noqa: E402

sys.path.insert(0, str(REPO_ROOT / 'scripts'))
sys.path.insert(0, str(REPO_ROOT / 'src'))

import deep_dive_rendering as rendering                           # noqa: E402

_SCENARIOS9 = [(a, b) for a in range(3) for b in range(3)]


def _threat_data_obj():
    """Four spreads; index 0 loses every shield vs the single opponent."""
    nIvs, nS, nO = 4, 9, 1
    scores = [800] * (nIvs * nS * nO)
    for si in range(nS):
        scores[0 * nS * nO + si * nO] = 200
    data_obj = {
        'ivA': [0, 5, 10, 15], 'ivD': [15] * 4, 'ivS': [15] * 4,
        'ivAtk': [100.0, 105.0, 110.0, 115.0],
        'ivDef': [100.0] * 4, 'ivHp': [135] * 4,
        'recIvs': [0, 3], 'recNames': ['Build 1', 'Most matchups won'],
    }
    return data_obj, scores, nS, nO


def test_threat_chips_carry_the_card_names_and_a_descriptive_hint():
    """Pre-fix the chips read the pole styles ("Matchup Hunter", "Max Bulk")
    and the hint read "-> build <style>". With the card's own names in the
    chips that hint would have read "build Build 1 or Build 2"."""
    data_obj, scores, nS, nO = _threat_data_obj()
    html = rendering.render_opponent_threats_section(
        [{'opponent': 'Medicham', 'stat': 'atk', 'threshold': 105.0,
          'hp_threshold': None, 'n_passing': 3,
          'scenarios': [(1, 1)], 'bait_modes': {'bait'}}],
        scores, _SCENARIOS9, ['Medicham'], nS, nO, data_obj, 'rank-1')
    assert 'Build 1' in html and 'Most matchups won' in html
    assert '&rarr; won by Most matchups won' in html
    assert '&rarr; build ' not in html
    assert 'one per build from "Which one to build?"' in html
    for style in _RETIRED_STYLES:
        assert style not in html


def test_the_best_buddy_threat_rows_say_their_builds_are_the_caps():
    """The L51 pass reuses the league-cap spreads, as the card does, and
    quotes the card's own pinned sentence rather than a second wording."""
    import deep_dive_card
    data_obj, scores, nS, nO = _threat_data_obj()
    args = ([], scores, _SCENARIOS9, ['Medicham'], nS, nO, data_obj, 'rank-1')
    plain = rendering.render_opponent_threats_section(*args)
    pinned = rendering.render_opponent_threats_section(*args,
                                                      builds_pinned=True)
    assert 'computed at the league cap' not in plain
    assert 'computed at the league cap' in pinned
    assert deep_dive_card.PINNED_NOTE.strip() in pinned.replace('&quot;', '"')


def _steal_data_obj(same=True):
    """Four spreads; the two recommended ones lose every matchup overall but
    steal individual shields (0v0 and 1v0; with ``same=False`` the second
    steals only 0v0)."""
    nIvs, nS, nO = 4, 9, 1
    scores = [200] * (nIvs * nS * nO)
    for iv in range(nIvs):
        for si in ((0, 3) if (same or iv == 0) else (0,)):
            scores[iv * nS * nO + si * nO] = 800
    data_obj = {
        'ivA': [0, 5, 10, 15], 'ivD': [15] * 4, 'ivS': [15] * 4,
        'ivAtk': [100.0, 105.0, 110.0, 115.0],
        'ivDef': [100.0] * 4, 'ivHp': [135] * 4,
        'recIvs': [0, 3], 'recNames': ['Build 1', 'Most matchups won'],
    }
    return data_obj, scores, nS, nO


def test_a_stealable_bullet_collapses_identical_shield_sets():
    """Pre-fix the bullet said the same thing once per spread -- "Altaria -
    Build 1 steals 1v0, 2v0, 2v1, 2v2; Build 2 steals 1v0, 2v0, 2v1, 2v2;
    Highest battle score steals ...; Most matchups won steals ..." -- and a
    standout's noun-phrase name read as a sentence fragment (2026-09-17 round
    6 review).
    """
    data_obj, scores, nS, nO = _steal_data_obj()
    html = rendering.render_opponent_threats_section(
        [], scores, _SCENARIOS9, ['Altaria'], nS, nO, data_obj, 'rank-1')
    assert 'Stealable' in html
    assert 'both spreads steal 0v0, 1v0' in html
    assert 'Most matchups won steals' not in html
    # and when they differ, each is named -- the standout with its article
    data_obj2, scores2, _nS, _nO = _steal_data_obj(same=False)
    html2 = rendering.render_opponent_threats_section(
        [], scores2, _SCENARIOS9, ['Altaria'], nS, nO, data_obj2, 'rank-1')
    assert 'Build 1 steals 0v0, 1v0' in html2
    assert 'the most matchups won spread steals 0v0' in html2
    assert 'both spreads steal' not in html2


def test_top_picks_are_labelled_by_build_membership_not_by_a_style():
    """Pre-fix: ``<h4 ...>Matchup Hunter: 7/2/12</h4>``. The picks are
    unchanged (top three by composite score); only the label moved to
    where each pick sits in the builds."""
    data_obj = {
        'ivA': [7, 8], 'ivD': [2, 7], 'ivS': [12, 5],
        'ivAtk': [149.2, 150.3], 'ivDef': [96.6, 97.2], 'ivHp': [125, 119],
        'spRanks': [913, 1103], 'ivTiers': [-1, -1],
    }
    recs = [{'iv': 0, 'avg_rank': 6, 'avg_score': 533.5, 'gains': 71,
             'losses': 4, 'net': 67, 'range': 300, 'score': 1.0},
            {'iv': 1, 'avg_rank': 9, 'avg_score': 533.0, 'gains': 60,
             'losses': 9, 'net': 51, 'range': 300, 'score': 0.5}]
    html = rendering._render_iv_recommendations(
        recs, {}, 'PvPoke default', data_obj, 0, 149.2, 96.6, {}, None, None,
        build_of={1: 'Build 1'})
    assert '>8/7/5 &mdash; in Build 1<' in html
    assert '>7/2/12 &mdash; in no build<' in html
    for style in _RETIRED_STYLES:
        assert style not in html
    # the two rankings are different questions, and the page says so where a
    # reader meets three picks labelled "in no build" (round 6 review)
    assert 'Top Picks rank single spreads by average score' in html
    assert 'the Standouts block there is the reconciliation' in html
    # a pick no BUILD holds but the wide region does is named, not "in no
    # build": the builds table names that same spread on the same page
    wide = rendering._render_iv_recommendations(
        recs, {}, 'PvPoke default', data_obj, 0, 149.2, 96.6, {}, None, None,
        build_of={0: 'Build 1 wide only', 1: 'Build 1'})
    assert '>7/2/12 &mdash; in Build 1 wide only<' in wide
    assert 'in no build' not in wide
    # with no builds on the page at all the cards say nothing about builds
    plain = rendering._render_iv_recommendations(
        recs, {}, 'PvPoke default', data_obj, 0, 149.2, 96.6, {}, None, None)
    assert 'in no build' not in plain and '>7/2/12<' in plain
