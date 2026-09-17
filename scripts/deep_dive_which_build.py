#!/usr/bin/env python
"""The dive page's "Which one to build?" section.

A page-facing renderer for the build brief (``scripts/deep_dive_brief.py``).
The brief module owns every number and every sentence; this module lays its
already-rendered fragments out as one collapsed ``<details>`` that sits
directly above the scatter controls, adds the section's own plot payload, and
marks first uses of six terms against ``scripts/glossary.py``.

Vocabulary (docs style rule, per document):

- Arm: one moveset of the blob, the brief's own word for it. Reader-facing
  text says "moveset"; the brief's G-voice gate bars "arm" from prose.
- Line / floor: the brief's printed stat threshold for this moveset. "Floor"
  is the internal name (``facts['floor']``); the page says "line".
- Rung: a clean cut ABOVE the line, each owning its own named matchup(s).
- Clearer: an IV spread at or above the line. Page text says "at or above
  the line" -- ``gate_voice`` bars the noun from the headline, and the same
  wording is used here for consistency.
- Payload: the small inline JSON the section's Plotly panel reads. It carries
  thresholds, marked spreads and one packed membership mask per threshold;
  every per-IV array it draws with (stats, stat-product rank, scores,
  cluster labels) is already on the page in ``DATA`` / ``SCORES`` / the
  clusters section's own payload.

NOTHING here simulates and nothing here recomputes a printed number: the
strip, the headline paragraphs, the sixteen evidence fields and the guards
block are the brief's own HTML.
"""
from __future__ import annotations

import html as _html
import json
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deep_dive_analysis as analysis  # noqa: E402
import deep_dive_brief as brief  # noqa: E402
import deep_dive_builds as builds  # noqa: E402
import deep_dive_logging  # noqa: E402
import glossary  # noqa: E402

SECTION_ID = 'dd-which-build'
SECTION_TITLE = 'Which one to build?'
# Top-N clearers the expander lists before the "show all" control. Matches the
# flavor guide's Member-IVs pattern (a short default list plus a toggle); the
# rest are built in the browser from DATA, so a 2220-spread line costs the
# page no extra bytes.
CLEARER_TOP_N = 25

# One colour per selected build, in selection order (primary, fork, bulk).
# Light-theme values, carried in the payload for the same reason
# WB_FALLBACK exists in the engine: a trace with no colour is a legend key
# pointing at invisible points. The CSS custom properties below are what
# normally drives them, so the panel still re-themes with the picker.
BUILD_COLORS = ('#7a4fc0', '#c0682a', '#16706a')

# Every view the section plot can show, with the selector label. The caption
# is per-page (it is a sentence of the brief's own headline), so it travels in
# the payload rather than here.
VIEWS_FLOOR = (('line', 'the line'), ('rungs', 'the rungs'),
               ('trade', 'the trade'), ('clusters', 'clusters'))
VIEWS_NO_FLOOR = (('clusters', 'clusters'), ('rank1', 'rank-1'))
# v4: the builds view leads on any page that HAS builds, and the four (or
# two) views above stay exactly as they were behind it. The line view is
# still the single-stat floor; the builds are the section's new primary
# object, not a replacement for the line.
VIEW_BUILDS = ('builds', 'the builds')
# v5: the same builds on the Def / HP plane, where a box IS a box
# (2026-09-16 review item 8). Second in the list, directly behind the builds
# view it re-draws.
VIEW_STATS = ('stats', 'stats')

# Terms marked on FIRST use in the section, longest-first so "stat-product
# rank-1" is claimed before "stat product" can match inside it. Each entry is
# (glossary term, regex over page text); the matched text is what gets
# wrapped, so a plural stays plural.
_TERM_PATTERNS = (
    # "SP1" is the same term under its short form: the section defines it
    # once ("stat-product rank-1 (SP1)") and then writes SP1 everywhere, so
    # whichever spelling a reader meets first gets the tooltip.
    ('stat-product rank-1', r'stat-product rank-1 \(SP1\)|stat-product rank-1'
                            r'|SP1'),
    ('decision matchup', r'decision matchups?'),
    ('build criteria', r'Build criteria'),
    ('outside rate', r'outside rates?'),
    ('guaranteed', r'guarantees?(?:d)?'),
    ('material', r'material'),
    ('build', r'builds?'),
    ('fork', r'forks?'),
    ('charge-move priority', r'charge-move[- ]priority'),
    ('contested matchups', r'contested matchups?'),
    ('one-sided gate', r'one-sided gates?'),
    ('stat product', r'stat product(?!s)'),
    ('bulkpoint', r'bulkpoints?'),
)

# A legend label drops a moveset-variant parenthetical -- "Thievul (Sucker
# Punch / Night Slash+Icy Wind)" is four words of opponent moveset inside a
# key that has to fit beside five others. A FORM parenthetical ("(Shadow)")
# is part of the opponent's name and stays; the two are told apart by the
# move-list punctuation, which a form never carries. The full name is in the
# hover.
_VARIANT_PAREN = re.compile(r'\s*\(([^()]*[/+][^()]*)\)\s*$')

_TAG_SPLIT = re.compile(r'(<[^>]*>)')
_SENTENCE_END = re.compile(r'(?<=[.!?])(?=\s|$)')


def _esc(s):
    return _html.escape(str(s), quote=True)


def display_moveset(label):
    """A moveset the way the rest of the page spells it.

    The blob's label is the gamemaster's ids ("SHADOW_CLAW / DRAIN_PUNCH,
    FOUL_PLAY"); the page header, the Moveset dropdown and every other
    reader-facing surface print "Shadow Claw / Drain Punch, Foul Play". The
    section's own sentences sit two inches under that header, so they use the
    page's spelling. ``deep_dive_analysis.pretty_moveset`` is the one rule for
    the conversion (it goes through the gamemaster's own ``name``, so
    SUPER_POWER reads "Superpower" here exactly as it does up there).

    The brief's fields and its guards block keep the identifiers: those are
    the audit, and the id is what a re-run is keyed on.
    """
    return analysis.pretty_moveset(label)


def relabel(text, all_facts):
    """Re-spell every raw moveset id in one of the brief's sentences.

    The brief writes "Same line as SHADOW_CLAW / DRAIN_PUNCH, FOUL_PLAY" into
    the headline of every moveset after the first. That is a reader-facing
    sentence on a page that spells the same moveset four different places in
    title case, so the label -- and only the label, by exact match against the
    page's own list -- is swapped for the display spelling. No other word of
    the brief's prose is touched.
    """
    for f in all_facts or []:
        raw = f['header']['arm_label']
        pretty = display_moveset(raw)
        if pretty != raw:
            text = text.replace(raw, pretty)
    return text


# The brief writes the object out in full ("The stat-product rank-1
# spread, 0/15/15, misses it by 6.35 attack"); the section defines it once
# and then writes SP1. Applied to the brief's headline sentences where the
# section embeds them, so the v3 half of the section and the v4 half spell
# one object one way (2026-09-17 round 6 review). Longest form first.
_SP1_SUBS = ((re.compile(r'The stat-product rank-1 spread'), 'SP1'),
             (re.compile(r'the stat-product rank-1 spread'), 'SP1'),
             (re.compile(r'stat-product rank-1'), 'SP1'),
             (re.compile(r'\brank-1\b'), 'SP1'))


def sp1_prose(text):
    """One of the brief's sentences, with its rank-1 spellings shortened."""
    for pat, short in _SP1_SUBS:
        text = pat.sub(short, text)
    return text


def short_movesets(all_facts):
    """One distinguishing name per moveset, or the full labels.

    Four movesets that share a fast move and a charged move differ in exactly
    one slot, and the lead reads as four near-identical strings unless it
    names that slot: "Drain Punch", "Power Gem", "Shadow Sneak", "Dazzling
    Gleam". Falls back to the full display label whenever the short names
    would not be unique (or there is nothing shared to drop), so the lead can
    never name two movesets the same way.
    """
    full = [display_moveset(f['header']['arm_label']) for f in all_facts]
    if len(all_facts) < 2:
        return full
    parsed = [analysis.parse_moveset_label(f['header']['arm_label'])
              for f in all_facts]
    if any(not charged for _fast, charged in parsed):
        return full
    common = set(parsed[0][1])
    for _fast, charged in parsed[1:]:
        common &= set(charged)
    short = []
    for _fast, charged in parsed:
        rest = [c for c in charged if c not in common]
        short.append(', '.join(analysis.pretty_name(c) for c in rest))
    if len(set(short)) != len(short) or any(not x for x in short):
        return full
    return short


def plain_value(fl):
    """The line's value at two places, with no precision parenthetical.

    :func:`printed_value` speaks the line the way the headline does, which on
    a page where stage 7 had to escalate is "123.42 (123.419)". That is the
    right string inside a paragraph that explains it, and the wrong one in a
    collapsed one-liner or under a plot, where it reads as a typo. The
    three-place selector still prints in the headline and in field 2.
    """
    if fl['axis'] == 'hp':
        return brief._n(fl['printed'])
    return brief.fmt(fl['printed'], 2)


def stat_words(fl):
    """'148.10 attack' / '125 HP' -- two places, no parenthetical."""
    return f"{plain_value(fl)} {brief.AXIS_WORD[fl['axis']]}"


# ---------------------------------------------------------------------------
# Glossary marking
# ---------------------------------------------------------------------------

class TermMarker:
    """Marks the FIRST use of each glossary term across a run of fragments.

    Substitution happens only in the text between tags, so a term appearing
    inside an attribute (a ``title=``, a table cell's ``data-`` value) is
    never rewritten into broken markup. State is per-instance: one marker per
    rendered section, fed the fragments in document order.
    """

    def __init__(self):
        # term -> (fragment number, offset of the first use in it). A set
        # would do for "have I marked this", but the terms list at the foot
        # of the section prints them in READING order, and the loop below
        # walks terms longest-first rather than left-to-right -- so within
        # one fragment the marking order is not the reading order.
        self.used = {}
        self._frag = 0

    def ordered(self):
        """The marked terms, in the order a reader meets them."""
        return sorted(self.used, key=lambda t: self.used[t])

    @staticmethod
    def _first_offset(original, pattern):
        """Where a term first occurs in the UNMARKED fragment, or None.

        Measured on the original text, never on the partially-marked one.
        The loop below claims terms in _TERM_PATTERNS order rather than in
        reading order, so a term claimed LATER can sit EARLIER in the text --
        and an offset read off the working copy would then carry the length
        of every tooltip inserted before it. On the v4 section that put
        "guaranteed" after "decision matchup" in the Terms list although a
        reader meets it first (the two are one sentence apart in the builds
        lead).
        """
        off = 0
        for piece in _TAG_SPLIT.split(original):
            if not piece.startswith('<') and piece.strip():
                m = re.search(pattern, piece, re.IGNORECASE)
                if m:
                    return off + m.start()
            off += len(piece)
        return None

    def mark(self, fragment):
        # One term per outer pass, re-splitting the fragment each time. The
        # markup a substitution inserts carries the DEFINITION in a title=
        # attribute, and re-splitting puts that text inside a tag piece where
        # the next term cannot match it. (No definition in the registry
        # contains another registered term today -- test_no_definition_
        # contains_another_term keeps it that way -- but a marker that only
        # works while that holds is a trap for whoever adds the seventh term.)
        original = fragment
        for term, pattern in _TERM_PATTERNS:
            if term in self.used:
                continue
            pieces = _TAG_SPLIT.split(fragment)
            # Depth inside an <abbr class="wb-term"> this marker already
            # inserted. Text there is a term that has been CLAIMED, and a
            # later shorter term matching inside it nests one tooltip in
            # another -- on the v4 page "Build criteria" was marked, then
            # "build" re-matched the word inside it, and the inner title (the
            # WRONG definition) is the one a hover shows. Splitting on tags
            # is not enough: the substitution puts the claimed text in its
            # own text piece.
            depth = 0
            for k, piece in enumerate(pieces):
                if piece.startswith('<'):
                    if piece.startswith('<abbr') and 'wb-term' in piece:
                        depth += 1
                    elif piece.startswith('</abbr') and depth:
                        depth -= 1
                    continue
                if depth or not piece.strip():
                    continue
                m = re.search(pattern, piece, re.IGNORECASE)
                if not m:
                    continue
                pieces[k] = (piece[:m.start()]
                             + glossary.abbr_html(term, text=m.group(0))
                             + piece[m.end():])
                # Offset in the WHOLE fragment as it arrived, not in this
                # piece and not in the working copy: see _first_offset.
                self.used[term] = (self._frag,
                                   self._first_offset(original, pattern))
                fragment = ''.join(pieces)
                break
        self._frag += 1
        return fragment


# ---------------------------------------------------------------------------
# Sentence surgery on the brief's headline
# ---------------------------------------------------------------------------

def sentences(paragraph):
    """Split a headline paragraph into sentences.

    Splits only at a terminator FOLLOWED BY whitespace, so "148.10" and
    "L45.5" stay whole; every printed stat value in the brief is written
    without a space after its decimal point.
    """
    return [s.strip() for s in _SENTENCE_END.split(paragraph) if s.strip()]


def example_spreads(facts):
    """The brief's example spreads, deduplicated, in the brief's order."""
    out, seen = [], set()
    for ex in facts.get('examples') or []:
        key = tuple(ex['ivs'])
        if key in seen:
            continue
        seen.add(key)
        out.append(ex)
    return out


def _spread_str(ivs, level):
    return f"{ivs[0]}/{ivs[1]}/{ivs[2]} at L{float(level):g}"


# The brief's opening sentence is a DIRECTIVE -- "Most Sableye (Shadow)
# running X in Great League should have at least 148.10 attack" -- which
# Michael's 2026-09-16 review called a strategy read the page has not earned:
# it tells a reader what to do, when what this section knows is what each
# region wins. The section rewrites the clause in place (the rest of the
# sentence, and the whole rest of the paragraph, are untouched) and the
# BUILDS carry the reader-facing verdict, one paragraph each.
_DIRECTIVE_OPENING = re.compile(r'^Most\s+(.+?)\s+should have at least\s+',
                                re.IGNORECASE)


def descriptive_opening(first):
    """The headline's opening sentence, with the directive taken out.

    "Most X should have at least 148.10 attack." -> "X has a line at 148.10
    attack." Returns the sentence unchanged when it is not the directive
    template (a moveset sharing an earlier one's line opens "Same line as
    ...", and a page with no line has no such sentence at all), so this can
    never half-rewrite a sentence it did not recognise.
    """
    m = _DIRECTIVE_OPENING.match(first)
    if not m:
        return first
    return f"{m.group(1)} has a line at {first[m.end():]}"


def extended_first_sentence(facts):
    """The headline's opening sentence, with the spreads that reach the line.

    "... should have at least 148.10 attack" becomes "... at least 148.10
    attack, which 6/9/7 at L50, 7/2/14 at L49.5, 10/13/11 at L45.5 and 2217
    other spreads reach." The counts are the brief's (``n_above`` minus the
    spreads named); nothing is recomputed.

    Returns the sentence unchanged on a page with no line -- there is no set
    of spreads that reach anything to name -- and on a moveset that shares an
    earlier moveset's line, whose opening sentence ALREADY ends in "reached by
    2220 of the 4096 IV spreads (54.2%)". Extending that one printed the same
    count twice in one sentence, once as a total and once as a remainder.
    """
    first = descriptive_opening(sentences(facts['_headline'][0])[0])
    fl = facts['floor']
    if fl is None or 'reached by' in first:
        return first
    exs = example_spreads(facts)
    if not exs:
        return first
    named = [_spread_str(ex['ivs'], ex['level']) for ex in exs]
    rest = int(fl['n_above']) - len(exs)
    if rest > 0:
        named.append(f"{brief._n(rest)} other "
                     f"{brief._noun(rest, 'spread')}")
    body = first[:-1] if first.endswith('.') else first
    return f"{body}, which {brief._and_list(named)} reach."


# ---------------------------------------------------------------------------
# The lead: which movesets on this page carry a line
# ---------------------------------------------------------------------------

def _line_words(f):
    """This moveset's line as the lead speaks it, or None."""
    fl = f['floor']
    return None if fl is None else stat_words(fl)


def lead_sentences(all_facts, arm):
    """Two sentences: what the page's movesets share, then which one this is.

    Round 1 wrote this in the machinery's voice -- "All 4 movesets rendered
    here carry a build line. This file is SHADOW_CLAW / DRAIN_PUNCH,
    FOUL_PLAY at Atk >= 148.10." -- which is three pieces of internal
    vocabulary ("rendered here", "this file", "build line") before the reader
    reaches a number. It says "page", never "file"; "line", never "build
    line"; and it names the movesets the way the Moveset dropdown does.

    The second sentence exists because each split file carries only ITS
    moveset's section: a reader who landed on the Power Gem page from a
    search has no way to see that Drain Punch prints the same line unless
    this sentence says so.
    """
    n = len(all_facts)
    mine = _line_words(all_facts[arm])
    names = short_movesets(all_facts)
    if n == 1:
        return [f"The only moveset on this page is {names[0]}"
                + (", and it carries no line."
                   if mine is None else f", at least {mine}.")]

    values = [_line_words(f) for f in all_facts]
    with_line = [v for v in values if v is not None]
    if not with_line:
        first = f"None of the {n} movesets on this page carries a line."
    elif len(with_line) == n and len(set(with_line)) == 1:
        first = (f"All {n} movesets on this page share one line: at least "
                 f"{with_line[0]}.")
    elif len(with_line) == n:
        first = f"All {n} movesets on this page carry a line, at different values."
    else:
        carries = 'carries' if len(with_line) == 1 else 'carry'
        first = (f"{len(with_line)} of the {n} movesets on this page "
                 f"{carries} a line.")

    second = (f"This page is {names[arm]}"
              + (", and it carries no line" if mine is None
                 else f", at least {mine}"))
    # Grouped by what they print, so a four-moveset page reads as one clause
    # and not as four. Semicolons between the groups: a moveset named by two
    # charged moves already carries a comma.
    same, other, none = [], [], []
    for i, f in enumerate(all_facts):
        if i == arm:
            continue
        val = values[i]
        if val is None:
            none.append(names[i])
        elif val == mine:
            same.append(names[i])
        else:
            other.append((names[i], val))
    bits = []
    if same:
        bits.append(f"{brief._and_list(same)} "
                    f"{'prints' if len(same) == 1 else 'print'} the same line")
    for name, val in other:
        bits.append(f"{name} is at least {val}")
    if none:
        bits.append(f"{brief._and_list(none)} "
                    f"{'carries' if len(none) == 1 else 'carry'} no line")
    if bits:
        second += '; ' + '; '.join(bits)
    return [first, second + '.']


# ---------------------------------------------------------------------------
# The summary line (what a reader sees before opening the section)
# ---------------------------------------------------------------------------

def _shared_clause(facts, all_facts):
    """'(the same line as its other 3 movesets)' / '(Power Gem)' / ''.

    A split file's summary is the whole verdict for a reader who never opens
    the section, so on a multi-moveset dive it has to say WHICH moveset it is
    the verdict for -- or, when every moveset prints the same line, that the
    choice of moveset does not change it.
    """
    if not all_facts or len(all_facts) < 2:
        return ''
    arm = facts['header']['arm']
    values = [_line_words(f) for f in all_facts]
    if values[arm] is not None and len(set(values)) == 1:
        return f"(the same line as its other {len(all_facts) - 1} movesets)"
    return f"({short_movesets(all_facts)[arm]})"


def summary_sentence(facts, all_facts=None):
    """The one sentence in the collapsed ``<summary>``.

    It is a DIRECTIVE, built here from the facts, not the headline's opening
    sentence quoted:

    - On a moveset that shares an earlier moveset's line the brief opens
      "Same line as SHADOW_CLAW / DRAIN_PUNCH, FOUL_PLAY: ...", which makes
      the answer to "which one to build?" a reference to a moveset on a
      DIFFERENT file. Here every file says the value.
    - The brief keeps its directive whenever the line's net cost is inside
      the materiality band, so the summary could say "should have at least
      123.42 attack" on a page whose own second paragraph says rank-1 wins
      one MORE matchup. A reader who reads only the summary would be sent
      after a line the evidence prices. The clause is in the same sentence.
    - The value prints at two places; the proven three-place selector stays
      in the headline and field 2, where the sentence around it explains why
      there are two numbers.

    A page with no line cannot be directive: its two replacements say what a
    reader who only reads the summary should do.
    """
    fl = facts['floor']
    if fl is None:
        gb = facts['grid_best']
        r1 = facts['rank1']
        # n_tied: "wins more than any other spread" is a strict claim, and
        # the same fact dict says how many spreads share the top count.
        if gb['total'] <= r1['total_won'] and int(gb.get('n_tied') or 1) == 1:
            # This sentence is its own surface -- the collapsed line of a
            # page with no line -- so the term is spelled out here at first
            # use rather than inheriting the builds lead's definition, which
            # a reader of the summary alone never reaches (round 6 review).
            return ("Your stat-product rank-1 (SP1): it already wins more "
                    "matchups than any other spread.")
        return "Any of them: no single stat threshold decides a matchup here."
    who = brief.focal_name(facts['header'])
    cost = facts.get('floor_cost') or {}
    if cost.get('material'):
        # The brief demoted its own directive here; the summary follows it
        # rather than re-promoting the line in the one line a reader reads.
        return (f"{who} has a line at {stat_words(fl)}, and clearing it "
                f"costs more than it buys.")
    out = f"Most {who} should have at least {stat_words(fl)}"
    clause = _shared_clause(facts, all_facts)
    if clause:
        out += ' ' + clause
    net = int(cost.get('net', 1) if cost else 1)
    if net <= 0:
        r1 = brief._ivs(facts['rank1']['ivs'])
        if net == 0:
            out += (f" -- though SP1 {r1} already wins as many matchups "
                    f"as anything above it")
        else:
            out += (f" -- though SP1 {r1} still wins {brief._n(-net)} "
                    f"more {brief._noun(-net, 'matchup')} overall")
    return out + '.'


# ---------------------------------------------------------------------------
# Plot payload
# ---------------------------------------------------------------------------

def mask_b64(flags):
    """Pack a per-spread boolean into base64, LSB-first inside each byte.

    Why the panel carries masks at all: ``DATA.ivAtk`` / ``ivDef`` on the
    page are ROUNDED TO 2 dp (``deep_dive.py``: ``iv_atk = [round(m[5], 2)
    ...]``), while the line is a full-precision value. Comparing the rounded
    array against it mis-sides the spreads inside the rounding window -- 19
    of 4096 on the Shadow Sableye grid, which would have shown as 19
    wrong-colored points under a sentence claiming the split is exact. The
    mask is computed here from the SAME full-precision plane the brief
    selected the line on, so the plot and the sentence cannot disagree.

    512 bytes per 4096-spread mask, ~684 base64 characters. That is the
    classification, not a second copy of the stats.

    The packing itself lives in ``deep_dive_builds.pack_mask`` -- the builds
    payload packs masks too, and the browser has exactly one unpacker
    (``_wbMask`` / ``_wbBit``), so there is one implementation per side.
    """
    return builds.pack_mask(flags)


def line_key(axis, T):
    """Pool key for one threshold. Two lines at the same value on the same
    axis are the same set of spreads, and nine shield scenarios share their
    values often enough to be worth saying once (the Shadow Sableye page's
    1v1 and 2v2 both turn over at 148.71)."""
    return f"{axis}:{float(T):.9f}"


def page_rounded(plane, axis):
    """The plane as the PAGE carries it.

    ``deep_dive.py`` embeds ``iv_atk = [round(m[5], 2) for m in meta]`` and
    the same for defense; HP is an integer and is embedded whole. This is
    that array, so a cut selected here selects the same spreads in the
    browser.
    """
    return plane if axis == 'hp' else np.round(plane, 2)


def rounded_cut(plane, axis, T):
    """One threshold, re-expressed against the page's own 2-dp stats.

    The panel has to split the grid at a full-precision value using an array
    that is rounded to two places. The section's own line does it with a
    packed 512-byte membership mask (:func:`mask_b64`), which is the right
    trade for a value the whole section is about -- but there is one of those
    per printed rung, and the Shield scenario control asks for up to a dozen
    MORE thresholds on one page.

    So a scenario line ships two things instead: the cut in the page's OWN
    rounded array -- ``min(rounded[at or above T])``, the smallest value a
    clearer displays -- and the indices where comparing against it disagrees
    with the full-precision plane. The second list is the exactness: it is
    computed here and applied in the browser, so the split the panel draws is
    the split the brief measured whether or not the rounding happens to be
    kind. On all three preview blobs it comes back EMPTY for every scenario
    line (the naive 19-spread hazard is comparing the rounded array against
    the raw threshold, not against the lowest rounded clearer), which is why
    this costs a float and an empty array per line rather than 684 base64
    characters.

    Returns ``(cut, wrong_indices)``.
    """
    exact = plane >= T
    rd = page_rounded(plane, axis)
    cut = float(rd[exact].min())
    wrong = np.nonzero((rd >= cut) != exact)[0]
    return cut, [int(x) for x in wrong]


def compute_masks(state, arm, facts, mode='pvpoke', level='l50'):
    """Membership masks for the line, each rung above it, the bulk pair, and
    every per-scenario line the Shield scenario control can draw.

    Recomputed from the blob's own stat planes rather than carried out of
    ``compute_brief`` (which drops every numpy array on the way to JSON).
    The counts are cross-checked against the brief's printed counts before
    anything is packed: a mismatch means the plot would draw a different set
    from the one the page describes, and there is no honest way to render
    that.

    The per-scenario lines do NOT get masks: they get a cut in the page's own
    rounded array plus the indices it gets wrong (:func:`rounded_cut`), which
    is a float and (so far always) an empty list per distinct value instead
    of 684 base64 characters. Pooled by (axis, value) all the same, since
    scenarios share their values.
    """
    _scores, meta = brief.arm_view(state, arm, mode, level=level)
    atk, dfn, hp = brief.stat_planes(meta)
    planes = {'atk': atk, 'def': dfn, 'hp': hp}
    lines = {}
    for entry in (facts.get('scenario_lines') or {}).values():
        for row in entry['lines']:
            key = line_key(row['axis'], row['T'])
            if key in lines:
                continue
            plane = planes[row['axis']]
            flags = plane >= row['T']
            got = int(flags.sum())
            if got != int(row['n_pass']):
                raise ValueError(
                    f"scenario line {row['printed']} covers {got} "
                    f"spreads, the brief counts {row['n_pass']}")
            cut, wrong = rounded_cut(plane, row['axis'], row['T'])
            # The reconstruction the browser will do, checked here against
            # the plane the brief measured on. It cannot fail by
            # construction; it is asserted anyway, because the whole point of
            # shipping the exceptions rather than a mask is that the two
            # sides agree, and a silent disagreement is 4096 points drawn in
            # the wrong colors under a sentence that says the split is exact.
            rebuilt = page_rounded(plane, row['axis']) >= cut
            rebuilt[wrong] = ~rebuilt[wrong]
            if not np.array_equal(rebuilt, flags):
                raise ValueError(
                    f"scenario line {row['printed']} does not reconstruct "
                    f"from the page's rounded stats")
            lines[key] = {'cut': cut, 'wrong': wrong}
    fl = facts['floor']
    if fl is None:
        return {'rungs': [], 'alt': None, 'lines': lines}
    plane = planes[fl['axis']]
    rungs = []
    for row, count in [(fl, fl['n_above'])] + [
            (r, r['n_pass']) for r in (facts.get('rungs_above') or [])]:
        flags = plane >= row['T']
        got = int(flags.sum())
        if got != int(count):
            raise ValueError(
                f"mask for {row['printed']} covers {got} spreads, the page "
                f"prints {count}")
        rungs.append(mask_b64(flags))
    alt = facts.get('alternative')
    alt_mask = None
    if alt is not None and not alt['too_wide']:
        flags = (dfn >= alt['def_cut']) & (hp >= alt['hp_cut'])
        got = int(flags.sum())
        if got != int(alt['n']):
            raise ValueError(
                f"bulk-pair mask covers {got} spreads, the page prints "
                f"{alt['n']}")
        alt_mask = mask_b64(flags)
    return {'rungs': rungs, 'alt': alt_mask, 'lines': lines}


def printed_value(fl):
    """The line's value EXACTLY as the headline speaks it.

    Two decimal places, plus the proven selector in parentheses when stage 7
    had to escalate past two ("123.42 (123.419)"): at three places the 2-dp
    rendering selects a different set of spreads, which is why the brief
    prints both. The section reuses the same string so the value a reader
    clicks is the value the sentence around it just said.
    """
    if fl['axis'] == 'hp':
        return brief._n(fl['printed'])
    return brief.headline_value(fl['printed'], fl['dp'])


def _rung_label(printed, dp, names, n_cells, short=False):
    """'148.10 (0v1 Annihilape)' -- one rung of the ladder, for a legend key.

    Two places ALWAYS, including the floor: the ladder is six keys in one
    horizontal legend, and a floor printed at three places under a headline
    that says two reads as a different kind of number. The value labels a
    group whose membership comes from the packed mask, so it is a name, not a
    selector -- the selector prints at full precision in field 2.

    ``short`` drops the opponent's moveset-variant parenthetical, which the
    hover still carries in full.
    """
    head = brief.fmt(printed, 2)
    if not names:
        return head
    name = names[0]
    if short:
        name = _VARIANT_PAREN.sub('', name)
    more = n_cells - 1
    tail = f"{name}{f' +{more}' if more > 0 else ''}"
    return f"{head} ({tail})"


# The brief's example-selection rules are audit vocabulary ("cells",
# "clearers", "SP"), and the panel would otherwise print them as legend keys
# under a caption written for a reader. Same three spreads, same rules, said
# the way the rest of the section says them. An unmapped rule falls through
# unchanged rather than being dropped: a legend key with no label is worse
# than one in the brief's words.
_EXAMPLE_LABELS = {
    'highest stat product clearing the floor':
        'highest stat product above the line',
    'most cells won on the whole grid':
        'most contested matchups won on this grid',
    'highest stat product (the rank-1 spread)':
        'highest stat product (rank-1)',
}
_EXAMPLE_PREFIXES = (
    ('most cells won among clearers with SP >= ',
     'most contested matchups won above the line, stat product >= '),
    ('most cells won among the whole grid with SP >= ',
     'most contested matchups won on this grid, stat product >= '),
    ('bulkiest (max Def x HP) among clearers with SP >= ',
     'bulkiest above the line, stat product >= '),
    ('bulkiest (max Def x HP) among the whole grid with SP >= ',
     'bulkiest on this grid, stat product >= '),
)


def example_label(rule):
    """One example-spread selection rule, in the section's own words."""
    if rule in _EXAMPLE_LABELS:
        return _EXAMPLE_LABELS[rule]
    for raw, reader in _EXAMPLE_PREFIXES:
        if rule.startswith(raw):
            return reader + rule[len(raw):]
    return rule


# ---------------------------------------------------------------------------
# The rung ramp
# ---------------------------------------------------------------------------

# The two ends of the ramp per theme, light first. Every step between them is
# interpolated for the number of rungs the page actually prints: a fixed
# six-color ramp painted the 6th and 7th rung of a seven-rung page in the same
# color, on the one view whose entire encoding is color. The ends (not the
# steps) are what the contrast test pins; interpolation stays inside the
# segment they bound.
RUNG_ENDS = {'light': ('#9d61d1', '#301547'),
             'dark': ('#9859cf', '#e6d7f4')}


def _hex_to_rgb(value):
    v = value.lstrip('#')
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def rung_ramp(n, theme='light'):
    """``n`` distinct colors along this theme's rung ramp, floor first."""
    n = max(int(n), 0)
    if n == 0:
        return []
    a, b = (_hex_to_rgb(x) for x in RUNG_ENDS[theme])
    if n == 1:
        return [RUNG_ENDS[theme][0]]
    out = []
    for i in range(n):
        t = i / (n - 1)
        out.append('#' + ''.join(
            f"{round(a[c] + (b[c] - a[c]) * t):02x}" for c in range(3)))
    return out


def ramp_css(n, prefix='r'):
    """The ``--wb-<prefix>*`` custom properties for a ramp of ``n`` steps.

    TWO ramps ship, not one stretched over both: ``--wb-r*`` is the page's own
    rung ladder and ``--wb-s*`` is whatever the Shield scenario control draws.
    A scenario's ladder can be LONGER than the page's (six on Shadow Sableye
    1v1 against the page's own count), and sizing one shared ramp to the
    longer of the two would have re-colored every printed rung on the page --
    a visible change to the default state, to fix a case the default state
    never reaches. Sized separately, the overflow rungs stop sharing a color
    and the "all" view is untouched.
    """
    if n <= 0:
        return ''
    def block(theme, sel):
        vals = '; '.join(f"--wb-{prefix}{k}: {c}"
                         for k, c in enumerate(rung_ramp(n, theme)))
        return f"{sel} {{ {vals}; }}\n"
    return (block('light', f"#{SECTION_ID}")
            + block('dark', f'[data-theme="gruvbox-dark"] #{SECTION_ID},\n'
                            f'[data-theme="pokemon-dark"] #{SECTION_ID}'))


def _corroboration_sentence(fields):
    """The brief's own cluster-corroboration sentence, or None.

    It lives in the "How sure" field and nowhere else; the clusters view's
    caption quotes it rather than authoring a second sentence about the same
    partition.
    """
    for field in fields:
        if field['title'] != 'How sure':
            continue
        for line in field['lines']:
            if line.startswith('Independent check:'):
                return line
    return None


# The clusters view's caption when the brief found no corroboration to
# quote -- a live path: cluster_corroboration is None whenever the clustering
# does not clear the floor. Section-authored, so prepare() puts it through the
# brief's word gates with the rest of this module's prose ("partition", the
# word the first draft used, is barred from reader-facing text by G-voice).
CLUSTERS_FALLBACK_CAPTION = (
    "The Matchup clusters section's own groups over this same grid, drawn "
    "here on the same axes.")


def fixed_note(facts, page_movesets=1):
    """The sentence under the panel: which view it is pinned to, and why.

    Round 3 replaced "this panel is inert to the page's dropdowns" with what
    is now true: the panel HAS a shield control, its own, on the selector row
    above. The rest of the pinning is unchanged -- PvPoke-default opponent
    IVs, the league cap, the whole opponent pool -- because those are the
    view the line was derived on, and the scatter's dropdowns still do not
    reach in here.
    """
    out = ("Stat-product rank against matchups won with PvPoke-default "
           "opponent IVs at the league cap over the whole opponent pool and, "
           "with Shield scenario on all, every baked shield state -- the view "
           "the line above was derived on. The Shield scenario selector on "
           "this row is the section's own; the scatter's dropdowns and the "
           "opponent filter do not drive this panel.")
    if page_movesets > 1:
        out += (f" This whole section is about "
                f"{display_moveset(facts['header']['arm_label'])}, which the "
                f"Moveset dropdown above does not change.")
    return out


BUILDS_CAPTION = (
    "Every spread on this grid, by stat product rank against the matchups it "
    "wins in the shield scenarios the Build criteria preset counts. One "
    "colour per build, with the wider region around Build 1 -- when the "
    "lattice holds one -- under it in a lighter tint of its colour and "
    "carrying only the spreads no build holds; the diamond is stat-product "
    "rank-1 (SP1), each triangle a "
    "build's most-winning member under this preset, the open square the "
    "spread that wins the most matchups over every shield scenario this dive "
    "baked -- which under a narrower preset is not the highest point on the "
    "plot, because the axis is not counting the same matchups -- and the "
    "open cross the spread with the highest Avg Battle Score on the main "
    "scatter.")

UPSET_CAPTION = (
    "Left: the named sets the lattice was built from (rows, labelled "
    "'spreads in the set / decision matchups every member of it wins') "
    "and the candidate regions made by intersecting them (columns -- bar "
    "height is spreads, the number above it is decision matchups guaranteed "
    "in the shield scenarios this preset counts, and a coloured column is "
    "one of the builds in the table above). A dot means the region sits "
    "inside that row's set. The letters index THIS preset's own eight sets "
    "and are re-assigned when the Build criteria change, so compare the row "
    "names across presets, not the letters.")


STATS_CAPTION = (
    "The same spreads on the two stats a build's rule is usually written in: "
    "defense across, HP up, marker size for attack. Each build's members are "
    "in its own colour, everything else is muted, and each build is outlined "
    "where it IS a region on this plane -- a two-stat box as a rectangle, an "
    "attack floor plus a defense staircase as the staircase itself, a linear "
    "trade as its boundary line. A build no rule fits is drawn as its points "
    "and nothing else. A cut on ATTACK cannot be drawn on these axes, so a "
    "build that has one carries it in the legend key instead: two spreads at "
    "the same defense and HP can sit on opposite sides of it. The diamond is "
    "stat-product rank-1 (SP1), the open square the spread that wins the most "
    "matchups, the open cross the highest Avg Battle Score, and gold stars "
    "your own collection.")


def _caption_for(view, facts, fields, all_facts=None):
    """One sentence of the brief's prose per view, chosen by what it shows.

    The builds view is the one view the brief has no sentence about -- it
    draws this module's own object -- so its caption is authored here and
    gated with the rest of this module's prose in :func:`prepare`.
    """
    if view == 'builds':
        return BUILDS_CAPTION
    if view == 'stats':
        return STATS_CAPTION
    head = facts['_headline']
    first = [sp1_prose(relabel(x, all_facts)) for x in sentences(head[0])]
    rest = ([sp1_prose(relabel(x, all_facts)) for x in sentences(head[1])]
            if len(head) > 1 else [])
    if view == 'line':
        # NOT the summary sentence: that one is six inches above and in the
        # collapsed <summary> above that, and a caption's job is to say what
        # the picture shows. The brief's own two sentences about the split
        # and about where rank-1 lands are exactly that.
        reach = next((x for x in first[1:] if ' reach' in x),
                     first[0] if 'reached by' in first[0] else None)
        pair = [x for x in (reach, rest[0] if rest else None) if x]
        return ' '.join(pair) if pair else first[0]
    if view == 'rank1':
        return rest[-1] if rest else first[0]
    if view == 'rungs':
        for s in first + rest:
            if s.startswith('The next step up is'):
                return s
        for s in first + rest:
            if s.startswith('It decides'):
                return s
        return first[0]
    if view == 'trade':
        for s in first + rest:
            if s.startswith('Trading ') or s.startswith('What bulk does'):
                return s
        for s in first + rest:
            if 'bulk' in s:
                return s
        return first[0]
    if view == 'clusters':
        cc = _corroboration_sentence(fields)
        if cc:
            return cc
        return CLUSTERS_FALLBACK_CAPTION
    return first[0]


# ---------------------------------------------------------------------------
# The Shield scenario control
# ---------------------------------------------------------------------------

# The "every scenario" entry of the section's own Shield scenario selector.
# It is the section's default and it is what every sentence outside the panel
# -- the collapsed summary, the lead, the headline, the evidence -- is about;
# the control changes the panel, its caption and the rung list note, and
# nothing else.
ALL_SCEN = 'all'
ALL_SCEN_LABEL = 'all'


def _axis_value(row):
    """One threshold's value, two places, no parenthetical."""
    if row['axis'] == 'hp':
        return brief._n(row['printed'])
    return brief.fmt(row['printed'], 2)


def _axis_words(row):
    """'148.10 attack' / '92.68 defense' / '125 HP'."""
    return f"{_axis_value(row)} {brief.AXIS_WORD[row['axis']]}"


def _cell_name(scen, label):
    """A cell label with its scenario prefix dropped.

    Inside a view that draws ONE shield scenario, "0v1 Annihilape" says the
    scenario twice: once in the selector the reader just set and once in
    every legend key under it.
    """
    prefix = scen + ' '
    return label[len(prefix):] if label.startswith(prefix) else label


def scen_line_label(scen, row, short=False):
    """'148.10 (Annihilape)' -- one per-scenario line, for a legend key.

    The axis word rides along only when the axis is NOT attack: every page
    that has printed a line so far prints an attack one, and a legend of six
    keys each carrying the same redundant word is six keys of noise. A
    defense or HP line has to say so, because the x-axis and the hover are
    both about stat product and nothing else on the panel names the axis.
    """
    head = _axis_value(row)
    if row['axis'] != 'atk':
        head += ' ' + brief.AXIS_WORD[row['axis']]
    name = _cell_name(scen, row['names'][0])
    if short:
        name = _VARIANT_PAREN.sub('', name)
    more = row['n_cells'] - 1
    return f"{head} ({name}{f' +{more}' if more > 0 else ''})"


def _decides_sentence(scen, row, where=None):
    """What one per-scenario line decides, in the primitive's own terms.

    ``where`` drops the "in 0v0 shields" phrase (pass ``''``) for a caller
    that has just named the shield state in the clause before it.
    """
    who = _cell_name(scen, row['names'][0])
    v = _axis_words(row)
    w = f" in {scen} shields" if where is None else where
    if row['kind'] == 'exact':
        return (f"At or above {v} every spread wins {who}{w}, "
                f"and below it none does.")
    if row['kind'] == 'gate' and row['gate_side'] == 'necessary':
        return (f"No spread below {v} wins {who}{w}, and "
                f"{brief._n(row['n_win_above'])} of the "
                f"{brief._n(row['n_above'])} spreads at or above it do.")
    if row['kind'] == 'gate':
        return (f"Every spread at or above {v} wins {who}{w}, "
                f"and {brief._n(row['n_win_below'])} of the "
                f"{brief._n(row['n_below'])} below it win it as well.")
    return (f"{v} splits {who}{w} with "
            f"{brief._n(row['n_wrong'])} of {brief._n(row['n_above'] + row['n_below'])} "
            f"spreads on the wrong side of it.")


# A per-scenario line is a WEAKER claim than the page's own: it is a real cut
# in a real cell, but stage 6's cross-setting gates never ran on it. Nothing
# else on the panel says so, and "at or above X every spread wins Y" reads
# exactly as strong as the printed line's own sentence. One clause, once per
# caption, stating the scope rather than apologising for it.
SCOPE_CLAUSE = ("Unlike this page's line, a scenario line is not checked "
                "against the other baked opponent-IV settings.")


def _degeneracy_finding(entry):
    """The Matchup clusters section's OWN sentence about a dead scenario.

    Imported rather than rewritten. The section used to state this absence in
    the brief's counts ("2 contested matchups over 3 distinct win patterns")
    while the clusters view of the SAME shield state stated it in the clusters
    section's ("1 opponent is a sharp marginal"), and a reader flipping Show:
    met two different numbers for what reads as one quantity, neither defined
    where it was printed. One claim, one source, one set of numbers.
    """
    return brief.clusters.degenerate_finding(
        int(entry['win_lo']), int(entry['win_hi']), int(entry['n_opp']))


def _degeneracy_tail(scen, entry):
    """The degeneracy note beside a line, when the scenario has both.

    G-scenario is a hard exclusion for the PAGE's line, and it is not applied
    to a scenario line -- so a shield state where the IV choice moves three
    matchups can still carry an in-band cut, and did (Melmetal 2v0). Stating
    the cut without the scale reads as "this threshold matters here"; the
    clusters view of the same state says the opposite two clicks away.
    """
    if not entry.get('degenerate'):
        return ''
    return (f" In {scen} shields little turns on IVs at all: "
            f"{_degeneracy_finding(entry)}.")


def _scope_tail(rows, off):
    """The scope clause, unless every line drawn IS the page's own."""
    if off or any(not r['is_floor'] for r in rows):
        return ' ' + SCOPE_CLAUSE
    return ''


def _off_axis_sentence(scen, off):
    """The in-band thresholds this scenario carries on the OTHER stats.

    They are named and they are not drawn. A ladder is a nesting claim --
    every clearer of a rung clears the rungs below it -- and across axes that
    is simply false: on Sableye GL 1v1, 1295 spreads clear the 123.92 attack
    line and miss the 119.55 defense one, and 1288 the reverse. Ranked into
    one ramp they were colored "by the highest line cleared" under a grey key
    reading "Below 119.55 defense", which mis-described a quarter of the grid.
    """
    if not off:
        return ''
    if len(off) == 1:
        o = off[0]
        return (f" {_decides_sentence(scen, o)} That is a "
                f"{brief.AXIS_WORD[o['axis']]} line, not a rung of this "
                f"ladder.")
    body = ' '.join(_decides_sentence(scen, o) for o in off)
    return (f" {body} Those are {brief._n(len(off))} thresholds on the other "
            f"stats, not rungs of this ladder.")


def _no_line_caption(scen, entry, facts):
    """What the muted grid says when one scenario has no ladder to draw.

    Two different absences, and they are not the same claim. A DEGENERATE
    scenario (G-scenario) barely turns over at all, and it says so in the
    Matchup clusters section's own words and numbers. A scenario with cuts
    that all sit outside the decision band has rules -- they are simply not
    build decisions, because almost everything or almost nothing clears them
    -- and the nearest one is named with its share AND with which side of the
    band it missed on, so the number is not doing all the work.
    """
    lo, hi = brief.DECISION_BAND
    n_iv = int(facts['header']['n_iv'])
    if entry.get('degenerate'):
        # No "closest rule" here on purpose: the finding is that nothing
        # moves, and naming a threshold under it tells the reader there is
        # something to reach for.
        return (f"In {scen} shields little turns on IVs at all: "
                f"{_degeneracy_finding(entry)}. There is no line to "
                f"draw.")
    head = (f"No attack, defense or HP threshold in {scen} shields splits "
            f"between {brief.pct(lo, 0)} and {brief.pct(hi, 0)} of the grid, "
            f"which is the range a line has to sit in to be a build "
            f"decision.")
    c = entry.get('closest')
    # A cut every spread clears (or none does) is not a rule a reader can act
    # on; stage 13 drops those, and this is the belt to that braces.
    if not c or not (0 < int(c['n_pass']) < n_iv):
        return head
    who = _cell_name(scen, c['names'][0])
    share = float(c['pool_share'])
    if c.get('dirty') and lo <= share <= hi:
        tail = (f"but {brief._n(c['n_wrong'])} spreads fall on the wrong "
                f"side of it")
    elif share > hi:
        tail = 'too much of the grid for that to be a build decision'
    else:
        tail = 'too little of the grid for that to be a build decision'
    return (f"{head} The nearest, {_axis_words(c)} ({who}), is cleared by "
            f"{brief._n(c['n_pass'])} of {brief._n(n_iv)} spreads "
            f"({brief.pct(share)}) -- {tail}.")


def _rungs_head(scen, rows):
    """'4 attack thresholds each turn a matchup over in 1v1 shields, from ...'

    The primitives are counted rather than flattened: a one-sided gate does
    not turn a matchup over, and the multi-line caption used to say every
    line on the ladder did.
    """
    aw = brief.AXIS_WORD[rows[0]['axis']]
    kinds = [r['kind'] for r in rows]
    n_ex = kinds.count('exact')
    if n_ex == len(rows):
        head = (f"{brief._n(len(rows))} {aw} thresholds each turn a matchup "
                f"over in {scen} shields")
    else:
        n_gate = kinds.count('gate')
        n_ne = kinds.count('near_exact')
        if n_gate == len(rows):
            note = 'all one-sided'
        elif n_ne == len(rows):
            note = 'all near-exact'
        else:
            bits = []
            if n_ex:
                bits.append(f"{brief._n(n_ex)} outright")
            if n_gate:
                bits.append(f"{brief._n(n_gate)} in one direction only")
            if n_ne:
                bits.append(f"{brief._n(n_ne)} with spreads on the wrong side")
            note = ', '.join(bits)
        head = (f"{brief._n(len(rows))} {aw} thresholds each decide a matchup "
                f"in {scen} shields ({note})")
    return (f"{head}, from {_axis_value(rows[0])} "
            f"({_cell_name(scen, rows[0]['names'][0])}) up to "
            f"{_axis_value(rows[-1])} "
            f"({_cell_name(scen, rows[-1]['names'][0])}); each spread is "
            f"colored by the highest it clears.")


def scenario_caption(view, scen, entry, facts, base=''):
    """One caption, for one view, with one shield scenario selected.

    ``base`` is the view's all-scenario caption (the brief's own sentence),
    which two of the views keep: the trade is a whole-grid trade whatever the
    selector says, so its caption is extended rather than rewritten.
    """
    rows = entry.get('lines') or []
    off = entry.get('off_axis') or []
    if view in ('line', 'rungs') and not rows:
        return _no_line_caption(scen, entry, facts)
    if view == 'line':
        out = _decides_sentence(scen, rows[0])
        if len(rows) > 1:
            out += (f" It is the lowest of {brief._n(len(rows))} "
                    f"{brief.AXIS_WORD[rows[0]['axis']]} lines in {scen} "
                    f"shields.")
        if rows[0]['is_floor']:
            # A statement about the SET, not about the cell. The same value
            # can be the page's line and be owned in THIS scenario by a
            # different opponent (0v0 Marowak against 0v1 Annihilape on
            # Sableye GL), and "it is this page's own line" then read as a
            # claim about the cell that the evidence table contradicts.
            out += (f" These are the same {brief._n(rows[0]['n_pass'])} "
                    f"spreads as this page's line.")
        return (out + _off_axis_sentence(scen, off)
                + _degeneracy_tail(scen, entry) + _scope_tail(rows, off))
    if view == 'rungs':
        if len(rows) == 1:
            out = (_decides_sentence(scen, rows[0])
                   + f" It is the only "
                     f"{brief.AXIS_WORD[rows[0]['axis']]} line in {scen} "
                     f"shields.")
        else:
            out = _rungs_head(scen, rows)
        return (out + _off_axis_sentence(scen, off)
                + _degeneracy_tail(scen, entry) + _scope_tail(rows, off))
    if view == 'trade':
        return (f"{base} Counted over every shield scenario; the y-axis here "
                f"is {scen} wins only.")
    if view == 'builds':
        return (f"The same builds, drawn against their {scen} shields win "
                f"count only. Which builds these ARE is still the Build "
                f"criteria preset's answer; this control moves the y axis, "
                f"not the selection.")
    if view == 'stats':
        # The stats view's axes are DEFENSE and HP, which no shield state
        # moves: the control changes only what the hover counts. Saying so
        # is the whole caption -- the alternative is a reader expecting the
        # picture to change and reading the unchanged one as a bug. NOT the
        # whole STATS_CAPTION with a clause bolted on: this string is
        # emitted once per shield scenario, so repeating a 900-character
        # caption nine times is nine copies of it in every file's payload.
        return (f"Defense against HP, builds in their own colours, each "
                f"outlined where it is a region on this plane. These axes "
                f"do not move with the shield state; with {scen} selected "
                f"the hover counts {scen} wins.")
    if view == 'clusters':
        return (f"The Matchup clusters section's own groups for {scen} "
                f"shields, drawn here on the same axes.")
    if view == 'rank1':
        out = (f"Every spread on this grid, by stat product rank against "
               f"its {scen} shields win count.")
        # A NEGATIVE page offers neither threshold view, so a shield state
        # that does carry a line of its own had nowhere to say so -- and this
        # is the page whose reader most wants to know ("is there really
        # nothing, even in one shield state?").
        if facts['floor'] is None and rows:
            said = _decides_sentence(scen, rows[0], where='')
            out += (f" {scen} shields does carry a threshold of its own: "
                    f"{said[0].lower()}{said[1:]}"
                    f"{_off_axis_sentence(scen, off)}"
                    f"{_degeneracy_tail(scen, entry)} It is not this page's "
                    f"line: a line has to hold across the other baked "
                    f"opponent-IV settings as well, and this one is not "
                    f"checked against them.")
        return out
    return base


def scenario_payload(facts, pay):
    """``pay['scen']``: per shield scenario, its lines and its captions.

    Lines are emitted only on a page that HAS a line: the two views that draw
    them ("the line", "the rungs") exist only there, and a payload carrying
    groups no view can select is a payload that has to be kept honest for
    nothing.

    A line costs a label, five numbers and (so far always) an empty
    exceptions list -- see :func:`rounded_cut`. No per-IV array, packed or
    otherwise, enters the payload through this control.
    """
    base = {v['id']: v['caption'] for v in pay['views']}
    view_ids = [v['id'] for v in pay['views']]
    has_floor = facts['floor'] is not None
    out = {}
    for scen in facts['header']['scenarios']:
        entry = (facts.get('scenario_lines') or {}).get(scen) or {
            'lines': [], 'off_axis': [], 'closest': None,
            'degenerate': False, 'win_lo': 0, 'win_hi': 0,
            'n_opp': int(facts['header']['pool_size'])}
        rows = []
        if has_floor:
            for row in entry['lines']:
                sel = facts['_masks']['lines'][line_key(row['axis'], row['T'])]
                rows.append({
                    'axis': row['axis'],
                    'axisWord': brief.AXIS_WORD[row['axis']],
                    'printed': _axis_value(row),
                    'n': int(row['n_pass']),
                    'kind': row['kind'],
                    'cut': sel['cut'], 'wrong': sel['wrong'],
                    'isFloor': bool(row['is_floor']),
                    'label': scen_line_label(scen, row, short=True),
                    'full': scen_line_label(scen, row)})
        # The captions are authored against the ENTRY, not against ``rows``:
        # on a page with no line of its own a scenario can still have one,
        # and a caption that said "no line here" because this payload drops
        # the group would be false. The two views that would draw it do not
        # exist on that page; the caption still never lies about the data.
        out[scen] = {
            'lines': rows,
            'degenerate': bool(entry['degenerate']),
            'captions': {vid: scenario_caption(vid, scen, entry, facts,
                                               base.get(vid, ''))
                         for vid in view_ids}}
    return out


def build_payload(facts, fields, moveset_idx, mode='pvpoke',
                  all_facts=None, arm_builds=None):
    """The section plot's inline JSON.

    Thresholds, marked spreads, and one packed membership mask per printed
    threshold. Everything else the panel draws with -- attack / defense / HP,
    stat-product rank, the score grid it counts wins from, the Matchup
    clusters labels -- is already embedded once on the page and is read from
    there; a second copy of the 4096-point stats is exactly what this payload
    exists to avoid. The masks are not that copy: they are the
    classification, which the page's 2-dp stats cannot reproduce (see
    :func:`mask_b64`), at 512 bytes each.
    """
    fl = facts['floor']
    r1 = facts['rank1']
    gb = facts['grid_best']
    views = VIEWS_FLOOR if fl is not None else VIEWS_NO_FLOOR
    has_builds = bool(arm_builds and arm_builds['presets'])
    if has_builds:
        views = (VIEW_BUILDS, VIEW_STATS) + tuple(views)
    pay = {
        'mi': int(moveset_idx),
        'mode': mode,
        'hasFloor': fl is not None,
        'rank1': {'iv': [int(x) for x in r1['ivs']],
                  'level': float(r1['level'])},
        'gridBest': {'iv': [int(x) for x in gb['ivs']],
                     'level': float(gb['level']),
                     'nTied': int(gb['n_tied'])},
        'views': [{'id': vid, 'label': lbl,
                   'caption': _caption_for(vid, facts, fields, all_facts)}
                  for vid, lbl in views],
        # The corroboration line the clusters caption quotes is computed on
        # the ALL-scenario concatenated fingerprint, so that is the partition
        # the view draws. Key comes from the clusters module, not a literal:
        # the payload it has to match is keyed by the same constant.
        'clusterScen': (brief.clusters.ALL_SCEN_KEY
                        if facts.get('cluster_corroboration') else None),
        'examples': [], 'rungs': [], 'alt': None,
    }
    if fl is not None:
        pay['axis'] = fl['axis']
        pay['axisWord'] = brief.AXIS_WORD[fl['axis']]
        pay['T'] = float(fl['T'])
        pay['printed'] = printed_value(fl)
        pay['cell'] = fl['cell']
        pay['nAbove'] = int(fl['n_above'])
        # How many clearers the expander lists before the "show all" control.
        # In the payload, not a JS literal: the two sides would otherwise
        # drift and the button would promise a count the table does not show.
        pay['topN'] = CLEARER_TOP_N
        masks = facts['_masks']
        pay['rungs'].append(
            {'axis': fl['axis'], 'T': float(fl['T']), 'n': int(fl['n_above']),
             'mask': masks['rungs'][0],
             'label': _rung_label(fl['printed'], fl['dp'], [fl['cell']], 1,
                                  short=True),
             'full': _rung_label(fl['printed'], fl['dp'], [fl['cell']], 1)})
        for k, row in enumerate(facts.get('rungs_above') or []):
            pay['rungs'].append(
                {'axis': fl['axis'], 'T': float(row['T']),
                 'n': int(row['n_pass']), 'mask': masks['rungs'][k + 1],
                 'label': _rung_label(row['printed'], row['dp'],
                                      row['names'], row['n_cells'],
                                      short=True),
                 'full': _rung_label(row['printed'], row['dp'],
                                     row['names'], row['n_cells'])})
        # The light-theme ramp, for the same reason WB_FALLBACK exists in the
        # engine: getComputedStyle can come back empty and a trace with no
        # color is a legend key pointing at invisible points. The CSS
        # properties are what normally drives the colors, so the ramp still
        # re-themes with the picker.
        pay['rungColors'] = rung_ramp(len(pay['rungs']), 'light')
        pay['examples'] = [
            {'iv': [int(x) for x in ex['ivs']], 'level': float(ex['level']),
             'rule': ex['rule'], 'label': example_label(ex['rule'])}
             for ex in example_spreads(facts)]
        # The spread the headline names as winning the most above the line.
        # It is NOT one of the examples whenever the example rules' stat-
        # product filter excludes it, and a reader who just read that
        # sentence and clicked Compare did not find the spread it named.
        cost = facts.get('floor_cost') or {}
        best = cost.get('best_ivs')
        if best is not None:
            best = [int(x) for x in best]
            known = [list(e['iv']) for e in pay['examples']]
            known.append([int(x) for x in facts['rank1']['ivs']])
            if best not in known:
                pay['bestAbove'] = {
                    'iv': best,
                    'label': 'wins the most matchups above the line'}
        alt = facts.get('alternative')
        if alt is not None and not alt['too_wide']:
            pay['alt'] = {'label': brief.alt_pair_short(alt),
                          'mask': facts['_masks']['alt'],
                          'n': int(alt['n'])}
    # ---- the section's own Shield scenario control ------------------------
    # Labels in grid order, from the brief's header, which built them with
    # the same deep_dive_rendering.scenario_label the page's DATA.
    # scenarioLabels comes from -- the panel looks a selected label up in
    # THAT array to get the index it slices the score grid with, so the two
    # vocabularies cannot drift apart.
    pay['scenLabels'] = list(facts['header']['scenarios'])
    pay['band'] = [float(x) for x in brief.DECISION_BAND]
    pay['scen'] = scenario_payload(facts, pay)
    # The scenario ladder's own ramp, sized to the longest ladder the control
    # can select. See ramp_css: the page's --wb-r* ramp stays sized to the
    # page's own rungs, so the default view does not move.
    pay['nScenRamp'] = max([len(e['lines']) for e in pay['scen'].values()]
                           + [0])
    if pay['nScenRamp']:
        pay['scenColors'] = rung_ramp(pay['nScenRamp'], 'light')
    # ---- v4: the builds half ---------------------------------------------
    # One nested object rather than a second <script> block: the section is
    # re-parented wholesale into an inert <template> by the best-buddy L51
    # pass, and one payload per section is what survives that unchanged.
    if has_builds:
        pay['bp'] = builds.builds_payload(
            arm_builds, moveset_idx, mode=mode,
            prose=builds_prose(facts, arm_builds, all_facts))
        pay['bp']['colors'] = list(BUILD_COLORS)
        pay['bp']['topN'] = CLEARER_TOP_N
    return pay


def compare_spreads(facts, arm_builds=None, preset=None):
    """The spreads the "Compare these spreads" button prefills, in order.

    Rank-1 first (it is the build a reader most likely already has), then the
    brief's example spreads -- or, with no line, the spread that wins the
    most matchups, which is the only other spread the page names.

    v5 appends the section's two STANDOUTS -- the spread that wins the most
    matchups and the one with the highest Avg Battle Score -- because the
    standouts block names both and a reader who just read it and clicked
    Compare did not find either (2026-09-16 review item 3). Deduplicated
    against everything already listed, so a standout that IS an example or
    IS rank-1 does not appear twice.
    """
    r1 = facts['rank1']
    out = [('rank-1', [int(x) for x in r1['ivs']])]
    if facts['floor'] is not None:
        for ex in example_spreads(facts):
            out.append((example_label(ex['rule']),
                        [int(x) for x in ex['ivs']]))
        cost = facts.get('floor_cost') or {}
        best = cost.get('best_ivs')
        if best is not None:
            best = [int(x) for x in best]
            if best not in [iv for _rule, iv in out]:
                out.append(('wins the most matchups above the line', best))
    else:
        gb = facts['grid_best']
        if list(gb['ivs']) != list(r1['ivs']):
            out.append(('wins the most matchups',
                        [int(x) for x in gb['ivs']]))
    for rule, iv in standout_spreads(arm_builds, preset):
        if iv not in [x for _r, x in out]:
            out.append((rule, iv))
    return out


def standout_spreads(arm_builds, preset=None):
    """(label, [a, d, s]) for each standout of one preset, in block order."""
    if not arm_builds or not arm_builds.get('presets'):
        return []
    key = preset or (builds.PRESET_FLAT
                     if builds.PRESET_FLAT in arm_builds['presets']
                     else next(iter(arm_builds['presets'])))
    bl = arm_builds['presets'].get(key)
    out = []
    for t in (bl or {}).get('standouts') or []:
        ivs = [int(x) for x in t['iv'].split('@')[0].split('/')]
        out.append((STANDOUT_KIND.get(t['kind'], t['kind']), ivs))
    return out


# ---------------------------------------------------------------------------
# CSS. Scoped under the section id, drawn from the page's own theme tokens.
# ---------------------------------------------------------------------------

# Palette. Chosen OUTSIDE the page's win / loss / tie / notable hues so a
# reader cannot read a section group as an outcome -- the mockup's pink for
# the bulk pair sat 20 degrees from --loss on the hue wheel and is now a
# magenta 45 away -- and every value clears 3:1 against its own theme's plot
# fill, including the FIRST rung step, which is the floor itself and so the
# most important group on the panel. The ramp runs dark-to-light on a dark
# canvas and light-to-dark on a light one, which is why there are two of
# everything.
# tests/test_which_build_section.py::test_section_palette_is_legible_in_every
# _theme recomputes the ratios from theme.py, so a re-valued token fails there
# rather than shipping an invisible legend entry.
CSS = """
#dd-which-build { background: var(--surface); padding: 14px 18px;
  border-radius: 8px; margin: 16px 0; border: 1px solid var(--border);
  --wb-line: #7a4fc0; --wb-below: #7f858f; --wb-alt: #a63089;
  --wb-mark1: #16706a; --wb-mark2: #2f5fd0; }
[data-theme="gruvbox-dark"] #dd-which-build,
[data-theme="pokemon-dark"] #dd-which-build {
  --wb-line: #b18cf0; --wb-below: #9aa3ad; --wb-alt: #ec93d6;
  --wb-mark1: #55d9c9; --wb-mark2: #8fb4ff; }
#dd-which-build > summary { cursor: pointer; font-size: 1.05rem;
  color: var(--title); list-style: revert; padding: 2px 0; }
#dd-which-build > summary b { color: var(--title); margin-right: 6px; }
#dd-which-build > summary .wb-head { font-weight: 400; color: var(--text);
  font-size: 0.92rem; }
#dd-which-build .wb-body { margin-top: 10px; }
#dd-which-build .wb-lead { font-size: 0.92rem; margin: 0 0 10px; }
#dd-which-build .strip { display: grid; grid-template-columns: 8.5rem 1fr;
  gap: 2px 12px; margin: 12px 0; padding: 10px 12px;
  background: var(--surface-2); border: 1px solid var(--border-2);
  border-radius: 6px; font-size: 0.85rem; }
#dd-which-build .strip dt { color: var(--text-muted); font-weight: 600;
  letter-spacing: .04em; text-transform: uppercase; font-size: .72rem;
  padding-top: 3px; }
#dd-which-build .strip dd { margin: 0; }
@media (max-width: 34rem) {
  #dd-which-build .strip { grid-template-columns: 1fr; }
  #dd-which-build .strip dd { margin: 0 0 6px; } }
#dd-which-build .wb-headline { border-left: 3px solid var(--accent);
  padding-left: 12px; margin: 12px 0 16px; }
#dd-which-build .wb-headline p { margin: 0 0 10px; font-size: 0.95rem; }
#dd-which-build .field { margin: 0 0 16px; }
#dd-which-build .field h3 { font-size: .74rem; letter-spacing: .09em;
  text-transform: uppercase; color: var(--text-muted); margin: 0 0 6px;
  font-weight: 600; }
#dd-which-build .field p { margin: 0 0 6px; font-size: 0.88rem; }
#dd-which-build .note { color: var(--text-muted); font-size: 0.85rem; }
#dd-which-build .tw { overflow-x: auto; margin: 8px 0; }
#dd-which-build table { border-collapse: collapse; font-size: 0.82rem;
  min-width: 100%; }
#dd-which-build th, #dd-which-build td { text-align: left;
  padding: 4px 10px 4px 0; vertical-align: top;
  border-bottom: 1px solid var(--border); white-space: nowrap; }
#dd-which-build th { color: var(--text-muted); font-weight: 600; }
#dd-which-build td.wrapcell, #dd-which-build th.wrapcell {
  white-space: normal; min-width: 16rem; }
#dd-which-build .wb-evidence, #dd-which-build .wb-guards {
  margin-top: 14px; border-top: 1px solid var(--border); padding-top: 10px; }
#dd-which-build .wb-evidence > summary, #dd-which-build .wb-guards > summary {
  cursor: pointer; font-size: .78rem; color: var(--text-muted);
  letter-spacing: .05em; text-transform: uppercase; font-weight: 600; }
#dd-which-build .wb-term { border-bottom: 1px dotted currentColor;
  text-decoration: none; cursor: help; }
#dd-which-build .wb-term-link { color: var(--accent); text-decoration: none; }
#dd-which-build .wb-val { background: none; border: 0; padding: 0;
  font: inherit; color: var(--accent); cursor: pointer;
  border-bottom: 1px dashed currentColor; }
#dd-which-build .wb-clearers { margin: 0 0 12px; padding: 8px 10px;
  background: var(--surface-2); border: 1px solid var(--border-2);
  border-radius: 6px; font-size: 0.82rem; max-height: 320px;
  overflow-y: auto; }
#dd-which-build .wb-btn { background: var(--accent); color: var(--surface);
  border: 0; border-radius: 4px; padding: 6px 12px; font-size: 0.86rem;
  font-weight: 600; cursor: pointer; }
#dd-which-build .wb-btn:hover { filter: brightness(1.1); }
#dd-which-build .wb-spreads { font-size: 0.82rem; color: var(--text-muted);
  margin-left: 8px; }
#dd-which-build .wb-plotbox { margin: 12px 0; }
#dd-which-build .wb-controls { display: flex; flex-wrap: wrap;
  align-items: center; gap: 6px 18px; font-size: 0.85rem; }
#dd-which-build .wb-controls label { white-space: nowrap; }
#dd-which-build .wb-panel { height: 400px; min-height: 400px; }
#dd-which-build .wb-caption { font-size: 0.85rem; color: var(--text-muted);
  margin: 4px 0 0; }
#dd-which-build .wb-fixed { font-size: 0.78rem; color: var(--text-muted);
  margin: 4px 0 0; }
#dd-which-build .wb-terms { display: grid; grid-template-columns: auto 1fr;
  gap: 2px 12px; margin: 14px 0 0; padding: 10px 12px; font-size: 0.82rem;
  background: var(--surface-2); border: 1px solid var(--border-2);
  border-radius: 6px; }
#dd-which-build .wb-terms dt { font-weight: 600; white-space: nowrap; }
#dd-which-build .wb-terms dd { margin: 0; color: var(--text-muted); }
#dd-which-build .wb-terms a { color: var(--accent); }
#dd-which-build .wb-terms-head { font-size: .74rem; letter-spacing: .09em;
  text-transform: uppercase; color: var(--text-muted); margin: 14px 0 0;
  font-weight: 600; }
@media (max-width: 34rem) {
  #dd-which-build .wb-terms { grid-template-columns: 1fr; }
  #dd-which-build .wb-terms dd { margin: 0 0 6px; } }
/* ---- v4: builds ---- */
#dd-which-build { --wb-b0: #7a4fc0; --wb-b1: #c0682a; --wb-b2: #16706a; }
[data-theme="gruvbox-dark"] #dd-which-build,
[data-theme="pokemon-dark"] #dd-which-build {
  --wb-b0: #b18cf0; --wb-b1: #f0a860; --wb-b2: #55d9c9; }
#dd-which-build .wb-builds { margin: 12px 0 16px; }
#dd-which-build .wb-builds-lead { font-size: 0.9rem; margin: 0 0 8px; }
#dd-which-build .wb-builds-table { width: 100%; }
#dd-which-build .wb-builds-table td { white-space: normal; }
#dd-which-build .wb-fid { color: var(--text-muted); font-size: 0.76rem; }
#dd-which-build .wb-swatch { display: inline-block; width: 10px;
  height: 10px; border-radius: 2px; margin-right: 6px;
  background: var(--wb-b0); }
#dd-which-build .wb-swatch[data-build="1"] { background: var(--wb-b1); }
#dd-which-build .wb-swatch[data-build="2"] { background: var(--wb-b2); }
/* The wide region borrows Build 1's colour at the tint the panel draws it
   in, whatever index its row carries. */
#dd-which-build .wb-swatch.wb-wide { background: var(--wb-b0); opacity: 0.4; }
#dd-which-build .wb-obj { font-size: 0.86rem; margin: 8px 0 0; }
#dd-which-build .wb-weighting { font-size: 0.78rem; color: var(--text-muted);
  margin: 8px 0 0; }
#dd-which-build .wb-build { margin: 8px 0 0; }
#dd-which-build .wb-build > summary { cursor: pointer; font-size: 0.84rem;
  color: var(--text-muted); }
#dd-which-build .wb-g-list { font-size: 0.82rem; margin: 6px 0;
  padding-left: 18px; }
#dd-which-build .wb-g-list ul { padding-left: 16px; margin: 2px 0 6px; }
#dd-which-build .wb-more, #dd-which-build .wb-free { color: var(--text-muted); }
#dd-which-build .wb-g-head { font-size: 0.8rem; color: var(--text-muted);
  margin: 6px 0 0; }
#dd-which-build .wb-upset-caption { font-size: 0.82rem;
  color: var(--text-muted); margin: 4px 0 0; }
#dd-which-build .wb-mem-head { font-size: .74rem; letter-spacing: .09em;
  text-transform: uppercase; color: var(--text-muted); margin: 10px 0 4px;
  font-weight: 600; }
#dd-which-build .wb-mem { font-size: 0.8rem; max-height: 260px;
  overflow-y: auto; background: var(--surface-2);
  border: 1px solid var(--border-2); border-radius: 6px; padding: 6px 10px; }
/* ---- v5: outside-rate emphasis, paragraphs, standouts ---- */
/* Three nested bands, strongest last, so the rarest guarantee on the page is
   also the loudest run of type on it. wb-o0 is the near-free tail: present,
   readable, and visibly not what the build is buying. */
#dd-which-build .wb-o1 { font-weight: 700; }
#dd-which-build .wb-o2 { font-weight: 700; text-decoration: underline; }
#dd-which-build .wb-o3 { font-weight: 700; text-decoration: underline;
  font-style: italic; }
#dd-which-build .wb-o0 { color: var(--text-muted); opacity: 0.75; }
#dd-which-build .wb-para { font-size: 0.92rem; margin: 0 0 10px; }
#dd-which-build .wb-para b { color: var(--title); }
#dd-which-build .wb-standouts { margin: 14px 0 0; padding: 10px 12px;
  background: var(--surface-2); border: 1px solid var(--border-2);
  border-radius: 6px; }
#dd-which-build .wb-standouts .wb-mem-head { margin-top: 0; }
#dd-which-build .wb-standout-note { font-size: 0.82rem;
  color: var(--text-muted); margin: 6px 0 0; }
#dd-which-build .wb-mem { font-size: 0.8rem; line-height: 1.5; }
#dd-which-build .wb-plotrow { display: flex; flex-wrap: wrap; gap: 10px; }
#dd-which-build .wb-upset { flex: 1 1 320px; min-width: 300px; height: 400px; }
#dd-which-build .wb-plotrow .wb-panel { flex: 2 1 420px; min-width: 320px; }
"""


# ---------------------------------------------------------------------------
# BUILDS (v4). The section's primary object: 2-3 regions of the IV grid per
# moveset, selected under the reader's Build-criteria preset.
# ---------------------------------------------------------------------------
# Vocabulary added by this block (docs style rule, per document):
#
# - Build: a region of the IV grid a player can aim at -- an intersection of
#   the named sets, at least 50 spreads.
# - Fork: a build with no spread in common with the primary that also
#   guarantees a different set of matchups.
# - Decision cell / decision matchup: a (shield scenario, opponent) pair the
#   IV choice decides -- top-50 opponent, and the whole grid's win rate on it
#   strictly inside 2%-98%.
# - Guaranteed: every spread in the build wins it.
# - Outside rate: how often the spreads OUTSIDE the build win that same cell.
# - Material: a cell no single-stat threshold rule of 100+ spreads wins at
#   more than 95%.
# - Preset: one of the three Build-criteria weightings.

# Reader-facing name per selected role, in selection order.
ROLE_NAME = {'primary': 'Build 1 (primary)',
             'fork': 'Build 2 (fork)',
             'rank1': 'Build 3 (bulk)',
             # Not a build of its own: the region AROUND Build 1, printed
             # under it (2026-09-17 round 5, item 4).
             'wide': 'Build 1 wide'}
# The same names without their role parenthetical, for the paragraphs and
# the collapsed line -- one mapping, so the table and the prose can never
# call one build two things.
ROLE_SHORT = {'primary': 'Build 1', 'fork': 'Build 2', 'rank1': 'Build 3',
              'wide': 'Build 1 wide'}


def role_short(b, i=0):
    return ROLE_SHORT.get(b['role'], f"Build {i + 1}")
# Guarantee rows printed per shield scenario before the "+N more" control.
# Four, not more: three presets x up to three builds x up to nine shield
# scenarios means every extra row is emitted ~80 times on one file, and the
# counts a reader is actually comparing are in the table above the lists.
GUARANTEE_CAP = 4
# A cell the rest of the grid wins at more than this is near-free: the build
# is not what got it. Counted in a trailing sentence rather than listed.
NEAR_FREE = 0.90
# Outside-rate emphasis (2026-09-16 review, item 5). Every guarantee row on
# the page, in the cards and in the standouts block is weighted by how RARE
# the guarantee is -- a cell the rest of the grid wins 92% of the time and a
# cell it wins 10% of the time were one typeface apart, and the second is the
# only one the build is really buying. Bands are inclusive upper bounds,
# strongest first; anything above NEAR_FREE is dimmed instead.
EMPH_BANDS = ((0.10, 'wb-o3'), (0.25, 'wb-o2'), (0.50, 'wb-o1'))
# It sits directly under the lead, BEFORE the paragraphs: the paragraphs use
# the typefaces and print "(outside 10%)" on their own rarest cells, so a key
# under the table below them explained a notation the reader had already met
# (2026-09-16 round-3 review). It also defines both rates the page prints --
# the build's outside rate and the whole grid's rate, which the Standouts
# block and the card use -- because the same three typefaces carry both.
EMPH_KEY = ("Rates: outside N% is the share of the spreads NOT in that build "
            "that win the same matchup anyway; grid N% (the Standouts block "
            "and the cards at the top of the page) is the share of all the "
            "spreads on the grid. Weight follows the rate: bold = fewer than "
            "half of them win it; bold and underlined = fewer than a "
            "quarter; bold, underlined and italic = fewer than a tenth; "
            "dim = more than nine in ten win it anyway.")


def emph_class(rate):
    """The emphasis class for one outside rate, or '' for the middle band."""
    if rate is None:
        return ''
    r = float(rate)
    for bar, cls in EMPH_BANDS:
        if r <= bar:
            return cls
    return 'wb-o0' if r > NEAR_FREE else ''


def _pct(x):
    return f"{round(float(x) * 100):.0f}%"


def _fidelity_clause(b):
    """How well the printed description reproduces the member list."""
    d = b['description']
    if d is None:
        return ('no two- or three-stat rule fits it; the list is the '
                + ('region' if b.get('role') == 'wide' else 'build'))
    j = float(d['jaccard'])
    if j >= 0.999:
        return 'exactly these spreads'
    return (f"{_pct(j)} of the same spreads "
            f"({brief._n(d['n_extra'])} extra, "
            f"{brief._n(d['n_missing'])} missed)")


def build_desc(b, steps=True):
    """The build's rule, or the honest "list of N" when none fits.

    ``steps`` prints a staircase's actual steps. A staircase description is
    unusable without them -- that is the 2026-09-16 review's own finding --
    so the TABLE always prints them; the one-line summary prints the RANGE
    instead, because eight "HP 115 -> Def 103.16" pairs in the collapsed
    summary bury the sentence a reader opened the page for, and the bare
    "Def >= d(HP)" the summary used to carry is notation nothing on the page
    defines.
    """
    d = b['description']
    if d is None:
        return f"list of {brief._n(b['size'])} spreads"
    rule = builds.display_rule(d['rule'])
    if d.get('steps'):
        if not steps:
            head = rule.split(' and Def >= d(HP)')[0]
            hps = [h for h, _d, _n, _p in d['steps']]
            defs = [dd for _h, dd, _n, _p in d['steps']]
            # Floor the low end and ceil the high one, so the printed band
            # CONTAINS every step of the staircase. Rounding either end to
            # nearest would print a range that excludes a real step by up to
            # half a hundredth, and the summary is what a reader acts on
            # before opening the table.
            lo = math.floor(min(defs) * 100) / 100
            hi = math.ceil(max(defs) * 100) / 100
            return (f"{head} and Def >= {lo:.2f}-{hi:.2f} depending on HP "
                    f"({min(hps):g}-{max(hps):g}; "
                    f"{brief._n(len(d['steps']))} steps, in the table)")
        # The step's PRINTED decimal (the 4th field), not the raw float:
        # formatting the float rounds half-up, above the true floor, and a
        # reader applying the printed rule then excluded the boundary member
        # of every step (2026-09-16 round-3 review: the printed rule
        # reproduced 57 of the build's 61 spreads).
        pairs = '; '.join(f"HP {h:g} -> Def {pr:g}"
                          for h, _dd, _n, pr in d['steps'])
        return f"{rule}: {pairs}"
    return rule


# The one set the header's own "Alternative" row is built from. Only a build
# whose region IS that set may call itself "the bulk box": the definite
# article was attached to any Def/HP rectangle, so one page called two
# different boxes "the bulk box" and printed a third number for the header's
# own (2026-09-16 round-3 review).
ALT_SET_NAME = 'S2 alternative rectangle'


def is_bulk_box(b):
    """A build whose rule is a defense floor AND an HP floor, nothing else.

    Item 8(a) of the 2026-09-16 review: "the bulk rectangle" was a name for
    a shape the page never drew, because the section plot's axes are
    stat-product rank and matchups won. It is called the bulk BOX in prose
    from here on, and the stats view draws it as an actual rectangle on the
    Def / HP axes -- the one plane where it is one.
    """
    d = b['description']
    if not d or not d.get('terms'):
        return False
    terms = {ax: op for ax, op, _t in d['terms']}
    return terms == {'def': '>=', 'hp': '>='}


def is_header_bulk_box(b, facts):
    """Is this build's region exactly the rectangle the header names?"""
    alt = (facts or {}).get('alternative') or {}
    return (bool(alt.get('n')) and is_bulk_box(b)
            and list(b.get('sets') or []) == [ALT_SET_NAME])


def header_bulk_rule(facts):
    """That rectangle's thresholds as the HEADER prints them.

    One box, one pair of numbers on the page: the describer's own decimals
    select the same spreads but print differently ("Def >= 120.00" under a
    header row that says "Def >= 120.03"), which reads as two boxes.
    """
    alt = facts['alternative']
    return ' and '.join(
        brief.stat_threshold_str(ax, alt[key_p], alt[key_dp])
        for key_p, key_dp, key_free, ax in (
            ('printed_a', 'dp_a', 'free_a', alt['axes'][0]),
            ('printed_b', 'dp_b', 'free_b', alt['axes'][1]))
        if not alt[key_free])


def rule_is_approx(b):
    """Does the printed rule fail to reproduce its own member list?

    The builds table already says so in its fidelity clause ("99% of the
    same spreads (1 extra, 1 missed)"), but the summary line, the paragraph
    and the card title printed the same rule as if it were exact -- a
    known-wrong number carried on three surfaces and flagged on one
    (2026-09-16 round-3 review).
    """
    d = b['description']
    return bool(d) and bool(d.get('n_extra') or d.get('n_missing'))


def _approx(b, rule):
    """A rule that does not reproduce its own build is printed as "roughly"."""
    return f"roughly {rule}" if rule_is_approx(b) else rule


def approx_clause(b):
    """The sentence a paragraph adds when its rule is the approximate one."""
    if not rule_is_approx(b):
        return ''
    d = b['description']
    n_x, n_m = int(d['n_extra']), int(d['n_missing'])
    bits = []
    if n_x:
        bits.append(f"takes in {brief._n(n_x)} "
                    f"{brief._noun(n_x, 'spread')} that "
                    f"{'is not a member' if n_x == 1 else 'are not members'}")
    if n_m:
        bits.append(f"misses {brief._n(n_m)}")
    what = 'region' if b.get('role') == 'wide' else 'build'
    return (f"That rule {' and '.join(bits)}; the member list in the table "
            f"is the {what}.")


def build_rule_phrase(b, facts=None):
    """One build's rule as a PARAGRAPH reads it, after "at ".

    The staircase prints its defense BAND and the HP range it spans rather
    than its four steps: the steps are in the table, and a paragraph that
    carries eight "HP 115 -> Def 103.16" pairs buries the sentence.
    """
    d = b['description']
    if d is None:
        return (f"no two- or three-stat rule -- one of {brief._n(b['size'])} "
                f"spreads whose IV box is in the table")
    if d.get('steps'):
        head = builds.stair_atk_head(d)
        hps = [h for h, _d, _n, _p in d['steps']]
        defs = [dd for _h, dd, _n, _p in d['steps']]
        lo = math.floor(min(defs) * 100) / 100
        hi = math.ceil(max(defs) * 100) / 100
        return _approx(b, f"{head} with Def >= {lo:.2f} to {hi:.2f} "
                          f"depending on HP ({min(hps):g}-{max(hps):g})")
    if is_header_bulk_box(b, facts):
        return f"the bulk box, {header_bulk_rule(facts)}"
    rule = _approx(b, builds.display_rule(d['rule']))
    if is_bulk_box(b):
        return f"a Def/HP box, {rule}"
    return rule


def build_summary_phrase(b, facts=None):
    """The same rule inside the collapsed one-line summary's parenthesis."""
    d = b['description']
    if d is None:
        return 'no rule fits it; its IV box is in the table'
    if is_header_bulk_box(b, facts):
        return f"the bulk box {header_bulk_rule(facts)}"
    if is_bulk_box(b):
        return f"a Def/HP box {_approx(b, builds.display_rule(d['rule']))}"
    return _approx(b, build_desc(b, steps=False))


def rank1_iv(arm_builds):
    """The stat-product rank-1 spread, as the builds' own "a/d/s@lv" string."""
    ctx = arm_builds['ctx']
    return builds.iv_str(ctx['meta'], int(np.argmin(ctx['sp_rank'])))


def build_envelope(b):
    """The IV box a ruleless build lives in, and what else is in that box.

    A build the describers cannot fit is printed as "list of N spreads",
    which is honest and unusable. The envelope gives a reader something to
    aim at WITHOUT selling it as the region: its own sentence says how many
    spreads inside the box are not members.
    """
    env = b.get('iv_envelope')
    if not env:
        return ''
    return (f"all inside attack IV {env['atk'][0]}-{env['atk'][1]}, "
            f"defense IV {env['def'][0]}-{env['def'][1]}, "
            f"HP IV {env['hp'][0]}-{env['hp'][1]}; that box also holds "
            f"{brief._n(env['n_outside'])} "
            f"{brief._noun(env['n_outside'], 'spread')} that "
            f"{'is not a member' if env['n_outside'] == 1 else 'are not members'}")


def _scen_weighted(bl, scen_labels):
    """The scenarios this preset counts, as a printable clause."""
    live = [scen_labels[i] for i, w in enumerate(bl['weights']) if w > 0]
    if len(live) == len(scen_labels):
        return 'all ' + brief._n(len(live)) + ' shield scenarios'
    return ' / '.join(live) + ' shields'


def _flat(bl):
    """Does this preset count every shield scenario the dive baked?"""
    return all(w > 0 for w in bl['weights'])


def _guarantee_phrase(arm_builds, bl, b, article=True):
    """What one build guarantees, in the preset's own terms first.

    The RANKING counts only the scenarios the preset weights, so under a
    narrow preset that count leads and the all-nine count follows as the
    qualifier. Before the 2026-09-16 review the page printed the all-nine
    count in the summary and the table and the WEIGHTED gap in the sentence
    between them, so a reader subtracting the table's columns got a number
    the sentence did not contain. Under the default preset the two counts
    are the same number and only one is printed.
    """
    n_all = arm_builds['n_decision_cells']
    the = 'the ' if article else ''
    if _flat(bl):
        return (f"{brief._n(b['n_guaranteed'])} of {the}{brief._n(n_all)} "
                f"decision matchups")
    scens = _scen_weighted(bl, arm_builds['ctx']['scen_labels'])
    return (f"{brief._n(b['n_guaranteed_weighted'])} of {the}"
            f"{brief._n(bl['n_decision_weighted'])} decision matchups in "
            f"{scens} ({brief._n(b['n_guaranteed'])} of all "
            f"{brief._n(n_all)})")


def _guarantee_short(arm_builds, bl, b, material=False):
    """The same two counts, for a table cell.

    ``material`` attaches the material count to the OVERALL number it is a
    count of: "53 of 87 overall (0 material)" left a reader guessing whether
    the 0 was out of 53 or out of the 29 printed beside it.
    """
    n_all = arm_builds['n_decision_cells']
    mat = (f", {b['n_guaranteed_material']} of them material" if material
           else '')
    if _flat(bl):
        return f"{b['n_guaranteed']} of {n_all}{mat}"
    scens = _scen_weighted(bl, arm_builds['ctx']['scen_labels'])
    return (f"{b['n_guaranteed_weighted']} of {bl['n_decision_weighted']} in "
            f"{scens}; {b['n_guaranteed']} of {n_all} overall{mat}")


def _wins_phrase(bl, b):
    """A most-winning member's count, never without its denominator.

    The member is chosen -- and the section plot's y axis drawn -- on the
    preset's weighted win count, so "378 matchups" on a page whose axis
    reads "of 76" was two scales one paragraph apart.
    """
    mw = b['most_winning_member']
    return f"{mw['wins']} of {mw['denominator']} matchups"


def _wide_keeps(arm_builds, bl, wide, prim, material=False):
    """What the wide region KEEPS of the build it is wide around.

    Never a bare count. The wide region contains every member of the
    primary, so every cell it guarantees is one the primary guarantees too:
    a bare "guarantees 33" printed after a clause that said "guarantees 43"
    read as 33 MORE cells when it is in fact 33 OF those 43 (2026-09-17
    round 6 review). It is also on the preset's own scale, like every other
    count in the same sentence -- the clause used the all-nine number under
    every preset.
    """
    pname = role_short(prim, 0)
    mat = wide['n_guaranteed_material']
    # Attached to the ALL-NINE count it is a count of, inside that number's
    # own bracket -- the rule the builds' paragraphs use. Appended after the
    # bracket it gave a sentence two parentheticals in a row.
    tail = ('none of them material' if not mat
            else f"{brief._n(mat)} of them material")
    if _flat(bl):
        return (f"keeps {brief._n(wide['n_guaranteed'])} of {pname}'s "
                f"{brief._n(prim['n_guaranteed'])} guaranteed matchups"
                + (f" ({tail})" if material else ''))
    scens = _scen_weighted(bl, arm_builds['ctx']['scen_labels'])
    return (f"keeps {brief._n(wide['n_guaranteed_weighted'])} of {pname}'s "
            f"{brief._n(prim['n_guaranteed_weighted'])} guaranteed matchups "
            f"in {scens} ({brief._n(wide['n_guaranteed'])} of its "
            f"{brief._n(prim['n_guaranteed'])} overall"
            + (f", {tail})" if material else ')'))


def _wide_clause(arm_builds, bl):
    """The collapsed line's clause for the wide region, or ''.

    A clause, not a build slot: the summary stays as many builds long as the
    section selected, and says the two things about the wide region a reader
    who never opens the section can act on -- how much of Build 1's
    guarantee survives out to it, and whether it reaches a standout no build
    holds. The standout half is printed only when it DOES reach one: "holds
    neither standout" is a non-finding, and it was the clause the headline
    ended on (2026-09-17 round 5 item 4, corrected by the round 6 reviews).
    """
    wide = (bl or {}).get('wide')
    if not wide or not (bl.get('builds') or []):
        return ''
    out = (f"; {role_short(wide)} ({brief._n(wide['size'])} spreads) "
           f"{_wide_keeps(arm_builds, bl, wide, bl['builds'][0])}")
    outside = [t for t in (bl.get('standouts') or []) if t['in_build'] is None]
    held = [t for t in outside if t.get('in_wide')]
    if held and len(held) == len(outside):
        out += (' and holds both standouts' if len(outside) > 1
                else ' and holds the standout')
    elif held:
        out += f" and holds {brief._n(len(held))} of the standouts"
    return out


def _negative_bridge(arm_builds, bl, facts):
    """One clause joining a "zero matchups wide" summary to the builds table.

    The v3 negative sentence is about TOTAL wins and stays -- Michael's
    2026-09-16 call. Standing alone beside a builds table that guarantees 29
    of 51 decision matchups it read as a contradiction, so the summary now
    says in one clause that the OTHER question does move.
    """
    if not bl or not bl['builds']:
        return ''
    # Named, in the same voice as the paragraphs and the table below: the
    # clause used to call them "the 55-spread build" and "a disjoint
    # 64-spread build" while every other surface on the page called the same
    # two regions Build 1 and Build 2 (2026-09-16 round-3 review).
    p = bl['builds'][0]
    out = (f" Which matchups you win still moves: {role_short(p, 0)} "
           f"({brief._n(p['size'])} spreads, "
           f"{build_summary_phrase(p, facts)}) guarantees "
           f"{_guarantee_phrase(arm_builds, bl, p)}")
    rest = bl['builds'][1:]
    if rest:
        f = rest[0]
        n = (f['n_guaranteed_weighted'] if not _flat(bl) else f['n_guaranteed'])
        out += (f"; {role_short(f, 1)} ({brief._n(f['size'])} spreads, "
                f"disjoint from it) guarantees {brief._n(n)} others")
    return out + _wide_clause(arm_builds, bl) + '.'


# How many guaranteed cells a paragraph, a card or the standouts block
# names before it stops. Three: they are sorted rarest-first, and the fourth
# is already the table's job.
TOP_CELLS = 3
# The fixed sentence the standouts block ends on. Authored once, gated with
# the rest of the module's prose, and quoted by the card set too, so the two
# surfaces cannot explain the same thing two ways.
STANDOUT_NOTE = (
    f"A build is a region of at least {builds.MIN_BUILD} spreads that all win "
    f"a common core of matchups, and no region that size reproduces the "
    f"matchup profile of a spread above. If you already have one of them, "
    f"build it: each is the top of this grid on the measure that named it. "
    f"If you are hunting, hunt a build instead{{window}}. What this page "
    f"cannot give you is a region that lands you on one of these profiles.")
# The window clause, when the page can name both of its edges. Filled from the
# brief's own floor, the primary build's printed attack rung and the bulk of
# the standouts themselves -- never hard-coded: the numbers are per-page
# (2026-09-17 round 5 item 3; round 6 replaced "is a few spreads wide" with
# the counted width, and prints the bulk cuts the count was taken at so a
# reader can reproduce it).
STANDOUT_WINDOW = (", because the window these spreads sit in (between "
                   "{line} and {rung}, at their own bulk of {bulk}) holds "
                   "{n} of the {grid} spreads on this grid")
_ATK_HEAD = re.compile(r'Atk >= ([0-9.]+)')


def build_atk_floor(b):
    """One build's attack floor as the page PRINTS it, or None.

    Read off the rule's own printed text rather than re-formatted from
    ``atk_floor``: two-place formatting of the raw selected value rounds a
    150.245638 cut UP to 150.25, a bar 0.01 above the cut the build is made
    at (see ``builds.stair_atk_head``).
    """
    d = b.get('description')
    if not d:
        return None
    m = _ATK_HEAD.search(builds.display_rule(d['rule']))
    return m.group(1) if m else None


def standout_note(facts, arm_builds, bl):
    """The fixed sentence the standouts block ends on, for THIS page.

    The window clause is printed only when the page can name both edges AND
    every standout outside a build actually sits between them: a sentence
    locating a spread in a window it is not in would be the one dishonesty
    this block cannot afford. Both numbers come from the page's own facts --
    the brief's line, and the primary build's printed attack rung.
    """
    window = ''
    fl = facts.get('floor')
    builds_list = bl['builds'] if bl else []
    rung = build_atk_floor(builds_list[0]) if builds_list else None
    ctx = arm_builds['ctx']
    if fl is not None and rung is not None and fl.get('axis') == 'atk':
        # ``fl['printed']`` is the number; printed_value is the STRING the
        # headline speaks, which carries the proven selector in brackets when
        # the line needed three decimals ("123.42 (123.419)") and is not a
        # float.
        lo, hi = float(fl['printed']), float(rung)
        outside = [t for t in (bl.get('standouts') or [])
                   if t['in_build'] is None]
        if lo < hi and outside and all(lo <= t['atk'] < hi for t in outside):
            kind = ((fl.get('mech') or {}).get('kind') or '')
            name = ('the charge-move-priority line'
                    if kind == 'cmp' else 'the line')
            # The bulk cuts are the standouts' own, TRUNCATED to the two
            # places the page prints -- not rounded: a rounded 96.3469 prints
            # 96.35, and the count taken at 96.35 excludes the very spread
            # the sentence is about.
            d0 = math.floor(min(t['def'] for t in outside) * 100) / 100
            h0 = int(min(t['hp'] for t in outside))
            pl = ctx['planes']
            n_win = int(((pl['atk'] >= lo) & (pl['atk'] < hi)
                         & (pl['def'] >= d0) & (pl['hp'] >= h0)).sum())
            window = STANDOUT_WINDOW.format(
                line=f"{name} at {printed_value(fl)}",
                rung=f"{role_short(builds_list[0], 0)}'s {rung} attack rung",
                bulk=f"Def >= {d0:.2f} and HP >= {h0}",
                n=brief._n(n_win), grid=brief._n(ctx['n_iv']))
    return STANDOUT_NOTE.format(window=window)
# The same point when both standouts sit INSIDE a build, which the fixed
# note above argues a case the page does not have (2026-09-16 round-3
# review: it shipped on the plain-Sableye and Melmetal pages).
STANDOUT_NOTE_INSIDE = (
    "Every standout here sits inside a build. What a region guarantees, it "
    "guarantees to every one of its members; the rest of what one exact "
    "spread wins is what that spread adds on top of the region. Hunting it "
    "is legitimate -- in a limited meta especially -- but it is a different "
    "plan from building a region.")
# The block's own heads: the canonical short name first, its qualifier
# after, so the head, the card title and the chip all start with the same
# words (2026-09-17 round 6 review).
STANDOUT_KIND = {
    'wins': 'Most matchups won (all nine shield scenarios)',
    'score': "Highest avg battle score (the scatter's own y axis)",
    'both': ("Most matchups won (all nine shield scenarios) and highest avg "
             "battle score"),
}


def _cell_phrase(r, rate_key='outside_wr', word='outside'):
    """One named cell with its rate, carrying the emphasis class."""
    rate = r[rate_key]
    cls = emph_class(rate)
    body = (f'{_esc(r["cell"])} ({_esc(word)} {_esc(_pct(rate))})')
    return f'<span class="{cls}">{body}</span>' if cls else body


# A cell in the "some members win it too" tail rather than in the printed
# list. A quarter of a build's members is Michael's cut (2026-09-17 round 5):
# above it the cell is one the region hands out often enough that naming it
# beside cells no member wins would flatten the distinction the list is about.
MEMBER_SHARE_TAIL = 0.25


def _share_cell_phrase(r):
    """One cell this spread wins beyond its build, with BOTH rates.

    The emphasis band is the GRID rate (the page's one emphasis spelling, and
    the rate a single spread has); the member share is what the sentence is
    about, so both are printed -- an emphasis keyed to a number the reader
    cannot see is the failure the emphasis key exists to prevent.
    """
    cls = emph_class(r['grid_wr'])
    body = (f'{_esc(r["cell"])} (grid {_esc(_pct(r["grid_wr"]))}; '
            f'{_esc(_pct(r["share"]))} of members)')
    return f'<span class="{cls}">{body}</span>' if cls else body


def _beyond_cells_html(rows, nm, size):
    """The cells one standout wins that its nearest build does not guarantee.

    Split at :data:`MEMBER_SHARE_TAIL`: the cells almost no member of the
    build wins are the content, and the ones a quarter or more of them win
    go to a counted tail.
    """
    listed = [r for r in rows if r['share'] <= MEMBER_SHARE_TAIL]
    tail = len(rows) - len(listed)
    out = (f"The other {brief._n(len(rows))} are matchups {_esc(nm)} does not "
           f"guarantee")
    if listed:
        out += (f", with the share of its {brief._n(size)} members that win "
                f"each: " + brief._and_list(
                    [_share_cell_phrase(r) for r in listed]))
    if tail:
        out += (f"; and {brief._n(tail)} more that more than a quarter of "
                f"its members win" if listed else
                f" -- every one of them won by more than a quarter of its "
                f"{brief._n(size)} members")
    return out + '.'


def _lost_cells_html(rows, nm, n_guaranteed):
    """The cells the nearest build guarantees and this spread does not win."""
    body = brief._and_list([_cell_phrase(r, 'grid_wr', 'grid') for r in rows])
    return (f"It loses {brief._n(len(rows))} of the "
            f"{brief._n(n_guaranteed)} matchups {_esc(nm)} guarantees to "
            f"every member: {body}.")


def _short_cells(rows, n=TOP_CELLS):
    """" (A, B, C and 4 more)" -- plain text, for a card. '' when empty."""
    rows = list(rows or [])
    if not rows:
        return ''
    named = ', '.join(r['cell'] for r in rows[:n])
    more = ('' if len(rows) <= n
            else f" and {brief._n(len(rows) - n)} more")
    return f" ({named}{more})"


def _top_cells_html(rows, rate_key='outside_wr', word='outside', n=TOP_CELLS):
    """The rarest few guaranteed cells, in the page's one emphasis spelling."""
    top = sorted(rows, key=lambda r: (r[rate_key], r['rank']))[:n]
    return brief._and_list([_cell_phrase(r, rate_key, word) for r in top])


def _paragraph_guarantee(arm_builds, bl, b):
    """What one build guarantees, with the material count attached cleanly.

    Under a narrow preset the count phrase already ends in a bracket ("... in
    0v0 / 1v1 / 2v2 shields (43 of all 76)"), so appending "(2 of them
    material)" gave a sentence two parentheticals in a row and left a reader
    guessing which number the 2 was out of. The material count is over ALL
    the decision cells, so it is attached to the all-nine number it is a
    count of -- the same rule the builds table uses.
    """
    mat = b['n_guaranteed_material']
    n_all = arm_builds['n_decision_cells']
    if _flat(bl):
        return (f"{_guarantee_phrase(arm_builds, bl, b)} "
                f"({brief._n(mat)} of them material)")
    scens = _scen_weighted(bl, arm_builds['ctx']['scen_labels'])
    # "and 44 of all 87 with 0 of those material" was a sentence a reader
    # had to re-read; the count goes in its own bracket on the number it is
    # a count of (2026-09-16 round-3 review).
    return (f"{brief._n(b['n_guaranteed_weighted'])} of the "
            f"{brief._n(bl['n_decision_weighted'])} decision matchups in "
            f"{scens}, and {brief._n(b['n_guaranteed'])} of all "
            f"{brief._n(n_all)} "
            + ('(none of them material)' if not mat
               else f"({brief._n(mat)} of them material)"))


def counted_guaranteed(arm_builds, bl, b):
    """One build's guaranteed cells the PRESET counts, and whether it fell back.

    The paragraph opens "guarantees 29 of the 43 decision matchups in 0v0 /
    1v1 / 2v2 shields" and then names its most notable three. Taken from all
    nine scenarios, the lead example was a matchup the preset does not count
    -- the sentence contradicting itself one line down (2026-09-16 round-3
    review). Falls back to all nine only when the counted scenarios cannot
    fill the list, and the caller then says so.
    """
    rows = b['guaranteed']
    if _flat(bl) or not rows:
        return rows, False
    labels = arm_builds['ctx']['scen_labels']
    counted = {labels[i] for i, w in enumerate(bl['weights']) if w > 0}
    kept = [r for r in rows if r['scenario'] in counted]
    if len(kept) >= TOP_CELLS:
        return kept, False
    return rows, True


def build_paragraph(facts, arm_builds, bl, b, i, all_facts=None):
    """One build, as a paragraph, in the descriptive voice.

    Michael's 2026-09-16 wording, field for field: what the build IS (the
    focal, its moveset and the rule), what it guarantees and the rarest
    three of those, what it gives up to the other builds, its most-winning
    member with that member's denominator, and where stat-product rank-1
    sits relative to it. No "should" and no "most X" -- the page describes
    the regions and leaves the choice to the reader.
    """
    who = _esc(brief.focal_name(facts['header']))
    moveset = _esc(display_moveset(facts['header']['arm_label']))
    name = _esc(role_short(b, i))
    if b['description'] is None:
        # A build no rule fits is a LIST. "has Sableye running Shadow Claw /
        # Drain Punch, Foul Play at no two- or three-stat rule" was not a
        # sentence (2026-09-16 round-3 review).
        out = [f'<b>{name}</b> is a list of {brief._n(b["size"])} {who} '
               f'spreads ({moveset}) that no two- or three-stat rule fits; '
               f'its IV envelope is in the table.']
    else:
        out = [f'<b>{name}</b> has {who} running {moveset} at '
               f'{_esc(build_rule_phrase(b, facts))}.']
        clause = approx_clause(b)
        if clause:
            out.append(_esc(clause))
    g = 'It guarantees ' + _esc(_paragraph_guarantee(arm_builds, bl, b))
    top, all_nine = counted_guaranteed(arm_builds, bl, b)
    if top:
        g += ', most notably ' + _top_cells_html(top)
        if all_nine:
            g += ' (over all nine shield scenarios)'
    gave = b['gives_up']
    if gave:
        names = brief._and_list(
            [f"{_esc(r['cell'])} (rank {r['rank']})"
             for r in gave[:TOP_CELLS]])
        tail = ('' if len(gave) <= TOP_CELLS
                else f", and {brief._n(len(gave) - TOP_CELLS)} more")
        g += f'; it gives up {names}{tail}'
    else:
        g += '; it gives up nothing the other builds guarantee'
    out.append(g + '.')
    mw = b['most_winning_member']
    # When the most-winning member IS stat-product rank-1, "rank-1 is inside
    # it" made a reader hunt the table for which member that was.
    tail = (', which is SP1'
            if mw['iv'] == rank1_iv(arm_builds)
            else f"; SP1 is "
                 f"{'inside' if b['rank1_in'] else 'outside'} it")
    out.append(f"Its most-winning member is {_esc(mw['iv'].split('@')[0])} "
               f"({mw['wins']} of {mw['denominator']}){tail}.")
    return '<p class="wb-para">' + ' '.join(out) + '</p>'


def wide_phrase(wide, facts=None):
    """What "Build 1 wide" IS, in one phrase: its RULE first, or None.

    The rule is the thing a reader can aim at. "Build 1 without the 1v0
    Azumarill staircase" is a gloss on it -- and until the 2026-09-17 round
    6 review it was ALL the page printed for a region that was simply
    ``Atk >= 150.24``, handing the reader an internal lattice-set alias the
    page defines nowhere in place of a one-stat rule. The gloss is kept
    where the difference from the primary is exactly one dropped set; a
    region that also ADDS a set is not "Build 1 without" anything.
    """
    rule = build_rule_phrase(wide, facts) if wide.get('description') else None
    gloss = None
    if len(wide.get('_dropped') or []) == 1 and not wide.get('_added'):
        lbl = builds.set_short_label(wide['_dropped'][0])
        art = '' if lbl.startswith('the ') else 'the '
        gloss = f"{ROLE_SHORT['primary']} without {art}{lbl}"
    if rule and gloss:
        return f"{rule} -- {gloss}"
    return rule or gloss


def _wide_lost_rows(arm_builds, prim, wide):
    """The cells the primary guarantees and the wide region does not."""
    cells = arm_builds['frame']['cells']
    g, wg = prim.get('_g'), wide.get('_g')
    if g is None or wg is None:
        return []
    rows = [{'cell': c['label'], 'rank': c['rank'] or 0,
             'grid_wr': float(c['wr'])}
            for ci, c in enumerate(cells) if g[ci] and not wg[ci]]
    rows.sort(key=lambda r: (r['grid_wr'], r['rank']))
    return rows


def wide_paragraph(facts, arm_builds, bl, wide, all_facts=None):
    """The wide region's paragraph, printed directly under Build 1's.

    It opens on what the region is FOR. Round 5 printed its size, its
    overlap and its guarantee count and left the reader to work out why a
    third region with fewer guarantees was being named at all (2026-09-17
    round 6 review).
    """
    name = _esc(role_short(wide))
    prim = bl['builds'][0]
    pname = _esc(role_short(prim, 0))
    phrase = wide_phrase(wide, facts)
    lead = (f"<b>{name}</b> is the looser target around {pname}, for a "
            f"reader who cannot hit {pname} exactly")
    if phrase is None:
        # Same shape as build_paragraph's no-rule branch: "is the region
        # around Build 1: no two- or three-stat rule" was not a sentence.
        # The selection rule requires a printable rule, so this is a guard.
        out = [f"{lead}: a list of {brief._n(wide['size'])} spreads that no "
               f"two- or three-stat rule fits, with its IV envelope in the "
               f"table."]
    else:
        out = [f"{lead}: {_esc(phrase)}."]
    clause = approx_clause(wide)
    if clause:
        out.append(_esc(clause))
    keep = (f"It holds every one of {pname}'s "
            f"{brief._n(wide['_primary_size'])} spreads in "
            f"{brief._n(wide['size'])} of its own, and "
            f"{_esc(_wide_keeps(arm_builds, bl, wide, prim, material=True))}")
    lost = _wide_lost_rows(arm_builds, prim, wide)
    if lost:
        keep += (f"; the {brief._n(len(lost))} it gives up out here are "
                 + _top_cells_html(lost, 'grid_wr', 'grid')
                 + ('' if len(lost) <= TOP_CELLS
                    else f", and {brief._n(len(lost) - TOP_CELLS)} more"))
    out.append(keep + '.')
    # Which standouts it holds -- a wider rule that reaches a spread no build
    # reaches is a different offer from one that does not, and a reader who
    # is here BECAUSE of a standout needs to be told when this is not a route
    # to it.
    outside = [t for t in (bl.get('standouts') or []) if t['in_build'] is None]
    if outside:
        held = [t for t in outside if t.get('in_wide')]
        if not held:
            out.append('It holds neither standout below, so it is not a '
                       'route to them.' if len(outside) > 1
                       else 'It does not hold the standout below, so it is '
                            'not a route to it.')
        elif len(held) == len(outside):
            out.append('It holds both standouts below.' if len(outside) > 1
                       else 'It holds the standout below.')
        else:
            out.append('It holds ' + brief._and_list(
                [_esc(t['iv'].split('@')[0]) for t in held])
                + ' of the standouts below, and not ' + brief._and_list(
                [_esc(t['iv'].split('@')[0]) for t in outside
                 if not t.get('in_wide')]) + '.')
    # A region every one of whose spreads is already in a build draws no
    # points of its own on the plot, and Plotly drops the empty trace: the
    # row and this paragraph would otherwise name a 249-spread region the
    # reader cannot find on either interactive surface (round 6 review).
    if wide.get('_own') == 0:
        out.append('On the plot it adds no points: every spread it holds is '
                   'already in a build.')
    return '<p class="wb-para">' + ' '.join(out) + '</p>'


def build_paragraphs_html(facts, arm_builds, preset, all_facts=None):
    """Every build of one preset, one paragraph each.

    The wide region's paragraph goes directly under the primary's, which is
    the build it is wide AROUND; it is not one of ``bl['builds']``.
    """
    bl = arm_builds['presets'].get(preset)
    if not bl or not bl['builds']:
        return ''
    out = []
    for i, b in enumerate(bl['builds']):
        out.append(build_paragraph(facts, arm_builds, bl, b, i, all_facts))
        if b['role'] == 'primary' and bl.get('wide'):
            out.append(wide_paragraph(facts, arm_builds, bl, bl['wide'],
                                      all_facts))
    return ''.join(out)


def standout_rows(arm_builds, idx):
    """The decision cells ONE spread wins, with the whole grid's rate on each.

    A build's rows carry an OUTSIDE rate -- how often the spreads not in it
    win the same cell -- which is a property of a region and has no meaning
    for a single spread. The honest analogue is the grid's own win rate on
    that cell, which is already on the cell, and the page says which of the
    two it is printing every time it prints one.
    """
    ctx, frame = arm_builds['ctx'], arm_builds['frame']
    won = ctx['win2'][idx]
    return [dict(cell=c['label'], rank=c['rank'] or 0,
                 grid_wr=float(c['wr']))
            for c in frame['cells'] if won[c['k']]]


def standout_paragraph(facts, arm_builds, bl, t):
    """One standout spread: what it is, where it sits, what is its own."""
    rows = standout_rows(arm_builds, t['idx'])
    head = _esc(STANDOUT_KIND.get(t['kind'], t['kind']))
    iv = _esc(t['iv'].split('@')[0])
    near = t['nearest_build']
    # The EDGE, in the scale the preset counts (the paragraphs' rule): the
    # number that makes this spread a standout is only readable next to the
    # best a build can offer, which is its most-winning member's count
    # (2026-09-17 round 5, item 3(i)). Pre-round-5 the win count stood alone.
    if _flat(bl):
        wins_clause = (f'It wins {t["wins_all"]} of {t["denominator_all"]} '
                       f'matchups over all nine shield scenarios')
    else:
        scens = _scen_weighted(bl, arm_builds['ctx']['scen_labels'])
        wins_clause = (f'It wins {t["wins_weighted"]} of {t["denominator"]} '
                       f'matchups in {_esc(scens)}')
    if near is not None and t['in_build'] is None:
        # ``most_winning_member['wins']`` is already on the preset's scale,
        # which is why the two halves of this sentence can be compared.
        _nb = bl['builds'][near]
        wins_clause += (f"; {_esc(role_short(_nb, near))}'s most-winning "
                        f"member wins {_nb['most_winning_member']['wins']}")
    lines = [f'<b>{head}: {iv}</b> -- {t["atk"]:.2f} atk / {t["def"]:.2f} '
             f'def / {int(t["hp"])} hp, CP {t["cp"]}, stat-product rank '
             f'{t["sp_rank"]}, Avg Battle Score {t["avg_score"]:.1f}. '
             + wins_clause + '.']
    if t['in_build'] is None:
        if near is None:
            lines.append('It is in none of the builds, and this moveset has '
                         'no build to compare it against.')
        else:
            nb = bl['builds'][near]
            nm = role_short(nb, near)
            own, got = t['n_own_decision_wins'], t['n_from_nearest']
            # NOT "the other N are this one spread's own": those cells are
            # won by hundreds of other spreads -- what they lack is a
            # region-wide guarantee (2026-09-16 round-3 review). Round 5
            # replaces the counted remainder with the two LISTS behind it:
            # which matchups they are, and how much of the build wins each.
            wide = bl.get('wide')
            where = 'It is in none of the builds'
            if wide is not None and t.get('in_wide') is not None:
                where += (f", though {_esc(role_short(wide))} holds it"
                          if t['in_wide']
                          else f", and {_esc(role_short(wide))} does not "
                               f"hold it either")
            lines.append(
                f"{where}. Of the {own} decision "
                f"matchups it wins, {_esc(nm)} guarantees {got} to every one "
                f"of its {brief._n(nb['size'])} members.")
            if t.get('beyond_cells'):
                lines.append(_beyond_cells_html(t['beyond_cells'], nm,
                                                nb['size']))
            if t.get('lost_cells'):
                lines.append(_lost_cells_html(t['lost_cells'], nm,
                                              nb['n_guaranteed']))
            elif t['n_lost_from_nearest'] == 0:
                lines.append(f"It loses none of the {nb['n_guaranteed']} "
                             f"matchups {_esc(nm)} guarantees.")
        # The measured version of the block's closing claim. "No region that
        # size reproduces this profile" is a statement about regions; this is
        # the stronger one about SPREADS, and it is the one a careful reader
        # would otherwise doubt (2026-09-17 round 6 review).
        peers = t.get('n_profile_peers')
        if peers is not None and own:
            lines.append(
                f"No other spread on this grid wins all {own} of the decision "
                f"matchups it wins." if peers == 0 else
                f"Only {brief._n(peers)} other "
                f"{brief._noun(peers, 'spread')} on this grid "
                f"{'wins' if peers == 1 else 'win'} all {own} of the decision "
                f"matchups it wins.")
    else:
        nb = bl['builds'][t['in_build']]
        lines.append(f"It is a member of {_esc(role_short(nb, t['in_build']))}, "
                     f"which guarantees {t['n_from_nearest']} of the "
                     f"{t['n_own_decision_wins']} decision matchups it wins.")
    # "Its rarest wins" only on the INSIDE branch. Outside, the two lists
    # above already print every cell with its grid rate in the page's own
    # emphasis spelling, and this sentence named three of them a second time
    # (2026-09-17 round 6 review).
    if rows and t['in_build'] is not None:
        lines.append('Its rarest wins: '
                     + _top_cells_html(rows, 'grid_wr', 'grid') + '.')
    # No "It is 1 of the 4096 spreads on this grid": every spread is, and
    # the encounter-count sentence under the block already carries the
    # rarity (2026-09-16 round-3 review).
    return '<p class="wb-para">' + ' '.join(lines) + '</p>'


def _rarity_sentence(facts, arm_builds):
    """How rare ONE exact spread is, from the brief's own encounter model.

    Block-level, not per standout: the count is a property of the grid and
    the acquisition class, so it is the same sentence under every standout
    and printing it twice is two paragraphs of the same caveat.
    """
    ctx = arm_builds['ctx']
    meta = ctx['meta']
    n = ctx['n_iv']
    mask = np.zeros(n, dtype=bool)
    mask[0] = True
    acq = brief.acquisition_class(facts['header']['species'],
                                  facts['header']['shadow'])
    model = brief.catch_model(mask, meta, acq)
    rows = [r for r in model['rows'] if r['n'] is not None]
    if not rows:
        return ''
    counts = ', '.join(f"{brief._n(r['n'])} for a {_pct(r['target'])} chance"
                       for r in rows)
    if acq == 'grunt':
        source = ('Rocket-grunt encounters (this is a shadow, so it cannot '
                  'be traded)')
        caveat = ('the grunt IV floor is not verified here, and the count '
                  'assumes uniform-random IVs over the whole grid')
    elif acq == 'none':
        source = 'Encounters, whatever the source (this species has no wild spawn)'
        caveat = ('the count assumes uniform-random IVs, and the IV floor on '
                  'those sources is not modelled here')
    else:
        source = 'Wild catches'
        caveat = ('the count assumes uniform-random IVs over the whole grid, '
                  'which is a model of a wild encounter and is not verified '
                  'for any other source')
    return (f"{source} needed to meet one named spread out of the "
            f"{brief._n(n)} on this grid: {counts}. Model: {caveat}.")


def standouts_html(facts, arm_builds, preset, all_facts=None):
    """The Standouts block: the two spreads that can beat every build."""
    bl = arm_builds['presets'].get(preset)
    if not bl or not bl.get('standouts'):
        return ''
    body = ''.join(standout_paragraph(facts, arm_builds, bl, t)
                   for t in bl['standouts'])
    rarity = _rarity_sentence(facts, arm_builds)
    note = (standout_note(facts, arm_builds, bl)
            if any(t['in_build'] is None for t in bl['standouts'])
            else STANDOUT_NOTE_INSIDE)
    return ('<div class="wb-standouts"><p class="wb-mem-head">Standouts</p>'
            + body
            + (f'<p class="wb-standout-note">{_esc(rarity)}</p>'
               if rarity else '')
            + f'<p class="wb-standout-note">{_esc(note)}</p>'
            + '</div>')


def builds_summary(facts, arm_builds, preset, all_facts=None):
    """The collapsed summary line for one preset: the builds, named.

    "[all shields, equal] Build 1 (61 spreads, Atk >= 150.24 and Def >=
    97.15-99.63 depending on HP (119-122)) guarantees 55 of 87 decision
    matchups; Build 2 (114 spreads, the bulk box Def >= 101.40 and HP >=
    125) guarantees 41 and holds rank-1."

    Descriptive, in the same voice as the per-build paragraphs (2026-09-16
    review): it names every build the section selected, what each is and
    what each guarantees, and says which one holds stat-product rank-1 --
    or that none of them does. No directive: the page does not know the
    reader's team.

    A page with no line keeps the v3 negative summary, with the preset tag
    in front of it and one bridging clause after it.
    """
    bl = arm_builds['presets'].get(preset)
    if not bl or not bl['builds'] or facts['floor'] is None:
        # A page with no line keeps the v3 negative summary -- Michael's
        # 2026-09-16 call. Its two sentences say what a reader who reads only
        # the summary can do ("your rank-1 already wins more than anything
        # else"), which a builds sentence would displace rather than improve.
        base = summary_sentence(facts, all_facts)
        if not bl:
            return base
        return (f"[{builds.PRESET_TAG[preset]}] " + base
                + _negative_bridge(arm_builds, bl, facts))
    clauses = []
    holder = None
    n_all = arm_builds['n_decision_cells']
    for i, b in enumerate(bl['builds']):
        if b['rank1_in']:
            holder = i
        if i == 0:
            # The first clause carries the denominator (and, under a narrow
            # preset, both scales); the rest carry the count alone. Printing
            # "of 87 decision matchups" three times is the sentence a reader
            # gives up on halfway through.
            got = _guarantee_phrase(arm_builds, bl, b, article=False)
        elif _flat(bl):
            got = brief._n(b['n_guaranteed'])
        else:
            got = (f"{brief._n(b['n_guaranteed_weighted'])} of those "
                   f"({brief._n(b['n_guaranteed'])} of all "
                   f"{brief._n(n_all)})")
        clauses.append(
            f"{role_short(b, i)} ({brief._n(b['size'])} spreads, "
            f"{build_summary_phrase(b, facts)}) guarantees {got}")
    if holder is not None:
        clauses[holder] += ' and holds stat-product rank-1 (SP1)'
    out = f"[{builds.PRESET_TAG[preset]}] " + '; '.join(clauses)
    if holder is None:
        out += '; stat-product rank-1 (SP1) is in none of them'
    out += _wide_clause(arm_builds, bl)
    return out + '.'


# Titled by what the card SHOWS. "Highest battle score" printed no score
# and "Most wins" printed no win count, so the two standout cards carried
# the same "wins 62 of 87 decision matchups" line and nothing told them
# apart (2026-09-16 round-3 review).
# One canonical short name per standout, and every surface leads with it:
# the section head, the card title, the threat chips, the scatter overlay and
# the stealable bullets. Round 5 shipped three spellings each ("Highest Avg
# Battle Score (the scatter's own y axis)" / "Highest average battle score" /
# "Highest battle score"), the shortest of which dropped the word that says
# it is an AVERAGE (2026-09-17 round 6 review).
CARD_TITLE_SCORE = 'Highest avg battle score'
CARD_TITLE_WINS = 'Most matchups won (outside the builds)'
CARD_TITLE_BOTH = 'Most matchups won and highest avg battle score'
# What a build's card adds to its title when that build's most-winning
# member is ALSO a standout: the dedup dropped the standout card silently,
# so the card set lost a role the page had named.
# The SHORT form of each standout's card title, for surfaces that name a
# spread beside its IVs rather than above a block of prose: the scatter's
# chips in "Threats where your build choice matters". A build's short form is
# ``role_short`` ("Build 1"); these are the two that are not builds.
CARD_SHORT = {
    'score': 'Highest avg battle score',
    'wins': 'Most matchups won',
    'both': 'Most matchups won and highest avg battle score',
}
CARD_ALSO = {
    'both': 'also the highest avg battle score and the most matchups won',
    'score': 'also the highest avg battle score',
    'wins': 'also the most matchups won',
}


def card_title_rule(b, facts=None):
    """The build's rule, short enough to sit beside its name on a card."""
    d = b['description']
    if d is None:
        return f"{brief._n(b['size'])} spreads, no rule fits"
    if d.get('steps'):
        return _approx(b, f"{builds.stair_atk_head(d)} + Def/HP steps")
    if is_header_bulk_box(b, facts):
        return header_bulk_rule(facts)
    return _approx(b, builds.display_rule(d['rule']))


def card_specs(facts, arm_builds, preset=None):
    """The dive card's spreads, taken from the builds.

    One card per named build, showing that build's most-winning member;
    then the spread with the highest Avg Battle Score (the scatter's own y
    axis at its maximum); then, only when it belongs to no build, the
    spread that wins the most matchups. This retires the three POLES the
    card used to headline ("MATCHUP HUNTER", "MAX BULK") -- they were
    selected by a stat-extreme rule that no other surface on the page uses,
    so the card and the section named different spreads for different
    reasons (2026-09-16 review item 6).

    Computed under the page's DEFAULT Build criteria preset: the card is
    static HTML at the top of the page and does not follow the knob, and a
    card that silently meant a different preset than the one the section is
    showing would be worse than one that says which preset it is.

    Every spec carries a ``short`` name as well as its ``title``: the title
    heads a card, the short form labels one chip beside an IV spread in the
    dive's threat rows, where the rule would not fit.

    Returns ``[]`` when the arm has no builds, which is the signal to the
    renderer to fall back to the composite-score top picks.
    """
    if not arm_builds or not arm_builds.get('presets'):
        return []
    key = preset or (builds.PRESET_FLAT
                     if builds.PRESET_FLAT in arm_builds['presets']
                     else next(iter(arm_builds['presets'])))
    bl = arm_builds['presets'].get(key)
    if not bl or not bl['builds']:
        return []
    n_all = arm_builds['n_decision_cells']
    out, seen = [], {}

    def _add(spec):
        iv = tuple(spec['iv'])
        if iv in seen:
            return
        seen[iv] = spec
        out.append(spec)

    def _also(iv, kind):
        """Name the standout role on the card that already holds its spread."""
        spec = seen.get(tuple(iv))
        if spec and CARD_ALSO.get(kind):
            spec['title'] = f"{spec['title']} ({CARD_ALSO[kind]})"

    for i, b in enumerate(bl['builds']):
        mw = b['most_winning_member']
        _add({
            'iv': [int(x) for x in mw['iv'].split('@')[0].split('/')],
            'title': f"{role_short(b, i)}: {card_title_rule(b, facts)}",
            'short': role_short(b, i),
            'guarantee': (
                f"guarantees "
                f"{_guarantee_phrase(arm_builds, bl, b, article=False)} "
                f"({role_short(b, i)}); this is that build's most-winning "
                f"member, {mw['wins']} of {mw['denominator']}"),
            'cells': [{'text': f"{r['cell']} (rank {r['rank']})",
                       'rate': float(r['outside_wr']), 'word': 'outside'}
                      for r in b['guaranteed'][:TOP_CELLS]],
        })
    # Highest battle score first among the standouts, which is the order
    # Michael's card set names them in; the standouts BLOCK leads with the
    # most-winning spread, which is the order that block's own sentence
    # ("a single exceptional spread can out-win every build") argues in.
    order = {'both': 0, 'score': 1, 'wins': 2}
    for t in sorted(bl.get('standouts') or [],
                    key=lambda x: order.get(x['kind'], 9)):
        rows = sorted(standout_rows(arm_builds, t['idx']),
                      key=lambda r: (r['grid_wr'], r['rank']))
        near = t['nearest_build']
        own, got = t['n_own_decision_wins'], t['n_from_nearest']
        iv = [int(x) for x in t['iv'].split('@')[0].split('/')]
        if t['in_build'] is not None:
            nb = bl['builds'][t['in_build']]
            where = (f"it is in {role_short(nb, t['in_build'])}, which "
                     f"guarantees {got} of them")
        elif near is not None:
            nb = bl['builds'][near]
            nm = role_short(nb, near)
            # The same two lists the standouts block prints, in the short
            # form a card has room for: the first three of each (rarest
            # first) and a count for the rest (2026-09-17 round 5, item 3).
            wide = bl.get('wide')
            wide_clause = ''
            if wide is not None and t.get('in_wide') is not None:
                wide_clause = (f" ({role_short(wide)} "
                               f"{'holds' if t['in_wide'] else 'does not hold'}"
                               f" it)")
            where = (f"it is in none of the builds{wide_clause}; {nm} "
                     f"guarantees {got} of "
                     f"those to all {brief._n(nb['size'])} of its members. "
                     f"It wins {own - got} {nm} does not guarantee"
                     f"{_short_cells(t.get('beyond_cells'))} and loses "
                     f"{t['n_lost_from_nearest']} {nm} guarantees"
                     f"{_short_cells(t.get('lost_cells'))}")
        else:
            where = 'it is in none of the builds'
        if t['kind'] == 'wins' and t['in_build'] is not None:
            # A most-winning spread INSIDE a build is already on that
            # build's card, or is one of its members; it does not need a
            # card of its own titled "outside the builds". It does need its
            # role named on the card that holds it.
            _also(iv, t['kind'])
            continue
        title = {'score': CARD_TITLE_SCORE, 'wins': CARD_TITLE_WINS,
                 'both': CARD_TITLE_BOTH}[t['kind']]
        _also(iv, t['kind'])
        score = (f"Avg Battle Score {t['avg_score']:.1f} (the main "
                 f"scatter's y axis); " if t['kind'] != 'wins' else '')
        wins = f"wins {t['wins_all']} of {t['denominator_all']} matchups"
        if t['kind'] != 'score':
            wins += ', the most of any spread on this grid'
        _add({
            'iv': iv,
            'title': title,
            'short': CARD_SHORT.get(t['kind'], title),
            'guarantee': (f"{score}{wins}, and {own} of {n_all} decision "
                          f"matchups; {where}"),
            'cells': [{'text': f"{r['cell']} (rank {r['rank']})",
                       'rate': float(r['grid_wr']), 'word': 'grid'}
                      for r in rows[:TOP_CELLS]],
        })
    return out


def card_build_membership(arm_builds, preset=None):
    """``{'7/2/12': 'Build 1', ...}`` -- the named build each spread is in.

    Every MEMBER of every selected build, not just the card's spreads: the
    dive's "Top Picks" cards are chosen by their own composite score and then
    labelled with where they sit, which is only answerable from the masks.
    A spread in no build is simply absent, and the caller says "in no build".

    Computed under the page's DEFAULT preset, like :func:`card_specs`, and for
    the same reason: the cards are static HTML that does not follow the knob.
    """
    if not arm_builds or not arm_builds.get('presets'):
        return {}
    key = preset or (builds.PRESET_FLAT
                     if builds.PRESET_FLAT in arm_builds['presets']
                     else next(iter(arm_builds['presets'])))
    bl = arm_builds['presets'].get(key)
    if not bl or not bl['builds']:
        return {}
    meta = arm_builds['ctx']['meta']
    out = {}
    for i, b in enumerate(bl['builds']):
        name = role_short(b, i)
        for idx in np.nonzero(b['_mask'])[0]:
            out.setdefault(builds.iv_str(meta, int(idx)).split('@')[0], name)
    # The wide region LAST, so a spread in a real build is named by that
    # build. A pick the builds miss but the wide region holds was labelled
    # "in no build" on a page whose builds table names the same spread as the
    # wide region's most-winning member (2026-09-17 round 6 review).
    wide = bl.get('wide')
    if wide is not None and wide.get('_mask') is not None:
        name = f"{role_short(wide)} only"
        for idx in np.nonzero(wide['_mask'])[0]:
            out.setdefault(builds.iv_str(meta, int(idx)).split('@')[0], name)
    return out


def builds_lead(facts, arm_builds, preset, all_facts=None):
    """The sentence under the section's own lead: which preset, what it does."""
    bl = arm_builds['presets'].get(preset)
    if not bl:
        return ''
    scens = _scen_weighted(bl, arm_builds['ctx']['scen_labels'])
    n = len(bl['builds'])
    n_all = arm_builds['n_decision_cells']
    out = ''
    if facts['floor'] is None:
        # The negative page's headline and summary are about TOTAL wins,
        # which the IV choice barely moves here. The builds table answers a
        # different question and moves a lot; without this the two sit on one
        # screen contradicting each other (2026-09-16 review).
        out += ("This moveset has no single-stat line: the summary and "
                "headline above are about how many matchups a spread wins "
                "in total, which the IV choice barely moves here. The "
                "builds below answer the other question -- which matchups "
                "every spread in a region is guaranteed to win -- and that "
                "one does move. A build is chosen for that guarantee, so "
                "its box need not be the rectangle the headline names. ")
    out += (f"Build criteria: {builds.PRESET_LABEL[preset]} -- the builds "
            f"below are selected and ranked by what they guarantee in "
            f"{scens}. {brief._n(n)} "
            f"{brief._noun(n, 'build')} for this moveset, out of "
            f"{brief._n(n_all)} decision matchups "
            f"({brief._n(arm_builds['n_material_cells'])} of them material)")
    if not _flat(bl):
        out += (f"; {brief._n(bl['n_decision_weighted'])} of those sit in "
                f"{scens}, and that is the count the ranking uses")
    out += '.'
    tie = bl.get('top_tie')
    if tie:
        if tie['by'] == 'material':
            how = ('Build 1 is the one of them that guarantees the most '
                   'material matchups')
        else:
            how = (f"Build 1 is the largest of them "
                   f"({brief._n(tie['size'])} spreads)")
        out += (f" {brief._n(tie['n'])} candidate regions tie at "
                f"{brief._n(tie['weighted'])} guaranteed "
                f"{brief._noun(tie['weighted'], 'matchup')} in {scens}; "
                f"{how}.")
    if arm_builds.get('presets_identical'):
        out += (' The Build criteria preset does not change which builds '
                'this moveset gets.')
    # The one place the section spells the term out. Everything below -- the
    # paragraphs, the table's own column, the standouts -- writes SP1, which
    # is a name a reader meets a dozen times in one block (2026-09-17 round 5,
    # item 2). The collapsed summary line above the section defines it again,
    # because a reader who never opens the section sees only that line.
    out += (' Stat-product rank-1 (SP1) is the spread with the largest '
            'attack x defense x HP on this grid; it is written SP1 below.')
    return out


def objectives_line(arm_builds, preset):
    """The two objectives, printed only when they disagree.

    Both numbers carry their scope. The win gap is over the preset's
    weighted win count (the section plot's y axis, and the count the
    most-winning members were picked on); the cell gap is over the
    preset-weighted guaranteed-cell count, with the all-nine pair in
    brackets so it reconciles with the table above.
    """
    bl = arm_builds['presets'].get(preset)
    if not bl or not bl['builds']:
        return ''
    obj = bl['objectives'] or {}
    if not obj.get('split'):
        return ''
    by_cells = next(b for b in bl['builds']
                    if b['combo'] == obj['best_cells_build'])
    by_wins = next(b for b in bl['builds']
                   if b['combo'] == obj['best_wins_build'])
    win_gap = int(obj['win_gap'])
    cell_gap = int(obj['cell_gap'] if not _flat(bl) else obj['cell_gap_all'])
    if win_gap <= 0 or cell_gap <= 0:
        # The two objectives name different builds but neither gap is
        # positive: a tie broken on material or size. "Wins 0 more matchups"
        # is a sentence about nothing.
        return ''
    scens = _scen_weighted(bl, arm_builds['ctx']['scen_labels'])
    scope = 'overall' if _flat(bl) else f"in {scens}"
    out = (f"The two objectives disagree here: "
           f"{ROLE_NAME.get(by_wins['role'], by_wins['role'])}'s "
           f"most-winning spread "
           f"{by_wins['most_winning_member']['iv']} wins "
           f"{brief._n(win_gap)} more "
           f"{brief._noun(win_gap, 'matchup')} {scope} "
           f"({by_wins['most_winning_member']['wins']} against "
           f"{by_cells['most_winning_member']['wins']}, of "
           f"{by_wins['most_winning_member']['denominator']}), while "
           f"{ROLE_NAME.get(by_cells['role'], by_cells['role'])} guarantees "
           f"{brief._n(cell_gap)} more")
    if _flat(bl):
        out += (f" of the {brief._n(arm_builds['n_decision_cells'])} decision "
                f"matchups ({by_cells['n_guaranteed']} against "
                f"{by_wins['n_guaranteed']}).")
    else:
        out += (f" of the {brief._n(bl['n_decision_weighted'])} decision "
                f"matchups in {scens} "
                f"({by_cells['n_guaranteed_weighted']} against "
                f"{by_wins['n_guaranteed_weighted']}; "
                f"{by_cells['n_guaranteed']} against "
                f"{by_wins['n_guaranteed']} over all "
                f"{arm_builds['n_decision_cells']}).")
    return out


WEIGHTING_NOTE = (
    "The shield weighting above is the page's Build criteria preset. The "
    "tables list cells per shield scenario whatever the preset is; the "
    "preset changes which of them the ranking counts, so under a preset "
    "that counts fewer than all nine every count is printed twice -- in the "
    "counted scenarios first, then over all nine.")


_TAGS = re.compile(r'<[^>]+>')


def gate_text(html_fragment):
    """The reader-visible text of a fragment this module authored.

    The paragraphs and the standouts block carry markup (the build name is
    bold; a guaranteed cell carries its outside-rate emphasis class), and
    the brief's word gates read STRINGS. They are gated on exactly what a
    reader sees, so no banned word can enter the page inside an attribute-
    free run of prose just because it sat next to a tag.
    """
    txt = _TAGS.sub('', html_fragment)
    return _html.unescape(txt)


def builds_prose(facts, arm_builds, all_facts=None):
    """Every preset's authored sentences, for the payload.

    Authored HERE, not in the browser: these are the section's reader-facing
    prose, and the whole module's rule is that prose passes the brief's word
    gates before it reaches a page. :func:`prepare` gates exactly this dict.
    """
    out = {}
    for key in arm_builds['presets']:
        out[key] = {
            'summary': builds_summary(facts, arm_builds, key, all_facts),
            'lead': builds_lead(facts, arm_builds, key, all_facts),
            'objectives_line': objectives_line(arm_builds, key),
        }
    return out


def _g_row_html(r, n_modes, hidden=False, free=False):
    """One guaranteed cell. Visible and revealed rows share this spelling.

    ``free`` marks a near-free row -- one the spreads outside the build win
    over NEAR_FREE of the time anyway. Those ship hidden behind their own
    control (item 4) and under their own class, so the two reveals in one
    scenario group do not fire each other.
    """
    flags = []
    if r['material']:
        flags.append('material')
    # Only the SHORTFALL is printed: "holds in 3 of 3 opponent-IV modes" on
    # every one of a few hundred rows is the page's single biggest run of
    # bytes and its least informative words. The count of rows that hold
    # everywhere is in the table above.
    if r['modes_ok'] < n_modes:
        flags.append(f"holds in {r['modes_ok']} of {n_modes} "
                     f"opponent-IV modes")
    tail = ('; ' + '; '.join(flags)) if flags else ''
    cls = [emph_class(r['outside_wr'])]
    if hidden:
        cls.append('wb-hidfree' if free else 'wb-hid')
    cls = ' '.join(c for c in cls if c)
    attrs = (f' class="{cls}"' if cls else '') + (' hidden' if hidden else '')
    return (f'<li{attrs}>{_esc(r["cell"])} (rank {r["rank"]}) -- outside '
            f'{_esc(_pct(r["outside_wr"]))}{_esc(tail)}</li>')


def _guarantee_rows_html(arm_builds, b):
    """One build's guaranteed cells, grouped by shield scenario.

    Sorted by OUTSIDE RATE ascending inside each group -- the guarantee the
    rest of the grid is least likely to hand a reader anyway reads first --
    capped, with the near-free tail counted rather than listed.
    """
    n_modes = b['honesty']['n_modes']
    parts = []
    by_scen = b['guaranteed_by_scenario']
    # The term is printed HERE, once per list, for two reasons: the rows say
    # "outside 40%" and nothing else on the page defined that number, and
    # the glossary marker only reaches a term the page actually spells --
    # before this the "outside rate" entry existed and was unreachable
    # (2026-09-16 review).
    head = ('<p class="wb-g-head">Sorted by outside rate: how often the '
            'spreads NOT in this build win the same matchup anyway. The '
            'lower the rate, the rarer the guarantee.</p>')
    for scen in arm_builds['ctx']['scen_labels']:
        rows = by_scen.get(scen)
        if not rows:
            continue
        listed = [r for r in rows if r['outside_wr'] <= NEAR_FREE]
        free = len(rows) - len(listed)
        items = [_g_row_html(r, n_modes) for r in listed[:GUARANTEE_CAP]]
        rest = listed[len(items):]
        if rest:
            # A dead "+N more" leaves the full guarantee list unreachable,
            # which is the affordance half of the pre-dive grid. The rows are
            # already computed, so they ship HIDDEN and the control reveals
            # them rather than promising rows that do not exist.
            items.append(f'<li class="wb-more"><button type="button" '
                         f'class="wb-val" data-reveal="wb-hid" '
                         f'onclick="if(window.wbMoreRows)'
                         f'wbMoreRows(this)">Show {len(rest)} more in '
                         f'{_esc(scen)}</button></li>')
            for r in rest:
                items.append(_g_row_html(r, n_modes, hidden=True))
        tail = ''
        if free:
            # Click-to-show, not a bare count (2026-09-16 review, item 4).
            # The rows exist either way; a sentence that names them and then
            # does not let a reader see them is the affordance half of the
            # pre-dive grid all over again. They stay dim when revealed --
            # the emphasis class says what they are.
            hidden_free = [_g_row_html(r, n_modes, hidden=True, free=True)
                           for r in rows if r['outside_wr'] > NEAR_FREE]
            tail = (f'<li class="wb-free"><button type="button" '
                    f'class="wb-val" data-reveal="wb-hidfree" '
                    f'onclick="if(window.wbMoreRows)wbMoreRows(this)">'
                    f'{brief._n(free)} more '
                    f'{brief._noun(free, "cell")} here '
                    f'{"is" if free == 1 else "are"} near-free (the '
                    f'spreads outside this build win '
                    f'{"it" if free == 1 else "them"} over '
                    f'{_esc(_pct(NEAR_FREE))} of the time too): show '
                    f'{"it" if free == 1 else "them"} with '
                    f'{"its" if free == 1 else "their"} outside '
                    f'{brief._noun(free, "rate")}</button></li>'
                    + ''.join(hidden_free))
        parts.append(f'<li class="wb-sgroup"><b>{_esc(scen)}</b> '
                     f'({len(rows)})<ul>' + ''.join(items) + tail + '</ul></li>')
    if not parts:
        return '<p>No decision matchup is guaranteed by every member.</p>'
    return head + '<ul class="wb-g-list">' + ''.join(parts) + '</ul>'


def _gives_up_text(b):
    if not b['gives_up']:
        return 'nothing the other builds guarantee'
    names = [f"{r['cell']} (rank {r['rank']})" for r in b['gives_up'][:4]]
    tail = ('' if len(b['gives_up']) <= 4
            else f", +{len(b['gives_up']) - 4} more")
    return ', '.join(names) + tail


def builds_table_html(arm_builds, preset):
    """The builds table for one preset, plus its per-build expanders."""
    bl = arm_builds['presets'].get(preset)
    if not bl or not bl['builds']:
        return ''
    scens = _scen_weighted(bl, arm_builds['ctx']['scen_labels'])
    g_head = ('Guarantees' if _flat(bl)
              else 'Guarantees (in the counted shields / overall)')
    mw_head = ('Most-winning member' if _flat(bl)
               else f'Most-winning member (in {scens})')
    head = (f'<tr><th>Build</th><th>What it is</th><th>Spreads</th>'
            f'<th>{_esc(g_head)}</th><th>{_esc(mw_head)}</th>'
            f'<th>SP1</th>'
            f'<th>Gives up (guaranteed by another build, not this one)</th>'
            f'</tr>')
    rows = []

    def _row(b, i, extra='', cls='', mw_cell=None):
        mw = b['most_winning_member']
        env = build_envelope(b) if b['description'] is None else ''
        return (
            f'<tr data-build="{i}">'
            f'<td><span class="wb-swatch{cls}" data-build="{i}"></span>'
            f'{_esc(ROLE_NAME.get(b["role"], b["role"]))}</td>'
            f'<td>{_esc(build_desc(b))}'
            + (f'<br><span class="wb-fid">{_esc(env)}</span>' if env else '')
            + f'<br>'
            f'<span class="wb-fid">{_esc(_fidelity_clause(b))}</span></td>'
            f'<td>{brief._n(b["size"])}</td>'
            f'<td>{_esc(_guarantee_short(arm_builds, bl, b, material=True))}'
            f' ({b["n_scenarios_covered"]} shield '
            f'{brief._noun(b["n_scenarios_covered"], "scenario")}'
            + (f', {b["honesty"]["n_guaranteed_all_modes"]} holding in all '
               f'{b["honesty"]["n_modes"]} opponent-IV modes'
               if b['honesty']['n_modes'] > 1 else '')
            + ')</td>'
            + (f'<td>{mw_cell}</td>' if mw_cell is not None else
               f'<td>{_esc(mw["iv"])} -- {_esc(_wins_phrase(bl, b))}</td>')
            + f'<td>{"in" if b["rank1_in"] else "out"}</td>'
            f'<td>{extra or _esc(_gives_up_text(b))}</td>'
            f'</tr>')

    for i, b in enumerate(bl['builds']):
        rows.append(_row(b, i))
        # The wide region sits directly under the build it is wide around.
        # Its data-build index is its position in the PAYLOAD's builds array
        # (last), where the browser looks its mask up; the row's place in the
        # table is a reading order, not an index (2026-09-17 round 5).
        if b['role'] == 'primary' and bl.get('wide'):
            # No most-winning member for the wide region. The plot draws it
            # no triangle and "Compare these spreads" does not offer it --
            # both because it is not a build to build -- so a cell naming one
            # pointed at a spread the reader could then find on neither
            # interactive surface (2026-09-17 round 6 review).
            rows.append(_row(bl['wide'], len(bl['builds']),
                             extra='<span class="wb-fid">not a build of its '
                                   'own -- the region around Build 1</span>',
                             cls=' wb-wide', mw_cell='--'))
    out = ['<table class="wb-builds-table">', head] + rows + ['</table>']
    obj = objectives_line(arm_builds, preset)
    if obj:
        out.append(f'<p class="wb-obj">{_esc(obj)}</p>')
    for i, b in enumerate(bl['builds']):
        out.append(
            f'<details class="wb-build" data-build="{i}">'
            f'<summary>{_esc(ROLE_NAME.get(b["role"], b["role"]))}: what it '
            f'guarantees ({_esc(_guarantee_short(arm_builds, bl, b))}) and '
            f'its members ({brief._n(b["size"])})</summary>'
            + _guarantee_rows_html(arm_builds, b)
            + f'<p class="wb-mem-head">Members ({brief._n(b["size"])}), '
              f'highest stat product first</p>'
            + f'<div class="wb-mem" data-preset="{_esc(preset)}" '
              f'data-build="{i}"></div>'
            + '<p><button type="button" class="wb-btn" '
              'onclick="if(window.wbCompareBuilds)wbCompareBuilds(this)">'
              'Compare these</button>'
              '<span class="wb-spreads"></span></p>'
            + '</details>')
    return ''.join(out)


def builds_block_html(facts, arm_builds, all_facts):
    """Every preset's builds block; the inactive ones start hidden."""
    if not arm_builds or not arm_builds['presets']:
        return ''
    parts = ['<div class="wb-builds">']
    default = (builds.PRESET_FLAT if builds.PRESET_FLAT in arm_builds['presets']
               else next(iter(arm_builds['presets'])))
    for key in arm_builds['presets']:
        hide = '' if key == default else ' hidden'
        parts.append(f'<div class="wb-preset" data-preset="{_esc(key)}"{hide}>')
        parts.append('<p class="wb-builds-lead">'
                     + _esc(builds_lead(facts, arm_builds, key, all_facts))
                     + '</p>')
        # The emphasis key, once per preset block and ABOVE the paragraphs:
        # they are the first prose that prints "(outside 10%)" in the page's
        # three typefaces, so the key that defines both has to precede them.
        parts.append(f'<p class="wb-g-head">{_esc(EMPH_KEY)}</p>')
        # The section's headline, one paragraph per named build. It sits
        # INSIDE the per-preset block so the Build criteria knob switches it
        # with the table it describes -- a paragraph naming builds the table
        # below no longer lists is the failure this placement rules out.
        parts.append(build_paragraphs_html(facts, arm_builds, key, all_facts))
        parts.append(builds_table_html(arm_builds, key))
        parts.append(standouts_html(facts, arm_builds, key, all_facts))
        parts.append('</div>')
    parts.append(f'<p class="wb-weighting">{_esc(WEIGHTING_NOTE)}</p>')
    parts.append('</div>')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# The section
# ---------------------------------------------------------------------------

def _guards_html(evidence):
    out = ['<details class="wb-guards"><summary>How the line was selected '
           '(gates and guards)</summary>']
    for line in evidence['lines']:
        out.append(f'<p>{_esc(line)}</p>')
    out.append(brief._table_html(evidence['head'], evidence['rows']))
    out.append('</details>')
    return ''.join(out)


def section_html(all_facts, arm, moveset_idx=0, mode='pvpoke',
                 page_movesets=1):
    """The whole ``<details>`` block for ONE moveset of one page.

    ``all_facts`` is every arm of the blob, in blob order, each already
    carrying its rendered parts under the ``_headline`` / ``_strip`` /
    ``_fields`` / ``_evidence`` keys that :func:`prepare` attaches.
    ``moveset_idx`` is this arm's index in the page's OWN ``DATA.movesets``
    (0 in every split file, since each file embeds only its moveset).
    ``page_movesets`` is how many movesets THIS file embeds: more than one
    means the page carries a Moveset dropdown that this section does not
    follow, and the note under the panel has to say which moveset it is
    about. Split files always pass 1 and their note is unchanged.
    """
    facts = all_facts[arm]
    marker = TermMarker()
    arm_builds = facts.get('_builds')
    pay = build_payload(facts, facts['_fields'], moveset_idx, mode=mode,
                        all_facts=all_facts, arm_builds=arm_builds)
    has_builds = 'bp' in pay
    default_preset = pay['bp']['default'] if has_builds else None

    lead = ' '.join(lead_sentences(all_facts, arm))
    # A literal space after the title, not the 6px CSS margin alone: copy /
    # paste, a screen reader and the stripped-text tests all read the two
    # runs with nothing between them ("build?Most Sableye").
    parts = [f'<style>{CSS}{ramp_css(len(pay["rungs"]))}'
             f'{ramp_css(pay.get("nScenRamp", 0), "s")}</style>',
             f'<details class="wb-root" id="{SECTION_ID}">',
             f'<summary class="wb-summary"><b>{_esc(SECTION_TITLE)}</b> '
             f'<span class="wb-head">'
             f'{_esc(builds_summary(facts, arm_builds, default_preset, all_facts) if has_builds else summary_sentence(facts, all_facts))}</span>'
             f'</summary>',
             '<div class="wb-body">',
             marker.mark(f'<p class="wb-lead">{_esc(lead)}</p>'),
             marker.mark(brief.strip_html(facts['_strip']))]
    if has_builds:
        parts.append(marker.mark(
            builds_block_html(facts, arm_builds, all_facts)))

    # ---- headline, with the opening sentence extended + the line expander --
    head = [sp1_prose(relabel(x, all_facts)) for x in facts['_headline']]
    first_para = sentences(head[0])
    opening = _esc(sp1_prose(relabel(extended_first_sentence(facts),
                                     all_facts)))
    fl = facts['floor']
    expander = False
    if fl is not None:
        printed = _esc(printed_value(fl))
        m = re.search(re.escape(printed), opening)
        if m:
            expander = True
            # Says what the control DOES. An earlier draft promised "hover
            # for the top few", which is a hover tooltip promising a hover
            # behaviour it does not have.
            title = (f"Click to list the "
                     f"{brief._n(int(fl['n_above']))} spreads that reach "
                     f"this line, by stat product.")
            btn = (f'<button type="button" class="wb-val" '
                   f'onclick="wbToggleClearers(this)" '
                   f'title="{_esc(title)}">{printed}</button>')
            opening = opening[:m.start()] + btn + opening[m.end():]
    rest = ' '.join(_esc(s) for s in first_para[1:])
    paras = [f'<p>{opening}{" " + rest if rest else ""}</p>']
    if expander:
        paras.append('<div class="wb-clearers" hidden></div>')
    for para in head[1:]:
        paras.append(f'<p>{_esc(para)}</p>')
    parts.append(marker.mark(
        '<div class="wb-headline">' + ''.join(paras) + '</div>'))

    # ---- the section plot -------------------------------------------------
    opts = ''.join(
        f'<option value="{_esc(v["id"])}"'
        f'{" selected" if i == 0 else ""}>{_esc(v["label"])}</option>'
        for i, v in enumerate(pay['views']))
    # The section's OWN shield control. It is NOT wired to the scatter's
    # Shields dropdown in either direction: this panel is the view the line
    # was derived on, and a reader who narrows it to one shield state is
    # asking a question about this section, not re-pointing the page.
    # "all" first and selected, then the nine scenarios in grid order.
    scen_opts = ''.join(
        [f'<option value="{ALL_SCEN}" selected>{_esc(ALL_SCEN_LABEL)}'
         f'</option>']
        + [f'<option value="{_esc(s)}">{_esc(s)}</option>'
           for s in pay['scenLabels']])
    parts.append(
        '<div class="wb-plotbox">'
        '<div class="wb-controls">'
        '<label>Show: '
        f'<select class="wb-view" onchange="if(window.wbSelectView)'
        f'wbSelectView(this)">{opts}</select></label>'
        '<label>Shield scenario: '
        f'<select class="wb-scen" onchange="if(window.wbSelectView)'
        f'wbSelectView(this)">{scen_opts}</select></label>'
        '</div>'
        + ('<div class="wb-plotrow"><div class="wb-upset"></div>'
           '<div class="wb-panel"></div></div>'
           if has_builds else '<div class="wb-panel"></div>')
        + (f'<p class="wb-upset-caption" hidden>'
           f'{_esc(UPSET_CAPTION)}</p>' if has_builds else '')
        + f'<p class="wb-caption">{_esc(pay["views"][0]["caption"])}</p>'
        f'<p class="wb-fixed">{_esc(fixed_note(facts, page_movesets))}</p>'
        '</div>')

    # ---- compare button ---------------------------------------------------
    spreads = compare_spreads(facts, arm_builds, default_preset)
    listed = ', '.join(
        f"{'SP1 ' if rule == 'rank-1' else ''}"
        f"{iv[0]}/{iv[1]}/{iv[2]}" for rule, iv in spreads)
    if len(spreads) == 1:
        # A no-line page whose most-winning spread IS SP1 names exactly
        # one spread, and a "compare these spreads" button that fills in one
        # candidate looks broken rather than settled.
        listed += ' -- the only spread this page names'
    parts.append(
        '<p><button type="button" class="wb-btn" '
        'onclick="if(window.wbCompare)wbCompare(this)">'
        'Compare these spreads</button>'
        f'<span class="wb-spreads">{_esc(listed)}</span></p>')

    # ---- evidence ---------------------------------------------------------
    fields = facts['_fields']
    ev = ['<details class="wb-evidence">'
          '<summary>Evidence</summary>']
    for field in fields:
        ev.append(brief.field_html(field))
    ev.append(_guards_html(facts['_evidence']))
    ev.append('</details>')
    parts.append(marker.mark(''.join(ev)))

    # ---- the terms this section marked ------------------------------------
    # Built last, because it lists what the marker actually used. The hover
    # definitions are title= text: no hover on a phone, <abbr> takes no
    # focus, and the four terms that carry a guide link navigate AWAY rather
    # than define. This prints the same registry sentences once, in the order
    # a reader met them.
    terms = glossary.terms_html(marker.ordered())
    if terms:
        parts.append('<p class="wb-terms-head">Terms used here</p>' + terms)

    # sort_keys so two renders of one blob are byte-identical; '<' escaped so
    # nothing inside the payload can close the <script> element early.
    blob = json.dumps(pay, sort_keys=True, separators=(',', ':'))
    parts.append('<script type="application/json" class="wb-data">'
                 + blob.replace('<', '\\u003c') + '</script>')
    parts.append('</div></details>\n')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Compute + prepare
# ---------------------------------------------------------------------------

def prepare(state, blob_path, mode='pvpoke', level='l50'):
    """Compute + gate every arm of a blob, ready for :func:`section_html`.

    Returns the list of fact dicts in blob order, each with its four rendered
    parts attached under ``_headline`` / ``_strip`` / ``_fields`` /
    ``_evidence``. The gates run here, once per arm, exactly as the
    standalone brief runs them.
    """
    n_arms = len(state['moveset_data'])
    all_facts = []
    for arm in range(n_arms):
        facts = brief.compute_brief(state, arm, blob_path, mode=mode,
                                    level=level)
        same = brief.shared_line_with(facts, all_facts)
        headline, strip, fields, evidence = brief.render_parts(
            state, arm, blob_path, facts, mode, level, same_as=same)
        facts['_headline'] = headline
        facts['_strip'] = strip
        facts['_fields'] = fields
        facts['_evidence'] = evidence
        facts['_masks'] = compute_masks(state, arm, facts, mode, level)
        # v4: the builds. Computed per arm from the same blob the brief read
        # (1-2 s on a 4096 x 9 x 76 grid), and NOT fatal on its own: a page
        # whose builds fail to compute still ships the v3 section, with its
        # line, its rungs and its trade, rather than losing the whole block.
        try:
            facts['_builds'] = builds.compute_builds(
                state, arm, mode=mode, level=level, facts=facts)
        except Exception as exc:                       # noqa: BLE001
            facts['_builds'] = None
            deep_dive_logging.get_logger().warning(
                f"  Which one to build?: builds for moveset {arm} omitted "
                f"({type(exc).__name__}: {exc})")
        all_facts.append(facts)
    # Every reader-facing string this module AUTHORS -- the lead, the note
    # under the panel, the clusters caption that stands in when the brief
    # has no corroboration sentence to quote, and the two no-line summaries
    # -- goes through the brief's word gates, so a banned adjective cannot
    # enter the page through the one block the brief module did not write.
    # The clusters fallback is gated whether or not this page uses it: it is
    # a constant, and a gate that fires only on the pages that happen to hit
    # the branch is a gate that ships the bad string.
    #
    # The DIRECTIVE summary is not in this list. It says 'Most X should have
    # at least Y', which the word gate allows at most once per call, and the
    # headline's own opening sentence (gated per arm above) is the other
    # instance of that fixed phrase. Gating a restatement of an already-
    # gated sentence would fail on the duplicate, not on a defect.
    ctx = {'blob': os.path.basename(blob_path), 'arm': '-', 'mode': mode}
    own = [CLUSTERS_FALLBACK_CAPTION, BUILDS_CAPTION, WEIGHTING_NOTE,
           EMPH_KEY, STANDOUT_NOTE, STANDOUT_NOTE_INSIDE, STATS_CAPTION]
    own.extend(STANDOUT_KIND.values())
    for arm, facts in enumerate(all_facts):
        ab = facts.get('_builds')
        if ab:
            # Every preset's sentences, for every preset -- gated whether or
            # not the reader ever selects that preset, for the same reason
            # the clusters fallback is: a gate that fires only on the branch
            # a page happens to take is a gate that ships the bad string.
            for key, block in builds_prose(facts, ab, all_facts).items():
                own.extend(v for v in block.values() if v)
            for key in ab['presets']:
                own.append(builds_summary(facts, ab, key, all_facts))
                own.append(builds_lead(facts, ab, key, all_facts))
                # The section's headline and its standouts block, stripped
                # of markup: these are the two longest runs of authored
                # prose v5 adds, and neither goes through render_parts.
                own.append(gate_text(
                    build_paragraphs_html(facts, ab, key, all_facts)))
                own.append(gate_text(
                    standouts_html(facts, ab, key, all_facts)))
        own.extend(lead_sentences(all_facts, arm))
        own.append(fixed_note(facts, page_movesets=2))
        if facts['floor'] is None:
            own.append(summary_sentence(facts, all_facts))
        # Every caption the Shield scenario control can put under the panel,
        # for every scenario and every view -- gated whether or not this page
        # reaches the branch, for the same reason the clusters fallback is:
        # a gate that fires only on the pages that happen to hit a branch is
        # a gate that ships the bad string. The trade caption is the brief's
        # own sentence plus a tag, so only the tag is new; it is cheaper to
        # gate the whole set than to special-case it.
        for scen, entry in (facts.get('scenario_lines') or {}).items():
            for view in ('builds', 'stats', 'line', 'rungs', 'clusters',
                         'rank1'):
                own.append(scenario_caption(view, scen, entry, facts))
    brief.gate_words(own, ctx)
    brief.gate_caveat(own, ctx)
    return all_facts
