"""The matchup-cluster panels build their scattergl traces through one helper.

`_mcRenderRoot` in scripts/deep_dive_engine.js used to spell the full trace
spec twice -- once per cluster, once for the owned-mon overlay -- so the two
could drift on `hoverinfo`/`mode`/`type` with nothing to catch it (DRY review
2026-08-05 entry 14 ride-along, "extract the cluster trace-spec helper").

The extraction is cosmetic: both call sites still produce byte-identical trace
objects. This pins the shape (via node, so the helper's real return value is
checked, not its source text) and keeps the literal from growing back.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_win_boundary import strip_js  # noqa: E402

_JS = Path(__file__).resolve().parents[1] / 'scripts' / 'deep_dive_engine.js'


def _mc_render_root_body():
    """Code of `_mcRenderRoot`, comments/strings blanked out.

    Stripped, because the function's comments legitimately discuss scattergl
    (why the owned-mon overlay is gl rather than an svg star).
    """
    text = _JS.read_text()
    start = text.index('function _mcRenderRoot(')
    end = text.index('\nfunction ', start + 1)
    return strip_js(text[start:end])


def test_cluster_panels_have_no_inline_trace_literal():
    body = _mc_render_root_body()
    assert 'scattergl' not in body, (
        '_mcRenderRoot spells a scattergl trace inline again; build it with '
        '_mcTrace() so the cluster and owned-mon traces cannot drift')
    assert body.count('_mcTrace(') == 2, (
        'expected exactly two _mcTrace() call sites (clusters + owned overlay)')


def test_mc_trace_shape():
    """Empty arrays by default; caller-supplied arrays passed through."""
    node = shutil.which('node')
    if node is None:
        pytest.skip('node not installed')
    text = _JS.read_text()
    m = re.search(r'function _mcTrace\(.*?\n\}', text, re.S)
    assert m, '_mcTrace not found'
    probe = m.group(0) + (
        "\nconsole.log(JSON.stringify(["
        " _mcTrace('C0 (n=3)', {size: 4}),"
        " _mcTrace('Yours (2)', {size: 11}, [1, 2], [3, 4], ['a', 'b'])"
        "]));\n")
    empty, filled = json.loads(subprocess.run(
        [node, '-e', probe], capture_output=True, text=True,
        check=True).stdout)
    assert empty == {'type': 'scattergl', 'mode': 'markers', 'x': [], 'y': [],
                     'text': [], 'hoverinfo': 'text', 'name': 'C0 (n=3)',
                     'marker': {'size': 4}}
    assert filled['x'] == [1, 2]
    assert filled['y'] == [3, 4]
    assert filled['text'] == ['a', 'b']
    assert filled['name'] == 'Yours (2)'
