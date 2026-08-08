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


def test_key_constant_is_the_shipped_key():
    assert theme._THEME_KEY == "pogo-theme"


def test_head_script_and_picker_use_the_constant():
    key = theme._THEME_KEY
    head = theme.theme_head_script()
    picker = theme.theme_picker_html()

    assert f"localStorage.getItem('{key}')" in head
    assert f"localStorage.setItem('{key}',this.value)" in picker
    assert f"localStorage.getItem('{key}')" in picker


def test_no_bare_key_literal_outside_the_constant():
    """Every occurrence of the raw key is the constant's own definition."""
    hits = [
        line
        for line in THEME_SRC.splitlines()
        if "pogo-theme" in line and not re.match(r"\s*#", line)
    ]
    assert hits == ['_THEME_KEY = "pogo-theme"'], hits
