"""The Cramorant strategy article's "See it for yourself" links must
replay, on PvPoke's own engine, the scores they advertise.

Boundary contract on the RENDERED artifact (not the renderer): every
"PvPoke's plan (loses, N)" link, decoded from its URL string the way
pvpoke.com does and run through PvPoke's Battle.js, must score exactly N
and be a loss; every "our line (wins, M)" sandbox link must score exactly
M and be a win.

Pre-fix values, from the article as published 2026-08-27 and still live
on 2026-09-12 (hardcoded links, encoded with the pre-e6827a0 turn clock,
scores from pre-rebalance sims): showcase 1's sandbox link replayed 634
against its advertised 674; showcase 3's replayed 493 -- a LOSS --
against 541; showcase 2's PLAIN link replayed a 642 WIN against
"loses, 467". This test fails on that page and passes on the render that
computes and verifies the showcases at build time.

Needs node + the ../pvpoke checkout + a rendered article, hence
local_artifacts; ~8 Battle.js runs, hence slow.
"""
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

pytestmark = [pytest.mark.local_artifacts, pytest.mark.slow]

ARTICLE = REPO / 'userdata' / 'website' / 'articles' / \
    'cramorant-pogodives-strategy' / 'index.html'
_PVPOKE = REPO.parent / 'pvpoke'
if not ARTICLE.exists():
    pytest.skip('strategy article not rendered', allow_module_level=True)
if not _PVPOKE.exists() or shutil.which('node') is None:
    pytest.skip('../pvpoke checkout or node not present',
                allow_module_level=True)

from pvpoke_sandbox import verify_url  # noqa: E402

_PAIR_RE = re.compile(
    r'<a href="(https://pvpoke\.com/battle/\d+/[^"]+)">PvPoke\'s plan '
    r'\(loses, (\d+)\)</a>\s*&middot;\s*'
    r'<a href="(https://pvpoke\.com/battle/sandbox/[^"]+)">our line '
    r'\(wins, (\d+)\)</a>')


def _pairs():
    html = ARTICLE.read_text()
    start = html.index('<h2>See it for yourself, on PvPoke</h2>')
    end = html.index('<h2>Caveats</h2>')
    return _PAIR_RE.findall(html[start:end])


def test_showcase_pairs_present():
    # Floor below today's four: the section must exist and be non-trivial,
    # or the per-link test below would pass vacuously.
    assert len(_pairs()) >= 3


@pytest.mark.parametrize('plain, lose, sandbox, win', _pairs(),
                         ids=lambda v: v[:0] if not str(v).isdigit()
                         else str(v))
def test_showcase_links_replay_their_advertised_scores(plain, lose,
                                                       sandbox, win):
    lose, win = int(lose), int(win)
    got_plain = verify_url(plain)
    assert round(got_plain['score'][0]) == lose, plain
    assert lose < 500
    got_sb = verify_url(sandbox)
    assert round(got_sb['score'][0]) == win, sandbox
    assert win > 500
    # Robust to PvPoke fixing its hasActed leak: the page's first and
    # second runs must end identically, or the link is right by accident.
    assert got_sb['firstRun']['hp'] == got_sb['hp'], sandbox
    # The sandbox script must actually drive the fight: a sandbox replay
    # that merely coincides with PvPoke's AI would score the plain number.
    assert round(got_sb['score'][0]) != round(got_plain['score'][0])
