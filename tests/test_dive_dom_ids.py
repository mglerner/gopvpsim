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
