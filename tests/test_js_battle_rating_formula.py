"""The three Node harnesses must use the BATTLE PAGE's rating formula.

pvpoke has two different battle-rating expressions and they are not the
same number:

* ``Pokemon.js:2124`` ``getBattleRating``:
  ``Math.floor((500 * damage) + (500 * health))`` -- scale each ratio by
  500, THEN sum. This is what ``Battle.js:665`` stores in
  ``battleRatings``, what the battle page shows, and what
  ``BattleResult.pvpoke_score`` (battle.py) mirrors.
* ``Ranker.js:329`` ``Math.floor((healthRating + damageRating) * 500)``
  -- sum THEN scale. Used only for the offline rankings.

Floating point makes them differ by 1 on exact fractions: with health
= 1 and damage = 46/125, sum-then-scale lands 683 and scale-then-sum
lands 684. Our three harnesses (``pvpoke_url_run.js``,
``pvpoke_sandbox_driver.js``, ``pvpoke_trace.js``) all carried the
Ranker form and a comment citing ``Ranker.js:325-332``, which produced
spurious 1-point "oracle divergences" against our own engine
(Forretress vs Corsola-G / Clodsire, GL 2-0) -- fixed 2026-08-27.

Two halves, per the source-scan rules in CLAUDE.md: an absence pin on
the Ranker form with a positive control that the replacement is
actually there, and a node arithmetic pin proving the two forms really
do disagree (so the absence pin is not guarding a distinction without a
difference).
"""
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / 'scripts'
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(_ROOT / 'src'))

from test_win_boundary import strip_js  # noqa: E402

HARNESSES = ('pvpoke_url_run.js', 'pvpoke_sandbox_driver.js',
             'pvpoke_trace.js')

# Ranker.js:329's shape: "(<health expr> + <damage expr>) * 500", i.e. a
# single `* 500` applied to a parenthesised sum. Tolerant about spacing and
# about which ratio comes first.
_SUM_THEN_SCALE = re.compile(r'\)\s*\)\s*\*\s*500')

# Pokemon.js:2124's shape: two separate `500 *` factors added together.
_SCALE_THEN_SUM = re.compile(r'500\s*\*.*\+.*500\s*\*', re.S)


@pytest.mark.parametrize('name', HARNESSES)
def test_harness_uses_the_battle_page_rating_formula(name):
    """Absence pin + positive control on each harness's score function."""
    src = strip_js((_SCRIPTS / name).read_text())
    body = [ln for ln in src.splitlines()
            if 'Math.floor' in ln and '500' in ln]
    assert body, f'{name}: no Math.floor(...500...) score line found at all'
    joined = '\n'.join(body)
    assert not _SUM_THEN_SCALE.search(joined), (
        f'{name} uses Ranker.js:329 sum-then-scale, which is 1 low on '
        f'exact fractions and is NOT the battle page number:\n{joined}')
    # Positive control: the canonical replacement must actually be present,
    # so this test fails loudly if the score function is deleted or renamed
    # rather than passing vacuously.
    assert _SCALE_THEN_SUM.search(joined), (
        f'{name}: no scale-then-sum (Pokemon.js:2124) score expression '
        f'found; the absence pin above would pass vacuously:\n{joined}')


@pytest.mark.parametrize('name', HARNESSES)
def test_harness_comment_cites_pokemon_js_not_ranker(name):
    """The misleading provenance comment is what kept the bug alive across
    three copies. Every harness must name Pokemon.js as the source; a
    Ranker.js mention is allowed only as the explicit counter-example."""
    text = (_SCRIPTS / name).read_text()
    assert 'Pokemon.js:2124' in text, (
        f'{name}: score formula must cite Pokemon.js:2124 getBattleRating')


def _node():
    exe = shutil.which('node')
    if exe is None:
        pytest.skip('node not installed')
    return exe


def test_the_two_formulas_actually_disagree():
    """Discriminating case (Forretress vs Corsola-G / Clodsire GL 2-0):
    health = 1, damage = 46/125. Sum-then-scale -> 683, scale-then-sum ->
    684. If JS ever stopped disagreeing here, the pins above would be
    guarding nothing."""
    out = subprocess.run(
        [_node(), '-e',
         'const h=1,d=46/125;'
         'process.stdout.write(JSON.stringify(['
         'Math.floor((h+d)*500), Math.floor((500*d)+(500*h))]))'],
        capture_output=True, text=True, check=True).stdout
    assert out == '[683,684]', f'node arithmetic drifted: {out}'


def test_python_pvpoke_score_matches_the_battle_page_form():
    """Our engine's side of the same pin: BattleResult.pvpoke_score must
    land on 684, not 683, for the discriminating case."""
    from gopvpsim.battle import BattleResult
    r = BattleResult(winner=0, turns=1, hp_remaining=[100, 79],
                     max_hp=[100, 125], shields_remaining=[0, 0],
                     energy_remaining=[0, 0])
    assert (r.max_hp[1] - r.hp_remaining[1]) / r.max_hp[1] == 46 / 125
    assert r.pvpoke_score(0) == 684
    assert math.floor((1 + 46 / 125) * 500) == 683  # the wrong answer
