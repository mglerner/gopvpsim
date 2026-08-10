"""The overnight verifier's cup-dive glob must key on data.cup_slug_suffix.

``data.cup_slug_suffix``'s docstring promises that the slug PRODUCER
(run_website_dives), the index ROUTER (build_website_index) and "the overnight
verifier's glob" all key on one spelling of ``<cup>-cup``. The verifier used to
re-spell the literal ``'*-cup'`` instead, so a suffix change would have moved
two of the three consumers and silently left the freshness check globbing for
directories that no longer exist -- a check that finds nothing reports green.

These tests pin the derivation and, more importantly, the BEHAVIOUR: the glob
still matches a real cup dive slug (including a multi-word species) and still
does not match a league dive.

The absence half used to be two exact substrings (``"glob('*-cup')"`` /
``'glob("*-cup")'``). A 2026-08-09 fragility probe re-introduced the
antipattern as ``root.glob('*-' 'cup')`` and both pins stayed green, so the
scan is now AST-based -- Python folds implicit concatenation, quote style and
interior whitespace away before we look at the constant -- and it is paired
with a positive control (the helper must still be CALLED here) plus a
scanner self-test, per the house rule for absence assertions over source.
"""
import ast
import fnmatch
import re
import sys
from pathlib import Path

from gopvpsim.data import cup_slug_suffix

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_overnight as vo  # noqa: E402

_VO_SRC = REPO_ROOT / "scripts" / "verify_overnight.py"

_RESPELLS_CUP = re.compile(r"-\s*cup", re.I)


def _static_str(node):
    """The literal text of ``node``, or None if it isn't statically known.

    Folds implicit concatenation (free -- the parser does it), an f-string
    with no interpolation (``ast.JoinedStr``, NOT ``ast.Constant`` -- the
    single likeliest regression here is deleting the interpolation out of
    ``f'*-{cup_slug_suffix("*")}'`` and leaving the ``f``), and ``'a' +
    'b'``. An interpolated chunk becomes ``\\x00``, so the LIVE derivation
    folds to ``*-\\x00`` and cannot false-positive.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "\x00"
                       for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _static_str(node.left), _static_str(node.right)
        return None if left is None or right is None else left + right
    return None


def _constant_glob_args(source):
    """Every statically-known ``glob``/``rglob`` argument in ``source``.

    Returns ``(respelled, seen)``: the literals that spell the ``-cup``
    suffix out by hand, and how many static glob arguments the scan saw
    at all (the anti-vacuity denominator -- a scan that stops finding any
    glob call would otherwise report "no violations" forever).
    """
    respelled, seen = [], 0
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in ("glob", "rglob"):
            continue
        for arg in node.args:
            text = _static_str(arg)
            if text is not None:
                seen += 1
                if _RESPELLS_CUP.search(text):
                    respelled.append(text)
    return respelled, seen


def test_cup_glob_is_derived_from_the_helper():
    """Not a re-spelled literal: change the helper, the glob follows."""
    assert cup_slug_suffix("*") in vo.CUP_DIR_GLOB
    assert vo.CUP_DIR_GLOB == f'*-{cup_slug_suffix("*")}'


def test_no_glob_call_respells_the_cup_suffix():
    """The literal the helper exists to delete must not come back -- in ANY
    spelling, including implicit concatenation and double quotes."""
    respelled, seen = _constant_glob_args(_VO_SRC.read_text())
    assert not respelled, respelled
    # Anti-vacuity floor, deliberately BELOW today's count (2 today:
    # '*-league' and 'index*.html'). Neither has anything to do with cup
    # slugs, and routing the index enumeration through ship_surfaces --
    # which test_ship_surfaces.py exists to encourage -- would legitimately
    # drop it to 1. The scanner self-test below is the real guard.
    assert seen >= 1, "scan found no glob args at all -- stale scanner?"


def test_the_respelling_scanner_actually_catches_the_antipattern():
    """Guard the guard. The first two spellings are what the old substring
    pins caught; the last three are the ones a 2026-08-09 probe slipped
    past them."""
    for snippet in ("root.glob('*-cup')",
                    'root.glob("*-cup")',
                    "root.glob('*-' 'cup')",
                    "root.rglob( '*-cup' )",
                    'root.rglob("*-CUP")',
                    # ...and the escapes an adversarial pass found on
                    # 2026-08-09: an inert `f` prefix (the likeliest
                    # regression) and a `+` join.
                    "root.glob(f'*-cup')",
                    "root.glob('*-' + 'cup')"):
        respelled, seen = _constant_glob_args(snippet)
        assert respelled, snippet
        assert seen == 1, snippet
    # ...and does not fire on the globs that legitimately live here.
    assert not _constant_glob_args("d.glob('index*.html')\nw.glob('*-league')")[0]
    # ...nor on the LIVE derivation, whose interpolated chunk is opaque.
    assert not _constant_glob_args("root.glob(f'*-{cup_slug_suffix(\"*\")}')")[0]


def test_the_helper_is_still_the_thing_being_called():
    """Positive control for the absence scan above: an absence assertion is
    satisfied for free by 'nobody globs for cup dives at all', so pin that
    the canonical replacement is still here."""
    calls = [n for n in ast.walk(ast.parse(_VO_SRC.read_text()))
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "cup_slug_suffix"]
    assert calls, "verify_overnight stopped deriving the cup suffix from the helper"
    assert vo.cup_slug_suffix is cup_slug_suffix


def test_cup_glob_matches_real_cup_slugs():
    """Slugs built the way run_website_dives builds them."""
    for species in ("clodsire", "galarian-corsola", "shadow-alolan-ninetales"):
        for cup in ("equinox", "love"):
            slug = f"{species}-{cup_slug_suffix(cup)}"
            assert fnmatch.fnmatch(slug, vo.CUP_DIR_GLOB), slug


def test_cup_glob_does_not_match_league_dives():
    """League dirs come in via the separate '*-league' glob; no double-count."""
    for slug in ("azumarill-great-league", "galarian-corsola-ultra-league",
                 "articles", "comparisons", "guides"):
        assert not fnmatch.fnmatch(slug, vo.CUP_DIR_GLOB), slug
