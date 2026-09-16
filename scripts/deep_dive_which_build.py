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

# Terms marked on FIRST use in the section, longest-first so "stat-product
# rank-1" is claimed before "stat product" can match inside it. Each entry is
# (glossary term, regex over page text); the matched text is what gets
# wrapped, so a plural stays plural.
_TERM_PATTERNS = (
    ('stat-product rank-1', r'stat-product rank-1'),
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
            for k, piece in enumerate(pieces):
                if piece.startswith('<') or not piece.strip():
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
    first = sentences(facts['_headline'][0])[0]
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
            return ("Your rank-1: it already wins more matchups than any "
                    "other spread.")
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
            out += (f" -- though rank-1 {r1} already wins as many matchups "
                    f"as anything above it")
        else:
            out += (f" -- though rank-1 {r1} still wins {brief._n(-net)} "
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
    "colour per build; the diamond is stat-product rank-1, each triangle a "
    "build's most-winning member, and the open square the spread that wins "
    "the most matchups anywhere on the grid.")


def _caption_for(view, facts, fields, all_facts=None):
    """One sentence of the brief's prose per view, chosen by what it shows.

    The builds view is the one view the brief has no sentence about -- it
    draws this module's own object -- so its caption is authored here and
    gated with the rest of this module's prose in :func:`prepare`.
    """
    if view == 'builds':
        return BUILDS_CAPTION
    head = facts['_headline']
    first = [relabel(x, all_facts) for x in sentences(head[0])]
    rest = ([relabel(x, all_facts) for x in sentences(head[1])]
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
        views = (VIEW_BUILDS,) + tuple(views)
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


def compare_spreads(facts):
    """The spreads the "Compare these spreads" button prefills, in order.

    Rank-1 first (it is the build a reader most likely already has), then the
    brief's example spreads -- or, with no line, the spread that wins the
    most matchups, which is the only other spread the page names.
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
#dd-which-build .wb-mem-head { font-size: .74rem; letter-spacing: .09em;
  text-transform: uppercase; color: var(--text-muted); margin: 10px 0 4px;
  font-weight: 600; }
#dd-which-build .wb-mem { font-size: 0.8rem; max-height: 260px;
  overflow-y: auto; background: var(--surface-2);
  border: 1px solid var(--border-2); border-radius: 6px; padding: 6px 10px; }
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
             'rank1': 'Build 3 (bulk)'}
ROLE_SHORT = {'primary': 'primary', 'fork': 'fork', 'rank1': 'bulk'}
# Guarantee rows printed per shield scenario before the "+N more" control.
# Four, not more: three presets x up to three builds x up to nine shield
# scenarios means every extra row is emitted ~80 times on one file, and the
# counts a reader is actually comparing are in the table above the lists.
GUARANTEE_CAP = 4
# A cell the rest of the grid wins at more than this is near-free: the build
# is not what got it. Counted in a trailing sentence rather than listed.
NEAR_FREE = 0.90


def _pct(x):
    return f"{round(float(x) * 100):.0f}%"


def _fidelity_clause(b):
    """How well the printed description reproduces the member list."""
    d = b['description']
    if d is None:
        return 'no two- or three-stat rule fits it; the list is the build'
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
    so the TABLE always prints them; the one-line summary does not, because
    eight "HP 115 -> def 103.16" pairs in the collapsed summary bury the
    sentence a reader opened the page for.
    """
    d = b['description']
    if d is None:
        return f"list of {brief._n(b['size'])} spreads"
    rule = d['rule']
    if d.get('steps'):
        if not steps:
            return rule
        pairs = '; '.join(f"HP {h:g} -> def {dd:g}" for h, dd, _n in d['steps'])
        return f"{rule}: {pairs}"
    return rule


def _scen_weighted(bl, scen_labels):
    """The scenarios this preset counts, as a printable clause."""
    live = [scen_labels[i] for i, w in enumerate(bl['weights']) if w > 0]
    if len(live) == len(scen_labels):
        return 'all ' + brief._n(len(live)) + ' shield scenarios'
    return ' / '.join(live) + ' shields'


def builds_summary(facts, arm_builds, preset, all_facts=None):
    """The collapsed summary line for one preset.

    "Which one to build? [even shields] 61 spreads at atk >= 150.24 with a
    defense staircase guarantee 55 of the 87 decision matchups; a disjoint
    114-spread rectangle guarantees 41 instead, and holds your rank-1."

    A page with no builds keeps the v3 sentence: the two no-line summaries
    already say what a reader who reads only the summary can do.
    """
    bl = arm_builds['presets'].get(preset)
    if not bl or not bl['builds'] or facts['floor'] is None:
        # A page with no line keeps the v3 negative summary -- Michael's
        # 2026-09-16 call. Its two sentences say what a reader who reads only
        # the summary can do ("your rank-1 already wins more than anything
        # else"), which a builds sentence would displace rather than improve.
        # The builds themselves are still rendered and still plotted below.
        return summary_sentence(facts, all_facts)
    tag = builds.PRESET_TAG[preset]
    p = bl['builds'][0]
    n_dec = arm_builds['n_decision_cells']
    out = (f"[{tag}] {brief._n(p['size'])} spreads -- "
           f"{build_desc(p, steps=False)} -- guarantee "
           f"{brief._n(p['n_guaranteed'])} of the "
           f"{brief._n(n_dec)} decision matchups")
    rest = bl['builds'][1:]
    if rest:
        f = rest[0]
        clause = (f"; a disjoint {brief._n(f['size'])}-spread build "
                  f"({build_desc(f, steps=False)}) guarantees "
                  f"{brief._n(f['n_guaranteed'])} instead")
        if f['rank1_in']:
            clause += ' and holds your stat-product rank-1'
        out += clause
    elif p['rank1_in']:
        out += ', and it holds your stat-product rank-1'
    return out + '.'


def builds_lead(facts, arm_builds, preset, all_facts=None):
    """The sentence under the section's own lead: which preset, what it does."""
    bl = arm_builds['presets'].get(preset)
    if not bl:
        return ''
    scens = _scen_weighted(bl, arm_builds['ctx']['scen_labels'])
    n = len(bl['builds'])
    return (f"Build criteria: {builds.PRESET_LABEL[preset]} -- the builds "
            f"below are selected and ranked by what they guarantee in "
            f"{scens}. {brief._n(n).capitalize()} "
            f"{brief._noun(n, 'build')} for this moveset, out of "
            f"{brief._n(arm_builds['n_decision_cells'])} decision matchups "
            f"({brief._n(arm_builds['n_material_cells'])} of them material).")


def objectives_line(arm_builds, preset):
    """The two objectives, printed only when they disagree."""
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
    cell_gap = int(obj['cell_gap'])
    return (f"The two objectives disagree here: "
            f"{ROLE_SHORT[by_wins['role']]}'s most-winning spread "
            f"{by_wins['most_winning_member']['iv']} wins "
            f"{brief._n(win_gap)} more "
            f"{brief._noun(win_gap, 'matchup')} overall, while "
            f"{ROLE_SHORT[by_cells['role']]} guarantees "
            f"{brief._n(cell_gap)} more decision "
            f"{brief._noun(cell_gap, 'matchup')}.")


WEIGHTING_NOTE = (
    "The shield weighting above is the page's Build criteria preset. The "
    "tables list cells per shield scenario whatever the preset is; the "
    "preset changes which of them the ranking counts.")


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


def _guarantee_rows_html(arm_builds, b):
    """One build's guaranteed cells, grouped by shield scenario.

    Sorted by OUTSIDE RATE ascending inside each group -- the guarantee the
    rest of the grid is least likely to hand a reader anyway reads first --
    capped, with the near-free tail counted rather than listed.
    """
    n_modes = b['honesty']['n_modes']
    parts = []
    by_scen = b['guaranteed_by_scenario']
    for scen in arm_builds['ctx']['scen_labels']:
        rows = by_scen.get(scen)
        if not rows:
            continue
        listed = [r for r in rows if r['outside_wr'] <= NEAR_FREE]
        free = len(rows) - len(listed)
        items = []
        for r in listed[:GUARANTEE_CAP]:
            flags = []
            if r['material']:
                flags.append('material')
            # Only the SHORTFALL is printed: "holds in 3 of 3 opponent-IV
            # modes" on every one of a few hundred rows is the page's single
            # biggest run of bytes and its least informative words. The
            # count of rows that hold everywhere is in the table above.
            if r['modes_ok'] < n_modes:
                flags.append(f"holds in {r['modes_ok']} of {n_modes} "
                             f"opponent-IV modes")
            tail = ('; ' + '; '.join(flags)) if flags else ''
            items.append(
                f'<li>{_esc(r["cell"])} (rank {r["rank"]}) -- outside '
                f'{_esc(_pct(r["outside_wr"]))}{_esc(tail)}</li>')
        more = len(listed) - len(items)
        if more > 0:
            items.append(f'<li class="wb-more">+{more} more in {_esc(scen)}'
                         f'</li>')
        tail = ''
        if free:
            tail = (f'<li class="wb-free">{brief._n(free).capitalize()} more '
                    f'{brief._noun(free, "cell")} here are near-free: the '
                    f'spreads outside this build win them over '
                    f'{_esc(_pct(NEAR_FREE))} of the time too.</li>')
        parts.append(f'<li class="wb-sgroup"><b>{_esc(scen)}</b> '
                     f'({len(rows)})<ul>' + ''.join(items) + tail + '</ul></li>')
    if not parts:
        return '<p>No decision matchup is guaranteed by every member.</p>'
    return '<ul class="wb-g-list">' + ''.join(parts) + '</ul>'


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
    n_dec = arm_builds['n_decision_cells']
    head = ('<tr><th>Build</th><th>What it is</th><th>Spreads</th>'
            '<th>Guarantees</th><th>Most-winning member</th>'
            '<th>Stat-product rank-1</th><th>Gives up</th></tr>')
    rows = []
    for i, b in enumerate(bl['builds']):
        mw = b['most_winning_member']
        rows.append(
            f'<tr data-build="{i}">'
            f'<td><span class="wb-swatch" data-build="{i}"></span>'
            f'{_esc(ROLE_NAME.get(b["role"], b["role"]))}</td>'
            f'<td>{_esc(build_desc(b))}<br>'
            f'<span class="wb-fid">{_esc(_fidelity_clause(b))}</span></td>'
            f'<td>{brief._n(b["size"])}</td>'
            f'<td>{b["n_guaranteed"]} of {n_dec}'
            f' ({b["n_guaranteed_material"]} material,'
            f' {b["n_scenarios_covered"]} shield '
            f'{brief._noun(b["n_scenarios_covered"], "scenario")}'
            + (f', {b["honesty"]["n_guaranteed_all_modes"]} holding in all '
               f'{b["honesty"]["n_modes"]} opponent-IV modes'
               if b['honesty']['n_modes'] > 1 else '')
            + ')</td>'
            f'<td>{_esc(mw["iv"])} -- {mw["wins"]} matchups</td>'
            f'<td>{"in" if b["rank1_in"] else "out"}</td>'
            f'<td>{_esc(_gives_up_text(b))}</td>'
            f'</tr>')
    out = ['<table class="wb-builds-table">', head] + rows + ['</table>']
    obj = objectives_line(arm_builds, preset)
    if obj:
        out.append(f'<p class="wb-obj">{_esc(obj)}</p>')
    for i, b in enumerate(bl['builds']):
        out.append(
            f'<details class="wb-build" data-build="{i}">'
            f'<summary>{_esc(ROLE_NAME.get(b["role"], b["role"]))}: what it '
            f'guarantees ({b["n_guaranteed"]}) and its members '
            f'({brief._n(b["size"])})</summary>'
            + _guarantee_rows_html(arm_builds, b)
            + f'<p class="wb-mem-head">Members ({brief._n(b["size"])}), '
              f'bulkiest first</p>'
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
        parts.append(builds_table_html(arm_builds, key))
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
    head = [relabel(x, all_facts) for x in facts['_headline']]
    first_para = sentences(head[0])
    opening = _esc(relabel(extended_first_sentence(facts), all_facts))
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
        + f'<p class="wb-caption">{_esc(pay["views"][0]["caption"])}</p>'
        f'<p class="wb-fixed">{_esc(fixed_note(facts, page_movesets))}</p>'
        '</div>')

    # ---- compare button ---------------------------------------------------
    spreads = compare_spreads(facts)
    listed = ', '.join(
        f"{'rank-1 ' if rule == 'rank-1' else ''}"
        f"{iv[0]}/{iv[1]}/{iv[2]}" for rule, iv in spreads)
    if len(spreads) == 1:
        # A no-line page whose most-winning spread IS rank-1 names exactly
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
    own = [CLUSTERS_FALLBACK_CAPTION, BUILDS_CAPTION, WEIGHTING_NOTE]
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
            for view in ('builds', 'line', 'rungs', 'clusters', 'rank1'):
                own.append(scenario_caption(view, scen, entry, facts))
    brief.gate_words(own, ctx)
    brief.gate_caveat(own, ctx)
    return all_facts
