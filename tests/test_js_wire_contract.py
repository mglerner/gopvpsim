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

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_win_boundary import strip_js  # noqa: E402

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


# ---------------------------------------------------------------------------
# 5. Matchup-cluster payload fields (scenario-clusters phase B, 2026-09-13)
# ---------------------------------------------------------------------------
#
# The section's inline JSON grew four reader-facing fields the JS renders
# verbatim -- `sil`, `root`, `rules` and `display` -- plus `allKey` and a
# `degenerate` map. Every one of them fails SILENTLY on a rename: the legend
# just drops the rule text, or a mini-grid title says nothing, with no error
# anywhere. The JS cannot be run in a browser here, so the parity half runs
# the real JS helper in node against a real Python payload.

_MC_TOP_FIELDS = ("palette", "default", "allKey", "scens", "degenerate")
_MC_SCEN_FIELDS = ("k", "labels", "sizes", "sil", "split", "rules",
                   "display")


def _mc_payload_fixture():
    """A real render's payload: 8 sharp opponents in 1v1/2v2, 2 in 0v0.

    Built through render_section rather than by hand so the schema under
    test is the one that ships.
    """
    n_opp, block = 8, 40
    n_iv = block * (n_opp + 1)
    arr = np.full((n_iv, 9, n_opp), 200, dtype=np.int32)
    for si in (4, 8):
        for i in range(n_opp + 1):
            arr[i * block:(i + 1) * block, si, :i] = 800
    arr[n_iv // 2:, 0, :2] = 800                      # 0v0: degenerate
    atk = np.linspace(100, 110, n_iv)
    names = [f"Opp{i}" for i in range(n_opp)]
    html = clusters.render_section(
        arr.ravel().tolist(), n_iv, 9, n_opp,
        [(a, b) for a in range(3) for b in range(3)], names,
        {"ivAtk": atk.tolist(), "ivDef": atk.tolist(),
         "ivHp": np.full(n_iv, 135.0).tolist()},
        "rank-1", "FAST / CM1, CM2", [])
    m = re.search(r'<script type="application/json" class="dd-mc-data">'
                  r'(.*?)</script>', html, re.S)
    assert m, "the section emitted no payload"
    return json.loads(m.group(1))


def test_cluster_payload_carries_every_field_the_js_reads():
    pay = _mc_payload_fixture()
    assert set(_MC_TOP_FIELDS) <= set(pay)
    assert pay["allKey"] == clusters.ALL_SCEN_KEY
    assert pay["default"] == clusters.ALL_SCEN_KEY   # the combined view
    sc = pay["scens"]["1v1"]
    assert set(_MC_SCEN_FIELDS) <= set(sc)
    assert len(sc["rules"]) == sc["k"] == len(sc["sizes"])
    assert isinstance(sc["sil"], float)
    assert sc["display"] == "1v1 shields"
    assert pay["scens"][clusters.ALL_SCEN_KEY]["display"] == \
        clusters.ALL_SCEN_DISPLAY
    # degenerate scenarios are NOT in scens (the JS treats presence there as
    # "per-IV labels exist"), and carry their reason for the mini titles
    assert "0v0" not in pay["scens"]
    assert "0v0" in pay["degenerate"]
    # the reason leads with the FINDING; the machine flag is the boolean,
    # and the mini-grid title reads the short form
    assert pay["degenerate"]["0v0"]["degenerate"] is True
    assert pay["degenerate"]["0v0"]["reason"].startswith("every spread wins ")
    assert pay["degenerate"]["0v0"]["short"].startswith("degenerate (")


def test_js_reads_those_exact_payload_field_names():
    """Source scan, comments and strings blanked (a field named only in a
    comment does not wire anything up)."""
    text = strip_js(_js())
    for field in ("allKey", "scens", "degenerate", "palette",
                  "labels", "sizes", "rules", "split", "sil", "display",
                  "short"):
        assert re.search(r"\.%s\b" % field, text), (
            f"no JS site reads payload field {field!r} any more")
    # self-test: a field that was never in the payload must NOT be found,
    # or the scan above passes for free
    assert not re.search(r"\.notAPayloadField\b", text)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_mc_headline_renders_the_payload_in_node():
    """The mini-grid titles and the scatter legend both read through
    ``_mcHeadline``; run the real function over a real payload."""
    pay = _mc_payload_fixture()
    program = _js_fn(_js(), "_mcHeadline") + """
var pay = %s;
console.log(JSON.stringify([_mcHeadline(pay, '1v1'), _mcHeadline(pay, '0v0'),
                            _mcHeadline(pay, 'nope')]));
""" % json.dumps(pay)
    got = _node(program)
    sc = pay["scens"]["1v1"]
    assert got[0] == (f"K={sc['k']}, silhouette {sc['sil']:.2f}, "
                      f"split {sc['split']}")
    # the no-cluster title carries its counts, not the bare word
    assert got[1] == pay["degenerate"]["0v0"]["short"]
    assert got[1].startswith("degenerate (")
    assert got[2] == ""                   # unknown label


def test_mini_grid_title_is_gated_on_the_same_predicate_as_its_colors():
    """B3: `_mcLabelsApply()` guards the COLORS and the TITLE together.

    state.oppIvMode is composed from the Opponent IVs and Bait dropdowns, so
    one click off either default makes the baked labels not describe the
    displayed grid. The colors always fell back to neutral there; the title
    kept asserting "K=2, silhouette 0.65, split atk 148.06" over data those
    labels do not describe.
    """
    raw = _js()
    assert "var mApply = _mcLabelsApply();" in raw
    assert "var mSc = (mPay && mPay.scens && mApply) ? mPay.scens[mLbl] : null;" \
        in raw
    assert "var mHead = mApply ? _mcHeadline(mPay, mLbl) : '';" in raw


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_mini_grid_headline_is_empty_when_labels_do_not_apply():
    """Run the gate itself: with the predicate false, no headline text."""
    program = """
var applies = false;
function _mcLabelsApply() { return applies; }
""" + _js_fn(_js(), "_mcHeadline") + """
var pay = %s;
var out = [];
[true, false].forEach(function(v) {
  applies = v;
  out.push(applies ? _mcHeadline(pay, '1v1') : '');
});
console.log(JSON.stringify(out));
""" % json.dumps(_mc_payload_fixture())
    got = _node(program)
    assert got[0].startswith("K=")
    assert got[1] == ""


def test_js_maps_the_avg_shields_state_to_the_combined_clusters():
    """Phase B1: 'avg' used to fall through to the payload default (1v1) and
    color by one scenario without saying so."""
    raw = _js()
    assert "state.scenarioMode === 'avg' && mcPay.scens[allKey0]" in raw
    # the key itself comes from the payload, with the Python constant as the
    # only hard-coded fallback
    assert "mcPay.allKey || 'all'" in raw
    assert clusters.ALL_SCEN_KEY == "all"


# ---------------------------------------------------------------------------
# 5. The Build criteria preset (v4 "Which one to build?")
# ---------------------------------------------------------------------------
# Three keys, one table. They key the section's payload, the clusters
# section's per-preset combined partitions and the scatter's weighted Shields
# entry, and every one of those fails SILENTLY on a drift: the section falls
# back to its default preset, the clusters option re-labels itself with a
# partition it is not drawing, and the scatter quietly averages all nine.

sys.path.insert(0, str(_SCRIPTS))
import deep_dive_builds as builds  # noqa: E402
import deep_dive_which_build as which_build  # noqa: E402


def test_the_three_preset_keys_have_one_definition():
    """deep_dive_builds.PRESETS is the table; nothing re-types the keys."""
    keys = [p[0] for p in builds.PRESETS]
    assert keys == ['flat', 'even', 'one_one']
    assert builds.PRESET_SCENS['flat'] is None            # every scenario
    assert builds.PRESET_SCENS['even'] == ('0v0', '1v1', '2v2')
    assert builds.PRESET_SCENS['one_one'] == ('1v1',)
    # The dropdown, the clusters call and the section all read that table.
    py = _PY.read_text()
    assert 'import deep_dive_builds' in py
    assert "_build_presets()" in py
    # the dropdown builder walks that table rather than re-typing it, and
    # the labels it emits are the table's own
    import deep_dive
    opts = deep_dive._build_criteria_select(list(builds.PRESET_KEYS))
    for key, label, _s, _t in builds.PRESETS:
        assert f'<option value="{key}">{label}</option>' in opts, key
    render = (_SCRIPTS / 'deep_dive_lib' / 'render.py').read_text()
    assert '_builds.PRESETS' in render
    # ... and no file writes the three strings out again.
    for path in (_JS, _SCRIPTS / 'deep_dive_matchup_clusters.py'):
        text = path.read_text()
        assert "'one_one'" not in text, path.name
        assert '"one_one"' not in text, path.name


def test_the_knob_id_is_the_same_string_on_both_sides():
    js = _js()
    assert "var WB_PRESET_SEL = 'build-criteria-sel';" in js
    assert 'id="build-criteria-sel"' in _PY.read_text()
    # onchange calls the one entry point
    assert 'onchange="wbSetPreset(this.value)"' in _PY.read_text()
    assert 'function wbSetPreset(' in js


def test_the_shields_dropdown_carries_both_all_entries():
    """'avg' is renamed and never changes; 'wbavg' is the weighted one.

    Pinned on the MARKUP the page gets, not on a source line: the emitted
    option was split across two Python string literals, so the old
    source-literal assertion pinned an indentation level instead of an
    option (2026-09-16 review), and its first alternative could never match.
    """
    import deep_dive
    assert (deep_dive._wbavg_option(['flat'])
            == '    <option value="wbavg">All (by build criteria)</option>\n')
    # no section, no weighted entry -- it would average a preset the page
    # cannot switch to
    assert deep_dive._wbavg_option([]) == ''
    py = _PY.read_text()
    assert "<option value=\"avg\">All (equal weight)</option>" in py
    js = _js()
    # the weighted entry resolves to the preset's scenarios, and 'avg' still
    # means every scenario
    body = _js_fn(js, 'getActiveScenarioIndices')
    assert "state.scenarioMode === 'avg'" in body
    assert "state.scenarioMode === 'wbavg'" in body
    assert 'wbPresetScenIndices()' in body


def test_the_knob_note_names_exactly_the_three_surfaces_it_drives():
    import deep_dive
    note = deep_dive._build_criteria_note(['flat'])
    for surface in ('Which one to build?', 'all-scenarios clusters',
                    'All (by build criteria)'):
        assert surface in note, surface
    # NOT "every other section counts all nine equally": Threats, Rank
    # Volatility and Matchup clusters each have their own per-scenario
    # views, so the only true claim is about re-weighting (2026-09-16).
    assert 'Nothing else on this page is re-weighted by it.' in note
    assert 'counts all nine shield scenarios equally' not in note
    assert deep_dive._build_criteria_note([]) == ''


def test_the_knob_lists_only_the_presets_this_page_built():
    """A dive that baked no 1v1 must not offer the 1v1-only preset.

    That preset weights nothing there, so compute_builds drops it from the
    payload; an option for it left wbApplyPreset returning early (the
    previous block and summary still on screen), the clusters view falling
    back to all nine scenarios and the Shields entry averaging everything
    while its label still read "All (by build criteria)".
    """
    import deep_dive
    import deep_dive_builds as B
    # the end of the chain that produces the live list
    assert not B.preset_is_live(B.PRESET_ONE, ['0v0', '2v2'])
    assert B.preset_is_live(B.PRESET_EVEN, ['0v0', '2v2'])
    live = [k for k in B.PRESET_KEYS if B.preset_is_live(k, ['0v0', '2v2'])]
    html = deep_dive._build_criteria_select(live)
    assert '<option value="flat">' in html
    assert '<option value="even">' in html
    assert 'one_one' not in html
    assert '1v1 only' not in html
    # positive control: with every preset live all three are offered, so an
    # always-empty select could not pass this
    full = deep_dive._build_criteria_select(list(B.PRESET_KEYS))
    assert full.count('<option ') == 3
    # and no section at all means no knob
    assert deep_dive._build_criteria_select([]) == ''


def test_the_weighted_shields_entry_labels_its_own_axis():
    """The scatter's y-axis title says WHICH scenarios it is averaging.

    Under "All (by build criteria)" the values average a subset and the axis
    used to read "Avg Battle Score", identical to "All (equal weight)"; the
    only signal was the muted line in the controls strip, scrolled off by
    the time a reader is looking at the chart (2026-09-16 review).
    """
    js = _js()
    body = _js_fn(js, 'yAxisTitle')
    assert "state.scenarioMode !== 'wbavg'" in body
    assert 'return currentYLabel' in body
    assert 'wbPresetScenLabel()' in body
    # the plot reads the title through that function, not through the raw
    # label (which also names the hover line and a table column)
    assert 'yaxis: {title:yAxisTitle(),' in js
    # and the label itself comes from the preset's own scenario list
    lbl = _js_fn(js, 'wbPresetScenLabel')
    assert 'presets[key].scens' in lbl.replace(' ', '')
    assert 'shield scenarios' in lbl and 'shields' in lbl


def test_the_more_control_and_its_hidden_rows_are_one_contract():
    """Each reveal is a button over rows the server already shipped hidden.

    v5 (2026-09-16 review item 4) gives a scenario group TWO reveals -- the
    capped tail (``wb-hid``) and the near-free tail (``wb-hidfree``) -- so
    the button names the class it owns in ``data-reveal`` and the JS reads
    it. Pre-fix the JS hard-coded ``li.wb-hid`` and one button revealed both
    tails; this asserts the class now comes from the attribute AND that the
    producer emits both classes with a matching ``data-reveal``.
    """
    js = _js()
    assert 'function wbMoreRows(' in js
    assert 'window.wbMoreRows = wbMoreRows;' in js
    body = _js_fn(js, 'wbMoreRows')
    assert "getAttribute('data-reveal')" in body
    assert "'li.' + cls" in body
    # the default is the class the pre-v5 control hard-coded, so an older
    # button with no attribute still reveals its own rows
    assert "|| 'wb-hid'" in body
    assert 'hidden = false' in body
    py = (_SCRIPTS / 'deep_dive_which_build.py').read_text()
    # the producing side emits exactly those things
    assert 'wbMoreRows(this)' in py
    assert "'wb-hidfree' if free else 'wb-hid'" in py
    for cls in ('wb-hid', 'wb-hidfree'):
        assert f'data-reveal="{cls}"' in py, cls


def test_the_section_payload_carries_every_builds_field_the_js_reads():
    """Both halves, for real: the BUILDER's output and the JS that reads it.

    The round-1 version only grepped the JS twice and claimed in its
    docstring to check the producer, so renaming e.g. ``nGw`` in
    builds_payload passed while the plot silently broke (2026-09-16 review).
    The producer half runs on the synthetic cube in tests/
    test_deep_dive_builds.py, so this stays a fast, blob-free test.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_deep_dive_builds import synthetic_res
    pay = builds.builds_payload(synthetic_res(), 0)
    top = ('presets', 'regions', 'default', 'rank1', 'gridBest',
           'nDecision', 'cells', 'presetKeys', 'scenLabels')
    for field in top:
        assert field in pay, field
    block = pay['presets'][pay['default']]
    for field in ('lattice', 'cols', 'builds', 'weights', 'scens', 'nDecW',
                  'tie', 'objectives'):
        assert field in block, field
    for field in ('nG', 'nGw', 'nGmat', 'memb', 'combo', 'size', 'role', 'r'):
        assert field in block['cols'][0], field
    for field in ('mostWinning', 'desc', 'region', 'nG', 'nGw', 'rank1In'):
        assert field in block['builds'][0], field
    for field in ('size', 'nG', 'nGmat', 'bits'):
        assert field in pay['regions'][0], field

    js = _js()
    for field in ('bp.presets', 'bp.regions', 'bp.default', 'bp.rank1',
                  'bp.gridBest', 'bp.nDecision', 'bp.topN', 'bp.colors'):
        assert field in js, field
    for field in ('.mostWinning', '.nGmat', '.nGw', '.memb', '.nDecW',
                  '.lattice', '.cols', '.builds', '.weights', '.scens',
                  '.summary', '.desc', '.region', '.bits'):
        assert field in js, field
    # the payload's own summary/lead sentences are merged in by the renderer
    # (prose is authored and word-gated in Python), so they are absent here
    assert 'summary' not in block


def test_the_clusters_payload_carries_one_all_scenarios_key_per_preset():
    pay = _mc_payload_fixture()
    # the fixture above renders without presets, so the map is absent or
    # empty; the keyed render is the one under test
    n_opp, block = 8, 40
    n_iv = block * (n_opp + 1)
    arr = np.full((n_iv, 9, n_opp), 200, dtype=np.int32)
    for si in (4, 8):
        for i in range(n_opp + 1):
            arr[i * block:(i + 1) * block, si, :i] = 800
    arr[n_iv // 2:, 0, :2] = 800
    atk = np.linspace(100, 110, n_iv)
    html = clusters.render_section(
        arr.ravel().tolist(), n_iv, 9, n_opp,
        [(a, b) for a in range(3) for b in range(3)],
        [f"Opp{i}" for i in range(n_opp)],
        {"ivAtk": atk.tolist(), "ivDef": atk.tolist(),
         "ivHp": np.full(n_iv, 135.0).tolist()},
        "rank-1", "FAST / CM1, CM2", [],
        presets=[(k, tag, scens) for k, _lbl, scens, tag in builds.PRESETS])
    m = re.search(r'<script type="application/json" class="dd-mc-data">'
                  r'(.*?)</script>', html, re.S)
    keyed = json.loads(m.group(1))
    assert set(keyed['allByPreset']) == {p[0] for p in builds.PRESETS}
    assert keyed['allByPreset']['flat'] == clusters.ALL_SCEN_KEY
    # every mapped key is either a real partition or None, never a dangling
    # name the JS would look up and miss
    for key, mapped in keyed['allByPreset'].items():
        assert mapped is None or mapped in keyed['scens'], (key, mapped)
        if mapped is not None:
            assert keyed['allLabelByPreset'][key]
    # the per-preset combined entries are NOT separate dropdown options
    opts = re.findall(r'<option value="([^"]+)"', html)
    assert clusters.ALL_SCEN_KEY in opts
    assert not [o for o in opts if o.startswith(
        clusters.ALL_SCEN_KEY + clusters.ALL_SCEN_PRESET_SEP)]
    # the JS reads the map through the same two names
    js = _js()
    assert 'payload.allByPreset' in js or 'pay.allByPreset' in js
    assert 'allLabelByPreset' in js


def test_the_section_view_ids_are_the_same_on_both_sides():
    js = _js()
    assert which_build.VIEW_BUILDS[0] == 'builds'
    assert "view === 'builds'" in js
    for vid, _label in which_build.VIEWS_FLOOR + which_build.VIEWS_NO_FLOOR:
        assert f"view === '{vid}'" in js or f"'{vid}'" in js, vid
