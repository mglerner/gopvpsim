"""Regression guard for the card attack/bulk pole strict-dominance tie-break
(deep_dive.py generate_analysis_sections, fix 810f53c).

The bug (UL Mimikyu card, 2026-06-24): a below-cap species ties `0/15/15` and
`1/15/15` on def+hp at max level, and the pole-selection keys maxed on
``(coverage, def, hp)`` / ``(coverage, hp, def)`` with NO attack tie-break, so
``max()`` returned the FIRST maximal index -- the lower-atk, strictly-dominated
spread -- as the headline. The fix adds ``ivAtk`` as the final tie-break key.

Why a dedicated test: the two poles are seeded UNCONDITIONALLY and are EXEMPT
from the ``_eff_mask`` (efficiency.efficient_frontier) strict-dominance filter
applied to the greedy-fill spreads. So the existing efficient-frontier tests do
NOT cover them -- the atk tie-break in the selection key is their ONLY guard.

Two parts:
  * behavioral -- on a synthetic below-cap layout, prove via the real
    ``efficient_frontier`` that the lower-atk spread is strictly dominated, then
    show the shipped tie-break key selects the frontier member while the
    pre-810f53c key selects the dominated one.
  * source tripwire -- assert the shipped pole-selection keys still carry
    ``data_obj['ivAtk'][iv]`` as the final tie-break element (the part that the
    behavioral test mirrors), so removing it can't silently regress. Pattern
    borrowed from tests/test_js_shadow_constants.py.
"""
import re
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from gopvpsim.efficiency import efficient_frontier  # noqa: E402

_DEEP_DIVE = REPO_ROOT / "scripts" / "deep_dive.py"

# Synthetic below-cap layout mirroring the UL Mimikyu repro: index 0 is
# `0/15/15` (lower atk), index 1 is `1/15/15` (same def + hp, higher atk), so 1
# weakly-dominates 0. Both clear the SAME breakpoint/bulkpoint coverage -> a
# pure def+hp / hp+def tie that only the atk tie-break can resolve.
IV_ATK = [148.7, 149.6]
IV_DEF = [179.8, 179.8]
IV_HP = [135, 135]
COVER = [1, 1]  # equal notable-tier coverage for both poles


def test_synthetic_lower_atk_spread_is_strictly_dominated():
    """The premise: with equal def+hp, the lower-atk spread is NOT on the
    efficient frontier (real efficient_frontier), so headlining it is a bug."""
    eff = efficient_frontier(list(zip(IV_ATK, IV_DEF, IV_HP)))
    assert eff == [False, True]


def test_attack_pole_tiebreak_picks_frontier_member():
    """Shipped attack-pole key (coverage, def, hp, atk) selects the efficient
    `1/15/15`; the pre-810f53c key (coverage, def, hp) returns the dominated
    `0/15/15` -- the bug. Confirms the atk tie-break is load-bearing."""
    eff = efficient_frontier(list(zip(IV_ATK, IV_DEF, IV_HP)))
    fixed = max(range(2), key=lambda iv: (COVER[iv], IV_DEF[iv], IV_HP[iv],
                                          IV_ATK[iv]))
    buggy = max(range(2), key=lambda iv: (COVER[iv], IV_DEF[iv], IV_HP[iv]))
    assert fixed == 1 and eff[fixed]          # pole is on the frontier
    assert buggy == 0 and not eff[buggy]      # pre-fix headlined the dominated one


def test_bulk_pole_tiebreak_picks_frontier_member():
    """Shipped bulk-pole key (coverage, hp, def, atk) selects the efficient
    `1/15/15`; the pre-810f53c key (coverage, hp, def) returns dominated
    `0/15/15`."""
    eff = efficient_frontier(list(zip(IV_ATK, IV_DEF, IV_HP)))
    fixed = max(range(2), key=lambda iv: (COVER[iv], IV_HP[iv], IV_DEF[iv],
                                          IV_ATK[iv]))
    buggy = max(range(2), key=lambda iv: (COVER[iv], IV_HP[iv], IV_DEF[iv]))
    assert fixed == 1 and eff[fixed]
    assert buggy == 0 and not eff[buggy]


def _pole_key_last_element(var: str) -> str:
    """Last comma-separated element of the coverage-branch `<var> = max(range(
    nIvs), key=lambda iv: (...))` tuple in deep_dive.py. The coverage branch is
    the FIRST occurrence (the raw max-atk/def else-branch comes after it)."""
    text = _DEEP_DIVE.read_text()
    m = re.search(rf"{var} = max\(range\(nIvs\),\s*key=lambda iv:\s*\((.*?)\)\)",
                  text, re.S)
    assert m, f"{var} coverage-branch selection not found in {_DEEP_DIVE.name}"
    # Elements contain no top-level commas inside their own brackets
    # (data_obj['ivAtk'][iv], _atk_cover(iv)), so a plain split is safe.
    return m.group(1).split(",")[-1].strip()


def test_source_attack_pole_keeps_atk_tiebreak():
    """Tripwire: the shipped attack-pole key must end on the ivAtk tie-break."""
    assert _pole_key_last_element("atk_iv") == "data_obj['ivAtk'][iv]"


def test_source_bulk_pole_keeps_atk_tiebreak():
    """Tripwire: the shipped bulk-pole key must end on the ivAtk tie-break."""
    assert _pole_key_last_element("bulk_iv") == "data_obj['ivAtk'][iv]"
