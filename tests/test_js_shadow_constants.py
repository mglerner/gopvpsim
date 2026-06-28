"""Parity tripwire: the JS engine's shadow-constant fallbacks must equal the
Python canonical constants.

Production injects the Python values into the JS (deep_dive.py ->
DATA.collection.shadow* -> setConstants), so the hardcoded ``var`` defaults in
``deep_dive_user_collection.js`` are fallbacks that production always overrides.
That is precisely why one of them silently rotted: ``SHADOW_DEF_MULT`` sat at the
wrong ``5/6`` until 2026-06-27 because nothing in production ever read the
default. This test makes that class of drift impossible to reintroduce.

See DEVELOPER_NOTES "Engine constant sourcing".
"""
import re
from pathlib import Path

from gopvpsim.pokemon import SHADOW_ATK_BONUS, SHADOW_DEF_MULT

_JS = Path(__file__).resolve().parents[1] / "scripts" / "deep_dive_user_collection.js"


def _js_const(name: str) -> float:
    """Eval the numeric literal/expression assigned to `var <name>` in the JS file."""
    text = _JS.read_text()
    m = re.search(rf"var\s+{name}\s*=\s*([^;]+);", text)
    assert m, f"{name} not found as a `var` in {_JS.name}"
    # The captured group is a trusted numeric expression (e.g. "6 / 5" or a float
    # literal); eval with no builtins so only arithmetic on the literal runs.
    return eval(m.group(1), {"__builtins__": {}})  # noqa: S307


def test_js_shadow_atk_matches_python():
    assert _js_const("SHADOW_ATK_BONUS") == SHADOW_ATK_BONUS


def test_js_shadow_def_matches_python():
    assert _js_const("SHADOW_DEF_MULT") == SHADOW_DEF_MULT
