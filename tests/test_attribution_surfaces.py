"""PvPoke attribution + support footer must survive onto the shipped dive page.

``src/gopvpsim/attribution.py`` is imported by 12 renderers, and exactly ONE
test asserted its text reaches rendered output -- tests/test_cup_plumbing.py:183,
covering the site index only.  The module being "pure string constants" is
what made it look low-risk; the actual risk is a RENDERER that stops emitting
them.  PvPoke attribution is a credit obligation on public pages, not chrome:
the battle engine here is a port of PvPoke's logic and every byte of game data
comes from PvPoke.  2026-08-09 test-suite review, blind-spots E7.

Scope is deliberately TWO surfaces, not twelve.  The dive page is the
highest-traffic one and is already rendered for free by the session-scoped
``small_dive_html`` fixture; sweeping all 12 renderers would need real output
under ``userdata/``, which reintroduces the machine-dependent skip pattern the
review flagged. The canonical constants are imported here rather than
re-typed, so a wording change moves both sides at once and this test keeps
asserting "the renderer emits THE constant", never a particular sentence.
"""
import pytest

from gopvpsim.attribution import (
    PVPOKE_ATTRIBUTION_HTML, PVPOKE_SITE, PVPOKE_REPO, support_footer_html,
)


@pytest.mark.render
def test_dive_page_carries_the_pvpoke_attribution(small_dive_html):
    assert PVPOKE_ATTRIBUTION_HTML in small_dive_html, (
        'the rendered deep-dive page no longer contains '
        'attribution.PVPOKE_ATTRIBUTION_HTML verbatim (scripts/deep_dive.py:3091). '
        'This is the credit obligation for the ported battle engine and the '
        'gamemaster data, so it is not optional page chrome.')
    # Both canonical links must be live on the page, not just the prose.
    assert PVPOKE_SITE in small_dive_html
    assert PVPOKE_REPO in small_dive_html


@pytest.mark.render
def test_dive_page_carries_the_support_footer(small_dive_html):
    """The dive lives one directory deep, so its footer must use the ``../``
    prefix -- a footer rendered with the wrong prefix ships a 404."""
    assert support_footer_html('../') in small_dive_html, (
        'the rendered deep-dive page no longer contains '
        'attribution.support_footer_html("../") verbatim '
        '(scripts/deep_dive.py:3160).')
    # The root-relative variant would mean the prefix argument was dropped.
    assert support_footer_html('') not in small_dive_html


def test_support_footer_prefix_reaches_both_links():
    """Unit-level companion so a prefix regression is diagnosable without a
    14-second render."""
    for prefix, href in (('', 'support.html'),
                         ('../', '../support.html'),
                         ('../../', '../../support.html')):
        html = support_footer_html(prefix)
        assert html.count(f'href="{href}"') == 2, html
        assert 'Support the developer' in html and 'Credits' in html


def test_attribution_constants_are_ascii_only():
    """The unicode-dash ship gate scans rendered HTML; these constants are
    emitted into every page, so keep them ASCII at the source (attribution.py
    says so in two docstrings, and nothing checked it)."""
    for label, text in (('PVPOKE_ATTRIBUTION_HTML', PVPOKE_ATTRIBUTION_HTML),
                        ('support_footer_html', support_footer_html('../'))):
        offenders = sorted({ch for ch in text if ord(ch) > 127})
        assert not offenders, f'{label} carries non-ASCII: {offenders}'
