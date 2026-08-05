"""Shared newest-chain-log rule (DRY review 2026-08-05 entry 3c).

Month subdirs lie (overnight_redive.sh hardcoded 2026-04 until
2026-08-04, so July logs sit under 2026-04/ on disk) and mtimes lie
after a copy. The one correct rule -- sort by the filename's launch
stamp -- lives in chain_logs and is used by verify_overnight,
overnight_eta, and chain_status.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

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


def test_consumers_route_through_shared_rule():
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    assert 'from chain_logs import newest_chain_log' in (
        scripts / 'verify_overnight.py').read_text()
    assert 'from chain_logs import run_stamp' in (
        scripts / 'overnight_eta.py').read_text()
    assert 'from chain_logs import run_stamp' in (
        scripts / 'chain_status.py').read_text()
