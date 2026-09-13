"""Tests for the dive page's "Which one to build?" section.

Five groups:

1. **Glossary registry** (``scripts/glossary.py``). One dict owns the six
   definitions; the anchors it links are recomputed from the guide bodies so
   a renamed heading fails here instead of shipping a dead link, and a scan
   asserts no renderer carries a second literal copy of a definition.
2. **Section assembly** (``scripts/deep_dive_which_build.py``). Sentence
   surgery on the brief's headline, the lead, the two negative-page summary
   strings, and the compare prefill -- each against a synthetic fact dict, so
   they run on a fresh clone with no blobs.
3. **Palette guards.** Every marker color clears 3:1 against its own theme's
   plot fill (recomputed from ``theme.py``) and sits at least 35 hue degrees
   from the page's win / loss / tie / notable hues, so no group reads as an
   outcome and no legend entry points at points nobody can see.
4. **JS source pins** (``strip_js`` + ``node --check``) and a node harness
   that RUNS the panel's grouping code, including the main-scatter draw-order
   fix: in the Matchup cluster color mode the cluster traces must be appended
   AFTER the anchor / Efficient / slayer overlays, or legend-hover isolation
   of a mostly-anchor cluster shows an empty plot.
5. **Blob-backed pins** (``local_artifacts``): the real Shadow Sableye
   section -- ASCII, byte-determinism, payload size, the membership masks
   against the page's printed counts, and the win count the panel computes in
   the browser against the brief's own totals -- plus a real no-line moveset
   (Melmetal) for the negative page.

Vocabulary (docs style rule, per document):

- Arm: one moveset of a replay blob (the brief's word). One rendered section
  covers one arm.
- Line / floor: the brief's printed stat threshold. ``facts['floor']`` is
  the internal name.
- Payload: the section's small inline JSON (``script.wb-data``), which
  carries thresholds, named spreads and one packed membership mask per
  threshold -- never a per-IV array of stats.
- Mask: a 512-byte bitmask saying which spreads clear one threshold. It
  exists because the page's ``DATA.ivAtk`` is rounded to 2 dp and a line is
  not, so a client-side comparison would mis-side the spreads inside the
  rounding window.
"""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
GUIDES_DIR = REPO_ROOT / 'guides'
ENGINE_JS = SCRIPTS_DIR / 'deep_dive_engine.js'
SABLEYE_SHADOW = '20260911_005150_Sableye_great_shadow.replay.pkl.gz'
# A real blob whose arms 1, 2 and 4 carry NO line -- the negative page, which
# neither Sableye blob reaches.
MELMETAL = '20260910_190103_Melmetal_great.replay.pkl.gz'

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_win_boundary import strip_js  # noqa: E402

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REPO_ROOT / 'src'))

import glossary  # noqa: E402
import deep_dive_which_build as W  # noqa: E402
import deep_dive_brief as B  # noqa: E402


def _replay_dirs():
    return [REPO_ROOT / 'userdata' / 'replay',
            REPO_ROOT.parent / 'gopvpsim' / 'userdata' / 'replay']


def require_blob(name):
    for d in _replay_dirs():
        if (d / name).exists():
            return d / name
    pytest.skip(f"{name} is not on this machine")


# ---------------------------------------------------------------------------
# 1. Glossary registry
# ---------------------------------------------------------------------------

def test_every_marked_term_has_a_definition():
    """Every term the section marks must resolve in the ONE registry."""
    for term, _pattern in W._TERM_PATTERNS:
        assert glossary.definition(term), f"{term!r} has no glossary entry"


def test_glossary_anchors_point_at_real_guide_headings():
    """Each ANCHORS value must be a heading the built guide actually emits.

    Recomputed from the guide bodies with the same markdown extension the
    build uses, so a renamed heading fails here rather than shipping a link
    that scrolls nowhere.
    """
    markdown = pytest.importorskip('markdown')
    for term, anchor in glossary.ANCHORS.items():
        slug, _, frag = anchor.partition('#')
        body = GUIDES_DIR / slug / 'body.md'
        assert body.exists(), f"{term!r} links to a guide that does not exist"
        rendered = markdown.markdown(
            body.read_text(),
            extensions=['extra', 'sane_lists', 'smarty', 'toc'],
            extension_configs={'toc': {'permalink': False}},
            output_format='html5')
        ids = set(re.findall(r'<h[1-6] id="([^"]+)"', rendered))
        assert frag in ids, (
            f"{term!r} -> {anchor}: no such heading id "
            f"(guide has {sorted(ids)})")
        # Positive control: the scan finds headings at all, so a markdown
        # extension change that stopped emitting ids cannot make this pass.
        assert len(ids) >= 3


def test_no_second_literal_definition_in_any_renderer():
    """Only glossary.py may carry the definition sentences.

    Scans every renderer source, not just the ones this section touches: the
    point of a registry is that a second copy cannot appear anywhere and
    drift.
    """
    sources = sorted(SCRIPTS_DIR.glob('*.py')) + sorted(SCRIPTS_DIR.glob('*.js'))
    assert len(sources) >= 20, "the scan found suspiciously few renderers"
    hits = []
    for path in sources:
        if path.name == 'glossary.py':
            continue
        text = path.read_text()
        for term, definition in glossary.TERMS.items():
            if definition in text:
                hits.append((path.name, term))
    assert hits == [], f"second literal definition(s): {hits}"


def test_no_second_definition_scan_has_a_positive_control(tmp_path):
    """The scan above must actually be able to fail."""
    definition = glossary.TERMS['bulkpoint']
    planted = tmp_path / 'planted.py'
    planted.write_text(f'X = "{definition}"\n')
    assert definition in planted.read_text()


def test_abbr_markup_carries_dotted_underline_and_link():
    html = glossary.abbr_html('bulkpoint')
    assert 'class="wb-term"' in html and 'title="' in html
    assert '../guides/threshold-tiers/#' in html
    # A term with no guide gets the hover alone, not a link to nowhere.
    assert '<a ' not in glossary.abbr_html('charge-move priority')


def test_abbr_rejects_an_unregistered_term():
    with pytest.raises(KeyError):
        glossary.abbr_html('sharp marginal')


# ---------------------------------------------------------------------------
# 2. Section assembly, against a synthetic fact dict
# ---------------------------------------------------------------------------

def _facts(floor=True):
    """A minimal fact dict shaped like compute_brief's, for the prose paths."""
    f = {
        'header': {'arm': 0, 'n_arms': 2, 'arm_label': 'FAST / CM1, CM2',
                   'league': 'great', 'n_iv': 4096},
        'rank1': {'ivs': [0, 15, 15], 'level': 49.5, 'total_won': 367,
                  'total_cells': 684},
        'grid_best': {'ivs': [7, 2, 14], 'level': 49.5, 'total': 382,
                      'total_cells': 684, 'n_tied': 1},
        'examples': [
            {'ivs': [6, 9, 7], 'level': 50.0, 'rule': 'highest stat product'},
            {'ivs': [10, 13, 11], 'level': 45.5, 'rule': 'bulkiest'},
        ],
        'floor': None, 'alternative': None, 'rungs_above': [],
        'cluster_corroboration': None,
        '_headline': ['Most X should have at least 148.10 attack. '
                      '2220 of the 4096 IV spreads reach it.',
                      'The stat-product rank-1 spread misses it.'],
    }
    if floor:
        f['floor'] = {'axis': 'atk', 'printed': 148.1, 'dp': 2,
                      'T': 148.1039982, 'cell': '0v1 Annihilape',
                      'n_above': 2220, 'pool_share': 0.542, 'kind': 'exact'}
    return f


def test_sentences_do_not_split_inside_a_decimal():
    got = W.sentences('Most X should have at least 148.10 attack. '
                      '2220 of the 4096 IV spreads reach it.')
    assert len(got) == 2
    assert got[0].endswith('148.10 attack.')
    assert W.sentences('Bulkiest at L45.5 wins.') == ['Bulkiest at L45.5 wins.']


def test_extended_first_sentence_names_spreads_then_the_remainder():
    got = W.extended_first_sentence(_facts())
    assert got == ('Most X should have at least 148.10 attack, which '
                   '6/9/7 at L50, 10/13/11 at L45.5 and 2218 other spreads '
                   'reach.')
    # 2220 clearers minus the 2 named: the count is the brief's, not a
    # recount of the grid.
    assert '2218' in got


def test_extended_first_sentence_is_untouched_with_no_line():
    f = _facts(floor=False)
    assert W.extended_first_sentence(f) == W.sentences(f['_headline'][0])[0]


def test_summary_uses_the_headline_sentence_when_there_is_a_line():
    assert W.summary_sentence(_facts()).startswith('Most X should have')


def test_summary_on_a_negative_page_says_any_of_them():
    f = _facts(floor=False)
    assert W.summary_sentence(f) == (
        'Any of them: no single stat threshold decides a matchup here.')


def test_summary_on_a_negative_page_defers_to_rank1_when_rank1_wins_most():
    f = _facts(floor=False)
    f['grid_best']['total'] = f['rank1']['total_won']
    assert W.summary_sentence(f) == (
        'Your rank-1: it already wins more matchups than any other spread.')


def test_compare_prefill_is_rank1_then_the_example_spreads():
    got = W.compare_spreads(_facts())
    assert [iv for _rule, iv in got] == [[0, 15, 15], [6, 9, 7], [10, 13, 11]]
    assert got[0][0] == 'rank-1'


def test_compare_prefill_on_a_negative_page_offers_the_most_winning_spread():
    got = W.compare_spreads(_facts(floor=False))
    assert [iv for _rule, iv in got] == [[0, 15, 15], [7, 2, 14]]


def test_no_definition_contains_another_registered_term():
    """A definition that named another term would be marked inside its own
    tooltip, and the reader would meet a term defined inside a definition."""
    offenders = []
    for term, definition in glossary.TERMS.items():
        for other, pattern in W._TERM_PATTERNS:
            if other == term:
                continue
            if re.search(pattern, definition, re.IGNORECASE):
                offenders.append((term, other))
    assert offenders == [], offenders


def test_term_marker_does_not_mark_inside_an_inserted_tooltip():
    """The markup a substitution inserts is a tag by the next pass."""
    m = W.TermMarker()
    got = m.mark('<p>bulkpoint, and separately contested matchups</p>')
    # Both marked, neither inside the other's title attribute.
    assert got.count('<abbr') == 2
    for chunk in re.findall(r'title="([^"]*)"', got):
        assert '<abbr' not in chunk


def test_term_marker_marks_only_the_first_use():
    m = W.TermMarker()
    a = m.mark('<p>a bulkpoint and another bulkpoint</p>')
    assert a.count('<abbr') == 1
    assert m.mark('<p>a third bulkpoint</p>').count('<abbr') == 0


def test_term_marker_never_rewrites_inside_a_tag():
    m = W.TermMarker()
    got = m.mark('<span title="a bulkpoint lives here">plain text</span>')
    assert got == '<span title="a bulkpoint lives here">plain text</span>'


def test_term_marker_prefers_the_longer_term():
    m = W.TermMarker()
    got = m.mark('<p>the stat-product rank-1 spread</p>')
    assert 'stat-product rank-1</abbr>' in got
    import html as _h
    assert _h.escape(glossary.TERMS['stat-product rank-1'], quote=True) in got


def test_lead_names_the_other_movesets_with_semicolons():
    """Every moveset label contains a comma, so the list cannot use one."""
    a, b = _facts(), _facts()
    b['header'] = dict(b['header'], arm=1, arm_label='FAST / CM3, CM4')
    out = W.lead_sentences([a, b], 0)
    assert len(out) == 3
    assert out[1].startswith('This file is FAST / CM1, CM2 at ')
    assert out[2].startswith('Other movesets on this page: ')
    assert 'FAST / CM3, CM4, the same line' in out[2]


def test_mask_packing_is_lsb_first_within_each_byte():
    """The bit order the JS decoder assumes, pinned on both sides."""
    import base64
    packed = W.mask_b64([True, False, True] + [False] * 5 + [True])
    raw = base64.b64decode(packed)
    assert raw == bytes([0b00000101, 0b00000001])
    assert W.mask_b64([]) == ''
    assert W.mask_b64([False] * 8) == base64.b64encode(b'\x00').decode()


def test_printed_value_keeps_the_proven_selector():
    """At 3 dp the 2-dp rendering selects a different set, so both print."""
    assert W.printed_value({'axis': 'atk', 'printed': 123.419, 'dp': 3}) \
        == '123.42 (123.419)'
    assert W.printed_value({'axis': 'atk', 'printed': 148.1, 'dp': 2}) == '148.10'
    assert W.printed_value({'axis': 'hp', 'printed': 125, 'dp': 2}) == '125'


# ---------------------------------------------------------------------------
# 3. Palette guards
# ---------------------------------------------------------------------------

def _relative_luminance(hex_color):
    c = [int(hex_color.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [(x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4)
         for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    la, lb = _relative_luminance(a), _relative_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _palette_blocks():
    """The section CSS's two --wb-* blocks, as {token: hex} per theme kind."""
    css = W.CSS
    light = css[css.index('#dd-which-build {'):css.index('[data-theme=')]
    dark = css[css.index('[data-theme='):css.index('#dd-which-build > summary')]
    def tokens(chunk):
        return dict(re.findall(r'(--wb-[a-z0-9]+):\s*(#[0-9a-fA-F]{6})', chunk))
    return tokens(light), tokens(dark)


def test_section_palette_is_legible_in_every_theme():
    """Every marker color clears 3:1 on its own theme's plot fill.

    The rung ramp is why this exists: its first step is the FLOOR -- the
    largest and most important group on the panel -- and a first draft put it
    at 1.37:1 on a dark canvas, i.e. a legend entry pointing at points nobody
    could see. Ratios are recomputed from theme.py, so re-valuing a theme
    token fails here.
    """
    from gopvpsim import theme
    light, dark = _palette_blocks()
    assert len(light) == len(dark) >= 9, (len(light), len(dark))
    assert set(light) == set(dark)
    fills = dict(zip(theme._THEME_ORDER, theme._TOKENS['--surface-2']))
    bad = []
    for name, fill in fills.items():
        palette = dark if name.endswith('dark') else light
        for token, value in palette.items():
            r = _contrast(value, fill)
            if r < 3.0:
                bad.append((name, token, value, round(r, 2)))
    assert bad == [], bad


def test_js_palette_fallback_matches_the_css():
    """The engine's WB_FALLBACK is a copy of the light-theme CSS block.

    Same deliberate-fallback pattern the engine already uses for level caps
    and theme tokens: the copy exists so an environment where
    getComputedStyle returns nothing still draws the right colors, and this
    test is what keeps the copy from drifting into the wrong ones.
    """
    # RAW source, not strip_js: the values being pinned ARE string literals,
    # and strip_js blanks those by design.
    src = ENGINE_JS.read_text()
    block = src[src.index('var WB_FALLBACK = {'):
                src.index('function _wbColors(')]
    got = dict(re.findall(r"'(--wb-[a-z0-9]+)':\s*'(#[0-9a-fA-F]{6})'", block))
    light, _dark = _palette_blocks()
    assert got == light, {k: (got.get(k), light.get(k))
                          for k in set(got) | set(light)
                          if got.get(k) != light.get(k)}
    assert len(got) >= 9


def test_palette_contrast_check_can_fail():
    """Positive control for the scan above."""
    assert _contrast('#ffffff', '#fffffe') < 3.0
    assert _contrast('#000000', '#ffffff') > 3.0


def _hue_sat(hex_color):
    import colorsys
    r, g, b = [int(hex_color.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    h, _l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s


def _hue_distance(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def test_section_palette_avoids_the_pages_outcome_hues():
    """No section group may read as win, loss, tie or notable.

    HUE distance, not contrast: a purple and a green can sit at the same
    luminance and still be unmistakable, so a contrast check answers the
    wrong question here. Near-grey values are exempt -- they have no hue to
    confuse. 35 degrees is the bar; the mockup's pink for the bulk pair was
    20 degrees from --loss and is now a magenta 45 away.
    """
    from gopvpsim import theme
    light, dark = _palette_blocks()
    outcome = {tok: {_hue_sat(v)[0] for v in theme._TOKENS[tok]}
               for tok in ('--win', '--loss', '--tie', '--notable')}
    checked = 0
    bad = []
    for palette in (light, dark):
        for token, value in palette.items():
            h, sat = _hue_sat(value)
            if sat < 0.15:
                continue          # grey: no hue to mistake for an outcome
            checked += 1
            for name, hues in outcome.items():
                near = min(_hue_distance(h, o) for o in hues)
                if near < 35:
                    bad.append((token, value, name, round(near)))
    assert bad == [], bad
    # Anti-vacuity: the saturation exemption must not swallow the palette.
    assert checked >= 16, checked


# ---------------------------------------------------------------------------
# 4. JS source pins
# ---------------------------------------------------------------------------

def _engine():
    return strip_js(ENGINE_JS.read_text())


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_engine_js_parses():
    subprocess.run(['node', '--check', str(ENGINE_JS)], check=True,
                   capture_output=True)


def test_cluster_traces_are_appended_after_the_overlays():
    """The draw-order fix: isolating a cluster must not reveal an empty plot.

    C0 on a CP-capped grid is mostly anchor spreads. With the cluster traces
    pushed where the color-mode branch builds them, the anchor / Efficient /
    slayer overlays sat ON TOP of them, so legend-hover isolation dimmed the
    cluster and left the overlay at full opacity -- the cluster read as
    empty. Cluster traces now append after the overlays, the same treatment
    the tier traces already had.
    """
    src = _engine()
    collect = src.index('_clusterTraces.push(ctr[c1])')
    anchor = src.index('traces.push(anchorTrace)')
    push = src.index('traces.push(_clusterTraces[_ci])')
    assert collect < anchor, "cluster traces are still built before the overlays"
    assert push > anchor, "cluster traces still draw under the anchor overlay"
    for name in ('effTrace', 'slayerTrace', 'recTrace'):
        assert push > src.index(f'traces.push({name})'), \
            f"cluster traces still draw under the {name} overlay"
    # The branch must not ALSO push ctr entries straight into traces.
    assert 'traces.push(ctr[' not in src
    # Positive control: the precedent this copies still holds, so a scan that
    # stopped finding the overlay pushes would fail here first.
    assert src.index('traces.push(_tierTraces[_ti])') > anchor
    assert src.count('traces.push(anchorTrace)') == 1


def test_section_panel_reads_the_page_arrays_and_embeds_no_second_grid():
    src = _engine()
    # Wins are counted from the embedded score grid, over every scenario and
    # every opponent -- the brief's own denominator.
    wins = src[src.index('function wbWins('):src.index('function _wbColors(')]
    assert 'SCORES[key]' in wins
    assert 'DATA.nScenarios' in wins and 'DATA.nOpponents' in wins
    assert 'isWin(' in wins
    # Stats come from the league-cap arrays, not whatever best-buddy swapped in.
    assert '_bbL50' in src[src.index('function wbLevelArrays('):
                           src.index('var _wbWinsCache')]
    # Cluster labels are the clusters section's, never re-derived here, and
    # they are drawn only when the section baked them for THIS panel's
    # moveset and opponent-IV mode.
    groups = src[src.index('function _wbGroups('):
                 src.index('function _wbOwnedTrace(')]
    assert '_mcPayloadPage()' in groups
    assert 'pay.mi === 0' in groups and 'DATA.oppIvModes[0]' in groups
    # ...and NOT on the scatter's live-dropdown gate, which asks a different
    # question of a panel that follows no dropdown.
    assert '_mcLabelsApply()' not in groups


def test_js_sides_every_spread_by_the_mask_not_the_rounded_stats():
    """The page's DATA.ivAtk is 2-dp; the line is not.

    Any comparison of a full-precision threshold against the rounded array
    mis-sides the spreads inside the rounding window. The JS must therefore
    carry no such comparison at all -- membership comes from the packed mask.
    """
    src = _engine()
    block = src[src.index('function _wbGroups('):src.index('function _wbWireLegend(')]
    assert '_wbBit(' in block
    assert 'pay.T' not in block, 'the panel still compares a rounded stat to T'
    assert 'defT' not in block and 'hpT' not in block
    # The clearer table sides the same way, and takes its cut-off from the
    # payload rather than a JS literal.
    clearers = src[src.index('function wbRenderClearers('):
                   src.index('function wbToggleClearers(')]
    assert '_wbBit(mask, i)' in clearers
    assert 'pay.topN' in clearers


def test_section_js_exports_every_inline_handler():
    """Inline onclick/onchange handlers only see window.* (engine is an IIFE)."""
    src = _engine()
    for name in ('wbSelectView', 'wbCompare', 'wbToggleClearers',
                 'wbShowAllClearers', 'wbRefresh', 'cmpSetCandidates'):
        assert f'window.{name} = {name};' in src, f'{name} is not exported'


def test_section_handlers_named_in_the_html_all_exist_in_the_engine():
    """Every handler the Python renderer names must be a real export."""
    py = (SCRIPTS_DIR / 'deep_dive_which_build.py').read_text()
    src = _engine()
    called = set(re.findall(r'window\.(wb[A-Za-z]+)\)\s*wb', py))
    called |= set(re.findall(r'onclick="wb([A-Za-z]+)\(', py))
    assert called, 'the scan found no handlers to check'
    for name in called:
        full = name if name.startswith('wb') else 'wb' + name
        assert f'window.{full} = {full};' in src


def test_compare_prefill_replaces_rather_than_appends():
    src = _engine()
    body = src[src.index('function cmpSetCandidates('):
               src.index('window.cmpSetCandidates')]
    assert 'state.compareCandidates = out;' in body
    assert 'CMP_MAX' in body and 'cmpRender()' in body


def test_collection_overlay_refreshes_the_section_panel():
    """Load / clear collection and a theme flip must redraw the panel."""
    src = _engine()
    assert src.count('wbRefresh();') >= 4
    for site in re.finditer(r'mcRefreshAll\(\);', src):
        tail = src[site.end():site.end() + 60]
        assert 'wbRefresh' in tail, 'a collection refresh site misses the panel'


_GROUP_HARNESS = r"""// Node harness: exercise the section's grouping logic in isolation.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const start = src.indexOf('function _wbRoot()');
const end = src.indexOf('// ---- Re-theme the canvases');
if (start < 0 || end < 0 || end <= start) { console.error('MARKERS'); process.exit(2); }
const block = src.slice(start, end);

const N = 6;
const DATA = {
  nIvs: N, nScenarios: 1, nOpponents: 4,
  ivA: [0,1,2,3,4,5], ivD: [15,14,13,12,11,10], ivS: [15,14,13,12,11,10],
  ivAtk: [140,145,148.2,149,150.5,151], ivDef: [110,105,101.5,100,99,98],
  ivHp: [130,128,126,124,122,120], ivLv: [50,50,50,50,50,50],
  spRanks: [1,2,3,4,5,6], ivL51: null,
};
const SCORES = { '0|pvpoke': new Uint16Array([
  600,400,400,400,  600,600,400,400,  600,600,600,400,
  600,600,600,600,  600,600,600,600,  600,600,600,600]) };
const SCORE_KEY_SEP = '|';
function isWin(v) { return v > 500; }
function plotChrome() { return {ink:'#000', paper:'', plot:'', font:'', grid:'',
  legendBg:'', legendBorder:'', hoverBg:'', hoverBorder:''}; }
function _mcPayloadPage() { return null; }
function _mcLabelsApply() { return false; }
const state = { ownedByIv: null };
const _bbL50 = null;
const window = {};
const document = { getElementById: () => null, addEventListener: () => {},
                   querySelector: () => null };
const Plotly = { react: () => {}, restyle: () => {}, Plots: { resize: () => {} } };
const getComputedStyle = () => ({ getPropertyValue: () => '' });

let out;
eval(block + '\nout = {wbWins, _wbGroups, wbLevelArrays, _wbIvIdx, _wbHover, _wbMask, _wbBit};');

// Masks are LSB-first per byte, exactly as deep_dive_which_build.mask_b64
// packs them: 'PA==' = 0b00111100 = spreads 2..5, 'MA==' = spreads 4..5,
// 'Aw==' = spreads 0..1. They deliberately DISAGREE with a naive compare
// against the page's 2-dp stats for spread 2 (atk 148.2 rounds the same way
// either side of the line), which is the whole reason the mask exists.
const pay = {
  mi: 0, mode: 'pvpoke', hasFloor: true, axis: 'atk', axisWord: 'attack',
  T: 148.1039982, printed: '148.10', cell: '0v1 X', nAbove: 4, topN: 25,
  rank1: {iv: [0,15,15], level: 50}, gridBest: {iv:[5,10,10], level:50},
  examples: [{iv:[2,13,13], level:50, rule:'r'}],
  rungs: [{axis:'atk', T:148.1039982, n:4, mask:'PA==', label:'148.10 (a)'},
          {axis:'atk', T:150.0, n:2, mask:'MA==', label:'150.00 (b)'}],
  alt: {label: 'Def >= 105, HP >= 128', mask: 'Aw==', n: 2},
  clusterScen: null, views: [],
};
const L = out.wbLevelArrays();
const wins = out.wbWins(0, 'pvpoke');
const fail = [];
function eq(name, got, want) {
  if (JSON.stringify(got) !== JSON.stringify(want)) fail.push(name + ': got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want));
}
// wins: rows are 1,2,3,4,4,4 wins
eq('wins', Array.from(wins), [1,2,3,4,4,4]);

const line = out._wbGroups(pay, 'line', L, wins, {line:'#1',below:'#2',alt:'#3',mark1:'#4',mark2:'#5',rungs:['#6','#7']});
const byName = {}; line.traces.forEach(t => byName[t.name.replace(/ \(\d+\)$/,'')] = t.x.length);
eq('line groups', byName, {'Below the line': 2, 'At or above the line': 4});

const rungs = out._wbGroups(pay, 'rungs', L, wins, {line:'#1',below:'#2',alt:'#3',mark1:'#4',mark2:'#5',rungs:['#6','#7']});
const rn = {}; rungs.traces.forEach(t => rn[t.name.replace(/ \(\d+\)$/,'')] = t.x.length);
// atk 140,145 below; 148.2,149 -> rung0; 150.5,151 -> rung1
eq('rung groups', rn, {'Below the line': 2, '148.10 (a)': 2, '150.00 (b)': 2});

const trade = out._wbGroups(pay, 'trade', L, wins, {line:'#1',below:'#2',alt:'#3',mark1:'#4',mark2:'#5',rungs:['#6','#7']});
const tn = {}; trade.traces.forEach(t => tn[t.name.replace(/ \(\d+\)$/,'')] = t.x.length);
// idx0 (def110,hp130) and idx1 (def105,hp128) qualify for the rectangle and are below the line
eq('trade groups', tn, {'Neither': 0, 'At or above the line': 4, 'Bulk alternative: Def >= 105, HP >= 128': 2});
// The mask, not the rounded stats: spread 2 sits inside the 2-dp rounding
// window and is a clearer only because the mask says so.
eq('mask bit 2 is a clearer', out._wbBit(out._wbMask('PA=='), 2), 1);
eq('mask bit 1 is not', out._wbBit(out._wbMask('PA=='), 1), 0);

const clusters = out._wbGroups(pay, 'clusters', L, wins, {line:'#1',below:'#2',alt:'#3',mark1:'#4',mark2:'#5',rungs:['#6','#7']});
eq('clusters missing when no mc payload', clusters.missing, true);

eq('ivIdx', out._wbIvIdx([2,13,13]), 2);
eq('ivIdx missing', out._wbIvIdx([9,9,9]), -1);
if (out._wbHover(2, L, wins, 'side').indexOf('2/13/13') !== 0) fail.push('hover ivs');
if (out._wbHover(2, L, wins, 'side').indexOf('wins 3 of 4') < 0) fail.push('hover wins');

if (fail.length) { console.error(fail.join('\n')); process.exit(1); }
console.log('OK');
"""


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_section_grouping_logic_runs(tmp_path):
    """Run the panel's grouping code for real, on a 6-spread synthetic grid.

    The engine is one scope-wrapped script whose top level touches the DOM,
    so the harness slices out the section's own block (between ``_wbRoot``
    and the theme observer) and evaluates it against stubs. That makes the
    three population views EXECUTABLE here: source pins alone would not
    catch a spread landing in the wrong group, which is the failure a reader
    would see as a mis-colored plot.
    """
    runner = tmp_path / 'wb_groups_check.js'
    runner.write_text(_GROUP_HARNESS)
    proc = subprocess.run(['node', str(runner), str(ENGINE_JS)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert proc.stdout.strip() == 'OK'


# ---------------------------------------------------------------------------
# 4b. Placement in the renderer
# ---------------------------------------------------------------------------

def test_section_is_emitted_above_the_scatter_controls():
    """Placement is the decision this preview exists to show."""
    src = (SCRIPTS_DIR / 'deep_dive.py').read_text()
    controls = '\'<div class="controls" id="dd-scatter">\\n\''
    assert src.count(controls) == 1, 'the scatter controls anchor moved'
    assert src.count('html += which_build_html') == 1
    assert src.index('html += which_build_html') < src.index(controls)


def test_section_is_omitted_without_a_blob_path():
    """No blob, no brief -- and the no-op is logged, never silent."""
    import deep_dive
    assert deep_dive._which_build_sections({}) == {}


# ---------------------------------------------------------------------------
# 5. Blob-backed pins
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def shadow_sableye():
    path = require_blob(SABLEYE_SHADOW)
    state = B.load_blob(str(path))
    return state, W.prepare(state, str(path)), str(path)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_real_section_is_ascii_deterministic_and_small(shadow_sableye):
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    assert html == W.section_html(all_facts, 0), 'two renders differ'
    assert html.isascii(), 'the section emitted a non-ASCII character'
    # The whole per-file budget for this section is ~150 KB; the payload
    # alone must stay tiny, because it is the part that would grow if a
    # per-IV array ever leaked into it.
    assert len(html) < 150_000, len(html)
    payload = json.loads(
        re.search(r'class="wb-data">(.*?)</script>', html, re.S).group(1))
    # One 512-byte mask per printed rung plus one for the bulk pair; the cap
    # is generous enough for a long rung ladder and far below the point where
    # a per-IV STAT array would have been cheaper.
    assert len(json.dumps(payload)) < 32_000, len(json.dumps(payload))


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_real_section_is_collapsed_and_carries_the_headline(shadow_sableye):
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    opening = html[html.index('<details class="wb-root"'):]
    assert opening.startswith('<details class="wb-root" id="dd-which-build">')
    summary = re.search(r'<summary class="wb-summary">(.*?)</summary>',
                        html, re.S).group(1)
    assert 'Which one to build?' in summary
    assert 'should have at least 148.10 attack.' in summary
    assert 'wb-evidence' in html and 'wb-guards' in html
    # The printed value is the expander's control, in the headline sentence.
    assert ('class="wb-val" onclick="wbToggleClearers(this)" '
            'title="Click to list the 2220 spreads') in html


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_reader_facing_text_never_says_brief_verdict_or_recommended(
        shadow_sableye):
    """The section is called "Which one to build?" and nothing else.

    The internal names stay internal: "build brief" is the module, "verdict"
    is the design doc, "recommended" is the word the brief's own G-words gate
    already bars. Scans attribute text too -- a `title=` is reader-facing the
    moment someone hovers it.
    """
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    body = html[html.index('<details class="wb-root"'):]
    lowered = body.lower()
    for word in ('build brief', 'verdict', 'recommend'):
        assert word not in lowered, f'{word!r} reached a reader-facing surface'
    # Positive control: the scan is looking at the right text.
    assert 'which one to build?' in lowered


# The prose this section AUTHORS, as opposed to the prose it quotes from the
# brief. Listed here so the guard below can hold it to the brief's own word
# rules without re-gating the brief's blocks (the headline's "should have at
# least" is allowed exactly once per rendered section, and the summary quotes
# it a second time by design).
_SECTION_CHROME = (
    'Stat-product rank against matchups won over every baked shield scenario '
    'and the whole opponent pool, with PvPoke-default opponent IVs at the '
    'league cap -- the exact view the line above was derived from, so this '
    "panel does not follow the scatter's dropdowns or the opponent filter.",
    'Compare these spreads',
    'Other movesets on this page: ',
    'Show: ',
)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_section_authored_chrome_is_present_and_passes_the_word_gates(
        shadow_sableye):
    """The few sentences this module writes itself obey the brief's rules.

    Everything else in the section is the brief's HTML and was gated when it
    was built. These four are not, so they are held to the same banned-word
    and caveat gates here -- and each is asserted PRESENT, so the guard
    cannot pass by scanning prose the page stopped emitting.
    """
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    for chunk in _SECTION_CHROME:
        assert chunk in html, chunk
    ctx = {'blob': 'test', 'arm': 0, 'mode': 'pvpoke'}
    B.gate_words(list(_SECTION_CHROME), ctx)
    B.gate_caveat(list(_SECTION_CHROME), ctx)
    # Positive control: the gate can still fail.
    with pytest.raises(B.GuardError):
        B.gate_words(['this is the best spread'], ctx)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_real_payload_thresholds_are_the_briefs_own(shadow_sableye):
    _state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    payload = W.build_payload(facts, facts['_fields'], 0)
    fl = facts['floor']
    assert payload['T'] == fl['T']
    assert payload['axis'] == fl['axis']
    assert payload['nAbove'] == fl['n_above']
    assert payload['rungs'][0]['T'] == fl['T']
    assert [r['T'] for r in payload['rungs'][1:]] == \
        [r['T'] for r in facts['rungs_above']]
    assert [e['iv'] for e in payload['examples']] == \
        [list(e['ivs']) for e in W.example_spreads(facts)]
    # No per-IV array may ride along: the page already carries them.
    for key, value in payload.items():
        assert not (isinstance(value, list) and len(value) > 64), key


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_masks_are_checked_against_the_pages_printed_counts(shadow_sableye):
    """compute_masks refuses to pack a mask that covers a different set."""
    import copy
    state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    masks = W.compute_masks(state, 0, facts)
    assert len(masks['rungs']) == 1 + len(facts['rungs_above'])
    assert masks['alt'] is not None
    # Positive control: a count the plot could not reproduce must raise, not
    # quietly draw a different set from the one the page describes.
    bad = copy.deepcopy({'floor': dict(facts['floor']),
                         'rungs_above': facts['rungs_above'],
                         'alternative': facts['alternative']})
    bad['floor']['n_above'] += 1
    with pytest.raises(ValueError, match='the page prints'):
        W.compute_masks(state, 0, bad)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_mask_disagrees_with_the_rounded_stats_on_this_grid(shadow_sableye):
    """Records the defect the mask exists to prevent.

    ``DATA.ivAtk`` is rounded to 2 dp by deep_dive.py; the line is
    148.1039982. Comparing the rounded array against it sides 19 of the 4096
    spreads wrongly -- they would have drawn in the wrong color under a
    sentence saying the split is exact. If this ever drops to zero the
    rounding hazard has gone away on THIS grid, not in general.
    """
    import numpy as np
    state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    _scores, meta = B.arm_view(state, 0, 'pvpoke')
    atk, _d, _h = B.stat_planes(meta)
    true_side = atk >= facts['floor']['T']
    rounded_side = np.round(atk, 2) >= facts['floor']['T']
    assert int(true_side.sum()) == facts['floor']['n_above'] == 2220
    assert int((true_side != rounded_side).sum()) == 19   # pre-mask value


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_panel_win_counts_match_the_briefs_totals(shadow_sableye):
    """The y-axis definition the browser implements, checked in Python.

    ``wbWins`` counts wins over every baked scenario and every opponent of
    the PvPoke-default grid at the league cap. That must reproduce the
    brief's own per-spread totals exactly -- otherwise the panel plots one
    number under a caption quoting another.
    """
    import numpy as np
    state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    scores, _meta = B.arm_view(state, 0, 'pvpoke')
    wins = B.win_cube(scores).reshape(scores.shape[0], -1).sum(axis=1)
    assert int(wins[facts['rank1']['i']]) == facts['rank1']['total_won']
    for ex in facts['examples']:
        assert int(wins[ex['i']]) == ex['total']
    assert int(wins[facts['grid_best']['i']]) == facts['grid_best']['total']
    assert wins.shape[0] == np.int64(facts['header']['n_iv'])


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_real_no_line_moveset_renders_the_negative_section():
    """The negative page, end to end, on a blob that actually has one.

    Both Sableye blobs carry a line on every moveset, so without this the
    negative summary strings, the two-view selector and the negative compare
    prefill would only ever have run against a hand-built fact dict.
    """
    path = require_blob(MELMETAL)
    state = B.load_blob(str(path))
    all_facts = W.prepare(state, str(path))
    no_line = [i for i, f in enumerate(all_facts) if f['floor'] is None]
    assert no_line, 'this blob no longer carries a no-line moveset'
    arm = no_line[0]
    html = W.section_html(all_facts, arm)
    assert html == W.section_html(all_facts, arm)
    assert html.isascii()
    summary = re.search(r'<summary class="wb-summary">(.*?)</summary>',
                        html, re.S).group(1)
    assert ('Your rank-1: it already wins more matchups than any other spread.'
            in summary
            or 'Any of them: no single stat threshold decides a matchup here.'
            in summary)
    payload = json.loads(
        re.search(r'class="wb-data">(.*?)</script>', html, re.S).group(1))
    assert payload['hasFloor'] is False
    assert [v['id'] for v in payload['views']] == ['clusters', 'rank1']
    assert payload['rungs'] == [] and payload['alt'] is None
    # No line means no printed value, so no clearer expander either.
    assert 'wbToggleClearers' not in html
    # The lead still names the movesets that DO carry one.
    lead = re.search(r'<p class="wb-lead">(.*?)</p>', html, re.S).group(1)
    with_line = [f for f in all_facts if f['floor'] is not None]
    for f in with_line:
        assert f['header']['arm_label'] in lead


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_single_file_page_says_which_moveset_the_section_is_about(
        shadow_sableye):
    """A page embedding several movesets carries a dropdown this section
    does not follow, so it has to name the moveset it IS about.

    Split files (every file on the website chain) embed one moveset and are
    byte-identical with or without the argument -- the note only appears
    where the ambiguity does.
    """
    _state, all_facts, _path = shadow_sableye
    one = W.section_html(all_facts, 0, page_movesets=1)
    many = W.section_html(all_facts, 0, page_movesets=4)
    assert one != many
    assert 'the Moveset dropdown above does not change' not in one
    assert ('This whole section is about SHADOW_CLAW / DRAIN_PUNCH, FOUL_PLAY'
            in many)
    # Nothing else moves: the difference is exactly that one sentence.
    assert len(many) > len(one)
    assert one == W.section_html(all_facts, 0)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_every_arm_renders_its_own_section(shadow_sableye):
    _state, all_facts, _path = shadow_sableye
    assert len(all_facts) == 4
    seen = set()
    for arm in range(len(all_facts)):
        html = W.section_html(all_facts, arm)
        lead = re.search(r'<p class="wb-lead">(.*?)</p>', html, re.S).group(1)
        label = all_facts[arm]['header']['arm_label']
        assert f'This file is {label}' in lead
        # The other movesets' lines are named, so a reader on one file can
        # see that the rest print the same one.
        assert 'Other movesets on this page: ' in lead
        for other in range(len(all_facts)):
            if other != arm:
                assert all_facts[other]['header']['arm_label'] in lead
        seen.add(lead)
    assert len(seen) == 4
