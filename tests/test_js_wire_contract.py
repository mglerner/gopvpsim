"""Py<->JS wire-contract tripwires for the strings the dive bake emits and
the shipped page JS reads back (DRY review 2026-08-05 entry 5, plus the
engine half of entry 9).

Four contracts, all of which used to be hand-typed on both sides and all of
which fail SILENTLY when they drift:

1. **Scenario label** ``{a}v{b}`` -- keys the matchup-cluster payload's
   ``scens`` map. A divergent form does not error; the cluster overlay just
   renders neutral points. Now baked as ``DATA.scenarioLabels``.
2. **Moveset label** ``FAST / CM1, CM2`` -- the compare widget used to
   re-split the DISPLAY label to build pvpoke battle URLs. A parser drift
   yields a wrong-but-200 URL that no link checker can see. Now baked as
   ``DATA.movesets[i].fast`` / ``.charged``.
3. **Tier-card slug** -- three implementations (dive card renderer, page JS,
   article deep links) that converge on today's data. A divergence is a dead
   anchor / a missing "N of yours qualify" count. Now one Python helper, with
   the result baked as ``DATA.tiers[i].slug``.
4. **Level ceilings** -- the engine's bare 50 / 51 literals, now
   ``DATA.levelCaps`` from ``pokemon.bestbuddy_caps`` / ``MAX_CPM_LEVEL``
   with a pinned fallback table (the deliberate-fallback pattern of
   tests/test_js_shadow_constants.py).

Pattern mirrors tests/test_js_score_key_parity.py; the node halves skip if
node is absent.
"""
import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
_JS = _SCRIPTS / "deep_dive_engine.js"
_CMP_JS = _SCRIPTS / "cmp_panels.js"
_PY = _SCRIPTS / "deep_dive.py"
_CLUSTERS = _SCRIPTS / "deep_dive_matchup_clusters.py"
_ARTICLE = _SCRIPTS / "generate_article.py"

sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_ROOT / "src"))

# Plain imports, not spec_from_file_location: both modules must come from the
# ONE sys.modules entry so ``clusters.scenario_label is rendering.scenario_label``
# means "the same function object", not "two copies of the same file".
import deep_dive_matchup_clusters as clusters  # noqa: E402
import deep_dive_rendering as rendering  # noqa: E402

from gopvpsim.pokemon import MAX_CPM_LEVEL, bestbuddy_caps  # noqa: E402


def _js():
    return _JS.read_text()


def _dive_data(html):
    """The rendered page's ``DATA`` blob, as a dict.

    Located by the assignment and decoded with ``raw_decode`` (not a
    ``.*?};`` regex), so nothing here depends on how the bake formats the
    JSON.
    """
    m = re.search(r"\bDATA\s*=\s*\{", html)
    assert m, "the dive emitted no DATA blob"
    data, _ = json.JSONDecoder().raw_decode(html, m.end() - 1)
    return data


def _call_nodes(src, name):
    """Every ``name(...)`` call node in ``src``."""
    return [n for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == name]


def _calls_to(src, name):
    """Every ``name(...)`` call in ``src``, re-printed from the AST.

    ``ast.unparse`` normalizes wrapping, spacing and quote style away, so a
    reformat is not a contract change -- but a call whose ARGUMENTS changed
    shape still shows up.
    """
    return [ast.unparse(n) for n in _call_nodes(src, name)]


def _labels_a_loop_pair_via_helper(src):
    """``<name> = scenario_label(<loop var>)`` inside ``for <loop var> in ...``.

    This pins the PAYLOAD-KEY site specifically. "the module calls
    scenario_label somewhere" is not good enough: deep_dive_matchup_clusters
    has two further, purely-prose call sites, so a non-emptiness check stays
    true even if the payload key is re-formed inline. Both the loop variable
    and the assigned name are free (a rename is not a drift), but
    ``f'{pair[0]}v{pair[1]}'``, ``'%dv%d' % pair``, string concatenation and
    ``'v'.join(map(str, pair))`` all fail -- and three of those four slip past
    the interpolation-only regexes elsewhere in the suite.
    """
    for loop in ast.walk(ast.parse(src)):
        if not (isinstance(loop, ast.For) and isinstance(loop.target, ast.Name)):
            continue
        var = loop.target.id
        for n in ast.walk(loop):
            if not (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)):
                continue
            call = n.value
            if (isinstance(call.func, ast.Name)
                    and call.func.id == "scenario_label"
                    and len(call.args) == 1
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == var):
                return True
    return False


def _node(program):
    res = subprocess.run(["node", "-e", program], capture_output=True,
                         text=True, check=True)
    return json.loads(res.stdout)


def _js_fn(text, name):
    m = re.search(r"function %s\([^)]*\)\s*\{.*?\n\}" % name, text, re.S)
    assert m, f"{name} not found"
    return m.group(0)


# ---------------------------------------------------------------------------
# 1. Scenario label
# ---------------------------------------------------------------------------

def test_python_scenario_label_shape():
    assert rendering.scenario_label((1, 1)) == "1v1"
    assert rendering.scenario_label([0, 2]) == "0v2"


@pytest.mark.render
def test_bake_emits_scenario_labels(small_dive_html):
    """The SHIPPED page carries one canonical label per baked scenario.

    Asserted on the rendered DATA blob rather than on the comprehension in
    deep_dive.py that builds it: the source pin broke on a line wrap or a
    rename of ``shield_scenarios``, and could not see whether the entry ever
    reached the page.
    """
    data = _dive_data(small_dive_html)
    assert data.get("scenarios"), "fixture baked no scenarios"
    assert data.get("scenarioLabels") == [
        rendering.scenario_label(s) for s in data["scenarios"]]


def test_js_reads_the_baked_scenario_label():
    text = _js()
    assert len(re.findall(r"function scenLabel\(", text)) == 1
    assert "DATA.scenarioLabels" in _js_fn(text, "scenLabel")
    # No site outside scenLabel re-forms the label from the tuple.
    hits = [ln.strip() for ln in text.splitlines()
            if re.search(r"\+\s*'v'\s*\+", ln)]
    assert hits == ["return s[0] + 'v' + s[1];"], hits


def test_cluster_payload_uses_the_same_label_form():
    """The clusters module keys its payload with the SHARED helper (entry 12
    routed its last hand-typed f-string through it), so the JS overlay can
    never stop finding its scenario in DATA.scenarioLabels.

    Object identity, not the text of the import line: adding a third imported
    name, reordering, or isort-ing the module is not a contract change, while
    a local re-definition or an import of a second copy fails. The call-site
    half is AST-derived and aimed at the payload loop specifically (a rename of
    the loop variable or of ``label`` is not a drift, but hand-rolling the key
    from the tuple is); that the payload keys really come out in ``{a}v{b}``
    form is additionally asserted behaviorally, on a real render, at
    tests/test_scenario_vocabulary.py::test_rendered_scenario_blocks_use_the_canonical_labels
    -- though that test pins only the rendered strings, which every inline
    re-forming of the same shape would also produce, so it cannot stand in for
    the structural check below.
    """
    assert clusters.scenario_label is rendering.scenario_label
    text = _CLUSTERS.read_text()
    assert _labels_a_loop_pair_via_helper(text), (
        "the clusters payload loop no longer keys off the shared "
        "scenario_label helper")
    assert not re.search(r'f"\{pair\[0\]\}\w*\{pair\[1\]\}"', text), (
        "the clusters payload key is being re-formed from the tuple again")


def test_cmp_panels_prefers_the_baked_label_and_keeps_the_dash_fallback():
    """cmp_panels.js is shared with the ML IV guide, whose close-call records
    are keyed by iv_envelope_analysis.shield_label ('1-1'). The dash form
    MUST stay as the no-DATA.scenarioLabels fallback or ccLookup silently
    stops matching there."""
    text = _CMP_JS.read_text()
    body = _js_fn(text, "cmpScenLabel")
    assert "DATA.scenarioLabels" in body
    assert "s[0] + '-' + s[1]" in body


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_scen_label_prefers_data_in_node():
    program = _js_fn(_js(), "scenLabel") + """
var DATA = { scenarios: [[1,1],[0,2]], scenarioLabels: ['1v1', '0v2'] };
var out = [scenLabel(0), scenLabel(1)];
DATA.scenarioLabels = null;          // pre-field DATA blob
out.push(scenLabel(1));
console.log(JSON.stringify(out));
"""
    assert _node(program) == ["1v1", "0v2", "0v2"]


# ---------------------------------------------------------------------------
# 2. Moveset label
# ---------------------------------------------------------------------------

def test_python_parse_moveset_label():
    assert rendering.parse_moveset_label(
        "COUNTER / DYNAMIC_PUNCH, ICE_PUNCH") == (
            "COUNTER", ["DYNAMIC_PUNCH", "ICE_PUNCH"])
    assert rendering.parse_moveset_label("COUNTER / DYNAMIC_PUNCH") == (
        "COUNTER", ["DYNAMIC_PUNCH"])
    assert rendering.parse_moveset_label("COUNTER") == ("COUNTER", [])


def test_bake_emits_structured_moveset_fields():
    text = _PY.read_text()
    assert "'fast': parse_moveset_label(md['label'])[0]," in text
    assert "'charged': parse_moveset_label(md['label'])[1]," in text


def test_cmp_battle_url_does_not_split_the_display_label():
    text = _js()
    m = re.search(r"window\.cmpBattleUrl = function.*?\n\};", text, re.S)
    assert m, "cmpBattleUrl not found"
    body = m.group(0)
    assert "ms.fast" in body and "ms.charged" in body
    assert "lab.split" not in body, (
        "cmpBattleUrl is re-parsing the moveset DISPLAY label again; read "
        "DATA.movesets[i].fast/.charged instead")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_cmp_battle_url_builds_from_structured_fields_in_node():
    """Behavioral half: the URL's move segment must be FAST-CM1-CM2 taken
    from DATA.movesets[i].fast/.charged, and a moveset without two charged
    moves must still return null (the cell then renders unlinked)."""
    text = _js()
    m = re.search(r"window\.cmpBattleUrl = function.*?\n\};", text, re.S)
    program = "var window = {};\n" + _js_fn(text, "atL51View") + "\n" + m.group(0) + """
var state = { movesetIdx: 0, levelMode: '50', oppIvMode: 'pvpoke' };
var DATA = {
  cpCap: 1500, ivL51: null, ivLv: [21.5],
  focalLink: { id: 'tinkaton' },
  oppLinks: [{ id: 'azumarill', moves: 'BUBBLE-ICE_BEAM-PLAY_ROUGH',
               byMode: { pvpoke: { lvl: 40, ivs: [1, 15, 15] } } }],
  scenarios: [[1, 1]],
  movesets: [{ label: 'FAIRY_WIND / PLAY_ROUGH, FLASH_CANNON',
               fast: 'FAIRY_WIND',
               charged: ['PLAY_ROUGH', 'FLASH_CANNON'] },
             { label: 'FAIRY_WIND / PLAY_ROUGH',
               fast: 'FAIRY_WIND', charged: ['PLAY_ROUGH'] }]
};
var out = [window.cmpBattleUrl(0, 0, { a: 0, d: 15, s: 14, iv: 0 })];
state.movesetIdx = 1;   // only one charged move -> no link
out.push(window.cmpBattleUrl(0, 0, { a: 0, d: 15, s: 14, iv: 0 }));
console.log(JSON.stringify(out));
"""
    got = _node(program)
    assert got[0] == (
        'https://pvpoke.com/battle/1500/tinkaton-21.5-0-15-14-4-4-1-1/'
        'azumarill-40-1-15-15-4-4-1-1/11/'
        'FAIRY_WIND-PLAY_ROUGH-FLASH_CANNON/BUBBLE-ICE_BEAM-PLAY_ROUGH/')
    assert got[1] is None


def test_article_parser_delegates_to_the_shared_helper():
    text = _ARTICLE.read_text()
    assert "return parse_moveset_label(label)" in text
    assert "rest.split(',')" not in text


# ---------------------------------------------------------------------------
# 3. Tier-card slug
# ---------------------------------------------------------------------------

_TIER_NAMES = [
    "Lapras Atk",
    "Steelix (Shadow) Slayer",
    "Wigglytuff  Atk",
    "-leading and trailing-",
    "Corsola (Galarian) Bulk",
]


def test_python_tier_slug_rule():
    assert rendering.tier_slug("Lapras Atk") == "lapras-atk"
    assert rendering.tier_slug("Steelix (Shadow) Slayer") == "steelix-shadow-slayer"
    assert rendering.tier_slug("") == ""


def _slugs_original_then_name(call):
    """``tier_slug(<x>.get('original_name') or <x>.get('name') or '')``.

    The receiver name is free (the renderer's ``t`` vs the bake's ``_t``) but
    the ORDER is pinned, because it is load-bearing and asymmetric: tiers get
    renamed, and the card anchor ``id="tier-card-{slug}"`` only keeps matching
    ``DATA.tiers[i].slug`` (and generate_article's deep links) while BOTH sides
    slug ``original_name`` first. A membership-only check passes a
    renderer-side swap to ``name or original_name`` -- exactly the silent
    dead-anchor class this file exists to catch.
    """
    if len(call.args) != 1 or call.keywords:
        return False
    arg = call.args[0]
    if not (isinstance(arg, ast.BoolOp) and isinstance(arg.op, ast.Or)):
        return False
    got = []
    for v in arg.values:
        if (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
                and v.func.attr == "get" and len(v.args) == 1
                and isinstance(v.args[0], ast.Constant)):
            got.append(v.args[0].value)
        elif isinstance(v, ast.Constant):
            got.append(v.value)
        else:
            return False
    return got == ["original_name", "name", ""]


def _stamps_slug_from_helper(node):
    """``<expr>['slug'] = tier_slug(<the original_name-first chain>)``."""
    for n in ast.walk(node):
        if not isinstance(n, ast.Assign):
            continue
        if not (isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name)
                and n.value.func.id == "tier_slug"
                and _slugs_original_then_name(n.value)):
            continue
        for tgt in n.targets:
            if (isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.slice, ast.Constant)
                    and tgt.slice.value == "slug"):
                return True
    return False


def test_card_renderer_and_bake_use_the_helper():
    """Both slug producers call the ONE helper -- derived from the AST.

    These were three whole-expression pins (the renderer's assignment with its
    ``or`` chain and empty-string default, the bake's subscript assignment, and
    the ``('tiers', 'pasteTiers')`` loop header including its loop variable).
    Any extraction, reorder, line-wrap or local rename broke them without
    changing the contract. Structure survives all of that and still fails if
    the helper, the ``original_name``-FIRST fallback chain, the slug stamp, or
    either tier list drops out. Both sides' arguments are matched by the same
    order-pinned structural rule, so the renderer and the bake cannot drift
    apart from each other either.
    """
    src = (_SCRIPTS / "deep_dive_rendering.py").read_text()
    assert any(_slugs_original_then_name(c)
               for c in _call_nodes(src, "tier_slug")), (
        "the card renderer no longer slugs original_name-then-name-or-'' "
        f"through tier_slug: {_calls_to(src, 'tier_slug')}")

    # The bake stamps BOTH tier lists, from the same helper.
    loops = [n for n in ast.walk(ast.parse(_PY.read_text()))
             if isinstance(n, ast.For)
             and isinstance(n.iter, (ast.Tuple, ast.List))
             and {"tiers", "pasteTiers"} <= {e.value for e in n.iter.elts
                                             if isinstance(e, ast.Constant)}]
    assert loops, "the bake no longer walks both ('tiers', 'pasteTiers')"
    assert any(_stamps_slug_from_helper(n) for n in loops), (
        "the bake's tier loop no longer sets ['slug'] from tier_slug()")


def test_js_reads_the_baked_slug():
    body = _js_fn(_js(), "updateTierCardCounts")
    assert "t.slug ||" in body, (
        "updateTierCardCounts no longer prefers the baked DATA.tiers[i].slug")


def test_article_tier_slug_uses_the_helper():
    text = _ARTICLE.read_text()
    assert "return tier_slug(badge)" in text
    assert "re.sub(r'[^a-z0-9]+', '-', badge.lower())" not in text


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_slug_fallback_matches_python():
    """The JS keeps a fallback slugify for a DATA blob predating the field;
    it must produce exactly what the Python helper does."""
    body = _js_fn(_js(), "updateTierCardCounts")
    m = re.search(r"var slug = t\.slug \|\| (.*?);", body, re.S)
    assert m, "slug fallback expression not found"
    expr = m.group(1).replace("t.original_name || t.name", "name")
    program = """
function slugOf(name) { return %s; }
console.log(JSON.stringify(%s.map(slugOf)));
""" % (expr, json.dumps(_TIER_NAMES))
    assert _node(program) == [rendering.tier_slug(n) for n in _TIER_NAMES]


# ---------------------------------------------------------------------------
# 4. Level ceilings (entry 9, engine half)
# ---------------------------------------------------------------------------

def test_bake_emits_level_caps():
    assert ("'levelCaps': dict(zip(('default', 'alt'), bestbuddy_caps(league)),"
            in _PY.read_text())


def test_js_level_cap_fallback_matches_python():
    """Same hazard as the shadow constants: production always injects
    DATA.levelCaps, so a wrong fallback table would rot unnoticed."""
    m = re.search(r"var LEVEL_CAP_FALLBACK = \{([^}]*)\};", _js())
    assert m, "LEVEL_CAP_FALLBACK not found"
    table = json.loads("{" + re.sub(r"(\w+):", r'"\1":', m.group(1)) + "}")
    gl_default, gl_alt = bestbuddy_caps("great")
    assert table == {"default": gl_default, "alt": gl_alt,
                     "maxCpm": MAX_CPM_LEVEL}


def test_js_has_no_bare_level_ceiling_literals():
    """The three sites the review named -- the collection cap, the
    manual-entry validator, and the compare widget's alt-cap label -- read
    levelCap() now."""
    text = _js()
    assert "DATA.bestBuddy.defaultCap || levelCap('default')" in text
    assert "level > levelCap('maxCpm')" in text
    assert "bb.defaultCap || levelCap('default')" in text
    assert "bb.altCap || levelCap('alt')" in text
    # No cap-shaped fallback may be a bare number again. (state.levelMode's
    # '50' / '51' STRING tokens are a two-valued toggle enum, not levels, and
    # are deliberately left as literals -- hence the numeric-only patterns.)
    assert not re.search(r"(defaultCap|altCap|maxLevel)\s*\|\|\s*5[01]", text)
    assert not re.search(r"level\s*[<>]=?\s*5[01]\b", text)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_level_cap_prefers_data_in_node():
    text = _js()
    m = re.search(r"var LEVEL_CAP_FALLBACK = \{[^}]*\};", text)
    program = m.group(0) + "\n" + _js_fn(text, "levelCap") + """
var DATA = { levelCaps: { default: 50, alt: 51, maxCpm: 51 } };
var out = [levelCap('default'), levelCap('maxCpm')];
DATA = {};                            // pre-field DATA blob
out.push(levelCap('default'), levelCap('alt'), levelCap('maxCpm'));
console.log(JSON.stringify(out));
"""
    gl_default, gl_alt = bestbuddy_caps("great")
    assert _node(program) == [50, 51, gl_default, gl_alt, MAX_CPM_LEVEL]
