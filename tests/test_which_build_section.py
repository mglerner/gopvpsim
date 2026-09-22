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
import html as _html
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
# The 2026-09-13 Aegislash (Shield) bake: the focal IS the G-caveat species,
# which is what took the section off every Aegislash page before 2026-09-20.
AEGISLASH_SHIELD = '20260913_062354_Aegislash_Shield_great.replay.pkl.gz'
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


def test_the_glossary_display_names_are_real_terms():
    """``DISPLAY`` renames a HEADING, never a registry key: an entry for a
    term that does not exist would silently print nothing different."""
    assert glossary.DISPLAY
    for key, shown in glossary.DISPLAY.items():
        assert key in glossary.TERMS, key
        # Case-insensitive: 'UpSet plot' is a proper name (Lex et al.
        # 2014) whose registry key is lower-cased for lookup, and
        # 'opponent-IV mode' capitalises IV (round 10). Pre-fix this
        # asserted an exact substring and barred both.
        assert key.lower() in shown.lower(), (key, shown)
    assert glossary.DISPLAY['stat-product rank-1'].endswith('(SP1)')


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
    """The spreads that reach the line, after the DESCRIPTIVE opening.

    Pre-v5 this read "Most X should have at least 148.10 attack, which ...",
    which Michael's 2026-09-16 review called a strategy read the page has
    not earned. The appendix (the named spreads, then the remainder) is
    unchanged; only the directive clause is rewritten.
    """
    got = W.extended_first_sentence(_facts())
    assert got == ('X has a line at 148.10 attack, which '
                   '6/9/7 at L50, 10/13/11 at L45.5 and 2218 other spreads '
                   'reach.')
    assert 'should' not in got and not got.startswith('Most ')
    # 2220 clearers minus the 2 named: the count is the brief's, not a
    # recount of the grid.
    assert '2218' in got


def test_the_directive_opening_is_rewritten_only_when_it_is_the_template():
    """descriptive_opening rewrites the one template and nothing else.

    A moveset sharing an earlier one's line opens "Same line as ...", and a
    half-rewritten sentence would be worse than the directive it replaced.
    """
    assert (W.descriptive_opening('Most X should have at least 148.10 attack.')
            == 'X has a line at 148.10 attack.')
    same = 'Same line as SHADOW_CLAW / DRAIN_PUNCH, FOUL_PLAY: 148.10 attack.'
    assert W.descriptive_opening(same) == same
    none = 'No single stat threshold decides a matchup here.'
    assert W.descriptive_opening(none) == none


def test_extended_first_sentence_is_not_extended_with_no_line():
    """With no line there is no set of spreads that reach anything to name.

    Pre-v5 this asserted the sentence came back byte-identical; v5 still
    takes the directive out of it (the voice fix applies wherever the
    template appears), so what is pinned is that the APPENDIX is not added.
    """
    f = _facts(floor=False)
    first = W.sentences(f['_headline'][0])[0]
    got = W.extended_first_sentence(f)
    assert got == W.descriptive_opening(first)
    assert got == 'X has a line at 148.10 attack.'
    assert ', which ' not in got


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
    # round 6: SP1 everywhere the section names the object
    # (pre-fix: 'though rank-1 0/15/15 still wins 1 more matchup overall')
    assert 'though SP1 0/15/15 still wins 1 more matchup overall' in got
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
    # The collapsed line of a no-line page is its own surface, so it
    # SPELLS the term at first use. Pre-round-6: 'Your rank-1: ...'.
    assert W.summary_sentence(f) == (
        'Your stat-product rank-1 (SP1): it already wins more matchups than '
        'any other spread.')


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
                src.index('function wbRenderBox(')]
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
    # Through the page's ONE score-key grammar, so the level suffix the
    # best-buddy toggle flips comes along. Pre-2026-09-20 this read the bare
    # L50 key `SCORES[mi + SCORE_KEY_SEP + mode]`, because the section only
    # ever existed at the league cap.
    assert 'getScores(mi, mode)' in wins
    assert 'getScoreKey(mi, mode)' in wins
    assert 'SCORES[mi + SCORE_KEY_SEP + mode]' not in wins
    assert 'DATA.nScenarios' in wins and 'DATA.nOpponents' in wins
    assert 'isWin(' in wins
    # Stats come from the level the section on screen was RENDERED at, which
    # since 2026-09-20 is whatever DATA.iv* currently holds: the section is
    # emitted once per level and swapped whole. Pre-fix it pinned itself to
    # the stashed `_bbL50` arrays, because one L50 copy was all there was.
    lvl = src[src.index('function wbLevelArrays('):
              src.index('var _wbWinsCache')]
    assert 'return DATA;' in lvl and '_bbL50' not in lvl
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
    # v5 routes both axes through _wbXY (the stats view draws defense
    # against HP), so the nudge is applied to the plane's own y. Pre-v5 this
    # read ``oy.push(wins[i] + ynudge)``.
    assert 'var mp = _wbXY(L, i, wins);' in owned
    # strip_js blanks string literals, so the plane name itself is not
    # matchable here -- the two halves around it are.
    assert 'oy.push(mp[1] + (_wbPlaneMode ===' in owned
    assert '? 0.02 : ynudge));' in owned
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
// The score-key grammar lives ABOVE _wbRoot, and wbWins goes through it so
// the best-buddy level suffix comes along. Sliced out of the real source
// rather than re-typed here: a harness copy of the key grammar is exactly
// the drift tests/test_js_score_key_parity.py exists to prevent.
const keyStart = src.indexOf('function getScoreKeyAt(');
const keyEnd = src.indexOf('// ---- Composite mode grammar');
if (keyStart < 0 || keyEnd < 0) { console.error('KEY MARKERS'); process.exit(2); }
const keyBlock = src.slice(keyStart, keyEnd);
const SCORE_KEY_L51 = '@51';
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
eval(keyBlock + block + '\nout = {wbWins, _wbGroups, wbLevelArrays, _wbIvIdx, _wbHover, _wbMask, _wbBit, _wbOwnedTrace, _wbClusterSides, _wbScen, _wbActiveLine, _wbSideAt, _wbOn};');

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
// The score-key grammar lives ABOVE _wbRoot, and wbWins goes through it so
// the best-buddy level suffix comes along. Sliced out of the real source
// rather than re-typed here: a harness copy of the key grammar is exactly
// the drift tests/test_js_score_key_parity.py exists to prevent.
const keyStart = src.indexOf('function getScoreKeyAt(');
const keyEnd = src.indexOf('// ---- Composite mode grammar');
if (keyStart < 0 || keyEnd < 0) { console.error('KEY MARKERS'); process.exit(2); }
const keyBlock = src.slice(keyStart, keyEnd);
const SCORE_KEY_L51 = '@51';
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
eval(keyBlock + block + '\nout = {wbWinsWeighted, wbWeightedDen, _wbBuildOf, _wbBuildSide,' +
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
    # A MARKER since 2026-09-20, not the section itself: on a best-buddy dive
    # the section is rendered at both levels and the host/<template> pair is
    # assembled farther down, beside the level bodies that supply each half's
    # clusters. Placement is unchanged -- the marker sits where the section
    # used to be emitted, and is replaced in place. Pre-fix this line read
    # `html += which_build_html`.
    slot = "'<!-- WHICH_BUILD_SLOT -->'"
    assert src.count("html += " + slot) == 1
    assert src.index("html += " + slot) < src.index(controls)
    # ...and the marker is really consumed, in both the paired and the
    # unpaired case, with the belt-and-braces cleanup after it.
    assert src.count("html.replace('<!-- WHICH_BUILD_SLOT -->'") == 2


def test_section_is_omitted_without_a_blob_path():
    """No blob, no brief -- and the no-op is logged, never silent."""
    import deep_dive
    # Two maps now: the rendered sections and the presets each arm's
    # section actually built (the controls strip's Build-criteria dropdown
    # lists the second, so a dive that produced no builds offers no knob).
    # Three maps now: the rendered sections, the presets each arm's section
    # actually built, and the card spreads taken from those builds (v5 --
    # the card no longer picks its own poles). Pre-v5 this was ``({}, {})``.
    # FIVE maps since 2026-09-20: the rendered sections, the live presets,
    # the card spreads taken from those builds, and then the best-buddy
    # (L51) section + its card spreads, which the caller puts in the
    # <template> the toggle swaps in. Pre-fix this was ``({}, {}, {})``;
    # before that ``({}, {}, {}, {})`` (round 8 dropped the membership map
    # with the Top Picks cards it labelled), ``({}, {}, {})`` pre-round-5
    # and ``({}, {})`` pre-v5.
    assert deep_dive._which_build_sections({}) == ({}, {}, {}, {}, {})


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
    # The whole per-file budget for this section; the payload alone must
    # stay tiny, because it is the part that would grow if a per-IV array
    # ever leaked into it.
    #
    # v5 (2026-09-16 review) raised the section ceiling from 150 KB to 175
    # KB: it added one PARAGRAPH per build per preset (8.4 KB here), the
    # standouts block (5 KB), the near-free guarantee rows the "show them"
    # control reveals (9 KB -- they were a counted sentence before) and an
    # emphasis class on every guarantee row. Measured 158.8 KB on this blob
    # when v5 shipped, against 145.6 KB for v4. The PAYLOAD ceiling did not
    # move: it is 43.0 KB here, and the per-scenario stats caption is a
    # short sentence rather than a ninth copy of the view's own.
    #
    # Round 6b (2026-09-17) raised it again, 175 KB -> 180 KB. The wide
    # region's new ranking key picks a LARGER region on this page (D,H, 644
    # spreads, against round 6's E,F at 292), so its table row's member list
    # is longer: measured 175.6 KB here against 174.4 KB at 62c4b6d, which
    # was already inside 1 KB of the old ceiling. Nothing per-IV entered the
    # section; the two numbers below cap the part that would show it.
    #
    # Round 8 (2026-09-17) raised it 180 KB -> 196 KB. Two blocks grew: the
    # Standouts block became the Notable spreads list, which names SP1 and
    # every build's most-winning member as well as the two standouts (four
    # entries here against two, each with its own where-it-sits sentence and
    # rarest-wins list), and every family added a table row with its
    # staircase stepped out. Measured 190.1 KB here against 175.6 KB at
    # 7bc9b51. Nothing per-IV entered the section; the payload cap below is
    # the number that would show it.
    #
    # Round 11 (2026-09-22) raised it 196 KB -> 206 KB for "The mirror" --
    # the cohort sentence once, and per Build criteria setting a table of the
    # mirror decision cells (seven rows on this blob, both Sableye forms)
    # plus the CMP paragraph and the cohort-rate paragraph, 201.7 KB here
    # against 193.2 KB with the block suppressed. The same day's cut takes it
    # back to 198 KB: the block is TWO SENTENCES now, one paragraph per Build
    # criteria setting, measured 195.2 KB here -- 2.0 KB over the suppressed
    # figure, which is the three paragraphs plus the trace clause on the two
    # builds captions. Nothing per-IV entered the section: the trace's
    # membership is ONE 684-character packed mask, and the payload caps below
    # are what would show it.
    assert len(html) < 198_000, len(html)
    payload = json.loads(
        re.search(r'class="wb-data">(.*?)</script>', html, re.S).group(1))
    # One 512-byte mask per printed rung plus one for the bulk pair, and
    # (v4) the builds half: one mask per selected region, the guarantee bits
    # of every candidate region, and the per-preset facts and sentences for
    # all three presets. Still far below the point where a per-IV STAT array
    # would have been cheaper. Measured 34 KB on this blob when v4 shipped.
    #
    # Round 6b raised it 48 KB -> 50 KB, measured 48.4 KB against 47.3 KB at
    # 62c4b6d. The whole delta is accounted for: the wide region's new
    # ranking key makes it a region no build already carries under the flat
    # and Even presets, so ``bp.regions`` gains ONE 684-character mask
    # (+782 B, 15 regions -> 16), and the collapsed lines gain the "and
    # holds both standouts" clause (+314 B over three presets).
    #
    # Round 8 raised it 50 KB -> 53 KB for the family membership masks: two
    # families on this arm, 684 base64 characters each, shipped ONCE at the
    # top of ``bp`` with the presets carrying indices into that table (a
    # family is a pure function of (grid, seed), so a per-preset copy would
    # have been the same bytes three times -- which is what this cap caught
    # when it was first written that way). Measured 51.2 KB here.
    #
    # Round 11: +1.2 KB (50.7 KB -> 51.8 KB) for the mirror trace's packed
    # mask and the two captions' trace clause. The cap does NOT move -- the
    # headroom it leaves is the point.
    assert len(json.dumps(payload)) < 53_000, len(json.dumps(payload))
    # Round 5 (2026-09-17) raised the builds-half ceiling from 24 KB to 28
    # KB: the nested wide build adds one payload build per preset, and with
    # it one 684-character membership mask each (measured 25.5 KB here,
    # against 23.4 KB before it). Round 6b did not move it: 26.3 KB.
    # The builds half is the part that would grow if a member LIST ever
    # replaced a packed mask.
    #
    # Round 8: 28 KB -> 30 KB. The families arrive here -- one table of
    # two (a rule string plus a 684-character membership mask each), an
    # index array per preset, and a ``family`` field on each standout.
    # The notable list itself is server-rendered HTML and costs the
    # payload nothing. Measured 28.2 KB here against 26.3 KB at 7bc9b51.
    assert len(json.dumps(payload['bp'])) < 30_000, len(json.dumps(payload['bp']))


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
    # v5: the line NAMES the builds, in the same descriptive voice as the
    # per-build paragraphs. Pre-fix it read "61 spreads -- Atk >= 150.24 ...
    # -- guarantee 55 of the 87 decision matchups; a disjoint 114-spread
    # build (Def >= 101.40 and HP >= 125) guarantees 41 instead and holds
    # your stat-product rank-1."
    assert 'Build 1 (61 spreads' in summary
    assert '55 of 87 decision matchups' in summary
    # Round 10: only the FIRST clause carries the word "spreads" and the
    # denominator; the rest carry the count alone, and every rule is the
    # table's own one-clause form. Pre-fix: 'Build 2 (114 spreads' and
    # 'the bulk box Def &gt;= 101.40 and HP &gt;= 125' (2026-09-19 round-10 review).
    assert 'Build 2 (114: ' in summary
    assert 'Def &gt;= 101.40 and HP &gt;= 125 (bulk box)' in summary
    # ...and the lead build carries BOTH guarantee numbers, which is the one
    # place the two-number rule had not reached (pre-fix: absent).
    assert 'under every opponent-IV mode' in summary
    # round 5: the collapsed line spells the term out, because a reader who
    # never opens the section sees only this line (pre-round-5: 'holds
    # rank-1')
    assert 'holds stat-product rank-1 (SP1)' in summary
    # no directive anywhere in the collapsed line
    assert 'should' not in summary
    # The line itself is still the headline's opening sentence -- with the
    # printed value wrapped in the clearers button, which is why this looks
    # for the two halves rather than the whole phrase. v5 rewrites the
    # directive clause: pre-fix the page carried 'should have at least '.
    assert 'has a line at ' in html
    assert 'should have at least ' not in html
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
    # Round 10: "the view the line above was derived on" pointed UP at a
    # line that round 9 moved DOWN into the "The single-stat line" expander
    # (2026-09-19 round-10 review).
    'Stat-product rank against matchups won with PvPoke-default opponent '
    'IVs at the league cap over the whole opponent pool and, with Shield '
    'scenario on all, every baked shield state -- the view the single-stat '
    'line in the expander below was derived on. The Shield scenario '
    "selector on this row is the section's own; the scatter's dropdowns and "
    'the opponent filter do not drive this panel.',
    'Compare these spreads',
    'All 4 movesets on this page share one line: at least 148.10 attack.',
    'Shield scenario: ',
    'Terms used here',
    # Round 9 replaced the six-entry Show select with three tab strips, and
    # added the answer strip's own two handles. Pre-fix this tuple carried
    # 'Show: '.
    'Builds on the grid',
    'Per shield scenario',
    # The glossary marks 'Build criteria' on first use, so the label ships
    # wrapped in its <abbr> and the colon after it is a separate run.
    'Build criteria',
    'Is mine in one of these?',
    'The single-stat line',
    'Why these regions',
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
    assert ('Your stat-product rank-1 (SP1): it already wins more matchups '
            'than any other spread.'
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
    # v5 adds the stats view behind the builds view it re-draws. Pre-fix:
    # ['builds', 'clusters', 'rank1'].
    # Round 9 adds the merged nine-mini grid as a view of its own (the
    # figure's third tab). Pre-fix: ['builds', 'stats', 'clusters', 'rank1'].
    assert ([v['id'] for v in payload['views']]
            == ['builds', 'stats', 'allscen', 'clusters', 'rank1'])
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
    # One row per marked term, in the order a reader met them. The
    # HEADING may be the display form ("stat-product rank-1 (SP1)"): a
    # reader scanning the terms for SP1 has to find it (round 6 review;
    # pre-fix the dt read "stat-product rank-1" and SP1 appeared only inside
    # the definition body).
    back = {v: k for k, v in glossary.DISPLAY.items()}
    names = re.findall(r'<dt>(?:<a[^>]*>)?([^<]+)', block)
    assert len(names) == len(set(marked)) == len(marked)
    assert [glossary.TERMS[back.get(n, n).lower()] for n in names] == marked
    assert 'stat-product rank-1 (SP1)' in block


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
    render = src[src.index('function wbRenderBox('):
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
    body = (_fn_body(raw, stripped, 'wbRenderBox')
            + _fn_body(raw, stripped, 'wbRenderRoot')
            + _fn_body(raw, stripped, 'wbSelectView')
            + _fn_body(raw, stripped, 'wbFillMembers')
            + _fn_body(raw, stripped, '_wbScen'))
    touched = set(re.findall(r"querySelector(?:All)?\(\s*'([^']+)'", body))
    # Round 9: the Show <select> is three tab strips (`.wb-tab`, read to set
    # aria-selected), the figures are `.wb-plotbox`es, and the merged grid's
    # caption is the box's own `.wb-caption`.
    assert touched == {'.wb-panel', '.wb-caption', '.wb-plotbox', '.wb-tab',
                       'select.wb-scen', '.wb-upset',
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
    assert 'wbRenderBox(root, box)' in sel
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
    # It sits on the section's OWN control row, under the figure's tab
    # strip. Round 9: the Show <select class="wb-view"> is gone -- the tabs
    # are buttons carrying data-view -- so the row's neighbours are the
    # merged grid's two toggles.
    row = re.search(r'<div class="wb-controls">.*?</div>', html, re.S).group(0)
    assert 'wb-scen' in row and 'wb-allscen-y' in row
    assert 'select class="wb-view"' not in html
    tabs = re.search(r'<div class="wb-tabs"[^>]*>.*?</div>', html, re.S).group(0)
    assert 'data-view="builds"' in tabs and 'data-view="allscen"' in tabs


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
    head = html[:html.index('<div class="wb-plotbox"')]
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
    render = _fn_body(ENGINE_JS.read_text(), _engine(), 'wbRenderBox')
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


# An arm that carries a LINE is a moving target: the brief gates a floor on
# the opponent's PvPoke meta rank, which is a live read, so a rankings refresh
# alone can take every line off a blob. The 2026-09-15 refresh did exactly
# that to Melmetal, which used to carry one on arm 2 -- the index this test
# pinned. So the positive arm is found BY PROPERTY now. The hints are tried
# first (one blob load in the common case) and the rest of the store is
# scanned in sorted order behind them, so the search is deterministic without
# being pinned to one blob that a later refresh can hollow out.
_LINE_ARM_HINTS = ['20260909_161909_Deoxys_Defense_ultra.replay.pkl.gz',
                   MELMETAL, SABLEYE_SHADOW]
_LINE_ARM_SCAN_BUDGET = 6


def _candidate_blobs():
    """Blob names to search, hints first, then the store in sorted order."""
    seen, out = set(), []
    for name in _LINE_ARM_HINTS:
        seen.add(name)
        out.append(name)
    for d in _replay_dirs():
        if d.is_dir():
            for name in sorted(q.name for q in d.glob('*.replay.pkl.gz')):
                if name not in seen:
                    seen.add(name)
                    out.append(name)
    return out


def _arm_with_a_line_and_an_empty_scenario():
    """First (blob name, facts, payload) whose arm carries all three shapes.

    The second half of the test below needs an arm that (a) prints a line,
    (b) still has a shield scenario with no line of its own, and (c) has a
    DEGENERATE scenario that does carry an in-band cut -- the case where the
    panel used to claim a threshold decides matchups in a shield state the
    clusters view calls dead two clicks away.
    """
    tried = 0
    for name in _candidate_blobs():
        path = next((d / name for d in _replay_dirs() if (d / name).exists()),
                    None)
        if path is None:
            continue
        tried += 1
        if tried > _LINE_ARM_SCAN_BUDGET:
            break
        state = B.load_blob(str(path))
        all_facts = W.prepare(state, str(path))
        for f in all_facts:
            if f['floor'] is None:
                continue
            pay = W.build_payload(f, f['_fields'], 0, all_facts=all_facts,
                                  arm_builds=f.get('_builds'))
            scen = pay['scen']
            if (any(v['lines'] for v in scen.values())
                    and any(not v['lines'] for v in scen.values())
                    and any(v['degenerate'] and v['lines']
                            for v in scen.values())):
                return name, f, pay
    pytest.skip(f"no blob in the first {_LINE_ARM_SCAN_BUDGET} searched "
                f"carries a line with an empty and a degenerate scenario")


@pytest.fixture(scope='module')
def line_carrying_arm():
    return _arm_with_a_line_and_an_empty_scenario()


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_negative_page_carries_the_control_and_its_captions(
        line_carrying_arm):
    """Melmetal Great League: the section's own control on a no-line page.

    A no-line arm prints no line at all, so the two threshold views do not
    exist and the control drives the y-axis, the clusters view and the
    caption. The opposite case -- an arm that DOES print one while most of
    its shield scenarios still have no line of their own -- is the case the
    captions have to say out loud, and it comes from
    ``line_carrying_arm``.

    Both arms are selected BY PROPERTY, not by index, and the second half's
    caption VALUES are read back out of the payload: what is pinned is the
    sentence each caption has to say, because which arm carries a line (and
    at what value) moves whenever PvPoke re-ranks the meta. Pinning Melmetal
    arm 2 made the 2026-09-15 rankings refresh look like a code failure.
    """
    path = require_blob(MELMETAL)
    state = B.load_blob(str(path))
    all_facts = W.prepare(state, str(path))
    neg = next((f for f in all_facts if f['floor'] is None), None)
    assert neg is not None, 'this blob no longer carries a no-line moveset'
    arm = neg['header']['arm']
    pay = W.build_payload(neg, neg['_fields'], 0, all_facts=all_facts,
                          arm_builds=neg.get('_builds'))
    # v5 adds the stats view, round 9 the merged grid. Pre-fix:
    # ['builds', 'stats', 'clusters', 'rank1'].
    assert ([v['id'] for v in pay['views']]
            == ['builds', 'stats', 'allscen', 'clusters', 'rank1'])
    assert len(pay['scen']) == len(state['shield_scenarios'])
    for lbl, entry in pay['scen'].items():
        assert entry['lines'] == []
        # v5 adds the stats view. Round 9's merged grid is deliberately
        # NOT here: it draws every scenario, so a per-scenario caption for
        # it would be nine copies of one paragraph (DRY rule D1).
        # Pre-fix: {'builds', 'stats', 'clusters', 'rank1'}.
        assert (set(entry['captions'])
                == {'builds', 'stats', 'clusters', 'rank1'})
        assert lbl in entry['captions']['rank1']
    html = W.section_html(all_facts, arm)
    assert 'Shield scenario: ' in html
    assert f'<option value="{W.ALL_SCEN}" selected>' in html

    # The arm that DOES carry a line: some scenarios have one, some do not.
    blob, _pos, pay2 = line_carrying_arm
    withline = [k for k, v in pay2['scen'].items() if v['lines']]
    assert withline, blob
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
    # The two sentences are what is pinned; the value and the opponent are
    # this arm's own, so they are read back from the payload rather than
    # spelled out (spelling them out is what tied the test to one blob).
    deg_lbl = next(k for k, v in pay2['scen'].items()
                   if v['degenerate'] and v['lines'])
    deg = pay2['scen'][deg_lbl]
    dcap = deg['captions']['line']
    printed = deg['lines'][0]['printed']
    assert float(printed) > 0, deg['lines'][0]     # a real value, not ''
    assert printed in dcap, dcap                   # ... and it is quoted
    assert f'{deg_lbl} shields' in dcap, dcap
    assert (f'In {deg_lbl} shields little turns on IVs at all: every spread '
            f'wins ') in dcap, dcap
    assert 'so the IV choice moves at most ' in dcap, dcap
    assert 'matchups in this shield state.' in dcap, dcap

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
    # 48 KB -> 50 KB in round 6b, for the one extra region mask the wide
    # region's new ranking key puts in ``bp.regions``; see the accounting on
    # ``test_real_section_is_ascii_deterministic_and_small``.
    # Round 8: 50 KB -> 53 KB for the family membership masks. There is ONE
    # table of them at the top of ``bp`` and the presets carry indices into
    # it -- a family is a pure function of (grid, seed), so shipping a
    # 684-byte mask once per preset would have been the same bytes three
    # times, which this cap caught when it was written that way. Measured
    # 51.2 KB here.
    assert len(json.dumps(pay)) < 53_000, len(json.dumps(pay))
    # v5 adds a fifth caption per scenario (the stats view). It is a SHORT
    # sentence, deliberately not a ninth copy of the view's own 900-
    # character caption -- that is what this cap exists to catch. Measured
    # 13.6 KB when v5 shipped, against 12.0 KB for v4.
    assert len(json.dumps(pay['scen'])) < 15_000, len(json.dumps(pay['scen']))


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
    render = _fn_body(ENGINE_JS.read_text(), _engine(), 'wbRenderBox')
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
    of the SAME state stated it in the clusters section's ("1 opponent is
    contested"), two clicks apart, neither defined where it was printed.
    """
    import deep_dive_matchup_clusters as M
    # The split-out finding is BYTE-IDENTICAL inside the reason string it came
    # out of, so the clusters section's own sentence did not move.
    assert M.degenerate_reason(1, 2, 74, 76, 76).startswith(
        'every spread wins 74-76 of 76 opponents here, so the IV choice '
        # Round 10: the clusters body says "contested", the table's own
        # word, instead of "sharp marginal" -- an undefined near-synonym it
        # used 49 times on the shadow page (2026-09-19 round-10 review).
        'moves at most 2 matchups in this shield state. Only 1 opponent is '
        'contested (2 distinct win patterns)')
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
    # Round 10: each setting owns THREE blocks -- the verdict sentence, its
    # table, and its notable entries -- because the two sentences that
    # CANNOT vary with the setting (species/moveset, and the single-stat
    # line) render once each, between the first two groups (DRY rule D1).
    # Pre-fix (9cb2b26) it was two, with the verdict lead and the
    # line-status sentence inside the first.
    #
    # Round 11 (2026-09-22) makes it FOUR: "The mirror" names builds in its
    # second sentence, so the paragraph is per setting. It was a block with a
    # setting-invariant cohort sentence above the group until the same day's
    # cut; the pair is now rendered together, per setting (the reason is on
    # ``mirror_block_html``).
    blocks = re.findall(r'<div class="wb-preset" data-preset="(\w+)"( hidden)?>',
                        html)
    assert [b[0] for b in blocks] == ['flat', 'even', 'one_one'] * 4
    assert [bool(b[1]) for b in blocks] == [False, True, True] * 4
    # The mirror owns the THIRD group: the verdict sentences and the builds
    # tables come before it, the notable entries after (its placement
    # relative to the table and the collection block is pinned in
    # test_real_section_places_the_mirror_between_the_table_and_the
    # _collection).
    #
    # SEVEN preset divs open before the paragraph and five after, not six and
    # six: the paragraph sits INSIDE the third group's first div. Pre-cut the
    # block's bordered wrapper opened before that div, so the two halves were
    # even -- the numbers move with the wrapper, not with the reading order,
    # which is what the line above them pins.
    mirror_at = html.index('<p class="wb-mirror">')
    tails = [m.start() for m in
             re.finditer(r'<div class="wb-preset" data-preset=', html)]
    assert sum(1 for t in tails if t < mirror_at) == 7
    assert sum(1 for t in tails if t > mirror_at) == 5
    # one table per preset, each with the seven columns the reader reads.
    # Round 9 (proposal s.3) renamed and re-ordered them: 'What it is' is
    # 'Rule' and carries the rule alone, 'Rarest win' is new, the SP1 column
    # folded into 'Best member / SP1', and the 'Gives up' header's
    # parenthetical became a hover. Pre-fix headers: Build, What it is,
    # Spreads, Guarantees, Most-winning member, SP1,
    # 'Gives up (guaranteed by another build, not this one)'.
    assert html.count('<table class="wb-builds-table">') == 3
    for col in ('Build', 'Rule', 'Spreads', 'Guarantees',
                'Best member / SP1'):
        assert f'<th>{col}</th>' in html, col
    # Round 10 gave "Rarest win" the hover its cells' "outside N%" needs --
    # the glossary's own 'outside rate' sentence (pre-fix: a bare <th>).
    assert f'title="{W._esc(W.RAREST_HOVER)}">Rarest win</abbr>' in html
    assert '<th>What it is</th>' not in html
    assert f'title="{W.GIVES_UP_HOVER}">Gives up</abbr>' in html
    # Under a preset that counts fewer than all nine scenarios the two
    # count-bearing headers say which scale their numbers are on; the
    # default preset's table keeps the short headers above.
    # Round 10 hung the weighting note on this header as its hover, under
    # exactly the settings whose clause it explains (pre-fix: a bare <th>,
    # with the note as a paragraph under every table).
    assert ('<abbr title="' + W._esc(W.WEIGHTING_NOTE)
            + '">Guarantees (in the counted shields / overall)</abbr>') in html
    assert '<th>Best member (in 1v1 shields) / SP1</th>' in html
    # the per-ROW expanders and their members box (pre-fix: separate
    # <details class="wb-build"> blocks under the table)
    assert '<details class="wb-build"' not in html
    assert html.count('<tr class="wb-rowexp">') >= 6
    assert html.count('class="wb-mem"') >= 6
    assert 'wbCompareBuilds(this)' in html
    # The note that says what the Build criteria setting does and does not
    # weight is the HOVER on the header it is about, under the two settings
    # whose clause it explains -- not a 60-word paragraph under every table.
    # Pre-fix: one <p class="wb-weighting"> printed under all three
    # (2026-09-19 round-10 review).
    import html as _hh
    assert 'class="wb-weighting"' not in html
    assert _hh.unescape(html).count(W.WEIGHTING_NOTE) == 2


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
    # Counted by regex, not by a literal: v5 puts the row's outside-rate
    # emphasis class in front of the reveal class, so the hidden rows are
    # class="wb-o2 wb-hid" as often as class="wb-hid".
    assert sum(shown) == len(re.findall(r'class="[^"]*\bwb-hid\b[^"]*" hidden',
                                        html))
    # v5 (review item 4): the near-free tail is a SECOND control over rows
    # that also ship hidden, under their own class so the two reveals do not
    # fire each other. Pre-fix those cells were counted in a sentence and
    # never listed, and this test asserted no printed row was above 90%.
    assert 'near-free' in html
    # Round 9 shortened the control's own sentence so no 120-character run
    # of it is identical across the three preset blocks (DRY rule D1).
    # Pre-fix: '<N> more cells here are near-free (the spreads outside this
    # build win them over 90% of the time too): show them with their outside
    # rates'.
    free_ctl = re.findall(
        r'data-reveal="wb-hidfree"[^>]*>(\d+) more near-free', html)
    assert free_ctl, 'the near-free tail has no control'
    n_free_rows = len(re.findall(r'class="[^"]*wb-hidfree"', html))
    assert sum(int(x) for x in free_ctl) == n_free_rows
    # ... and the rows behind it are exactly the ones above the bar, so the
    # visible list still leads with the rare guarantees
    listed = [int(x) for x in re.findall(
        r'<li(?![^>]*wb-hidfree)[^>]*>[^<]*-- outside (\d+)%', html)]
    assert listed, 'no guarantee row was printed at all'
    assert all(x <= 90 for x in listed), max(listed)
    free_listed = [int(x) for x in re.findall(
        r'<li class="[^"]*wb-hidfree" hidden>[^<]*-- outside (\d+)%', html)]
    assert free_listed and all(x > 90 for x in free_listed), free_listed


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
    # v5 drops the article from the collapsed line ("13 of 16", not "13 of
    # the 16") so the sentence can name three builds without reading as a
    # list of denominators; the two-scale form is unchanged.
    assert '13 of 16 decision matchups in 1v1 shields (49 of all 87)' in line, line
    assert '(49 of all 87)' in line, line
    table = W.builds_table_html(ab, builds_mod.PRESET_ONE)
    assert '13 of 16 in 1v1 shields; 49 of 87 overall' in table
    # the default preset has ONE scale and prints one number
    flat_line = W.builds_summary(all_facts[0], ab, builds_mod.PRESET_FLAT,
                                 all_facts)
    # v5: no article. Pre-fix: '55 of the 87 decision matchups'.
    assert '55 of 87 decision matchups' in flat_line
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
        # v5 says "holds rank-1" (Michael's own wording for the collapsed
        # line); pre-fix it said "holds your stat-product rank-1" and the
        # non-holder case read "your stat-product rank-1 is in none of
        # them". The glossary term is still spelled in the builds table's
        # own column header, which is what the term marker reaches.
        assert 'rank-1' in line, key
        holder = next((i for i, b in enumerate(block['builds'])
                       if b['rank1_in']), None)
        if holder is None:
            assert 'is in none of them' in line, key
        else:
            # ... and the clause is attached to the build that holds it,
            # whichever one that is. Pre-fix a rank-1 holder past build 2
            # got a whole extra clause ("sits in a third, 114-spread
            # build"); v5 names every build anyway, so it is two words.
            assert (f"{W.role_short(block['builds'][holder], holder)} "
                    in line), key
    even = W.builds_summary(all_facts[0], ab, builds_mod.PRESET_EVEN,
                            all_facts)
    # Pre-fix: 'Build 3 (114 spreads' (2026-09-19 round-10 review: "spreads" is on the
    # first clause only).
    assert ('Build 3 (114: ' in even
            and 'holds stat-product rank-1 (SP1)' in even), even


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
        # round 4: a step is (HP, exact floor, members, printed decimal)
        defs = [d for _h, d, _n, _p in b['description']['steps']]
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
    # Round 9 (DRY rule D1) prints this key ONCE under the table instead of
    # once per build per preset. Pre-fix: 'Sorted by outside rate:' inside
    # every build expander.
    # The key's own first use of the term is MARKED, so its sentence ships
    # with an <abbr> inside it: count the two halves rather than the literal.
    head, _, tail = W._esc(W.GUARANTEE_SORT_KEY).partition('outside rate')
    assert html.count(head) == 1
    assert html.count(tail) == 1
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
    # Round 9 item 7: reader text says "Build criteria setting", never
    # "preset" (the control's own label is Build criteria). Pre-fix:
    # 'The Build criteria preset does not change ...'.
    assert ('The Build criteria setting does not change which builds this '
            'moveset gets.' in W.builds_lead(all_facts[arm], ab,
                                             builds_mod.PRESET_FLAT,
                                             all_facts))


# ---------------------------------------------------------------------------
# 6. v5 -- the 2026-09-16 review (eight items)
# ---------------------------------------------------------------------------

def test_outside_rate_emphasis_bands_and_their_key():
    """Item 5: one function owns the four bands, and the key names them all.

    Pre-fix every guarantee row was one typeface, so a cell the rest of the
    grid wins 92% of the time and one it wins 10% of the time read the same
    -- and the second is the only one the build is really buying.
    """
    assert W.emph_class(0.05) == 'wb-o3'
    assert W.emph_class(0.10) == 'wb-o3'          # inclusive upper bound
    assert W.emph_class(0.11) == 'wb-o2'
    assert W.emph_class(0.25) == 'wb-o2'
    assert W.emph_class(0.26) == 'wb-o1'
    assert W.emph_class(0.50) == 'wb-o1'
    assert W.emph_class(0.51) == ''
    assert W.emph_class(W.NEAR_FREE) == ''        # the bar itself is not dim
    assert W.emph_class(0.91) == 'wb-o0'
    assert W.emph_class(None) == ''
    # the key describes the bands a reader will actually meet
    for phrase in ('fewer than half', 'fewer than a quarter',
                   'fewer than a tenth', 'nine in ten'):
        assert phrase in W.EMPH_KEY, phrase
    # ... and every class the key describes has a CSS rule
    for cls in ('wb-o1', 'wb-o2', 'wb-o3', 'wb-o0'):
        assert f'#dd-which-build .{cls} {{' in W.CSS, cls


def test_the_card_copies_the_sections_emphasis_bands_exactly():
    """The standalone card carries no section, so it re-declares the bands.

    They are the same numbers by assertion rather than by import: a card
    that dimmed at 0.8 while the section dimmed at 0.9 would put two
    different meanings on one typeface, three inches apart on one page.
    """
    import deep_dive_card as dc
    assert [b for b, _c in dc._EMPH_BANDS] == [b for b, _c in W.EMPH_BANDS]
    assert dc._EMPH_NEAR_FREE == W.NEAR_FREE
    for rate in (0.0, 0.05, 0.10, 0.11, 0.25, 0.26, 0.5, 0.51, 0.9, 0.95):
        sec, card = W.emph_class(rate), dc._emph_class(rate)
        assert card == (sec.replace('wb-', 'ddcard-') if sec else ''), rate
        if card:
            assert f'.{card} {{' in dc.CARD_CSS, card


def test_the_member_list_is_iv_spreads_and_nothing_else():
    """Item 7. Pre-fix each member was its own <div> carrying the level and
    the stat-product rank, which made a 25-row list three times as tall as
    the spreads it lists -- and the rank is already the sort order."""
    src = _engine()
    body = src[src.index('function _wbMemberRows('):
               src.index('function wbRenderMembers(')]
    assert 'out.push(DATA.ivA[i] +' in body
    for gone in ('@L', 'ivLv', 'spRanks[i]', '<div>'):
        assert gone not in body, gone
    render = src[src.index('function wbRenderMembers('):
                 src.index('function wbMoreRows(')]
    # strip_js blanks string literals, so the separator itself is not
    # matchable -- that the list is JOINED into one string is.
    assert 'var html = out.join(' in render
    assert 'box.innerHTML = html;' in render
    # the order and the cap are unchanged: stat-product rank, topN then
    # all (the header says so since round 4; the old one said 'bulkiest')
    assert 'L.spRanks[a] - L.spRanks[b]' in render
    assert 'pay.bp.topN' in render


def test_the_upset_rows_wrap_and_size_their_own_margin():
    """Item 1: the row labels ran off the left edge of the plot.

    Two things, both pinned: the tick text carries a <br> so it wraps, and
    the left margin is computed from the longest wrapped LINE instead of the
    fixed 230px that was not enough for "A two-stat box for 0v1 Empoleon
    (665 spreads / 42 guaranteed)".
    """
    src = _engine()
    body = src[src.index('function _wbUpset('):
               src.index('function _wbMemberRows(')]
    assert 'rowTicks' in body and 'ticktext: rowTicks' in body
    assert "split(" in body and 'widest' in body
    assert 'l: tickMargin' in body
    assert 'l: 230' not in body, 'the fixed margin is still there'
    # the label itself is the set's target plus its counts, on two lines
    assert 'rr.key +' in body and 'rr.short +' in body
    assert 'rr.size +' in body and 'rr.nG +' in body
    # the <br> is a string literal, which strip_js blanks -- read it raw
    raw = ENGINE_JS.read_text()
    raw_body = raw[raw.index('function _wbUpset('):
                   raw.index('function _wbMemberRows(')]
    assert "'<br>'" in raw_body


def test_set_labels_name_the_target_not_the_shape_sentence():
    """Item 1, the producing half. Pre-fix: "two-stat box for 0v1 Empoleon"
    and "Atk 148.10 + defense staircase for 1v2 Corviknight"."""
    assert (builds_mod.set_short_label('S5 box -> 0v1 Empoleon')
            == '0v1 Empoleon box')
    assert (builds_mod.set_short_label('S4 frontier (atk >= 148.1 -> '
                                       '1v2 Corviknight)')
            == '1v2 Corviknight staircase')
    # item 8(a): one name for the bulk build everywhere
    assert (builds_mod.set_short_label('S2 alternative rectangle')
            == 'the bulk box')
    assert 'rectangle' not in builds_mod.set_short_label(
        'S2 alternative rectangle')


def test_the_stats_view_is_wired_end_to_end_in_the_js():
    """Item 8(b): a second plane, and every trace builder reads one switch."""
    src = _engine()
    assert 'var _wbPlaneMode' in src
    assert 'function _wbXY(' in src
    assert 'function _wbPlaneShapes(' in src
    render = _fn_body(ENGINE_JS.read_text(), _engine(), 'wbRenderBox')
    # the switch is set once per render, from the view
    assert '_wbPlaneMode =' in render
    # the stats view re-uses the BUILDS grouping, colours and weighting
    assert "view === 'stats'" in render
    assert '_wbPlaneShapes(pblock,' in render
    # the three drawable shapes, and nothing drawn for a build no rule fits
    shapes = src[src.index('function _wbPlaneShapes('):]
    shapes = shapes[:shapes.index('function wbRenderMembers(')]
    # three drawable kinds, one branch each (the kind NAMES are string
    # literals, which strip_js blanks, so the branches are counted)
    assert shapes.count('pl.kind ===') == 4      # none + box + stair + line
    assert 'continue;' in shapes, 'a ruleless build must draw no outline'
    assert 'fillcolor:' in shapes, 'the box branch draws no rectangle'
    raw = ENGINE_JS.read_text()
    raw_shapes = raw[raw.index('function _wbPlaneShapes('):
                     raw.index('function _wbMemberRows(')]
    for kind in ("'box'", "'stair'", "'line'", "'none'", "'rect'"):
        assert kind in raw_shapes, kind


def test_the_standouts_join_the_compare_prefill():
    """Item 3: the block names two spreads the Compare button did not carry."""
    src = _engine()
    body = src[src.index('function wbCompareBuilds('):
               src.index('window.wbCompareBuilds')]
    assert 'block.standouts' in body
    assert 'push(so[t].iv)' in body
    # dedup is the pre-existing push(); assert it is still the only entry
    # point, so a standout that IS a most-winning member is listed once
    assert body.count('function push(') == 1


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_builds_table_replaces_the_per_build_paragraphs(shadow_sableye):
    """Round 9 item 2: the table is the answer, the row expander the detail.

    The three ``<p class="wb-para">`` paragraphs duplicated the table row for
    row -- rule, guarantee count, three rarest wins, three gives-ups,
    most-winning member, SP1 -- between the verdict and the table a reader
    was scrolling to.

    Pre-fix (0ca9693) ``build_paragraphs_html`` returned three paragraphs
    whose text began "Build 1 has Sableye (Shadow) running Shadow Claw /
    Drain Punch, Foul Play at Atk >= 150.24 with Def >= 97.15 to 99.63
    depending on HP (119-122)." and ended "Its most-winning member is 8/7/5
    (378 of 684); SP1 is outside it.". Every one of those facts is asserted
    below in the cell that carries it now.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    bl = ab['presets'][builds_mod.PRESET_FLAT]
    assert not hasattr(W, 'build_paragraphs_html')
    html = W.section_html(all_facts, 0)
    assert 'wb-para' not in html, 'a paragraph class survived the delete'
    table = W.builds_table_html(ab, builds_mod.PRESET_FLAT, all_facts[0])
    text = W.gate_text(table)
    assert len(bl['builds']) == 2
    # the rule, one clause, no steps and no d(HP)
    assert 'Atk >= 150.24 + Def/HP staircase (4 steps)' in text
    assert 'd(HP)' not in text
    # the guarantee count, at BOTH confidence levels in one cell
    assert ('55 of 87, 4 of them material; 38 hold under every opponent-IV '
            'mode') in text
    # the rarest win, with its outside rate and the page's emphasis
    assert '<span class="wb-o3">1v2 Feraligatr (outside 10%)</span>' in table
    # the most-winning member and where SP1 sits
    assert '8/7/5 (378 of 684 matchups)' in text
    assert 'Def >= 101.40 and HP >= 125 (bulk box)' in text
    assert '2/11/13 (374 of 684 matchups); SP1 in' in text
    # descriptive: no directive anywhere in the table
    assert 'should' not in text
    # ...and the table lives inside the per-preset block, so the knob
    # switches it with the verdict lead above it
    # Round 10 split the per-setting loop: the verdict sentence and the
    # table are two groups of .wb-preset blocks with the ONE setting-
    # invariant sentence (the single-stat line) between them. Pre-fix this
    # read W.builds_block_html(...), which carried both.
    block = W.tables_block_html(all_facts[0], ab)
    for key in ab['presets']:
        one = block[block.index(f'data-preset="{key}"'):]
        one = one[:one.index('</table>')]
        assert 'wb-builds-table' in one, key
        assert 'wb-para' not in one, key


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_standouts_block_prints_what_is_the_spreads_own(shadow_sableye):
    """Item 3, and its arithmetic recomputed from the cube.

    The point of the block is the SUBTRACTION: of the decision matchups one
    exceptional spread wins, the nearest build guarantees most of them to
    every member, and the remainder is what hunting that exact spread buys.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    bl = ab['presets'][builds_mod.PRESET_FLAT]
    so = bl['standouts']
    assert [t['kind'] for t in so] == ['wins', 'score']
    assert so[0]['iv'] == '7/2/14@49.5' and so[0]['wins_all'] == 382
    assert so[1]['iv'] == '9/6/13@47.5' and so[1]['wins_all'] == 380
    # the highest-battle-score spread is the maximum of the scatter's own
    # default y axis, recomputed here off the cube
    ctx = ab['ctx']
    avg = ctx['scores'].reshape(ctx['n_iv'], -1).mean(axis=1)
    assert so[1]['idx'] == int(avg.argmax())
    assert abs(so[1]['avg_score'] - float(avg.max())) < 1e-9
    # both sit outside every build, and the subtraction is real
    for t in so:
        assert t['in_build'] is None
        won = ctx['win2'][t['idx']]
        cells = ab['frame']['cells']
        own = sum(1 for c in cells if won[c['k']])
        assert t['n_own_decision_wins'] == own
        b = bl['builds'][t['nearest_build']]
        got = sum(1 for ci, c in enumerate(cells)
                  if won[c['k']] and b['_g'][ci])
        assert t['n_from_nearest'] == got
        assert 0 < got < own, (got, own)
        # the nearest build is the one that covers the MOST of them
        for other in bl['builds']:
            assert got >= sum(1 for ci, c in enumerate(cells)
                              if won[c['k']] and other['_g'][ci])
    html = W.notable_html(all_facts[0], ab, builds_mod.PRESET_FLAT,
                          all_facts)
    text = W.gate_text(html)
    assert 'Of the 62 decision matchups it wins, Build 1 guarantees 49' in text
    # Round 8 item 2 merged 9/6/13 into 7/2/14 (six decision matchups apart,
    # above the 90% profile bar), so its own entry -- which read "Of the 62
    # decision matchups it wins, Build 1 guarantees 52 to every one of its 61
    # members" -- is a variant line on 7/2/14's entry instead. Pre-round-8
    # both sentences were in this block.
    assert 'Of the 62 decision matchups it wins, Build 1 guarantees 52' \
        not in text
    assert '9/6/13 (Highest avg battle score) differs from it by 6' in text
    # round 5: the remainder is not a COUNT any more -- the block names the
    # matchups and how much of the build wins each. Asserted in full in
    # test_the_standouts_name_the_matchups_behind_their_counts. (Round 4:
    # "the other 13 come with no guarantee from it"; round 3 and earlier:
    # "the other 13 are this one spread's own".)
    # Round 9 item 5 put the same fact on the entry's own fact line, with
    # both rates per cell, and deleted the second copy that carried only the
    # member shares. Pre-fix: 'The other 13 are matchups Build 1 does not
    # guarantee, with the share of its 61 members that win each: ...'.
    assert 'wins 13 it does not guarantee' in text
    assert 'are matchups Build 1 does not guarantee' not in text
    assert 'come with no guarantee from it' not in text
    assert "spread's own" not in text
    # rarity, in the brief's own encounter model (this is a shadow).
    # Round 9 renders it once under the list rather than inside every
    # Build criteria setting's block (DRY rule D1).
    tail = W.gate_text(W.notable_tail_html(all_facts[0], ab))
    assert 'Rocket-grunt encounters' in tail
    assert 'the grunt IV floor is not verified here' in tail
    # ...and the one piece of advice on the page, as its own call-out under
    # the list. Round 9 dissolved the 143-word fixed note: its definition
    # sentence is the glossary's 'build' entry (printed in Terms), its
    # window and family clauses were table facts, and this is the middle.
    # Pre-fix: ``W.standout_note(facts, ab, bl)``, whose text opened "A build
    # is a region of at least 50 spreads that all win a common core of
    # matchups".
    assert not hasattr(W, 'standout_note')
    assert W.NOTABLE_ADVICE in tail
    assert 'see the single-stat line for what changes the score' in tail
    assert W.NOTABLE_ADVICE not in text
    assert (f'at least {builds_mod.MIN_BUILD} of them'
            in glossary.TERMS['build']
            or 'at least fifty of them' in glossary.TERMS['build'])
    # both are in the Compare prefill
    listed = [tuple(iv) for _rule, iv in
              W.compare_spreads(all_facts[0], ab, builds_mod.PRESET_FLAT)]
    assert (7, 2, 14) in listed and (9, 6, 13) in listed
    assert len(listed) == len(set(listed)), listed


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_card_specs_come_from_the_builds(shadow_sableye):
    """Item 6: the card's spreads are the builds', not three stat poles.

    Pre-fix the card headlined "MATCHUP HUNTER 9/6/13", "MAX BULK 0/15/13"
    and "MAX BULK 15/15/0" -- picked by a stat-extreme rule no other surface
    on the page uses, so the card and the section named different spreads
    for different reasons.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    specs = W.card_specs(all_facts[0], ab)
    assert [s['iv'] for s in specs] == [[8, 7, 5], [2, 11, 13],
                                        [9, 6, 13], [7, 2, 14]]
    # round 4 titles: each names what the card SHOWS. Pre-fix: 'Highest
    # battle score' (which printed no score) and 'Most wins (outside the
    # builds)' (which printed no win count).
    assert [s['title'] for s in specs] == [
        'Build 1: Atk >= 150.24 + Def/HP steps',
        'Build 2: Def >= 101.40 and HP >= 125',
        'Highest avg battle score',
        'Most matchups won (outside the builds)']
    # the threshold on a card is the one the build is actually cut at:
    # formatting the raw atk_floor (150.245638) to two places rounds UP to
    # 150.25 and excludes real members
    assert '150.25' not in specs[0]['title']
    # every card carries its guarantee sentence and its rarest three cells
    for spec in specs:
        assert spec['guarantee']
        assert 1 <= len(spec['cells']) <= W.TOP_CELLS
        assert all(0.0 <= c['rate'] <= 1.0 for c in spec['cells'])
    # the build cards quote the build's own outside rate; the standout cards
    # quote the grid's, because "outside" has no meaning for one spread
    assert {c['word'] for c in specs[0]['cells']} == {'outside'}
    assert {c['word'] for c in specs[2]['cells']} == {'grid'}
    # ... and they agree with the section by construction
    assert specs[0]['guarantee'].startswith(
        'guarantees 55 of 87 decision matchups (Build 1)')
    # round 4: the standout cards lead with the number that MAKES them
    # standouts. Pre-fix both read "wins 62 of 87 decision matchups" and
    # nothing else, so neither card showed its own score or win count.
    assert specs[2]['guarantee'].startswith('Avg Battle Score ')
    assert '62 of 87 decision matchups' in specs[2]['guarantee']
    assert specs[3]['guarantee'].startswith('wins 382 of 684 matchups, the '
                                            'most of any spread on this grid')
    # no pole label survives on this path
    joined = ' '.join(s['title'] for s in specs)
    assert 'Matchup Hunter' not in joined and 'Max Bulk' not in joined
    # round 5: every spec also carries a SHORT name, which is what the dive's
    # threat chips print beside an IV spread (the card title's rule would not
    # fit there). Pre-round-5 there was no short name and those chips read the
    # retired pole styles.
    # round 6: one canonical short name per standout, and the title leads
    # with it (pre-fix the score standout was short 'Highest battle score',
    # titled 'Highest average battle score' and headed "Highest Avg Battle
    # Score (the scatter's own y axis)" -- three spellings)
    assert [s['short'] for s in specs] == [
        'Build 1', 'Build 2', 'Highest avg battle score', 'Most matchups won']
    assert all(s['title'].startswith(s['short']) for s in specs)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_wide_region_holds_the_standout_no_build_does(shadow_sableye):
    """RETIRED 2026-09-17 (round 8 item 2): ``card_build_membership``.

    This test pinned the {iv string: build name} map that labelled the
    composite-score "Top Picks" cards. Those cards are gone -- one Notable
    spreads list replaces them -- and so is the map. Pre-fix values, for the
    record: ``len(memb) == 61 + 114 + 583``, values exactly {'Build 1',
    'Build 2', 'Build 1 wide only'}, 61 in Build 1 and 114 in Build 2, each
    build's most-winning member mapping to its own build's short name, and
    ``memb['7/2/14'] == 'Build 1 wide only'``.

    What survives is the MEASUREMENT behind the last of those, which is a
    fact about the section and not about the retired cards: no build holds
    7/2/14 -- it fails Build 1's attack rung and the bulk box alike -- and
    round 6b's wide-region ranking key exists precisely so the wide region
    does. Recomputed here from the masks the page prints.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    bl = ab['presets'][builds_mod.PRESET_FLAT]
    meta = ab['ctx']['meta']
    i7 = next(k for k in range(ab['ctx']['n_iv'])
              if builds_mod.iv_str(meta, k).split('@')[0] == '7/2/14')
    assert [int(b['_mask'].sum()) for b in bl['builds']] == [61, 114]
    assert not any(b['_mask'][i7] for b in bl['builds'])
    assert bl['wide']['_mask'][i7]
    inb = bl['builds'][0]['_mask'] | bl['builds'][1]['_mask']
    assert int((bl['wide']['_mask'] & ~inb).sum()) == 583   # round 6 (E,F): 231
    # ... and the Notable spreads block is where a reader now reads it
    text = W.gate_text(W.notable_html(all_facts[0], ab,
                                      builds_mod.PRESET_FLAT, all_facts))
    assert 'It is in none of the builds, though Build 1 wide holds it.' in text


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_each_build_carries_a_drawable_plane_or_says_it_cannot(
        shadow_sableye):
    """Item 8(b), the producing half: what the stats view is given.

    Every family the describers can return maps to exactly one drawable
    shape, and the one that cannot (a build no rule fits) says so rather
    than getting an outline its members do not fill.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    pay = builds_mod.builds_payload(ab, 0)
    seen = set()
    for key, block in pay['presets'].items():
        for b in block['builds']:
            pl = b['plane']
            assert pl['kind'] in ('box', 'stair', 'line', 'none'), pl
            seen.add(pl['kind'])
            if pl['kind'] == 'box':
                assert pl['def'] != [None, None] or pl['hp'] != [None, None]
            if pl['kind'] == 'stair':
                assert len(pl['steps']) >= 2
                # the PRINTED attack floor, not the raw selected value
                assert pl['atkNote'].startswith('Atk >= ')
                assert '150.25' not in pl['atkNote']
            # round 5: the BOX and LINE families' attack notes had the bug
            # the staircase's ``stair_atk_head`` fixed -- f"{float(t):.2f}"
            # printed the 150.245638 cut as "Atk >= 150.25" beside a rule
            # that said 150.24, in one legend string (seen on the 1v1
            # preset's wide region). Every attack cut the note carries must
            # be spelled exactly as the build's own printed rule spells it.
            if pl.get('atkNote'):
                for bit in pl['atkNote'].split(' and '):
                    assert bit in b['desc'], (bit, b['desc'])
            if pl['kind'] == 'line':
                assert pl['k'] > 0 and pl['c'] > 0
    # this blob exercises three of the four on one arm
    assert {'box', 'stair', 'line', 'none'} >= seen
    assert len(seen) >= 3, seen
    # the scatter's own maximum travels with the payload, pre-formatted
    assert pay['bestScore']['iv'] == '9/6/13@47.5'
    assert pay['bestScore']['avgStr'] == '534.2'


# ---------------------------------------------------------------------------
# 7. Round 4 -- the 2026-09-16 ROUND-3 review (numbers, reader, contracts)
# ---------------------------------------------------------------------------


_FACTS_CACHE = {}


def _facts_for(name):
    """(state, all_facts) for one blob, loaded once per test session."""
    if name not in _FACTS_CACHE:
        path = require_blob(name)
        state = B.load_blob(str(path))
        _FACTS_CACHE[name] = (state, W.prepare(state, str(path)))
    return _FACTS_CACHE[name]


def test_the_builds_caption_explains_every_marker_the_view_draws():
    """The builds plot marks BOTH standouts, so the caption names both.

    Pre-fix it named the diamond, the triangles and the open square and
    said nothing about the open cross (the highest Avg Battle Score), which
    the same view has drawn since round 3 -- an unexplained marker in the
    default view. The stats caption already named it.
    """
    # Round 10 cut this caption to two sentences: the legend already names
    # every key on its own line (11 keys, zero overlaps, measured), and at
    # 900 px the round-9 caption was 20 lines under it. The markers it
    # listed are the legend's job; the caption says what the PICTURE is.
    # Pre-fix: 'open cross', 'Avg Battle Score', 'diamond', 'triangle' and
    # 'open square' were all in BUILDS_CAPTION (2026-09-19 round-10 review).
    for marker in ('open cross', 'diamond', 'triangle', 'open square'):
        assert marker not in W.BUILDS_CAPTION, marker
    assert 'hollow ring' in W.BUILDS_CAPTION
    assert 'Gold stars' in W.BUILDS_CAPTION
    # positive control: the stats caption's own wording is unchanged
    assert 'the open cross the highest Avg Battle Score' in W.STATS_CAPTION
    # round 5: the builds view draws one more trace -- the wide region
    # around Build 1 -- so the caption names it too. Round 7b: it is the
    # containment ring, named by the wording its own test pins.
    # Round 10 cut the builds caption to two sentences: the LEGEND names
    # every key on its own line (measured: 11 keys, 0 overlapping pairs at
    # 1400 and 900 px), so the caption says what the picture is rather than
    # re-describing them. Pre-fix: 'Build 1 wide', 'lighter tint' and
    # 'stat-product rank-1 (SP1)' were all in it (2026-09-19 round-10 review). The
    # wide rule is still named as a ring, and the STATS caption is unchanged.
    assert 'the wide rule' in W.BUILDS_CAPTION
    assert 'stat-product rank-1 (SP1)' in W.STATS_CAPTION


def test_the_emphasis_key_defines_both_rates_it_weights():
    """Item 5's key described the outside rate only, while the Standouts
    block and the cards use the same three typefaces on the GRID rate with
    no definition anywhere. Pre-fix it opened "Weight follows the outside
    rate:".
    """
    assert 'outside N%' in W.EMPH_KEY and 'grid N%' in W.EMPH_KEY
    assert not W.EMPH_KEY.startswith('Weight follows the outside rate')
    for phrase in ('fewer than half', 'fewer than a quarter',
                   'fewer than a tenth', 'nine in ten'):
        assert phrase in W.EMPH_KEY, phrase


def test_an_approximate_rule_is_flagged_on_a_synthetic_build():
    """The fast positive control for the "about" flag: a rule that takes in
    one non-member and misses one is printed as approximate on the
    paragraph, the summary line and the card title.

    Pre-fix only the builds table's fidelity clause said so, and the plain
    Sableye page printed "at Atk >= 125.00 and Def + 1.9*HP >= 345.067" as
    exact on three surfaces -- the un-flagged known-wrong case Michael's
    standing rule forbids.
    """
    exact = {'rule': 'atk >= 125 and def >= 100', 'terms': [['atk', '>=', 125.0],
             ['def', '>=', 100.0]], 'n_extra': 0, 'n_missing': 0,
             'jaccard': 1.0, 'family': 'two_box'}
    approx = dict(exact, n_extra=1, n_missing=1, jaccard=0.9937)
    b_exact = {'description': exact, 'size': 318, 'role': 'primary',
               'sets': ['S5 box -> 1v2 Snorlax']}
    b_approx = dict(b_exact, description=approx)
    assert not W.rule_is_approx(b_exact)
    assert W.rule_is_approx(b_approx)
    # ``approx_clause`` is DELETED (round 10). Pre-fix:
    #   W.approx_clause(b_exact)  == ''
    #   W.approx_clause(b_approx) == 'That rule takes in 1 spread that is
    #       not a member and misses 1; the member list in the table is the
    #       build.'
    # The row expander printed it directly under ``_fidelity_clause``, which
    # says the same two counts, and under a Rule cell whose "~" hover says
    # them a third time (2026-09-19 round-10 review).
    assert not hasattr(W, 'approx_clause')
    assert W._fidelity_clause(b_approx) == (
        'The rule covers 99% of the same spreads (1 extra, 1 missed); '
        'the member list is the build.')
    assert W._fidelity_clause(b_exact) == (
        'The rule fits exactly: these spreads and no others.')
    assert W.build_rule_phrase(b_approx).startswith('roughly ')
    assert 'roughly ' in W.build_summary_phrase(b_approx)
    assert W.card_title_rule(b_approx).startswith('roughly ')
    # ... and an exact rule carries no hedge
    for phrase in (W.build_rule_phrase(b_exact),
                   W.build_summary_phrase(b_exact),
                   W.card_title_rule(b_exact)):
        assert 'roughly' not in phrase, phrase


def test_the_staircase_geometry_skips_zero_length_segments():
    """Consecutive HP steps that share one defense floor emitted a shape
    with x0 == x1 and y0 == y1 -- one on the flat Sableye staircase, three
    on the 1v1 one. Invisible, but dead shapes in the layout.
    """
    src = _engine()
    body = src[src.index('function _wbPlaneShapes('):
               src.index('function _wbGuaranteedInScen(')]
    assert 'if (x0 === x1 && y0 === y1) return;' in body
    # positive control: the guard sits inside the segment emitter it guards
    assert body.index('function line(') < body.index(
        'if (x0 === x1 && y0 === y1) return;') < body.index('shapes.push({ type')


def test_the_member_list_header_names_its_own_sort_order():
    """The list is sorted by STAT PRODUCT rank (attack counts too), so the
    first member is not the bulkiest. Pre-fix the header said "bulkiest
    first" over a list the JS sorts by ``L.spRanks``.
    """
    src = _engine()
    render = src[src.index('function wbRenderMembers('):
                 src.index('function wbMoreRows(')]
    assert 'L.spRanks[a] - L.spRanks[b]' in render
    body = SCRIPTS_DIR.joinpath('deep_dive_which_build.py').read_text()
    assert "'highest stat product first" in body or \
           'highest stat product first' in body
    assert 'bulkiest first' not in body


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_outside_rates_are_rounded_once_at_print_time(shadow_sableye):
    """``cell_rows`` stored ``round(ow, 4)`` and ``_pct`` rounded that again.

    A true 0.3749632677 was stored as 0.375 and printed 38% where the data
    says 37% (errors went both ways), and the same stored value decided the
    emphasis band and the near-free bucket, so a rate within 1e-4 of a band
    edge could be weighted wrongly. Recomputed here from the cube.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    Wd = ab['frame']['Wd']
    rows = []
    for bl in ab['presets'].values():
        for b in bl['builds']:
            outside = ~b['_mask']
            for r in b['guaranteed']:
                raw = float(Wd[outside, r['ci']].mean())
                assert abs(raw - r['outside_wr']) < 1e-12, r['cell']
                assert W.emph_class(r['outside_wr']) == W.emph_class(raw)
                rows.append(r['outside_wr'])
    assert len(rows) > 200, len(rows)
    # The pre-fix behaviour, recorded: at least one row on this blob prints
    # a different percent through the 4-dp store than through the raw value.
    differs = [v for v in rows
               if f"{round(round(v, 4) * 100):.0f}%" != W._pct(v)]
    assert differs, 'no row here distinguishes the two roundings'


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_printed_staircase_reproduces_its_own_build(shadow_sableye):
    """A staircase's steps are printed as the decimals that SELECT them.

    Pre-fix the raw float was formatted with %g, which rounds half-up and
    lands ABOVE the true per-HP floor, so a reader applying the printed rule
    literally dropped the boundary member of every step: 57 spreads out of
    Build 1's 61.
    """
    import numpy as np
    _state, all_facts, _path = shadow_sableye
    checked = 0
    for facts in all_facts:
        ab = facts.get('_builds')
        if not ab:
            continue
        ctx = ab['ctx']
        atk, dfn, hp = (ctx['planes']['atk'], ctx['planes']['def'],
                        ctx['planes']['hp'])
        for bl in ab['presets'].values():
            for b in bl['builds']:
                d = b['description']
                if not d or not d.get('steps'):
                    continue
                floor = float(builds_mod.stair_atk_head(d).split('>=')[1])
                need = np.full(atk.shape, np.inf)
                for h, exact, _n, printed in d['steps']:
                    need[hp == h] = printed
                    # never above the true floor, so the printed rule can
                    # only ever be a superset of its own membership
                    assert printed <= exact + 1e-12, (h, printed, exact)
                got = int(((atk >= floor) & (dfn >= need)).sum())
                assert got == b['size'], (b['role'], got, b['size'])
                checked += 1
    assert checked >= 2, checked


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_rarest_win_cell_names_a_matchup_the_setting_counts(
        shadow_sableye):
    """The rarest guarantee a build buys, in the column that names it.

    Pre-fix this fact was the per-build paragraph's "most notably" three,
    and its bug was scope: under the Even setting Build 1's paragraph said
    "guarantees 29 of the 43 decision matchups in 0v0 / 1v1 / 2v2 shields"
    and then named 1v0 Tinkaton -- a matchup the same sentence says the
    setting does not count. Round 9's cell is one matchup, and it has to be
    one of the counted ones for the same reason.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    labels = ab['ctx']['scen_labels']
    seen_narrow = 0
    for key, bl in ab['presets'].items():
        counted = {labels[i] for i, w in enumerate(bl['weights']) if w > 0}
        for b in bl['builds']:
            cell = W.gate_text(W.rarest_win_cell(b))
            if cell == '--':
                continue
            rows = []
            for scen_rows in (b.get('guaranteed_by_scenario') or {}).values():
                rows.extend(scen_rows)
            rarest = min(rows, key=lambda r: (r['outside_wr'], r['rank']))
            assert rarest['cell'] in cell, (key, cell)
            # every guaranteed_by_scenario group is a scenario the build
            # covers; the cell has to name one of them
            assert rarest['cell'].split()[0] in set(labels)
            if len(counted) < len(labels):
                seen_narrow += 1
    assert seen_narrow >= 2, seen_narrow


@pytest.mark.local_artifacts
@pytest.mark.slow
@pytest.mark.parametrize('blob', [SABLEYE_SHADOW, SABLEYE_PLAIN, MELMETAL])
def test_only_the_headers_own_rectangle_is_the_bulk_box(blob):
    """"The bulk box" is the box the header's Alternative row names, and
    nothing else.

    Pre-fix the definite article was attached to ANY Def-floor + HP-floor
    rule, so one page called two different boxes the bulk box (Def >=
    101.40 with HP >= 125 under two presets, Def >= 99.99 with HP >= 121
    under the third), and on the plain page the section printed Def >=
    120.00 for the very box its own header row calls Def >= 120.03.
    """
    _state, all_facts = _facts_for(blob)
    seen_header_box = seen_other_box = 0
    for facts in all_facts:
        ab = facts.get('_builds')
        if not ab:
            continue
        alt = facts.get('alternative') or {}
        for key, bl in ab['presets'].items():
            for i, b in enumerate(bl['builds']):
                phrase = W.build_rule_phrase(b, facts)
                summary = W.build_summary_phrase(b, facts)
                if W.is_header_bulk_box(b, facts):
                    seen_header_box += 1
                    assert phrase.startswith('the bulk box, '), phrase
                    assert summary.startswith('the bulk box '), summary
                    # one box, one pair of numbers on the page
                    numbers = B.alt_pair_short(alt).replace(', ', ' and ')
                    assert numbers in phrase, (numbers, phrase)
                    assert b['size'] == alt['n'], (b['size'], alt['n'])
                else:
                    assert 'bulk box' not in phrase, (key, phrase)
                    assert 'bulk box' not in summary, (key, summary)
                    if W.is_bulk_box(b):
                        seen_other_box += 1
                        assert phrase.startswith('a Def/HP box, '), phrase
    # Not every page HAS the header's own rectangle as a build -- on
    # Melmetal the bulk build is an intersection of that rectangle with a
    # cell's winner set, which is a different (55-spread) region and so is
    # "a Def/HP box". What every page must do is name at most the one.
    assert seen_header_box + seen_other_box >= 1


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_header_box_build_quotes_the_headers_own_numbers(shadow_sableye):
    """The positive control for the test above: a page that DOES build the
    header's rectangle names it "the bulk box" and prints the header row's
    numbers, not the describer's own decimals for the same spreads.
    """
    _state, all_facts, _path = shadow_sableye
    found = 0
    for facts in all_facts:
        ab = facts.get('_builds')
        if not ab:
            continue
        alt = facts['alternative']
        for key, bl in ab['presets'].items():
            for i, b in enumerate(bl['builds']):
                if not W.is_header_bulk_box(b, facts):
                    continue
                found += 1
                want = B.alt_pair_short(alt).replace(', ', ' and ')
                assert W.build_rule_phrase(b, facts) == f'the bulk box, {want}'
                assert W.build_summary_phrase(b, facts) == \
                    f'the bulk box {want}'
                assert W.card_title_rule(b, facts) == want
    assert found >= 1, 'no build on this blob is the header rectangle'


@pytest.mark.local_artifacts
@pytest.mark.slow
@pytest.mark.parametrize('blob', [SABLEYE_SHADOW, SABLEYE_PLAIN, MELMETAL])
def test_every_approximate_rule_on_a_real_page_says_so(blob):
    """The invariant on real data, whatever the rankings do: a rule that
    does not reproduce its member list is hedged everywhere it is printed,
    and an exact one is hedged nowhere. The synthetic test above is the
    positive control that the hedge can appear at all.
    """
    _state, all_facts = _facts_for(blob)
    for facts in all_facts:
        ab = facts.get('_builds')
        if not ab:
            continue
        for key, bl in ab['presets'].items():
            table = W.builds_table_html(ab, key, facts)
            for i, b in enumerate(bl['builds']):
                summary = W.build_summary_phrase(b, facts)
                title = W.card_title_rule(b, facts)
                # Round 9 item 2: the hedge on the TABLE is the `~` glyph
                # with a hover saying how approximate, and the sentence that
                # used to open the build's paragraph ("That rule takes in N
                # spreads that are not members; the member list in the table
                # is the build") is in the row's own expander. Pre-fix the
                # paragraph carried 'at roughly ' and that sentence.
                cell = W.rule_cell_html(b, facts)
                exp = W.gate_text(W.build_row_expander(ab, bl, b, i, key,
                                                       facts))
                if W.rule_is_approx(b):
                    assert W.RULE_APPROX_GLYPH in cell, (key, cell)
                    assert 'class="wb-approx"' in cell
                    assert 'of the same spreads' in cell
                    # Round 10: the row expander says the fidelity ONCE, in
                    # ``_fidelity_clause``'s own sentence. Pre-fix it also
                    # carried approx_clause's 'the member list in the table
                    # is the build'.
                    assert 'of the same spreads' in exp
                    assert 'the member list is the build' in exp
                    assert 'roughly ' in summary, summary
                    assert 'roughly ' in title, title
                else:
                    assert W.RULE_APPROX_GLYPH not in cell, (key, cell)
                    assert 'roughly' not in summary, summary
                    assert 'roughly' not in title, title
                assert 'd(HP)' not in W.gate_text(table)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_standouts_block_claims_no_exclusivity(shadow_sableye):
    """Pre-fix: "so the other 13 are this one spread's own".

    Each of those 13 cells is won by hundreds of other spreads -- what they
    lack is a REGION-WIDE guarantee -- and the block never printed the
    number a reader needs to compare the two plans: what the hunt costs
    (7/2/14 loses 6 matchups every Build 1 member wins).
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    bl = ab['presets'][builds_mod.PRESET_FLAT]
    text = W.gate_text(W.notable_html(all_facts[0], ab,
                                      builds_mod.PRESET_FLAT, all_facts))
    assert "spread's own" not in text
    assert 'It is 1 of the 4096 spreads on this grid.' not in text
    cells = ab['frame']['cells']
    # Round 8 item 2: the block prints one paragraph per NOTABLE entry, and
    # 9/6/13 merged into 7/2/14. The recomputation below is unchanged and
    # still runs over both standouts; only the printed-sentence assertions
    # are scoped to the entries that survived the merge.
    printed = {t['idx'] for t in bl['notable']}
    for t in bl['standouts']:
        if t['in_build'] is not None:
            continue
        nb = bl['builds'][t['nearest_build']]
        own, got = t['n_own_decision_wins'], t['n_from_nearest']
        lost = t['n_lost_from_nearest']
        # recomputed from the cube: what the build guarantees and this
        # spread does not win
        won = ab['ctx']['win2'][t['idx']]
        assert lost == sum(1 for ci, c in enumerate(cells)
                           if nb['_g'][ci] and not won[c['k']])
        assert lost == nb['n_guaranteed'] - got
        if t['idx'] not in printed:
            continue
        assert (f"guarantees {got} to every one of its {nb['size']} members"
                in text)
        # round 5: the counted remainder became the named list, and the cost
        # sentence names its matchups (pre-round-5: "the other 13 come with
        # no guarantee from it" / "It loses 6 of the 55 matchups Build 1
        # guarantees.")
        nm = W.role_short(nb, t['nearest_build'])
        # Round 9 item 5 compacted both lists onto the entry's fact line.
        # Pre-fix: "The other 13 are matchups Build 1 does not guarantee,
        # with the share of its 61 members that win each: ..." and "It loses
        # 6 of the 55 matchups Build 1 guarantees to every member: ...".
        assert f"vs {nm}: wins {own - got} it does not guarantee" in text
        assert (f"loses: {lost} of the {nb['n_guaranteed']} {nm} guarantees"
                in text)


@pytest.mark.local_artifacts
@pytest.mark.slow
@pytest.mark.parametrize('blob', [SABLEYE_SHADOW, SABLEYE_PLAIN, MELMETAL])
def test_the_notable_list_ends_on_one_advice_callout(blob):
    """Round 9 item 5 dissolved the two-branch fixed note into one call-out.

    Pre-fix the block ended on ``standout_note`` (143 words opening "A build
    is a region of at least 50 spreads ...") when a standout sat outside
    every build, and on ``STANDOUT_NOTE_INSIDE`` ("Every standout here sits
    inside a build ...") when neither did -- two long paragraphs arguing
    about which case the page was in. The definition is the glossary's
    'build' entry (printed once in Terms), the window and family clauses
    were table facts, and what is left is the one piece of advice on the
    page, labelled, under the list.
    """
    _state, all_facts = _facts_for(blob)
    assert not hasattr(W, 'standout_note')
    assert not hasattr(W, 'STANDOUT_NOTE')
    assert not hasattr(W, 'STANDOUT_NOTE_INSIDE')
    seen = 0
    for facts in all_facts:
        ab = facts.get('_builds')
        if not ab:
            continue
        tail = W.gate_text(W.notable_tail_html(facts, ab))
        # Round 10: the call-out follows the page's LINE STATUS. Pre-fix it
        # was the fixed NOTABLE_ADVICE on every page, so Melmetal GL -- no
        # line, and an SP1 that already wins the most -- read "If you are
        # hunting, hunt a build instead -- see the single-stat line for what
        # changes the score" four inches under "No single-stat line on this
        # moveset." (2026-09-19 round-10 review, major 4).
        want = W.notable_advice(facts)
        assert want in tail
        if facts['floor'] is None and W.sp1_wins_most(facts):
            assert want is W.NOTABLE_ADVICE_SP1
            assert 'single-stat line' not in tail
        # ...and it is invariant per page, so it is rendered once, not once
        # per Build criteria setting (DRY rule D1)
        for key in ab['presets']:
            entries = W.gate_text(W.notable_html(facts, ab, key, all_facts))
            assert want not in entries
        seen += 1
    assert seen >= 1, blob


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_standout_cards_print_what_makes_them_standouts(shadow_sableye):
    """Pre-fix both standout cards read "wins 62 of 87 decision matchups"
    and nothing else, so "Highest battle score" showed no score and "Most
    wins" showed no win count -- the two cards were indistinguishable to a
    reader who had not opened the section.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    bl = ab['presets'][builds_mod.PRESET_FLAT]
    specs = {s['title']: s for s in W.card_specs(all_facts[0], ab)}
    by_kind = {t['kind']: t for t in bl['standouts']}
    score, wins = by_kind['score'], by_kind['wins']
    sc = specs[W.CARD_TITLE_SCORE]
    assert f"Avg Battle Score {score['avg_score']:.1f}" in sc['guarantee']
    assert (f"wins {score['wins_all']} of {score['denominator_all']} matchups"
            in sc['guarantee'])
    wc = specs[W.CARD_TITLE_WINS]
    assert (f"wins {wins['wins_all']} of {wins['denominator_all']} matchups, "
            f"the most of any spread on this grid" in wc['guarantee'])
    # both still carry the decision-matchup count and the nearest build
    for spec in (sc, wc):
        assert f"of {ab['n_decision_cells']} decision matchups" in \
            spec['guarantee']
        assert 'it is in none of the builds' in spec['guarantee']
        assert "spread's own" not in spec['guarantee']
        # round 5: the same two lists the block prints, in short form
        # (pre-round-5 the card said only "it loses N that Build 1
        # guarantees")
        assert ' does not guarantee (' in spec['guarantee']
        assert ' and loses ' in spec['guarantee']


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_standout_inside_a_build_names_its_role_on_that_card():
    """Melmetal: the most-winning spread, the highest battle score and
    stat-product rank-1 are all 1/15/14, which is Build 1's most-winning
    member. The dedup dropped the standout card silently, so the card set
    lost a role the section had named; now the build card carries it.
    """
    _state, all_facts = _facts_for(MELMETAL)
    seen = 0
    for facts in all_facts:
        ab = facts.get('_builds')
        if not ab or not ab.get('presets'):
            continue
        bl = ab['presets'].get(builds_mod.PRESET_FLAT)
        if not bl or not bl['builds']:
            continue
        specs = W.card_specs(facts, ab)
        ivs = [tuple(s['iv']) for s in specs]
        assert len(ivs) == len(set(ivs)), ivs
        for t in bl['standouts']:
            iv = tuple(int(x) for x in t['iv'].split('@')[0].split('/'))
            holder = next((s for s in specs if tuple(s['iv']) == iv), None)
            if t['in_build'] is None or holder is None:
                continue
            if holder['title'].startswith('Build'):
                seen += 1
                assert W.CARD_ALSO[t['kind']] in holder['title'], \
                    holder['title']
    assert seen >= 1, 'no standout coincides with a build card here'


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_emphasis_key_is_printed_once_above_the_figure(shadow_sableye):
    """The key that defines the page's three typefaces, rendered once.

    Pre-fix it was inside every one of the three hidden preset blocks
    (``block.count(key) == len(ab['presets'])``, with the key required above
    the first ``wb-para``). The paragraphs are gone and the key is
    preset-invariant, so DRY rule D1 puts it outside the loop -- above the
    figure, still ahead of every cell that uses the emphasis.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    block = W.tables_block_html(all_facts[0], ab)
    key = W._esc(W.EMPH_KEY)
    assert block.count(key) == 0
    html = W.section_html(all_facts, 0)
    assert html.count(key) == 1
    # ahead of the figure, and after the table whose cells it weights
    assert html.index(key) < html.index('<div class="wb-plotbox"')
    assert html.index('wb-builds-table') < html.index(key)
    # Round 10: the verdict sentence is its own group of .wb-preset blocks
    # ABOVE the setting-invariant single-stat-line sentence, which is above
    # the tables (pre-fix: 'wb-builds-lead' then 'wb-builds-table' inside
    # one block). Reading order: who -> verdict -> line -> table.
    # On the MARKUP, not the class names: section_html prefixes a <style>
    # block that mentions every one of these selectors.
    assert (html.index('<p class="wb-who">')
            < html.index('<p class="wb-answer-line">')
            < html.index('<p class="wb-linestatus">')
            < html.index('<table class="wb-builds-table">'))
    # and the members list header names the sort order the JS actually uses
    assert 'highest stat product first' in html
    assert 'bulkiest first' not in html


# ---------------------------------------------------------------------------
# 8. Round 5 (2026-09-17) -- SP1, the standouts' two matchup lists, and the
#    nested wide build.
# ---------------------------------------------------------------------------


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_section_defines_sp1_once_and_then_writes_sp1(shadow_sableye):
    """Item 2. Pre-fix every surface spelled it out every time: the
    paragraphs ("rank-1 is outside it"), the collapsed line ("and holds
    rank-1"), the builds table's column header ("Stat-product rank-1").
    """
    _state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    ab = facts['_builds']
    key = builds_mod.PRESET_FLAT
    lead = W.builds_lead(facts, ab, key, all_facts)
    assert lead.endswith('Stat-product rank-1 (SP1) is the spread with the '
                         'largest attack x defense x HP on this grid; it is '
                         'written SP1 below.'), lead[-160:]
    # Round 9: the short form is in the table's own column now. Pre-fix the
    # per-build paragraphs said "SP1 is outside it" / "SP1 is inside it".
    table = W.gate_text(W.builds_table_html(ab, key, facts))
    assert 'SP1 in' in table
    assert 'rank-1 is outside it' not in table
    # the collapsed line is its own surface: a reader who never opens the
    # section sees only that, so it spells the term out again
    line = W.builds_summary(facts, ab, key, all_facts)
    assert 'holds stat-product rank-1 (SP1)' in line
    html = W.section_html(all_facts, 0)
    # Round 9 folded the one-word SP1 column into 'Best member / SP1'.
    # Pre-fix: '<th>SP1</th>'.
    assert '<th>Best member / SP1</th>' in html
    assert '<th>SP1</th>' not in html
    assert '<th>Stat-product rank-1</th>' not in html
    # ... and the glossary tooltip follows the short form, so the first SP1 a
    # reader meets still carries the definition
    assert 'stat-product rank-1' in glossary.terms_html(['stat-product rank-1'])
    assert 'Terms used here' in html
    marker = W.TermMarker()
    marked = marker.mark('<p>SP1 is outside it.</p>')
    assert 'wb-term' in marked and 'stat-product rank-1' in marker.used


def test_the_panel_legend_names_sp1_with_the_term_it_abbreviates():
    """The plot's own legend entry, which is a label and not prose.

    Read off the RAW source, not through ``strip_js``: that helper blanks
    string literals, which is exactly what this pin is about.
    """
    js = ENGINE_JS.read_text()
    assert js.count("_wbMarkTrace('Stat-product rank-1 (SP1)'") == 3
    # pre-round-5 spelling, with the call itself as the positive control
    assert "_wbMarkTrace('Stat-product rank-1'," not in js
    assert js.count('_wbMarkTrace(') > 3


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_standouts_name_the_matchups_behind_their_counts(shadow_sableye):
    """Item 3, recomputed from the cube.

    Pre-fix the block printed the two COUNTS and no names: "the other 13 come
    with no guarantee from it" and "It loses 6 of the 55 matchups Build 1
    guarantees" -- a reader could not tell which 13 or which 6, nor whether
    the 13 were cells the build almost wins anyway.
    """
    _state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    ab = facts['_builds']
    bl = ab['presets'][builds_mod.PRESET_FLAT]
    cells, Wd = ab['frame']['cells'], ab['frame']['Wd']
    t = bl['standouts'][0]
    assert t['iv'] == '7/2/14@49.5'
    nb = bl['builds'][t['nearest_build']]
    won = ab['ctx']['win2'][t['idx']]
    beyond = {c['label']: float(Wd[nb['_mask'], ci].mean())
              for ci, c in enumerate(cells)
              if won[c['k']] and not nb['_g'][ci]}
    lost = {c['label'] for ci, c in enumerate(cells)
            if nb['_g'][ci] and not won[c['k']]}
    assert {r['cell'] for r in t['beyond_cells']} == set(beyond)
    assert {r['cell'] for r in t['lost_cells']} == lost
    assert len(t['beyond_cells']) == t['n_own_decision_wins'] - \
        t['n_from_nearest'] == 13
    assert len(t['lost_cells']) == t['n_lost_from_nearest'] == 6
    assert lost == {'0v1 Empoleon', '1v1 Empoleon (Shadow)', '1v1 Hippowdon',
                    '1v2 Feraligatr', '1v0 Azumarill', '2v2 Empoleon'}
    # ascending by the share of the build's own members that win the cell
    shares = [r['share'] for r in t['beyond_cells']]
    assert shares == sorted(shares)
    # Round 9 retired MEMBER_SHARE_TAIL with the second copy of this list
    # (the fact line carries both rates per cell now). Pre-fix the bar was
    # ``W.MEMBER_SHARE_TAIL`` == 0.25.
    assert not hasattr(W, 'MEMBER_SHARE_TAIL')
    assert shares[0] == 0.0 and max(shares) > 0.25
    for r in t['beyond_cells']:
        assert abs(r['share'] - beyond[r['cell']]) < 1e-12
    html = W.notable_html(facts, ab, builds_mod.PRESET_FLAT, all_facts)
    text = W.gate_text(html)
    # (i) the edge, against the best a region can offer
    # Round 8 item 2 put this spread's own decision-matchup count in before
    # the build it is measured against; appended after that clause it read as
    # the build's member's count. Pre-round-8: "It wins 382 of 684 matchups
    # over all nine shield scenarios; Build 1's most-winning member wins
    # 378."
    # Round 9 item 5 put these on the entry's stat line, in the compact
    # format. Pre-fix: "It wins 382 of 684 matchups over all nine shield
    # scenarios, and 62 of the 87 decision matchups; Build 1's most-winning
    # member wins 378."
    assert 'wins 382 of 684 over all nine shield scenarios' in text
    assert '62 of 87 decision matchups' in text
    assert "Build 1's most-winning member wins 378" in text
    # (ii) the cells it wins that the build does not guarantee, with the
    #      share of the build's members that win each, and the >25% tail
    # Round 9 item 5: one fact line per list, three cells shown and the
    # rest behind a "+N" that reveals them in place. Pre-fix the lead-ins
    # were "The other 13 are matchups Build 1 does not guarantee, with the
    # share of its 61 members that win each: " and "It loses 6 of the 55
    # matchups Build 1 guarantees to every member: ".
    assert 'vs Build 1: wins 13 it does not guarantee' in text
    assert '1v2 Electrode (Hisuian) (grid 8%; 0% of members)' in text
    assert '1v2 Sableye (grid 32%; 11% of members)' in text
    assert '+10' in text
    # (iii) what the hunt costs, by name
    assert 'loses: 6 of the 55 Build 1 guarantees' in text
    assert '1v2 Feraligatr (grid 11%' in text
    assert '2v2 Empoleon (grid 64%' in text
    # the round-4 sentence the lists replace
    assert 'come with no guarantee from it' not in text
    # the emphasis is the page's one spelling, banded on the GRID rate
    assert '<span class="wb-o3">1v2 Electrode (Hisuian) (grid 8%; 0% of ' \
        'members)</span>' in html
    # (iv) round 6: the MEASURED version of the block's closing claim, and
    # recomputed here from the cube rather than re-asserting the producer
    #
    # Round 8 item 2 merged 9/6/13 into 7/2/14's entry (six decision matchups
    # apart, above the 90% profile bar), so its own paragraph -- which ended
    # "Only 2 other spreads on this grid win all 62 of the decision matchups
    # it wins." -- is a variant line now. The MEASUREMENT is still recomputed
    # for both standouts; only the printed sentence is asserted for the entry
    # the block prints.
    import numpy as _np
    printed = {t3['idx'] for t3 in bl['notable']}
    for t2, sentence in ((bl['standouts'][0],
                          'No other spread on this grid wins all 62 of the '
                          'decision matchups it wins.'),
                         (bl['standouts'][1],
                          'Only 2 other spreads on this grid win all 62 of '
                          'the decision matchups it wins.')):
        own = _np.array([bool(ab['ctx']['win2'][t2['idx']][c['k']])
                         for c in cells])
        peers = int(Wd[:, own].all(axis=1).sum()) - 1
        assert t2['n_profile_peers'] == peers
        if t2['idx'] in printed:
            assert sentence in text
        else:
            assert sentence not in text
    # and the "Its rarest wins" sentence is gone from the OUTSIDE branch: it
    # named three cells the two lists above had already printed with their
    # grid rates (round 6 review). Round 8 item 2 put three INSIDE-a-build
    # entries in this same block (SP1 and the two builds' most-winning
    # members), and those do carry it -- so the absence is scoped to the
    # paragraph it was ever about. Pre-round-8 the block held only the two
    # standouts and the bare `not in text` was the whole test.
    # Round 9 item 5: each entry is a <div class="wb-note-entry">, not a
    # paragraph. Pre-fix the scan was `<p class="wb-para">(.*?)</p>`.
    outside = re.search(r'<div class="wb-note-entry">(.*?)</div>\s*<div',
                        html, re.S).group(1)
    assert '7/2/14' in outside and 'in none of the builds' in outside
    assert 'rarest wins' not in W.gate_text(outside)
    assert 'rarest wins' in text, 'the inside entries lost their control'


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_one_short_name_per_standout_on_every_surface(shadow_sableye):
    """The section head, the card title and the chip name lead with the SAME
    words. Round 5 shipped three spellings each -- "Highest Avg Battle Score
    (the scatter's own y axis)" in the section, "Highest average battle
    score" on the card and "Highest battle score" on the chips and the
    scatter overlay, the last of which drops the word that says the score is
    an average (2026-09-17 round 6 review).
    """
    _state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    ab = facts['_builds']
    specs = {sp['short']: sp for sp in W.card_specs(facts, ab)}
    assert 'Most matchups won' in specs and 'Highest avg battle score' in specs
    for kind, short in W.CARD_SHORT.items():
        # the section head carries its qualifier after the short name, so
        # the comparison is on the leading name (the 'both' head reads
        # "Most matchups won (all nine shield scenarios) and highest avg
        # battle score")
        assert W.STANDOUT_KIND[kind].startswith(short.split(' and ')[0]), kind
    assert W.CARD_TITLE_SCORE.startswith(W.CARD_SHORT['score'])
    assert W.CARD_TITLE_WINS.startswith(W.CARD_SHORT['wins'])
    assert W.CARD_TITLE_BOTH.startswith(W.CARD_SHORT['both'])
    # the chips read the card's shorts, so the section head a reader lands on
    # starts with the chip they came from
    text = W.gate_text(W.notable_html(facts, ab, builds_mod.PRESET_FLAT,
                                      all_facts))
    # Round 8 item 2: 9/6/13 merged into 7/2/14's entry, so its canonical
    # short name appears as the variant's label rather than as a heading.
    # Pre-round-8 both read "<short> (" as block heads.
    assert 'Most matchups won (' in text
    assert '(Highest avg battle score)' in text
    assert 'Highest battle score' not in text
    assert 'Highest Avg Battle Score' not in text
    # the section PLOT's two standout markers carry the same two names
    # (pre-fix: 'Wins the most matchups over ' + scope, 'Highest Avg Battle
    # Score' -- a fourth and fifth spelling, in the legend)
    js = ENGINE_JS.read_text()
    assert "_wbMarkTrace('Most matchups won (' + gbScope + ')'" in js
    assert "_wbMarkTrace('Highest avg battle score', bsi," in js
    assert "_wbMarkTrace('Most matchups won', gbi," in js
    assert 'Highest Avg Battle Score' not in js
    assert 'function _wbMarkTrace(' in js          # positive control


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_single_stat_line_status_prints_this_pages_own_two_numbers(
        shadow_sableye):
    """The one-sentence line status, computed from the page's own facts.

    Round 9 item 1 reduced the v3 five-row strip to one sentence at the top
    of the section (the strip itself is in the "The single-stat line"
    expander). It prints the page's line, the matchup that line decides, and
    how far SP1 sits below it.

    Pre-fix the two numbers below lived in the fixed note's window clause:
    "the window these spreads sit in (between the charge-move-priority line
    at 148.10 and Build 1's 150.24 attack rung, at their own bulk of Def >=
    96.34 and HP >= 124) holds 58 of the 4096 spreads on this grid", which
    round 9 dropped as a table fact.
    """
    _state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    ab = facts['_builds']
    # Round 10: the sentence takes no preset -- nothing in it varies with
    # the Build criteria setting, so it renders ONCE (DRY rule D1). Pre-fix:
    # line_status_sentence(facts, ab, PRESET_FLAT) and _sp1_gap(facts, ab).
    line = W.line_status_sentence(facts)
    assert line.startswith('Single-stat line: Attack >= 148.10 decides ')
    assert W.printed_value(facts['floor']) == '148.10'
    # The shortfall is the ONE ``stage11_rank1`` computed against the line's
    # full-precision T, which is what expander F's five-row strip prints.
    # Pre-fix this sentence said 6.34 and that strip said 6.35, because the
    # gap was re-derived from the 2-dp value the headline SPEAKS.
    gap = W._sp1_gap(facts)
    assert gap is not None and gap > 0
    assert gap == facts['rank1']['shortfall']
    assert f'SP1 is {B.fmt(gap)} short.' in line
    assert '6.34' not in line
    # the negative case: a page with no line says so in one sentence
    off = dict(facts)
    off['floor'] = None
    assert W.line_status_sentence(off) == W.NO_LINE_STATUS
    assert W._sp1_gap(off) is None


def test_a_wide_region_must_be_big_and_must_hold_the_primary():
    """The round-6 rule on a synthetic lattice: contains EVERY member of the
    primary, >= 2x its size, then the most guaranteed cells, ties to the
    larger.

    Round 5 shipped clause 1 as "holds >= WIDE_MIN_SHARE (90%) of the
    primary's members", which on Shadow Sableye selected a region missing
    two of Build 1's 61 spreads and printed it as "Build 1 wide" (both
    round-6 reviews). ``misses`` below was the 50%-overlap case then and is
    the not-a-superset case now.
    """
    import numpy as np
    n = 40

    def region(lo, hi, wg, combo, constructed=False):
        m = np.zeros(n, bool)
        m[lo:hi] = True
        return {'mask': m, 'size': int(m.sum()), 'wg': float(wg),
                'n_g': int(wg), 'combo': combo, 'sets': [combo],
                'constructed': constructed}

    primary = region(0, 10, 9, 'P')
    too_small = region(0, 19, 8, 'S')          # 1.9x -> rejected
    misses = region(5, 35, 8, 'M')             # holds 5/10 -> rejected
    loser = region(0, 22, 5, 'W')              # 2.2x, holds 10/10
    fewer = region(0, 30, 4, 'F')              # bigger but guarantees fewer
    winner = region(0, 25, 5, 'T')             # ties W on cells, and larger
    partial = region(1, 30, 9, 'X')            # 29 spreads, misses member 0
    box = region(0, 30, 9, 'BULK', constructed=True)
    L = {'inters': [primary, too_small, misses, fewer, winner, loser, box]}
    got = builds_mod.wide_build(L, primary)
    assert got is winner, got['combo']         # cells first, then size
    # one member short is not "wide around" the primary, however good it is
    assert builds_mod.wide_build({'inters': [primary, partial]},
                                 primary) is None
    assert builds_mod.wide_build({'inters': [primary, fewer, loser]},
                                 primary) is loser
    # nothing qualifies -> no wide region at all
    assert builds_mod.wide_build({'inters': [primary, too_small, misses]},
                                 primary) is None
    # the constructed bulk box is never it, even when it would win outright
    assert builds_mod.wide_build({'inters': [primary, box]}, primary) is None


def test_a_wide_region_must_carry_a_rule_the_table_can_print(monkeypatch):
    """Round 6's third clause: a region no two- or three-stat rule fits is
    not a target a reader can aim at, so it is filtered OUT rather than
    ranked. Pre-fix the Shadow Sableye row read "a list of 157 spreads that
    no two- or three-stat rule fits", with three describable supersets
    rejected for guaranteeing two cells fewer.

    Also pins the LAZY fit: the rule is fitted best-candidate-first, so the
    winner is the first describable one in ranking order, not the best
    describable one found by describing them all (same thing, fewer
    describe() calls -- the assertion is on the call count).
    """
    import numpy as np
    n = 40

    def region(lo, hi, wg, combo):
        m = np.zeros(n, bool)
        m[lo:hi] = True
        return {'mask': m, 'size': int(m.sum()), 'wg': float(wg),
                'n_g': int(wg), 'combo': combo, 'sets': [combo]}

    primary = region(0, 10, 9, 'P')
    ruleless = region(0, 30, 8, 'R')           # ranks first, fits no rule
    ruled = region(0, 25, 7, 'T')              # the answer
    tiny = region(0, 24, 6, 'U')               # never reached
    seen = []

    def fake_rule(ctx, mask):
        seen.append(int(mask.sum()))
        return None if int(mask.sum()) == 30 else {'rule': 'Atk >= 1'}

    monkeypatch.setattr(builds_mod, 'region_rule', fake_rule)
    L = {'inters': [primary, ruleless, ruled, tiny]}
    got = builds_mod.wide_build(L, primary, ctx={})
    assert got is ruled, got['combo']
    assert seen == [30, 25], seen              # lazy, in ranking order
    # nothing describable -> no wide region at all, not a rule-less one
    monkeypatch.setattr(builds_mod, 'region_rule', lambda ctx, mask: None)
    assert builds_mod.wide_build(L, primary, ctx={}) is None


def test_a_wide_region_is_ranked_on_the_standouts_it_holds_first():
    """Round 6b: the FIRST clause of the ranking key is how many of the
    preset's outside standouts the region holds, 2 > 1 > 0, and only then
    the guaranteed cells and the size.

    Round 6 ranked inside its filters on cells alone, which on Shadow
    Sableye GL arm 0 picked E,F -- 292 spreads, 49 cells, holding NEITHER
    standout -- over D,H (644 / 43 / both), D (838 / 39 / both) and H
    (1656 / 34 / both). The page then had to end the row's own paragraph on
    "it holds neither standout below, so it is not a route to them", on the
    one region whose stated purpose is "the standouts as ordinary members of
    Build 1 wide". ``cells_only`` below is the pre-fix pick here.

    The filters do NOT move: a region holding both standouts that is too
    small, or that drops a member of the primary, still loses to one that
    holds neither.
    """
    import numpy as np
    n = 40
    s1, s2 = 35, 36                      # the two standouts, outside builds

    def region(idx, wg, combo, constructed=False):
        m = np.zeros(n, bool)
        m[list(idx)] = True
        return {'mask': m, 'size': int(m.sum()), 'wg': float(wg),
                'n_g': int(wg), 'combo': combo, 'sets': [combo],
                'constructed': constructed}

    primary = region(range(10), 9, 'P')
    cells_only = region(range(25), 9, 'C')               # 0 standouts
    one = region(list(range(30)) + [s1], 7, 'O')         # 1 standout
    both = region(list(range(22)) + [s1, s2], 5, 'B')    # 2, fewer cells
    both_big = region(list(range(24)) + [s1, s2], 5, 'G')  # ties B, larger
    both_worse = region(list(range(34)) + [s1, s2], 4, 'W')
    L = {'inters': [primary, cells_only, one, both, both_big, both_worse]}
    outs = [s1, s2]
    assert builds_mod.wide_build(L, primary, None, outs) is both_big
    # ... cells decide among regions holding the SAME number of standouts
    L2 = {'inters': [primary, cells_only, one, both_worse]}
    assert builds_mod.wide_build(L2, primary, None, outs) is both_worse
    L3 = {'inters': [primary, cells_only, one]}
    assert builds_mod.wide_build(L3, primary, None, outs) is one
    # no outside standouts -> exactly the round-6 key, and the pre-fix pick
    assert builds_mod.wide_build(L, primary, None, []) is cells_only
    assert builds_mod.wide_build(L, primary) is cells_only
    # the filters still bind: a 1.9x region and a non-superset holding both
    # standouts both lose to a qualifying region holding neither
    small = region(list(range(17)) + [s1, s2], 9, 'S')     # 19 -> 1.9x
    misses = region(list(range(1, 34)) + [s1, s2], 9, 'M')
    L4 = {'inters': [primary, small, misses, cells_only]}
    assert builds_mod.wide_build(L4, primary, None, outs) is cells_only


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_wide_region_on_shadow_sableye(shadow_sableye):
    """The pin, re-recorded for the round-6b ranking key.

    It picks **D,H** -- 644 spreads, 43 guaranteed cells, fitted by
    ``Atk >= 148.70 and Def + 1.7*HP >= 301.928`` at the table's own
    fidelity -- and it holds BOTH outside standouts.

    Two pre-fix values are recorded here:

    * round 5 picked D,F,G (157 spreads, 51 guaranteed, holding 59 of Build
      1's 61 and fitted by NO two- or three-stat rule), which containment +
      describability as FILTERS removed; and
    * round 6, ranking inside those filters on cells alone, picked **E,F**
      (292 spreads, 49 cells, `_own` 231, 'd(HP) [8 steps]') -- which holds
      NEITHER standout, so this same paragraph read "It holds neither
      standout below, so it is not a route to them" and the collapsed line
      ended "keeps 49 of Build 1's 55 guaranteed matchups." on the one row
      that exists to be a route to them.

    Both outside standouts sit below Build 1's 150.24 attack rung, so only a
    region dropping the rung reaches them; D,H is the best-guaranteeing
    describable superset that does (the others are D at 838/39 and H at
    1656/34, with D,E,H at 369/48 holding 9/6/13 alone).
    """
    _state, all_facts, _path = shadow_sableye
    facts = all_facts[0]
    ab = facts['_builds']
    bl = ab['presets'][builds_mod.PRESET_FLAT]
    wide = bl['wide']
    assert wide is not None
    assert wide['combo'] == 'DH'
    assert (wide['size'], wide['n_guaranteed']) == (644, 43)
    assert (wide['_in_primary'], wide['_primary_size']) == (61, 61)
    assert wide['_own'] == 583
    assert wide['role'] == 'wide'
    # it contains the primary outright, and carries a rule the table prints
    prim = bl['builds'][0]
    assert not (prim['_mask'] & ~wide['_mask']).any()
    assert wide['description'] is not None
    assert wide['description']['rule'] == \
        'atk >= 148.7 and Def + 1.7*HP >= 301.928'
    # every cell it guarantees is one of Build 1's: the counts are retentions
    assert not (wide['_g'] & ~prim['_g']).any()
    # BOTH standouts are ordinary members of it, which is what the region is
    # for and what the round-6b key ranks on (round 6: [False, False])
    assert [t['in_wide'] for t in bl['standouts']] == [True, True]
    assert all(t['in_build'] is None for t in bl['standouts'])
    # it is NOT one of the builds: the objectives, the card set and the
    # standouts' nearest-build search all still see two
    assert len(bl['builds']) == 2
    assert all(b['role'] != 'wide' for b in bl['builds'])
    assert len(W.card_specs(facts, ab)) == 4
    assert all('wide' not in s['title'] for s in W.card_specs(facts, ab))
    # Round 9 item 2: its row sits directly under Build 1's, and what its
    # paragraph said is in the row's own expander. Pre-fix the three
    # paragraphs came from ``build_paragraphs_html`` and this asserted their
    # order and the wide one's opening sentence, "Build 1 wide is the looser
    # target around Build 1, for a reader who cannot hit Build 1 exactly:
    # roughly Atk >= 148.70 and Def + 1.7*HP >= 301.928."
    assert not hasattr(W, 'build_paragraphs_html')
    exp = W.gate_text(W.build_row_expander(ab, bl, bl['wide'], 2,
                                           builds_mod.PRESET_FLAT, facts,
                                           wide=True))
    assert ('The looser target around Build 1, for a reader who cannot hit '
            'Build 1 exactly.' in exp)
    assert 'It holds every one of' in exp
    assert ("It holds every one of Build 1's 61 spreads in 644 of its own, "
            "and keeps 43 of Build 1's 55 guaranteed matchups (none of them "
            "material)" in exp)
    assert 'The 12 it gives up out here: 1v2 Feraligatr (grid 11%)' in exp
    # ...and the TABLE cell says so too. Pre-fix the wide row printed the
    # positive claim "nothing the other builds guarantee", because
    # ``run_preset`` passed ``others=[]`` and ``gives_up`` was empty by
    # construction on every page (2026-09-19 round-10 review, major 1). The column
    # counts what ANY other build on the table guarantees and this one does
    # not -- Build 1's 12 plus Build 2's, 30 here.
    assert bl['wide']['gives_up']
    assert W._gives_up_text(bl['wide']) != 'nothing the other builds guarantee'
    assert W._gives_up_text(bl['wide']).startswith('30: ')
    # its rule, hedged the way every approximate rule is
    cell = W.rule_cell_html(bl['wide'], facts)
    assert W.RULE_APPROX_GLYPH in cell
    assert W._esc('Atk >= 148.70 and Def + 1.7*HP >= 301.928') in cell
    assert '99% of the same spreads (4 extra, 3 missed)' in cell
    table = W.builds_table_html(ab, builds_mod.PRESET_FLAT, facts)
    rows = re.findall(r'<tr data-build="(\d+)">', table)
    assert rows == ['0', '2', '1'], rows      # wide row directly under Build 1
    assert 'wb-swatch wb-wide' in table
    # no most-winning member for the wide row: the plot draws it no triangle
    # and Compare does not offer it (pre-fix: "9/0/14@49 -- 380 of 684")
    wide_row = re.search(r'<tr data-build="2">.*?</tr>', table, re.S).group(0)
    assert '<td>--</td>' in wide_row
    assert 'matchups)</td>' not in wide_row
    # the collapsed line keeps the RETENTION clause and, now that the region
    # reaches them, ends on the standouts (round 6: it ended on "...55
    # guaranteed matchups." and said nothing about them, because "holds
    # neither standout" is a non-finding)
    # Round 10: the collapsed line is the VERDICT and stops at the builds;
    # the wide region's retention clause is the wide ROW, which now also
    # prints what it gives up. Pre-fix the line ended "; Build 1 wide (644
    # spreads) keeps 43 of Build 1's 55 guaranteed matchups and holds both
    # standouts." (2026-09-19 round-10 review).
    line = W.builds_summary(facts, ab, builds_mod.PRESET_FLAT, all_facts)
    assert 'Build 1 wide' not in line
    assert line.count('guarantees') == 2
    assert "keeps 43 of Build 1's 55 guaranteed matchups" in exp
    # and the standouts say where they sit relative to it
    so = W.gate_text(W.notable_html(facts, ab, builds_mod.PRESET_FLAT,
                                      all_facts))
    # Round 8 item 2: both standouts still sit in the wide region and in no
    # build (asserted on the data above), but the block prints one entry for
    # the two of them -- 9/6/13 merged into 7/2/14. Pre-round-8 this sentence
    # appeared twice.
    assert so.count('It is in none of the builds, though Build 1 wide '
                    'holds it.') == 1
    assert 'Build 1 wide does not hold it either' not in so
    # Under the Even preset it is E -- also holding both standouts, on the
    # preset's own scale, and the clause carries both counts like its
    # neighbours. Round 6 picked E,H there (249 spreads), the one page on
    # which the wide region held no spread a build did not; no preset of
    # this page now has ``_own`` = 0, so that branch is pinned on a faked
    # block below rather than on a rendered preset.
    even = ab['presets'][builds_mod.PRESET_EVEN]
    assert even['wide']['combo'] == 'E'
    assert (even['wide']['size'], even['wide']['_own']) == (838, 589)
    assert [t['in_wide'] for t in even['standouts']] == [True, True]
    # Round 10: the wide clause is the wide ROW's, not the collapsed line's.
    # Pre-fix this line ended "; Build 1 wide (838 spreads) keeps 20 of
    # Build 1's 29 guaranteed matchups in 0v0 / 1v1 / 2v2 shields (39 of its
    # 53 overall) and holds both standouts." (2026-09-19 round-10 review).
    eline = W.builds_summary(facts, ab, builds_mod.PRESET_EVEN, all_facts)
    assert 'Build 1 wide' not in eline
    assert "keeps 20 of Build 1's 29 guaranteed matchups" in W.gate_text(
        W.build_row_expander(ab, even, even['wide'], 3,
                             builds_mod.PRESET_EVEN, facts, wide=True))
    # Round 7 retired the "_own == 0" caveat with the trace it was about:
    # the wide region draws a containment RING around every one of its
    # members, so it always has points on the plot. Pinned as an ABSENCE
    # with a positive control. Round 9 moved the prose from
    # ``wide_paragraph`` into the row's own expander.
    faked = dict(wide, _own=0)
    faked_exp = W.gate_text(W.build_row_expander(ab, bl, faked, 2,
                                                 builds_mod.PRESET_FLAT,
                                                 facts, wide=True))
    assert 'adds no points' not in faked_exp
    assert 'The looser target around Build 1' in faked_exp
    # The 1v1 preset is this page's PARTIAL case -- D, holding 9/6/13 and
    # not 7/2/14 -- and it names them by IV, because the block below names
    # them by IV and a reader here for one of them needs to see which
    # (round 6: "It holds 9/6/13 of the standouts below, and not 7/2/14.").
    one = ab['presets'][builds_mod.PRESET_ONE]
    assert one['wide']['combo'] == 'D'
    assert [t['in_wide'] for t in one['standouts']] == [False, True]
    one_exp = W.gate_text(W.build_row_expander(
        ab, one, one['wide'], len(one['builds']), builds_mod.PRESET_ONE,
        facts, wide=True))
    assert 'It holds 9/6/13 below, and not 7/2/14.' in one_exp


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_wide_region_travels_to_the_browser_without_a_column():
    """What the payload hands the panel: the wide region LAST in the builds
    array (so every real build claims its members first) and no UpSet column.
    """
    _state, all_facts = _facts_for(SABLEYE_SHADOW)
    ab = all_facts[0]['_builds']
    pay = builds_mod.builds_payload(ab, 0)
    seen = 0
    for key, block in pay['presets'].items():
        wides = [b for b in block['builds'] if b['role'] == 'wide']
        if not wides:
            continue
        seen += 1
        assert len(wides) == 1
        assert block['builds'][-1]['role'] == 'wide'
        assert wides[0]['col'] is None
        assert all(b['col'] is not None
                   for b in block['builds'][:-1])
        # its membership mask travels, so the panel can draw it
        assert pay['regions'][wides[0]['region']]['mask']
        assert block['wide'] is True
        # no UpSet column is coloured for it -- and its combo is not among
        # the unselected EXTRA candidate columns either: the table directly
        # above the panel names that same region "Build 1 wide", so an
        # anonymous column for it was a second appearance of a named object
        # (2026-09-17 round 6 review; pre-fix 'DFG' was among the flat
        # preset's cols).
        assert all(c['role'] != 'wide' for c in block['cols'])
        assert all(c['combo'] != wides[0]['combo'] for c in block['cols'])
        # the standouts carry their membership
        assert all('inWide' in t for t in block['standouts'])
    assert seen == len(pay['presets'])


def test_the_js_draws_the_wide_region_under_build_1_and_skips_it_elsewhere():
    # Raw source: half these pins are string literals, which ``strip_js``
    # blanks. The positive controls at the foot keep the scan honest.
    js = ENGINE_JS.read_text()
    assert "wide: 'Build 1 wide'" in js
    assert 'function _wbTint(' in js and 'function _wbBuildCol(' in js
    # Round 7: the region is a CONTAINMENT RING -- a larger hollow marker
    # around every one of its members, pushed FIRST so it draws under
    # everything else (pre-fix it was a solid trace carrying only the
    # spreads no build held, which drew "Build 1 wide" beside Build 1
    # instead of around it).
    assert "var WB_RING_SYMBOL = 'circle-open';" in js
    assert 'var WB_RING_SIZE = 9;' in js
    assert 'if (wideIdx >= 0) out.push(ts[wideIdx]);' in js
    assert "if (k3 !== wideIdx && ts[k3].x.length) out.push(ts[k3]);" in js
    # ...and the round-6 legend phrasings are gone with the reason for them:
    # the ring trace holds the whole region, so a bare count IS its size.
    assert "' not already in a build'" not in js
    assert "' already in a build'" not in js
    assert ("ts[k2].name = wrapLegendName(ts[k2].name + ' (' + "
            "ts[k2].x.length + ')'," in js)
    # it is not a build to build, so it is not a Compare candidate
    assert "if (block.builds[b].role === 'wide') continue;" in js
    # and it has no UpSet column
    assert 'if (block.builds[b].col == null) continue;' in js
    # positive control: the functions the pins sit in are still the ones the
    # panel calls
    assert 'function _wbBuildGroups(' in js and 'function wbCompareBuilds(' in js
    assert 'function _wbPlaneShapes(' in js


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_wide_region_on_the_negative_page():
    """Melmetal, recorded rather than asserted-into-existence: arm 0's flat
    preset DOES get one. Under the round-6 rule it is A,G -- 158 spreads,
    22 guaranteed, holding all 55 of Build 1's (pre-fix: B,F, 426 spreads,
    also 22, but selected without the describability filter). Neither
    standout sits outside a build here, so the clause it adds to the
    negative summary is the retention alone.

    Round 6b (the standout clause of the ranking key) leaves this page
    ENTIRELY unchanged, and the reason is asserted below rather than
    asserted away: no preset of any arm here has a standout outside a build,
    so the new first clause is constant and the key reduces to round 6's.
    """
    _state, all_facts = _facts_for(MELMETAL)
    ab = all_facts[0]['_builds']
    bl = ab['presets'][builds_mod.PRESET_FLAT]
    wide = bl['wide']
    assert wide is not None
    assert (wide['combo'], wide['size'], wide['n_guaranteed']) == ('AG', 158, 22)
    assert (wide['_in_primary'], wide['_primary_size']) == (55, 55)
    assert wide['description'] is not None       # never a rule-less region
    for facts in all_facts:
        a = facts.get('_builds')
        for b in (a or {}).get('presets', {}).values():
            assert all(t['in_build'] is not None for t in b['standouts'])
    line = W.builds_summary(all_facts[0], ab, builds_mod.PRESET_FLAT,
                            all_facts)
    # pre-fix: '; Build 1 wide (426 spreads) guarantees 22.' -- a bare count
    # after a clause reading "guarantees 26 others", which read as 22 MORE
    assert line.endswith("; Build 1 wide (158 spreads) keeps 22 of Build 1's "
                         '29 guaranteed matchups.')
    # every arm that has builds either gets one or says nothing about it
    for facts in all_facts:
        a = facts.get('_builds')
        if not a or not a.get('presets'):
            continue
        for k, b in a['presets'].items():
            if not b['builds']:
                assert b['wide'] is None
                continue
            if b['wide'] is None:
                assert 'Build 1 wide' not in W.builds_summary(
                    facts, a, k, all_facts)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_wide_region_on_plain_sableye():
    """The third preview page's pin, and the second page round 6b does not
    move: plain Sableye's arm 0 flat preset picks C,D (703 spreads, 33
    guaranteed) under both the round-6 key and the round-6b one, because
    every standout here sits inside a build.
    """
    _state, all_facts = _facts_for(SABLEYE_PLAIN)
    facts = all_facts[0]
    ab = facts['_builds']
    bl = ab['presets'][builds_mod.PRESET_FLAT]
    wide = bl['wide']
    assert wide is not None
    assert (wide['combo'], wide['size'], wide['n_guaranteed']) == ('CD', 703,
                                                                  33)
    assert (wide['_in_primary'], wide['_primary_size']) == (318, 318)
    assert wide['description'] is not None
    # Round 10: the wide clause is the wide ROW's, not the collapsed line's.
    # Pre-fix the line ended "; Build 1 wide (703 spreads) keeps 33 of Build
    # 1's 43 guaranteed matchups." (2026-09-19 round-10 review).
    line = W.builds_summary(facts, ab, builds_mod.PRESET_FLAT, all_facts)
    assert 'Build 1 wide' not in line
    assert "keeps 33 of Build 1's 43 guaranteed matchups" in W.gate_text(
        W.build_row_expander(ab, bl, wide, 2, builds_mod.PRESET_FLAT, facts,
                             wide=True))
    # the reason it is unchanged, asserted rather than assumed
    for f in all_facts:
        a = f.get('_builds')
        for b in (a or {}).get('presets', {}).values():
            assert all(t['in_build'] is not None for t in b['standouts'])


# ---------------------------------------------------------------------------
# 7. Round 7 (2026-09-17): the containment ring, the section's own
#    all-scenarios grid, and the named standout on the collapsed line
# ---------------------------------------------------------------------------

_RING_HARNESS = r"""
// Node harness: the wide region's containment ring, and the mini variant.
// Same slice and same globals as _BUILDS_HARNESS above.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
// The score-key grammar lives ABOVE _wbRoot, and wbWins goes through it so
// the best-buddy level suffix comes along. Sliced out of the real source
// rather than re-typed here: a harness copy of the key grammar is exactly
// the drift tests/test_js_score_key_parity.py exists to prevent.
const keyStart = src.indexOf('function getScoreKeyAt(');
const keyEnd = src.indexOf('// ---- Composite mode grammar');
if (keyStart < 0 || keyEnd < 0) { console.error('KEY MARKERS'); process.exit(2); }
const keyBlock = src.slice(keyStart, keyEnd);
const SCORE_KEY_L51 = '@51';
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
const state = { ownedByIv: null, compareCandidates: [] };
const window = {};
const document = { getElementById: () => null, addEventListener: () => {},
                   querySelector: () => null, querySelectorAll: () => [] };
const location = { hash: '' };
const history = { replaceState: () => {} };
const Plotly = { react: () => {}, newPlot: () => {}, restyle: () => {},
                 Plots: { resize: () => {} } };
const getComputedStyle = () => ({ getPropertyValue: () => '' });

let out;
// The export list is TOLERANT so this one file runs on both sides of the
// fix: _wbBuildMarks and _wbMiniShrink do not exist before it, and a bare
// {_wbMiniShrink} in the eval is a ReferenceError rather than a reading.
eval(keyBlock + block + '\nout = {_wbBuildGroups, wbPresetBlock, wbLevelArrays, ' +
     'wbWins, _wbBuildOf,' +
     ' _wbBuildMarks: (typeof _wbBuildMarks === "function")' +
     '   ? _wbBuildMarks : null,' +
     ' _wbMiniShrink: (typeof _wbMiniShrink === "function")' +
     '   ? _wbMiniShrink : null};');

// Build 1 = spreads 0..1 ('Aw=='), Build 1 wide = spreads 0..3 ('Dw==',
// 0b00001111): it CONTAINS Build 1 and reaches two spreads no build holds.
const bp = {
  mi: 0, mode: 'pvpoke', default: 'flat', presetKeys: ['flat'],
  nDecision: 3, nMaterial: 1, nOpp: 2, topN: 25, colors: ['#a','#b','#c'],
  scenLabels: ['0v0', '1v1'],
  cells: [[0, 5, 1], [1, 9, 0], [0, 12, 0]],
  regions: [{size: 2, nG: 2, nGmat: 1, bits: 'BQ==', mask: 'Aw=='},
            {size: 4, nG: 1, nGmat: 0, bits: 'Ag==', mask: 'Dw=='}],
  rank1: {iv: '0/15/15@50', idx: 0, wins: 1},
  gridBest: {iv: '5/10/10@50', idx: 5, wins: 4},
  bestScore: {iv: '4/11/11@50', idx: 4, avgStr: '512.0'},
  presets: {
    flat: {label: 'All shields, equal', tag: 'all shields, equal',
           weights: [1, 1], scens: ['0v0', '1v1'], summary: 'S-flat',
           builds: [{role: 'primary', combo: 'A', col: 0, region: 0, size: 2,
                     desc: 'd0', nG: 2, nGw: 2, nGmat: 1,
                     mostWinning: {iv: '1/14/14@50', idx: 1, wins: 2, den: 4}},
                    {role: 'wide', combo: 'AB', col: null, region: 1, size: 4,
                     desc: 'wide-rule', nG: 1, nGw: 1, nGmat: 0}],
           cols: [], lattice: []}
  }
};
const pay = {mi: 0, mode: 'pvpoke', hasFloor: false, views: [], bp: bp,
             rank1: {iv: [0,15,15], level: 50},
             gridBest: {iv: [5,10,10], level: 50},
             examples: [], rungs: []};
const L = out.wbLevelArrays();
const fail = [];
const block0 = out.wbPresetBlock(pay);
const wins = out.wbWins(0, 'pvpoke', null);
const g = out._wbBuildGroups(pay, L, wins, {below: '#z', line: '#y'}, 4,
                             {querySelector: () => null}, null);
const t = g.traces;

// (a) the ring is trace 0 -- under every other trace
if (!/^Build 1 wide/.test(t[0].name))
  fail.push('the ring is not the first trace: ' + t.map(x => x.name));
if (t[0].marker.symbol !== 'circle-open')
  fail.push('the wide trace is not a ring: ' + t[0].marker.symbol);
if (!(t[0].marker.size > 4))
  fail.push('the ring is not larger than a build dot: ' + t[0].marker.size);

// (b) it rings EVERY member of the region, including the two Build 1 holds
if (t[0].x.length !== 4)
  fail.push('the ring does not hold all 4 members: ' + t[0].x.length);
if (t[0].name.indexOf('(4)') < 0)
  fail.push('the legend count is not the region size: ' + t[0].name);
if (/not already in a build|already in a build/.test(t[0].name))
  fail.push('the round-6 legend phrasing survived: ' + t[0].name);

// (c) Build 1's two members are still solid dots of their own, and the two
// extras fall to the muted centre trace
const byName = {};
t.forEach(x => { byName[x.name.replace(/ \((\d+)\)$/, '')] = x; });
if (!byName['In no build'] || byName['In no build'].x.length !== 4)
  fail.push('the muted trace should hold 2 extras + 2 outsiders: ' +
            JSON.stringify(Object.keys(byName)));
const prim = t.filter(x => /^Build 1 \(primary\)/.test(x.name))[0];
if (!prim || prim.x.length !== 2 || prim.marker.symbol !== 'circle')
  fail.push('Build 1 lost its solid dots');

// (d) hovering a ring names the region
if (t[0].text[0].indexOf('Build 1 wide') < 0)
  fail.push('the ring hover does not name the region: ' + t[0].text[0]);

// (e) the minis: nine (here two) per-scenario trace sets with the same
// shape, and every marker shrunk for a 200px panel. Guarded, so an engine
// without the mini helpers still reports (a)-(d) instead of throwing.
if (!out._wbBuildMarks || !out._wbMiniShrink) {
  fail.push('this engine has no mini helpers (pre-fix build)');
} else {
const marks = out._wbBuildMarks(pay, block0, L, out.wbWins(0, 'pvpoke', 0),
                                {below:'#z', line:'#y', mark1:'#m', mark2:'#n'},
                                2, {idx: 0, label: '0v0'},
                                {querySelector: () => null}, true);
if (!marks.length) fail.push('the minis mark no spreads');
marks.forEach(m => {
  if (m.mode !== 'markers') fail.push('a mini mark kept its text label');
});
const mini = out._wbBuildGroups(pay, L, out.wbWins(0, 'pvpoke', 0),
                                {below: '#z', line: '#y'}, 2,
                                {querySelector: () => null},
                                {idx: 0, label: '0v0'}).traces.concat(marks);
const before = mini.map(x => x.marker.size);
out._wbMiniShrink(mini);
mini.forEach((x, i) => {
  if (!(x.marker.size < before[i])) fail.push('mini marker not shrunk at ' + i);
  if (x.marker.size < 2) fail.push('mini marker shrunk below 2px at ' + i);
});
if (!/^Build 1 wide/.test(mini[0].name))
  fail.push('the mini ring is not the first trace either');
}

if (fail.length) { console.error(fail.join('\n')); process.exit(1); }
console.log('OK');
"""


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_the_wide_region_rings_every_member_and_draws_underneath(tmp_path):
    """Run the ring code on a synthetic grid whose wide region CONTAINS
    Build 1 -- the shape the round-6 trace could not draw.

    Pre-fix values, measured by running THIS file against 0afbee9's
    engine (`git show 0afbee9:scripts/deep_dive_engine.js`); the eval
    export list is tolerant of the two helpers that engine lacks, so
    the same harness reproduces both sides:

        [{name: 'In no build (2)',                        n: 2, circle, 3},
         {name: 'Build 1 wide: wide-rule
                 (2 of 4 not already in a build)',        n: 2, circle, 4},
         {name: 'Build 1 (primary): d0 (2)',              n: 2, circle, 4}]

    ...i.e. the wide region was a SOLID trace of the 2 spreads no build
    held, drawn ABOVE the muted remainder, with a legend count that had to
    explain which count it was. Post-fix:

        [{name: 'Build 1 wide: wide-rule (4)',   n: 4, circle-open, 9},
         {name: 'In no build (4)',               n: 4, circle,      3},
         {name: 'Build 1 (primary): d0 (2)',     n: 2, circle,      4}]
    """
    runner = tmp_path / 'wb_ring_check.js'
    runner.write_text(_RING_HARNESS)
    proc = subprocess.run(['node', str(runner), str(ENGINE_JS)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert proc.stdout.strip() == 'OK'


def test_the_section_offers_the_one_all_scenarios_grid():
    """The merged grid's wiring, on both sides of the Py<->JS boundary.

    Round 9 item 4 turned two grids into one: this section's checkbox-gated
    build-coloured grid and the Matchup clusters section's cluster-coloured
    one. The grid is the figure's third TAB now, with a Y toggle (wins in
    that shield state / avg score) and a colour toggle (build / matchup
    cluster) carrying the difference the two grids used to carry.

    Pre-fix pins that are gone with their subjects:
    ``window.wbToggleAllScen = wbToggleAllScen;``,
    ``function _wbAllScen(root, force)``,
    ``var offer = !!(pblock && view === 'builds');``,
    ``_wbAllScen(root, false);`` and ``W.allscen_html()``.
    """
    js = ENGINE_JS.read_text()
    code = strip_js(js)
    assert 'function wbToggleAllScen(' not in js
    assert 'function _wbAllScen(root, box, force)' in js
    # one mini per baked scenario, y = wins in THAT scenario out of the pool
    assert 'for (var si = 0; si < DATA.nScenarios; si++)' in code
    assert "var wins = wbWins(pay.mi, pay.mode, si);" in js
    assert 'var chrome = plotChrome(), den = DATA.nOpponents;' in js
    # the y axis says what it is out of -- and now which measure it is
    assert "var y = wins, yTitle = 'Wins (of ' + den + ')';" in js
    assert "yTitle = 'Avg battle score';" in js
    # the two toggles, and the cluster colouring read from the clusters
    # payload rather than a second clustering
    assert "_wbAllScenMode(box, 'wb-allscen-y', 'wins')" in js
    assert "_wbAllScenMode(box, 'wb-allscen-color', 'build')" in js
    assert 'function _wbClusterMiniTraces(' in js
    # shown on the grid TAB only
    assert "var on = !!(pblock && _wbBoxView(box) === 'allscen');" in js
    # and re-drawn by every box render (a Build criteria change included)
    assert '_wbAllScen(root, box, false);' in js
    # nine scattergl panels are nine WebGL contexts: they are PURGED, not
    # just dropped, or a tab / Build-criteria change leaks a set and the
    # browser starts blanking plots elsewhere on the page
    assert 'function _wbClearMinis(grid) {' in js
    assert 'Plotly.purge(kids[i])' in js
    # a floor, not an equality: a further teardown site (a purge on unload)
    # improves the code
    assert js.count('_wbClearMinis(grid);') >= 2
    assert "grid.innerHTML = '';" in js

    py = (SCRIPTS_DIR / 'deep_dive_which_build.py').read_text()
    assert not hasattr(W, 'allscen_html')
    html = W.plotbox_html([('builds', 'Builds on the grid'),
                           ('allscen', 'Per shield scenario')],
                          ['0v0', '1v1'], allscen=True)
    assert 'class="wb-allscen-grid" hidden' in html
    assert 'class="wb-allscen-y"' in html and 'class="wb-allscen-color"' in html
    assert 'data-view="allscen"' in html
    # the caption says what it shows AND that the colours follow the knob
    cap = W.ALLSCEN_CAPTION
    assert 'shield state' in cap
    assert 'Build criteria' in cap
    # the [hidden] override, without which a bare attribute loses to the
    # display rule and the grid stays laid out on the other two tabs.
    # (Round 9 retired `.wb-allscen`, the checkbox's own label; the two
    # toggles that replaced it carry the same override.)
    assert '.wb-allscen-grid[hidden] { display: none; }' in py
    assert '.wb-allscen-ctl[hidden] { display: none; }' in py


def test_a_standout_the_collapsed_line_holds_is_named_not_counted():
    """Item 4. Pre-fix the clause read "and holds 1 of the standouts" -- the
    count, with the reader left to guess WHICH of two different offers.
    """
    assert W.standout_short_phrase(
        {'iv': '9/6/13@50', 'kind': 'score'}) == \
        '9/6/13 (the highest avg battle score)'
    assert W.standout_short_phrase(
        {'iv': '7/2/14@49.5', 'kind': 'wins'}) == \
        '7/2/14 (the most matchups won)'
    # the parenthetical is the page's ONE canonical short name, not a second
    # spelling composed here
    assert W.CARD_SHORT['score'] == 'Highest avg battle score'

    # the clause itself, on a synthetic block: one standout outside every
    # build, held by the wide region
    bl = {
        'builds': [{'role': 'primary', 'n_guaranteed': 55,
                    'n_guaranteed_weighted': 29, 'size': 61}],
        'wide': {'role': 'wide', 'size': 644, 'n_guaranteed': 43,
                 'n_guaranteed_weighted': 20, 'n_guaranteed_material': 0,
                 '_primary_size': 61},
        'standouts': [
            {'iv': '9/6/13@50', 'kind': 'score', 'in_build': None,
             'in_wide': True},
            {'iv': '7/2/14@49.5', 'kind': 'wins', 'in_build': None,
             'in_wide': False},
        ],
        'weights': [1] * 9,
    }
    ab = {'ctx': {'scen_labels': ['0v0', '0v1', '0v2', '1v0', '1v1', '1v2',
                                  '2v0', '2v1', '2v2']}}
    clause = W._wide_clause(ab, bl)
    assert clause.endswith(' and holds 9/6/13 (the highest avg battle score)')
    assert 'of the standouts' not in clause


# ---------------------------------------------------------------------------
# Round 7b (2026-09-17): the two reviews of the round-7 render -- the
# captions still described the retired round-6 trace, the minis' caption
# overclaimed, a Best Buddy tick threw the moved section away, and the
# clusters grid never released its WebGL contexts.
# ---------------------------------------------------------------------------


def test_the_builds_caption_describes_the_ring_and_not_the_retired_trace():
    """The captions that INTRODUCE the ring described round 6's trace.

    Pre-fix values (round 7, commit c11431e):

        'carrying only the spreads no build holds' in BUILDS_CAPTION -> True
        'hollow ring'                              in BUILDS_CAPTION -> False
        'hollow ring'                              in STATS_CAPTION  -> False

    So the first explanation a reader got of the ring said the opposite of
    what the plot drew: the legend's "(644)" (the region's own size) and the
    caption's "only the spreads no build holds" cannot both be true. On the
    stats plane the ring is also the one marker whose size does NOT encode
    attack, which that caption never mentioned.
    """
    # absence pin for the retired phrasing...
    assert 'only the spreads no build holds' not in W.BUILDS_CAPTION
    # ...with the replacement as the positive control that gives it meaning.
    # Round 10 shortened the builds caption to two sentences, so the three
    # detail phrases moved out of it (pre-fix: 'around every spread it
    # holds', 'faint grey centre' and 'lighter tint' were all here); the
    # ring is still named, and the STATS caption keeps the long form.
    assert 'hollow ring' in W.BUILDS_CAPTION
    assert 'faint grey centre' not in W.BUILDS_CAPTION
    # the stats view draws the ring too, at one fixed size
    assert 'hollow ring' in W.STATS_CAPTION
    assert 'does not follow attack' in W.STATS_CAPTION


def test_the_mini_grid_caption_does_not_promise_bands_in_every_state():
    """The grid's caption must not overclaim what one shield state shows.

    Round 7 read "It is where each build's members band above the rest,
    shield state by shield state" -- but a build is chosen on the counted
    scenarios TAKEN TOGETHER, and in a single state its members need not
    band above the rest at all. Round 9's merged caption keeps the caveat
    and drops "did not count", which belonged to a grid that was offered on
    the builds view only.

    Pre-fix values: 'band above the rest' -> True; 'taken together' -> True;
    'did not count' -> True.
    """
    cap = W.ALLSCEN_CAPTION
    assert 'band above the rest' not in cap
    assert 'taken together' in cap
    assert 'can look ordinary in a single' in cap
    # positive controls: the caption still says what the axes are, what the
    # two toggles do and that the colours follow the knob
    assert 'stat-product rank' in cap
    assert 'avg battle score' in cap
    assert 'matchup clusters' in cap
    assert 'Build criteria' in cap


def test_a_ringed_spread_says_both_what_holds_it_and_what_does_not():
    """One point, two labels -- in the order that cannot mislead.

    Pre-fix a spread the wide rule reaches that NO build holds sat in the
    muted "In no build (3921)" legend trace while its hover read
    "Build 1 wide: guarantees 43 ..." with no mention of being in no build;
    a Build 1 member's hover said nothing about sitting INSIDE Build 1 wide,
    so where dots crowd and hide the rings the containment was invisible on
    hover. The b < 0 fallback also still pointed "below" at a table that
    moved above the plot in round 7.

    Pre-fix source values: 'in none of the builds below' present (1);
    '_wbSideWithWide' absent (0).
    """
    js = ENGINE_JS.read_text()
    # the fallback no longer points at a table that is now above the plot
    assert 'in none of the builds below' not in js
    assert "if (b < 0) return 'in none of the builds';" in js
    # the two-label builder, and the three cases it distinguishes
    assert 'function _wbSideWithWide(' in js
    assert "return _wbBuildSide(pay, block, -1, scen) + '; inside ' + w;" in js
    assert ("return _wbBuildSide(pay, block, b, scen) + '; inside ' + wname;"
            in js)
    code = strip_js(js)
    # ...called with the ringed flag from the per-point pass, and WITHOUT it
    # for the ring's own hover (which names the region, as it should)
    assert 'sideFor(b, ringed)' in code
    assert 'sideFor(wideIdx, false)' in code


def test_a_best_buddy_toggle_keeps_the_moved_section_open():
    """The swap restored stored markup, which is markup with no `open`.

    Round 7 moved the Matchup clusters section's own <details> INSIDE the
    best-buddy host, so `host.innerHTML = stored` collapsed it. Measured in
    headless Chrome on the round-7 preview (pre-fix): open the section
    {detOpen: true, minis: 9}; tick #dd-bb-toggle {detOpen: FALSE, minis: 0};
    untick {detOpen: FALSE, minis: 0}. A reader who opened the section and
    toggled Best Buddy lost the figure and their scroll position -- and the
    `!grid.children.length` branch added to refreshAllScenarios for exactly
    that case was dead for the grid.

    Pre-fix source value: '_bbOpenIn' absent (0 occurrences).
    """
    js = ENGINE_JS.read_text()
    assert 'function _bbOpenIn(host) {' in js
    # the open ids are captured BEFORE the swap and re-applied after it
    assert 'var wasOpen = _bbOpenIn(host);' in js
    assert "host.innerHTML = _bbHostHTML[hid][mode];" in js
    assert (js.index('var wasOpen = _bbOpenIn(host);')
            < js.index('host.innerHTML = _bbHostHTML[hid][mode];'))
    # re-opening dispatches the toggle the lazy-draw path listens for, so
    # the nine minis come back rather than waiting for a second click
    assert "new Event('toggle'" in js
    assert 'function _bbReopen(ids) {' in js


def test_the_one_grid_purges_its_contexts_when_it_leaves_the_screen():
    """Leaving the grid tab must release the nine WebGL contexts.

    Round 7's clusters grid had an off-path that only set
    ``grid.style.display = 'none'``, so nine scattergl divs stayed live for
    the life of the page. Round 9 deleted that grid; the ONE grid's
    off-path is ``_wbAllScen``'s early return, which purges.

    Pre-fix source value: ``_wbClearMinis(grid);`` call count 3, one of them
    inside ``toggleAllScenarios``.
    """
    js = ENGINE_JS.read_text()
    assert 'function toggleAllScenarios(' not in js
    assert js.count('_wbClearMinis(grid);') >= 2
    off = js.split('function _wbAllScen(root, box, force)', 1)[1]
    off = off.split('\n}', 1)[0]
    assert 'if (!on) { _wbClearMinis(grid); _wbAllScenKey = null; return; }' in off
    # the redraw path purges before it rebuilds, so a tab round-trip does not
    # stack two sets of contexts
    assert off.index('_wbClearMinis(grid);') < off.index('_wbPlaneMode =')


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_rendered_section_carries_the_one_scenario_grid(shadow_sableye):
    """The merged grid, pinned on a rendered section rather than its emitter.

    Pre-fix the markup was a checkbox (``class="wb-allscen-chk"``), the grid
    and a caption of its own, all three hidden, emitted between the panel
    and the fixed note by ``W.allscen_html()``. Round 9 makes it the
    figure's third TAB: no checkbox, no caption of its own (the box's one
    caption is the grid's while the grid is on screen), and two toggles.
    """
    _state, all_facts, _path = shadow_sableye
    h = W.section_html(all_facts, 0)
    assert 'wb-allscen-chk' not in h
    assert 'class="wb-allscen-caption"' not in h
    tab = h.index('data-view="allscen"')
    ctl = h.index('class="wb-allscen-ctl"')
    panel = h.index('class="wb-panel"')
    grid = h.index('class="wb-allscen-grid"')
    cap = h.index('class="wb-caption"')
    # tabs, then the controls, then the panel, then the grid, then the one
    # caption -- which is under the figure it describes either way
    assert tab < ctl < panel < grid < cap
    assert cap < h.index('class="wb-fixed"')
    # the grid and the toggles ship hidden; the JS owns when they show
    assert '<div class="wb-allscen-grid" hidden>' in h
    assert '<div class="wb-allscen-ctl">' in h


# ---------------------------------------------------------------------------
# Round 8 item 4: one plot per row
# ---------------------------------------------------------------------------

def test_the_upset_and_the_scatter_never_share_a_row():
    """Michael, 2026-09-17: at some widths the UpSet panel and the section
    scatter split a flex row and neither was readable.

    Pre-fix the CSS carried ``.wb-plotrow { display: flex; flex-wrap: wrap;
    gap: 10px; }`` with ``.wb-upset { flex: 1 1 320px; min-width: 300px; }``
    and ``.wb-plotrow .wb-panel { flex: 2 1 420px; min-width: 320px; }``, so
    between roughly 700px and 1100px of section width the two sat side by
    side at 320px each. There is no viewport at which they share a row now.

    Pinned on the CSS the section ships and on the DOM order it emits, not on
    a screenshot: the failure was a layout rule, and the rule is the artifact.
    """
    css = W.CSS
    # Round 9 item 4 moved the set panel out of the figure entirely (it is
    # in the "Why these regions" expander), so the wrapper the two used to
    # share is gone with the sharing. Pre-fix the two pinned rules were
    # ``#dd-which-build .wb-plotrow { display: block; }`` and
    # ``#dd-which-build .wb-plotrow .wb-panel { display: block; width:
    # 100%; ...}``; what the rule protects is that NEITHER is ever a flex
    # child of anything.
    assert '.wb-plotrow' not in css
    row = [ln for ln in css.splitlines()
           if ln.startswith('#dd-which-build .wb-upset')
           or ln.startswith('#dd-which-build .wb-panel')]
    assert row, 'the plot-block rules vanished'
    joined = '\n'.join(row)
    assert 'flex' not in joined, joined
    # Both blocks claim the full width of the section.
    assert '#dd-which-build .wb-upset { display: block; width: 100%;' in css
    assert '#dd-which-build .wb-panel { display: block; width: 100%;' in css


@pytest.mark.local_artifacts
def test_the_upset_block_precedes_the_scatter_in_the_rendered_section(
        shadow_sableye):
    """Round 8 item 4, on the artifact: the UpSet div comes FIRST, its
    caption directly under it, and the scatter panel below both -- so the
    stacking order the CSS enforces is also the reading order.

    Pre-fix the emitted markup was
    ``<div class="wb-plotrow"><div class="wb-upset"></div>
    <div class="wb-panel"></div></div>`` with the UpSet's caption AFTER the
    pair, i.e. under the scatter it does not describe.
    """
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    i_up = html.index('class="wb-upset"')
    i_cap = html.index('class="wb-upset-caption"')
    i_panel = html.index('class="wb-panel"')
    # Round 9 item 4 moved the set panel OUT of the figure and into the
    # "Why these regions" expander, where it answers the question it is
    # about; its caption is still directly under it. Pre-fix i_up < i_cap <
    # i_panel with all three in the one plot box.
    assert i_up < i_cap
    assert i_panel < i_up, 'the set panel is no longer above the figure'
    regions = html.index('class="wb-regions-exp"')
    assert regions < i_up < html.index(W._esc(W.EXPANDER_EVIDENCE))
    # ...and it is named and defined where it appears
    assert 'UpSet plot' in html
    assert 'Lex et al. 2014' in html


def test_the_section_plot_legend_is_below_the_plot_and_wraps():
    """Round 8 item 4, the JS half.

    Pre-fix ``wbRenderBox`` (then ``wbRenderRoot``) sent a legend of more than six keys VERTICAL on
    the right (``orientation: 'v', x: 1.02``), which spent a third of a
    now-full-width panel on legend text. The legend is horizontal and under
    the plot at every trace count; wrapping costs height, so the panel grows
    by one row per wrapped legend line rather than squeezing the plot.
    """
    src = _engine()
    body = src[src.index('function wbRenderBox('):
               src.index('function wbSelectView(')]
    assert "orientation: 'v'" not in body, 'the vertical branch is still there'
    assert 'x: 1.02' not in body
    # strip_js blanks string literals (quotes included), so the orientation
    # and the anchors read as runs of spaces here.
    assert re.search(r'legend: \{ orientation:\s+, y: legY, yanchor:\s+,',
                     body), 'the legend is not anchored below the plot'
    raw = ENGINE_JS.read_text()
    raw_body = raw[raw.index('function wbRenderBox('):
                   raw.index('function wbSelectView(')]
    assert ("legend: { orientation: 'h', y: legY, yanchor: 'top', x: 0,"
            in raw_body)
    # the geometry is computed from named pixel constants, not guessed
    for name in ('WB_PANEL_H', 'WB_PLOT_T', 'WB_LEG_PER_ROW', 'WB_LEG_ROW_H',
                 'WB_LEG_GAP', 'WB_LEG_PAD', 'WB_PLOT_AREA'):
        assert f'var {name} = ' in src, name
    # ...and the renderer's own first guess is built from them. WB_PANEL_H is
    # no longer among them: since the round-8 review the renderer sizes from
    # the PLOT AREA (WB_PANEL_H defines that constant and nothing else), so
    # the panel's height follows the legend instead of the legend being
    # squeezed into a 400px panel.
    for name in ('WB_PLOT_T', 'WB_LEG_PER_ROW', 'WB_LEG_ROW_H',
                 'WB_PLOT_AREA'):
        assert name in body, name
    assert 'WB_PLOT_AREA = WB_PANEL_H - WB_PLOT_T -' in src
    assert 'panel.style.height = panelH' in body
    assert 'margin: { t: WB_PLOT_T, b: legB, l: 56, r: 8 }' in body
    # the guess is corrected by a measurement before the reader sees it
    assert '_wbFitLegend(panel, layout);' in body
    i_react = body.index('Plotly.react(panel, traces, layout,')
    assert body.index('_wbFitLegend(panel, layout);') > i_react, (
        'the legend is measured before it is drawn')


_LEGEND_FIT_HARNESS = r"""// Node harness: the panel's legend geometry, executed.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const start = src.indexOf('var WB_PANEL_H = ');
const end = src.indexOf("// One family's name");
if (start < 0 || end < 0 || end <= start) { console.error('MARKERS'); process.exit(2); }
const block = src.slice(start, end);

// A panel whose legend reports whatever CONTENT height the case asks for,
// with the drawn rect reporting Plotly's own cap (half the graph height) so
// the measurement has to prefer the uncapped reading; plus a Plotly that
// records how each redraw was asked for.
let legH = 0, graphH = 0, relayouts = [], reacts = [];
const legendG = { querySelector: (sel) => (sel === 'rect.bg'
  ? { getAttribute: () => String(Math.min(legH, 0.5 * graphH)) } : null) };
const panel = { style: {}, _fullLayout: { legend: {} },
  querySelector: (sel) => (sel === 'g.legend' ? legendG : null) };
const Plotly = {
  react: (p, t, l, c) => { reacts.push(l.margin.b); },
  relayout: (p, u) => {
    // what the real one does, and the reason this is not a react: it picks
    // the container's new height up
    graphH = parseFloat(p.style.height);
    relayouts.push({ b: u['margin.b'], autosize: u.autosize });
  }
};

let out;
eval(block + '\nout = {WB_PANEL_H, WB_PLOT_T, WB_PLOT_AREA, WB_LEG_GAP,' +
     ' WB_LEG_PAD, WB_LEG_ROW_H, WB_LEG_PER_ROW, _wbLegBottom,' +
     ' _wbLegendHeight, _wbFitLegend};');

function run(measured, nTraces) {
  legH = measured; relayouts = []; reacts = [];
  // exactly the first guess wbRenderBox makes, from the trace COUNT
  const rows = Math.max(1, Math.ceil(nTraces / out.WB_LEG_PER_ROW));
  const guess = out._wbLegBottom(rows * out.WB_LEG_ROW_H);
  const layout = { margin: { t: out.WB_PLOT_T, b: guess, l: 56, r: 8 },
                   legend: { y: -out.WB_LEG_GAP / out.WB_PLOT_AREA } };
  panel.style.height = (out.WB_PLOT_T + out.WB_PLOT_AREA + guess) + 'px';
  graphH = parseFloat(panel.style.height);
  panel._fullLayout.legend._height = measured;
  const passes = out._wbFitLegend(panel, layout);
  const h = parseFloat(panel.style.height);
  return { guess: guess, marginB: layout.margin.b, panelH: h,
           plotArea: h - out.WB_PLOT_T - layout.margin.b,
           legendBottom: out.WB_LEG_GAP + measured,
           redraws: relayouts.length, reacts: reacts.length,
           autosize: relayouts.every(r => r.autosize === true),
           passes: passes, legY: layout.legend.y };
}

// ...and that the CAPPED reading is not the one used: a legend whose content
// is 342px inside a 608px graph draws a 303px rect, and sizing from 303
// converges on the cap instead of on the content.
legH = 342; graphH = 608;
panel._fullLayout.legend._height = 342;
const measured = out._wbLegendHeight(panel);
const capped = parseFloat(legendG.querySelector('rect.bg').getAttribute('height'));

console.log(JSON.stringify({
  area: out.WB_PLOT_AREA,
  measured: measured, capped: capped,
  // the 900px viewport of the round-8 review: 11 keys, 342px of legend
  narrow: run(342, 11),
  // the same 11 keys where the count formula happens to be right
  exact: run(out.WB_LEG_ROW_H * 4, 11),
  // one key, one row: the geometry must not move at all
  single: run(out.WB_LEG_ROW_H, 1)
}));
"""


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_the_panel_height_is_measured_from_the_legend_not_counted(tmp_path):
    """Round 8 review, the major finding -- executed, not source-pinned.

    Pre-fix ``wbRenderBox`` (then ``wbRenderRoot``) reserved the legend's room from the TRACE
    COUNT alone: ``legRows = ceil(traces.length / 3)`` and 18px a row. That
    assumes three keys fit across the panel and that no key wraps. At a
    900px viewport the panel is 604px wide, Plotly fits ONE key per row and
    ``wrapLegendName(..., 34)`` gives the family and build keys two or three
    lines each, so an 11-key legend measured 335px against the 72px the
    formula reserved (bottom margin 122, panel 454). The pre-fix numbers,
    measured in headless Chrome on the shipped shadow preview: legend box
    top 220 / bottom 554 inside a ``main-svg`` of height 454 with
    ``overflow: hidden``, so six keys -- both standout keys, both
    most-winning-member keys and the SP1 key -- were cut off AND unhittable
    (``document.elementFromPoint`` at each key's centre returned the caption
    paragraph below the figure, so legend-hover isolation was dead for
    exactly the marks a reader wants isolated). The plot was squeezed too,
    261px at 1400 and 186px at 900 against the 324px the layout intends,
    because Plotly's own automargin pushed into a panel whose CSS height
    was pinned at 454.

    Post-fix the count is only the first guess: the legend is measured after
    the draw and the panel is redrawn to hold it, with the PLOT AREA as the
    invariant.
    """
    runner = tmp_path / 'wb_legend_fit.js'
    runner.write_text(_LEGEND_FIT_HARNESS)
    proc = subprocess.run(['node', str(runner), str(ENGINE_JS)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    got = json.loads(proc.stdout)
    assert got['area'] == 324, got['area']
    # the measurement is the UNCAPPED content height, not the drawn rect:
    # Plotly caps a horizontal legend at half the graph height and scrolls
    # the rest, so sizing from the rect converges on the cap (303 inside a
    # 608px graph) rather than on the 342 the keys need
    assert got['measured'] == 342, got
    assert got['capped'] == 304, got

    narrow = got['narrow']
    # the pre-fix reservation, still what the first guess computes
    assert narrow['guess'] == 122, narrow
    # ...and the correction, from the measurement
    assert narrow['marginB'] == 44 + 6 + 342
    assert narrow['panelH'] == 8 + 324 + 392
    assert narrow['redraws'] == 1, 'one measurement, one correction'
    assert narrow['passes'] == 1
    # THE assertion the round-7b probe was missing: the legend fits
    assert narrow['legendBottom'] <= narrow['panelH'] - narrow['plotArea'], (
        'the legend still overflows the panel')
    for case in ('narrow', 'exact', 'single'):
        g = got[case]
        assert g['plotArea'] == 324, (case, g)
        assert g['legendBottom'] <= g['marginB'], (case, g)
        assert abs(g['legY'] + 44 / 324) < 1e-9, (case, g)
        # the redraw is a relayout carrying autosize, never a second react:
        # react does not re-read the container's height (measured)
        assert g['reacts'] == 0, (case, g)
        assert g['autosize'], (case, g)
    # a guess that is already right costs no redraw
    assert got['exact']['redraws'] == 0 and got['single']['redraws'] == 0
    assert got['single']['panelH'] == 400, 'the one-row panel moved'


def test_no_live_string_names_the_retired_picks_block():
    """Round 8 review, minor: stale prose pointing at a deleted section.

    Pre-fix the opponent-filter banner read "The infographic card, threshold
    tiers, Top Picks, and narrative are computed against the full N-opponent
    pool" and the methodology line "(you filtered the opponent set; the
    card, tiers, Top Picks and narrative above still use all N)". Round 8
    retired that block, so both sentences sent the reader looking for a
    heading the page no longer has (``grep 'Top Picks'`` returned three hits
    on each of the four shipped previews; two were live prose).

    Scanned on the RAW engine source, because ``strip_js`` blanks string
    literals and would make this pin vacuous. The positive control is the
    sentence itself: it must still be there, and must still name a section
    the page really renders.
    """
    raw = ENGINE_JS.read_text()
    assert 'Top Picks' not in raw
    # positive control: the sentences survive, naming a live section
    assert 'The infographic card, threshold tiers,' in raw
    assert 'the card, tiers,' in raw
    assert raw.count(W.SECTION_TITLE) >= 2, 'the banner lost its referent'
    # ...and that section is the one whose title they quote
    assert W.SECTION_TITLE == 'Which one to build?'


# ---------------------------------------------------------------------------
# Round 8 item 1: families
# ---------------------------------------------------------------------------

def _families(res, preset='flat'):
    return res['presets'][preset]['families']


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_family_is_grown_around_every_standout_outside_a_build(
        shadow_sableye):
    """Round 8 item 1, recomputed from the blob.

    Pre-fix there was no such object at all: a standout outside every build
    left the reader one exact spread and nothing to aim at near it, and the
    block's closing note said so ("what this page cannot give you is a region
    that lands you on one of these profiles").

    The two numbers are the 2026-09-17 corpus run's own, measured on this
    arm: 7/2/14 grows a 54-spread family guaranteeing 54 of the 87 decision
    matchups, 9/6/13 a 52-spread one guaranteeing 57. Both rules are an
    attack floor plus a defense staircase.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    assert ab['n_decision_cells'] == 87
    for key in ab['presets']:
        bl = ab['presets'][key]
        outside = [t for t in bl['standouts'] if t['in_build'] is None]
        assert len(outside) == 2, key
        fams = bl['families']
        assert len(fams) == 2, key
        assert [t['family'] for t in outside] == [0, 1], key
        by_iv = {f['seed_iv'].split('@')[0]: f for f in fams}
        assert set(by_iv) == {'7/2/14', '9/6/13'}, key
        assert (by_iv['7/2/14']['size'],
                by_iv['7/2/14']['n_guaranteed']) == (54, 54), key
        assert (by_iv['9/6/13']['size'],
                by_iv['9/6/13']['n_guaranteed']) == (52, 57), key
        for f in fams:
            assert f['n_decision_cells'] == 87
            assert f['rule'].startswith('Atk >= 148.77'), f['rule']
            assert 'defense staircase' in f['rule'], f['rule']
            # A family is grown from the seed's own wins alone, so the seed
            # is always in it.
            assert f['_mask'][f['seed_idx']]
            # ... and every member guarantees every cell the family claims.
            assert int(ab['frame']['Wd'][f['_mask']].all(axis=0).sum()) == \
                f['n_guaranteed']
    # A family is a pure function of (grid, seed): the preset decides which
    # standouts are OUTSIDE a build, never what the region around one is.
    sigs = {tuple((f['seed_iv'], f['_mask'].tobytes())
                  for f in ab['presets'][k]['families'])
            for k in ab['presets']}
    assert len(sigs) == 1, 'a family moved with the preset'


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_standout_inside_a_build_gets_no_family(sableye_plain):
    """"Standouts inside a build get no family" (Michael, 2026-09-17): the
    build IS the region around it, and a second outline over the same points
    would be two names for one answer.

    Plain Sableye is the page where every standout sits inside a build --
    the same page the fixed note's INSIDE variant ships on.
    """
    _state, all_facts, _path = sableye_plain
    found = False
    for facts in all_facts:
        ab = facts.get('_builds')
        if not ab:
            continue
        for bl in ab['presets'].values():
            inside = [t for t in bl['standouts'] if t['in_build'] is not None]
            if not inside:
                continue
            found = True
            for t in inside:
                assert t['family'] is None, t['iv']
            assert len(bl['families']) == sum(
                1 for t in bl['standouts'] if t['family'] is not None)
    assert found, 'no arm of this blob has a standout inside a build'


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_a_family_reaches_the_table_the_paragraph_and_the_payload(
        shadow_sableye):
    """Round 8 item 1, on the artifact. Three surfaces, one set of numbers.

    Pre-fix none of the three mentioned a family, and the standouts note
    closed on a claim ("cannot give you ... a region that lands you on one of
    these profiles") that the plot now draws two counterexamples to.
    """
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    ab = all_facts[0]['_builds']
    f0 = _families(ab)[0]
    # (a) the table row, after the builds, labelled as not a build
    assert 'data-fam-kind="wins"' in html
    assert W.FAMILY_NOT_A_BUILD == 'family (not a build)'
    assert 'Family around 7/2/14' in html
    i_b1 = html.index('Build 1 (primary)')
    assert html.index('Family around 7/2/14') > i_b1
    # Round 9 item 2: the Guarantees cell is the same two counts the builds'
    # carry, with a hover where a family has no robustness count of its own;
    # the seed is named in the last column; the staircase is a two-column
    # mini-table in the row's own expander. Pre-fix: '54 of 87 decision
    # matchups', 'seeded by the standout Most matchups won' and
    # 'HP 115 -&gt; Def ...' all inline in the row.
    assert '54 of 87 ' in html
    assert W._esc(W.FAMILY_GUARANTEE_HOVER) in html
    assert 'seeded by 7/2/14' in html
    assert '<table class="wb-steps">' in html
    assert W.STEPS_HEAD in html
    # (b) the standout's paragraph names its family in one sentence
    assert 'It sits in a family of 54 spreads' in html
    assert 'guarantee 54 of the 87 decision matchups together' in html
    # (c) the payload carries it -- and it is NOT a build, a region or a
    # lattice row
    pay = json.loads(
        re.search(r'class="wb-data">(.*?)</script>', html, re.S).group(1))
    idx = pay['bp']['presets']['flat']['families']
    assert idx == [0, 1], 'a preset carries INDICES into the one family table'
    fams = [pay['bp']['families'][k] for k in idx]
    assert fams[0]['size'] == 54 and fams[0]['nG'] == 54
    assert fams[0]['nDec'] == 87 and fams[0]['kind'] == 'wins'
    assert fams[0]['mask'], 'a family with no membership mask draws nothing'
    # one table, shared by every preset that draws the same region
    assert len(pay['bp']['families']) == 2
    assert all(p['families'] == [0, 1]
               for p in pay['bp']['presets'].values())
    block = pay['bp']['presets']['flat']
    assert not any(b.get('role') == 'family' for b in block['builds'])
    assert not any('Family' in (r.get('name') or '') for r in block['lattice'])
    assert not any('Family' in (c.get('combo') or '') for c in block['cols'])
    # the standout entry points at its family by index
    assert [t.get('family') for t in block['standouts']] == [0, 1]
    assert f0['seed_iv'].startswith('7/2/14')


@pytest.mark.local_artifacts
@pytest.mark.slow
@pytest.mark.parametrize('blob', [SABLEYE_SHADOW, SABLEYE_PLAIN, MELMETAL])
def test_a_family_row_hedges_its_rule_the_way_a_build_row_does(blob):
    """Round 8 review, minor: a family's rule was printed unqualified.

    Pre-fix the family row's "What it is" cell rendered ``build_desc(f)`` and
    "seeded by the standout ..." and stopped there, while every BUILD row
    ends on ``_fidelity_clause`` ("exactly these spreads", or on the shadow
    page's Build 1 wide "99% of the same spreads (4 extra, 3 missed)"). The
    family's rule comes from the SAME describer, whose ``d95`` accepts any
    rule from 0.95 fidelity up and deliberately prefers the SIMPLEST rule
    over the most faithful one -- so the first family whose rule fits at 96%
    would have been presented as if the rule WERE the region, which is the
    one thing the builds are careful to say out loud. Nothing shipped was
    wrong (all three shipped families are exact, jaccard 1.0, 0 extra, 0
    missed); the row simply could not have said otherwise.

    The payload could not either: ``add_family`` shipped
    iv/kind/rule/size/nG/nDec/seedIdx/mask and no fidelity, so the hover and
    the legend key had nothing to qualify with.
    """
    _state, all_facts = _facts_for(blob)
    seen, all_fam_rows = 0, []
    for ai, facts in enumerate(all_facts):
        ab = facts.get('_builds')
        if not ab:
            continue
        html = W.section_html(all_facts, ai)
        pay = json.loads(
            re.search(r'class="wb-data">(.*?)</script>', html, re.S).group(1))
        rows = pay['bp'].get('families') or []
        # the clause must be inside the FAMILY's own row: every build row
        # already prints one, so a whole-page search would pass pre-fix
        fam_rows = re.findall(r'<tr data-family="\d+">.*?</tr>', html, re.S)
        all_fam_rows += fam_rows
        for bl in ab['presets'].values():
            for f in bl.get('families') or []:
                seen += 1
                clause = W._fidelity_clause(f)
                # Round 9 item 2: a family's rule goes through the SAME cell
                # renderer a build's does (``rule_cell_html``), so an
                # inexact one carries the `~` glyph and the hover that says
                # how inexact, and an exact one carries neither -- exactly
                # as a build row behaves. Pre-fix the row appended
                # ``_fidelity_clause`` as text and this asserted it was in
                # the family's own <tr>.
                cell = W.rule_cell_html(f)
                rows_for_f = [r for r in fam_rows if W.family_title(f) in r]
                assert rows_for_f, (blob, W.family_title(f))
                assert any(cell in r for r in rows_for_f), (blob, cell)
                if W.rule_is_approx(f):
                    assert W.RULE_APPROX_GLYPH in cell
                    assert 'of the same spreads' in clause, clause
                else:
                    assert W.RULE_APPROX_GLYPH not in cell
                    # Round 10: a sentence, not a fragment -- it renders on
                    # a <p> of its own in the row expander. Pre-fix:
                    # clause == 'exactly these spreads'.
                    assert clause == ('The rule fits exactly: these spreads '
                                      'and no others.'), clause
                # the expander under the row carries the clause in full
                exp = W.gate_text(W.build_row_expander(ab, bl, None, 0, 'flat',
                                                       facts, family=f))
                assert clause in exp, clause
                assert f['rule_fidelity'] >= 0.95
        for r in rows:
            assert 'jac' in r, 'the payload still cannot qualify the rule'
            assert 0.95 <= r['jac'] <= 1.0, r['jac']
    if seen == 0:
        pytest.skip('no arm of this blob grows a family')
    # positive control: the scan finds rows at all, and they are the family
    # rows and not the build rows a whole-page search would have matched
    assert all_fam_rows, 'no family row matched the row scanner'
    assert not any('data-build=' in r for r in all_fam_rows)
    # ...and the hover says it only when it is NOT exact, so an exact rule
    # reads as the plain statement it is.
    raw = ENGINE_JS.read_text()
    assert 'function _wbFamilyFid(f) {' in raw
    assert "if (typeof f.jac !== 'number' || f.jac >= 0.999) return '';" in raw
    assert '_wbFamilyFid(f)' in _engine()


def test_the_family_rings_are_drawn_under_everything_and_are_their_own_mark():
    """Round 8 item 1, the JS half.

    A family must be readable as neither a build (a filled dot in a build
    hue) nor the wide region (a plain open circle in a tint of Build 1's
    hue), so it gets an open circle with a centre dot in its own standout's
    marker colour, one size larger than the wide ring, drawn first so it sits
    under every other trace. Pre-fix none of these symbols existed.
    """
    src = _engine()
    assert "var WB_FAM_SYMBOL = " in src
    assert 'var WB_FAM_SIZE = 12;' in src
    raw = ENGINE_JS.read_text()
    assert "var WB_FAM_SYMBOL = 'circle-open-dot';" in raw
    assert "var WB_RING_SYMBOL = 'circle-open';" in raw, 'the wide ring moved'
    body = src[src.index('function _wbFamilyTraces('):
               src.index('function _wbBuildGroups(')]
    assert '_wbFamilyColor(f, colors)' in body
    assert '_wbMask(f.mask)' in body and '_wbBit(m, i)' in body
    # colour by the seed standout, the same two colours the marks use
    col = src[src.index('function _wbFamilyColor('):
              src.index('function _wbFamilyTraces(')]
    assert 'colors.mark1' in col and 'colors.mark2' in col
    # drawn FIRST inside the builds grouping, so under the rings and the dots
    grp = src[src.index('function _wbBuildGroups('):
              src.index('function _wbBuildMarks(')]
    i_fam = grp.index('_wbFamilyTraces(pay, block, L, wins, colors, den)')
    i_wide = grp.index('if (wideIdx >= 0) out.push(ts[wideIdx]);')
    assert i_fam < i_wide


# ---------------------------------------------------------------------------
# Round 8 item 2: the one Notable spreads list
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_notable_list_is_the_named_spreads_deduplicated_by_profile(
        shadow_sableye):
    """Round 8 item 2, recomputed from the blob.

    Pre-fix the page ranked single spreads TWICE: the section's Standouts
    block named two (the most-winning spread and the highest-avg-score one)
    and the dive's "Top Picks" cards named three more off a composite of
    average-score rank, matchup flips and rank stability. One list now, built
    from the spreads the page already has a reason to name, and merged where
    two of them win the same matchups.

    On this arm the five candidates are 7/2/14 (most wins), 9/6/13 (highest
    avg battle score), 0/15/15 (SP1), 8/7/5 (Build 1's most-winning member)
    and 2/11/13 (Build 2's). 9/6/13 merges into 7/2/14 -- six decision
    matchups apart -- leaving four entries.
    """
    _state, all_facts, _path = shadow_sableye
    ab = all_facts[0]['_builds']
    Wd = ab['frame']['Wd']
    meta = ab['ctx']['meta']
    assert ([t['iv'].split('@')[0] for t in ab['presets']['flat']['notable']]
            == ['7/2/14', '0/15/15', '8/7/5', '2/11/13'])
    # A build's most-winning member is chosen on the preset's own weighted
    # count, so the last two entries move with the knob (Even shields:
    # 9/2/7 and 9/0/14). The two standouts and SP1 do not.
    assert ([t['iv'].split('@')[0] for t in ab['presets']['even']['notable']]
            == ['7/2/14', '0/15/15', '9/2/7', '9/0/14'])
    for key, bl in ab['presets'].items():
        nb = bl['notable']
        ivs = [t['iv'].split('@')[0] for t in nb]
        assert ivs[:2] == ['7/2/14', '0/15/15'], (key, ivs)
        assert len(nb) == 4, (key, ivs)
        assert [r[0] for r in nb[0]['roles']] == ['wins']
        assert nb[1]['roles'] == [('sp1', None)]
        assert nb[2]['roles'] == [('build', 0)]
        assert nb[3]['roles'] == [('build', 1)]
        # the variant carries the reason it was on the list
        v = nb[0]['variants']
        assert len(v) == 1 and v[0]['iv'].split('@')[0] == '9/6/13'
        assert v[0]['roles'] == [('score', None)]
        assert v[0]['n_diff'] == 6
        # recomputed: the merge is above the bar and every kept pair below it
        def _j(a, b):
            u = int((Wd[a] | Wd[b]).sum())
            return (int((Wd[a] & Wd[b]).sum()) / u) if u else 0.0
        assert _j(nb[0]['idx'], v[0]['idx']) >= builds_mod.NOTABLE_DEDUP_J
        assert int((Wd[nb[0]['idx']] ^ Wd[v[0]['idx']]).sum()) == 6
        for a in range(len(nb)):
            for b in range(a + 1, len(nb)):
                assert _j(nb[a]['idx'], nb[b]['idx']) < \
                    builds_mod.NOTABLE_DEDUP_J, (key, ivs[a], ivs[b])
        # every entry is a real spread of this grid, and SP1 really is SP1
        for t in nb:
            assert builds_mod.iv_str(meta, t['idx']) == t['iv']
        assert nb[1]['sp_rank'] == 1


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_notable_block_prints_what_michael_asked_each_entry_to_print(
        shadow_sableye):
    """Round 8 item 2, on the artifact: IVs, stats, CP, SP rank, wins,
    decision cells won, where it sits, and -- for an entry no build holds --
    the two matchup lists round 5 added.

    Pre-fix this block was headed "Standouts" and carried two entries; SP1
    and the builds' most-winning members were named only in the table, and
    the page's other list of single spreads was the retired Top Picks.
    """
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    text = W.gate_text(W.notable_html(all_facts[0], all_facts[0]['_builds'],
                                      builds_mod.PRESET_FLAT, all_facts))
    assert 'Notable spreads' in html
    assert '<p class="wb-mem-head">Standouts</p>' not in html
    # Round 9 item 5 kept every fact and changed the SHAPE: one stat line
    # plus up to three labelled facts, with the argument in the entry's own
    # expander. Each pre-fix sentence is recorded beside its replacement.
    # (a) the four entry heads, each naming why the spread is on the list.
    #     Pre-fix: 'Most matchups won (all nine shield scenarios): 7/2/14'.
    for head in ('7/2/14 -- Most matchups won (all nine shield scenarios)',
                 '0/15/15 -- Stat-product rank-1 (SP1)',
                 "8/7/5 -- Build 1's most-winning member",
                 "2/11/13 -- Build 2's most-winning member"):
        assert head in text, head
    # (b) stats, CP and SP rank on the stat line. Pre-fix: '148.79 atk /
    #     96.35 def / 126 hp, CP 1499, stat-product rank 817'.
    assert '148.79 / 96.35 / 126 | CP 1499 | SP rank 817' in text
    assert 'wins 382 of 684 over all nine shield scenarios' in text
    assert '62 of 87 decision matchups' in text
    assert "Build 1's most-winning member wins 378" in text
    # (c) where it sits -- build, wide region, family or none
    assert 'It is in none of the builds, though Build 1 wide holds it.' in text
    assert 'It is a member of Build 2, which guarantees 41 of the 47' in text
    # (d) the two matchup lists, on the outside-a-build entry only
    assert 'vs Build 1: wins 13 it does not guarantee' in text
    assert 'loses: 6 of the 55 Build 1 guarantees' in text
    # (e) the variants sentence, in the entry's own expander now
    assert ('9/6/13 (Highest avg battle score) differs from it by 6 decision '
            'matchups' in text)
    # (f) the advice call-out and the encounter-count sentence, rendered
    #     once for the page rather than once per Build criteria setting.
    #     Pre-fix both were inside notable_html, with the call-out being
    #     ``W.standout_note(...)``.
    tail = W.gate_text(W.notable_tail_html(all_facts[0],
                                           all_facts[0]['_builds']))
    assert W.NOTABLE_ADVICE in tail
    assert 'Rocket-grunt encounters' in tail
    assert 'Rocket-grunt encounters' not in text
    assert tail in W.gate_text(html)


# ---------------------------------------------------------------------------
# Round 8 item 3: the collection, by build
# ---------------------------------------------------------------------------

def test_each_owned_star_is_outlined_in_its_builds_colour():
    """Round 8 item 3(a). Pre-fix every gold star carried the same ink-colour
    border (``t.marker.line = { width: 1.5, color: plotChrome().ink }``), so a
    collection of 40 stars said "you own these" and nothing else."""
    src = _engine()
    body = src[src.index('function _wbOwnedTrace('):
               src.index('function _wbOwnWhere(')]
    assert 'sideFn, borderFn) {' in body
    assert 'ob.push(borderFn ? borderFn(i) : plotChrome().ink);' in body
    assert ('t.marker.line = { width: 2, color: borderFn ? ob : '
            'plotChrome().ink };') in body
    # the classification is read ONCE and drives both the border and the list
    w = src[src.index('function _wbOwnWhere('):
            src.index('function _wbOwnColorOf(')]
    assert '_wbBuildOf(pay.bp, block, i)' in w
    assert "role !== " in w and '_wbFamilies(pay, block)' in w
    raw = ENGINE_JS.read_text()
    rw = raw[raw.index('function _wbOwnWhere('):
             raw.index('function _wbOwnColorOf(')]
    # build, then the wide region, then a family, then nothing
    assert rw.index("{ kind: 'build'") < rw.index("{ kind: 'wide'") \
        < rw.index("{ kind: 'family'") < rw.index("{ kind: 'none'")
    # and the builds view hands both of them in
    rr = src[src.index('function wbRenderBox('):
             src.index('function wbSelectView(')]
    assert '_wbOwnSide(pay, pblock, scen, i)' in rr
    assert '_wbOwnColor(pay, pblock, ownCols, colors, i)' in rr


def test_your_collection_is_listed_under_the_plot_grouped_by_build():
    """Round 8 item 3(b): the same collection state the stars read, grouped
    the way the reader's question is shaped. Pre-fix there was no such list --
    a reader could see a gold star inside Build 1 but had no way to read off
    which of their own mons those stars were."""
    src = _engine()
    body = src[src.index('function _wbYours('):
               src.index('function _wbWireLegend(')]
    assert "root.querySelector(" in body
    assert 'state.ownedByIv' in body
    # grouped in Michael's order, builds first and "in no build" last
    assert 'var rank = { build: 0, wide: 1, family: 2, none: 3 };' in body
    # each row is IVs, SP rank, wins out of the axis denominator, and the
    # CURRENT CP only when the collection knows one. strip_js blanks string
    # literals, so the two labelled bits are read raw.
    assert 'DATA.spRanks[i]' in body
    assert 'wins[i]' in body and 'den' in body
    assert 'if (cps.length) bits.push(' in body
    # ... and a manual entry typed with the level field blank knows NEITHER a
    # level nor a current CP (``mon.cp`` is 0 there). Pre-fix the row read
    # "1/15/13 (SP #9, wins 394 of 684, CP 0)" -- measured in headless Chrome
    # on the round-8 Melmetal GL render.
    assert 'if (mon.level == null || !(mon.cp > 0)) continue;' in body
    raw = ENGINE_JS.read_text()
    raw_body = raw[raw.index('function _wbYours('):
                   raw.index('function _wbWireLegend(')]
    assert "'SP #' + DATA.spRanks[i]" in raw_body
    assert "'wins ' + wins[i] + ' of ' + den" in raw_body
    assert "'CP ' + cps.join(" in raw_body
    # hidden outright when there is no collection
    assert 'function clear() { box.hidden = true; box.innerHTML =' in body
    assert 'if (!n) return clear();' in body
    # re-rendered by the one function a preset change and a collection load
    # both go through
    rr = src[src.index('function wbRenderBox('):
             src.index('function wbSelectView(')]
    assert '_wbYours(root, pay, pblock, wins, den);' in rr


@pytest.mark.local_artifacts
def test_the_section_ships_the_collection_list_container(shadow_sableye):
    """The container is server-rendered and starts hidden, so a page with no
    collection shows nothing at all rather than an empty heading."""
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    assert '<div class="wb-yours" hidden></div>' in html
    # Round 9 item 3: directly under the builds table, in the "Is mine in
    # one of these?" block -- the section's second question answered where
    # it is asked. Pre-fix it sat under the plot.
    assert html.index('class="wb-yours"') < html.index('class="wb-panel"')
    assert html.index('wb-builds-table') < html.index('class="wb-yours"')
    assert html.index('class="wb-mine"') < html.index('class="wb-yours"')
    # ...and the entry point next to it drives the page's ONE collection
    # loader rather than a second paste box (DRY rule D2).
    assert 'wbOpenCollection(this)' in html
    assert 'collection-csv' not in html
    assert '#dd-which-build .wb-yours[hidden] { display: none; }' in W.CSS


def test_a_variant_keeps_the_pages_own_short_name_and_says_when_it_is_identical():
    """Round 8, from the first round-8 render.

    Two wordings the variants sentence got wrong on pages other than Shadow
    Sableye, both fixed here:

    * ``0/13/15 (sp1) differs from it by 3 decision matchups`` on the
      Melmetal ULTRA page -- the sentence lower-cased the canonical short
      name to fit, turning the section's own term SP1 into a second spelling
      of it. The name now travels verbatim.
    * ``0/15/15 (sp1) differs from it by 0 decision matchups`` on the plain
      Sableye page -- a sentence about a difference that is not there. Two
      spreads with identical decision-win sets now say so.

    Driven through the renderer on synthetic blocks, so it runs with no blob.
    """
    bl = {'builds': [{'role': 'primary', 'size': 61, 'n_guaranteed': 55,
                      'most_winning_member': {'iv': '8/7/5@50', 'wins': 378}}]}
    same = {'variants': [{'iv': '0/15/15@50', 'roles': [('sp1', None)],
                          'n_diff': 0}]}
    out = W.notable_variants_sentence(bl, same)
    assert out.startswith('0/15/15 (SP1) wins exactly the same decision '
                          'matchups, so this entry is the offer')
    assert 'sp1' not in out and 'by 0 ' not in out
    near = {'variants': [{'iv': '0/13/15@50', 'roles': [('sp1', None)],
                          'n_diff': 3}]}
    out2 = W.notable_variants_sentence(bl, near)
    assert ('0/13/15 (SP1) differs from it by 3 decision matchups'
            in out2), out2
    # a build's most-winning member keeps its own name, and a mixed span
    # reads as a range
    two = {'variants': [{'iv': '9/6/13@47.5', 'roles': [('score', None)],
                         'n_diff': 6},
                        {'iv': '7/2/12@50', 'roles': [('build', 0)],
                         'n_diff': 2}]}
    out3 = W.notable_variants_sentence(bl, two)
    assert '9/6/13 (Highest avg battle score)' in out3
    assert '7/2/12 (Build 1&#x27;s most-winning member)' in out3
    assert 'differ from it by 2 to 6 decision matchups' in out3
    # and no variants is no sentence
    assert W.notable_variants_sentence(bl, {'variants': []}) == ''


# ---------------------------------------------------------------------------
# 12. B1 -- the alternative rectangle's mask is read off its OWN axes
#     (2026-09-20 pre-dive grid, docs/validations/2026-09-20_predive_grid_wotb_v4.md)
# ---------------------------------------------------------------------------

# Blobs whose alternative rectangle is ATTACK-paired, i.e. the shape that
# made compute_masks raise. The probe blob the grid report names comes
# first; the 2026-09-13 bake blobs behind it are the durable fallbacks, so
# this test does not go dark the moment the probe blob is pruned.
_ATTACK_PAIRED_BLOBS = [
    '20260920_093803_Oinkologne_Female_great.replay.pkl.gz',
    '20260913_071040_Cradily_great.replay.pkl.gz',
    '20260913_020826_Mandibuzz_great.replay.pkl.gz',
    '20260913_063703_Morpeko_Full_Belly_great.replay.pkl.gz',
]


def _first_present(names):
    for name in names:
        for d in _replay_dirs():
            if (d / name).exists():
                return d / name
    pytest.skip("no attack-paired replay blob on this machine")


def _decode_mask(packed, n):
    import base64
    import numpy as np
    raw = np.frombuffer(base64.b64decode(packed), dtype=np.uint8)
    return np.unpackbits(raw, bitorder='little')[:n].astype(bool)


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_prepare_survives_an_attack_paired_alternative_rectangle():
    """An attack-paired rectangle must not cost the page its section.

    PRE-FIX (measured 2026-09-20): ``compute_masks`` read
    ``alt['def_cut']`` / ``alt['hp_cut']`` unconditionally, but
    ``deep_dive_brief._alt_facts`` attaches those back-compat aliases ONLY
    when the pair is (Def, HP) -- deliberately, because a (HP, Atk) or
    (Def, Atk) rectangle has no Def-and-HP reading. So ``prepare()`` raised
    ``KeyError: 'def_cut'`` here, ``deep_dive._which_build_sections``
    swallowed it, and the page shipped with NO "Which one to build?"
    section at all. On the grid report's samples that was 4 of 13 Great
    League blobs and 3 of 17 Ultra League ones.

    On the Oinkologne (Female) probe blob the pre-fix run raised; post-fix
    arm 0 is ``axes=['hp', 'atk']`` with 302 members and a packed mask.
    """
    import numpy as np
    path = _first_present(_ATTACK_PAIRED_BLOBS)
    state = B.load_blob(str(path))
    all_facts = W.prepare(state, str(path))          # pre-fix: KeyError
    attack_paired = [f for f in all_facts
                     if (f.get('alternative') or {}).get('axes')
                     and 'atk' in f['alternative']['axes']]
    assert attack_paired, (
        f"{path.name} no longer carries an attack-paired rectangle; this "
        "test needs one to mean anything")
    for facts in attack_paired:
        alt = facts['alternative']
        # the exact pre-fix failure, pinned: the aliases are absent
        assert 'def_cut' not in alt and 'hp_cut' not in alt
        if alt['too_wide']:
            continue
        packed = facts['_masks']['alt']
        assert packed, "an in-scope rectangle must ship a mask"
        _scores, meta = B.arm_view(state, all_facts.index(facts), 'pvpoke')
        flags = _decode_mask(packed, len(meta))
        assert int(flags.sum()) == int(alt['n'])
        a0, a1 = alt['axes']
        expect = ((meta[:, B.AXIS_META_COL[a0]] >= alt['cut_a'])
                  & (meta[:, B.AXIS_META_COL[a1]] >= alt['cut_b']))
        assert np.array_equal(flags, expect)


def _synthetic_meta(n=64):
    import numpy as np
    meta = np.zeros((n, 8), dtype=float)
    meta[:, 0] = np.arange(n) % 16              # atk IV
    meta[:, 1] = (np.arange(n) // 4) % 16       # def IV
    meta[:, 2] = (np.arange(n) // 2) % 16       # hp IV
    meta[:, 3] = 40.0
    meta[:, 4] = 1500.0
    meta[:, 5] = 100.0 + meta[:, 0] * 1.5       # atk
    meta[:, 6] = 90.0 + meta[:, 1] * 1.25       # def
    meta[:, 7] = 120.0 + meta[:, 2]             # hp
    return meta


@pytest.mark.parametrize('axes,search', [
    (('def', 'hp'), ('hp', 'def')),
    (('hp', 'atk'), ('hp', 'atk')),
    (('def', 'atk'), ('def', 'atk')),
])
def test_the_alt_mask_is_right_for_every_axis_pairing(axes, search):
    """All three rectangle shapes the brief can emit, end to end, no blob.

    The alt dict is built by ``deep_dive_brief._alt_facts`` itself, so the
    back-compat-alias rule under test is the real one and not a fixture's
    imitation: only (Def, HP) carries ``def_cut``/``hp_cut``, which is
    precisely why the pre-fix ``(dfn >= alt['def_cut']) & (hp >=
    alt['hp_cut'])`` raised ``KeyError`` on the other two.
    """
    import numpy as np
    n = 64
    meta = _synthetic_meta(n)
    state = {'opponent_names': ['A', 'B'],
             'shield_scenarios': [(0, 0), (1, 1)],
             'moveset_data': [{'meta': meta,
                               'scores': {'pvpoke':
                                          np.full((n, 2, 2), 500, np.int32)}}]}
    win = np.zeros((n, 2, 2), dtype=bool)
    all_cuts = {'atk': 112.0, 'def': 101.0, 'hp': 127.0}
    cuts = {a: all_cuts[a] for a in axes}
    mask = np.ones(n, dtype=bool)
    for a in axes:
        mask &= meta[:, B.AXIS_META_COL[a]] >= cuts[a]
    alt = B._alt_facts({'mask': mask, 'axes': axes, 'search_axes': search,
                        'cuts': cuts, 'n': int(mask.sum()), 'guaranteed': [],
                        'exclusive': [], 'given_up': []},
                       state, meta, win, n)
    assert ('def_cut' in alt) is (set(axes) == {'def', 'hp'})
    assert not alt['too_wide'], "the fixture must stay in scope for a mask"
    facts = {'floor': {'axis': 'atk', 'T': 112.0,
                       'n_above': int((meta[:, 5] >= 112.0).sum()),
                       'printed': '112.00'},
             'alternative': alt}
    out = W.compute_masks(state, 0, facts, 'pvpoke', 'l50')  # pre-fix: KeyError
    assert np.array_equal(_decode_mask(out['alt'], n), mask)
    assert int(mask.sum()) == int(alt['n'])


def test_a_code_bug_in_the_section_stops_the_dive():
    """``_which_build_sections`` degrades on no-verdict, crashes on bugs.

    PRE-FIX the handler was ``except Exception``, so the B1 ``KeyError``
    above became one WARNING line, the dive exited 0, and the page shipped
    without the merge's flagship section. Only two outcomes are legitimate
    no-verdicts -- a failed brief guard, and a blob that is not on disk --
    and those still degrade.
    """
    import deep_dive
    from deep_dive_brief import GuardError
    state = {'replay_blob_path': '/nonexistent/x.replay.pkl.gz',
             'split_movesets': False, 'moveset_data': [{}]}

    def raising(exc):
        def _p(_state, _blob, **_kw):
            raise exc
        return _p

    for exc in (GuardError('G-caveat: field=all'),
                FileNotFoundError('blob is gone')):
        W_prepare = W.prepare
        W.prepare = raising(exc)
        try:
            assert deep_dive._which_build_sections(state) == ({}, {}, {},
                                                              {}, {})
        finally:
            W.prepare = W_prepare
    for exc in (KeyError('def_cut'), ValueError('mask covers 0 spreads')):
        W_prepare = W.prepare
        W.prepare = raising(exc)
        try:
            with pytest.raises(type(exc)):
                deep_dive._which_build_sections(state)
        finally:
            W.prepare = W_prepare


# ---------------------------------------------------------------------------
# 13. The best-buddy swap covers the WHOLE section
#     (2026-09-20 pre-dive grid, lens 5)
# ---------------------------------------------------------------------------

def _engine_js():
    return (SCRIPTS_DIR / 'deep_dive_engine.js').read_text()


def _js_region(name, until):
    """(raw, code) slices of one JS region, cut at the SAME offsets.

    ``strip_js`` blanks comments and string literals to spaces without
    moving anything, so one pair of indices addresses both views: the
    stripped half proves a call is real code, the raw half is the only
    place a string literal still exists to be read.
    """
    raw = _engine_js()
    code = strip_js(raw)
    i = code.index(name)
    j = code.index(until, i)
    return raw[i:j], code[i:j]


def test_the_section_is_registered_as_a_best_buddy_host_pair():
    """The section gets its own host/template pair, like the card and prose.

    PRE-FIX only `dd-bb-card-*`, `dd-bb-prose-*` and `dd-bb-clusters-*` were
    registered, and the clusters live INSIDE the section -- so ticking Best
    Buddy swapped L51 clusters into an L50 headline, an L50 answer strip and
    an L50 builds table.
    """
    raw, code = _js_region('function _initBestBuddy', 'function _bbOpenIn')
    assert "_bbInitHost('dd-bb-wb-host', 'dd-bb-wb-tmpl')" in raw
    # positive control: the pre-existing pairs read the same way, so a change
    # to the registration syntax fails here rather than silently emptying
    # this assertion; and the calls are code, not a comment.
    assert "_bbInitHost('dd-bb-card-host', 'dd-bb-card-tmpl')" in raw
    assert code.count('_bbInitHost(') == 4


def test_the_swap_carries_the_sections_tab_scenario_and_preset():
    """A toggle must not reset what the reader set inside the section.

    `<details>` open state is carried for every host by _bbOpenIn/_bbReopen.
    These three are the section's own: the figure tabs, its Shield-scenario
    control, and the Build-criteria preset (re-applied from the controls
    strip rather than copied, since the swap never touches that strip).
    """
    raw, code = _js_region('function setBestBuddyLevel',
                           'window.setBestBuddyLevel')
    assert '_wbSnapshot()' in code
    assert '_wbRestore(' in code
    assert "'dd-bb-wb-host'" in raw
    raw_r, code_r = _js_region('function _wbRestore',
                               'function setBestBuddyLevel')
    assert 'data-wb-view' in raw_r            # the tab
    assert '_wbSyncScen(' in code_r           # the Shield-scenario control
    assert 'wbApplyPreset(' in code_r         # the Build-criteria preset


def test_the_section_reads_the_level_it_is_showing():
    """`wbLevelArrays` must follow the displayed level, not pin to L50.

    It pinned to the stashed L50 arrays because only one L50 copy of the
    section existed; with a per-level copy, the copy on screen was derived
    at whatever level DATA.iv* holds, which is what its thresholds must be
    compared against. `wbWins` likewise goes through `getScoreKey`, whose
    L51 suffix follows `state.levelMode`, and its cache is keyed on that.
    """
    js = strip_js(_engine_js())
    fn = js[js.index('function wbLevelArrays'):]
    fn = fn[:fn.index('function wbWins')]
    assert '_bbL50' not in fn, fn          # pre-fix: `return ... ? _bbL50 : DATA`
    assert 'return DATA;' in fn
    wins = js[js.index('function wbWins'):]
    wins = wins[:wins.index('_wbWinsCache[key] = out')]
    assert 'getScoreKey(mi, mode)' in wins
    assert 'getScores(mi, mode)' in wins


def test_a_no_op_best_buddy_dive_renders_one_section():
    """No second copy when the two levels are provably the same grid.

    A species whose every IV is already CP-capped below the alt level has
    an L51 grid identical to its L50 one, so a second section would be a
    byte-identical ~140 KB duplicate and a wasted `prepare()` per arm.
    """
    import deep_dive
    base = {'moveset_data': [{'meta_l51': [[0]]}]}
    assert deep_dive._bb_section_active(
        dict(base, best_buddy={'active': True, 'noop': False})) is True
    assert deep_dive._bb_section_active(
        dict(base, best_buddy={'active': True, 'noop': True})) is False
    assert deep_dive._bb_section_active(
        dict(base, best_buddy={'active': False})) is False
    assert deep_dive._bb_section_active({'moveset_data': [{}],
                                         'best_buddy': {'active': True}}) is False
    assert deep_dive._bb_section_active({}) is False


# A dive whose best buddy is NOT a no-op, so the two levels really differ.
SABLEYE_PLAIN_BB = '20260911_051621_Sableye_great.replay.pkl.gz'


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_the_l51_section_says_something_different():
    """The whole point: the two halves are not the same bytes.

    On plain Sableye GL the line moves 123.419 -> 123.41 between the levels,
    so the headline, the summary the collapsed row carries and the section's
    length all differ. PRE-FIX there was no L51 section at all to compare --
    the L50 one was the only copy, and the toggle left it in place.
    """
    path = require_blob(SABLEYE_PLAIN_BB)
    state = B.load_blob(str(path))
    out = {}
    for level in ('l50', 'l51'):
        facts = W.prepare(state, str(path), level=level)
        out[level] = (W.section_html(facts, 0, moveset_idx=0, page_movesets=1),
                      facts[0]['floor']['printed'])
    assert out['l50'][1] != out['l51'][1], out
    assert out['l50'][0] != out['l51'][0]
    # and the difference is visible in the collapsed line, not only deep in
    # a payload a reader never opens
    def _summary(html):
        i = html.index('<span class="wb-head">')
        return html[i:html.index('</span>', i)]
    assert _summary(out['l50'][0]) != _summary(out['l51'][0])


# Non-no-op best-buddy dives with a section, smallest first.
_BB_SECTION_BLOBS = [
    '20260911_153453_Mimikyu_ultra.replay.pkl.gz',
    '20260911_051621_Sableye_great.replay.pkl.gz',
    '20260911_071541_Medicham_great.replay.pkl.gz',
]


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_a_rendered_best_buddy_page_carries_one_live_section_and_one_inert(
        tmp_path):
    """Exactly one `.wb-root` in the document, exactly one in the template.

    PRE-FIX the page had ONE `.wb-root` full stop, and `dd-bb-clusters-host`
    sat inside it -- so the toggle replaced the clusters under an L50
    headline. Now the section itself is the host/template pair and the
    clusters ride inside each half, which is why `dd-bb-clusters-host` is
    absent from a page that HAS a section (it stays for the blob-free
    fallback, where the clusters render as a sibling).
    """
    import re
    from tests.conftest import load_deep_dive
    dd = load_deep_dive()
    path = _first_present(_BB_SECTION_BLOBS)
    state = dd.load_replay_state(str(path))
    state['html_path'] = str(tmp_path / 'index.html')
    state['card_path'] = None
    state['replay_blob_path'] = str(path)
    dd.render_dive_html(state)
    html = (tmp_path / 'index.html').read_text()
    assert html.count('id="dd-bb-wb-host"') == 1
    assert html.count('id="dd-bb-wb-tmpl"') == 1
    assert html.count('class="wb-root"') == 2        # pre-fix: 1
    assert html.count('id="dd-which-build"') == 2    # pre-fix: 1
    # one clusters body per section half, and no sibling pair of their own
    assert html.count('id="dd-matchup-clusters"') == 2
    assert 'id="dd-bb-clusters-host"' not in html    # pre-fix: present
    # the template really is the second copy, and it really is inert
    tmpl = html[html.index('id="dd-bb-wb-tmpl"'):]
    tmpl = tmpl[:tmpl.index('</template>')]
    assert 'class="wb-root"' in tmpl
    assert 'id="dd-matchup-clusters"' in tmpl
    live = re.sub(r'<template\b.*?</template>', '', html, flags=re.S)
    assert live.count('class="wb-root"') == 1
    # no stray assembly markers shipped
    assert 'WHICH_BUILD_SLOT' not in html
    assert 'MATCHUP_CLUSTERS_SLOT' not in html


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_aegislash_page_still_gets_a_section():
    """G-caveat's focal exemption, on the blob that lost the section to it.

    Pre-fix (2026-09-20) ``prepare()`` on this blob raised ``G-caveat:
    field=all cell=Aegislash printed='No attack, defense or HP threshold
    decides a matchup for Aegislash (Shield) runn' recomputed=named with no
    engine-divergence marker``, so ``deep_dive.py`` logged one WARNING and
    shipped the flagship section ABSENT on every Aegislash page. The gate is
    NOT off here: a caveat cell inside the page still has to carry the mark,
    which is what ``cell_label_with_caveat`` guarantees.
    """
    path = require_blob(AEGISLASH_SHIELD)
    state = B.load_blob(str(path))
    all_facts = W.prepare(state, str(path))
    assert all_facts, 'prepare returned no arms'
    html = W.section_html(all_facts, 0)
    # Non-trivial output, not an empty string that would pass every scan.
    assert len(html) > 5000, len(html)
    assert 'Aegislash' in html
    # The focal's own NAME is exempt; an Aegislash CELL -- which on this page
    # means the mirror -- still carries the marker. Checked on the plain
    # text, since the markup between the name and the mark is what a naive
    # scan trips on.
    txt = W.gate_text(html)
    cells = list(re.finditer(r'\dv\d Aegislash', txt))
    assert cells, 'no Aegislash cell on the page: the marker check is vacuous'
    for m in cells:
        window = txt[m.start():m.start() + 100]
        assert 'divergence' in window, window


# ---------------------------------------------------------------------------
# 6. A guard failure takes down ONE arm, not the dive
# ---------------------------------------------------------------------------
# 2026-09-22. shadow-alolan-ninetales-ultra-league shipped all SEVEN of its
# files with no "Which one to build?" section because arm 6 raised one
# GuardError: prepare() computes every arm in one loop and
# _which_build_sections caught the escape for the whole dive. The guard was
# right (see tests/test_deep_dive_brief.py, the merged-rung gate cell), but
# six arms whose numbers were fine lost their section for a seventh arm's bad
# sentence.


def _prepared_stub(arm, label, failed=False):
    """One entry of a prepare() return list, as the caller sees it."""
    f = _facts()
    f['header'] = dict(f['header'], arm=arm, arm_label=label, n_arms=3)
    if failed:
        return W.failed_arm_facts(
            {'species': 'Sableye', 'shadow': True, 'league': 'great',
             'moveset_data': [{'label': label}] * 3},
            arm, 'G-recompute: field=Floor merge ...')
    f['_builds'] = None
    return f


def test_one_arm_s_guard_failure_leaves_the_other_arms_their_section(
        monkeypatch):
    """Pre-fix: prepare()'s GuardError escaped and EVERY arm lost its
    section (``_which_build_sections`` returned five empty maps). Now the
    failed arm alone is missing, and it is missing out loud."""
    import deep_dive
    labels = ['POWDER_SNOW / ICE_BEAM',
              'POWDER_SNOW / BLIZZARD',
              'POWDER_SNOW / WEATHER_BALL_ICE']
    facts = [_prepared_stub(0, labels[0]),
             _prepared_stub(1, labels[1], failed=True),
             _prepared_stub(2, labels[2])]

    monkeypatch.setattr(W, 'prepare', lambda state, blob, level='l50': facts)
    monkeypatch.setattr(W, 'section_html',
                        lambda af, arm, **kw: f'<section>{arm}</section>')
    monkeypatch.setattr(W, 'card_specs', lambda f, b: [f'card{f["header"]["arm"]}'])

    state = {'replay_blob_path': '/nowhere/x.replay.pkl.gz',
             'split_movesets': True,
             'moveset_data': [{'label': x} for x in labels]}
    html, presets, cards, h51, c51 = deep_dive._which_build_sections(state)

    assert sorted(html) == [0, 2], html
    assert sorted(cards) == [0, 2]
    assert sorted(presets) == [0, 2]
    assert (h51, c51) == ({}, {})


def test_prepare_catches_the_guard_per_arm_and_says_so(monkeypatch, caplog):
    """The real prepare(), with only the brief's per-arm calls stubbed.

    Pre-fix prepare() had no try/except at all: the GuardError from arm 1
    propagated out of the loop and the caller dropped all three arms.
    """
    labels = ['POWDER_SNOW / ICE_BEAM',
              'POWDER_SNOW / BLIZZARD',
              'POWDER_SNOW / WEATHER_BALL_ICE']
    state = {'species': 'Ninetales (Alolan)', 'shadow': True,
             'league': 'ultra', 'moveset_data': [{'label': x} for x in labels]}

    def fake_brief(st, arm, blob, mode='pvpoke', level='l50'):
        if arm == 1:
            raise B.GuardError(
                "G-recompute: field=Floor merge cell=2v2 Ninetales (Alolan) "
                "printed='clean at its own cut' recomputed=not a clean "
                "partition there (blob=b arm=1 mode=pvpoke)")
        f = _facts()
        f['header'] = dict(f['header'], arm=arm, arm_label=labels[arm],
                           n_arms=3, species='Ninetales (Alolan)')
        return f

    monkeypatch.setattr(B, 'compute_brief', fake_brief)
    monkeypatch.setattr(B, 'shared_line_with', lambda f, prev: None)
    monkeypatch.setattr(B, 'render_parts',
                        lambda *a, **k: (['head.'], 'strip', [], []))
    monkeypatch.setattr(W, 'compute_masks', lambda *a, **k: {})
    monkeypatch.setattr(W.builds, 'compute_builds', lambda *a, **k: None)

    with caplog.at_level('WARNING', logger='deep_dive'):
        all_facts = W.prepare(state, '/nowhere/b.replay.pkl.gz')

    assert len(all_facts) == 3, 'the list must stay index-aligned by arm'
    assert all_facts[1]['_failed'].startswith('G-recompute')
    assert 'floor' not in all_facts[1], (
        'a failed arm must not carry a floor: "no line" is a computed answer')
    assert [f.get('_failed') for f in all_facts] == [None, all_facts[1]['_failed'], None]
    # The morning gate scans the chain log for this literal
    # (tests/test_verify_overnight_which_build_scan.py), so a per-arm
    # omission has to keep saying it.
    msgs = [r.message for r in caplog.records]
    assert any('Which one to build?: omitted' in m for m in msgs), msgs
    assert any('moveset 2 of 3' in m for m in msgs), msgs


def test_a_failed_arm_is_named_but_never_given_a_line(monkeypatch):
    """The other arms' cross-arm prose must not invent the failed arm's line.

    A failed arm has no floor, and calling that "carries no line" would be a
    claim about numbers nobody computed. It is counted out of the totals and
    named as uncomputed instead.
    """
    labels = ['POWDER_SNOW / ICE_BEAM',
              'POWDER_SNOW / BLIZZARD',
              'POWDER_SNOW / WEATHER_BALL_ICE']
    facts = [_prepared_stub(0, labels[0]),
             _prepared_stub(1, labels[1], failed=True),
             _prepared_stub(2, labels[2])]
    lead = ' '.join(W.lead_sentences(facts, 0))
    assert '2 of the 3 movesets' in lead, lead
    assert 'could not be computed' in lead, lead
    assert 'carries no line' not in lead and 'carry no line' not in lead
    # The summary's clause must not claim a shared line across an arm whose
    # line was never computed.
    summary = W.summary_sentence(facts[0], facts)
    assert 'the same line as its other' not in summary, summary


# ---------------------------------------------------------------------------
# 6. "The mirror" (round 11, 2026-09-22)
# ---------------------------------------------------------------------------

def test_the_mirror_block_is_empty_without_a_cohort():
    """No mirror facts on the arm, no block at all -- not a heading with
    nothing under it. The computation's own gates are pinned in
    tests/test_deep_dive_builds.py; this is the renderer's half."""
    assert W.mirror_block_html({}, None) == ''
    assert W.mirror_block_html({}, {'presets': {}, 'mirror': {}}) == ''
    assert W.mirror_trace_caption(None) == ''
    assert W.mirror_trace_caption({'mirror': {}}) == ''


def test_the_mirror_terms_are_in_the_one_registry():
    """'CMP' rides on the entry that was already there, the way SP1 does;
    'mirror cohort' is its own."""
    assert glossary.definition('mirror cohort')
    assert glossary.DISPLAY['charge-move priority'].endswith('(CMP)')
    marker = W.TermMarker()
    out = marker.mark('<p>CMP against the mirror cohort.</p>')
    assert marker.ordered() == ['charge-move priority', 'mirror cohort']
    assert glossary.TERMS['charge-move priority'] in out
    assert glossary.TERMS['mirror cohort'] in out
    # Whichever spelling comes FIRST carries the tooltip, so the long form
    # after a marked 'CMP' is plain text.
    m2 = W.TermMarker()
    assert '<abbr' not in m2.mark('<p>CMP</p>').split('</abbr>')[-1]


def _ul_mirror():
    """Melmetal Ultra's shape: two distinct cuts, one build clearing both.

    The numbers are the blob's (31 members, 17 and 25 beaten, 71/113/50
    members); the blob-backed pins below read the real thing.
    """
    mf = {'n_iv': 4096, 'atk_lo': 154.62, 'n_final': 31, 'tilt': 'bulk',
          'split': None,
          'cmp': [{'q': 0.5, 'T': 156.7899, 'line': 156.8712,
                   'line_printed': 156.87, 'line_dp': 2, 'n_beaten': 17,
                   'n_cohort': 31, 'n_grid_strict': 2891,
                   'n_grid_ties': 2996},
                  {'q': 0.75, 'T': 158.0302568, 'line': 158.0315,
                   'line_printed': 158.031, 'line_dp': 3, 'n_beaten': 25,
                   'n_cohort': 31, 'n_grid_strict': 2035,
                   'n_grid_ties': 2144}],
          'builds': [{'role': 'primary', 'size': 71, 'n_clear': [0, 0],
                      'atk_max': 150.0},
                     {'role': 'fork', 'size': 113, 'n_clear': [113, 113],
                      'atk_max': 162.0},
                     {'role': 'third', 'size': 50, 'n_clear': [0, 0],
                      'atk_max': 149.0}]}
    bl = {'builds': [{'role': 'primary'}, {'role': 'fork'},
                     {'role': 'third'}]}
    return mf, bl


def test_the_cut_is_printed_as_a_selector_not_as_a_strict_above():
    """``brief.printed_cut`` FLOORS, so ``atk >= line_printed`` selects
    exactly the spreads that beat the cohort quantile and the spread sitting
    exactly ON the printed number is one of them. "above 156.87" reads it out
    of the set the number was computed to select, so the paragraph says
    "156.87 and up".

    The dp comes from ``printed_cut`` too and is not re-rounded: Melmetal
    Ultra's 75th needs three places (158.031), and "158.03 and up" would take
    in the 109 spreads between 158.03 and 158.0302568 that lose priority.
    """
    mf, _bl = _ul_mirror()
    clause = W.mirror_cut_clause(mf)
    assert clause == ('attack of 156.87 and up wins charge-move priority '
                      'against 17 of them, and 158.031 and up against 25')
    assert 'above' not in clause
    assert '158.03 and up' not in clause


def test_the_build_clause_groups_and_leads_with_what_is_reachable():
    """Pre-cut (d66a78d) this was one clause per build in build order, inside
    the block: "Build 1 clears neither with any of its 71; Build 2 clears
    both with all 113 of its members; Build 3 clears neither with any of its
    50." The sentence that replaced the block leads with the build that
    CLEARS -- that is the half a reader choosing between them acts on -- and
    names builds that land in the same place together.
    """
    mf, bl = _ul_mirror()
    assert W.mirror_build_clause(mf, bl) == (
        'Build 2 clears both cuts with every one of its 113 members; '
        'Build 1 and Build 3 clear neither with any')
    # A build whose members SPLIT on a cut carries its own counts, so it is
    # never grouped with another.
    mf['builds'][0]['n_clear'] = [40, 12]
    assert W.mirror_build_clause(mf, bl) == (
        'Build 2 clears both cuts with every one of its 113 members; '
        'Build 1 clears the first cut with 40 of 71 and the second with 12; '
        'Build 3 clears neither with any of its 50')
    # One threshold (the two percentiles are one number) and the clause
    # speaks of one cut, not of "both" and "neither".
    mf['cmp'][1] = dict(mf['cmp'][0], q=0.75)
    mf['builds'][0]['n_clear'] = [0, 0]
    assert W.mirror_build_clause(mf, bl) == (
        'Build 2 clears it with every one of its 113 members; '
        'Build 1 and Build 3 clear it with none of theirs')


def test_the_closest_build_is_named_when_nothing_clears():
    """Melmetal Great and Azumarill: no spread in any build reaches the first
    cut. The clause names how far off the closest build is, because that is
    the only number left that a reader picking a build can act on. Pre-cut
    this sentence also carried the Azumarill-only clause that the builds top
    out below the cohort's own floor; the two-sentence version drops it (the
    number is still ``mf['atk_lo']``).
    """
    mf, bl = _ul_mirror()
    mf['builds'][1]['n_clear'] = [0, 0]
    mf['builds'][1]['atk_max'] = 124.12
    mf['builds'][0]['atk_max'] = 120.0
    mf['builds'][2]['atk_max'] = 119.0
    assert W.mirror_build_clause(mf, bl) == (
        'no build on this page holds a spread that clears the first cut; '
        'the closest is Build 2 at 124.12')


def test_the_cohort_tilt_never_claims_a_hundredth_percentile():
    """The parenthetical in sentence one. Pre-cut the block printed the tilt
    as a clause with the share behind it ("attack-first here: the median
    member's attack is higher than 99.6% of this grid and its stat product
    ranks 3366 of 4096"); the paragraph prints the label alone, so the
    share -- the number that used to read as "the 100th percentile" -- is not
    printed at all now.

    A split cohort is still named as SPLIT rather than by the lobe its median
    sits in: Shadow Sableye's median is above 99.6% of the grid while 12 of
    its 30 members are 13 points below it.
    """
    base = {'atk_pct': 99.5605, 'sp_rank_med': 3366, 'n_iv': 4096,
            'tilt': 'atk', 'split': None}
    assert W.mirror_tilt_label(base) == 'attack-first here'
    assert W.mirror_tilt_label(dict(base, tilt='bulk')) == 'bulk-first here'
    assert (W.mirror_tilt_label(dict(base, tilt=None))
            == 'neither attack-first nor bulk-first here')
    split = dict(base, split={'n_lo': 12, 'n_hi': 18, 'lo_lo': 1.0,
                              'lo_hi': 2.0, 'hi_lo': 3.0, 'hi_hi': 4.0})
    assert W.mirror_tilt_label(split) == 'split in two here'


def test_no_second_sentence_where_nothing_on_the_grid_clears_the_cohort():
    """Mimikyu Ultra: the cohort's 50th AND 75th attack percentiles are both
    161.34, which is the grid's own top attack, so there is no spread to
    name. Sentence one says that in words and sentence two is DROPPED -- "take
    the highest attack you have" followed by a clause saying it buys nothing
    is a rule with no consequence.

    Before the honesty pass in d66a78d this branch crashed formatting a
    threshold no spread is above; pre-cut it printed "nothing on this grid is
    above it" inside the block.
    """
    row = {'q': 0.5, 'T': 161.3376, 'line': None, 'line_printed': None,
           'line_dp': None, 'n_beaten': 35, 'n_cohort': 35,
           'n_grid_strict': 0, 'n_grid_ties': 251}
    mf = {'n_iv': 4096, 'atk_lo': 150.0, 'n_final': 35, 'tilt': 'atk',
          'split': None, 'cmp': [row, dict(row, q=0.75)],
          'builds': [{'role': 'primary', 'size': 50, 'n_clear': [0, 0],
                      'atk_max': 155.0}]}
    bl = {'builds': [{'role': 'primary'}]}
    facts = {'header': {'species': 'Mimikyu', 'shadow': False}}
    out = W.mirror_sentences(mf, bl, facts)
    assert out == ['Against the 35 spreads the mirror-slayer protocol '
                   'converges on for Mimikyu (attack-first here), no attack '
                   'on this grid wins charge-move priority against even half '
                   'of them.']
    assert '161.34' not in out[0] and 'None' not in out[0]
    # And the plot draws no trace for a threshold nothing reaches.
    one = {'mirror': {'flat': dict(mf, builds=[])}}
    assert builds_mod.mirror_payload(one) is None


# ---- the JS trace --------------------------------------------------------

def test_the_mirror_trace_is_one_masked_trace_drawn_under_the_marks():
    """A marker STYLE, not a line: attack is an axis on neither builds
    plane. strip_js blanks string literals, so this pins the structure --
    the mask read, the position helper, the legend default and the order --
    not the words in the legend key."""
    src = _engine()
    assert 'function _wbMirrorTrace(' in src
    body = src[src.index('function _wbMirrorTrace('):
               src.index('function _wbBuildMarks(')]
    # Membership comes off the packed mask, never off DATA.ivAtk (which is
    # rounded to 2 dp and would mis-side every spread in the window).
    assert '_wbMask(m.mask)' in body and '_wbBit(bits, i)' in body
    assert 'DATA.ivAtk' not in body
    # Plotted with the same position helper every other builds trace uses, so
    # it follows the plane switch instead of pinning itself to one view.
    assert '_wbXY(L, i, wins)' in body
    # Default OFF where the payload says no build reaches the threshold.
    # The Plotly value is a string literal, which strip_js blanks, so the
    # guard is pinned on the stripped source and the literal on the raw one.
    assert 'if (!m.on) t.visible =' in body
    raw = ENGINE_JS.read_text()
    raw_body = raw[raw.index('function _wbMirrorTrace('):
                   raw.index('function _wbBuildMarks(')]
    assert "t.visible = 'legendonly'" in raw_body
    assert "'triangle-up-open'" in raw
    # Called on BOTH builds planes, and pushed before the marked spreads so
    # it cannot cover them.
    box = src[src.index('function wbRenderBox('):]
    call = box.index('_wbMirrorTrace(pay, L, wins, colors, den)')
    marks = box.index('_wbBuildMarks(pay, pblock, L, wins, colors, den, scen,')
    assert call < marks
    # Which branch it sits in is spelled with string literals too, so that
    # half is read off the raw source.
    raw_box = raw[raw.index('function wbRenderBox('):]
    rcall = raw_box.index('_wbMirrorTrace(pay, L, wins, colors, den)')
    guard = raw_box.rindex("view === 'builds'", 0, rcall)
    assert "view === 'stats'" in raw_box[guard:rcall]
    # Positive control: the trace it is drawn under is still there, so a scan
    # that stopped finding either name fails here rather than passing empty.
    assert src.count('function _wbBuildMarks(') == 1


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_real_section_places_the_mirror_between_the_table_and_the_collection(
        shadow_sableye):
    """Reading order: builds table -> the mirror paragraph -> "Is mine in one
    of these?". It is a reading OF the table, so it sits with it.

    Pre-cut (d66a78d) this was a bordered ``<div class="wb-mirror">`` with a
    ``<p class="wb-mirror-head">The mirror</p>`` heading; the two sentences
    that replaced the block are one ``<p class="wb-mirror">`` per Build
    criteria setting, with no heading of their own.
    """
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    body = html[html.index('<div class="wb-body">'):]
    table = body.index('wb-builds-table')
    mirror = body.index('<p class="wb-mirror">')
    mine = body.index('wb-mine')
    assert table < mirror < mine
    assert 'wb-mirror-head' not in html and 'The mirror</p>' not in html
    # One paragraph per setting, in the section's own preset divs.
    assert html.count('<p class="wb-mirror">') == 3


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_real_section_mirror_paragraph_is_the_two_sentences(shadow_sableye):
    """The whole rendered mirror, verbatim, on the default setting.

    Pre-cut (d66a78d) this arm rendered, under a "The mirror" heading: the
    cohort sentence ("The mirror cohort is the 30 spreads the mirror-slayer
    protocol converges on for Sableye (Shadow) -- split in two here: the
    median member's attack is higher than 99.6% of this grid and its stat
    product ranks 3366 of 4096. Their attack runs 141.76 to 156.84, in two
    groups with nothing between them -- 12 between 141.76 and 143.91 and 18
    between 155.90 and 156.84. Every member of it was picked, over the
    protocol's rounds, for beating the others in the mirror, so it is the
    mirror you would face if the other side were optimising for the mirror
    too -- not a survey of what players build."), then per setting a
    seven-row table of the mirror decision cells, three CMP paragraphs and
    three cohort-rate paragraphs -- 6.8 KB of block for a finding that is two
    sentences long (TODO.md "NEXT BAKE: mirror population").

    The cohort is still named as what it IS -- the spreads the mirror-slayer
    protocol converges on, not a census of what players own -- which is the
    one thing a reader could be wrong about; 'mirror cohort' carries the rest
    in the glossary.
    """
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    raw = re.search(r'<p class="wb-mirror">(.*?)</p>', html, re.S).group(1)
    para = _html.unescape(re.sub(r'<[^>]+>', '', raw))
    assert para == (
        'Against the 30 spreads the mirror-slayer protocol converges on for '
        'Sableye (Shadow) (split in two here), attack of 156.29 and up wins '
        'charge-move priority against 21 of them, and 156.36 and up against '
        '24. Inside a build, take the highest attack you have: no build on '
        'this page holds a spread that clears the first cut; the closest is '
        'Build 1 at 151.25.')


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_real_section_mirror_drops_the_readings_it_still_computes(
        shadow_sableye):
    """The three readings the cut removed from the PAGE are still computed
    and still true of the blob: the per-scenario decision cells, the
    cohort-rate surface, and the Spearman between them. They are the
    population version's inputs (TODO.md "NEXT BAKE: mirror population"), so
    they must not be deleted -- and they must not be rendered either.

    Pre-cut the page carried all three: a row per decision cell ("1v1 Sableye
    (Shadow) | 48% | Build 1"), "the median member of Build 1 takes 33%,
    Build 2 takes 44%, against 33% over the whole grid", and "That surface
    barely tracks the matchups in the table above (Spearman +0.24 here)".
    """
    _state, all_facts, _path = shadow_sableye
    html = W.section_html(all_facts, 0)
    mf = next(iter(all_facts[0]['_builds']['mirror'].values()))
    # Computed: not one of them is empty or None on this blob.
    assert len(mf['cells']) == 7
    assert all(c['wr'] is not None for c in mf['cells'])
    assert mf['rate_med_grid'] is not None and mf['rate_max_grid'] is not None
    assert mf['spearman'] is not None
    assert any(r['rate_med'] is not None for r in mf['builds'])
    # Not rendered. The cells table had its own class and its own header row;
    # the other two are pinned on words nothing else on the page uses.
    assert 'wb-mirror-table' not in html
    assert 'Share of the grid that wins it' not in html
    assert 'Spearman' not in html
    # Not "over the whole grid" on its own: the flavor guide says "random IVs
    # over the whole grid" a few thousand characters up, and an absence pin
    # that matches another block's prose fails for the wrong reason.
    assert 'Across the cohort' not in html
    assert 'per-scenario or per-member breakdown' not in html
    # Positive control: a scan that stopped finding the paragraph would pass
    # every absence above, so the paragraph is asserted present here too.
    assert html.count('<p class="wb-mirror">') == 3
