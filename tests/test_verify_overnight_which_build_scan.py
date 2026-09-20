"""Which-one-to-build omission scan in scripts/verify_overnight.py.

deep_dive._which_build_sections wraps the whole "Which one to build?" render
in a bare ``except Exception`` and degrades to a single
``WARNING:   Which one to build?: omitted (<Error>: <detail>)`` log line
(the three honest no-ops its docstring lists, plus any bug).  The dive itself
still exits 0, the page still renders, and the chain still prints SUCCESS --
so the flagship section can vanish from an arbitrary number of pages in a
multi-hour bake with nothing red anywhere.

That is the same silent-incompleteness shape as the narrative-patch WARN and
the ML best-effort tail, and it gets the same treatment: the morning gate
scans the teed chain log and turns each omission into an error (rc=1).

Pre-fix value: scan_which_build_omissions did not exist, so a bake that
omitted the section on every page passed the gate GREEN.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_overnight as vo  # noqa: E402


def test_omission_lands_in_errors():
    log = (
        "[STEP] dive oinkologne-female-great-league\n"
        "[09:38:07] WARNING:   Which one to build?: omitted "
        "(KeyError: 'def_cut')\n"
        "[DONE] dive oinkologne-female-great-league (450s)\n"
    )
    errors = vo.scan_which_build_omissions(log)
    assert len(errors) == 1
    assert "def_cut" in errors[0]


def test_skipped_no_blob_is_also_scanned():
    """The --no-replay-dump path logs 'skipped', not 'omitted', and is an
    equally invisible way for the section to be absent from the shipped
    page.  Both spellings must be caught."""
    log = (
        "  Which one to build?: skipped (no replay blob path on this "
        "render; the brief is computed from the blob)\n"
    )
    errors = vo.scan_which_build_omissions(log)
    assert len(errors) == 1


def test_clean_log_is_clean():
    """Positive control: a log with the section rendering normally, and with
    the neighbouring scans' own trigger lines present, must produce zero
    errors -- otherwise this scan would be matching on something generic."""
    log = (
        "[STEP] dive melmetal-great-league\n"
        "  Which one to build?: 5 moveset(s) in 41.2s\n"
        "  [WARN] narrative patch failed for melmetal_great (rc=1)\n"
        "[DONE] dive melmetal-great-league (500s)\n"
    )
    assert vo.scan_which_build_omissions(log) == []


def test_scanner_matches_the_literal_the_renderer_emits():
    """Self-test on the producing source: the substrings this scan keys on
    must still be the ones deep_dive.py writes.  A reworded log line would
    silently disarm the gate, which is exactly the failure this file exists
    to prevent."""
    src = (REPO_ROOT / "scripts" / "deep_dive.py").read_text()
    assert 'Which one to build?: omitted' in src
    assert 'Which one to build?: skipped' in src
