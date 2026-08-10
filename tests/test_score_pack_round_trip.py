"""One packed-uint16 wire format across the dive and the ML-guide chains.

DRY review 2026-08-05, entry 12 (``js-py-score-pack``). Both chains embed
big integer grids inline as ``base64(gzip(little-endian uint16))``, and
until this entry the format was written out five times: two Python
encoders (``deep_dive._pack_u16``, ``iv_envelope_analysis.pack_scores``)
and three JS decoders as hand-maintained string literals -- the dive's
scores block, the dive's energy block, and the guide's ``decodeGrid``.
Both guide-side copies carried comments *claiming* to be identical to the
dive's; nothing checked the claim, and a mismatch decodes garbage on a
shipped page with no error anywhere.

``scripts/deep_dive_lib/score_pack.py`` is now the single source: one
``pack_u16`` and one parameterized JS decoder template. This file pins
that, end to end:

1. structurally -- both Python encoders ARE the shared function, and no
   open-coded decoder literal survives in either renderer;
2. behaviorally, via node -- the decoder the DIVE actually emitted into a
   rendered page decodes that page's own shipped bytes to exactly what
   Python packed, and the decoder the GUIDE embeds decodes the same
   encoder's output including the clamp edges.

The node half skips if node is absent (pattern from
tests/test_js_mirror_cmp_rule.py).
"""
import base64
import gzip
import json
import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from tests.conftest import load_deep_dive

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / 'scripts'

# load_deep_dive() puts scripts/ and src/ on sys.path and binds the shared
# 'deep_dive' module -- iv_envelope_analysis does `from deep_dive import ...`
# at import time, so it has to come first.
deep_dive = load_deep_dive()

from deep_dive_lib import score_pack        # noqa: E402
import iv_envelope_analysis                 # noqa: E402
import render_iv_envelope_article           # noqa: E402


def _py_unpack(b64):
    """Reference decode, spelled out here on purpose: a test that reused
    the production unpacker could not catch the production packer."""
    raw = gzip.decompress(base64.b64decode(b64))
    return list(struct.unpack(f'<{len(raw) // 2}H', raw))


def _node(program):
    res = subprocess.run(['node', '-e', program], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return res.stdout


def _js_assignment(html, var_name):
    """Same ';\\n'-terminated slice contract the offline consumers use
    (compare_loadouts._extract_js_assignment, export_owned_breakdown_bundle)."""
    marker = f'var {var_name} = '
    i = html.index(marker) + len(marker)
    return html[i:html.index(';\n', i)]


# ---------------------------------------------------------------------------
# Structural: one encoder, one decoder template
# ---------------------------------------------------------------------------

def test_both_python_encoders_are_the_shared_one():
    assert deep_dive._pack_u16 is score_pack.pack_u16
    assert iv_envelope_analysis.pack_scores is score_pack.pack_u16


def test_no_open_coded_decoder_survives():
    """``new DecompressionStream(`` -- the constructor, so the prose that
    explains the pipeline to readers does not count -- appears in exactly
    one Python file: the shared template. A second occurrence means
    someone spelled the decoder out again instead of calling
    decoder_js()."""
    owners = {}
    for path in sorted(SCRIPTS.rglob('*.py')):
        n = path.read_text().count('new DecompressionStream(')
        if n:
            owners[path.relative_to(REPO_ROOT).as_posix()] = n
    assert owners == {'scripts/deep_dive_lib/score_pack.py': 1}, owners


def test_guide_embeds_the_shared_template_verbatim():
    """The guide's setup JS splices in decoder_js('decodeGrid') -- same
    template, different name and indent, which is the whole point of
    parameterizing it."""
    assert (score_pack.decoder_js('decodeGrid', indent='  ')
            in render_iv_envelope_article.CMP_SETUP_JS)


@pytest.mark.render
def test_dive_emits_the_shared_template(small_dive_html):
    assert score_pack.decoder_js('_unpackU16') in small_dive_html
    # Exactly ONE decoder body -- that is the single-source contract this
    # file exists for, so it stays an equality.
    assert small_dive_html.count('new DecompressionStream') == 1
    # ...but the number of CALL SITES is a floor, not a count: today it is
    # scores + --compare-energy energy, and a third packed grid must not
    # turn this into a repair commit (2026-08-09 review, Phase 3).
    assert small_dive_html.count('await _unpackU16(') >= 1


# ---------------------------------------------------------------------------
# Behavioral round trips (node)
# ---------------------------------------------------------------------------

@pytest.mark.render
@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_dive_page_decoder_round_trips_its_own_shipped_bytes(small_dive_html):
    """Chain 1: run the page's OWN emitted decoder over the page's OWN
    SCORES_GZ / ENERGY_GZ and require it to reproduce what Python packed."""
    packed = {'SCORES': json.loads(_js_assignment(small_dive_html, 'SCORES_GZ')),
              'ENERGY': json.loads(_js_assignment(small_dive_html, 'ENERGY_GZ'))}
    assert packed['SCORES'] and packed['ENERGY'], 'fixture embedded no grids'

    decoder = re.search(r'async function _unpackU16\(b64\) \{.*?\n\}\n',
                        small_dive_html, re.S)
    assert decoder, 'the dive emitted no _unpackU16 decoder'
    loops = re.findall(
        r'var (?:SCORES|ENERGY) = \{\};\nvar _\w+ = \(async function\(\) \{'
        r'.*?\n\}\)\(\);\n', small_dive_html, re.S)
    assert len(loops) == 2, f'expected scores + energy decode loops, got {len(loops)}'

    out = _node(
        f'var SCORES_GZ = {json.dumps(packed["SCORES"])};\n'
        f'var ENERGY_GZ = {json.dumps(packed["ENERGY"])};\n'
        + decoder.group(0) + ''.join(loops)
        + '(async function(){ await _scoresReady; await _energyReady;'
          ' console.log(JSON.stringify({SCORES: SCORES, ENERGY: ENERGY}));'
          ' })();\n')
    decoded = json.loads(out)
    for grid, blobs in packed.items():
        assert set(decoded[grid]) == set(blobs)
        for key, blob in blobs.items():
            assert decoded[grid][key] == _py_unpack(blob), f'{grid}[{key}]'


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_guide_decoder_round_trips_the_shared_encoder():
    """Chain 2: the guide's embedded decoder, over bytes from the shared
    encoder -- scores at the win boundary, the clamp edges, and a value
    that must truncate rather than round."""
    values = [0, 1, 258, 499, 500, 501, 1000, 65535]
    edges = [-1, 65536, 3.9]                 # clamp low / clamp high / truncate
    want = [0, 1, 258, 499, 500, 501, 1000, 65535, 0, 65535, 3]

    grids = {'q': iv_envelope_analysis.pack_scores(values + edges)}
    decoder = re.search(r'  async function decodeGrid\(b64\) \{.*?\n  \}\n',
                        render_iv_envelope_article.CMP_SETUP_JS, re.S)
    assert decoder, 'the guide setup JS embeds no decodeGrid'

    out = _node(
        f'var grids = {json.dumps(grids)};\n'
        + decoder.group(0)
        + '(async function(){ console.log(JSON.stringify('
          'await decodeGrid(grids.q))); })();\n')
    assert json.loads(out) == want
    # ... and the dive's Python-side reference agrees on the same bytes.
    assert _py_unpack(grids['q']) == want


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_the_two_chains_decode_each_other():
    """The cross-chain claim the old comments made and nothing checked:
    guide-packed bytes decode under the dive's decoder name, and the
    template is name-agnostic."""
    values = [7, 500, 65535, 0, 42]
    blob = iv_envelope_analysis.pack_scores(values)
    out = _node(
        score_pack.decoder_js('_unpackU16')
        + f'(async function(){{ console.log(JSON.stringify('
          f'await _unpackU16({json.dumps(blob)}))); }})();\n')
    assert json.loads(out) == values
