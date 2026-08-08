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
import inspect
import json
import re
from pathlib import Path

from gopvpsim.pokemon import (
    LEAGUE_CAPS, LEAGUE_MAX_LEVEL, MAX_CPM_LEVEL,
    SHADOW_ATK_BONUS, SHADOW_DEF_MULT,
)
from gopvpsim.user_collection import ivs_to_stats_at_cap

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


def _js_table(name: str) -> dict:
    """Parse the object literal assigned to `var <name>` in the JS file."""
    m = re.search(rf"var\s+{name}\s*=\s*(\{{[^}}]*\}});", _JS.read_text())
    assert m, f"{name} not found as a `var` object literal in {_JS.name}"
    # Bare JS identifier keys -> JSON keys, then parse (no eval needed).
    as_json = re.sub(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", r'"\1":', m.group(1))
    return json.loads(as_json)


def test_js_league_caps_fallback_matches_python():
    """Same shape, same hazard: the league CP caps.

    ``matchMons`` takes ``opts.leagueCaps`` (production injects the Python
    dict) and falls back to a module-level table that nothing in
    production reads -- the exact condition under which SHADOW_DEF_MULT rotted.
    Pin it to ``pokemon.LEAGUE_CAPS`` so a cap change cannot leave a wrong
    fallback behind.

    (DRY review 2026-08-05 entry 9 hoisted this literal out of ``matchMons``
    so ``CAP_TO_LEAGUE`` could be derived from it instead of hand-typed; the
    second assertion keeps ``matchMons`` wired to the hoisted table.)

    The 'little' row entry 13 (L6) gave Python is now in the JS too, so this
    is plain whole-table equality. It used to be a pinned GAP ("every league
    the JS carries must match, and little must be the only one it lacks"),
    which is a strictly weaker guard: an exception clause in a rot tripwire
    is the thing that lets a second missing row look like the first. No
    little dive is baked, so the row is inert -- ``matchMons`` looks the
    league up rather than iterating -- but it costs nothing and it lets the
    assertion be stated without a carve-out.
    """
    js_caps = _js_table("LEAGUE_CAPS")
    assert js_caps == LEAGUE_CAPS
    assert re.search(r"opts\.leagueCaps\s*\|\|\s*LEAGUE_CAPS", _JS.read_text()), (
        f"matchMons no longer falls back to the LEAGUE_CAPS table in {_JS.name}"
    )


def test_js_league_max_level_fallback_matches_python():
    """Third instance of the same hazard, and the one that already bit:
    the per-league power-up ceiling (DRY review 2026-08-05 entry 9).

    ``matchMons``/``ivsToStatsAtCap`` derive their default ``maxLevel``
    from these tables when the caller passes none. A league-blind 51.0 is
    the "GL/UL owned mons one level too high" bug -- best buddy is +1 level
    and only one mon can hold it, so GL/UL cap at 50.
    """
    assert _js_table("LEAGUE_MAX_LEVEL") == LEAGUE_MAX_LEVEL


def test_js_max_cpm_level_matches_python():
    """The unknown-league / unknown-cap fallback is the CPM table ceiling."""
    assert _js_const("MAX_CPM_LEVEL") == MAX_CPM_LEVEL


def test_js_ivs_to_stats_at_cap_default_cap_matches_python():
    """``ivsToStatsAtCap``'s no-``maxCp`` default must be Python's default.

    Same hazard one level down, and the one place the caps table is READ as a
    default rather than injected: ``ivs_to_stats_at_cap(max_cp=1500)`` in
    Python, ``opts.maxCp != null ? opts.maxCp : LEAGUE_CAPS.great`` in the JS.
    Nothing in production exercises the JS branch, so a Python default change
    (or someone re-typing 1500 into the JS) would drift unnoticed -- and a
    wrong CP cap silently returns stats for the wrong level.

    Pinned via the SPELLING (must go through the table, not a literal) plus
    the VALUE (that table entry must equal Python's declared default).
    """
    default_cap = inspect.signature(ivs_to_stats_at_cap).parameters["max_cp"].default
    assert default_cap == LEAGUE_CAPS["great"], (
        "user_collection.ivs_to_stats_at_cap's default max_cp is no longer the "
        "great-league cap; the JS fallback LEAGUE_CAPS.great now disagrees"
    )
    assert re.search(
        r"opts\.maxCp\s*!=\s*null\)\s*\?\s*opts\.maxCp\s*:\s*LEAGUE_CAPS\.great",
        _JS.read_text()), (
        f"ivsToStatsAtCap in {_JS.name} no longer defaults maxCp to "
        f"LEAGUE_CAPS.great (a re-typed literal is how the table gets bypassed)"
    )


def test_js_cap_to_league_reverse_covers_every_league():
    """``maxLevelForCap`` derives its ceiling from CAP_TO_LEAGUE, so the
    reverse map has to be total -- which it is only if the caps are distinct.

    Mirrors ``user_collection._CAP_TO_LEAGUE``. This is what the new 'little'
    row buys concretely: ``maxLevelForCap(500)`` now resolves through
    little -> 51.0 instead of falling through to the MAX_CPM_LEVEL default.
    """
    js_caps = _js_table("LEAGUE_CAPS")
    assert len(set(js_caps.values())) == len(js_caps), "cap collision"
    assert set(js_caps.values()) == set(LEAGUE_CAPS.values())
