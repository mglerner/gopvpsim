"""Parity tripwires for the two score-lookup wire contracts between the
Python bake and the shipped page JS: the SCORES/ENERGY grid KEY and the
composite MODE grammar that key embeds.

The dive embeds score grids under keys of the form ``{mi}_{mode}`` with a
parallel ``{mi}_{mode}@51`` grid when best-buddy (L51) is active
(``deep_dive_rendering.score_key``, called from ``deep_dive.py``). The browser
reads those grids back through ``getScoreKeyAt`` / ``getScoreKey`` in
``deep_dive_engine.js``. ``{mode}`` itself is the composite
``base[:nobait][:eN]`` grammar (``deep_dive_rendering.parse_mode`` /
``parse_energy`` / ``compose_mode``), mirrored in JS by ``parseModeBase`` /
``parseModeBait`` / ``parseModeEnergy`` / ``composeMode``.

Both halves are load-bearing and fail SILENTLY: a divergent key misses every
grid lookup (blank scores, or the W3 fallback path), and a divergent mode
grammar renders a different mode than the dropdowns show.

Coverage here (DRY review 2026-08-05 entry 5):
  * the two key literals (separator, ``@51`` suffix) match on both sides;
  * no JS site reconstructs a grid key inline any more -- they all route
    through ``getScoreKeyAt`` (three inline copies lived in the compare
    widget, and the W3 fallback did not strip the ``@51`` suffix before
    putting the remainder into state.oppIvMode and the dropdowns);
  * the mode grammar round-trips identically in node and in Python.

The key half is a STRUCTURAL check: it pins the literals and the call sites,
not the CONDITIONAL gating that decides *when* the ``@51`` suffix applies
(Python: ``_bb_active and md.get('scores_l51')``; JS: ``state.levelMode ===
'51' && DATA.ivL51``) -- that runtime logic is out of reach of a
string-extract test. Belt-and-suspenders per TODO.md (todo-0).

Pattern mirrors tests/test_js_shadow_constants.py.
"""
import importlib.util
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
_PY = _SCRIPTS / "deep_dive.py"

sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_ROOT / "src"))
_spec = importlib.util.spec_from_file_location(
    "deep_dive_rendering", _SCRIPTS / "deep_dive_rendering.py")
rendering = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(rendering)


def _js_var(name):
    """String literal assigned to `var <name>` in the JS engine."""
    m = re.search(rf"var\s+{name}\s*=\s*'([^']*)';", _JS.read_text())
    assert m, f"{name} not found as a string `var` in {_JS.name}"
    return m.group(1)


# ---------------------------------------------------------------------------
# Grid key
# ---------------------------------------------------------------------------

def test_score_key_separator_matches():
    assert _js_var("SCORE_KEY_SEP") == rendering.SCORE_KEY_SEP == "_"


def test_score_key_l51_suffix_matches():
    assert _js_var("SCORE_KEY_L51") == rendering.SCORE_KEY_L51_SUFFIX == "@51"


def test_python_bake_uses_the_helper():
    """deep_dive.py must build the embedded keys via score_key(), not by
    hand -- otherwise the constants above pin nothing on the Python side."""
    text = _PY.read_text()
    assert "key = score_key(mi, mode)" in text
    assert "score_arrays[score_key(mi, mode, l51=True)]" in text
    assert "energy_arrays[score_key(mi, mode, l51=True)]" in text


def test_python_score_key_shape():
    assert rendering.score_key(3, "pvpoke:nobait") == "3_pvpoke:nobait"
    assert rendering.score_key(0, "rank1", l51=True) == "0_rank1@51"


def test_js_has_no_inline_grid_key_reconstruction():
    """Every SCORES/ENERGY lookup goes through getScoreKeyAt.

    Before entry 5 the compare widget rebuilt the key three times
    (``state.movesetIdx + '_' + state.oppIvMode`` plus a hand-appended
    ``'@51'``); a separator or suffix change would have left those behind.
    """
    text = _JS.read_text()
    assert not re.search(r"movesetIdx\s*\+\s*'_'", text), (
        "inline '{mi}_{mode}' grid-key reconstruction is back in "
        f"{_JS.name}; use getScoreKeyAt")
    # '@51' may appear ONLY as the SCORE_KEY_L51 constant's definition
    # (comments explaining the suffix are fine).
    hits = [ln.strip() for ln in text.splitlines()
            if "'@51'" in ln and not ln.lstrip().startswith("//")]
    assert hits == ["var SCORE_KEY_L51 = '@51';"], hits


def test_js_w3_fallback_strips_the_l51_suffix():
    """The W3 fallback slices a mode out of a live SCORES key; on a
    best-buddy dive that key can end in '@51', which is NOT part of the mode
    (getScoreKey re-adds it from the level toggle). Leaving it on poisons
    state.oppIvMode and every subsequent lookup."""
    text = _JS.read_text()
    m = re.search(r"var _prefix = state\.movesetIdx.*?if \(_fallback\) \{",
                  text, re.S)
    assert m, "W3 fallback block not found"
    assert "SCORE_KEY_L51" in m.group(0), (
        "W3 fallback no longer strips the best-buddy suffix from the "
        "recovered mode string")


# ---------------------------------------------------------------------------
# Composite mode grammar
# ---------------------------------------------------------------------------

_MODES = [
    "pvpoke",
    "rank1",
    "pvpoke:nobait",
    "rank1:nobait",
    "pvpoke:e1",
    "pvpoke:nobait:e1",
    "rank1:nobait:e3",
    "pvpoke:bait",
    "",
]


def _js_grammar_source():
    text = _JS.read_text()
    out = []
    for fn in ("parseModeBase", "parseModeBait", "parseModeEnergy",
               "composeMode"):
        m = re.search(r"function %s\([^)]*\)\s*\{.*?\n\}" % fn, text, re.S)
        assert m, f"{fn} not found in {_JS.name}"
        out.append(m.group(0))
    return "\n".join(out)


def test_mode_grammar_defined_once_and_used():
    """The three hand-rolled parsers are gone: the dropdown composer, the
    legacy parse_oppiv_base, and the W3 fallback all route through these."""
    text = _JS.read_text()
    for fn in ("parseModeBase", "parseModeBait", "parseModeEnergy",
               "composeMode"):
        assert len(re.findall(r"function %s\(" % fn, text)) == 1
    assert "state.oppIvMode = composeMode(" in text
    assert re.search(
        r"function parse_oppiv_base\(mode\) \{ return parseModeBase", text)
    # The old inline compositions / parsers must not come back: the two
    # grammar literals below now occur exactly once each, inside composeMode.
    assert "':nobait') : base" not in text
    assert text.count("mode += ':e'") == 1
    assert text.count("mode += ':nobait'") == 1
    assert not re.search(r"_fallback\.match\(/:e", text)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_mode_grammar_round_trips_against_python():
    program = _js_grammar_source() + """
const modes = %s;
const out = modes.map(function(m) {
  return { base: parseModeBase(m), bait: parseModeBait(m),
           energy: parseModeEnergy(m),
           round: composeMode(parseModeBase(m), parseModeBait(m),
                              parseModeEnergy(m)) };
});
console.log(JSON.stringify(out));
""" % json.dumps(_MODES)
    res = subprocess.run(["node", "-e", program], capture_output=True,
                         text=True, check=True)
    got = json.loads(res.stdout)
    for mode, js in zip(_MODES, got):
        py_base, py_bait = rendering.parse_mode(mode)
        py_energy = rendering.parse_energy(mode)
        # Python's parse_mode has no empty-mode default; the JS one falls
        # back to 'pvpoke' for a missing mode, which is the dropdown default.
        if mode == "":
            assert js["base"] == "pvpoke"
        else:
            assert js["base"] == py_base, mode
        assert js["bait"] == py_bait, mode
        assert js["energy"] == py_energy, mode
        assert js["round"] == rendering.compose_mode(
            js["base"], js["bait"], js["energy"]), mode
