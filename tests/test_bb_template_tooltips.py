"""Tooltips must survive the best-buddy (L51) template swap.

Dive pages ship tooltip text once, in ``DATA.tooltips``, and mark each
element with ``data-t="<sid>"``; a DOMContentLoaded pass copies the text
into ``title=``. With the best-buddy toggle active the whole prose (and
the dive card) is rendered TWICE -- the L50 copy lives in
``#dd-bb-prose-host``, the L51 copy rides in an inert
``<template id="dd-bb-prose-tmpl">`` that ``setBestBuddyLevel`` swaps into
the host.

Two separate things can go wrong there, and only one of them ever did:

1. **Registry completeness (checked 2026-08-27: NOT broken).** The
   suspicion in TODO was that the tooltip registry is the same bug class
   as the ``#opp-<slug>`` registry fixed in ``b43bd2d`` -- i.e. that the
   L51 pass inherits an exhausted registry and ships entry-less markup.
   It is not: ``_TooltipRegistry.register`` is keyed by TEXT and returns
   the cached sid on a repeat, so the second pass re-emits the SAME sids
   rather than nothing, and ``dump_tooltip_registry()`` runs AFTER the
   L51 render pass, so any L51-only text is in the table too. Pinned by
   ``test_every_data_t_sid_resolves_in_the_tooltip_table`` (the dump
   ordering is the part a future edit could break).

2. **In-browser hydration (WAS broken).**
   ``document.querySelectorAll('[data-t]')`` does not descend into
   ``<template>`` content -- it lives in an inert DocumentFragment, not
   in the document tree -- so the DOMContentLoaded pass never touches
   the L51 copy, and ``setBestBuddyLevel`` did not re-run it after the
   swap. Every tooltip on the L51 half was therefore missing (and on a
   ``defaultDisplay: 51`` dive, missing from first paint). Fixed by
   exposing the pass as ``window.ddPopulateTooltips`` and calling it
   right after the host swap.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_win_boundary import strip_js  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_JS = REPO_ROOT / 'scripts' / 'deep_dive_engine.js'

_DATA_T_RE = re.compile(r'data-t="([^"]+)"')
_TMPL_RE = re.compile(r'<template id="(dd-bb-[a-z]+-tmpl)">')


def _set_bb_level_body(text):
    """``setBestBuddyLevel``'s code, comments/strings blanked out."""
    start = text.index('function setBestBuddyLevel(')
    end = text.index('window.setBestBuddyLevel', start)
    return strip_js(text[start:end])


def _templates(html):
    """{template id: inner HTML} for the best-buddy <template>s in a page."""
    out = {}
    for m in _TMPL_RE.finditer(html):
        end = html.index('</template>', m.end())
        out[m.group(1)] = html[m.end():end]
    return out


# ---------------------------------------------------------------------------
# Source-level: the swap must re-hydrate
# ---------------------------------------------------------------------------

def test_set_best_buddy_level_rehydrates_tooltips_after_the_swap():
    """The innerHTML swap injects data-t markup the load-time pass never saw.

    Pre-fix (2026-08-27) this call did not exist and the L51 prose had zero
    title= attributes in the browser.
    """
    body = _set_bb_level_body(ENGINE_JS.read_text())
    swap_at = body.index('host.innerHTML = _bbHostHTML[hid][mode]')
    hydrate_at = body.find('ddPopulateTooltips()')
    assert hydrate_at != -1, (
        'setBestBuddyLevel swaps <template> content into the live document '
        'but never re-runs the tooltip pass. document.querySelectorAll '
        "('[data-t]') cannot see inside a <template>, so the swapped-in L51 "
        'prose/card ships data-t attrs with no title=. Call '
        'window.ddPopulateTooltips() after the host swap.')
    assert hydrate_at > swap_at, (
        'ddPopulateTooltips() runs BEFORE the innerHTML swap, so it hydrates '
        'the outgoing copy instead of the incoming one.')


# ---------------------------------------------------------------------------
# Rendered artifact
# ---------------------------------------------------------------------------

@pytest.mark.render
def test_bb_templates_ship_tooltip_markup_that_needs_hydrating(small_dive_html):
    """Anti-vacuity for the guard above + the page must define the hook.

    Records the pre-fix state (2026-08-27): the L51 prose template carries
    79 ``data-t`` attrs on the small_dive fixture (760 on a real Cramorant
    Great dive), ZERO hydration calls existed anywhere in the page, and the
    load-time pass could not reach any of them -- so every one of those
    tooltips was dead in the browser.
    """
    tmpls = _templates(small_dive_html)
    assert 'dd-bb-prose-tmpl' in tmpls, (
        'fixture rendered no best-buddy prose template -- this guard is '
        'vacuous without one (see SMALL_DIVE_ARGS in conftest).')
    n_tmpl = len(_DATA_T_RE.findall(tmpls['dd-bb-prose-tmpl']))
    assert n_tmpl > 0, (
        'no data-t attrs inside the L51 prose template; if tooltips stopped '
        'being emitted there, this whole guard is moot and should be revisited')
    assert 'window.ddPopulateTooltips = populate;' in small_dive_html, (
        'the page never exposes the tooltip pass, so setBestBuddyLevel has '
        'nothing to call after the template swap')
    assert 'ddPopulateTooltips()' in _set_bb_level_body(small_dive_html), (
        'the inlined engine in the rendered page does not re-hydrate '
        'tooltips after the best-buddy swap')


@pytest.mark.render
def test_every_data_t_sid_resolves_in_the_tooltip_table(small_dive_html):
    """The L51 pass must not emit sids that post-date the registry dump.

    ``data_obj['tooltips'] = dump_tooltip_registry()`` has to run AFTER the
    best-buddy render pass; hoisting it above would leave every L51-only
    tooltip pointing at a missing table entry. This is the check that shows
    the tooltip registry is NOT the ``b43bd2d`` bug class -- nothing is lost
    across the two passes today.
    """
    m = re.search(r'<script>var DATA = (\{.*?\});\n', small_dive_html, re.S)
    assert m is not None, 'no embedded DATA blob in the rendered page'
    tips = json.loads(m.group(1)).get('tooltips') or {}
    assert tips, 'DATA.tooltips is empty -- the comparison would be vacuous'

    tmpls = _templates(small_dive_html)
    tmpl_sids = set(_DATA_T_RE.findall(tmpls.get('dd-bb-prose-tmpl', '')))
    assert tmpl_sids, 'no data-t sids in the L51 template -- vacuous'

    # Every sid the page emits ANYWHERE (both copies) must resolve. Scan the
    # body only: the trailing <script> blocks discuss data-t="<sid>" in prose.
    body = small_dive_html[:small_dive_html.index('<script>var DATA = ')]
    unresolved = sorted({s for s in _DATA_T_RE.findall(body) if s not in tips})
    assert not unresolved, (
        f'{len(unresolved)} data-t sid(s) have no DATA.tooltips entry '
        f'(e.g. {unresolved[:5]}) -- dump_tooltip_registry() is running '
        f'before some renderer finished registering.')
    assert tmpl_sids <= set(tips), 'L51 template sids missing from the table'
