"""ML IV-guide progress reporting: iv_envelope_analysis routes progress through
the structured logger (no bare print), and the two watch views surface each
running worker's current phase from its per-guide log.

These are FAST source/helper tests — they never run iv_envelope_analysis or any
battle sim (which would collide on output files and be slow). The phase-line
logic is exercised by calling the watch-view helpers directly against synthetic
per-guide / wrapper logs.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import iv_guides_status as igs  # noqa: E402
import chain_status as cs  # noqa: E402

ANALYSIS = REPO_ROOT / "scripts" / "iv_envelope_analysis.py"


def test_no_bare_print_in_iv_envelope():
    """All progress/status is routed through the structured logger."""
    src = ANALYSIS.read_text()
    assert "print(" not in src, (
        "iv_envelope_analysis.py must route progress through the logger, "
        "not bare print()")


def test_species_from_cmd_reconstructs_full_name():
    """Both watch views recover a spaced/paren'd species (and skip flags) so the
    slug -> per-guide-log mapping resolves the path the worker wrote."""
    cmd = ("/usr/bin/python scripts/iv_envelope_analysis.py --all-shields "
           "--iv-floor 10 Dialga (Origin)")
    assert igs._species_from_cmd(cmd) == "Dialga (Origin)"
    assert cs._ml_species_from_cmd(cmd) == "Dialga (Origin)"


def test_slug_matches_iv_envelope_formula():
    for slugger in (igs._slug, cs._ml_slug):
        assert slugger("Dialga (Origin)") == "dialga_origin"


_SYNTH_LOG = (
    "[2026-06-27 18:18:49.274] RESULT  deep_dive: Dialga (Origin): 3 opponents\n"
    "[2026-06-27 18:18:53.387] INFO    deep_dive: [hundo 4/4] wbb_vs_bb: 2 won (of 9)\n"
    "[2026-06-27 18:18:53.388] INFO    deep_dive: [recommended 32/64] combos\n"
)
_EXPECTED_PHASE = "[recommended 32/64] combos"


def test_iv_guides_status_worker_phase(monkeypatch, tmp_path):
    """worker_phase reads the per-guide log (cwd-relative) and strips the
    structured-logger prefix, surfacing the last phase line."""
    monkeypatch.chdir(tmp_path)
    log = tmp_path / "userdata" / "logs" / "iv_guides" / "dialga_origin.log"
    log.parent.mkdir(parents=True)
    log.write_text(_SYNTH_LOG)
    assert igs.worker_phase("Dialga (Origin)") == _EXPECTED_PHASE
    # Missing log (worker just launched) is tolerated.
    assert igs.worker_phase("Nonexistent Mon") == ""


def test_chain_status_worker_phase(monkeypatch, tmp_path):
    """_ml_worker_phase reads the per-guide log under REPO_ROOT and strips the
    prefix, surfacing the last phase line; missing log -> ''."""
    monkeypatch.setattr(cs, "REPO_ROOT", tmp_path)
    log = tmp_path / "userdata" / "logs" / "iv_guides" / "dialga_origin.log"
    log.parent.mkdir(parents=True)
    log.write_text(_SYNTH_LOG)
    assert cs._ml_worker_phase("Dialga (Origin)") == _EXPECTED_PHASE
    assert cs._ml_worker_phase("Nonexistent Mon") == ""


def test_print_ml_guides_parses_synthetic_wrapper(capsys, tmp_path):
    """print_ml_guides digests a synthetic batch/wrapper log without crashing
    and reflects the parsed completion line."""
    wrapper = tmp_path / "overnight_20260627_181800.log"
    wrapper.write_text(
        "Detected 8 physical cores; reserving 1; running up to 7 concurrent dives.\n"
        "5 species to generate.\n"
        "[1/5] OK   Dialga (Origin) (2.0 min) dialga-origin-ml-iv-guide\n"
    )
    cs.print_ml_guides(wrapper, 100)
    out = capsys.readouterr().out
    assert "ML IV guides" in out
    assert "1/5" in out
