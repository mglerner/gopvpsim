"""Step [3/5] must REPORT an unusable pool file, not die on it.

``missing_pool_entries`` reads the dive's declared ``opponents_file``, so a
renamed/moved pool file raises ``FileNotFoundError`` (an ``OSError``) rather
than the ``ValueError`` the parser raises on a bad line. Step 3 used to catch
only ``ValueError``, so that drift propagated out of ``main()`` and aborted
the gate mid-step: steps 4 (ship gates) and 5 (ML IV guides) never ran, and
the morning check produced no verdict at all -- the worst failure mode for a
"did the overnight chain finish?" script.

The test drives ``main()`` end to end against a synthetic website tree so it
pins the BEHAVIOUR (an ERR line plus a nonzero exit, with steps 4 and 5 still
reached), not the shape of the except clause. Steps 4/5 are stubbed at the
import boundary they already use -- step 4 shells out to every ship gate,
which is minutes of subprocess work and has nothing to do with this path.
"""
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_overnight as vo  # noqa: E402


@pytest.fixture
def gate(tmp_path, monkeypatch):
    """A minimal green chain with one fresh dive whose pool file is missing."""
    website = tmp_path / "website"
    dive = website / "foo-league"
    dive.mkdir(parents=True)
    # extract_opponents() only needs the embedded JSON array.
    (dive / "index.html").write_text('var DATA = {"opponents": ["Azumarill"]};')

    status = tmp_path / "overnight_status.txt"
    status.write_text("2026-08-27 06:00 SUCCESS\n")

    monkeypatch.setattr(vo, "WEBSITE", website)
    monkeypatch.setattr(vo, "STATUS_FILE", status)
    # No chain log -> step 1's [FAIL]/WARN scans and step 5's ML WARN scan
    # are skipped; --since supplies the cutoff instead.
    monkeypatch.setattr(vo, "newest_chain_log", lambda: None)
    monkeypatch.setattr(vo, "load_resolutions", lambda: [])
    monkeypatch.setattr(
        vo, "dive_pool_map", lambda: {"foo-league": tmp_path / "renamed.txt"})

    ship = types.ModuleType("run_ship_gates")
    ship.SHIP_GATES = []
    monkeypatch.setitem(sys.modules, "run_ship_gates", ship)
    guides = types.ModuleType("run_iv_guides")
    guides.DEFAULT_POOL = tmp_path / "ml_pool.txt"
    guides.read_pool = lambda _p: []
    monkeypatch.setitem(sys.modules, "run_iv_guides", guides)

    monkeypatch.setattr(
        sys, "argv", ["verify_overnight.py", "--since", "2020-01-01 00:00"])
    return tmp_path


def test_missing_pool_file_reports_err_instead_of_aborting(gate, capsys):
    # Pre-fix this raised FileNotFoundError out of main().
    rc = vo.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "ERR foo-league: pool renamed.txt unusable" in out
    # ...and the gate ran to completion rather than dying inside step 3.
    assert "[4/5] ship gates" in out
    assert "[5/5] ML IV guides" in out
    assert "FAIL" in out


def test_malformed_pool_line_still_reports_err(gate, tmp_path, capsys):
    """The ValueError half of the widened clause still behaves.

    Positive control for the test above: it would also pass if step 3 had
    simply stopped calling missing_pool_entries at all.
    """
    pool = tmp_path / "renamed.txt"
    pool.write_text("Azumarill | fastBUG_BITE\n")
    with pytest.raises(ValueError):
        vo.missing_pool_entries(["Azumarill"], pool)
    rc = vo.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "ERR foo-league: pool renamed.txt unusable" in out
