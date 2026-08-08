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
    # rglob, not glob: the entry-12 split put ~2900 lines of scripts/ code
    # under scripts/deep_dive_lib/, which a flat glob would stop scanning.
    for py in sorted(SCRIPTS.rglob('*.py')):
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


# ---------------------------------------------------------------------------
# Third scan surface: JS that Python EMITS.
#
# Neither scan above can see it. The JS scan globs ``scripts/*.js``, and the
# self-contained pages don't ship a .js file -- build_matchup_web.py and
# render_iv_envelope_article.py inline their whole engine as a Python string
# template. The Python scan tokenizes, so string literals are structurally
# excluded by design. So the ~5 emitted win checks in those templates sat in
# the one blind spot between the two guards, which is exactly where this
# boundary has drifted before (a .js file, three times).
#
# The emitted content is a whole HTML document (HTML + CSS + JS), NOT pure JS,
# so ``strip_js`` cannot be reused on it: run over that blob it inverts -- one
# unbalanced apostrophe in prose flips its string state and it keeps ~23% of
# the characters, precisely the JS *string contents*, blanking the code. What
# survives contact with mixed HTML/CSS/JS is a comment-only strip, which is
# all this scan needs: comments are where the documented false positive lives
# (prose discussing ">= 500"), and comment delimiters are unambiguous.
#
# Two accepted limitations, both fail-loud rather than fail-silent:
#   * prose in a non-comment string ("scores >= 500 were counted") flags; the
#     scan runs over ALL scripts/**/*.py string literals, not just the two
#     emitters, so a docstring or a log message can hit it. The only such
#     sites today are the two that describe the documented cohort-MEAN gate,
#     carried in _EMITTED_ALLOWED below on the same "name the left-hand
#     operand" principle as _ALLOWED_GE.
#   * a ``//`` inside a quoted string (a URL) blanks the rest of THAT line, so
#     a second win check later on the same line would be missed.
# ---------------------------------------------------------------------------

# Prose/log strings that describe the one allow-listed ``>=``: the cohort-MEAN
# break-even gate in synthesize_mirror_tier (a float mean where exact-500 is
# measure-zero -- a deliberately different "wins on average" semantic). Matched
# against the flagged line PLUS the line before it, because both sites wrap the
# phrase across the ``>=``.
_EMITTED_ALLOWED = ('cohort mean',)

# Same idiom as _JS_GE_RE plus the interpolated forms, since emitted JS can
# inject the constant: ``>= {WIN_RATING}`` / ``>= {win_threshold}``.
_EMITTED_GE_RE = re.compile(
    r'>=\s*(?:500(?![0-9.])|\{?\s*(?:WIN_RATING|win_threshold)\b)')


def strip_embedded_comments(text):
    """Blank ``//`` , ``/* */`` and ``<!-- -->`` comments, preserving length.

    Deliberately does NOT track string or regex literals -- see the block
    comment above for why a full JS scanner is the wrong tool for an emitted
    HTML document.
    """
    out = list(text)
    i, n = 0, len(text)

    def blank(a, b):
        for k in range(a, b):
            if out[k] != '\n':
                out[k] = ' '

    while i < n:
        if text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
        elif text.startswith('<!--', i):
            j = text.find('-->', i + 4)
            j = n if j < 0 else j + 3
        else:
            i += 1
            continue
        blank(i, j)
        i = j
    return ''.join(out)


def _string_literal_regions(path):
    """Absolute (start, end) offsets of every Python string literal's CONTENT.

    Plain/byte/raw strings contribute the text between their quotes. An
    f-string contributes its whole interior INCLUDING the ``{...}`` fields, so
    an emitted ``>= {WIN_RATING}`` is visible as text (the tokenizer hands the
    replacement field back as real Python tokens, which puts a ``{`` rather
    than the ``>=`` before the name and so slips past the tokenize scan).
    """
    text = path.read_text()
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))

    def offset(rowcol):
        row, col = rowcol
        return starts[row - 1] + col

    regions = []
    depth = 0
    fstring_open = None
    with open(path, 'rb') as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type == tokenize.FSTRING_START:
                if depth == 0:                   # outermost only; f-strings nest
                    fstring_open = offset(tok.end)
                depth += 1
            elif tok.type == tokenize.FSTRING_END:
                depth -= 1
                if depth == 0 and fstring_open is not None:
                    regions.append((fstring_open, offset(tok.start)))
                    fstring_open = None
            elif tok.type == tokenize.STRING and depth == 0:
                start, end = offset(tok.start), offset(tok.end)
                literal = text[start:end]
                k = 0
                while k < len(literal) and literal[k] not in '\'"':
                    k += 1               # skip the r/b/u prefix
                quote = literal[k]
                width = 3 if literal[k:k + 3] == quote * 3 else 1
                regions.append((start + k + width, end - width))
    return text, regions


def emitted_offenders(path):
    """``>= 500`` sites inside Python string literals, as report lines."""
    text, regions = _string_literal_regions(path)
    masked = [('\n' if ch == '\n' else ' ') for ch in text]
    for start, end in regions:
        if end <= start:
            continue
        masked[start:end] = list(strip_embedded_comments(text[start:end]))
    raw = text.splitlines()
    offenders = []
    for i, line in enumerate(''.join(masked).splitlines()):
        if not _EMITTED_GE_RE.search(line):
            continue
        window = (raw[i - 1] if i else '') + ' ' + raw[i]
        if any(a in window for a in _EMITTED_ALLOWED):
            continue
        offenders.append(f'{path.name}:{i + 1}: {raw[i].strip()}')
    return offenders


def test_emitted_scan_finds_code_but_not_comments(tmp_path):
    """The emitted scanner itself, so a stripper bug can't neuter the scan."""
    src = (
        'HEAD = "<style>a{color:red}</style>"\n'                # 1
        'PAGE = """\n'                                          # 2
        'if (s >= 500) win();\n'                                # 3: offender
        '// historical: s >= 500 was wrong\n'                   # 4: comment
        '/* block\n'                                            # 5
        '   s >= 500 inside\n'                                  # 6
        '*/\n'                                                  # 7
        '<!-- html comment: s >= 500 -->\n'                     # 8
        'if (s >= 5000) huge();\n'                              # 9: not 500
        '"""\n'                                                 # 10
        'x = s >= 500  # real python, not a string\n'           # 11
    )
    path = tmp_path / 'emitter.py'
    path.write_text(src)
    assert [o.split(':')[1] for o in emitted_offenders(path)] == ['3']


def test_emitted_scan_sees_fstring_interpolated_boundary(tmp_path):
    """``f"... >= {WIN_RATING} ..."`` is the form the tokenize scan misses."""
    path = tmp_path / 'emitter_f.py'
    path.write_text('W = 500\nPAGE = f"if (s >= {W}) win();"\n'
                    'P2 = f"if (s >= {WIN_RATING}) win();"\n')
    assert [o.split(':')[1] for o in emitted_offenders(path)] == ['3']


def test_no_ge_against_win_boundary_in_emitted_js():
    """No ``>= 500`` in JS/HTML that scripts/ emits as a Python string.

    Scans every ``scripts/**/*.py``, not just today's two emitters, so a new
    page generator is covered the day it lands.
    """
    offenders = []
    for py in sorted(SCRIPTS.rglob('*.py')):
        offenders.extend(emitted_offenders(py))
    assert not offenders, (
        'win boundary drifted back to ">=" in EMITTED JS (500 must be a TIE '
        '-> use "> 500"):\n  ' + '\n  '.join(offenders))


def test_emitters_are_actually_covered_by_the_emitted_scan():
    """Guard the guard: the two known emitters must really carry win checks
    inside string literals, or the scan above is vacuous.

    If this fails because a page stopped inlining its engine, delete the entry
    -- do not delete the scan.
    """
    known = ('build_matchup_web.py', 'render_iv_envelope_article.py')
    probe = re.compile(r'[<>]\s*(?:500(?![0-9.])|\{?\s*WIN_RATING\b)')
    for name in known:
        path = SCRIPTS / name
        text, regions = _string_literal_regions(path)
        found = any(probe.search(text[a:b]) for a, b in regions if b > a)
        assert found, (
            f'{name} no longer has a win check inside a string literal; the '
            f'emitted-JS scan may be scanning nothing')


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
