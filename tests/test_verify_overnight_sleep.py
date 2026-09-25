"""verify_overnight's system-sleep check (added 2026-09-25).

The 2026-09-20 bake slept 1.82 h across two lid-closes and nothing went red:
every step passed, and the long gaps were first blamed on render code. The
check reads `pmset -g log` and goes red when the machine slept inside the
chain window. The fixture lines below are verbatim from that night's log
(09-21 06:35, the first lid-close), so the parser is pinned to the real
format, not a guess at it.

Pre-fix value: there was no check, so main() printed nothing about sleep and
returned 0 for a chain that had slept (test_main_goes_red_on_a_slept_chain).
"""
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import pmset_sleep  # noqa: E402
import verify_overnight as vo  # noqa: E402

PMSET = """\
PM ASL data store: /var/log/powermanagement

Time stamp                Domain              \tMessage   \tDuration  \tDelay
==========                ======              \t=======   \t========  \t=====
2026-09-21 06:30:00 -0400 Assertions          \tPID 1(x) Created PreventUserIdleSystemSleep "caffeinate" 00:00:00
2026-09-21 06:35:52 -0400 Sleep               \tEntering DarkWake state due to 'Clamshell Sleep':TCPKeepAlive=active Using AC (Charge:4%)
2026-09-21 06:35:57 -0400 Sleep               \tEntering Sleep state due to 'Clamshell Sleep':TCPKeepAlive=active Using Batt (Charge:4%) 921 secs
2026-09-21 06:51:18 -0400 DarkWake            \tDarkWake from Deep Idle [CDNP] : due to NUB.SPMI0Sw3IRQ nub-spmi0.0x02 rtc/SleepService Using BATT (Charge:4%) 2 secs
2026-09-21 06:51:20 -0400 Sleep               \tEntering Sleep state due to 'Sleep Service Back to Sleep':TCPKeepAlive=active Using Batt (Charge:4%) 976 secs
2026-09-21 07:07:36 -0400 DarkWake            \tDarkWake from Deep Idle [CDNP] : due to NUB.SPMI0Sw3IRQ nub-spmi0.0x02 rtc/SleepService Using BATT (Charge:4%) 2 secs
2026-09-21 07:07:38 -0400 Sleep               \tEntering Sleep state due to 'Sleep Service Back to Sleep':TCPKeepAlive=active Using Batt (Charge:4%) 11 secs
2026-09-21 07:17:52 -0400 Wake                \tWake from Deep Idle [CDNVA] : due to smc.sysState.Wake(0x70070000) lid SMC.OutboxNotEmpty RTP.multi-touch/UserActivity Assertion Using BATT (Charge:3%)
"""
SLEPT = 921 + 976 + 11          # the three 'Entering Sleep state' durations
T0 = pmset_sleep._epoch('2026-09-21 06:30:00 -0400')   # first stamp
LID = pmset_sleep._epoch('2026-09-21 06:35:57 -0400')


def test_parser_reads_the_real_format():
    windows, first = pmset_sleep.parse_sleep_windows(PMSET)
    assert first == T0
    assert [r for _s, _e, r in windows] == [
        'Clamshell Sleep', 'Sleep Service Back to Sleep',
        'Sleep Service Back to Sleep']
    assert windows[0][:2] == (LID, LID + 921)
    assert sum(e - s for s, e, _r in windows) == SLEPT


def test_sleep_inside_the_window_is_red_with_the_slept_total():
    verdict, msg = vo.chain_sleep_report(PMSET, T0, T0 + 86400)
    assert verdict == 'ERR'
    assert f'system slept {SLEPT} s' in msg
    assert 'Clamshell Sleep' in msg and '3 sleep entries' in msg


def test_window_edges_clip_the_total():
    """A chain that ended 100 s into the lid-close slept 100 s of it."""
    verdict, msg = vo.chain_sleep_report(PMSET, T0, LID + 100)
    assert verdict == 'ERR'
    assert 'system slept 100 s' in msg


def test_sleep_outside_the_window_is_ok():
    """Positive control: the same log is green for a chain that ended
    before the lid closed."""
    verdict, msg = vo.chain_sleep_report(PMSET, T0, LID - 1)
    assert verdict == 'OK', msg


@pytest.mark.parametrize('text', [None, '', 'pmset: command not found\n'])
def test_unavailable_or_unparseable_log_is_skip(text):
    verdict, msg = vo.chain_sleep_report(text, T0, T0 + 86400)
    assert verdict == 'SKIP'
    assert 'unchecked' in msg


def test_log_that_starts_after_the_chain_is_skip_not_ok():
    """A rolled-over log that shows no sleep cannot vouch for the part of
    the chain it does not cover."""
    verdict, msg = vo.chain_sleep_report(PMSET, T0 - 7200, LID - 1)
    assert verdict == 'SKIP'
    assert 'starts after the chain' in msg


def test_read_pmset_log_is_none_without_pmset(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError('pmset')
    monkeypatch.setattr(subprocess, 'run', missing)
    assert pmset_sleep.read_pmset_log() is None

    def hangs(*a, **k):
        raise subprocess.TimeoutExpired('pmset', 1)
    monkeypatch.setattr(subprocess, 'run', hangs)
    assert pmset_sleep.read_pmset_log() is None


@pytest.fixture
def chain(tmp_path, monkeypatch):
    """A green chain whose log spans the 06:35 lid-close; steps 2-5 stubbed."""
    log = tmp_path / "overnight_20260920_164044.log"
    log.write_text("2026-09-20 16:40:44 === overnight chain start ===\n")
    import os
    os.utime(log, (T0 + 86400, T0 + 86400))
    status = tmp_path / "overnight_status.txt"
    status.write_text("2026-09-22 06:21 SUCCESS overnight chain complete\n")
    monkeypatch.setattr(vo, "WEBSITE", tmp_path / "website")
    monkeypatch.setattr(vo, "STATUS_FILE", status)
    monkeypatch.setattr(vo, "newest_chain_log", lambda: log)
    monkeypatch.setattr(vo, "dive_pool_map", lambda: {})
    ship = types.ModuleType("run_ship_gates")
    ship.SHIP_GATES = []
    monkeypatch.setitem(sys.modules, "run_ship_gates", ship)
    guides = types.ModuleType("run_iv_guides")
    guides.DEFAULT_POOL = tmp_path / "ml_pool.txt"
    guides.read_pool = lambda _p: []
    monkeypatch.setitem(sys.modules, "run_iv_guides", guides)
    monkeypatch.setattr(
        sys, "argv", ["verify_overnight.py", "--since", "2026-09-20 16:40"])
    return log


def test_main_goes_red_on_a_slept_chain(chain, monkeypatch, capsys):
    monkeypatch.setattr(vo, "load_resolutions", lambda: [])
    monkeypatch.setattr(pmset_sleep, "read_pmset_log", lambda: PMSET)
    rc = vo.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert f"ERR system slept {SLEPT} s" in out


def test_main_is_green_when_pmset_is_unavailable(chain, monkeypatch, capsys):
    """SKIP never fails the gate (non-macOS, or pmset broken)."""
    monkeypatch.setattr(vo, "load_resolutions", lambda: [])
    monkeypatch.setattr(pmset_sleep, "read_pmset_log", lambda: None)
    rc = vo.main()
    out = capsys.readouterr().out
    assert "SKIP system sleep unchecked" in out
    assert rc == 0, out


def test_a_recorded_resolution_clears_the_sleep_line(chain, monkeypatch,
                                                     capsys):
    monkeypatch.setattr(vo, "load_resolutions", lambda: [{
        'chain_log': chain.name, 'step': 'system slept',
        'fix_commit': 'n/a', 'reason': 'lid closed; timings understood',
        'verified': 'pmset -g log'}])
    monkeypatch.setattr(pmset_sleep, "read_pmset_log", lambda: PMSET)
    rc = vo.main()
    out = capsys.readouterr().out
    assert f"RSLV system slept {SLEPT} s" in out
    assert rc == 0, out
