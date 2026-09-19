"""The five DRY rules the v4 round-9 reorganization is held to.

Michael, 2026-09-19: "do some DRY thinking before implementing." Each rule
below is a thing that was duplicated in the round-8 code, and each test here
FAILED at 0ca9693 with the pre-fix value recorded in its own docstring, so a
regression puts the duplicate back and the test says which one.

Vocabulary (docs style rule, per document):

- Preset / Build criteria setting: one of the three shield weightings
  (``scripts/deep_dive_builds.PRESETS``). Reader text says "Build criteria
  setting"; the code keys them by preset key.
- Preset block: one ``<div class="wb-preset" data-preset=...>`` in the
  rendered section. Only the active one is visible; the other two ship
  hidden, so every byte inside one is paid for three times.
- strip_js: the tests' JS scrubber (``tests/test_win_boundary.strip_js``),
  which blanks comments, string literals and regex literals so a source scan
  cannot match a word that only appears inside a quoted sentence.
- Wire contract: the payload keys the section's inline JSON carries and the
  engine actually reads (``tests/test_js_wire_contract.py``).
"""
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
ENGINE_JS = SCRIPTS_DIR / 'deep_dive_engine.js'
SABLEYE_SHADOW = '20260911_005150_Sableye_great_shadow.replay.pkl.gz'

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_win_boundary import strip_js  # noqa: E402

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REPO_ROOT / 'src'))

import glossary  # noqa: E402
import deep_dive_which_build as W  # noqa: E402
import deep_dive_brief as B  # noqa: E402
import deep_dive_matchup_clusters as MC  # noqa: E402


def require_blob(name):
    for d in (REPO_ROOT / 'userdata' / 'replay',
              REPO_ROOT.parent / 'gopvpsim' / 'userdata' / 'replay'):
        if (d / name).exists():
            return d / name
    pytest.skip(f"{name} is not on this machine")


@pytest.fixture(scope='module')
def shadow_section():
    path = require_blob(SABLEYE_SHADOW)
    state = B.load_blob(str(path))
    all_facts = W.prepare(state, str(path))
    return W.section_html(all_facts, 0)


_TAGS = re.compile(r'<[^>]+>')


def _preset_blocks(html):
    """The rendered text of each ``data-preset`` block, keyed by preset.

    A preset that owns more than one block (the builds table and the notable
    list are two separate runs in the reading order) has them concatenated:
    the rule is about text a reader pays for three times, not about which
    ``<div>`` it sits in.
    """
    out = {}
    for m in re.finditer(r'<div class="wb-preset" data-preset="([^"]+)"', html):
        key = m.group(1)
        # Walk to the matching close by counting <div> depth from the tag.
        i = html.index('>', m.start()) + 1
        depth, j = 1, i
        while depth:
            nxt = re.search(r'<(/?)div\b', html[j:])
            if not nxt:
                break
            depth += -1 if nxt.group(1) else 1
            j += nxt.end()
        out.setdefault(key, []).append(_TAGS.sub(' ', html[i:j]))
    return {k: ' '.join(v) for k, v in out.items()}


D1_WINDOW = 121


def _fragments(text, n=D1_WINDOW):
    """Every whitespace-normalized n-character window of ``text``, step 1.

    Windows rather than sentences, and every offset rather than a stride: a
    paragraph that differs only in its first clause still costs three copies
    of its tail, and an aligned stride would miss it because the three blocks
    do not start at the same length.
    """
    flat = ' '.join(text.split())
    return {flat[i:i + n] for i in range(max(0, len(flat) - n) + 1)}


# ---------------------------------------------------------------------------
# D1. Preset-invariant text renders ONCE
# ---------------------------------------------------------------------------

# Shared 121-character windows between all three preset blocks, measured at
# 0ca9693 on the Shadow Sableye section: 3,555. Almost all of it is authored
# prose paid for three times (the emphasis key, the notable-list intro, the
# rocket-grunt sentence, the near-free sentences, the fixed note's definition
# -- about 5.5 KB). What is left after the split is table DATA that happens
# to coincide between presets (a family's staircase steps are the same
# numbers under every Build criteria setting), which is a real per-preset
# render rather than a duplicated string, so the rule below is a ceiling and
# the authored-text rule is the one stated exactly.
D1_ROUND8_SHARED_WINDOWS = 3555
# Round 9 as shipped: 1,186 (the round-10 reviewer's independent split, which
# unescapes HTML and strips <script>, measured 1,176 -- same direction, same
# magnitude). MOST of that is FAMILY-ROW DATA -- the same rule, the same
# staircase steps and the same two counts, because a family is grown around a
# standout and does not move with the Build criteria setting -- which is a
# per-preset render of identical data rather than a duplicated string. But
# three of the ten maximal shared runs were authored template prose still
# inside the preset loop, and the round-10 reviewer named them: the lead's
# "decision matchups (a top-50 opponent and shield state ...)" parenthetical,
# the family sentence, and the notable entry's "that is a family (not a
# build) ... No other spread on this grid wins all 62 ..." run. Round 10
# retired the first with the lead itself; the other two are family/notable
# DATA sentences whose wording happens to coincide. So this stays a ceiling
# with headroom, and the exact rules above are the ones stated exactly.
D1_SHARED_WINDOW_CEILING = 1500


def _authored_constants(mod, n=120):
    """Module-level string constants long enough to be a paragraph.

    A format string is matched on its literal head (up to the first ``{``),
    because that is what reaches the page verbatim.
    """
    out = {}
    for name in dir(mod):
        if not name.isupper():
            continue
        val = getattr(mod, name)
        if not isinstance(val, str):
            continue
        head = val.split('{', 1)[0]
        if len(head) >= n:
            out[name] = head[:n]
    return out


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_d1_no_authored_paragraph_is_rendered_more_than_once(shadow_section):
    """Preset-invariant authored text renders ONCE.

    Pre-fix (0ca9693) these were each rendered three times, once per hidden
    preset block: ``EMPH_KEY``, ``NOTABLE_LEAD``, ``STANDOUT_NOTE``,
    ``GUARANTEE_SORT_KEY``, ``WEIGHTING_NOTE``'s neighbours and the
    rocket-grunt sentence -- about 5.5 KB of byte-identical bytes.
    """
    text = ' '.join(_TAGS.sub(' ', shadow_section).split())
    import html as _h
    text = _h.unescape(text)
    offenders = {}
    for name, head in _authored_constants(W).items():
        flat = ' '.join(head.split())
        n = text.count(flat)
        if n > 1:
            offenders[name] = n
    assert not offenders, offenders


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_d1_no_rendered_paragraph_is_repeated_verbatim(shadow_section):
    """No ``<p>`` in the section prints twice.

    The constants test above only sees module-level UPPERCASE strings, so it
    missed the two sentences the round-9 reorganization itself built inside
    the preset loop and shipped three times each: the single-stat-line
    sentence ("Single-stat line: Attack >= 148.10 decides 0v1 Annihilape.
    SP1 is 6.34 short." -- 3 copies) and the species/moveset opening of the
    verdict lead ("Sableye (Shadow) running Shadow Claw / Drain Punch, Foul
    Play." -- 3 copies). Pre-fix (9cb2b26) this test found both.
    """
    import collections
    import html as _h
    paras = [' '.join(_h.unescape(_TAGS.sub(' ', m)).split())
             for m in re.findall(r'<p\b[^>]*>.*?</p>', shadow_section, re.S)]
    counts = collections.Counter(q for q in paras if len(q) >= 60)
    dupes = {q[:90]: n for q, n in counts.items() if n > 1}
    # The two TEMPLATE sentences render exactly once now. The residue is
    # FOUR data paragraphs a family row and a notable entry build per
    # setting: the two "The region grown around 7/2/14 / 9/6/13 until 50
    # spreads guarantee every matchup left in it..." sentences, "No other
    # spread on this grid wins all 62 of the decision matchups it wins." and
    # "9/6/13 (Highest avg battle score) differs from it by 6 decision
    # matchups...". They coincide because a family is grown around a
    # standout and does not move with the Build criteria setting, so each is
    # a real per-setting render of identical data. Hoisting them would mean
    # lifting per-family rows out of a per-setting table, so this is a named
    # ceiling rather than zero. Pre-fix (9cb2b26): SIX -- these four plus
    # the line-status sentence and the lead's species/moveset opening, which
    # ARE templates and now render once.
    assert len(dupes) <= 4, dupes
    assert all(n == 3 for n in dupes.values()), dupes
    assert shadow_section.count('class="wb-linestatus"') == 1
    assert shadow_section.count('class="wb-who"') == 1
    # positive control: the sentence that CAN differ by setting still has one
    # copy per Build criteria setting.
    assert shadow_section.count('class="wb-answer-line"') >= 3


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_d1_shared_text_between_preset_blocks_is_under_the_ceiling(
        shadow_section):
    """The blunt measure behind the rule above, as a ceiling.

    Pre-fix: 3,555 shared 121-character windows between all three blocks;
    1,186 after the split, all of them family-row data.
    """
    blocks = _preset_blocks(shadow_section)
    assert len(blocks) >= 3, f"expected 3 preset blocks, got {list(blocks)}"
    sets = [_fragments(t) for t in blocks.values()]
    shared = set.intersection(*sets)
    assert len(shared) < D1_SHARED_WINDOW_CEILING, (
        f"{len(shared)} shared windows (round 8: "
        f"{D1_ROUND8_SHARED_WINDOWS}); first: {sorted(shared)[0]!r}")


# ---------------------------------------------------------------------------
# D2. One of each
# ---------------------------------------------------------------------------

def _js():
    return strip_js(ENGINE_JS.read_text(encoding='utf-8'))


def _defs(js):
    """(name, body) for every top-level ``function name(...)`` in the file."""
    out = []
    for m in re.finditer(r'^function (\w+)\(', js, re.M):
        nxt = re.search(r'^function \w+\(', js[m.end():], re.M)
        body = js[m.start():m.end() + (nxt.start() if nxt else len(js))]
        out.append((m.group(1), body))
    return out


def test_d2_one_mini_grid_builder():
    """One function draws a nine-mini shield-scenario grid, not two.

    Pre-fix (0ca9693): TWO -- ``renderAllScenarios`` (the Matchup clusters
    section's grid) and ``_wbAllScen`` (this section's), both looping the
    baked scenarios and calling Plotly.newPlot per scenario, on the same x
    axis, one directly above the other on the page.
    """
    hits = [n for n, body in _defs(_js())
            if re.search(r'for \(var \w+ = 0; \w+ < (?:nS|DATA\.nScenarios)',
                         body) and 'Plotly.newPlot' in body]
    assert hits == ['_wbAllScen'], hits


def test_d2_one_view_dispatcher():
    """One function reads the section's view control and re-renders.

    Pre-fix: the section's Show ``<select>`` (``wbSelectView``) and the
    clusters section's own checkbox path (``toggleAllScenarios``) were two
    entry points into two different figures. After the merge every view of
    this section's figure goes through ``wbSelectView``.
    """
    js = _js()
    assert 'function toggleAllScenarios(' not in js
    dispatchers = [n for n, _b in _defs(js)
                   if n in ('wbSelectView', 'toggleAllScenarios')]
    assert dispatchers == ['wbSelectView'], dispatchers


def test_d2_one_preset_setter():
    """One SETTER behind both Build criteria handles.

    "Setter" is mechanical here: the function that both writes the select's
    value and persists the choice in the URL hash. ``wbApplyPresetHash`` also
    assigns the select, but it is the load-time reader of that same hash and
    writes none, so the rule is stated against the writer.

    Pre-fix there was one handle and one setter; the reorganization adds a
    second handle (the section's mirror) and this pins that it did not bring
    a second setter with it.
    """
    hits = [n for n, body in _defs(_js())
            if 'WB_PRESET_SEL' in body and '_wbWriteHash(' in body
            and re.search(r'\bsel\.value\s*=[^=]', body)]
    assert hits == ['wbSetPreset'], hits
    # ...and both handles are wired to it, in Python, by the same string.
    import deep_dive as DD
    strip = DD._build_criteria_select(['flat'])
    mirror = W.criteria_mirror_html(['flat'])
    assert 'onchange="wbSetPreset(this.value)"' in strip
    assert 'onchange="wbSetPreset(this.value)"' in mirror


def test_d2_one_collection_loader_and_one_manual_parser():
    """One CSV loader and one manual-entry parser serve both entry points."""
    js = _js()
    assert len(re.findall(r'^function loadCollection\(', js, re.M)) == 1
    # ``== 1``, not ``<= 1``: the round-9 form passed at zero, which is an
    # absence pin with no positive control (2026-09-19 round-10 review).
    assert len(re.findall(r'^function readManualForm\(', js, re.M)) == 1
    # ...and the section's entry point reaches that one form rather than
    # shipping a second paste box of its own.
    assert 'function wbOpenCollection(' in js


def test_d2_one_scenario_setter():
    """One function puts a shield scenario on every handle in the section.

    Pre-fix (9cb2b26) there were FOUR unlinked "Shield scenario:" selects
    inside one section -- the figure box's, expander F's, expander G's and
    the clusters subsection's own ``select.dd-mc-scen`` -- and
    ``wbSelectView`` re-rendered only the ``.wb-plotbox`` that owned the
    changed one, so narrowing the figure to 1v1 left the other three on
    "all" with no signal.
    """
    # The SELECTOR is a string literal, which strip_js blanks, so the scan
    # for it reads the raw source and the value-write is checked on the
    # stripped one.
    raw = ENGINE_JS.read_text(encoding='utf-8')
    js = _js()
    setters = [n for n, body in _defs(raw)
               if "querySelectorAll('select.wb-scen')" in body]
    assert setters == ['_wbSyncScen'], setters
    body = js.split('function _wbSyncScen(', 1)[1].split('\nfunction ', 1)[0]
    assert re.search(r'\.value\s*=[^=]', body), body
    # ...and the clusters subsection follows it rather than a select of its
    # own. Positive control: the block markup it switches is still emitted.
    MC_src = (SCRIPTS_DIR / 'deep_dive_matchup_clusters.py').read_text()
    assert 'class="dd-mc-scen"' not in MC_src
    assert 'dd-mc-scen-block' in MC_src
    assert 'function mcSelectScenario(' not in js
    assert 'function mcSetScenario(' in js


def test_d2_one_row_expander_builder():
    """One Python helper builds a build's row expander.

    Pre-fix: ``builds_table_html`` built the table rows in one loop and a
    SECOND loop under the table built a standalone ``<details class="wb-build">``
    per build. After the merge the expander is a row of the table, built once.
    """
    src = (SCRIPTS_DIR / 'deep_dive_which_build.py').read_text()
    assert src.count('def build_row_expander') == 1
    assert '<details class="wb-build"' not in src


def test_d2_one_glossary_source():
    """Every first-use definition and the Terms block come from glossary.py.

    Scans the two renderers for a literal copy of any registry sentence --
    the same rule ``test_no_second_definition_in_renderer`` enforces, widened
    to the clusters renderer now that its content lives in this section.
    """
    for path in (SCRIPTS_DIR / 'deep_dive_which_build.py',
                 SCRIPTS_DIR / 'deep_dive_matchup_clusters.py'):
        src = path.read_text()
        for term, sentence in glossary.TERMS.items():
            assert sentence not in src, (path.name, term)
    # ...and the section's own first-use definitions are registry lookups,
    # not typed sentences: every term the section marks resolves.
    for term, _pattern in W._TERM_PATTERNS:
        assert glossary.definition(term), term


# ---------------------------------------------------------------------------
# D3. Delete what is replaced
# ---------------------------------------------------------------------------

def test_d3_the_replaced_python_symbols_are_gone():
    """The v3/round-8 blocks the reorganization replaces are deleted.

    Pre-fix these all existed: ``build_paragraphs_html`` (three per-build
    paragraphs duplicating the table row for row), ``build_paragraph``,
    ``wide_paragraph``, and the clusters section's own ``_allscen_figure``.
    """
    W_src = (SCRIPTS_DIR / 'deep_dive_which_build.py').read_text()
    for name in ('build_paragraphs_html', 'build_paragraph', 'wide_paragraph'):
        assert f'def {name}(' not in W_src, name
        assert not hasattr(W, name), name
    assert not hasattr(MC, '_allscen_figure')
    # positive control: the renderers they were part of are still here
    assert hasattr(W, 'builds_table_html')
    assert hasattr(W, 'notable_html')
    assert hasattr(MC, 'render_section')


def test_d3_the_replaced_markup_is_gone():
    """The Show select, the all-scenarios checkbox and the clusters
    section's own ``<details>`` no longer reach the page.

    Pre-fix: ``select class="wb-view"`` (six entries), ``wb-allscen-chk``,
    ``id="allscen-toggle"``, ``id="allscen-grid"`` and
    ``id="dd-matchup-clusters-section"`` were all emitted.
    """
    W_src = (SCRIPTS_DIR / 'deep_dive_which_build.py').read_text()
    MC_src = (SCRIPTS_DIR / 'deep_dive_matchup_clusters.py').read_text()
    assert 'select class="wb-view"' not in W_src
    assert 'wb-allscen-chk' not in W_src
    assert 'id="allscen-toggle"' not in MC_src
    assert 'id="allscen-grid"' not in MC_src
    assert 'dd-mc-collapse' not in MC_src
    # positive controls: what REPLACED them is emitted
    assert 'wb-tab' in W_src                       # the tabbed figure
    assert 'wb-allscen-grid' in W_src              # the one merged grid
    assert 'dd-mc-root' in MC_src                  # the clusters body survives


def test_d3_the_clusters_section_is_a_subsection_now():
    """The clusters content ships inside this section's own expander.

    Pre-fix ``_section_open`` opened with ``<details class="dd-collapsible
    dd-mc-collapse" id="dd-matchup-clusters-section">``; now it opens the
    plain body div, and the section renderer carries the slot the page fills.
    """
    assert MC._section_open(9).startswith('<div class="dd-section dd-mc-root"')
    assert '<details' not in MC._section_open(9)
    W_src = (SCRIPTS_DIR / 'deep_dive_which_build.py').read_text()
    assert 'MATCHUP_CLUSTERS_SLOT' in W_src


# ---------------------------------------------------------------------------
# D4. Byte budget
# ---------------------------------------------------------------------------

# What this measures, exactly: the bytes ``section_html`` AUTHORS, from
# ``<details class="wb-root">`` on. It excludes the ``<style>`` prelude the
# page hoists (11,580 bytes at 0ca9693) and it excludes the Matchup clusters
# body, which reaches the page through a slot marker
# (``deep_dive.generate_interactive_html`` fills it) rather than through this
# renderer.
#
# Round 8, same measurement on the same page and arm: 178,751 bytes, with the
# Matchup clusters section's live copy a further 245,472 beside it. Round 9
# as shipped: 184,376 -- under the 185,000 cap and far under the two round-8
# blocks together, but 5,625 bytes MORE than round 8's section alone. That is
# the honest number: the reorganization deletes three per-build paragraphs,
# one of the two nine-mini grids, the duplicated emphasis keys and the
# duplicated view captions, and it adds the mirror control, the line-status
# sentence, the collection block, three tab strips, three plot boxes, the
# per-row steps tables and six new glossary entries (each printed twice, as
# a hover and as a Terms row). The net is +3.1%.
#
# At PAGE level the merged <details> on the shadow preview is 668,057 bytes,
# because best-buddy is active there and the clusters body ships twice (a
# live host plus an inert <template>) -- exactly as it did in round 8, when
# the same two copies sat in a sibling section.
D4_ROUND8_PAGE_SECTION_BYTES = 178_751
D4_ROUND8_CLUSTERS_BYTES = 245_472
D4_CEILING = 185_000


def _section_bytes(html):
    """The section as the PAGE carries it: from ``<details class="wb-root">``.

    ``section_html`` prefixes a ``<style>`` block that the page hoists; the
    round-8 figure this is measured against was taken on the rendered page
    and so excludes it. Measured the same way here or the comparison is not
    one.
    """
    return len(html[html.index('<details class="wb-root"'):].encode('utf-8'))


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_d4_the_merged_section_fits_the_budget(shadow_section):
    """The section's OWN bytes (the clusters subsection is slotted in later).

    ``section_html`` emits the clusters content as a one-line slot marker
    that ``deep_dive.generate_interactive_html`` fills, so what this measures
    is everything the reorganization actually authors.

    Round 8: 178,751 bytes. Round 9: 184,376 (+3.1%). Round 10: 177,815 --
    below round 8's section ALONE, against the 424,223 the two round-8
    blocks took between them.
    """
    # One assertion, because there is one question. The round-9 second line
    # compared two module constants summing to 424,223 against a measured
    # value already capped at 185,000, so it could never fail while the cap
    # held (2026-09-19 round-10 review).
    n = _section_bytes(shadow_section)
    assert n < D4_CEILING, (
        f"section is {n:,} bytes (ceiling {D4_CEILING:,}; round 8 "
        f"{D4_ROUND8_PAGE_SECTION_BYTES:,} + clusters "
        f"{D4_ROUND8_CLUSTERS_BYTES:,})")


# ---------------------------------------------------------------------------
# D5. No new payload keys unless the JS reads them
# ---------------------------------------------------------------------------

# The three payload keys the engine did NOT read at 0ca9693: ``T`` (the
# full-precision threshold, carried for the masks' own documentation), and
# ``band`` / ``nAbove``, both read by Python before the payload is built. They
# are grandfathered; anything ADDED has to have a reader.
D5_UNREAD_AT_ROUND8 = frozenset({'T', 'band', 'nAbove'})


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_d5_every_payload_key_added_is_read_by_the_engine(shadow_section):
    """Every top-level payload key outside the grandfathered three has a
    reader in ``deep_dive_engine.js``.

    The wire-contract test owns the detailed direction; this is the cheap
    both-ways pin that a key added by the reorganization is not dead weight
    in every one of the page's embedded sections.
    """
    import json
    blob = shadow_section.split('class="wb-data">', 1)[1].split('</script>', 1)[0]
    pay = json.loads(blob.replace('\\u003c', '<'))
    js = _js()
    for key in pay:
        if key in D5_UNREAD_AT_ROUND8:
            continue
        k = re.escape(key)
        assert re.search(r'\.' + k + r'\b|\[[\'"]' + k + r'[\'"]\]', js), key
    # positive control: the grandfathered set is still exactly unread, so a
    # key that GAINS a reader has to leave the list rather than hide in it.
    still = {k for k in D5_UNREAD_AT_ROUND8 if k in pay
             and not re.search(r'\.' + re.escape(k) + r'\b', js)}
    assert still == set(D5_UNREAD_AT_ROUND8 & set(pay)), still
