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
        "league's CP cap -- the bulk-first build most IV tools list first.",
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
}

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
