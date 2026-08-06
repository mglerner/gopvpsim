"""One shield-scenario vocabulary, and the flip-number cross-label.

DRY review 2026-08-05 entry 12 (register item R11 + mc-single-stat-flip).

R11 half -- the dive page used to spell one shield scenario two ways
because ~a dozen renderers each re-formed ``f'{s[0]}v{s[1]}'`` inline.
Entry 5 landed the canonical helper (``deep_dive_rendering.scenario_label``)
and baked its output as ``DATA.scenarioLabels``; this file pins that the
inline copies do not come back, in the four Python renderers that print
scenarios (deep_dive.py, deep_dive_rendering.py, deep_dive_lib/categories.py,
deep_dive_matchup_clusters.py).

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

# Every Python file that renders a shield scenario onto the dive page.
LABEL_RENDERERS = [
    'scripts/deep_dive.py',
    'scripts/deep_dive_rendering.py',
    'scripts/deep_dive_lib/categories.py',
    'scripts/deep_dive_matchup_clusters.py',
]

# An inline re-forming of the label from the tuple, e.g. f'{s[0]}v{s[1]}',
# f'{scen[0]}v{scen[1]}', f'{shield_scenarios[0][0]}v{shield_scenarios[0][1]}'.
_REFORMED = re.compile(r'\{[^{}]*\[0\]\}v\{[^{}]*\[1\]\}')


# ---------------------------------------------------------------------------
# R11: one vocabulary
# ---------------------------------------------------------------------------

def test_scenario_label_is_the_0v0_family():
    assert rendering.scenario_label((0, 0)) == '0v0'
    assert rendering.scenario_label((1, 1)) == '1v1'
    assert rendering.scenario_label([2, 1]) == '2v1'


def test_no_renderer_re_forms_the_label_inline():
    """The helper itself is the only place the '{a}v{b}' form is written."""
    offenders = []
    for rel in LABEL_RENDERERS:
        src = (REPO_ROOT / rel).read_text()
        for i, line in enumerate(src.splitlines(), 1):
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
