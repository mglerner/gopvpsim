"""Win/tie boundary: single source of truth + anti-drift regression guard.

A PvP battle rating of EXACTLY 500 is a TIE, not a win (per vendored PvPoke
BattleHistogram.js/Interface.js/Battle.js). The win predicate is therefore
``score > 500``. This boundary drifted THREE times when it was open-coded as a
bare ``500`` literal AND as a ``win_threshold`` parameter, with the ``>`` vs
``>=`` operator hand-copied at ~20 sites:

  1. session-3: deep_dive_engine.js + _won_set shipped ``>= 500``;
  2. commit ddb996a: "finished unifying" but a literal-only grep missed the
     ``>= win_threshold`` variable form;
  3. an all-Opus DRY audit found six per-cell ``>= win_threshold`` survivors
     in the render/analysis path.

`gopvpsim.battle.is_win` / `WIN_RATING` are now the single source. This test
pins the helper semantics AND source-scans the win-classification scripts so a
new ``>= win_threshold`` / ``>= WIN_RATING`` per-cell win check can't land
silently again. (The cohort-MEAN break-even gate in synthesize_mirror_tier is
the one documented, allow-listed ``>=`` -- a float mean where exact-500 is
measure-zero, a deliberately different "wins on average" semantic.)
"""
import tokenize
from pathlib import Path

import numpy as np

from gopvpsim.battle import is_win, WIN_RATING

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / 'scripts'

# The only legitimate ``>= win_threshold`` site: the cohort-MEAN break-even
# gate. Keyed by the left-hand operand so a new per-cell ``>=`` can't hide.
_ALLOWED_GE = ('pass_mean',)


def test_win_rating_is_500():
    assert WIN_RATING == 500


def test_is_win_treats_500_as_tie():
    assert is_win(501) is True
    assert is_win(500) is False   # exactly 500 is a TIE, not a win
    assert is_win(499) is False


def test_is_win_elementwise_on_numpy():
    got = is_win(np.array([499, 500, 501, 720]))
    assert got.tolist() == [False, False, True, True]


def test_no_ge_against_win_boundary_variable_in_scripts():
    """No per-cell win check may use ``>= win_threshold`` / ``>= WIN_RATING``.

    This is the exact regression that recurred: the win boundary written as a
    variable (not the literal ``500``) slipped past a literal-only grep. Any
    new such site must either use ``>`` or be added to the documented
    cohort-mean allow-list above.

    Tokenize (not regex) so the match is a real ``>=`` OPERATOR followed by the
    NAME token -- string/docstring/comment occurrences are structurally
    excluded, not heuristically.
    """
    _GE_NAMES = {'win_threshold', 'WIN_RATING'}
    offenders = []
    for py in sorted(SCRIPTS.glob('*.py')):
        lines = py.read_text().splitlines()
        prev = None  # previous significant token
        with open(py, 'rb') as fh:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type in (tokenize.NL, tokenize.NEWLINE,
                                tokenize.INDENT, tokenize.DEDENT,
                                tokenize.COMMENT, tokenize.ENCODING):
                    continue
                if (tok.type == tokenize.NAME and tok.string in _GE_NAMES
                        and prev is not None
                        and prev.type == tokenize.OP and prev.string == '>='):
                    ln = tok.start[0]
                    text = lines[ln - 1] if ln <= len(lines) else ''
                    if any(a in text for a in _ALLOWED_GE):
                        prev = tok
                        continue
                    offenders.append(f'{py.name}:{ln}: {text.strip()}')
                prev = tok
    assert not offenders, (
        'win boundary drifted back to ">=" (500 must be a TIE -> use "> '
        'win_threshold" or is_win()):\n  ' + '\n  '.join(offenders))
