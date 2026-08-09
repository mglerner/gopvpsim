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


def test_no_dive_dir_warn_is_also_scanned():
    """run_website_dives also WARNs when the dive dir is missing entirely.

    That branch skips the patcher rather than running it, so it used to emit
    no line at all -- the last silent path past this gate. It reuses the same
    wording deliberately; a reworded copy would be invisible here.
    """
    log = (
        "[STEP] dive azumarill\n"
        "  [WARN] narrative patch failed for azumarill_great "
        "(no dive dir at userdata/website/azumarill_great); continuing.\n"
    )
    errors = vo.scan_narrative_warnings(log)
    assert len(errors) == 1
    assert "no dive dir" in errors[0]


def test_every_producer_warn_carries_the_scanned_substring():
    """The literal is the only contract between producer and scanner.

    scan_narrative_warnings matches on 'WARN] narrative patch failed'. If a
    producer site in run_website_dives.py is reworded, this gate goes blind
    with no other test noticing, so pin every producer line here.
    """
    src = (REPO_ROOT / "scripts" / "run_website_dives.py").read_text()
    sites = [ln for ln in src.splitlines()
             if "narrative patch failed" in ln and "print(" in ln]
    assert sites, "no narrative-patch WARN producer found"
    for ln in sites:
        assert "WARN] narrative patch failed" in ln, ln


def test_clean_log_yields_no_errors():
    log = (
        "[STEP] dive azumarill\n"
        "  Patching narrative: python patch_dive_species_narrative.py ...\n"
        "[DONE] dive azumarill (120s)\n"
    )
    assert vo.scan_narrative_warnings(log) == []
