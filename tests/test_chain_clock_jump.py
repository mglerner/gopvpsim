"""overnight_redive.sh's keeper-loop sleep tripwire (added 2026-09-25).

The TTL keeper ticks every CACHE_TOUCH_POLL seconds; it cannot tick while the
machine is asleep, so a wall-clock gap far above one poll between two ticks
is (roughly) system sleep. The chain now writes a [WARN] line to its log when
that happens. Pre-fix nothing did: the 2026-09-20 bake's two lid-closes left
no trace in the chain log and were first misread as slow render code.

The function is run for real under bash, extracted verbatim from the script,
so the test exercises the shipped shell, not a Python re-implementation.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'overnight_redive.sh'

pytestmark = pytest.mark.skipif(shutil.which('bash') is None,
                                reason='needs bash')


def _snippet() -> str:
    src = SCRIPT.read_text()
    slack = re.search(r'^CLOCK_JUMP_SLACK=.*$', src, re.M)
    fn = re.search(r'^clock_jump_warning\(\) \{\n.*?^\}$', src, re.M | re.S)
    assert slack and fn, 'clock_jump_warning or its slack default is gone'
    return slack.group(0) + '\n' + fn.group(0) + '\n'


def _run(last: int, now: int, poll: int = 60) -> str:
    r = subprocess.run(
        ['bash', '-c', f'set -euo pipefail\nCACHE_TOUCH_POLL={poll}\n'
                       f'{_snippet()}clock_jump_warning {last} {now}'],
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_on_time_and_slightly_late_ticks_are_quiet():
    assert _run(1000, 1060) == ''
    assert _run(1000, 1000 + 60 + 120) == ''     # at the slack edge


def test_a_lid_close_gap_warns_with_the_unaccounted_time():
    # 09-21 06:35 lid-close: the sleep entries + DarkWakes span 2,515 s.
    out = _run(1000, 1000 + 60 + 2515)
    assert '[WARN] wall clock jumped 2575s' in out
    assert '~2515s unaccounted' in out
    assert 'pmset -g log' in out


def test_the_keeper_loop_calls_it_and_it_is_defined_before_the_fork():
    """A function defined after `( ... ) &` is invisible in the subshell,
    and the keeper would die on 'command not found' under set -e."""
    src = SCRIPT.read_text()
    loop = re.search(r'^\(\n(.*?)^\) &$', src, re.M | re.S)
    assert loop, 'keeper subshell not found'
    body = loop.group(1)
    assert re.search(r'clock_jump_warning\s+"\$last_tick"\s+"\$now_tick"',
                     body), body
    assert re.search(r'last_tick=\$now_tick', body), body
    # Positive control: the loop this found is the TTL keeper.
    assert 'touch_data_cache' in body
    assert src.index('clock_jump_warning() {') < loop.start()
