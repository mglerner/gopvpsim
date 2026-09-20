"""The 2026-09-19 round-10 review's findings, pinned.

Two independent reviews read the round-9 section (9cb2b26) -- a
numbers/JS/DOM/DRY lens and a scientific-communication lens. Every test here
FAILED at 9cb2b26 with the pre-fix value recorded in its own docstring, per
the project's testing policy.

Vocabulary (docs style rule, per document):

- Build criteria setting: one of the three shield weightings
  (``scripts/deep_dive_builds.PRESETS``). Reader text never says "preset".
- Decision matchup: a (shield scenario, opponent) pair the IV choice decides.
- Wide region: the looser rule drawn around the primary build; it holds every
  spread the build holds and more, so it guarantees less.
- Family: a region grown greedily around one standout spread; it takes no
  column in the set panel and no card, and it is not a build.
- SP1: stat-product rank-1, the spread with the largest attack x defense x HP
  at the league's CP cap.
- strip_js: the tests' JS scrubber (``tests/test_win_boundary.strip_js``),
  which blanks comments, string and regex literals.
"""
import html as _html
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
ENGINE_JS = SCRIPTS_DIR / 'deep_dive_engine.js'
SABLEYE_SHADOW = '20260911_005150_Sableye_great_shadow.replay.pkl.gz'
MELMETAL_GREAT = '20260910_190103_Melmetal_great.replay.pkl.gz'

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_win_boundary import strip_js  # noqa: E402

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REPO_ROOT / 'src'))

import glossary  # noqa: E402
import deep_dive_which_build as W  # noqa: E402
import deep_dive_brief as B  # noqa: E402
import deep_dive_builds as BL  # noqa: E402

_TAGS = re.compile(r'<[^>]+>')


def require_blob(name):
    for d in (REPO_ROOT / 'userdata' / 'replay',
              REPO_ROOT.parent / 'gopvpsim' / 'userdata' / 'replay'):
        if (d / name).exists():
            return d / name
    pytest.skip(f"{name} is not on this machine")


def _load(name):
    path = require_blob(name)
    state = B.load_blob(str(path))
    return W.prepare(state, str(path))


@pytest.fixture(scope='module')
def shadow_facts():
    return _load(SABLEYE_SHADOW)


@pytest.fixture(scope='module')
def shadow_section(shadow_facts):
    return W.section_html(shadow_facts, 0)


@pytest.fixture(scope='module')
def melmetal_facts():
    return _load(MELMETAL_GREAT)


def _text(html):
    return ' '.join(_html.unescape(_TAGS.sub(' ', html)).split())


# ---------------------------------------------------------------------------
# Major 1 (numbers lens): the wide region's "Gives up" cell
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_wide_row_never_claims_it_gives_up_nothing(shadow_facts):
    """A region that guarantees LESS than a build on the same table gives
    something up, and the cell says what.

    Pre-fix (9cb2b26): ``run_preset`` called ``region_block`` for the wide
    with ``others=[]``, so ``gives_up`` was empty BY CONSTRUCTION on every
    page and ``_gives_up_text`` turned "not computed" into the positive
    claim "nothing the other builds guarantee" -- one line above the row's
    own expander, which said "The 12 it gives up out here: 1v2 Feraligatr
    (grid 11%), ...". Measured on this blob: wide guarantees 43, Build 1
    guarantees 55, and the wide's guaranteed cells are a strict subset.
    """
    ab = shadow_facts[0]['_builds']
    for key, bl in ab['presets'].items():
        wide = bl.get('wide')
        if not wide or not bl['builds']:
            continue
        prim = bl['builds'][0]
        if wide['n_guaranteed'] >= prim['n_guaranteed']:
            continue
        cell = W._gives_up_text(wide)
        assert cell != 'nothing the other builds guarantee', (key, cell)
        assert cell.startswith(str(len(wide['gives_up'])) + ':'), (key, cell)
    # The shadow page's own numbers, so a re-derivation that changes them
    # fails here rather than silently.
    bl = ab['presets'][BL.PRESET_FLAT]
    assert bl['builds'][0]['n_guaranteed'] == 55
    assert bl['wide']['n_guaranteed'] == 43
    assert len(bl['wide']['gives_up']) > 0


# ---------------------------------------------------------------------------
# Major 2 (both lenses): one shortfall, one number
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_strip_and_the_v3_strip_print_the_same_shortfall(shadow_facts):
    """The answer strip's SP1 gap is the number expander F prints.

    Pre-fix: the strip said "SP1 is 6.34 short" and expander F's five-row
    strip said "6.35 attack short", because ``_sp1_gap`` subtracted from the
    2-dp value the headline SPEAKS (148.10) while ``stage11_rank1`` subtracts
    from the full-precision threshold (148.1039982).
    """
    facts = shadow_facts[0]
    gap = W._sp1_gap(facts)
    assert gap is not None
    assert B.fmt(gap) == B.fmt(facts['rank1']['shortfall'])
    sentence = W.line_status_sentence(facts)
    assert f"SP1 is {B.fmt(facts['rank1']['shortfall'])} short." in sentence, \
        sentence
    # pre-fix value, recorded: the sentence said 6.34 and the strip 6.35.
    assert '6.34' not in sentence, sentence


# ---------------------------------------------------------------------------
# Major (scicomm 1): the strip carries the verdict, and it is ONE string
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_verdict_sentence_is_one_string_in_two_places(shadow_facts,
                                                          shadow_section):
    """The collapsed summary and the strip's second sentence are the same
    sentence, and it names a build and its rule.

    Pre-fix: the strip carried a PREAMBLE ("2 builds ranked on what they
    guarantee in all 9 shield scenarios, out of 87 decision matchups (...),
    and SP1 is in Build 2") and the only prose statement of the answer was
    the collapsed line -- 71 words, with a staircase spelled as a range
    ("Def >= 97.15-99.63 depending on HP (119-122; 4 steps, in the table)").
    """
    facts = shadow_facts[0]
    ab = facts['_builds']
    verdict = W.builds_summary(facts, ab, BL.PRESET_FLAT, shadow_facts)
    # It IS the verdict: a build, its size, its rule, what it guarantees.
    assert 'Build 1' in verdict and 'guarantees' in verdict
    assert W.rule_cell(ab['presets'][BL.PRESET_FLAT]['builds'][0],
                       facts) in verdict
    # Both guarantee numbers, in the one place the two-number rule had not
    # reached (pre-fix: "guarantees 55 of 87 decision matchups;" and no 38).
    assert 'under every opponent-IV mode' in verdict, verdict
    # The staircase is not spelled as a range here any more.
    assert 'depending on HP' not in verdict, verdict
    # Shorter than the 71-word round-9 line.
    assert len(verdict.split()) <= 55, (len(verdict.split()), verdict)
    # ...and the same string reaches both surfaces.
    flat = _text(shadow_section)
    assert verdict in flat, verdict
    assert flat.count(verdict) >= 2, flat.count(verdict)


# ---------------------------------------------------------------------------
# Major (scicomm 3): the family rows say "family" once and explain themselves
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
@pytest.mark.slow
def test_family_rows_name_the_word_once_and_say_why_57_beats_55(
        shadow_section):
    """Pre-fix the name cell read "Family around 7/2/14 -- family (not a
    build)" and the (--) hover explained only the missing robustness count,
    never why a region guaranteeing 57 is not the answer beside a build
    guaranteeing 55.
    """
    rows = re.findall(r'<tr data-family="\d+">.*?</tr>', shadow_section, re.S)
    assert rows, 'no family rows on this page'
    for row in rows:
        name_cell = row.split('</td>', 1)[0]
        assert _text(name_cell).lower().count('family') == 1, _text(name_cell)
        assert '(not a build)' in _text(name_cell), _text(name_cell)
    assert 'not comparable with a build' in W.FAMILY_GUARANTEE_HOVER
    import html as _h
    assert _h.escape(W.FAMILY_GUARANTEE_HOVER, quote=True) in shadow_section


# ---------------------------------------------------------------------------
# Major (scicomm 4): the advice call-out follows the page's line status
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_advice_callout_does_not_point_at_a_line_that_is_not_there(
        melmetal_facts, shadow_facts):
    """On a no-line page whose SP1 already wins the most, the call-out says
    so; it never points at a single-stat line the strip says does not exist.

    Pre-fix (9cb2b26) the call-out was a fixed string and Melmetal GL --
    whose strip says "No single-stat line on this moveset." and whose
    summary says "Your stat-product rank-1 (SP1): it already wins more
    matchups than any other spread" -- read "If you are hunting, hunt a
    build instead -- see the single-stat line for what changes the score."
    """
    mel = melmetal_facts[0]
    assert mel['floor'] is None, 'this blob is supposed to have no line'
    assert W.sp1_wins_most(mel)
    advice = W.notable_advice(mel)
    assert advice == W.NOTABLE_ADVICE_SP1
    assert 'single-stat line' not in advice, advice
    # ...and it agrees with the collapsed summary, which asks the same
    # predicate.
    assert 'already wins more' in W.summary_sentence(mel, melmetal_facts)
    # positive control: a page WITH a line keeps the pointer.
    assert W.notable_advice(shadow_facts[0]) is W.NOTABLE_ADVICE
    assert 'single-stat line' in W.NOTABLE_ADVICE


# ---------------------------------------------------------------------------
# Major (scicomm 5): one Shield scenario control per section
# ---------------------------------------------------------------------------

@pytest.mark.render
def test_the_section_has_one_scenario_control_and_it_drives_everything():
    """Pre-fix: FOUR "Shield scenario:" selects inside one section, three
    ``select.wb-scen`` (the figure, expander F, expander G) plus the clusters
    subsection's own ``select.dd-mc-scen`` with a different option list, and
    nothing synced them.
    """
    raw = ENGINE_JS.read_text(encoding='utf-8')
    js = strip_js(raw)
    assert 'function _wbSyncScen(' in js
    assert 'function mcSelectScenario(' not in js
    # the selector it writes is a STRING literal, which strip_js blanks, so
    # this half is read off the raw source.
    raw_body = raw.split('function _wbSyncScen(', 1)[1].split('\nfunction ', 1)[0]
    assert "select.wb-scen" in raw_body
    body = js.split('function _wbSyncScen(', 1)[1].split('\nfunction ', 1)[0]
    assert 'mcSetScenario(' in body
    # the dispatcher routes a wb-scen change to the setter and redraws the
    # whole root, not just the box that owns the changed select.
    disp = js.split('function wbSelectView(', 1)[1].split('\nfunction ', 1)[0]
    assert '_wbSyncScen(' in disp
    assert 'wbRenderRoot(root)' in disp


# ---------------------------------------------------------------------------
# Major (scicomm 6): one vocabulary inside the section
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_clusters_subsection_speaks_the_sections_vocabulary(
        shadow_section):
    """Pre-fix: the clusters body used "marginal" 49 times on the shadow
    page -- an undefined near-synonym of the table's "decision matchup" and
    the expander lead's "contested matchups" -- and one "preset" survived in
    reader text ("This is the Build criteria preset's own combined
    partition").
    """
    import deep_dive_matchup_clusters as MC
    src = (SCRIPTS_DIR / 'deep_dive_matchup_clusters.py').read_text()
    # reader-facing strings only: identifiers and docstrings may keep the
    # module's internal name for the concept.
    reader = [m for m in re.findall(r"'([^'\n]{12,})'|\"([^\"\n]{12,})\"", src)]
    flat = [a or b for a, b in reader]
    bad = [t for t in flat
           if re.search(r'\bmarginals?\b', t) and '<' in t or
           (re.search(r'\bmarginal\b', t) and t.strip().startswith(('<', 'Per ')))]
    assert not bad, bad
    assert "Build criteria preset's" not in src
    # the section's lead is the ONE sentence that opens the expander
    assert 'contested matchups' in W.WHY_REGIONS_LEAD
    assert MC.SECTION_SUMMARY_BASE.endswith('contested matchups they win')
    # the round-8 intro paragraphs are gone from the body
    assert 'instead of by average score' not in src
    assert 'often the sharpest partition on the page' not in src


# ---------------------------------------------------------------------------
# Major (scicomm 8) + minors: hovers, headers, gating
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_two_columns_that_introduce_a_term_carry_its_definition(
        shadow_section):
    """"opponent-IV mode" and "outside N%" are both first used in the table.

    Pre-fix: only "Gives up" had a header hover; "opponent-IV mode" appeared
    in every Guarantees cell and was defined nowhere on the page (not in the
    Terms block either), and "outside N%" was defined by the Rates key
    printed BELOW the table.
    """
    assert glossary.definition('opponent-IV mode')   # lookup is case-folded
    import html as _h
    assert W.RAREST_HOVER == glossary.definition('outside rate')
    assert _h.escape(W.RAREST_HOVER, quote=True) in shadow_section
    assert 'Rarest win' in shadow_section
    # the Terms block prints the new entry, from the registry
    assert glossary.TERMS['opponent-iv mode'] in shadow_section
    # UpSet is a proper name in the printed form (pre-fix: "upset plot")
    assert glossary.DISPLAY['upset plot'] == 'UpSet plot'


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_weighting_note_prints_only_where_its_clause_fires(
        shadow_section):
    """Pre-fix the 60-word weighting note was a paragraph under the table on
    EVERY Build criteria setting, including All shields, equal -- where the
    "every count is printed twice" clause it explains never applies.
    """
    import html as _h
    esc = _h.escape(W.WEIGHTING_NOTE, quote=True)
    assert 'class="wb-weighting"' not in shadow_section
    assert esc in shadow_section                       # as a header hover
    # once per narrow setting (2 of 3), never under the flat one, and never
    # as reader text (it is a title= attribute now).
    assert _text(shadow_section).count(W.WEIGHTING_NOTE) == 0
    assert shadow_section.count(esc) == 2, shadow_section.count(esc)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_row_expander_summary_only_promises_steps_it_has(shadow_section):
    """Pre-fix every build row's summary said "its steps" -- including the
    bulk-box row, which has none ("What Build 2 guarantees (41 of 87), its
    steps and its 114 members").
    """
    summaries = [s for s in
                 re.findall(r'<summary>What [^<]*</summary>', shadow_section)
                 if 'guarantees' in s]
    assert summaries
    for summ in summaries:
        if 'its steps' in summ:
            continue
        assert 'members' in summ and ', its steps' not in summ, summ
    # positive control: the staircase row still says it
    assert 'its steps and' in shadow_section
    # the exact-fit fidelity is a sentence, not an orphan fragment
    assert 'exactly these spreads<' not in shadow_section
    assert 'The rule fits exactly:' in shadow_section


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_the_moved_content_does_not_point_at_where_it_used_to_be(
        shadow_section):
    """Pre-fix, six sentences still named places the reorganization emptied:
    the figure note said "the view the line above was derived on" (the line
    is now BELOW, in expander F), the Rates key said "the Standouts block",
    and the family rows said "the figure's set panel" (the set panel is in
    expander G).
    """
    flat = _text(shadow_section)
    assert 'the line above was derived on' not in flat
    assert 'the single-stat line in the expander below' in flat
    assert 'the Standouts block' not in flat
    assert 'the Notable spreads list' in flat
    assert "the figure's set panel" not in flat
    assert 'the set panel under Why these regions' in flat


@pytest.mark.render
def test_the_collection_round_trip_comes_back():
    """Pre-fix ``wbOpenCollection`` scrolled the reader to the page's panel
    and nothing brought them back to ".wb-yours", which is where the answer
    renders.
    """
    js = strip_js(ENGINE_JS.read_text(encoding='utf-8'))
    assert 'function wbReturnFromCollection(' in js
    body = js.split('function wbRefresh(', 1)[1].split('\nfunction ', 1)[0]
    assert 'wbReturnFromCollection()' in body
    # still ONE loader and ONE manual form (DRY rule D2)
    assert len(re.findall(r'^function loadCollection\(', js, re.M)) == 1
