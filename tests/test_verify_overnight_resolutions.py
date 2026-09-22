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


def test_shipped_entries_match_a_line_their_gate_reports():
    """Guards against a typo'd step label shipping as a live suppression
    rule. main() reports that case as a stale resolution; this catches it
    at test time for the entry whose log is still on disk.

    Checked against every line check [1/5] reports, not the [FAIL] lines
    alone: since 2026-09-22 the two WARN scans go through report() too, and
    the first entry to use that (the which-one-to-build omission on
    overnight_20260920_164044.log) matches a WARNING line, not a [FAIL] one.
    Pre-fix this test read only ``"[FAIL]" in ln`` and failed on it.
    """
    for res in vo.load_resolutions():
        log = next(vo.LOGS.glob(f"*/{res['chain_log']}"), None)
        if log is None:
            continue  # log aged out of userdata/; entry is spent history
        text = log.read_text()
        reported = ([ln for ln in text.splitlines() if "[FAIL]" in ln]
                    + vo.scan_narrative_warnings(text)
                    + vo.scan_which_build_omissions(text))
        assert reported, f"{res['chain_log']}: nothing reported to match"
        assert vo.stale_resolutions([res], res["chain_log"], reported) == [], (
            f"{res['chain_log']}: step {res['step']!r} matches no line the "
            f"gate reports")


# ---------------------------------------------------------------------------
# What a resolution may cover, and when it is stale
# ---------------------------------------------------------------------------
# 2026-09-22. The gate's [1/5] step reports three kinds of line -- the status
# line, [FAIL] step lines, and the two WARN scans (narrative patch,
# which-one-to-build omission) -- but only the first two could ever be
# resolved: the scans appended straight to `errors`. A dive whose missing
# section was diagnosed, fixed and RE-RENDERED by hand therefore kept the
# gate red forever, with the only ways out being to doctor the chain log or
# to wave the whole gate off. Both are what this file exists to prevent.

WB_LINE = (
    "which-one-to-build section missing: [22:22:41] WARNING:   Which one to "
    "build?: omitted (GuardError: G-recompute: field=Floor merge cell=2v2 "
    "Ninetales (Alolan) ...)"
)


def test_a_which_build_omission_can_be_resolved():
    """The line the scan produces must be matchable by a resolution entry."""
    res = [{"chain_log": "overnight_20260920_164044.log",
            "step": "Which one to build?: omitted",
            "fix_commit": "abc1234", "reason": "r", "verified": "v"}]
    assert vo.match_resolution(
        res, "overnight_20260920_164044.log", WB_LINE) is not None
    # and only for the log it names
    assert vo.match_resolution(
        res, "overnight_20260921_000000.log", WB_LINE) is None


def test_stale_resolutions_looks_at_every_line_the_step_reports():
    """Pre-fix the staleness test only saw the [FAIL] lines (it keyed on the
    ids `report()` had collected, and the two WARN scans ran AFTER it), so an
    entry covering a which-build omission was reported as stale -- red either
    way."""
    res = [{"chain_log": "overnight_20260920_164044.log",
            "step": "Which one to build?: omitted",
            "fix_commit": "abc1234", "reason": "r", "verified": "v"}]
    log = "overnight_20260920_164044.log"
    assert vo.stale_resolutions(res, log, [FAIL_LINE, WB_LINE]) == []
    # Nothing it names is in this chain's output: that IS stale.
    stale = vo.stale_resolutions(res, log, [FAIL_LINE])
    assert len(stale) == 1 and 'Which one to build?' in stale[0]
    # An entry for another log is spent, not stale.
    assert vo.stale_resolutions(res, "overnight_20260921_000000.log", []) == []
