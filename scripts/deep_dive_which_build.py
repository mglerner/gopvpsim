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

import base64
import html as _html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deep_dive_brief as brief  # noqa: E402
import glossary  # noqa: E402

SECTION_ID = 'dd-which-build'
SECTION_TITLE = 'Which one to build?'
# Top-N clearers the expander lists before the "show all" control. Matches the
# flavor guide's Member-IVs pattern (a short default list plus a toggle); the
# rest are built in the browser from DATA, so a 2220-spread line costs the
# page no extra bytes.
CLEARER_TOP_N = 25

# Every view the section plot can show, with the selector label. The caption
# is per-page (it is a sentence of the brief's own headline), so it travels in
# the payload rather than here.
VIEWS_FLOOR = (('line', 'the line'), ('rungs', 'the rungs'),
               ('trade', 'the trade'), ('clusters', 'clusters'))
VIEWS_NO_FLOOR = (('clusters', 'clusters'), ('rank1', 'rank-1'))

# Terms marked on FIRST use in the section, longest-first so "stat-product
# rank-1" is claimed before "stat product" can match inside it. Each entry is
# (glossary term, regex over page text); the matched text is what gets
# wrapped, so a plural stays plural.
_TERM_PATTERNS = (
    ('stat-product rank-1', r'stat-product rank-1'),
    ('charge-move priority', r'charge-move[- ]priority'),
    ('contested matchups', r'contested matchups?'),
    ('one-sided gate', r'one-sided gates?'),
    ('stat product', r'stat product(?!s)'),
    ('bulkpoint', r'bulkpoints?'),
)

_TAG_SPLIT = re.compile(r'(<[^>]*>)')
_SENTENCE_END = re.compile(r'(?<=[.!?])(?=\s|$)')


def _esc(s):
    return _html.escape(str(s), quote=True)


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
        self.used = set()

    def mark(self, fragment):
        # One term per outer pass, re-splitting the fragment each time. The
        # markup a substitution inserts carries the DEFINITION in a title=
        # attribute, and re-splitting puts that text inside a tag piece where
        # the next term cannot match it. (No definition in the registry
        # contains another registered term today -- test_no_definition_
        # contains_another_term keeps it that way -- but a marker that only
        # works while that holds is a trap for whoever adds the seventh term.)
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
                self.used.add(term)
                fragment = ''.join(pieces)
                break
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
    of spreads that reach anything to name.
    """
    first = sentences(facts['_headline'][0])[0]
    fl = facts['floor']
    if fl is None:
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

def lead_sentences(all_facts, arm):
    """The page-wide count, this file's line, then the other movesets'.

    One sentence on a single-moveset page, three on a multi-moveset one --
    two rendered lines either way. The first is the brief's own page-lead
    sentence, verbatim (``deep_dive_brief.lead_block``). The other two exist
    because each split file carries only ITS moveset's section: a reader on
    the Power Gem file has no way to see that Drain Punch prints the same
    line unless this sentence says so.
    """
    _, lead_strings = brief.lead_block(all_facts)
    out = [lead_strings[0]]
    if len(all_facts) < 2:
        return out

    def line_of(f):
        fl = f['floor']
        if fl is None:
            return None
        return brief.stat_threshold_str(fl['axis'], fl['printed'], fl['dp'])

    mine = line_of(all_facts[arm])
    out.append(
        f"This file is {all_facts[arm]['header']['arm_label']}"
        + (" and carries no line." if mine is None else f" at {mine}."))
    # Semicolons, not "A, B and C": every moveset label already contains a
    # comma ("SHADOW_CLAW / FOUL_PLAY, POWER_GEM"), so a comma-joined list
    # reads as twice as many movesets as the page has.
    bits = []
    for i, f in enumerate(all_facts):
        if i == arm:
            continue
        lbl = f['header']['arm_label']
        val = line_of(f)
        if val is None:
            bits.append(f"{lbl}, no line")
        elif val == mine:
            bits.append(f"{lbl}, the same line")
        else:
            bits.append(f"{lbl} at {val}")
    out.append("Other movesets on this page: " + '; '.join(bits) + '.')
    return out


# ---------------------------------------------------------------------------
# The summary line (what a reader sees before opening the section)
# ---------------------------------------------------------------------------

def summary_sentence(facts):
    """The one sentence in the collapsed ``<summary>``.

    A page WITH a line shows the headline's opening sentence, which already
    says the stat and the value. A page without one cannot: its headline
    opens on the negative, which is a fine paragraph and a poor label. The
    two replacements say what a reader who only reads the summary should do.
    """
    if facts['floor'] is not None:
        return sentences(facts['_headline'][0])[0]
    gb = facts['grid_best']
    r1 = facts['rank1']
    if gb['total'] <= r1['total_won']:
        return ("Your rank-1: it already wins more matchups than any "
                "other spread.")
    return "Any of them: no single stat threshold decides a matchup here."


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
    """
    buf = bytearray((len(flags) + 7) // 8)
    for i, flag in enumerate(flags):
        if flag:
            buf[i >> 3] |= 1 << (i & 7)
    return base64.b64encode(bytes(buf)).decode('ascii')


def compute_masks(state, arm, facts, mode='pvpoke', level='l50'):
    """Membership masks for the line, each rung above it, and the bulk pair.

    Recomputed from the blob's own stat planes rather than carried out of
    ``compute_brief`` (which drops every numpy array on the way to JSON).
    The counts are cross-checked against the brief's printed counts before
    anything is packed: a mismatch means the plot would draw a different set
    from the one the page describes, and there is no honest way to render
    that.
    """
    fl = facts['floor']
    if fl is None:
        return {'rungs': [], 'alt': None}
    _scores, meta = brief.arm_view(state, arm, mode, level=level)
    atk, dfn, hp = brief.stat_planes(meta)
    planes = {'atk': atk, 'def': dfn, 'hp': hp}
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
    return {'rungs': rungs, 'alt': alt_mask}


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


def _rung_label(printed, dp, names, n_cells):
    head = brief.fmt(printed, dp)
    if not names:
        return head
    more = n_cells - 1
    tail = f"{names[0]}{f' +{more}' if more > 0 else ''}"
    return f"{head} ({tail})"


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


def _caption_for(view, facts, fields):
    """One sentence of the brief's prose per view, chosen by what it shows."""
    head = facts['_headline']
    first = sentences(head[0])
    rest = sentences(head[1]) if len(head) > 1 else []
    if view == 'line':
        return first[0]
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
        return ("The Matchup clusters section's own partition of this same "
                "grid, drawn here on the same axes.")
    return first[0]


def build_payload(facts, fields, moveset_idx, mode='pvpoke'):
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
                   'caption': _caption_for(vid, facts, fields)}
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
             'label': _rung_label(fl['printed'], fl['dp'], [fl['cell']], 1)})
        for k, row in enumerate(facts.get('rungs_above') or []):
            pay['rungs'].append(
                {'axis': fl['axis'], 'T': float(row['T']),
                 'n': int(row['n_pass']), 'mask': masks['rungs'][k + 1],
                 'label': _rung_label(row['printed'], row['dp'],
                                      row['names'], row['n_cells'])})
        pay['examples'] = [
            {'iv': [int(x) for x in ex['ivs']], 'level': float(ex['level']),
             'rule': ex['rule']} for ex in example_spreads(facts)]
        alt = facts.get('alternative')
        if alt is not None and not alt['too_wide']:
            pay['alt'] = {'label': brief.alt_pair_short(alt),
                          'mask': facts['_masks']['alt'],
                          'n': int(alt['n'])}
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
            out.append((ex['rule'], [int(x) for x in ex['ivs']]))
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
  --wb-mark1: #16706a; --wb-mark2: #2f5fd0;
  --wb-r0: #9d61d1; --wb-r1: #8840c7; --wb-r2: #7232ab;
  --wb-r3: #5c288a; --wb-r4: #461e68; --wb-r5: #301547; }
[data-theme="gruvbox-dark"] #dd-which-build,
[data-theme="pokemon-dark"] #dd-which-build {
  --wb-line: #b18cf0; --wb-below: #9aa3ad; --wb-alt: #ec93d6;
  --wb-mark1: #55d9c9; --wb-mark2: #8fb4ff;
  --wb-r0: #9859cf; --wb-r1: #a872d6; --wb-r2: #b78cdd;
  --wb-r3: #c7a5e5; --wb-r4: #d7beec; --wb-r5: #e6d7f4; }
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
#dd-which-build .wb-panel { height: 400px; min-height: 400px; }
#dd-which-build .wb-caption { font-size: 0.85rem; color: var(--text-muted);
  margin: 4px 0 0; }
#dd-which-build .wb-fixed { font-size: 0.78rem; color: var(--text-muted);
  margin: 4px 0 0; }
"""


# ---------------------------------------------------------------------------
# The section
# ---------------------------------------------------------------------------

def _guards_html(evidence):
    out = ['<details class="wb-guards"><summary>Evidence and guards'
           '</summary>']
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
    pay = build_payload(facts, facts['_fields'], moveset_idx, mode=mode)

    lead = ' '.join(lead_sentences(all_facts, arm))
    parts = [f'<style>{CSS}</style>',
             f'<details class="wb-root" id="{SECTION_ID}">',
             f'<summary class="wb-summary"><b>{_esc(SECTION_TITLE)}</b>'
             f'<span class="wb-head">{_esc(summary_sentence(facts))}</span>'
             f'</summary>',
             '<div class="wb-body">',
             marker.mark(f'<p class="wb-lead">{_esc(lead)}</p>'),
             marker.mark(brief.strip_html(facts['_strip']))]

    # ---- headline, with the opening sentence extended + the line expander --
    head = facts['_headline']
    first_para = sentences(head[0])
    opening = _esc(extended_first_sentence(facts))
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
    parts.append(
        '<div class="wb-plotbox">'
        '<label style="font-size:0.85rem">Show: '
        f'<select class="wb-view" onchange="if(window.wbSelectView)'
        f'wbSelectView(this)">{opts}</select></label>'
        '<div class="wb-panel"></div>'
        f'<p class="wb-caption">{_esc(pay["views"][0]["caption"])}</p>'
        '<p class="wb-fixed">Stat-product rank against matchups won over '
        'every baked shield scenario and the whole opponent pool, with '
        'PvPoke-default opponent IVs at the league cap -- the exact view '
        'the line above was derived from, so this panel does not follow the '
        'scatter\'s dropdowns or the opponent filter.'
        + (f' This whole section is about {_esc(facts["header"]["arm_label"])}'
           f', which the Moveset dropdown above does not change.'
           if page_movesets > 1 else '')
        + '</p>'
        '</div>')

    # ---- compare button ---------------------------------------------------
    spreads = compare_spreads(facts)
    listed = ', '.join(
        f"{'rank-1 ' if rule == 'rank-1' else ''}"
        f"{iv[0]}/{iv[1]}/{iv[2]}" for rule, iv in spreads)
    parts.append(
        '<p><button type="button" class="wb-btn" '
        'onclick="if(window.wbCompare)wbCompare(this)">'
        'Compare these spreads</button>'
        f'<span class="wb-spreads">{_esc(listed)}</span></p>')

    # ---- evidence ---------------------------------------------------------
    fields = facts['_fields']
    ev = ['<details class="wb-evidence">'
          f'<summary>Evidence ({len(fields)} fields)</summary>']
    for field in fields:
        ev.append(brief.field_html(field))
    ev.append(_guards_html(facts['_evidence']))
    ev.append('</details>')
    parts.append(marker.mark(''.join(ev)))

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
        all_facts.append(facts)
    # The section's OWN prose -- the second lead sentence and the two summary
    # replacements -- goes through the brief's word gates too, so the page
    # cannot smuggle a banned adjective past them in the one block the brief
    # module did not write. The headline sentence the summary quotes is NOT
    # re-gated: it is already gated once per arm above, and 'should have at
    # least' is allowed exactly once per rendered section.
    ctx = {'blob': os.path.basename(blob_path), 'arm': '-', 'mode': mode}
    own = []
    for arm, facts in enumerate(all_facts):
        own.extend(lead_sentences(all_facts, arm)[1:])
        if facts['floor'] is None:
            own.append(summary_sentence(facts))
    brief.gate_words(own, ctx)
    brief.gate_caveat(own, ctx)
    return all_facts
