"""Narrative auto-gen WARN scan in scripts/verify_overnight.py (todo-2 F3).

run_website_dives.py patches the species-narrative block WARN-not-FAIL, so a
failed patch only ever surfaces as a "[WARN] narrative patch failed ..." line
in the teed chain log -- neither the [FAIL] scan nor the SUCCESS status line
catches it. scan_narrative_warnings() must turn that log line into an error
(rc=1), so this gate fails loudly instead of passing GREEN.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_overnight as vo  # noqa: E402


def test_narrative_warn_lands_in_errors():
    log = (
        "[STEP] dive azumarill\n"
        "  Patching narrative: python patch_dive_species_narrative.py ...\n"
        "  [WARN] narrative patch failed for azumarill_great (rc=1); continuing.\n"
        "[DONE] dive azumarill (120s)\n"
    )
    errors = vo.scan_narrative_warnings(log)
    assert len(errors) == 1
    assert "azumarill_great" in errors[0]


def test_clean_log_yields_no_errors():
    log = (
        "[STEP] dive azumarill\n"
        "  Patching narrative: python patch_dive_species_narrative.py ...\n"
        "[DONE] dive azumarill (120s)\n"
    )
    assert vo.scan_narrative_warnings(log) == []
