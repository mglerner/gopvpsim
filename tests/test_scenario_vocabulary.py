"""One shield-scenario vocabulary, and the flip-number cross-label.

DRY review 2026-08-05 entry 12 (register item R11 + mc-single-stat-flip).

R11 half -- the dive page used to spell one shield scenario two ways
because ~a dozen renderers each re-formed ``f'{s[0]}v{s[1]}'`` inline.
Entry 5 landed the canonical helper (``deep_dive_rendering.scenario_label``)
and baked its output as ``DATA.scenarioLabels``; this file pins that the
inline copies do not come back, in every Python renderer that prints
scenarios (see ``LABEL_RENDERERS``).

The AFK deferral churn 2026-08-08 added the last three files to that list:
``deep_dive_narrative.py`` (the IV Flavor Guide, which spoke a THIRD
spelling -- '1-1' -- until it was converted; a visible render change),
``generate_article.py`` and ``deep_dive_analysis.py`` (each carried one
more inline ``f'{a}v{b}'``).

Scope of that guard, stated exactly: it catches an *interpolated* re-forming
in either historical spelling -- subscripted ``f'{s[0]}v{s[1]}'`` and
destructured ``f'{s0}v{s1}'``. It does not catch bare literals ('0v0'), which
are fine as fixed keys, and it does not cover scripts/slayer_cache.py, whose
copy of the form is a cache-key ingredient rather than page text. See the
comments on ``_REFORMED`` below.

Cross-label half -- the page prints TWO different flip numbers for the same
opponent, from two engines that deliberately stay separate:

  * ``analysis.find_matchup_boundaries`` -> "flips at Def >= X" (lowest
    CLEAN 75/25 cutoff; a build target)
  * ``matchup_clusters.single_stat_flip`` -> the clusters section's best
    single-stat rule (most ACCURATE predictor; a diagnostic)

The rules are NOT merged (the review says so explicitly). Instead each
surface names the other, from one pair of constants; these tests pin that
both labels are rendered and that neither loses its cross-reference.
"""
import importlib.util
import re
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / 'scripts'

for _p in (REPO_ROOT / 'src', SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


rendering = _load('deep_dive_rendering_vocab',
                  'scripts/deep_dive_rendering.py')
mc = _load('deep_dive_matchup_clusters_vocab',
           'scripts/deep_dive_matchup_clusters.py')

# Every Python file that renders a shield scenario onto the dive page or the
# CD article. deep_dive_analysis.py is in the list because find_flips' entry
# 'scenario' string is printed verbatim by the renderers -- it is page text,
# not an internal key.
LABEL_RENDERERS = [
    'scripts/deep_dive.py',
    'scripts/deep_dive_rendering.py',
    'scripts/deep_dive_lib/categories.py',
    'scripts/deep_dive_matchup_clusters.py',
    'scripts/deep_dive_analysis.py',
    'scripts/deep_dive_narrative.py',
    'scripts/generate_article.py',
]

# An inline re-forming of the label from the tuple. BOTH historical spellings
# have to match, because the pre-entry-12 code used both:
#   subscripted  -- f'{s[0]}v{s[1]}', f'{shield_scenarios[0][0]}v{...[1]}'
#   destructured -- f'{s0}v{s1}' (after `for s0, s1 in shield_scenarios`)
# A pattern pinned to the subscripted form only is blind to a literal revert of
# the destructured sites, which is how this guard first shipped toothless.
_REFORMED = re.compile(r'\{[^{}]*\}v\{[^{}]*\}')

# What this pattern does NOT cover, on purpose: bare string literals ('0v0',
# "1v1"). Those are legitimate as fixed lookup keys / defaults and are also
# quoted in prose and docstrings, so pinning them is noise. The drift R11
# actually fixed was the interpolated form, and that is what is pinned here.
#
# Also deliberately out of LABEL_RENDERERS: scripts/slayer_cache.py:113 still
# builds f'{s0}v{s1}' -- but that string is md5'd into a cache key, not
# rendered onto the page. Its text is frozen by the cache, not by the page
# vocabulary; rewriting it through the helper would silently invalidate every
# cached slayer entry for no rendered benefit.


# ---------------------------------------------------------------------------
# R11: one vocabulary
# ---------------------------------------------------------------------------

def test_scenario_label_is_the_0v0_family():
    assert rendering.scenario_label((0, 0)) == '0v0'
    assert rendering.scenario_label((1, 1)) == '1v1'
    assert rendering.scenario_label([2, 1]) == '2v1'


# The historical inline constructions entry 12 removed, verbatim from the
# commit's deleted lines -- both spellings. The scan pattern must catch every
# one of them, or a straight revert of that hunk lands green.
_REMOVED_INLINE_SITES = [
    "    shield_desc = ', '.join(f'{s0}v{s1}' for s0, s1 in shield_scenarios)",
    '''            html += f'    <option value="{si}"{sel}>{s0}v{s1}</option>' ''',
    "    shield_desc_default = f'{shield_scenarios[0][0]}v"
    "{shield_scenarios[0][1]}'",
    "                    scen_label = f'{scen[0]}v{scen[1]}'",
    '        label = f"{pair[0]}v{pair[1]}"',
    '''        parts.append(f'<th title="Rank out of {nIvs} IVs in the '''
    '''{s0}v{s1} shield scenario (1 = best)">{s0}v{s1}</th>')''',
    "        return [f'{scenarios[si][0]}v{scenarios[si][1]}'",
    """        cells = [f'<td class="dd-sg-row">{scen[0]}v{scen[1]}</td>']""",
    "            f'{s[0]}v{s[1]}' for s in sorted(b['scenarios']))",
]


def test_scan_pattern_catches_both_historical_spellings():
    """Guard the guard: the scan below is only worth anything if it matches
    the destructured f'{s0}v{s1}' form as well as the subscripted one. Three
    of the sites entry 12 removed used the destructured spelling."""
    missed = [s for s in _REMOVED_INLINE_SITES if not _REFORMED.search(s)]
    assert missed == [], missed
    # both spellings, minimally
    assert _REFORMED.search("f'{s0}v{s1}'")
    assert _REFORMED.search("f'{s[0]}v{s[1]}'")
    # and it does not fire on unrelated adjacent interpolation
    assert not _REFORMED.search("f'{a}-{b}'")
    assert not _REFORMED.search("f'{shields} vs {opp}'")


def test_no_renderer_re_forms_the_label_inline():
    """The helper itself is the only place the '{a}v{b}' form is written.

    Comment lines are skipped -- a comment quoting the format (deep_dive.py
    documents what it bakes into DATA.scenarioLabels) renders nothing.
    """
    offenders = []
    for rel in LABEL_RENDERERS:
        src = (REPO_ROOT / rel).read_text()
        for i, line in enumerate(src.splitlines(), 1):
            if line.strip().startswith('#'):
                continue
            if _REFORMED.search(line):
                offenders.append(f'{rel}:{i}: {line.strip()}')
    # deep_dive_rendering.scenario_label's own body is the single exception.
    assert offenders == [
        "scripts/deep_dive_rendering.py:%d: return f'{scenario[0]}v"
        "{scenario[1]}'" % _helper_line()
    ], offenders


def _helper_line():
    src = (SCRIPTS / 'deep_dive_rendering.py').read_text().splitlines()
    for i, line in enumerate(src, 1):
        if line.strip() == "return f'{scenario[0]}v{scenario[1]}'":
            return i
    raise AssertionError('scenario_label body not found')


def test_scenario_label_has_exactly_one_definition():
    hits = [rel for rel in LABEL_RENDERERS
            if 'def scenario_label(' in (REPO_ROOT / rel).read_text()]
    assert hits == ['scripts/deep_dive_rendering.py']


def test_clusters_module_imports_the_helper():
    """The clusters payload keys are the load-bearing copy: the JS overlay
    looks each one up in DATA.scenarioLabels and renders neutral points
    (silently) when it misses."""
    assert mc.scenario_label is rendering.scenario_label or (
        mc.scenario_label((1, 1)) == rendering.scenario_label((1, 1)))
    assert mc.EVEN_SHIELD_PAIRS == ((0, 0), (1, 1), (2, 2))


# ---------------------------------------------------------------------------
# The Flavor Guide's third spelling (AFK deferral churn 2026-08-08)
# ---------------------------------------------------------------------------
#
# deep_dive_narrative.py printed '1-1' where the rest of the page printed
# '1v1' -- a VISIBLE difference, so converting it is a render change, not a
# refactor. The dash form is pinned dead here in its exact old spelling; the
# generic _REFORMED scan above cannot do it (it only knows the 'v' form) and
# a generic dash regex would false-positive on the legitimate '{k50}-{k75}'
# catch-count range a few lines away.

_DASH_FORM = re.compile(r"\{s\[0\]\}-\{s\[1\]\}")


def test_flavor_guide_dash_spelling_is_gone():
    src = (SCRIPTS / 'deep_dive_narrative.py').read_text()
    offenders = [f'{i}: {line.strip()}'
                 for i, line in enumerate(src.splitlines(), 1)
                 if not line.strip().startswith('#') and _DASH_FORM.search(line)]
    assert offenders == [], offenders
    # Guard the guard: the pattern really did match the removed sites.
    assert _DASH_FORM.search("scen_str = ', '.join(f'{s[0]}-{s[1]}' for s in x)")


def test_flavor_guide_prose_speaks_the_shared_vocabulary():
    import deep_dive_narrative as narrative

    assert narrative._scenario_str([(1, 1), (0, 2)]) == '0v2, 1v1'
    assert narrative._scenario_str([(1, 1)]) == rendering.scenario_label((1, 1))
    prose = narrative._gain_prose([{'opponent': 'Azumarill',
                                    'scenarios': [(1, 1)]}])
    assert prose == 'pick up the Azumarill 1v1'


def test_flip_entries_carry_the_shared_label():
    """analysis.find_flips' 'scenario' string is printed verbatim by the
    renderers (opponent-threats table, flip lists), so it is page text."""
    import deep_dive_analysis as analysis

    scenarios = [(0, 0), (1, 1)]
    nIvs, nS, nO = 2, len(scenarios), 1
    # IV 0 loses 1v1, IV 1 wins it; 0v0 is a win for both (no flip).
    scores = [800, 200,      # ref IV: 0v0 win, 1v1 loss
              800, 800]      # test IV: both wins
    flips = analysis.find_flips(scores, nIvs, nS, nO, 0, [1], scenarios,
                                ['Azumarill'])
    assert [g['scenario'] for g in flips[1]['gains']] == ['1v1']
    assert flips[1]['losses'] == []


# ---------------------------------------------------------------------------
# Rendered-output half: the labels the section actually emits
# ---------------------------------------------------------------------------

SCENARIOS9 = [(a, b) for a in range(3) for b in range(3)]
OPP_NAMES = ['Azumarill', 'Medicham', 'Registeel']


def _render_clusters():
    nIvs, nO = 100, len(OPP_NAMES)
    arr = np.full((nIvs, 9, nO), 200, dtype=np.int32)
    for si in (0, 4, 8):                       # 0v0, 1v1, 2v2
        arr[50:, si, :] = 800
        arr[:50, si, 0] = 800
    atk = np.linspace(100, 110, nIvs)
    data_obj = {'ivAtk': atk.tolist(), 'ivDef': atk.tolist(),
                'ivHp': np.full(nIvs, 135.0).tolist()}
    return mc.render_section(
        arr.ravel().tolist(), nIvs, 9, nO, SCENARIOS9, OPP_NAMES, data_obj,
        'rank-1', 'FAIRY_WIND / PLAY_ROUGH, ICE_BEAM', [])


def test_rendered_scenario_blocks_use_the_canonical_labels():
    html = _render_clusters()
    got = set(re.findall(r'data-scen="([^"]+)"', html))
    assert got == {'0v0', '1v1', '2v2'}
    # and the selector options agree with the blocks
    assert set(re.findall(r'<option value="([^"]+)"', html)) == got


# ---------------------------------------------------------------------------
# mc-single-stat-flip: the two flip numbers are cross-labeled
# ---------------------------------------------------------------------------

def test_the_two_flip_definitions_live_in_one_place():
    """Both tips are defined next to each other in deep_dive_rendering; the
    clusters module imports its half rather than restating it."""
    assert 'clean' in rendering.BOUNDARY_RULE_TIP
    assert 'build target' in rendering.BOUNDARY_RULE_TIP
    assert 'predicts' in rendering.BEST_RULE_TIP
    assert mc.BEST_RULE_TIP == rendering.BEST_RULE_TIP
    # imported, never restated
    assert 'BEST_RULE_TIP =' not in (
        SCRIPTS / 'deep_dive_matchup_clusters.py').read_text()


def test_each_tip_names_the_other_surface():
    assert 'Matchup clusters' in rendering.BOUNDARY_RULE_TIP
    assert 'best single-stat rule' in rendering.BOUNDARY_RULE_TIP
    assert 'Threats where your build choice matters' in rendering.BEST_RULE_TIP
    assert 'flips at' in rendering.BEST_RULE_TIP


def test_clusters_flip_table_carries_the_best_rule_label():
    html = _render_clusters()
    # The collapsible keeps its guide-quoted name; the cross-label rides on
    # the note, the column header and its tooltip.
    assert 'Matchup flip thresholds (candidate anchors)' in html
    assert 'Best single-stat rule</th>' in html
    # The tip renders twice per scenario block: as prose under the summary
    # and as the column tooltip. Three even-shield blocks here.
    head = rendering.BEST_RULE_TIP[:40]
    assert html.count(f'--text-muted)">{head}') == 3
    assert html.count(f'<th title="{head}') == 3


def test_threats_section_carries_the_boundary_label():
    """The reciprocal half, on the surface that prints the 75/25 cutoff."""
    nIvs, nS, nO = 4, 9, 1
    scores = [800] * (nIvs * nS * nO)
    for si in range(nS):                     # IV 0 loses everything
        scores[0 * nS * nO + si * nO] = 200
    data_obj = {
        'ivA': [0, 5, 10, 15], 'ivD': [15] * 4, 'ivS': [15] * 4,
        'ivAtk': [100.0, 105.0, 110.0, 115.0],
        'ivDef': [100.0] * 4, 'ivHp': [135] * 4,
        'recIvs': [0, 3], 'recStyles': ['bulk', 'atk'],
    }
    html = rendering.render_opponent_threats_section(
        [{'opponent': 'Medicham', 'stat': 'atk', 'threshold': 105.0,
          'hp_threshold': None, 'n_passing': 3,
          'scenarios': [(1, 1)], 'bait_modes': {'bait'}}],
        scores, SCENARIOS9, ['Medicham'], nS, nO, data_obj, 'rank-1')
    assert '<b>Flips at</b>' in html
    assert 'at least 75% of the IVs at or above it win' in html
    assert 'Matchup clusters section' in html
