"""Each matchup web must identify its own league.

Regression test for the landing-page bug Michael spotted 2026-09-12: the
"Matchup Web" section rendered TWO cards, both titled "Great League matchup
web", both describing "a scatter plot of 4,096 IVs by stat product".

Two independent causes, both fixed:

1. `render_html` hardcoded "Great League" in <title> and <h1>, left over from
   when the module had a `LEAGUE = 'great'` constant instead of a `--league`
   flag. So the Ultra page was mislabelled in its own <title>.
2. Neither `matchups/` nor `matchups-ultra/` carried a `meta.toml`, so
   `build_website_index.py` fell back to the HTML <title> for the name and to
   its GENERIC DIVE blurb for the description -- a dive's description, not a
   matchup web's.
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

_PAGES = [('matchups', 'Great League'), ('matchups-ultra', 'Ultra League')]


def test_renderer_does_not_hardcode_a_league_in_the_title():
    """Source-level: the template must interpolate, not name one league."""
    src = (REPO / 'scripts' / 'build_matchup_web.py').read_text()
    template = src[src.index('<!DOCTYPE html>'):src.index('""".format(')]
    for tag in ('title', 'h1'):
        m = re.search(rf'<{tag}>([^<]*)</{tag}>', template)
        assert m, f'no <{tag}> in the template'
        assert 'League' not in m.group(1) or '{' in m.group(1), (
            f'<{tag}> hardcodes a league name: {m.group(1)!r}')


@pytest.mark.local_artifacts
@pytest.mark.parametrize('slug,league', _PAGES)
def test_built_page_names_its_own_league(slug, league):
    page = REPO / 'userdata' / 'website' / slug / 'index.html'
    if not page.exists():
        pytest.skip(f'no locally built {slug}')
    title = re.search(r'<title>([^<]*)</title>', page.read_text())
    assert title and title.group(1) == f'{league} matchup web', (
        f'{slug} <title> is {title and title.group(1)!r}')


@pytest.mark.local_artifacts
@pytest.mark.parametrize('slug,league', _PAGES)
def test_built_page_carries_a_curated_meta(slug, league):
    """Without meta.toml the index invents a DIVE description for it."""
    meta = REPO / 'userdata' / 'website' / slug / 'meta.toml'
    if not (REPO / 'userdata' / 'website' / slug / 'index.html').exists():
        pytest.skip(f'no locally built {slug}')
    assert meta.exists(), f'{slug}/meta.toml missing'
    import tomllib
    d = tomllib.loads(meta.read_text())
    assert d['title'] == f'{league} matchup web'
    assert league in d['description']
    # The generic dive fallback, which must never describe a matchup web.
    assert '4,096 IVs by stat product' not in d['description']


@pytest.mark.local_artifacts
def test_the_two_matchup_webs_are_distinguishable():
    """The actual user-visible symptom: two identical cards.

    Positive control for the pair above -- they could both pass while the
    landing page still showed duplicates if the titles matched each other.
    """
    built = [(s, REPO / 'userdata' / 'website' / s / 'meta.toml')
             for s, _ in _PAGES]
    if not all(p.exists() for _, p in built):
        pytest.skip('matchup webs not both built locally')
    import tomllib
    titles = [tomllib.loads(p.read_text())['title'] for _, p in built]
    assert len(set(titles)) == len(titles), f'duplicate card titles: {titles}'
