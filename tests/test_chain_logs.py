"""Shared newest-chain-log rule (DRY review 2026-08-05 entry 3c).

Month subdirs lie (overnight_redive.sh hardcoded 2026-04 until
2026-08-04, so July logs sit under 2026-04/ on disk) and mtimes lie
after a copy. The one correct rule -- sort by the filename's launch
stamp -- lives in chain_logs and is used by verify_overnight,
overnight_eta, and chain_status.

The three consumer pins used to be exact import-line substrings, which
cannot fail on a refactor (an added import name, an isort, an alias or a
line wrap breaks them; a consumer that quietly re-implements the rule does
not). They now exercise each consumer: swap the shared function (or spy on
it) and drive the consumer's real entry point, so a consumer that keeps the
import but re-implements the rule fails.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import chain_logs  # noqa: E402
from chain_logs import newest_chain_log, run_stamp  # noqa: E402


def test_stamp_beats_path_order(tmp_path):
    # A July run misfiled under 2026-04/ must still beat a May run
    # correctly filed under 2026-05/ -- the exact on-disk situation the
    # old path sort got wrong.
    misfiled = tmp_path / '2026-04' / 'overnight_20260706_204813.log'
    older = tmp_path / '2026-05' / 'overnight_20260520_010101.log'
    for p in (misfiled, older):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('x')
    assert sorted([misfiled, older])[-1] == older  # path sort picks WRONG
    assert newest_chain_log(tmp_path) == misfiled  # stamp sort picks right


def test_run_stamp_extraction():
    assert run_stamp(Path('overnight_20260706_204813.log')) == '20260706_204813'
    assert run_stamp(Path('somethingelse.log')) == ''


def test_empty_dir_returns_none(tmp_path):
    assert newest_chain_log(tmp_path) is None


def test_verify_overnight_routes_through_shared_rule(monkeypatch):
    import verify_overnight
    sentinel = Path('/sentinel/overnight_20260101_000000.log')
    monkeypatch.setattr(chain_logs, 'newest_chain_log', lambda root: sentinel)
    assert verify_overnight.newest_chain_log() == sentinel


def test_overnight_eta_routes_through_shared_rule(tmp_path, monkeypatch):
    """USAGE, not just the alias binding. An earlier version of this test
    asserted ``overnight_eta._run_stamp is run_stamp`` and nothing else --
    which stays green if someone leaves the import in place and inlines the
    sort key at the one call site (overnight_eta.py:156). So drive the real
    consumer and count the calls (2026-08-09 adversarial review)."""
    import overnight_eta
    (tmp_path / '2026-07').mkdir()
    (tmp_path / '2026-05').mkdir()
    current = tmp_path / '2026-07' / 'overnight_20260706_204813.log'
    current.write_text('')
    prior = tmp_path / '2026-05' / 'overnight_20260520_010101.log'
    prior.write_text('[1/2] azumarill-great-league\nDone in 3.0 min\n')

    calls = []
    real = overnight_eta._run_stamp
    monkeypatch.setattr(overnight_eta, '_run_stamp',
                        lambda p: calls.append(p) or real(p))
    table = overnight_eta._build_slug_timing_table(current)
    # Anti-vacuity: the consumer really did its job over these logs...
    assert table == {'azumarill-great-league': 3.0}, table
    # ...and it got its ordering from the shared rule, not a private one.
    assert calls, 'overnight_eta stopped consulting the shared stamp rule'
    assert real is run_stamp, 'overnight_eta re-implemented the stamp rule'


def test_chain_status_routes_through_shared_rule(tmp_path, monkeypatch):
    """latest_file must pick by launch stamp, not mtime. Built as the real
    disagreement: the July run is older on disk, newer by stamp."""
    import chain_status
    newer_stamp = tmp_path / 'overnight_20260706_204813.log'
    older_stamp = tmp_path / 'overnight_20260520_010101.log'
    for p in (newer_stamp, older_stamp):
        p.write_text('x')
    os.utime(newer_stamp, (0, 0))  # oldest mtime, newest stamp
    assert chain_status.latest_file(str(tmp_path / '*.log')) == newer_stamp
    calls = []
    real = chain_logs.run_stamp
    monkeypatch.setattr(chain_logs, 'run_stamp',
                        lambda p: calls.append(p) or real(p))
    chain_status.latest_file(str(tmp_path / '*.log'))
    assert calls, 'chain_status stopped consulting the shared stamp rule'
