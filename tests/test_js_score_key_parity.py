"""Parity tripwire: the score-key string contract must match between the Python
embedder and the JS reader.

The dive embeds score grids under keys of the form ``{mi}_{mode}`` with a
parallel ``{mi}_{mode}@51`` grid when best-buddy (L51) is active
(``deep_dive.py`` ``score_arrays``). The browser reads those grids back through
``getScoreKey`` in ``deep_dive_engine.js``. If either side changed the
separator (``_``) or the L51 suffix (``@51``) independently, every score lookup
would silently miss and the page would render blank scores.

This is a STRUCTURAL parity check only: it pins the two static literals
(separator + suffix) on both sides. It deliberately does NOT verify the
CONDITIONAL gating that decides *when* the ``@51`` suffix is appended (Python:
``_bb_active and md.get('scores_l51')``; JS: ``state.levelMode === '51' &&
DATA.ivL51``) -- that runtime logic is out of reach of a string-extract test.
Belt-and-suspenders per TODO.md (todo-0).

Pattern mirrors tests/test_js_shadow_constants.py.
"""
import re
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_JS = _SCRIPTS / "deep_dive_engine.js"
_PY = _SCRIPTS / "deep_dive.py"


def _js_key_parts():
    """Extract (separator, l51_suffix) from getScoreKey in the JS engine."""
    text = _JS.read_text()
    m = re.search(
        r"function getScoreKey\(mi, mode\)\s*\{\s*"
        r"return mi \+ '([^']*)' \+ mode \+ "
        r"\([^?]*\?\s*'([^']*)'\s*:\s*''\);",
        text,
    )
    assert m, "getScoreKey not found in expected form in deep_dive_engine.js"
    return m.group(1), m.group(2)


def _py_key_parts():
    """Extract (separator, l51_suffix) from the score_arrays builder in Python."""
    text = _PY.read_text()
    sep = re.search(r"key = f'\{mi\}([^{]*)\{mode\}'", text)
    assert sep, "base score key (f'{mi}_{mode}') not found in deep_dive.py"
    suffix = re.search(r"score_arrays\[f'\{key\}([^']*)'\]", text)
    assert suffix, "L51 score key (f'{key}@51') not found in deep_dive.py"
    return sep.group(1), suffix.group(1)


def test_score_key_separator_matches():
    js_sep, _ = _js_key_parts()
    py_sep, _ = _py_key_parts()
    assert js_sep == py_sep == "_"


def test_score_key_l51_suffix_matches():
    _, js_suffix = _js_key_parts()
    _, py_suffix = _py_key_parts()
    assert js_suffix == py_suffix == "@51"
