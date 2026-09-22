#!/usr/bin/env python
"""Minimal glossary registry for reader-facing dive surfaces.

ONE place defines each term. A renderer that wants a hover definition asks
for it here; it never types the sentence itself. The rule is enforced by
``tests/test_which_build_section.py::test_no_second_definition_in_renderer``,
which scans the renderers for a literal copy of any definition below.

Scope is deliberately small: the terms the "Which one to build?" section uses
on first mention. The full glossary page is a later task (TODO.md); this
module is what that page will be built from, so definitions are one sentence
each and carry their own reader's-guide anchor where one exists.

Vocabulary used below (docs style rule, per document):

- CMP (Charge Move Priority): the same-turn charged-move tiebreak, decided by
  the attack stat. Spelled out in the ``charge-move priority`` entry.
- Reader's guide: the built ``guides/<slug>/`` pages (``scripts/build_guides.py``).
  Anchors are the markdown ``toc`` extension's slugified headings, so
  ``ANCHORS`` below is pinned to the guide bodies by a test rather than
  hand-maintained.
"""
from __future__ import annotations

import html as _html

# term -> one-sentence definition. Lower-case keys; the rendered text keeps
# whatever casing the call site passes.
TERMS = {
    'charge-move priority':
        "When both sides throw a charged move on the same turn, the higher "
        "attack stat goes first.",
    'stat-product rank-1':
        "The IV spread with the largest attack x defense x HP at this "
        "league's CP cap -- the bulk-first spread most IV tools list first. "
        "Written SP1 where it is named repeatedly.",
    # BOTH directions, deliberately: a gate is one-sided either way round
    # (necessary OR sufficient), and a definition naming only the necessary
    # one would be wrong on every page whose gate is the sufficient kind.
    'one-sided gate':
        "A stat value with one clean side: either nothing below it wins the "
        "matchup, or everything at or above it does -- so clearing it is "
        "required, or enough, but not both.",
    'contested matchups':
        "The matchups some IV spreads on this grid win and others lose -- "
        "the only ones an IV choice can change.",
    'bulkpoint':
        "A defense value across which an opponent's damage into you steps "
        "down by a whole point, or an HP value across which the number of "
        "hits they need to knock you out changes.",
    'stat product':
        "Attack x defense x HP at the league's CP cap, the usual one-number "
        "summary of an IV spread.",
    # ---- the v4 "Which one to build?" builds vocabulary ----
    'build':
        "A region of the IV grid you can aim at -- every spread that clears "
        "the same combination of thresholds, at least fifty of them.",
    'fork':
        "A second region with no spread in common with the first that wins "
        "a noticeably different set of matchups outright -- the two overlap "
        "on less than 80% of them -- so they are a real choice rather than "
        "two spellings of one.",
    'decision matchup':
        "A (shield scenario, opponent) pair the IV choice decides: a top-50 "
        "opponent that some spreads on this grid beat and others lose to.",
    'guaranteed':
        "Won by every single spread in the region, not by most of them.",
    'outside rate':
        "How often the spreads left OUT of a region win the same matchup "
        "its own members all win -- one the rest of the grid takes anyway "
        "is not what you bought.",
    'material':
        "A matchup no single-stat threshold of a hundred or more spreads "
        "wins more than 95% of the time, so it takes two stats at once to "
        "claim it.",
    'build criteria':
        "Which shield scenarios the ranking counts: all nine equally, the "
        "three even ones, or 1v1 alone.",
    # ---- round 9: the six terms the 2026-09-19 communication review found
    # printed on the page and defined nowhere on it.
    # Worded around the other registry keys on purpose: a definition that
    # spells another registered term would be marked inside its own tooltip
    # (test_no_definition_contains_another_registered_term).
    'wide':
        "The looser rule drawn around a region of the grid: it holds every "
        "spread that region holds and more, so it wins less for every "
        "member but is easier to hit.",
    'family':
        "A region grown around one standout spread until at least fifty "
        "spreads all win every matchup left in it: something to aim at near "
        "a spread the table's own regions miss.",
    'staircase':
        "A rule whose defense floor steps DOWN as HP goes up, so bulk can be "
        "spent on either stat: one floor per HP value rather than one floor "
        "for all of them.",
    'bulk box':
        "A rule that is a defense floor and an HP floor and nothing else -- "
        "a rectangle on the defense / HP plane.",
    'rung':
        "An attack value above the line at which some further matchup flips "
        "for every spread that reaches it.",
    # Round 10: the qualifier that keeps "guarantees" honest, and the
    # rate the "Rarest win" column leads with -- both were first used in the
    # table and defined nowhere on the page (2026-09-19 round-10 review).
    'opponent-iv mode':
        "One of the ways every opponent was made for this bake -- "
        "PvPoke-default IVs or the bulkiest ones, each with and without the "
        "focal side baiting -- so a claim that holds in all of them does "
        "not depend on how the opponent was made.",
    # Round 11 (2026-09-22): the term "The mirror" block introduces. 'CMP'
    # is the short form of an entry that was already here, marked the way
    # SP1 is -- whichever spelling a reader meets first carries the tooltip.
    'mirror cohort':
        "The population of same-species opponents the mirror-slayer "
        "protocol converges on: spreads picked over several rounds for "
        "beating each other in the mirror, not a census of what players "
        "own.",
    'upset plot':
        "A bar chart of set intersections: each column is one candidate "
        "region, and the dots under it mark which named sets it lies inside "
        "(Lex et al. 2014).",
}

# term -> the heading a definition list PRINTS for it, where that differs
# from the registry key. The section writes "SP1" after defining it once, so
# a reader scanning the terms at the foot for SP1 has to find it there
# (2026-09-17 round 6 review).
DISPLAY = {'stat-product rank-1': 'stat-product rank-1 (SP1)',
           'charge-move priority': 'charge-move priority (CMP)',
           'upset plot': 'UpSet plot',
           'opponent-iv mode': 'opponent-IV mode'}

# term -> "<guide-slug>#<heading-anchor>", relative to the guides directory.
# Absent = no guide covers the term today, and the hover definition stands
# alone rather than linking somewhere that does not define it.
ANCHORS = {
    'contested matchups':
        'matchup-clusters#sharp-marginals-the-only-opponents-that-matter-here',
    'bulkpoint': 'threshold-tiers#what-a-tier-card-actually-shows',
    'stat product': 'deep-dive-scatter#axes-at-a-glance',
    'stat-product rank-1': 'deep-dive-scatter#axes-at-a-glance',
}

# A dive page lives at ``website/<slug>/index.html``; the guides land at
# ``website/guides/<slug>/``.
GUIDES_PREFIX = '../guides/'


def definition(term):
    """The one-sentence definition, or None when the term is not registered."""
    return TERMS.get(term.lower())


def guide_href(term, prefix=GUIDES_PREFIX):
    """Reader's-guide URL for the term, or None when no guide covers it."""
    anchor = ANCHORS.get(term.lower())
    if anchor is None:
        return None
    slug, _, frag = anchor.partition('#')
    return f'{prefix}{slug}/#{frag}'


def abbr_html(term, text=None, cls='wb-term', prefix=GUIDES_PREFIX):
    """``<abbr>`` markup for one first use of ``term``.

    ``text`` is the literal page text to wrap (defaults to the term itself),
    so a sentence that says "charge-move-priority line" can mark just the
    words it actually uses. Raises KeyError for an unregistered term: a
    silent passthrough would leave the page with an undefined term and no
    signal that the registry was missed.
    """
    key = term.lower()
    if key not in TERMS:
        raise KeyError(f"no glossary entry for {term!r}")
    body = _html.escape(term if text is None else text)
    title = _html.escape(TERMS[key], quote=True)
    mark = f'<abbr class="{cls}" title="{title}">{body}</abbr>'
    href = guide_href(term, prefix=prefix)
    if href is None:
        return mark
    return (f'<a class="{cls}-link" href="{_html.escape(href, quote=True)}">'
            f'{mark}</a>')


def terms_html(terms, cls='wb-terms', prefix=GUIDES_PREFIX):
    """A definition list for the terms one section actually marked.

    The hover definitions above are ``title=`` text, which a phone reader
    never sees: there is no hover, ``<abbr>`` is not focusable, and a tap on
    the two terms that carry a guide link is a navigation rather than a
    definition. So the same registry entries are printed once, in reading
    order, at the foot of the section. Built from :data:`TERMS`, never from a
    second copy of the sentences -- the registry test scans for exactly that.

    ``terms`` is the marked terms in the order they were first used; an
    unregistered one raises, for the same reason :func:`abbr_html` does.
    """
    rows = []
    for term in terms:
        key = term.lower()
        if key not in TERMS:
            raise KeyError(f"no glossary entry for {term!r}")
        href = guide_href(term, prefix=prefix)
        name = _html.escape(DISPLAY.get(key, term))
        if href is not None:
            name = (f'<a href="{_html.escape(href, quote=True)}">{name}</a>')
        rows.append(f'<dt>{name}</dt>'
                    f'<dd>{_html.escape(TERMS[key])}</dd>')
    if not rows:
        return ''
    return f'<dl class="{cls}">' + ''.join(rows) + '</dl>'
