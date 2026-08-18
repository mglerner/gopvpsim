"""Round-trip pin for the tie-fact contract between the Thievul/Licki
assembler and the shipped page JS.

``scripts/thievul_licki_assemble.py`` writes a per-card sentence ("2992
spreads tie on the primary metric (1-1 top-512 coverage); tiebreak chain:
...") that ``scripts/thievul_licki_page.js`` parses back out in
``tieText()`` to render the TL;DR band's "one of N tied" caveat. That is a
cross-file string contract with no compiler behind it, and it has already
failed once in exactly the silent way such contracts do: pluralising the
assembler's "spread(s)" to "spreads" left the page's regex matching
nothing, so the band quietly dropped the caveat that says the pick is
near-arbitrary (found in the 2026-08-17 delta review).

The test feeds the REAL producer's output through the REAL consumer:
``tie_line()`` generates the string, node runs the ``tieText`` function
extracted from the page source, and the count must come back out. Both
plural branches are exercised, plus the structured ``tie`` block that is
now the primary path.
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
_JS = _SCRIPTS / "thievul_licki_page.js"

sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_ROOT / "src"))
_spec = importlib.util.spec_from_file_location(
    "thievul_licki_assemble", _SCRIPTS / "thievul_licki_assemble.py")
_assemble = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_assemble)


def _tie_text_source():
    """The real ``tieText`` function body, lifted from the page source."""
    text = _JS.read_text()
    start = text.index("function tieText(c) {")
    depth, i = 0, start
    while True:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    src = text[start:i + 1]
    assert "tiebreak chain" in src, "extracted the wrong function"
    return src


_CASES = [
    # (n_tied, metric, tiebreak)
    (1, "1-1 coverage under NS+IW", None),
    (2, "1-1 coverage under NS+IW", None),
    (352, "1-1 coverage under NS+IW", None),
    (2992, "the primary metric (1-1 top-512 coverage)",
     "1-1 coverage > 0-0 coverage > meta wins (SP/IW+PR, 1-1) > "
     "stat-product rank"),
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_emitted_tie_line_parses_back_to_its_count():
    """assemble emits -> tieText parses -> the count survives."""
    cards = [{"lines": [_assemble.tie_line(n, metric, tb)]}
             for n, metric, tb in _CASES]
    program = _tie_text_source() + """
const cards = %s;
console.log(JSON.stringify(cards.map(tieText)));
""" % json.dumps(cards)
    res = subprocess.run(["node", "-e", program], capture_output=True,
                         text=True, check=True)
    got = json.loads(res.stdout)
    assert len(got) == len(_CASES)
    for (n, metric, tb), out in zip(_CASES, got):
        # Pre-fix value: the pluralised line matched nothing and tieText
        # returned "" (the band then fell through to the subtitle, losing
        # the count entirely).
        assert out, f"tieText returned nothing for {n!r} / {metric!r}"
        assert f"one of {n} tied" in out, (n, out)
        assert metric in out, (metric, out)
        if tb:
            assert tb in out, (tb, out)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_structured_tie_block_is_preferred_and_complete():
    """The primary path: a card carrying `tie` needs no string parsing."""
    cards = [{"tie": {"n_tied": 7, "metric": "meta wins (SP/IW+PR, 1-1)"},
              "lines": []},
             {"tie": {"n_tied": 352, "metric": "1-1 coverage under NS+IW",
                      "tiebreak": "1-1 coverage > stat-product rank"},
              "lines": []}]
    program = _tie_text_source() + """
const cards = %s;
console.log(JSON.stringify(cards.map(tieText)));
""" % json.dumps(cards)
    res = subprocess.run(["node", "-e", program], capture_output=True,
                         text=True, check=True)
    got = json.loads(res.stdout)
    assert "one of 7 tied on meta wins (SP/IW+PR, 1-1)" == got[0]
    assert got[1].startswith("one of 352 tied on 1-1 coverage under NS+IW;")


def test_assembler_builds_every_tie_line_through_the_helper():
    """No second copy of the sentence: the helper IS the contract.

    A hand-rolled f-string elsewhere in the assembler would be invisible to
    the round-trip above -- which is how the plural change slipped in.
    """
    text = (_SCRIPTS / "thievul_licki_assemble.py").read_text()
    body = text.split("def tie_line(", 1)[1].split("\ndef ", 1)[1]
    stray = re.findall(r"tie on \{", body) + re.findall(r"' tie on ", body)
    assert not stray, f"tie sentence built outside tie_line(): {stray}"
    assert body.count("tie_line(") >= 2, "the helper is not actually used"
