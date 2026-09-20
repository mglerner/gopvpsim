"""Every DIVE_OVERRIDES key must name a dive the registry actually emits.

DIVE_OVERRIDES is keyed by SLUG, and the slugs are DERIVED from the opponent
pools.  So a pool regeneration that drops a species, or a slug-rule change,
silently strips that dive's editorial content -- the moveset pin, the
reference line, the strategy policy, the hand-authored thresholds -- with no
error anywhere.  The bake runs, the page renders, and it renders with the
wrong moveset.

Pre-fix value: three orphan keys were live on 2026-09-20 --
``dewgong-great-league`` (Dewgong left the GL pool) and
``mimikyu-busted-{great,ultra}-league`` (the two Busted pages were dropped in
the 2026-09-10 pool-derived rewrite, but their pins were copied into the
table by the equivalence gate and never removed).  Nothing reported them.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import dive_registry as reg  # noqa: E402


def test_no_orphan_override_keys():
    slugs = {d["slug"] for d in reg.all_dives()}
    orphans = sorted(k for k in reg.DIVE_OVERRIDES if k not in slugs)
    assert orphans == [], (
        f"DIVE_OVERRIDES keys naming no dive: {orphans}. Their editorial "
        f"content (pins, reference, policy, thresholds) is silently dropped."
    )


def test_checker_raises_on_an_orphan():
    """The preflight itself, driven with a synthetic table so the test does
    not depend on today's pool."""
    dives = [{"slug": "melmetal-great-league"}]
    with pytest.raises(ValueError) as exc:
        reg.check_override_keys(dives, overrides={"no-such-dive": {}})
    assert "no-such-dive" in str(exc.value)


def test_checker_accepts_a_matching_key():
    """Positive control: a key that DOES name a dive must not raise, so the
    checker cannot pass the test above by rejecting everything."""
    dives = [{"slug": "melmetal-great-league"}]
    reg.check_override_keys(
        dives, overrides={"melmetal-great-league": {"policy": "both"}})


def test_run_website_dives_calls_the_preflight():
    """The guard is worthless unless the bake entry point runs it.  Pin the
    call site the way check_cup_slugs is pinned -- a source scan, because
    calling main() would launch 136 dives."""
    src = (REPO_ROOT / "scripts" / "run_website_dives.py").read_text()
    assert "check_override_keys(" in src
