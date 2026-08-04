"""Resolved-chain-failure records in scripts/verify_overnight.py check [1/5].

A chain step can fail for a reason that is diagnosed and already fixed, but
the chain log and overnight_status.txt are immutable history -- so the gate
re-reports the dead failure forever. docs/chain_resolutions.toml records the
resolution instead of doctoring those files. These tests pin the two
properties that keep it from degrading into a blanket suppressor: an entry
only matches the ONE log it names, and the shipped entry actually matches
the failure it claims to resolve.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_overnight as vo  # noqa: E402

FAIL_LINE = (
    "2026-07-07 17:01:37 [FAIL] Running article link verification (rc=1, 94s)"
)
RESOLUTIONS = [
    {
        "chain_log": "overnight_20260706_204813.log",
        "step": "Running article link verification",
        "fix_commit": "73747e6",
        "reason": "guides tree absent on a fresh laptop",
        "verified": "re-run clean 2026-08-04",
    }
]


def test_matches_the_log_it_names():
    res = vo.match_resolution(
        RESOLUTIONS, "overnight_20260706_204813.log", FAIL_LINE)
    assert res is not None
    assert res["fix_commit"] == "73747e6"


def test_does_not_match_a_later_chain_log():
    """The expiry property: a fresh chain writes a new filename, so no
    existing entry can suppress a future failure of the same step."""
    assert vo.match_resolution(
        RESOLUTIONS, "overnight_20260901_010101.log", FAIL_LINE) is None


def test_does_not_match_a_different_step_in_the_same_log():
    other = "2026-07-07 03:00:00 [FAIL] Rebuilding website index (rc=1, 4s)"
    assert vo.match_resolution(
        RESOLUTIONS, "overnight_20260706_204813.log", other) is None


def test_shipped_file_parses_and_carries_evidence():
    for res in vo.load_resolutions():
        assert res["chain_log"] and res["step"]
        # A resolution without a fix and an independent re-run is an excuse,
        # not a resolution -- the gate prints both, so both must be present.
        assert res["fix_commit"], f"{res['chain_log']}: no fix_commit"
        assert res["verified"], f"{res['chain_log']}: no re-verification"


def test_shipped_entries_match_their_own_fail_line():
    """Guards against a typo'd step label shipping as a live suppression
    rule. main() reports that case as a stale resolution; this catches it
    at test time for the entry whose log is still on disk."""
    for res in vo.load_resolutions():
        log = next(vo.LOGS.glob(f"*/{res['chain_log']}"), None)
        if log is None:
            continue  # log aged out of userdata/; entry is spent history
        fails = [ln for ln in log.read_text().splitlines() if "[FAIL]" in ln]
        assert any(res["step"] in ln for ln in fails), (
            f"{res['chain_log']}: step {res['step']!r} matches no [FAIL] line")
