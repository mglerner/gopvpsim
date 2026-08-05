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
import importlib.util
import re
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


# ---------------------------------------------------------------------------
# The Python half above cannot see the JS half of the engine, which is where
# the boundary last regressed (session-3 shipped ``>= 500`` in
# deep_dive_engine.js). The shipped JS open-codes the boundary at ~13 sites --
# the constant is NOT injected from Python today -- so the cheap guard is a
# literal scan for the wrong operator. Comments and strings are stripped by a
# real JS scanner (below), not by regex over raw text: several legitimate
# comments discuss ">= 500" in prose, and several regex literals contain quote
# characters that a naive stripper would swallow.
# ---------------------------------------------------------------------------

_JS_GE_RE = re.compile(r'>=\s*(?:500(?![0-9.])|WIN_RATING\b)')

# Characters after which a `/` starts a regex literal rather than a division.
_RE_PRECEDERS = set('(,=:[!&|?{};+-*%~^<>\n')


def strip_js(text):
    """Blank out JS comments, string literals and regex literals.

    Removed regions are replaced by spaces so line numbers and columns are
    preserved for reporting. Handles ``//`` line comments, ``/* */`` block
    comments, ``'``/``"``/`` ` `` strings with backslash escapes, and regex
    literals (disambiguated from division by the previous significant char).
    """
    out = list(text)
    i, n = 0, len(text)
    prev_sig = '\n'   # last significant (non-space) code character

    def blank(a, b):
        for k in range(a, b):
            if out[k] != '\n':
                out[k] = ' '

    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if c in '\'"`':
            j = i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2
                    continue
                if text[j] == c:
                    j += 1
                    break
                j += 1
            blank(i, j)
            prev_sig = 'x'   # a string is a value, like an identifier
            i = j
            continue
        if c == '/' and prev_sig in _RE_PRECEDERS:
            j, in_class = i + 1, False
            while j < n:
                ch = text[j]
                if ch == '\\':
                    j += 2
                    continue
                if ch == '\n':
                    break            # not a regex after all; bail
                if ch == '[':
                    in_class = True
                elif ch == ']':
                    in_class = False
                elif ch == '/' and not in_class:
                    j += 1
                    break
                j += 1
            blank(i, j)
            prev_sig = 'x'
            i = j
            continue
        if not c.isspace():
            prev_sig = c
        i += 1
    return ''.join(out)


def test_strip_js_detects_only_real_code():
    """The JS scanner itself: code hits found, comment/string/regex hits not.

    Without this, a stripper bug would silently turn the scan below into a
    test that can never fail.
    """
    src = (
        "var a = x >= 500;\n"                       # 1: real offender
        "// historical note: avg >= 500 was wrong\n"  # 2: comment
        "/* block\n   b >= 500 inside\n*/\n"          # 3-5: block comment
        "var s = 'text >= 500 in a string';\n"        # 6: string
        "t.replace(/\">= 500\"/g, '');\n"             # 7: regex with a quote
        "if (score >= WIN_RATING) {}\n"               # 8: variable form
    )
    hits = sorted(
        i + 1 for i, ln in enumerate(strip_js(src).splitlines())
        if _JS_GE_RE.search(ln))
    assert hits == [1, 8]


def test_no_ge_against_win_boundary_in_shipped_js():
    """No ``>= 500`` / ``>= WIN_RATING`` in the shipped JS (500 is a TIE)."""
    offenders = []
    for js in sorted(SCRIPTS.glob('*.js')):
        raw = js.read_text().splitlines()
        for i, line in enumerate(strip_js(js.read_text()).splitlines()):
            if _JS_GE_RE.search(line):
                offenders.append(f'{js.name}:{i + 1}: {raw[i].strip()}')
    assert not offenders, (
        'win boundary drifted back to ">=" in JS (500 must be a TIE -> use '
        '"> 500"):\n  ' + '\n  '.join(offenders))


def test_matchup_clusters_imports_win_rating():
    """scripts/deep_dive_matchup_clusters.py must not re-declare the boundary.

    It used to carry its own ``WIN_RATING = 500`` with a comment promising it
    matched battle.py -- exactly the copy that let the boundary drift before.
    """
    spec = importlib.util.spec_from_file_location(
        'deep_dive_matchup_clusters_winpin',
        SCRIPTS / 'deep_dive_matchup_clusters.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.WIN_RATING is WIN_RATING
    src = (SCRIPTS / 'deep_dive_matchup_clusters.py').read_text()
    assert not re.search(r'^WIN_RATING\s*=', src, re.M), (
        'deep_dive_matchup_clusters.py re-declares WIN_RATING; import it from '
        'gopvpsim.battle instead')
