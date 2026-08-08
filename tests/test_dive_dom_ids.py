"""Every ``getElementById('...')`` in the shipped dive JS must resolve.

DRY review 2026-08-05, entry 12 (``js-py-dom-id-registry``). The dive's
DOM contract is split across two languages: Python string literals in
``deep_dive.py`` emit ``id="..."`` attributes, and the JS files injected
into the page look them up by literal. Nothing connected the two -- rename
an id on the Python side and the JS lookup returns ``null``, which in most
of these call sites is a silent no-op (a control that stops working, not
an error anyone sees). ~39 ids are wired this way.

The review's explicit call was "a guard, not a constants file": the ids
read naturally inside the HTML string literals that emit them, and a
manifest would just be a third place to keep in sync. So this test renders
one real (tiny) dive via the shared ``small_dive_html`` fixture and checks
that every literal id resolves in the produced HTML.

Coverage boundary, stated because it is easy to over-trust this file:

* Only LITERAL ids are checked. ``deep_dive_engine.js`` also has five
  computed lookups (``getElementById(hostId)`` and friends) whose argument
  is built at runtime; no static scan can reach those.
* An id only reachable under page chrome the fixture does not render is
  not really covered. That is why ``conftest.SMALL_DIVE_ARGS`` carries a
  per-flag rationale -- the flags exist to make every conditional block
  render. Today the fixture covers all of them.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / 'scripts'

# The JS files deep_dive.py injects into the page (pvpoke_trace.js is a
# node oracle harness, never shipped, so it is deliberately absent), each
# with a probe string used only to prove the file reached the page. Any
# stable line works; these three are function headers other tests already
# pin, so they will not drift out from under this one silently. The engine
# file cannot be compared wholesale -- _interactive_js_engine substitutes
# nine __PLACEHOLDER__ tokens on the way in.
SHIPPED_JS = {
    SCRIPTS / 'deep_dive_engine.js': 'function getScoreKeyAt(',
    SCRIPTS / 'cmp_panels.js': 'function cmpCellHtml(',
    SCRIPTS / 'deep_dive_user_collection.js': 'function parseCsvText(',
}

_ID_RE = re.compile(r"""getElementById\(\s*(['"])([A-Za-z0-9_:.-]+)\1\s*\)""")


def _literal_ids(text):
    return {m.group(2) for m in _ID_RE.finditer(text)}


def _shipped_js_ids():
    ids = set()
    for path in SHIPPED_JS:
        ids |= _literal_ids(path.read_text())
    return ids


def test_id_scan_finds_the_expected_scale():
    """Anti-vacuity: a regex that stops matching must fail loudly here
    rather than turn the real guard below into a no-op. The review counted
    39 literal ids; the floor leaves room for deletions without churn."""
    ids = _shipped_js_ids()
    assert len(ids) >= 35, f'only {len(ids)} literal DOM ids found: {sorted(ids)}'


def test_shipped_js_is_actually_injected(small_dive_html):
    """Second anti-vacuity guard, and the one that matters most: the ids
    come from the Python side, so a page that dropped the JS entirely
    would still carry every ``id=`` attribute and pass the check below."""
    for path, probe in SHIPPED_JS.items():
        assert probe in path.read_text(), f'{path.name}: stale probe {probe!r}'
        assert probe in small_dive_html, f'{path.name} not injected into the dive'


def test_every_literal_dom_id_resolves(small_dive_html):
    """The guard itself: every id the shipped JS looks up by literal --
    from the JS files AND from the inline JS deep_dive.py emits -- is
    emitted as an ``id=`` attribute somewhere on the page."""
    ids = _shipped_js_ids() | _literal_ids(small_dive_html)
    missing = sorted(i for i in ids
                     if f'id="{i}"' not in small_dive_html
                     and f"id='{i}'" not in small_dive_html)
    assert not missing, (
        'JS looks up DOM ids the rendered dive never emits: '
        f'{missing}. Either the emitting Python was renamed/removed, or the '
        'block that emits it needs a flag added to conftest.SMALL_DIVE_ARGS.')


@pytest.mark.parametrize('sample', ['plot', 'summary', 'cmp-body',
                                    'collection-csv', 'scenario-sel'])
def test_known_ids_are_in_the_scan(sample):
    """Cheap pin on the scan's shape: these five span the plot, the tables,
    the compare widget, the collection paste-box and the control strip. If
    the regex drifts to matching only some call spellings, this catches it
    without needing the render."""
    assert sample in _shipped_js_ids()


# ---------------------------------------------------------------------------
# Duplicate-id guard
# ---------------------------------------------------------------------------
#
# TODO.md carried "duplicate DOM ids on dive pages" (predive gate
# 2026-08-06): ``af-<hash>`` x3 per page plus ``dd-recommendations`` /
# ``dd-threshold-tiers`` x2, called invalid HTML. Re-derived 2026-08-08
# against two shipped pages (melmetal-great-league m1,
# azumarill-great-league m1) and the fixture below: BOTH halves of that
# finding are artifacts of the text scan that produced it, not defects.
#
#   * ``af-<hash>`` is never emitted as an ``id`` at all. It ships as
#     ``data-anchor-id="af-..."`` (deep_dive_rendering.anchor_group_id ->
#     the ``span.user-anchor-hits`` placeholder), read by
#     annotateAnchorBullets via querySelectorAll, which is *meant* to hit
#     every copy. A dup-id regex without a left boundary guard matches the
#     ``-id="`` tail of ``data-anchor-id="``; that is where "x3" came from.
#     Pinned by test_anchor_group_id_is_a_data_attribute_not_an_id below.
#   * The second ``dd-recommendations`` / ``dd-threshold-tiers`` lives
#     inside ``<template id="dd-bb-prose-tmpl">`` -- the best-buddy L51
#     variant of the same section (deep_dive.py, ``_bb_active`` branch).
#     Template content is parsed into a separate DocumentFragment, so it
#     is not in the document tree, ``getElementById`` cannot see it, and
#     the id-uniqueness requirement does not span the boundary. The JS
#     swaps by assigning ``host.innerHTML`` (deep_dive_engine.js
#     setBestBuddyLevel), so exactly one copy is ever live.
#
# So there was nothing to de-dupe. What was missing is the guard, which is
# what these tests are: the invariant is checked on BOTH document states a
# reader can actually observe -- L50 (template inert) and L51 (each host's
# children replaced by its template's) -- so a genuinely duplicated id in
# either state fails here instead of being re-discovered by hand.

_VOID_TAGS = frozenset((
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
    'meta', 'param', 'source', 'track', 'wbr'))

_BB_PAIR_RE = re.compile(
    r"""_bbInitHost\(\s*(['"])([\w:.-]+)\1\s*,\s*(['"])([\w:.-]+)\3\s*\)""")


def _bb_host_pairs():
    """{host id: template id} for every best-buddy swap, read from the JS
    that performs the swap so the pair list cannot drift away from it."""
    js = (SCRIPTS / 'deep_dive_engine.js').read_text()
    return {m.group(2): m.group(4) for m in _BB_PAIR_RE.finditer(js)}


class _IdContextCollector(HTMLParser):
    """Record every ``id=`` attribute together with the container it sits in.

    Context is the innermost enclosing ``<template>`` (``tmpl:<id>``) or
    best-buddy host (``host:<id>``), else ``doc``. A real tag stack is
    needed because hosts wrap arbitrarily nested markup; ``</tag>`` pops to
    the nearest matching open tag, which is enough for generated HTML.

    ``<script>``/``<style>`` bodies never reach handle_starttag at all --
    HTMLParser reads them as CDATA -- so the score-pack decoder template
    and other JS string literals cannot spoof an id.
    """

    def __init__(self, hosts):
        super().__init__(convert_charrefs=True)
        self._hosts = hosts
        self._stack = []          # [(tag, pushed_context or None)]
        self._ctx = ['doc']
        self.rows = []            # [(id value, context)]

    def handle_starttag(self, tag, attrs):
        if tag in _VOID_TAGS:
            self.handle_startendtag(tag, attrs)
            return
        el_id = dict(attrs).get('id')
        if el_id:
            self.rows.append((el_id, self._ctx[-1]))
        pushed = None
        if tag == 'template':
            pushed = 'tmpl:' + (el_id or '<anonymous>')
        elif el_id in self._hosts:
            pushed = 'host:' + el_id
        self._stack.append((tag, pushed))
        if pushed:
            self._ctx.append(pushed)

    def handle_startendtag(self, tag, attrs):
        el_id = dict(attrs).get('id')
        if el_id:
            self.rows.append((el_id, self._ctx[-1]))

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS:
            return
        for k in range(len(self._stack) - 1, -1, -1):
            if self._stack[k][0] == tag:
                for _, pushed in self._stack[k:]:
                    if pushed:
                        self._ctx.pop()
                del self._stack[k:]
                return


def _duplicates(ids):
    seen, dups = set(), {}
    for i in ids:
        if i in seen:
            dups[i] = dups.get(i, 1) + 1
        seen.add(i)
    return dups


@pytest.fixture(scope='session')
def dive_id_rows(small_dive_html):
    """[(id, context)] for the rendered dive, one row per ``id=`` attribute."""
    parser = _IdContextCollector(_bb_host_pairs())
    parser.feed(small_dive_html)
    return parser.rows


def test_bb_host_pairs_are_read_from_the_engine():
    """Anti-vacuity: with no pairs the L51 view below collapses into the
    L50 view and stops testing anything."""
    pairs = _bb_host_pairs()
    assert pairs, 'no _bbInitHost(host, tmpl) pairs found in deep_dive_engine.js'
    assert 'dd-bb-prose-host' in pairs


def test_id_contexts_cover_live_and_template(dive_id_rows):
    """Anti-vacuity for the two view assertions: the fixture must really
    render a best-buddy host AND its template, or the L50/L51 split is a
    no-op and the guard degenerates to one flat scan."""
    contexts = {ctx.split(':')[0] for _, ctx in dive_id_rows}
    assert 'host' in contexts and 'tmpl' in contexts, (
        f'fixture rendered no best-buddy host/template pair: {contexts}. '
        'Either the dive stopped emitting one (then this guard needs '
        'rewriting) or SMALL_DIVE_ARGS lost the flag that turns it on.')
    assert len(dive_id_rows) >= 40, (
        f'only {len(dive_id_rows)} ids parsed -- the collector is probably '
        'not seeing the page')


def test_no_duplicate_ids_in_the_live_page(dive_id_rows):
    """L50 view: everything outside ``<template>``. This is the document
    getElementById actually walks on load."""
    live = [i for i, ctx in dive_id_rows if not ctx.startswith('tmpl:')]
    dups = _duplicates(live)
    assert not dups, f'duplicate DOM ids in the rendered dive: {dups}'


def test_no_duplicate_ids_after_the_best_buddy_swap(dive_id_rows):
    """L51 view: setBestBuddyLevel('51') replaces each host's children with
    its template's, so the observable document is doc-level ids + template
    ids, with the host's own subtree gone."""
    swapped = [i for i, ctx in dive_id_rows
               if ctx == 'doc' or ctx.startswith('tmpl:')]
    dups = _duplicates(swapped)
    assert not dups, (
        f'duplicate DOM ids after the best-buddy L51 swap: {dups}. The L51 '
        'variant of a section must reuse only ids that live inside its host.')


def test_anchor_group_id_is_a_data_attribute_not_an_id():
    """``af-<hash>`` repeats across grouping passes by design (tier cards
    and the flat anchor list render the same bullet). That is legal only
    because it ships as ``data-anchor-id`` -- annotateAnchorBullets uses
    querySelectorAll and fills every copy. Promoting it to ``id=`` would
    turn the repetition into real duplicate ids AND leave all but the
    first copy unannotated.
    """
    from gopvpsim.anchors import ResolvedAnchor

    from tests.conftest import load_deep_dive

    deep_dive = load_deep_dive()
    anchor = ResolvedAnchor(
        name='mirror_blkp_any', parent_display_name='mirror bulk',
        parent='mirror_blkp_any', kind='bulkpoint',
        threshold_value=103.54, target_stat='def', opponent='Annihilape',
    )
    rec = {'anchor': anchor, 'opponent': 'Annihilape',
           'scenarios': [(2, 2)], 'direction': 'gain', 'passing_ivs': [0, 3]}
    sink = {}
    out = deep_dive.rendering.render_anchor_flip_bullets(
        [rec], anchor_passing_sink=sink)
    assert len(sink) == 1
    anchor_id = next(iter(sink))
    assert anchor_id.startswith('af-')
    assert f'data-anchor-id="{anchor_id}"' in out[0]
    assert f'id="{anchor_id}"' not in out[0].replace('data-anchor-id=', '')
