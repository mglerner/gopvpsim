"""The localStorage theme key is defined once and used everywhere.

The pre-paint head script and the picker's read/write handlers must agree on
the storage key -- if they drift, a visitor's stored choice is written under
one name and read under another, and the picker silently stops persisting.
Sourcing all three from ``_THEME_KEY`` makes that drift impossible; this test
is the tripwire that keeps a future edit from re-introducing a bare literal.
"""

import re
from pathlib import Path

from gopvpsim import theme

THEME_SRC = Path(theme.__file__).read_text()


def _storage_call(op):
    """``localStorage.<op>('pogo-theme'`` as a whitespace/quote-tolerant regex.

    The guarded content is "the key literal reaches this handler", not the
    emitted JS's spacing or quote style -- pinning
    ``setItem('pogo-theme',this.value)`` as an exact string made a
    one-character reformat of the emitter a test failure (2026-08-09 test
    suite review, fragility lens).
    """
    return re.compile(r"localStorage\.%s\(\s*['\"]%s['\"]\s*[,)]"
                      % (op, re.escape(theme._THEME_KEY)))


def test_key_constant_is_the_shipped_key():
    assert theme._THEME_KEY == "pogo-theme"


def test_head_script_and_picker_use_the_constant():
    head = theme.theme_head_script()
    picker = theme.theme_picker_html()

    assert _storage_call("getItem").search(head), head
    assert _storage_call("setItem").search(picker), picker
    assert _storage_call("getItem").search(picker), picker


def test_no_bare_key_literal_outside_the_constant():
    """The raw key is spelled EXACTLY once, and that once is the constant.

    Matched as a pattern rather than as one exact line, so a quote-style or
    spacing change on the definition is not a drift -- but the two properties
    that make this a guard are both kept: the definition pattern is anchored at
    column 0 (an indented re-definition or a bare ``return "pogo-theme"`` inside
    a handler is stray), and the count is pinned at one (a second copy of the
    definition is a drift waiting to happen, even while the values agree).
    """
    key = theme._THEME_KEY
    hits = [
        line
        for line in THEME_SRC.splitlines()
        if key in line and not re.match(r"\s*#", line)
    ]
    definition = re.compile(r"""^_THEME_KEY\s*=\s*['"]%s['"]\s*(#.*)?$"""
                            % re.escape(key))
    stray = [line for line in hits if not definition.match(line)]
    assert not stray, stray
    # Anti-vacuity + define-once: a renamed constant leaves nothing to check,
    # and a second definition is the drift this whole file exists to prevent.
    assert len(hits) == 1, f"expected exactly one {key!r} line, got {hits}"
