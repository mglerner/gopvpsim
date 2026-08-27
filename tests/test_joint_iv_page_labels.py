"""Cross-arm display labels + the escaped label regex in the page JS.

``scripts/joint_iv_page.js`` renders one page per analyzed pair, so both
arms are named from ``TL_DATA.meta`` rather than from any literal in the
file. Before 6a7e534 the two name vars were the SPECIES keys
(``meta.focal`` / ``meta.opponent``), which made the Thievul moveset-fork
page ("Thievul (NS+IW) vs Thievul (IW+PR)") say bare "Thievul" for both
arms -- the panels could not tell the reader which side they described.
The fix points ``FOCAL``/``OPP`` at the display labels
(``meta.focal_display`` / ``meta.opp_display``, falling back to the
species keys), and that immediately put regex metacharacters into the one
RegExp built from those vars:

    new RegExp('\\\\s*by (?:' + OPP + '|' + FOCAL + ') atk stage\\\\s*', 'ig')

Unescaped, ``Thievul (NS+IW)`` compiles as a *group* matching "NSIW", so
the label-cleaning strip in ``cleanSubject()`` silently stops firing and
the by-stage headings render doubled: "sucker punch damage by Thievul
(NS+IW) atk stage by Thievul (IW+PR) attack stage". ``reEsc()`` exists
for exactly that. It is a silent-wrong-prose failure: nothing throws, the
page still renders, and only a reader notices.

Both tests run the REAL page source under a stub DOM in node (the same
harness shape the 6a7e534 smoke-render used) and read the rendered HTML
back out. Test one pins the display-label plumbing, test two pins the
escaping independently of where the label came from.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_JS = _ROOT / "scripts" / "joint_iv_page.js"

# The two arm labels of the cross-arm page: same species, forked moveset,
# and both carry "(" ")" "+" -- the metacharacters reEsc() is about.
_FOCAL_LABEL = "Thievul (NS+IW)"
_OPP_LABEL = "Thievul (IW+PR)"

# Just enough DOM for the page app to run to completion. Every element it
# asks for exists (so no render path is skipped for want of a node) and
# every innerHTML it writes is kept for inspection.
_STUB_DOM = """
var __NODES = {};
function __mk(id) {
  return {
    id: id, innerHTML: '', textContent: '', value: '', className: '',
    open: false, disabled: false, checked: false, files: null,
    style: {setProperty: function () {}, removeProperty: function () {}},
    dataset: {}, children: [],
    classList: {add: function () {}, remove: function () {},
                toggle: function () {},
                contains: function () { return false; }},
    appendChild: function (c) { this.children.push(c); return c; },
    removeChild: function () {}, insertBefore: function () {},
    setAttribute: function () {}, removeAttribute: function () {},
    getAttribute: function () { return null; },
    addEventListener: function () {}, removeEventListener: function () {},
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementsByTagName: function () { return []; },
    closest: function () { return null; },
    getBoundingClientRect: function () {
      return {width: 600, height: 400, top: 0, left: 0};
    },
    scrollIntoView: function () {}, focus: function () {},
    click: function () {}
  };
}
var document = {
  readyState: 'complete',
  documentElement: __mk('html'),
  body: __mk('body'),
  getElementById: function (id) {
    if (!__NODES[id]) __NODES[id] = __mk(id);
    return __NODES[id];
  },
  createElement: function (t) { return __mk('<' + t + '>'); },
  createTextNode: function (t) { return __mk('#text'); },
  createDocumentFragment: function () { return __mk('#frag'); },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  addEventListener: function () {}, removeEventListener: function () {}
};
var location = {hash: '', href: 'file:///page.html', search: ''};
var window = {
  document: document, location: location,
  addEventListener: function () {}, removeEventListener: function () {},
  matchMedia: function () {
    return {matches: false, addListener: function () {},
            addEventListener: function () {}};
  },
  getComputedStyle: function () {
    return {getPropertyValue: function () { return ''; }};
  },
  devicePixelRatio: 1, innerWidth: 1200, innerHeight: 900
};
globalThis.window = window;
globalThis.document = document;
globalThis.location = location;
globalThis.getComputedStyle = window.getComputedStyle;
globalThis.navigator = {userAgent: 'node',
                        clipboard: {writeText: function () {}}};
globalThis.MutationObserver = function () {
  this.observe = function () {}; this.disconnect = function () {};
};
globalThis.Plotly = {
  react: function () { return Promise.resolve(); },
  newPlot: function () { return Promise.resolve(); },
  purge: function () {}, relayout: function () {},
  Plots: {resize: function () {}}
};
globalThis.FileReader = function () {
  this.readAsText = function () {}; this.onload = null;
};
globalThis.alert = function () {};
"""

_DUMP = """
var __out = [];
Object.keys(__NODES).forEach(function (k) {
  __out.push('<!--' + k + '-->' + __NODES[k].innerHTML);
});
console.log(__out.join('\\n'));
"""

# A by-stage answers block is the shortest path to the label pipeline:
# answerLabel() renames the frozen "thievul" slot spelling to the focal
# LABEL, then cleanSubject() has to strip the resulting
# "by <label> atk stage" tail before the caller appends its own
# "by <opponent> attack stage".
_ANSWERS_KEY = "sp_damage_by_thievul_atk_stage"


def _tl_data(focal, opponent):
    """A minimal page blob: only the closed-form answers panel is baked."""
    return {
        "meta": {
            "focal": focal, "opponent": opponent,
            "focal_display": _FOCAL_LABEL, "opp_display": _OPP_LABEL,
            # focalMoveId() reads the headline move off the grids.
            "grids": {"ns_iw|bait": {"focal_fast": "sucker_punch",
                                     "pretty": "SP/NS+IW, baiting"}},
            "movesets": {"ns_iw": "SP/NS+IW"},
            "scenarios": ["0-0", "0-1", "0-2", "1-0", "1-1", "1-2",
                          "2-0", "2-1", "2-2"],
            "generated": "(test)", "engine": "(test)",
            "gamemaster": "(test)",
        },
        "reco": {"cards": [], "pool_n": 0, "notes": []},
        "breakpoints": {
            "meta": {"model": "closed-form damage model",
                     "move_slots": {"fast": "lick", "charged_1": "body_slam",
                                    "charged_2": "power_whip"}},
            "answers": {_ANSWERS_KEY: {"0": {"12": 4096},
                                       "-1": {"11": 4096}}},
        },
    }


def _render(focal, opponent):
    """Run the real page source over a stub DOM; return the rendered HTML."""
    program = (_STUB_DOM
               + "\nvar TL_DATA = " + json.dumps(_tl_data(focal, opponent))
               + ";\n" + _JS.read_text() + _DUMP)
    res = subprocess.run(["node", "-e", program], capture_output=True,
                         text=True, check=True)
    html = res.stdout
    # An all-empty render would pass every absence pin below for the wrong
    # reason, so prove the panel under test actually drew something.
    assert "Closed-form answers" in html, (
        "the mechanism panel did not render; harness is broken:\n"
        + res.stderr[-2000:])
    return html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_cross_arm_page_names_both_arms():
    """A moveset-fork page must name its two arms, not say "Thievul" twice.

    Pre-fix (ba557ad) FOCAL/OPP were meta.focal/meta.opponent -- the same
    species key on both sides -- so neither "(NS+IW)" nor "(IW+PR)" ever
    reached the page and every panel said bare "Thievul".
    """
    html = _render("Thievul", "Thievul")
    assert _FOCAL_LABEL in html, "the focal arm's label never reached the page"
    assert _OPP_LABEL in html, "the opponent arm's label never reached the page"
    # The label pipeline still cleans itself: the by-stage heading names the
    # opponent arm ONCE, with no key-derived tail left in front of it.
    assert "by " + _FOCAL_LABEL + " atk stage" not in html
    assert ("sucker punch damage by " + _OPP_LABEL + " attack stage") in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_label_regex_survives_metacharacters():
    """reEsc(): a label reaching the RegExp must be matched literally.

    This drives the metacharacter label in through the pre-fix var
    (meta.focal / meta.opponent) as well as the display keys, so the
    escaping is pinned wherever the name comes from. Pre-fix, the
    unescaped '(NS+IW)' compiled as a group matching "NSIW", the strip in
    cleanSubject() matched nothing, and the heading rendered doubled:
    "sucker punch damage by Thievul (NS+IW) atk stage by Thievul (IW+PR)
    attack stage".
    """
    html = _render(_FOCAL_LABEL, _OPP_LABEL)
    # Absence pin, tolerant about surrounding whitespace/markup.
    assert "by " + _FOCAL_LABEL + " atk stage" not in html, (
        "key-derived 'by <label> atk stage' tail survived cleanSubject(); "
        "the regex built from the display labels is not escaped")
    assert "by " + _OPP_LABEL + " atk stage" not in html
    # Positive control for the absence pin: the canonical cleaned heading
    # must be what replaced it. If cleanSubject() ever stops emitting this
    # (or the caller stops appending its own by-stage phrase), the two
    # asserts above would pass vacuously and this one fails.
    assert ("sucker punch damage by " + _OPP_LABEL + " attack stage") in html
    # ...and the arms are still named, so the strip did not eat the label.
    assert _FOCAL_LABEL in html
