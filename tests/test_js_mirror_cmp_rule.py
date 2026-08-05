"""Mirror-CMP compare rule single-sourcing in deep_dive_engine.js.

DRY review 2026-08-05 (js-parity-2): three surfaces compared attack
values three ways -- _computeMirrorCmpPct and _computeTopMirrorCmpPct
rounded to 2dp with ties-as-beat, cmpMirror used raw values with a
1e-6 epsilon -- so one page could show "100% mirror CMP" in the table
column and "Loses mirror CMP" on the compare pill for the same IV.
The rule now lives in one helper, _atkBeats. This file pins:

1. structurally, that all three surfaces route through _atkBeats and
   the raw-epsilon compare is gone;
2. behaviorally (via node), that the helper implements 2dp + ties-beat
   on the shipped source, including the Tinkaton UL boundary case the
   original comment documents.

Pattern mirrors tests/test_js_score_key_parity.py; the node half skips
if node is absent.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_JS = Path(__file__).resolve().parents[1] / "scripts" / "deep_dive_engine.js"


def _source():
    return _JS.read_text()


def test_atk_beats_defined_once():
    assert len(re.findall(r"function _atkBeats\(", _source())) == 1


def test_all_three_surfaces_call_the_helper():
    text = _source()
    for fn in ("_computeMirrorCmpPct", "_computeTopMirrorCmpPct", "cmpMirror"):
        m = re.search(r"function %s\([^)]*\)\s*\{(.*?)\n\}" % fn, text, re.S)
        assert m, f"{fn} not found"
        assert "_atkBeats(" in m.group(1), f"{fn} does not route through _atkBeats"


def test_raw_epsilon_compare_is_gone():
    # The old cmpMirror rule was `>= cohort[0] - 1e-6`; reintroducing an
    # epsilon-based compare against a mirror cohort forks the rule again.
    # (Integer-display epsilons elsewhere in the file are fine.)
    assert not re.search(r"cohort\[\w+\]\s*-\s*1e-\d", _source())


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_helper_semantics_in_node():
    m = re.search(r"function _atkBeats\(a, b\)\s*\{.*?\n\}", _source(), re.S)
    assert m
    program = m.group(0) + """
const cases = [
  // [a, b, expected]
  [142.85, 142.8509983, true],   // Tinkaton UL: display atk ties cohort at 2dp
  [142.84, 142.8509983, false],  // strictly under at 2dp still loses
  [103.0, 103.0, true],          // exact tie beats
  [102.9982, 103.0, true],       // rounds up to tie at 2dp -- display precision rules
  [104.0, 103.0, true],
  [102.0, 103.0, false],
];
for (const [a, b, want] of cases) {
  if (_atkBeats(a, b) !== want) {
    console.error(`FAIL _atkBeats(${a}, ${b}) != ${want}`);
    process.exit(1);
  }
}
console.log("ok");
"""
    res = subprocess.run(["node", "-e", program], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "ok"
