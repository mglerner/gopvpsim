"""A no-op best-buddy dive renders ONE level pass and ships no L51 <template>s.

When best buddy is provably a no-op for a species/league (every IV already
CP-capped below the alt level), ``deep_dive.py`` aliases the L50 grids as the
L51 grids. Until 2026-09-25 the render still ran a full second
``_render_level_body`` on those aliases and shipped its output in
``<template id="dd-bb-*-tmpl">`` blocks: the same fight with renumbered ids
plus a misleading "builds pinned to the league cap" card note, at ~30 s per
page (~4.6 h of the 2026-09-20 bake; docs/perf/
2026-09-25_bake_attribution_and_cruft_scout.md, R3). Michael's decision
(Q3, 2026-09-25): skip the pass and drop the templates. The sidenav toggle
stays (with its "no change for this mon" hint) and degrades to a DATA-only
rebind, because ``_bbInitHost`` skips a host whose template is absent.

Pre-fix values, for the record: the no-op Bastiodon render below called
``generate_analysis_sections`` TWICE per page and shipped
``dd-bb-card-tmpl`` + ``dd-bb-prose-tmpl``.
"""
import re
import sys

import pytest

from tests.conftest import REPO_ROOT, load_deep_dive

ENGINE_JS = REPO_ROOT / 'scripts' / 'deep_dive_engine.js'
_TMPL_RE = re.compile(r'<template id="(dd-bb-[a-z]+-tmpl)">')

# Bastiodon GL is CP-capped below L50 at every IV, so best buddy (auto-on in
# Great League) is a no-op. Smallest args that still render the card + prose.
NOOP_ARGS = [
    'Bastiodon', '--league', 'great',
    '--opponents', '2', '--species-iv-floor', '14,14,14',
    '--no-thresholds', '--no-mirror-slayer',
    '--no-cache', '--no-sweep-cache', '--no-replay-dump',
    '--quiet', '--log-file', '/dev/null',
]


@pytest.fixture(scope='module')
def noop_render(tmp_path_factory):
    """(html text, generate_analysis_sections call count, pages written)."""
    dd = load_deep_dive()
    out = tmp_path_factory.mktemp('bb_noop') / 'bb_noop.html'
    real = dd.generate_analysis_sections
    calls = []

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    old_argv = sys.argv
    sys.argv = ['deep_dive.py'] + NOOP_ARGS + ['--html', str(out)]
    dd.generate_analysis_sections = counting
    try:
        dd.main()
    finally:
        dd.generate_analysis_sections = real
        sys.argv = old_argv
    pages = sorted(out.parent.glob('*.html'))
    return out.read_text(), len(calls), len(pages)


@pytest.mark.slow
def test_noop_best_buddy_renders_one_level_pass(noop_render):
    html, n_calls, n_pages = noop_render
    # Anti-vacuity: this really is a best-buddy no-op page (toggle + hint).
    assert 'id="dd-bb-toggle"' in html
    assert '(no change for this mon)' in html
    assert n_pages >= 1
    # One analysis pass per page, not two (pre-fix: 2 * n_pages).
    assert n_calls == n_pages, (n_calls, n_pages)
    assert _TMPL_RE.findall(html) == []


@pytest.mark.slow
def test_noop_best_buddy_keeps_hosts_the_engine_tolerates(noop_render):
    """The live hosts stay (unstyled wrappers), and the engine's host
    registration returns early when the template is missing, so the toggle
    rebinds DATA only -- no null dereference on a template-less page."""
    html, _, _ = noop_render
    assert 'id="dd-bb-prose-host"' in html
    js = ENGINE_JS.read_text()
    init = js[js.index('function _bbInitHost('):js.index('function _initBestBuddy(')]
    assert 'if (!host || !tmpl) return;' in init


@pytest.mark.render
def test_active_best_buddy_still_renders_both_levels(small_dive_html):
    """Positive control: the shared fixture (Marill GL, best buddy ACTIVE)
    still ships the L51 prose and card templates."""
    found = set(_TMPL_RE.findall(small_dive_html))
    assert {'dd-bb-prose-tmpl', 'dd-bb-card-tmpl'} <= found, found
