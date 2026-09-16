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
  rounding window. The section's own line and its rungs carry one each.
- Rounded cut: the cheaper encoding the per-scenario lines use instead --
  the cut in the page's own 2-dp array plus the indices that comparison gets
  wrong. Equally exact, a float and (so far) an empty list per line.
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
import deep_dive_builds as builds_mod  # noqa: E402


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
                   'species': 'Sableye', 'shadow': True,
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
        'floor_cost': None, 'cluster_corroboration': None,
        '_headline': ['Most X should have at least 148.10 attack. '
                      '2220 of the 4096 IV spreads reach it.',
                      'The stat-product rank-1 spread misses it.'],
    }
    if floor:
        f['floor'] = {'axis': 'atk', 'printed': 148.1, 'dp': 2,
                      'T': 148.1039982, 'cell': '0v1 Annihilape',
                      'n_above': 2220, 'pool_share': 0.542, 'kind': 'exact'}
        f['floor_cost'] = {'best_ivs': (7, 2, 14), 'best_total': 382,
                           'rank1_total': 367, 'net': 15, 'n_tied': 1,
                           'material': False, 'total_cells': 684}
    return f


def _two_movesets(same_line=True):
    """A page with two movesets, for the lead and the summary's clause."""
    a, b = _facts(), _facts()
    b['header'] = dict(b['header'], arm=1,
                       arm_label='SHADOW_CLAW / FOUL_PLAY, POWER_GEM')
    a['header'] = dict(a['header'],
                       arm_label='SHADOW_CLAW / DRAIN_PUNCH, FOUL_PLAY')
    if not same_line:
        b['floor'] = dict(b['floor'], printed=149.2, T=149.2)
    return [a, b]


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


def test_summary_is_a_directive_at_two_places():
    """Not the headline sentence quoted: the value prints at two places and
    the sentence is built from the facts, so a moveset that shares an earlier
    moveset's line still answers the question instead of pointing at another
    file."""
    got = W.summary_sentence(_facts())
    assert got == 'Most Sableye (Shadow) should have at least 148.10 attack.'


def test_summary_drops_the_precision_parenthetical():
    """"123.42 (123.419)" reads as a typo in a one-line summary; the proven
    selector stays in the headline and field 2."""
    f = _facts()
    f['floor'] = dict(f['floor'], printed=123.419, dp=3)
    assert W.printed_value(f['floor']) == '123.42 (123.419)'
    assert '(123.419)' not in W.summary_sentence(f)
    assert '123.42 attack' in W.summary_sentence(f)


def test_summary_prices_a_line_that_costs_a_matchup():
    """The brief keeps its directive while the net loss is immaterial, so a
    reader who reads ONLY the summary would be sent after a line the page's
    own second paragraph prices. The clause is in the same sentence."""
    f = _facts()
    f['floor_cost'] = dict(f['floor_cost'], net=-1, best_total=359,
                           rank1_total=360)
    got = W.summary_sentence(f)
    assert 'should have at least 148.10 attack' in got
    assert 'though rank-1 0/15/15 still wins 1 more matchup overall' in got
    f['floor_cost'] = dict(f['floor_cost'], net=0)
    assert 'already wins as many matchups' in W.summary_sentence(f)


def test_summary_follows_the_brief_when_the_line_is_demoted():
    f = _facts()
    f['floor_cost'] = dict(f['floor_cost'], net=-40, material=True)
    got = W.summary_sentence(f)
    assert got.startswith('Sableye (Shadow) has a line at 148.10 attack')
    assert 'should' not in got


def test_summary_names_the_moveset_on_a_multi_moveset_page():
    """Split files each carry one moveset, so the summary has to say which."""
    pair = _two_movesets(same_line=True)
    got = W.summary_sentence(pair[0], pair)
    assert got.endswith('(the same line as its other 1 movesets).') or \
        '(the same line as its other 1 moveset' in got
    pair = _two_movesets(same_line=False)
    got = W.summary_sentence(pair[0], pair)
    assert '(Drain Punch)' in got, got


def test_summary_on_a_negative_page_says_any_of_them():
    f = _facts(floor=False)
    assert W.summary_sentence(f) == (
        'Any of them: no single stat threshold decides a matchup here.')


def test_summary_on_a_negative_page_defers_to_rank1_when_rank1_wins_most():
    f = _facts(floor=False)
    f['grid_best']['total'] = f['rank1']['total_won']
    assert W.summary_sentence(f) == (
        'Your rank-1: it already wins more matchups than any other spread.')


def test_summary_does_not_claim_a_strict_win_when_the_top_is_tied():
    """"more matchups than any other spread" is a strict claim, and the same
    fact dict says how many spreads share the top count."""
    f = _facts(floor=False)
    f['grid_best']['total'] = f['rank1']['total_won']
    f['grid_best']['n_tied'] = 3
    assert W.summary_sentence(f) == (
        'Any of them: no single stat threshold decides a matchup here.')


def test_compare_prefill_is_rank1_then_the_example_spreads():
    got = W.compare_spreads(_facts())
    assert [iv for _rule, iv in got] == [[0, 15, 15], [6, 9, 7], [10, 13, 11],
                                         [7, 2, 14]]
    assert got[0][0] == 'rank-1'


def test_compare_prefill_carries_the_spread_the_headline_names():
    """The headline names the spread that clears the line and wins the most;
    the example rules' stat-product filter can exclude it, and a reader who
    clicked Compare after reading that sentence did not find it."""
    got = W.compare_spreads(_facts())
    assert got[-1] == ('wins the most matchups above the line', [7, 2, 14])
    # ...and not twice, when an example already names it.
    f = _facts()
    f['examples'] = f['examples'] + [{'ivs': [7, 2, 14], 'level': 49.5,
                                      'rule': 'bulkiest'}]
    ivs = [iv for _rule, iv in W.compare_spreads(f)]
    assert ivs.count([7, 2, 14]) == 1


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


def test_term_marker_orders_by_reading_order_not_by_claim_order():
    """The Terms list is in the order a reader MEETS the terms.

    Pre-fix the offset was read off the partially-marked working copy, so a
    term claimed later by _TERM_PATTERNS but sitting earlier in the sentence
    carried the length of every tooltip inserted before it and sorted after
    the term it precedes. The builds lead has exactly that shape.
    """
    m = W.TermMarker()
    m.mark('<p>Build criteria: what these builds guarantee, over 87 '
           'decision matchups</p>')
    order = m.ordered()
    assert order.index('guaranteed') < order.index('decision matchup')
    assert order.index('build criteria') < order.index('guaranteed')


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


def test_lead_is_two_sentences_in_the_pages_own_words():
    """Round 1 opened with "All 4 movesets rendered here carry a build line.
    This file is SHADOW_CLAW / DRAIN_PUNCH, FOUL_PLAY at Atk >= 148.10" --
    three pieces of internal vocabulary before the reader reaches a number."""
    pair = _two_movesets(same_line=True)
    out = W.lead_sentences(pair, 0)
    assert len(out) == 2
    assert out[0] == ('All 2 movesets on this page share one line: at least '
                      '148.10 attack.')
    assert out[1] == ('This page is Drain Punch, at least 148.10 attack; '
                      'Power Gem prints the same line.')
    for sentence in out:
        for banned in ('rendered here', 'this file', 'build line', 'Atk >='):
            assert banned not in sentence, (banned, sentence)


def test_lead_names_only_what_differs_when_the_lines_differ():
    pair = _two_movesets(same_line=False)
    out = W.lead_sentences(pair, 1)
    assert out[0] == 'All 2 movesets on this page carry a line, at different values.'
    assert out[1] == ('This page is Power Gem, at least 149.20 attack; '
                      'Drain Punch is at least 148.10 attack.')


def test_lead_falls_back_to_full_labels_when_short_names_collide():
    """Two movesets that differ only in the FAST move share every charged
    move, so there is no distinguishing charged slot to name."""
    a, b = _facts(), _facts()
    a['header'] = dict(a['header'], arm_label='SHADOW_CLAW / FOUL_PLAY')
    b['header'] = dict(b['header'], arm=1, arm_label='ASTONISH / FOUL_PLAY')
    assert W.short_movesets([a, b]) == ['Shadow Claw / Foul Play',
                                        'Astonish / Foul Play']


def test_lead_on_a_single_moveset_page_is_one_sentence():
    out = W.lead_sentences([_facts()], 0)
    assert len(out) == 1
    assert out[0].startswith('The only moveset on this page is ')


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


# The rung ramp is generated per page now, so the palette guards below cover
# EVERY length a page can ask for rather than a fixed six. RAMP_LENGTHS spans
# one rung (a page whose floor owns the only clean cut) to twelve (past
# anything in the corpus: the longest ladder in the two Sableye blobs is 7).
RAMP_LENGTHS = range(1, 13)


def _theme_colors(kind):
    """Every color the section can paint in one theme kind, ramp included."""
    light, dark = _palette_blocks()
    out = dict(dark if kind == 'dark' else light)
    for n in RAMP_LENGTHS:
        for k, value in enumerate(W.rung_ramp(n, kind)):
            out[f'ramp{n}-r{k}'] = value
    return out


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
    assert len(light) == len(dark) >= 5, (len(light), len(dark))
    assert set(light) == set(dark)
    fills = dict(zip(theme._THEME_ORDER, theme._TOKENS['--surface-2']))
    bad = []
    for name, fill in fills.items():
        kind = 'dark' if name.endswith('dark') else 'light'
        for token, value in _theme_colors(kind).items():
            r = _contrast(value, fill)
            if r < 3.0:
                bad.append((name, token, value, round(r, 2)))
    assert bad == [], bad


def test_every_rung_gets_its_own_color():
    """A fixed six-color ramp painted the 6th and 7th rung of a seven-rung
    page identically -- on the one view whose whole encoding IS color, and on
    three of the five preview pages. The ramp is generated for the number of
    rungs the page prints."""
    for kind in ('light', 'dark'):
        for n in RAMP_LENGTHS:
            ramp = W.rung_ramp(n, kind)
            assert len(ramp) == n, (kind, n)
            assert len(set(ramp)) == n, (kind, n, ramp)
    assert W.rung_ramp(0) == []


def test_ramp_css_declares_one_property_per_rung_in_both_themes():
    css = W.ramp_css(7)
    for k in range(7):
        assert css.count(f'--wb-r{k}:') == 2, k       # light + dark
    assert '--wb-r7' not in css
    assert 'gruvbox-dark' in css and 'pokemon-dark' in css
    assert W.ramp_css(0) == ''
    # The payload's fallback ramp is the light block, same pinned-copy rule
    # the engine's WB_FALLBACK follows.
    light = re.findall(r'--wb-r\d+: (#[0-9a-fA-F]{6})',
                       css[:css.index('[data-theme=')])
    assert light == W.rung_ramp(7, 'light')


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
    assert len(got) >= 5


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
    for palette in (_theme_colors('light'), _theme_colors('dark')):
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
    assert light and dark


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
    """The color mode a reader selected owns the top of the canvas.

    Same treatment the tier traces already had. This is a z-order fix only:
    what made C0 isolate to an EMPTY plot is pinned by the two tests below.
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


def test_legend_hover_resolves_the_trace_plotly_bound_not_the_dom_position():
    """The bug behind the empty C0.

    Measured on a rendered preview page in headless Chrome: the main scatter
    in cluster color mode had 7 traces and 6 legend rows, and legend row 4
    ("C0") addressed trace 4 -- the note key -- so hovering C0 brightened an
    invisible trace and dimmed C0 itself to 0.03. Both legend wirings now
    read the trace index Plotly bound to the node.
    """
    src = _engine()
    assert 'function _legendTraceIndex(' in src
    # The main scatter: hover, leave and click all go through the resolver.
    main = src[src.index('function reattachLegendHandlers('):
               src.index('window.updateView = updateView;')]
    assert 'highlightTrace(idx)' not in main, \
        'the main legend still highlights by DOM position'
    assert main.count('_legendTraceIndex(el, idx)') >= 2
    # The section panel wires the same way.
    panel = src[src.index('function _wbWireLegend('):
                src.index('function wbRenderRoot(')]
    assert '_legendTraceIndex(el, idx)' in panel
    assert '(j === idx)' not in panel


def test_the_cluster_note_key_carries_a_point_so_it_gets_a_legend_entry():
    """Plotly builds the legend from calcdata: a trace with no points gets no
    entry at all. That silently dropped the "Matchup clusters: <scenario>"
    note AND put every later legend row out of step with its trace. One null
    point renders nothing and legends normally (verified in 2.35.2)."""
    # strip_js blanks string literals, so the note key is located by its
    # structure (the first ctr.push in the cluster branch), not by its text.
    src = _engine()
    note = src[src.index('ctr.push({'):src.index('for (var c0 = 0;')]
    assert 'x: [null], y: [null]' in note, note[:400]
    assert 'hoverinfo:' in note
    # The cluster traces keep their legend position even though they now draw
    # last, so the reader's chosen color mode still reads first.
    assert 'legendrank: 100' in note
    assert 'legendrank: 101 + c0' in src


def test_section_panel_reads_the_page_arrays_and_embeds_no_second_grid():
    src = _engine()
    # Wins are counted from the embedded score grid, over every scenario and
    # every opponent -- the brief's own denominator.
    wins = src[src.index('function wbWins('):src.index('function _wbColors(')]
    assert 'SCORES[mi + SCORE_KEY_SEP + mode]' in wins
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


def test_collection_overlay_is_nudged_off_the_population_point():
    """An svg/gl marker at the EXACT coordinates of a scattergl point loses
    the hover contest (3 of 24 stars hovered as the wrong spread when the
    cluster panel shipped without the nudge), and then "Yours: <mon>" never
    appears. Same 0.05%-of-range nudge as the cluster panels and the main
    scatter."""
    src = _engine()
    owned = src[src.index('function _wbOwnedTrace('):
                src.index('function _wbWireLegend(')]
    assert 'ynudge' in owned
    assert 'oy.push(wins[i] + ynudge)' in owned
    assert '* 0.0005' in owned
    # Positive control: the precedent it copies is still there -- the
    # cluster panels' own star overlay, which measured the hover loss.
    assert src.count('* 0.0005') >= 2


def test_panel_legends_speak_the_sections_vocabulary_not_the_audits():
    """"cells", "clearers" and "SP" are what the brief's voice gate keeps out
    of the prose this legend sits under."""
    py = (SCRIPTS_DIR / 'deep_dive_which_build.py').read_text()
    assert W.example_label('most cells won among clearers with SP >= 95%') == \
        'most contested matchups won above the line, stat product >= 95%'
    assert W.example_label('bulkiest (max Def x HP) among clearers with '
                           'SP >= 95%') == \
        'bulkiest above the line, stat product >= 95%'
    assert W.example_label('highest stat product clearing the floor') == \
        'highest stat product above the line'
    # An unmapped rule falls through rather than being dropped.
    assert W.example_label('some new rule') == 'some new rule'
    assert 'label' in py[py.index("pay['examples'] = ["):
                         py.index("pay['examples'] = [") + 400]
    src = _engine()
    assert 'pay.examples[e].label' in src
    assert "'Example: ' + pay.examples[e].rule" not in src


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
// Two scenarios x two opponents, which is the SAME flat (iv, scenario,
// opponent) layout as the one-scenario grid this harness started with -- the
// score bytes below are unchanged -- and it lets the section's own Shield
// scenario control be exercised for real rather than pinned in source.
const DATA = {
  nIvs: N, nScenarios: 2, nOpponents: 2, scenarioLabels: ['0v0', '1v1'],
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
function scenLabel(si) { return DATA.scenarioLabels[si]; }
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
eval(block + '\nout = {wbWins, _wbGroups, wbLevelArrays, _wbIvIdx, _wbHover, _wbMask, _wbBit, _wbOwnedTrace, _wbClusterSides, _wbScen, _wbActiveLine, _wbSideAt, _wbOn};');

// Masks are LSB-first per byte, exactly as deep_dive_which_build.mask_b64
// packs them: 'PA==' = 0b00111100 = spreads 2..5, 'MA==' = spreads 4..5,
// 'Aw==' = spreads 0..1. They deliberately DISAGREE with a naive compare
// against the page's 2-dp stats for spread 2 (atk 148.2 rounds the same way
// either side of the line), which is the whole reason the mask exists.
const pay = {
  mi: 0, mode: 'pvpoke', hasFloor: true, axis: 'atk', axisWord: 'attack',
  T: 148.1039982, printed: '148.10', cell: '0v1 X', nAbove: 4, topN: 25,
  rank1: {iv: [0,15,15], level: 50}, gridBest: {iv:[5,10,10], level:50},
  examples: [{iv:[2,13,13], level:50, rule:'r', label:'reader label'}],
  rungColors: ['#6','#7'],
  rungs: [{axis:'atk', T:148.1039982, n:4, mask:'PA==', label:'148.10 (a)',
           full:'148.10 (a (Sucker Punch / Night Slash))'},
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

const line = out._wbGroups(pay, 'line', L, wins, {line:'#1',below:'#2',alt:'#3',mark1:'#4',mark2:'#5',rungs:['#6','#7'],scenRungs:['#8','#9','#a','#b']});
const byName = {}; line.traces.forEach(t => byName[t.name.replace(/ \(\d+\)$/,'')] = t.x.length);
eq('line groups', byName, {'Below the line': 2, 'At or above the line': 4});

const rungs = out._wbGroups(pay, 'rungs', L, wins, {line:'#1',below:'#2',alt:'#3',mark1:'#4',mark2:'#5',rungs:['#6','#7'],scenRungs:['#8','#9','#a','#b']});
const rn = {}; rungs.traces.forEach(t => rn[t.name.replace(/ \(\d+\)$/,'')] = t.x.length);
// atk 140,145 below; 148.2,149 -> rung0; 150.5,151 -> rung1
eq('rung groups', rn, {'Below the line': 2, '148.10 (a)': 2, '150.00 (b)': 2});
// A rung key carries NO '(N)': every count in the prose above is cumulative
// and a drawn rung group is exclusive, so the same label would carry two
// different numbers on one screen.
rungs.traces.forEach(t => { if (/^1\d\d\./.test(t.name) && / \(\d+\)$/.test(t.name))
  fail.push('rung key carries a band count: ' + t.name); });
// The hover names the opponent in full even though the key drops the
// moveset-variant parenthetical.
const rh = rungs.traces.find(t => t.name.indexOf('148.10 (a)') === 0).text[0];
if (rh.indexOf('Sucker Punch') < 0) fail.push('rung hover lost the full name');

const trade = out._wbGroups(pay, 'trade', L, wins, {line:'#1',below:'#2',alt:'#3',mark1:'#4',mark2:'#5',rungs:['#6','#7'],scenRungs:['#8','#9','#a','#b']});
const tn = {}; trade.traces.forEach(t => tn[t.name.replace(/ \(\d+\)$/,'')] = t.x.length);
// idx0 (def110,hp130) and idx1 (def105,hp128) qualify for the rectangle and are below the line
eq('trade groups', tn, {'Neither': 0, 'At or above the line': 4, 'Bulk alternative, below the line: Def >= 105, HP >= 128': 2});
// Hover word order: "attack at or above the 148.10 line", not "at or above
// attack 148.10".
const lineTrace = line.traces.find(t => t.name.indexOf('At or above') === 0);
if (lineTrace.text[0].indexOf('attack at or above the 148.10 line') < 0)
  fail.push('line hover reads backwards: ' + lineTrace.text[0]);
// The mask, not the rounded stats: spread 2 sits inside the 2-dp rounding
// window and is a clearer only because the mask says so.
eq('mask bit 2 is a clearer', out._wbBit(out._wbMask('PA=='), 2), 1);
eq('mask bit 1 is not', out._wbBit(out._wbMask('PA=='), 1), 0);

const clusters = out._wbGroups(pay, 'clusters', L, wins, {line:'#1',below:'#2',alt:'#3',mark1:'#4',mark2:'#5',rungs:['#6','#7'],scenRungs:['#8','#9','#a','#b']});
eq('clusters missing when no mc payload', clusters.missing, true);

// Cluster keys say which side of the clusters section's own split they sit
// on when that section printed no iff rule -- 'C0 (n=...)' alone is two
// colors with no stat meaning under a caption about a split.
const sc = {k: 2, sizes: [3, 3], split: 'atk 148.68', rules: [null, null],
            labels: [0,0,0,1,1,1]};
const sides = out._wbClusterSides(sc, L);
eq('cluster side 0', sides[0].label, 'mostly below atk 148.68');
eq('cluster side 1', sides[1].label, 'mostly at or above atk 148.68');
if (sides[1].hover.indexOf('%') < 0) fail.push('cluster side hover has no share');
eq('no split, no side labels', out._wbClusterSides({k:2, split:null}, L), null);

// The collection overlay nudges off the population point, or its hover
// loses the contest with the scattergl trace under it.
state.ownedByIv = {2: [{mon: {name: 'Sab'}, stats: {cp: 1495}}]};
const owned = out._wbOwnedTrace(pay, L, wins);
state.ownedByIv = null;
if (!owned) fail.push('no owned trace');
else {
  if (!(owned.y[0] > wins[2])) fail.push('owned star is not nudged: ' + owned.y[0]);
  if (owned.y[0] - wins[2] > 0.01) fail.push('owned nudge is visible: ' + owned.y[0]);
  if (owned.text[0].indexOf('Yours: Sab') !== 0) fail.push('owned hover does not name the mon');
}

eq('ivIdx', out._wbIvIdx([2,13,13]), 2);
eq('ivIdx missing', out._wbIvIdx([9,9,9]), -1);
if (out._wbHover(2, L, wins, 'side').indexOf('2/13/13') !== 0) fail.push('hover ivs');
if (out._wbHover(2, L, wins, 'side').indexOf('wins 3 of 4') < 0) fail.push('hover wins');

// ---- the section's own Shield scenario control -------------------------
const COL = {line:'#1',below:'#2',alt:'#3',mark1:'#4',mark2:'#5',rungs:['#6','#7'],scenRungs:['#8','#9','#a','#b']};
// 'OA==' = 0b00111000 = spreads 3..5 (atk >= 149), 'MA==' = spreads 4..5
// (atk >= 150.5): the same LSB-first packing deep_dive_which_build.mask_b64
// emits, pooled by (axis, value) the way the payload pools them.
// A scenario line carries a CUT in the page's own 2-dp array plus the
// indices that comparison gets wrong, not a packed mask: atk >= 149 is
// spreads 3..5 and atk >= 150.5 is 4..5 on this grid. Spread 2's `wrong`
// entry is the rounding hazard made explicit -- 148.2 is below 149 but this
// line claims it, and the payload says so rather than hoping.
const scenPay = Object.assign({}, pay, {
  scenLabels: ['0v0', '1v1'],
  scen: {
    '0v0': {lines: [], degenerate: false,
            captions: {line: 'nothing in 0v0', rungs: 'nothing in 0v0'}},
    '1v1': {lines: [
        {axis:'atk', axisWord:'attack', printed:'149.00', n:3, kind:'exact',
         cut:149, wrong:[], isFloor:false, label:'149.00 (c)', full:'149.00 (c)'},
        {axis:'atk', axisWord:'attack', printed:'150.50', n:2, kind:'exact',
         cut:150.5, wrong:[], isFloor:false, label:'150.50 (d)', full:'150.50 (d)'}],
      degenerate: false, captions: {line: 'lowest in 1v1', rungs: 'two in 1v1'}},
  }});
// The exception list is what makes the cheap encoding exact: with spread 2
// listed, the line owns it even though the page's rounded stat is below the
// cut -- and unlisted, it does not.
eq('cut alone sides spread 2 below',
   out._wbOn(L, {axis:'atk', cut:149, wrong:[]}, 2), 0);
eq('the exception list flips it',
   out._wbOn(L, {axis:'atk', cut:149, wrong:[2]}, 2), 1);
eq('a mask line still reads its mask',
   out._wbOn(L, {mask:'PA=='}, 2), 1);
function fakeRoot(v) {
  return { querySelector: (s) => (s === 'select.wb-scen' ? {value: v} : null) };
}
eq('control default is every scenario', out._wbScen(fakeRoot('all'), scenPay), null);
eq('control resolves a label to its grid index',
   out._wbScen(fakeRoot('1v1'), scenPay).idx, 1);
eq('control ignores a label this page does not carry',
   out._wbScen(fakeRoot('9v9'), scenPay), null);

const s1 = {idx: 1, label: '1v1', entry: scenPay.scen['1v1']};
const s0 = {idx: 0, label: '0v0', entry: scenPay.scen['0v0']};
const w1 = out.wbWins(0, 'pvpoke', 1);
const w0 = out.wbWins(0, 'pvpoke', 0);
eq('per-scenario wins, 1v1', Array.from(w1), [0,0,1,2,2,2]);
eq('per-scenario wins, 0v0', Array.from(w0), [1,2,2,2,2,2]);
eq('every-scenario wins are unchanged', Array.from(out.wbWins(0, 'pvpoke')),
   [1,2,3,4,4,4]);

const sr = out._wbGroups(scenPay, 'rungs', L, w1, COL, s1, 2);
const srn = {}; sr.traces.forEach(t => srn[t.name.replace(/ \(\d+\)$/,'')] = t.x.length);
eq('scenario rung groups', srn,
   {'Below 149.00 (c)': 3, '149.00 (c)': 1, '150.50 (d)': 2});
const slv = out._wbGroups(scenPay, 'line', L, w1, COL, s1, 2);
const sln = {}; slv.traces.forEach(t => sln[t.name.replace(/ \(\d+\)$/,'')] = t.x.length);
eq('the line view draws only the lowest line in the scenario', sln,
   {'Below 149.00 (c)': 3, 'At or above 149.00 (c)': 3});
const slt = slv.traces.find(t => t.name.indexOf('At or above') === 0);
// The denominator is the opponent pool, not scenarios x opponents...
if (slt.text[0].indexOf('wins 2 of 2') < 0)
  fail.push('scenario hover denominator: ' + slt.text[0]);
// ...and the side string names the line being drawn, not the page's.
if (slt.text[0].indexOf('attack at or above the 149.00 line') < 0)
  fail.push('scenario side string: ' + slt.text[0]);
const srh = sr.traces.find(t => t.name.indexOf('150.50 (d)') === 0);
if (srh.text[0].indexOf('highest line cleared: 150.50 (d)') < 0)
  fail.push('scenario rung hover: ' + srh.text[0]);

// A scenario with no line is a muted grid carrying every spread, not an
// empty panel: the caption is the only thing that says why.
const g0 = out._wbGroups(scenPay, 'line', L, w0, COL, s0, 2);
eq('muted grid is one group', g0.traces.length, 1);
eq('muted grid holds every spread', g0.traces[0].x.length, 6);
if (g0.traces[0].text[0].indexOf('no line in 0v0 shields') < 0)
  fail.push('muted hover: ' + g0.traces[0].text[0]);

// The trade is a whole-grid trade and does not move with the control.
const tr1 = out._wbGroups(scenPay, 'trade', L, w1, COL, s1, 2);
const tr1n = {}; tr1.traces.forEach(t => tr1n[t.name.replace(/ \(\d+\)$/,'')] = t.x.length);
eq('trade is whole-grid under a scenario', tr1n, tn);

// The marked spreads and the collection overlay follow the drawn line.
eq('active line under a scenario', out._wbActiveLine(scenPay, s1).printed, '149.00');
eq('active line under all scenarios', out._wbActiveLine(scenPay, null).printed, '148.10');
eq('no active line where the scenario has none',
   out._wbActiveLine(scenPay, s0), null);
if (out._wbSideAt(L, out._wbActiveLine(scenPay, s1), 2)
      .indexOf('attack below the 149.00 line') < 0)
  fail.push('marked-spread side under a scenario');

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
# 4c. v4: the builds half, executed
# ---------------------------------------------------------------------------

_BUILDS_HARNESS = r"""// Node harness: the builds view's grouping + the weighted win count.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const start = src.indexOf('function _wbRoot()');
const end = src.indexOf('// ---- Re-theme the canvases');
if (start < 0 || end < 0 || end <= start) { console.error('MARKERS'); process.exit(2); }
const block = src.slice(start, end);

const N = 6;
const DATA = {
  nIvs: N, nScenarios: 2, nOpponents: 2, scenarioLabels: ['0v0', '1v1'],
  ivA: [0,1,2,3,4,5], ivD: [15,14,13,12,11,10], ivS: [15,14,13,12,11,10],
  ivAtk: [140,145,148.2,149,150.5,151], ivDef: [110,105,101.5,100,99,98],
  ivHp: [130,128,126,124,122,120], ivLv: [50,50,50,50,50,50],
  spRanks: [1,2,3,4,5,6], ivL51: null,
};
// Flat (iv, scenario, opponent): iv0 wins one 0v0 cell, iv1 wins both 0v0,
// iv2 adds a 1v1, and iv3..5 win everything.
const SCORES = { '0|pvpoke': new Uint16Array([
  600,400,400,400,  600,600,400,400,  600,600,600,400,
  600,600,600,600,  600,600,600,600,  600,600,600,600]) };
const SCORE_KEY_SEP = '|';
function isWin(v) { return v > 500; }
function scenLabel(si) { return DATA.scenarioLabels[si]; }
function wrapLegendName(n) { return n; }
function plotChrome() { return {ink:'#000', paper:'', plot:'', font:'', grid:'',
  legendBg:'', legendBorder:'', hoverBg:'', hoverBorder:''}; }
function _mcPayloadPage() { return null; }
function _mcLabelsApply() { return false; }
const state = { ownedByIv: null };
const _bbL50 = null;
const window = {};
const document = { getElementById: () => null, addEventListener: () => {},
                   querySelector: () => null, querySelectorAll: () => [] };
const location = { hash: '' };
const history = { replaceState: () => {} };
const Plotly = { react: () => {}, restyle: () => {}, Plots: { resize: () => {} } };
const getComputedStyle = () => ({ getPropertyValue: () => '' });

let out;
eval(block + '\nout = {wbWinsWeighted, wbWeightedDen, _wbBuildOf, _wbBuildSide,' +
     ' _wbGuaranteedInScen, _wbBuildGroups, _wbBuildName, wbPresetBlock,' +
     ' wbLevelArrays, wbWins};');

// Two builds: spreads 0..1 (mask 'Aw==' = 0b00000011) and spreads 4..5
// ('MA==' = 0b00110000). Region guarantee bits are over the decision-cell
// axis below: region 0 guarantees cells 0 and 2, region 1 cell 1.
const bp = {
  mi: 0, mode: 'pvpoke', default: 'flat', presetKeys: ['flat', 'one_one'],
  nDecision: 3, nMaterial: 1, nOpp: 2, topN: 25, colors: ['#a','#b','#c'],
  scenLabels: ['0v0', '1v1'],
  cells: [[0, 5, 1], [1, 9, 0], [0, 12, 0]],
  regions: [{size: 2, nG: 2, nGmat: 1, bits: 'BQ==', mask: 'Aw=='},
            {size: 2, nG: 1, nGmat: 0, bits: 'Ag==', mask: 'MA=='}],
  rank1: {iv: '0/15/15@50', idx: 0, wins: 1},
  gridBest: {iv: '5/10/10@50', idx: 5, wins: 4},
  presets: {
    flat: {label: 'All shields, equal', tag: 'all shields, equal',
           weights: [1, 1], scens: ['0v0', '1v1'], summary: 'S-flat',
           builds: [{role: 'primary', combo: 'A', col: 0, region: 0, size: 2,
                     desc: 'd0', nG: 2, nGw: 2, nGmat: 1,
                     mostWinning: {iv: '1/14/14@50', idx: 1, wins: 2}},
                    {role: 'fork', combo: 'B', col: 1, region: 1, size: 2,
                     desc: 'd1', nG: 1, nGw: 1, nGmat: 0,
                     mostWinning: {iv: '4/11/11@50', idx: 4, wins: 4}}],
           cols: [], lattice: []},
    one_one: {label: '1v1 only', tag: '1v1 only', weights: [0, 1],
              scens: ['1v1'], summary: 'S-one',
              builds: [{role: 'primary', combo: 'B', col: 0, region: 1,
                        size: 2, desc: 'd1', nG: 1, nGw: 1, nGmat: 0,
                        mostWinning: {iv: '4/11/11@50', idx: 4, wins: 2}}],
              cols: [], lattice: []}
  }
};
const pay = {mi: 0, mode: 'pvpoke', hasFloor: false, views: [], bp: bp,
             rank1: {iv: [0,15,15], level: 50}, gridBest: {iv: [5,10,10], level: 50},
             examples: [], rungs: []};
const L = out.wbLevelArrays();
const fail = [];
function eq(name, got, want) {
  if (JSON.stringify(got) !== JSON.stringify(want))
    fail.push(name + ': got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want));
}

// 1. the weighted win count. All-ones must equal the unweighted count, and
// the 1v1-only vector must equal that scenario's own slice.
eq('flat weights == every scenario',
   Array.from(out.wbWinsWeighted(0, 'pvpoke', [1, 1])),
   Array.from(out.wbWins(0, 'pvpoke', null)));
eq('1v1 weights == the 1v1 slice',
   Array.from(out.wbWinsWeighted(0, 'pvpoke', [0, 1])),
   Array.from(out.wbWins(0, 'pvpoke', 1)));
eq('weighted denominator', out.wbWeightedDen([0, 1]), 2);
eq('flat denominator', out.wbWeightedDen([1, 1]), 4);

// 2. membership, from the packed masks
const flat = bp.presets.flat;
eq('membership', [0,1,2,3,4,5].map(i => out._wbBuildOf(bp, flat, i)),
   [0, 0, -1, -1, 1, 1]);

// 3. the guarantee bits, read per shield scenario
eq('region 0 guarantees in 0v0', out._wbGuaranteedInScen(bp, 0, 0), 2);
eq('region 0 guarantees in 1v1', out._wbGuaranteedInScen(bp, 0, 1), 0);
eq('region 1 guarantees in 1v1', out._wbGuaranteedInScen(bp, 1, 1), 1);

// 4. the hover text: counts, and the scenario-scoped form when one is picked
const side = out._wbBuildSide(pay, flat, 0, null);
if (side.indexOf('guarantees 2 of 3 decision matchups') < 0)
  fail.push('build hover lost its counts: ' + side);
const sideScen = out._wbBuildSide(pay, flat, 0, {idx: 0, label: '0v0'});
if (sideScen.indexOf('2 decision matchups in 0v0 shields') < 0)
  fail.push('scenario hover is not scenario-scoped: ' + sideScen);
if (out._wbBuildSide(pay, flat, -1, null).indexOf('none of the builds') < 0)
  fail.push('a spread in no build is not said to be in none');

// 5. the grouping: one trace per build plus the grey remainder, every spread
// drawn exactly once.
const wins = out.wbWinsWeighted(0, 'pvpoke', [1, 1]);
const g = out._wbBuildGroups(pay, L, wins, {below: '#z', line: '#y'}, 4,
                             {querySelector: () => null}, null);
const counts = {};
g.traces.forEach(t => { counts[t.name.replace(/ \(\d+\)$/, '')] = t.x.length; });
eq('every spread drawn once',
   g.traces.reduce((a, t) => a + t.x.length, 0), N);
if (!Object.keys(counts).some(k => k.indexOf('Build 1 (primary)') === 0))
  fail.push('no primary trace: ' + JSON.stringify(Object.keys(counts)));
if (counts['In no build'] !== 2)
  fail.push('the remainder trace is wrong: ' + JSON.stringify(counts));

// 6. wbPresetBlock falls back to the payload default with no knob on the page
eq('default preset block', out.wbPresetBlock(pay).summary, 'S-flat');

if (fail.length) { console.error(fail.join('\n')); process.exit(1); }
console.log('OK');
"""


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_builds_view_logic_runs(tmp_path):
    """Run the builds view's own code for real, on a 6-spread synthetic grid.

    Source pins cannot catch a spread landing in the wrong build, a weighted
    win count that ignores its weights, or a guarantee-bit read that is off
    by a cell -- all three of which a reader would see as a wrong picture
    with no error anywhere.
    """
    runner = tmp_path / 'wb_builds_check.js'
    runner.write_text(_BUILDS_HARNESS)
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
    # Two maps now: the rendered sections and the presets each arm's
    # section actually built (the controls strip's Build-criteria dropdown
    # lists the second, so a dive that produced no builds offers no knob).
    assert deep_dive._which_build_sections({}) == ({}, {})


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
    # One 512-byte mask per printed rung plus one for the bulk pair, and
    # (v4) the builds half: one mask per selected region, the guarantee bits
    # of every candidate region, and the per-preset facts and sentences for
    # all three presets. Still far below the point where a per-IV STAT array
    # would have been cheaper. Measured 34 KB on this blob when v4 shipped.
    assert len(json.dumps(payload)) < 48_000, len(json.dumps(payload))
    # The builds half is the part that would grow if a member LIST ever
    # replaced a packed mask.
    assert len(json.dumps(payload['bp'])) < 24_000, len(json.dumps(payload['bp']))


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
    # v4: the summary names the PRIMARY BUILD under the default preset, and
    # self-labels the preset it was selected under. The line is still the
    # headline's own opening sentence, asserted below.
    assert '[all shields, equal]' in summary
    assert '61 spreads' in summary and '55 of the 87 decision matchups' in summary
    assert 'disjoint 114-spread build' in summary
    # The line itself is still the headline's opening sentence -- with the
    # printed value wrapped in the clearers button, which is why this looks
    # for the two halves rather than the whole phrase.
    assert 'should have at least ' in html
    assert '>148.10</button> attack' in html
    # A literal space between the title and the sentence: copy/paste, a
    # screen reader and this test all read the runs with nothing between
    # them otherwise ("build?Most Sableye").
    assert '</b> <span class="wb-head">' in summary
    # Display spelling, not gamemaster ids, on the most visible line of the
    # page -- the header two inches above says "Shadow Claw / Drain Punch".
    assert 'SHADOW_CLAW' not in summary
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
    'Stat-product rank against matchups won with PvPoke-default opponent '
    'IVs at the league cap over the whole opponent pool and, with Shield '
    'scenario on all, every baked shield state -- the view the line above '
    'was derived on. The Shield scenario selector on this row is the '
    "section's own; the scatter's dropdowns and the opponent filter do not "
    'drive this panel.',
    'Compare these spreads',
    'All 4 movesets on this page share one line: at least 148.10 attack.',
    'Show: ',
    'Shield scenario: ',
    'Terms used here',
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
    # The note is element TEXT, so its apostrophe ships escaped; compare
    # what a reader reads.
    html = W.section_html(all_facts, 0).replace('&#x27;', "'")
    for chunk in _SECTION_CHROME:
        assert chunk in html, chunk
    ctx = {'blob': 'test', 'arm': 0, 'mode': 'pvpoke'}
    B.gate_words(list(_SECTION_CHROME) + [W.CLUSTERS_FALLBACK_CAPTION], ctx)
    B.gate_caveat(list(_SECTION_CHROME) + [W.CLUSTERS_FALLBACK_CAPTION], ctx)
    # prepare() runs the same two gates over every string this module
    # authors, the clusters fallback caption included: it is a constant on a
    # live branch (no corroboration sentence to quote), and a gate that only
    # fires on the pages that reach the branch is a gate that ships the bad
    # string. 'partition', the first draft's word, is barred by G-voice.
    B.gate_voice([W.CLUSTERS_FALLBACK_CAPTION], ctx)
    with pytest.raises(B.GuardError):
        B.gate_voice(['the partition of this grid'], ctx)
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
    # v4: the builds view leads even here -- a page with no single-stat line
    # still has regions of the grid worth aiming at -- and the two
    # line-derived views are still absent. The SUMMARY stays the negative
    # one, asserted above.
    assert [v['id'] for v in payload['views']] == ['builds', 'clusters', 'rank1']
    assert payload['rungs'] == [] and payload['alt'] is None
    # No line means no printed value, so no clearer expander either.
    assert 'wbToggleClearers' not in html
    # The lead still names the movesets that DO carry one, in the page's
    # own spelling (the distinguishing charged move, or the full label).
    lead = re.search(r'<p class="wb-lead">(.*?)</p>', html, re.S).group(1)
    names = W.short_movesets(all_facts)
    for i, f in enumerate(all_facts):
        if f['floor'] is not None:
            assert names[i] in lead, (names[i], lead)
    assert 'carries no line' in lead or 'carry no line' in lead
    assert '_' not in lead, 'a raw gamemaster id reached the lead'


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
    assert ('This whole section is about Shadow Claw / Drain Punch, Foul Play'
            in many)
    assert 'SHADOW_CLAW' not in many[many.index('wb-fixed'):
                                     many.index('wb-fixed') + 600]
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
        names = W.short_movesets(all_facts)
        assert f'This page is {names[arm]}' in lead
        # The other movesets' lines are named, so a reader on one file can
        # see that the rest print the same one.
        assert 'print the same line' in lead
        for other in range(len(all_facts)):
            if other != arm:
                assert names[other] in lead
        # Reader vocabulary: no "file", no "build line", no raw ids.
        for banned in ('this file', 'build line', 'rendered here', '_'):
            assert banned not in lead, (banned, lead)
        seen.add(lead)
    assert len(seen) == 4
    # Each split file's SUMMARY answers the question itself rather than
    # pointing at a moveset on another file.
    for arm in range(len(all_facts)):
        html = W.section_html(all_facts, arm)
        summary = re.search(r'<summary class="wb-summary">(.*?)</summary>',
                            html, re.S).group(1)
        assert 'Same line as' not in summary
        # v4: every split file answers with its own builds, under the
        # default preset, rather than pointing at another file's moveset.
        assert '[all shields, equal]' in summary
        assert 'decision matchups' in summary


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_seven_rung_arm_paints_every_rung_its_own_color(shadow_sableye):
    """The ramp is generated for the page's OWN rung count.

    Shadow Sableye moveset 2 prints seven rungs; with the old fixed six-color
    ramp the 6th and 7th were painted identically -- on the view whose entire
    encoding is color, and the larger of the two groups was the biggest on
    the panel.
    """
    _state, all_facts, _path = shadow_sableye
    counts = []
    for arm in range(len(all_facts)):
        html = W.section_html(all_facts, arm)
        payload = json.loads(
            re.search(r'class="wb-data">(.*?)</script>', html, re.S).group(1))
        n = len(payload['rungs'])
        counts.append(n)
        # The payload's fallback ramp and the emitted CSS both have exactly
        # one color per rung, and no two the same.
        assert len(payload['rungColors']) == n
        assert len(set(payload['rungColors'])) == n
        css = html[html.index('<style>'):html.index('</style>')]
        for k in range(n):
            assert f'--wb-r{k}:' in css
        assert f'--wb-r{n}:' not in css
        # ...and the rung keys are distinct strings too, so two groups can
        # never read as one.
        labels = [r['label'] for r in payload['rungs']]
        assert len(set(labels)) == n, labels
    assert max(counts) >= 7, counts


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_terms_used_here_prints_the_registry_once(shadow_sableye):
    """A phone reader never sees a title= tooltip: no hover, <abbr> takes no
    focus, and the guide links navigate away rather than define. The same
    registry sentences are printed once at the foot of the section."""
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    import html as _h
    assert '<p class="wb-terms-head">Terms used here</p>' in html
    block = html[html.index('<p class="wb-terms-head">'):]
    block = _h.unescape(block[:block.index('</dl>')])
    marked = [_h.unescape(t) for t in
              re.findall(r'<abbr class="wb-term" title="([^"]*)"', html)]
    assert marked, 'the section marked no terms at all'
    for title in set(marked):
        # Every term the marker used is defined once in the list, in the
        # registry's own words -- and the definition is not typed twice.
        assert block.count(title) == 1, title
        assert title in glossary.TERMS.values()
    # One row per marked term, in the order a reader met them.
    names = re.findall(r'<dt>(?:<a[^>]*>)?([^<]+)', block)
    assert len(names) == len(set(marked)) == len(marked)
    assert [glossary.TERMS[n.lower()] for n in names] == marked


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_shared_line_moveset_states_the_line_and_counts_it_once(
        shadow_sableye):
    """Moveset 2+ of a page opens "Same line as <another file's moveset>",
    which is a reference, not an answer -- and the spread extension then
    printed the reach count twice, once as a total and once as a remainder."""
    _state, all_facts, _path = shadow_sableye
    first = W.extended_first_sentence(all_facts[1])
    assert 'reached by 2220' in first
    assert first.count('2220') == 1
    assert 'other spreads reach' not in first
    html = W.section_html(all_facts, 1)
    summary = re.search(r'<summary class="wb-summary">(.*?)</summary>',
                        html, re.S).group(1)
    # v4: the summary is this moveset's own builds sentence; the shared-line
    # clause it used to carry is in the headline, which this test's first
    # half already reads.
    assert '[all shields, equal]' in summary
    assert 'decision matchups' in summary
    assert 'Same line as' not in summary


# ---------------------------------------------------------------------------
# 6. The section's own Shield scenario control
# ---------------------------------------------------------------------------
#
# Vocabulary for this group: a SCENARIO LINE is one value in the brief's
# exact / gate / near-exact cut ladder whose cell sits in ONE shield scenario
# and whose pool share is inside the decision band -- the narrower question
# the control asks. The page's own line is a whole-grid claim and does not
# move with the control.

def _fn_body(raw, stripped, name):
    """One JS function's RAW source, located on the STRIPPED source.

    The boundaries are found on the stripped text, so a function name inside
    a comment or a string cannot move them; the slice is then taken from the
    raw text at the same offsets (strip_js preserves them), because what this
    group asserts about is which DOM selector STRINGS a handler touches.
    """
    start = stripped.index('function ' + name + '(')
    nxt = stripped.find('\nfunction ', start + 1)
    end = len(stripped) if nxt < 0 else nxt
    return raw[start:end]


def test_js_wires_the_sections_own_scenario_control():
    src = _engine()
    wins = src[src.index('function wbWins('):src.index('var WB_ALL_SCEN')]
    # The scenario slice is a BOUND on the same loop, not a second decoding:
    # the section and the main plot must count a win the same way.
    assert 'function wbWins(mi, mode, si)' in src
    assert 'si == null' in wins and 'si + 1' in wins
    assert 'isWin(' in wins
    scen = src[src.index('function _wbScen('):src.index('function _wbColors(')]
    # The label -> index lookup goes through the page's own scenLabel(), so
    # the option the reader picks and the grid slice it selects cannot drift.
    assert 'scenLabel(si)' in scen
    assert 'WB_ALL_SCEN' in scen
    groups = src[src.index('function _wbGroups('):
                 src.index('function _wbClusterSides(')]
    assert 'function _wbGroups(pay, view, L, wins, colors, scen, den)' in src
    assert '_wbOn(L, use[sk], i)' in groups
    assert '_wbMutedTrace(' in groups
    # The clusters view follows the control to THAT scenario's labels.
    assert 'scen ? scen.label' in groups
    render = src[src.index('function wbRenderRoot('):
                 src.index('function wbSelectView(')]
    assert 'wbWins(pay.mi, pay.mode, scen ? scen.idx : null)' in render
    assert 'DATA.nOpponents' in render and 'scen.label' in render
    assert 'scen.entry.captions[view]' in render


def test_the_js_all_scenarios_label_matches_the_renderers():
    """One spelling of the "every scenario" option, on both sides."""
    raw = ENGINE_JS.read_text()
    assert f"var WB_ALL_SCEN = '{W.ALL_SCEN}';" in raw


def test_the_control_moves_the_panel_and_nothing_else():
    """The handler may touch the plot, its caption and its own selectors.

    The collapsed summary line and the headline paragraphs are the
    ALL-scenario verdict; a control that rewrote them would make the one
    sentence a reader reads depend on a dropdown they may never touch.

    v4 adds two panels the Shield-scenario control legitimately re-renders
    -- the UpSet matrix beside the plot and the visible preset block's
    member lists -- and nothing else. The scan now catches
    ``querySelectorAll`` too: the v4 render path reaches its new nodes that
    way, and a scan blind to it would have let the summary line be rewritten
    from ``querySelectorAll('.wb-head')`` without a word.
    """
    raw = ENGINE_JS.read_text()
    stripped = _engine()
    body = (_fn_body(raw, stripped, 'wbRenderRoot')
            + _fn_body(raw, stripped, 'wbSelectView')
            + _fn_body(raw, stripped, 'wbFillMembers')
            + _fn_body(raw, stripped, '_wbScen'))
    touched = set(re.findall(r"querySelector(?:All)?\(\s*'([^']+)'", body))
    assert touched == {'.wb-panel', '.wb-caption', 'select.wb-view',
                       'select.wb-scen', '.wb-upset', '.wb-upset-caption',
                       '.wb-preset:not([hidden]) .wb-mem'}, touched
    # Positive control: the scan sees the selectors that ARE there, so an
    # empty match set cannot pass this silently.
    assert '.wb-panel' in touched
    for banned in ('.wb-summary', '.wb-head', '.wb-headline', '.wb-clearers',
                   '.wb-fixed', '.wb-terms'):
        assert banned not in body, banned
    # wbSelectView is the only thing the two <select>s call, and all it does
    # is re-render the panel.
    sel = _fn_body(raw, stripped, 'wbSelectView')
    assert 'wbRenderRoot(root)' in sel
    assert 'textContent' not in sel and 'innerHTML' not in sel


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_scenario_control_markup_is_all_then_the_grid_order(shadow_sableye):
    state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    block = re.search(r'<select class="wb-scen".*?</select>', html, re.S)
    assert block, 'no Shield scenario control on the selector row'
    opts = re.findall(r'<option value="([^"]+)"([^>]*)>([^<]*)</option>',
                      block.group(0))
    values = [v for v, _a, _t in opts]
    assert values[0] == W.ALL_SCEN
    assert ' selected' in opts[0][1], 'every-scenario is not the default'
    assert all(' selected' not in a for _v, a, _t in opts[1:])
    # The nine scenarios, in the grid's own order, in the page's own
    # vocabulary (deep_dive_rendering.scenario_label).
    assert values[1:] == [B.scenario_label(state, si)
                          for si in range(len(state['shield_scenarios']))]
    assert values[1:] == ['0v0', '0v1', '0v2', '1v0', '1v1', '1v2',
                          '2v0', '2v1', '2v2']
    assert 'Shield scenario: ' in html
    # It sits on the section's OWN row, beside Show:, not in the page's
    # scatter controls.
    row = re.search(r'<div class="wb-controls">.*?</div>', html, re.S).group(0)
    assert 'wb-view' in row and 'wb-scen' in row


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_per_scenario_lines_pin_the_shadow_sableye_ladder(shadow_sableye):
    """The values each shield scenario turns a matchup over at.

    Recorded here as the numbers, not as "whatever the code produces": the
    0v1 line IS the page's own line, 1v1 carries the mirror and the Shadow
    Feraligatr steps, and 2v1's cuts all sit outside the decision band so it
    has none.
    """
    _state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    pay = W.build_payload(facts, facts['_fields'], 0, all_facts=all_facts)
    got = {k: [l['label'] for l in v['lines']] for k, v in pay['scen'].items()}
    assert got['0v1'] == ['148.10 (Annihilape +2)']
    assert pay['scen']['0v1']['lines'][0]['isFloor'] is True
    assert pay['scen']['0v1']['lines'][0]['printed'] == pay['printed']
    assert got['1v1'] == ['148.55 (Sableye (Shadow))',
                          '148.71 (Feraligatr (Shadow))',
                          '149.68 (Hippowdon)',
                          '150.24 (Empoleon (Shadow))']
    assert got['2v2'] == ['148.71 (Feraligatr (Shadow))',
                          '150.60 (Tinkaton)']
    assert got['0v0'] == ['148.77 (Araquanid)']
    assert got['1v0'] == ['148.18 (Feraligatr)']
    assert got['1v2'] == ['148.63 (Wartortle)']
    # 2v1's Thievul / Florges cuts are real and 86.8% of the grid already
    # clears them, so they are not build decisions and not lines here.
    assert got['0v2'] == [] and got['2v1'] == [] and got['2v0'] == []
    assert pay['scen']['2v0']['degenerate'] is True
    assert pay['scen']['2v1']['degenerate'] is False
    # Ascending, and inside the band the brief selects a line from.
    lo, hi = pay['band']
    for lbl, entry in pay['scen'].items():
        vals = [float(l['printed']) for l in entry['lines']]
        assert vals == sorted(vals), lbl
    for row in (facts['scenario_lines']['1v1']['lines']):
        assert lo <= row['pool_share'] <= hi


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_scenario_with_no_line_says_so_and_names_the_closest_rule(
        shadow_sableye):
    _state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    pay = W.build_payload(facts, facts['_fields'], 0, all_facts=all_facts)
    for view in ('line', 'rungs'):
        cap = pay['scen']['2v1']['captions'][view]
        assert 'No attack, defense or HP threshold in 2v1 shields' in cap
        assert 'The nearest, 155.43 attack (Forretress (Bug Bite)),' in cap
        # With its numbers, both of them: the value and how much of the grid
        # is on its passing side -- AND which side of the band it missed on,
        # in words, so the percentage is not doing all the work.
        assert re.search(r'\d+ of \d+ spreads \(\d', cap), cap
        assert 'too little of the grid' in cap, cap
        # The degenerate scenario states its absence in the Matchup clusters
        # section's own sentence and its own numbers -- not in a second set
        # the reader would have to reconcile with it.
        degen = pay['scen']['2v0']['captions'][view]
        assert degen == (
            'In 2v0 shields little turns on IVs at all: every spread wins '
            '74-76 of 76 opponents here, so the IV choice moves at most 2 '
            'matchups in this shield state. There is no line to draw.'), degen
        assert 'closest' not in degen and 'nearest' not in degen
    # A scenario that HAS a line names it and what it decides.
    one = pay['scen']['1v1']['captions']['line']
    assert one.startswith('At or above 148.55 attack every spread wins '
                          'Sableye (Shadow) in 1v1 shields')
    assert pay['scen']['1v1']['captions']['rungs'].startswith(
        '4 attack thresholds each turn a matchup over in 1v1 shields, from '
        '148.55 (Sableye (Shadow)) up to 150.24 (Empoleon (Shadow))')
    # The scope of a scenario line, stated once per caption.
    assert one.endswith(W.SCOPE_CLAUSE)
    # ... and NOT on the one scenario whose line IS the page's line, which
    # the gates did run on.
    floor_cap = pay['scen']['0v1']['captions']['line']
    assert not floor_cap.endswith(W.SCOPE_CLAUSE), floor_cap
    assert floor_cap.endswith("These are the same 2220 spreads as this "
                              "page's line."), floor_cap
    # The trade is a whole-grid trade and says so rather than being rewritten.
    trade_all = next(v['caption'] for v in pay['views'] if v['id'] == 'trade')
    assert pay['scen']['1v1']['captions']['trade'] == (
        trade_all + ' Counted over every shield scenario; the y-axis here is '
        '1v1 wins only.')


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_scenario_lines_carry_a_cut_and_its_exceptions_not_a_mask(
        shadow_sableye):
    """No per-IV array, packed or otherwise, enters through this control.

    A scenario line ships a cut in the page's OWN 2-dp array plus the indices
    that comparison gets wrong. The exceptions are what make it exact; they
    are empty on this grid, and the test recomputes the split from the cut to
    prove the browser will draw what the brief measured.
    """
    import numpy as np
    state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    pay = W.build_payload(facts, facts['_fields'], 0, all_facts=all_facts)
    rows = [l for e in pay['scen'].values() for l in e['lines']]
    assert len(rows) == 10, rows          # ten lines across the nine scenarios
    assert 'lineMasks' not in pay
    blob = json.dumps(pay['scen'])
    assert 'mask' not in blob
    _scores, meta = B.arm_view(state, 0, 'pvpoke')
    atk, dfn, hp = B.stat_planes(meta)
    planes = {'atk': atk, 'def': dfn, 'hp': hp}
    exceptions = 0
    for row in rows:
        plane = planes[row['axis']]
        rounded = W.page_rounded(plane, row['axis'])
        side = rounded >= row['cut']
        for i in row['wrong']:
            side[i] = not side[i]
        assert int(side.sum()) == row['n'], (row['label'], int(side.sum()))
        # ...and the reconstructed set IS the brief's set, spread for spread,
        # not merely the same size.
        T = next(r['T'] for e in facts['scenario_lines'].values()
                 for r in e['lines']
                 if W._axis_value(r) == row['printed']
                 and r['axis'] == row['axis'])
        assert np.array_equal(side, plane >= T), row['label']
        exceptions += len(row['wrong'])
    # Recorded, not required: if this stops being zero the encoding still
    # works, it just costs more.
    assert exceptions == 0, exceptions
    # A line whose count disagrees with the brief's is refused, not drawn.
    bad = dict(facts)
    bad['scenario_lines'] = {
        '1v1': {'lines': [{'axis': 'atk', 'T': 148.5539982, 'n_pass': 7,
                           'printed': 148.55}], 'closest': None,
                'degenerate': False}}
    with pytest.raises(ValueError):
        W.compute_masks(state, 0, bad, 'pvpoke', 'l50')


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_rounded_cut_reproduces_the_full_precision_split(shadow_sableye):
    """The encoding, against the hazard it has to survive.

    Comparing the page's 2-dp array against the RAW threshold mis-sides 19 of
    the 4096 Shadow Sableye spreads -- that is why the section's own line
    carries a mask. Comparing it against the lowest rounded value a clearer
    displays does not, and rounded_cut reports any spread it would.
    """
    import numpy as np
    state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    _scores, meta = B.arm_view(state, 0, 'pvpoke')
    atk, _d, _h = B.stat_planes(meta)
    T = facts['floor']['T']
    naive = int(((np.round(atk, 2) >= T) != (atk >= T)).sum())
    assert naive == 19, naive          # the hazard, still live on this grid
    cut, wrong = W.rounded_cut(atk, 'atk', T)
    side = np.round(atk, 2) >= cut
    for i in wrong:
        side[i] = not side[i]
    assert np.array_equal(side, atk >= T)
    assert int(side.sum()) == facts['floor']['n_above'] == 2220


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_every_scenario_caption_passes_the_briefs_word_gates(shadow_sableye):
    _state, all_facts, _path = shadow_sableye
    ctx = {'blob': 'test', 'arm': 0, 'mode': 'pvpoke'}
    blocks = []
    for facts in all_facts:
        for scen, entry in facts['scenario_lines'].items():
            for view in ('line', 'rungs', 'clusters', 'rank1'):
                blocks.append(W.scenario_caption(view, scen, entry, facts))
    assert len(blocks) >= 4 * 9
    assert all(b and b[-1] == '.' for b in blocks)
    B.gate_words(blocks, ctx)
    B.gate_caveat(blocks, ctx)
    B.gate_voice(blocks, ctx)
    # Positive control: the same gates still fail on a bad string.
    with pytest.raises(B.GuardError):
        B.gate_words(blocks + ['this is the best line'], ctx)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_control_leaves_the_summary_and_the_headline_alone(shadow_sableye):
    """The all-scenario verdict is baked once and is not per-scenario.

    Nothing in the payload's per-scenario block can reach the summary or the
    headline: those are rendered as text, the control's handler never
    rewrites them (see test_the_control_moves_the_panel_and_nothing_else),
    and the payload does not carry a second copy of either.
    """
    _state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    pay = W.build_payload(facts, facts['_fields'], 0, all_facts=all_facts)
    summary = W.summary_sentence(facts, all_facts)
    blob = json.dumps(pay['scen'])
    assert summary not in blob
    for para in facts['_headline']:
        assert para not in blob
    html = W.section_html(all_facts, 0)
    head = html[:html.index('<div class="wb-plotbox">')]
    assert 'wb-scen' not in head, 'the control is emitted above the panel'


def test_a_single_scenario_marks_only_rank1():
    """No example spread is labelled against a line the panel is not drawing.

    Every example key is named for where the spread sits relative to the
    PAGE's line ("highest stat product above the line"), and under a single
    shield scenario the two threshold views draw a DIFFERENT line. Both
    halves of that go wrong on screen:

    * on a scenario with NO line the keys claim one exists;
    * on a scenario WITH one the marker is plotted inside the "Below
      <scenario line>" group while its own key says "above the line" -- on
      Shadow Sableye 1v1, 6/9/7 (148.23 atk) and 10/13/11 (148.19 atk) both
      sit below the 148.55 scenario line and both carried "above the line"
      keys.

    So the examples are dropped for ANY single scenario on those two views.
    Rank-1 stays: its key claims nothing about any line.
    """
    # The raw body, located on the stripped source: the pins below are about
    # view NAMES, which strip_js blanks out.
    render = _fn_body(ENGINE_JS.read_text(), _engine(), 'wbRenderRoot')
    assert ("var hideExamples = !!(scen && (view === 'line' || "
            "view === 'rungs'));") in render
    # The '&& !line' that used to gate this is GONE: that is the whole fix,
    # and a positive control for the pin above (a revert re-introduces it).
    assert "|| view === 'rungs') && !line" not in render
    assert 'hideExamples ? false : e < pay.examples.length' in render
    assert 'pay.bestAbove && !hideExamples' in render
    # ...and the side string names the scenario only when the PAGE has a line
    # to contrast it with. On a negative page the absence is the page's, and
    # the selected scenario may well carry a threshold of its own.
    assert '(line ? _wbSideAt(L, line, r1i) : noLine)' in render
    assert ("var noLine = (scen && pay.hasFloor)\n"
            "                    ? ('no line in ' + scen.label + ' shields')"
            ) in render


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_negative_page_carries_the_control_and_its_captions():
    """Melmetal Great League: the section's own control on a no-line page.

    Arm 0 prints no line at all, so the two threshold views do not exist and
    the control drives the y-axis, the clusters view and the caption. Arm 2
    DOES print one, and most of its shield scenarios still have no line of
    their own -- which is the case the captions have to say out loud.
    """
    path = require_blob(MELMETAL)
    state = B.load_blob(str(path))
    all_facts = W.prepare(state, str(path))
    neg = all_facts[0]
    assert neg['floor'] is None
    pay = W.build_payload(neg, neg['_fields'], 0, all_facts=all_facts,
                          arm_builds=neg.get('_builds'))
    assert [v['id'] for v in pay['views']] == ['builds', 'clusters', 'rank1']
    assert len(pay['scen']) == len(state['shield_scenarios'])
    for lbl, entry in pay['scen'].items():
        assert entry['lines'] == []
        assert set(entry['captions']) == {'builds', 'clusters', 'rank1'}
        assert lbl in entry['captions']['rank1']
    html = W.section_html(all_facts, 0)
    assert 'Shield scenario: ' in html
    assert f'<option value="{W.ALL_SCEN}" selected>' in html

    # The arm that DOES carry a line: 1v1 has one, most scenarios do not.
    pos = all_facts[2]
    assert pos['floor'] is not None
    pay2 = W.build_payload(pos, pos['_fields'], 0, all_facts=all_facts,
                           arm_builds=pos.get('_builds'))
    withline = [k for k, v in pay2['scen'].items() if v['lines']]
    assert '1v1' in withline
    assert len(withline) < len(pay2['scen']), 'expected empty scenarios here'
    empty = next(k for k, v in pay2['scen'].items() if not v['lines'])
    cap = pay2['scen'][empty]['captions']['rungs']
    assert ('No attack, defense or HP threshold' in cap
            or 'little turns on IVs at all' in cap), cap
    assert 'The nearest, ' in cap

    # A degenerate scenario that DOES carry an in-band cut says both things.
    # G-scenario is a hard exclusion for the page's line and is applied to
    # nothing here, so without this the panel claimed a threshold decides
    # matchups in a shield state the clusters view calls dead two clicks away.
    deg = pay2['scen']['2v0']
    assert deg['degenerate'] and deg['lines'], deg
    dcap = deg['captions']['line']
    assert dcap.startswith('Every spread at or above 122.54 attack wins '
                           'Charjabug in 2v0 shields'), dcap
    assert ('In 2v0 shields little turns on IVs at all: every spread wins '
            '73-76 of 76 opponents here, so the IV choice moves at most 3 '
            'matchups in this shield state.') in dcap, dcap

    # The NEGATIVE arm's rank-1 caption names the scenario's own threshold
    # where it has one -- that page offers neither threshold view, so this is
    # the only place a reader asking "is there really nothing, even in one
    # shield state?" can be answered.
    ncap = pay['scen']['1v0']['captions']['rank1']
    assert ('1v0 shields does carry a threshold of its own: at or above '
            '122.01 attack every spread wins Hippowdon, and below it none '
            'does.') in ncap, ncap
    assert "It is not this page's line" in ncap
    # ...and stays silent where the scenario has none.
    assert 'carry a threshold of its own' not in (
        pay['scen']['1v1']['captions']['rank1'])


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_section_is_byte_deterministic_with_the_control(shadow_sableye):
    """Two renders of one blob stay identical with the control's payload in.

    The per-scenario block is a dict keyed by scenario label and a pooled
    list of masks; both are emitted through the same sort_keys dump as the
    rest, so a set-iteration order cannot leak into the page bytes.
    """
    _state, all_facts, _path = shadow_sableye
    a = W.section_html(all_facts, 0)
    b = W.section_html(all_facts, 0)
    assert a == b
    assert a.isascii()
    pay = json.loads(
        re.search(r'class="wb-data">(.*?)</script>', a, re.S).group(1))
    # Small: ten lines, nine pooled masks and a caption per view per
    # scenario -- not a per-IV array per scenario. Plus the v4 builds half;
    # the per-scenario block itself is unchanged and is capped separately
    # below, so this cap moving cannot hide growth in it.
    assert len(json.dumps(pay)) < 48_000, len(json.dumps(pay))
    assert len(json.dumps(pay['scen'])) < 12_000, len(json.dumps(pay['scen']))


# ---------------------------------------------------------------------------
# 5b. Round 4: one ladder, one axis, one number per threshold
# ---------------------------------------------------------------------------

SABLEYE_PLAIN = '20260911_051621_Sableye_great.replay.pkl.gz'


@pytest.fixture(scope='module')
def sableye_plain():
    path = require_blob(SABLEYE_PLAIN)
    state = B.load_blob(str(path))
    return state, W.prepare(state, str(path)), str(path)


@pytest.mark.local_artifacts
@pytest.mark.slow
@pytest.mark.parametrize('blob', [SABLEYE_SHADOW, SABLEYE_PLAIN, MELMETAL])
def test_every_scenario_ladder_is_one_axis_and_nests(blob):
    """The drawn rungs are a NESTING claim, so they have to actually nest.

    The panel colors a spread "by the highest line it clears" and prints one
    grey key, "Below <the lowest line>", for everything else. Both are only
    true of a ladder on ONE axis: ``atk >= 123.92`` and ``def >= 119.55`` do
    not nest in either direction, and on Sableye GL 1v1 the two sets differ
    by 1295 spreads each way -- so a mixed ladder colored a quarter of the
    grid as clearing a rung under a grey key saying it was below the line.

    Recomputed here from the blob's own stat planes, not from the payload's
    counts: this is the invariant the encoding rests on.
    """
    import numpy as np
    path = require_blob(blob)
    state = B.load_blob(str(path))
    all_facts = W.prepare(state, str(path))
    seen_multi = 0
    for arm, facts in enumerate(all_facts):
        _scores, meta = B.arm_view(state, arm, 'pvpoke', level='l50')
        atk, dfn, hp = B.stat_planes(meta)
        planes = {'atk': atk, 'def': dfn, 'hp': hp}
        for scen, entry in (facts.get('scenario_lines') or {}).items():
            rows = entry['lines']
            axes = {r['axis'] for r in rows}
            assert len(axes) <= 1, (blob, arm, scen, axes)
            masks = [planes[r['axis']] >= r['T'] for r in rows]
            for k in range(1, len(masks)):
                assert masks[k - 1][masks[k]].all(), (
                    f"{blob} arm {arm} {scen}: rung {k} is not inside rung "
                    f"{k - 1}")
            if len(rows) > 1:
                seen_multi += 1
            # Off-axis lines are on OTHER stats, in the band, and named --
            # never silently dropped.
            for o in entry['off_axis']:
                assert o['axis'] not in axes, (blob, arm, scen)
                cap = W.scenario_caption('rungs', scen, entry, facts)
                assert o['names'][0].split(' ', 1)[-1] in cap, cap
                assert 'not a rung of this ladder' in cap or (
                    'not rungs of this ladder' in cap), cap
    # Floors set BELOW today's counts (9 / 19 / 1 across the three blobs), so
    # the nesting assertion cannot pass by finding nothing to assert on.
    floor = {SABLEYE_SHADOW: 6, SABLEYE_PLAIN: 2, MELMETAL: 1}[blob]
    assert seen_multi >= floor, (blob, seen_multi)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_off_axis_line_is_stated_not_ranked(sableye_plain):
    """Sableye GL 1v1: the exact case the mixed ladder got wrong.

    Four attack lines and one defense line. The ladder is the four; the
    defense line is a sentence of its own, in its own primitive's words.
    """
    _state, all_facts, _path = sableye_plain
    facts = all_facts[0]
    entry = facts['scenario_lines']['1v1']
    assert [r['printed'] for r in entry['lines']] == [123.92, 123.97,
                                                      124.74, 125.2]
    assert [(r['axis'], r['printed']) for r in entry['off_axis']] == [
        ('def', 119.55)]
    cap = W.scenario_caption('rungs', '1v1', entry, facts)
    assert cap.startswith(
        '4 attack thresholds each decide a matchup in 1v1 shields '
        '(3 outright, 1 in one direction only), from 123.92 '
        '(Feraligatr (Shadow)) up to 125.20 (Empoleon (Shadow)); each '
        'spread is colored by the highest it clears.'), cap
    assert ('At or above 119.55 defense every spread wins Toxapex in 1v1 '
            'shields, and below it none does. That is a defense line, not a '
            'rung of this ladder.') in cap, cap
    # The "line" view draws the lowest of the LADDER, not the lowest number.
    lcap = W.scenario_caption('line', '1v1', entry, facts)
    assert lcap.startswith('At or above 123.92 attack'), lcap
    assert 'It is the lowest of 4 attack lines in 1v1 shields.' in lcap


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_floor_prints_one_value_everywhere_on_the_page(sableye_plain):
    """Sableye GL: the floor needs three places, and says so once.

    Stage 7 escalated this line to 123.419 because two places could not
    select its 2220 spreads; the headline speaks it "123.42 (123.419)". The
    scenario ladder printed the same T freshly and got "123.41", so the panel
    and the paragraph above it disagreed about the value of the line they
    both describe.
    """
    _state, all_facts, _path = sableye_plain
    facts = all_facts[0]
    fl = facts['floor']
    assert (fl['printed'], fl['dp']) == (123.419, 3)
    floor_rows = [r for e in facts['scenario_lines'].values()
                  for r in e['lines'] + e['off_axis'] if r['is_floor']]
    assert len(floor_rows) >= 2, floor_rows
    for r in floor_rows:
        assert (r['printed'], r['dp']) == (fl['printed'], fl['dp']), r
        assert W._axis_value(r) == W.plain_value(fl) == '123.42'
        assert W.scen_line_label('0v0', r).startswith('123.42 ('), r
    # And the tail is a statement about the SET, not about the cell: the 0v0
    # owner (Marowak) is not the cell the strip names as deciding the line.
    cap = W.scenario_caption('line', '0v0', facts['scenario_lines']['0v0'],
                             facts)
    assert cap.startswith('At or above 123.42 attack every spread wins '
                          'Marowak in 0v0 shields'), cap
    assert "These are the same 2220 spreads as this page's line." in cap
    assert "It is this page's own line" not in cap


@pytest.mark.local_artifacts
@pytest.mark.slow
@pytest.mark.parametrize('blob', [SABLEYE_SHADOW, SABLEYE_PLAIN, MELMETAL])
def test_no_shipped_closest_rule_is_one_every_spread_clears(blob):
    """"The closest rule" has to have somebody on both sides of it.

    Shadow Sableye 2v0 named "92.68 defense (Moltres (Galarian)), which 4096
    of 4096 spreads (100.0%) clear" -- a sentence shaped like a finding about
    a threshold nobody can miss. Those are dropped from the candidate pool
    now; the caption says which side of the band the survivor missed on.
    """
    path = require_blob(blob)
    state = B.load_blob(str(path))
    all_facts = W.prepare(state, str(path))
    n_iv = int(all_facts[0]['header']['n_iv'])
    seen = 0
    for facts in all_facts:
        for scen, entry in (facts.get('scenario_lines') or {}).items():
            c = entry.get('closest')
            if c is None:
                continue
            seen += 1
            assert 0 < int(c['n_pass']) < n_iv, (blob, scen, c)
            if entry['lines'] or entry['degenerate']:
                continue
            cap = W.scenario_caption('rungs', scen, entry, facts)
            assert 'The nearest, ' in cap, cap
            assert ('too little of the grid' in cap
                    or 'too much of the grid' in cap
                    or 'on the wrong side of it' in cap), cap
    # Floors BELOW today's counts (7 / 3 / 25), so the assertions above
    # cannot pass by finding no closest rule to check.
    floor = {SABLEYE_SHADOW: 4, SABLEYE_PLAIN: 2, MELMETAL: 15}[blob]
    assert seen >= floor, (blob, seen)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_shadow_sableye_2v0_closest_rule_is_gone(shadow_sableye):
    """The concrete case: every 2v0 candidate is vacuous, so none is named."""
    _state, all_facts, _path = shadow_sableye
    entry = all_facts[0]['scenario_lines']['2v0']
    assert entry['closest'] is None, entry['closest']
    cap = W.scenario_caption('line', '2v0', entry, all_facts[0])
    assert 'Moltres' not in cap and '100.0%' not in cap, cap


def test_a_scenario_group_takes_its_name_from_the_cell_it_quotes():
    """The claim and the name come from the SAME cell.

    The caption's primitive, gate side and counts are the representative
    cell's (strongest primitive first); the name used to be ``cells[0]`` --
    pool insertion order. A group with no exact cut in it, mixing a
    near-exact and a gate, printed the gate's stronger claim ("No spread
    below V wins X") under the near-exact cell's name, for which it is false.

    Synthetic, because no shipped page reaches that shape: every group on the
    three preview blobs contains an exact cut, which sorts first either way.
    """
    import numpy as np
    n_iv = 100
    atk = np.arange(n_iv, dtype=float)
    planes = {'atk': atk, 'def': atk.copy(), 'hp': atk.copy()}
    win = np.zeros((n_iv, 1, 2), dtype=bool)
    win[50:, 0, 0] = True
    state = {'shield_scenarios': [(0, 0)]}
    triage = {'degenerate': {0: False}}

    def cell(label, kind, gate_side, oi):
        return {'si': 0, 'oi': oi, 'axis': 'atk', 'T': 50.0, 'n_pass': 50,
                'kind': kind, 'gate_side': gate_side, 'label': label,
                'n_above': 50, 'n_win_above': 50, 'n_below': 50,
                'n_win_below': 0, 'n_wrong': 3, 'rank': 1}
    # Insertion order puts the NEAR-EXACT cell first; the gate is the rep.
    pool = [cell('0v0 Wrong', 'near_exact', 'both', 0),
            cell('0v0 Right', 'gate', 'necessary', 1)]
    out = B.scenario_lines(pool, win, planes, triage, [], {}, state, n_iv,
                           None)
    row = out['0v0']['lines'][0]
    assert row['kind'] == 'gate'
    assert row['names'][0] == '0v0 Right', row['names']
    assert 'No spread below 50.00 attack wins Right' in (
        W._decides_sentence('0v0', row))


def test_js_draws_a_scenario_ladder_on_its_own_colour_ramp():
    """A scenario's ladder can be LONGER than the page's own rung ladder.

    Read off ``--wb-r*`` (sized to ``pay.rungs.length``), the overflow rungs
    fell back to one colour and two steps of an encoding whose whole content
    is colour became indistinguishable. ``--wb-s*`` is sized server-side to
    the longest ladder the control can select, and is separate so that
    lengthening it does not re-colour the default view's rungs.
    """
    raw, src = ENGINE_JS.read_text(), _engine()
    colors = _fn_body(raw, src, '_wbColors')
    assert "'--wb-s' + k2" in colors
    assert 'pay.scenColors' in colors and 'pay.nScenRamp' in colors
    assert 'scenRungs: sramp' in colors
    groups = _fn_body(raw, src, '_wbGroups')
    assert 'colors.scenRungs[k] ||' in groups
    # ...and the page's own ramp is still sized to the page's own rungs.
    assert 'pay.rungs.length : 0' in colors


def test_the_two_colour_ramps_are_sized_independently():
    """Extending the scenario ramp must not move the printed rungs."""
    assert W.ramp_css(3) == W.ramp_css(3, 'r')
    assert '--wb-r0' in W.ramp_css(3) and '--wb-s0' in W.ramp_css(3, 's')
    # The page ramp for n rungs is byte-identical however long the scenario
    # ramp is -- they are two calls, not one stretched over both.
    assert W.rung_ramp(3) != W.rung_ramp(6)[:3], 'ramp is length-dependent'
    assert W.ramp_css(0, 's') == ''


def test_js_caption_enrichment_is_scenario_only():
    """The two captions the JS extends, and the state it must not touch.

    Under "all" the section renders exactly what Python wrote -- the round-2
    pin -- so both additions are inside a ``scen &&`` guard.
    """
    render = _fn_body(ENGINE_JS.read_text(), _engine(), 'wbRenderRoot')
    assert "if (scen && view === 'rank1')" in render
    assert "if (scen && view === 'clusters')" in render
    # The clusters caption carries that scenario's own K and its depth-1
    # split as the clusters payload spells it -- this file formats no
    # threshold.
    assert 'msc.k' in render and 'msc.split' in render
    assert 'toFixed' not in render
    # The clusters section's `display` already carries the word "shields";
    # appending a second one printed "for 0v1 shields shields" in the
    # browser, which is what the headless probe caught.
    assert "(msc.display || (scen.label + ' shields')) + \": \"" in render
    assert '+ " shields: "' not in render
    # ...and only where those labels describe what the panel is drawing. The
    # clusters section bakes for moveset 0 at the default opponent-IV mode;
    # on any other page the view draws nothing, so the caption must not
    # describe groups the reader cannot see. One predicate, both callers.
    assert '_wbMcApplies(pay, mcP)' in render
    src_raw = ENGINE_JS.read_text()
    assert src_raw.count('function _wbMcApplies(') == 1
    assert src_raw.count('_wbMcApplies(') == 4, 'view + both caption branches'
    assert 'pay.mi === 0 &&' in _fn_body(src_raw, _engine(), '_wbMcApplies')
    # The rank-1 caption's two integers come off the wins array the panel is
    # already plotting.
    assert 'wins[r1x]' in render and 'the most any spread wins is' in render


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_payload_scenario_keys_are_the_pages_own_vocabulary(
        shadow_sableye):
    """``_wbScen`` fails OPEN: a label it cannot match renders "all".

    The lookup string-matches the selected option against
    ``DATA.scenarioLabels``, so if the payload's keys and the page's labels
    ever drift the panel silently draws the all-scenario view while the
    selector still reads "1v1". Nothing else pins the two vocabularies
    against each other, so this does -- against ``deep_dive.py``'s own
    expression, not against a copy of it.
    """
    import deep_dive_rendering
    state, all_facts, _path = shadow_sableye
    pay = W.build_payload(all_facts[0], all_facts[0]['_fields'], 0,
                          all_facts=all_facts)
    page_labels = [deep_dive_rendering.scenario_label(s)
                   for s in state['shield_scenarios']]
    assert list(pay['scen'].keys()) == page_labels
    assert page_labels == [B.scenario_label(state, si)
                           for si in range(len(state['shield_scenarios']))]
    # The source the labels come from on the page, so a renamed helper fails
    # here rather than in a browser.
    src = (SCRIPTS_DIR / 'deep_dive.py').read_text()
    assert "'scenarioLabels': [scenario_label(s) for s in shield_scenarios]" \
        in src


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_page_rounded_matches_the_array_the_page_actually_embeds(
        shadow_sableye):
    """The exactness guard has to be a CROSS-implementation check.

    ``compute_masks`` asserts that its own rounded array reconstructs the
    brief's split -- but it rounds with numpy while ``deep_dive.py`` embeds
    ``[round(m[5], 2) for m in meta]``, Python's own round. If the two ever
    disagreed on a value the guard would still pass and the browser would
    mis-colour that spread. This runs deep_dive.py's expression against the
    same meta and compares element for element.
    """
    import numpy as np
    state, _all_facts, _path = shadow_sableye
    _scores, meta = B.arm_view(state, 0, 'pvpoke', level='l50')
    atk, dfn, hp = B.stat_planes(meta)
    page_atk = [round(m[5], 2) for m in meta]        # deep_dive.py:1451
    page_def = [round(m[6], 2) for m in meta]
    assert np.array_equal(W.page_rounded(atk, 'atk'), np.array(page_atk))
    assert np.array_equal(W.page_rounded(dfn, 'def'), np.array(page_def))
    assert np.array_equal(W.page_rounded(hp, 'hp'), hp)


def test_the_degenerate_sentence_has_one_source():
    """The section quotes the clusters module rather than counting again.

    The section used to state a dead shield state in the brief's counts ("2
    contested matchups over 3 distinct win patterns") while the clusters view
    of the SAME state stated it in the clusters section's ("1 opponent is a
    sharp marginal"), two clicks apart, neither defined where it was printed.
    """
    import deep_dive_matchup_clusters as M
    # The split-out finding is BYTE-IDENTICAL inside the reason string it came
    # out of, so the clusters section's own sentence did not move.
    assert M.degenerate_reason(1, 2, 74, 76, 76).startswith(
        'every spread wins 74-76 of 76 opponents here, so the IV choice '
        'moves at most 2 matchups in this shield state. Only 1 opponent is '
        'a sharp marginal (2 distinct win patterns)')
    assert M.degenerate_reason(1, 1, 76, 76, 76).startswith(
        'every spread wins exactly 76 of 76 opponents here -- no IV choice '
        'changes this shield state.')
    # ...and the section reaches it through the same function, not a copy.
    entry = {'degenerate': True, 'win_lo': 74, 'win_hi': 76, 'n_opp': 76}
    assert W._degeneracy_finding(entry) == M.degenerate_finding(
        74, 76, 76)
    src = (SCRIPTS_DIR / 'deep_dive_which_build.py').read_text()
    assert 'brief.clusters.degenerate_finding(' in src
    assert 'contested win patterns' not in src


# ---------------------------------------------------------------------------
# 9. v4: the builds block, the presets, and the section's own prose
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_section_renders_one_builds_block_per_preset(shadow_sableye):
    """Every preset's table is server-rendered; the inactive ones are hidden.

    Rendering all three rather than formatting them in the browser is what
    keeps the prose inside the word gates: the knob chooses a block, it does
    not compose a sentence.
    """
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    blocks = re.findall(r'<div class="wb-preset" data-preset="(\w+)"( hidden)?>',
                        html)
    assert [b[0] for b in blocks] == ['flat', 'even', 'one_one']
    assert [bool(b[1]) for b in blocks] == [False, True, True]
    # one table per preset, each with the seven columns the reader reads
    assert html.count('<table class="wb-builds-table">') == 3
    for col in ('Build', 'What it is', 'Spreads', 'Guarantees',
                'Most-winning member', 'Stat-product rank-1',
                'Gives up (guaranteed by another build, not this one)'):
        assert f'<th>{col}</th>' in html, col
    # Under a preset that counts fewer than all nine scenarios the two
    # count-bearing headers say which scale their numbers are on; the
    # default preset's table keeps the short headers above.
    assert '<th>Guarantees (in the counted shields / overall)</th>' in html
    assert '<th>Most-winning member (in 1v1 shields)</th>' in html
    # the per-build expanders and their members box
    assert html.count('<details class="wb-build"') >= 6
    assert html.count('class="wb-mem"') >= 6
    assert 'wbCompareBuilds(this)' in html
    # the note that says what the preset does and does not weight
    import html as _hh
    assert W.WEIGHTING_NOTE in _hh.unescape(html)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_summary_self_labels_its_preset(shadow_sableye):
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    for key in ab['presets']:
        line = W.builds_summary(all_facts[0], ab, key, all_facts)
        assert line.startswith(f'[{builds_mod.PRESET_TAG[key]}]'), line
        assert 'decision matchups' in line
        # the staircase's steps belong in the table, not in the one line a
        # reader reads before opening anything
        assert '->' not in line


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_guarantee_lists_are_sorted_by_outside_rate_and_capped(shadow_sableye):
    """Rarest guarantee first, cap with a "+N more", near-free cells counted."""
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    block = ab['presets'][builds_mod.PRESET_FLAT]
    b = block['builds'][0]
    for scen, rows in b['guaranteed_by_scenario'].items():
        outs = [r['outside_wr'] for r in rows]
        assert outs == sorted(outs), (scen, outs)
    html = W.section_html(all_facts, 0)
    # The "+N more" control is a BUTTON over rows that already shipped
    # hidden, not a dead label: every one of them has its rows.
    shown = [int(x) for x in re.findall(r'wbMoreRows\(this\)">Show (\d+) more',
                                        html)]
    assert shown, 'no "+N more" control was rendered at all'
    assert sum(shown) == html.count('<li class="wb-hid" hidden>')
    assert 'near-free' in html
    # a near-free cell is counted, never listed
    listed = re.findall(r'-- outside (\d+)%', html)
    assert listed, 'no guarantee row was printed at all'
    assert all(int(x) <= 90 for x in listed), max(listed)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_objectives_line_is_printed_only_when_they_disagree(shadow_sableye):
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    for key, block in ab['presets'].items():
        line = W.objectives_line(ab, key)
        split = (block['objectives'] or {}).get('split')
        assert bool(line) == bool(split), (key, split, line)
        if line:
            obj = block['objectives']
            assert line.startswith('The two objectives disagree here:')
            # the wins half carries its own denominator, and the cells half
            # the count the RANKING used -- a reader who subtracts the
            # table's columns has to land inside this sentence
            mw = next(b for b in block['builds']
                      if b['combo'] == obj['best_wins_build']
                      )['most_winning_member']
            assert f"of {mw['denominator']}" in line
            assert 'decision matchup' in line
            flat = all(w > 0 for w in block['weights'])
            if not flat:
                assert 'over all' in line, line


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_builds_payload_travels_with_the_section(shadow_sableye):
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    pay = json.loads(
        re.search(r'class="wb-data">(.*?)</script>', html, re.S).group(1))
    bp = pay['bp']
    assert bp['presetKeys'] == ['flat', 'even', 'one_one']
    assert bp['default'] == 'flat'
    assert bp['nDecision'] == 87
    # every selected build points at a region that carries a membership mask
    for key in bp['presetKeys']:
        block = bp['presets'][key]
        assert block['summary'] and block['lead']
        assert len(block['weights']) == len(bp['scenLabels'])
        assert set(block['weights']) <= {0, 1}
        for b in block['builds']:
            reg = bp['regions'][b['region']]
            assert reg['mask'] and reg['size'] == b['size']
            assert bp['regions'][b['region']]['bits']
    # the builds view leads the Show selector
    assert [v['id'] for v in pay['views']][0] == 'builds'


def test_the_glossary_defines_every_v4_term():
    for term in ('build', 'fork', 'guaranteed', 'outside rate',
                 'decision matchup', 'material', 'build criteria'):
        assert glossary.definition(term), term


# ---------------------------------------------------------------------------
# 10. v4 round 2: the preset's own scale in the prose (2026-09-16 review)
# ---------------------------------------------------------------------------

def test_the_term_marker_does_not_mark_inside_a_marked_term():
    """Nested <abbr> tooltips: the INNER title is what a hover shows.

    "Build criteria" was claimed first, then the shorter "build" re-matched
    the word inside the span already inserted for it, so hovering "Build" in
    "Build criteria:" showed the build definition. Splitting on tags is not
    enough -- the substitution puts the claimed text in its own text piece.
    """
    out = W.TermMarker().mark('<p>Build criteria decide the build</p>')
    assert out.count('<abbr') == 2
    assert '<abbr class="wb-term" title="' in out
    # no abbr opens before the previous one closes
    depth, worst = 0, 0
    for tok in re.findall(r'</?abbr', out):
        depth += 1 if tok == '<abbr' else -1
        worst = max(worst, depth)
    assert worst == 1, out
    # the long term kept its own definition
    first = re.search(r'<abbr class="wb-term" title="([^"]*)">Build criteria',
                      out)
    assert first and first.group(1) == glossary.definition('build criteria')


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_narrow_preset_leads_with_the_count_its_ranking_used(shadow_sableye):
    """The summary, the table and the objectives sentence all quote the
    preset's own denominator first, then all nine in brackets.

    Pre-fix the summary and the table printed "49 of the 87" (all nine)
    while the ranking that chose those 292 spreads counted 13 of 16, and the
    sentence between them quoted the weighted gap -- so a reader subtracting
    the table's columns got a number the sentence did not contain.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    one = ab['presets'][builds_mod.PRESET_ONE]
    assert one['n_decision_weighted'] == 16
    assert ab['n_decision_cells'] == 87
    line = W.builds_summary(all_facts[0], ab, builds_mod.PRESET_ONE, all_facts)
    assert '13 of the 16 decision matchups in 1v1 shields' in line, line
    assert '(49 of all 87)' in line, line
    table = W.builds_table_html(ab, builds_mod.PRESET_ONE)
    assert '13 of 16 in 1v1 shields; 49 of 87 overall' in table
    # the default preset has ONE scale and prints one number
    flat_line = W.builds_summary(all_facts[0], ab, builds_mod.PRESET_FLAT,
                                 all_facts)
    assert '55 of the 87 decision matchups' in flat_line
    assert 'of all 87' not in flat_line


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_lead_says_when_the_primary_only_won_a_tie(shadow_sableye):
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    even = W.builds_lead(all_facts[0], ab, builds_mod.PRESET_EVEN, all_facts)
    assert 'tie at 29 guaranteed matchups in 0v0 / 1v1 / 2v2 shields' in even
    assert 'Build 1 is the largest of them (92 spreads)' in even
    # and the count the ranking uses is named where the preset is named
    assert '43 of those sit in 0v0 / 1v1 / 2v2 shields' in even


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_summary_always_says_where_rank1_sits(shadow_sableye):
    """Under the even preset the rank-1 holder is the THIRD build, which the
    round-1 summary dropped entirely (it named builds 1 and 2 only)."""
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    for key, block in ab['presets'].items():
        line = W.builds_summary(all_facts[0], ab, key, all_facts)
        assert 'stat-product rank-1' in line, key
        holder = next((i for i, b in enumerate(block['builds'])
                       if b['rank1_in']), None)
        if holder is None:
            assert 'is in none of them' in line, key
    even = W.builds_summary(all_facts[0], ab, builds_mod.PRESET_EVEN,
                            all_facts)
    assert 'sits in a third, 114-spread build' in even, even


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_staircase_summary_prints_a_range_not_undefined_notation(
        shadow_sableye):
    """"Def >= d(HP)" is notation nothing on the page defines, and the
    collapsed line is what most readers act on."""
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    stairs = [b for block in ab['presets'].values() for b in block['builds']
              if (b['description'] or {}).get('steps')]
    assert stairs, 'no staircase build on this blob to check'
    for b in stairs:
        short = W.build_desc(b, steps=False)
        assert 'd(HP)' not in short, short
        assert 'depending on HP' in short and 'steps, in the table' in short
        # the printed band CONTAINS every step of the staircase
        lo, hi = re.search(r'Def >= ([\d.]+)-([\d.]+) ', short).groups()
        defs = [d for _h, d, _n in b['description']['steps']]
        assert float(lo) <= min(defs) and float(hi) >= max(defs)
        # the table still prints the steps themselves
        assert '->' in W.build_desc(b, steps=True)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_outside_rate_is_named_on_the_page_and_reaches_the_terms_list(
        shadow_sableye):
    """The rows say "outside 40%" and the glossary had an "outside rate"
    entry the page could never reach, because it never spelled the term."""
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    assert 'Sorted by outside rate:' in html
    assert re.search(r'<abbr class="wb-term" title="[^"]*">outside rate</abbr>',
                     html), 'the term was printed but never marked'
    terms = html[html.index('Terms used here'):]
    assert '<dt>outside rate</dt>' in terms
    # positive control: an unrelated v4 term is in the same list, so an
    # empty Terms block cannot pass this
    assert '<dt>decision matchup</dt>' in terms


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_negative_page_bridges_its_summary_to_its_builds():
    """The v3 "zero matchups wide" sentence is about TOTAL wins and stays
    (Michael's call). Standing alone beside a builds table guaranteeing 29
    of 51 decision matchups it read as a contradiction."""
    path = require_blob(MELMETAL)
    state = B.load_blob(str(path))
    all_facts = W.prepare(state, str(path))
    arm = next(i for i, f in enumerate(all_facts) if f['floor'] is None)
    ab = all_facts[arm]['_builds']
    assert ab and ab['presets'], 'this arm no longer builds anything'
    for key in ab['presets']:
        line = W.builds_summary(all_facts[arm], ab, key, all_facts)
        assert line.startswith(f'[{builds_mod.PRESET_TAG[key]}]'), line
        assert 'Which matchups you win still moves:' in line, key
        lead = W.builds_lead(all_facts[arm], ab, key, all_facts)
        assert 'no single-stat line' in lead
        assert 'is guaranteed to win -- and that one does move' in lead
    # every preset lands on the same regions here, and the lead says so
    assert ab['presets_identical'] is True
    assert ('The Build criteria preset does not change which builds this '
            'moveset gets.' in W.builds_lead(all_facts[arm], ab,
                                             builds_mod.PRESET_FLAT,
                                             all_facts))
