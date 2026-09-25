"""run_ship_gates runs the roster concurrently (2026-09-25, plan item R5).

Stubbed gates only -- the real roster includes the fast test tier, which
cannot run from inside itself. The barrier test FAILS on the old serial
loop: each stub waits until every stub has started, so a serial runner
times the first one out. The parity test pins that the concurrent runner
reports the same (gate, rc, output) list, in roster order, as a serial
one (max_workers=1).
"""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import run_ship_gates  # noqa: E402

# A stub gate: wait at a barrier until N stubs have started, optionally
# sleep, print one line to each stream, exit with the given rc.
_STUB = textwrap.dedent('''\
    import pathlib, sys, time
    d, name = pathlib.Path(sys.argv[1]), sys.argv[2]
    rc, barrier, sleep = int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])
    (d / (name + '.started')).touch()
    deadline = time.monotonic() + 10
    while len(list(d.glob('*.started'))) < barrier:
        if time.monotonic() > deadline:
            print(name + ': barrier timeout (gates ran serially)')
            sys.exit(99)
        time.sleep(0.02)
    time.sleep(sleep)
    print(name + ' stdout')
    print(name + ' stderr', file=sys.stderr)
    sys.exit(rc)
''')

# (name, rc, sleep). 'a' is first in the roster but finishes LAST, so a
# runner that reported in completion order would be caught.
_SPEC = (('gate_a.py', 0, 0.6), ('gate_b.py', 3, 0.0),
         ('gate_c.py', 0, 0.2), ('gate_d.py', 1, 0.0))


def _stub_roster(tmp_path, monkeypatch, barrier):
    work = tmp_path / 'work'
    work.mkdir()
    gates = []
    for name, rc, sleep in _SPEC:
        (tmp_path / name).write_text(_STUB)
        gates.append((name, (str(work), name, str(rc), str(barrier),
                             str(sleep))))
    monkeypatch.setattr(run_ship_gates, 'SCRIPTS', tmp_path)
    monkeypatch.setattr(run_ship_gates, 'SHIP_GATES', tuple(gates))
    return tuple(gates)


def test_gates_run_concurrently(tmp_path, monkeypatch):
    # Every stub blocks until all four have started. The pre-2026-09-25
    # serial loop returned [(gate_a, 99), (gate_b, 99), (gate_c, 99),
    # (gate_d, 1)] here after ~30 s of barrier timeouts.
    _stub_roster(tmp_path, monkeypatch, barrier=len(_SPEC))
    failures = run_ship_gates.run_gates(verbose=False)
    assert failures == [('gate_b.py', 3), ('gate_d.py', 1)]


def test_concurrent_roster_matches_serial(tmp_path, monkeypatch):
    gates = _stub_roster(tmp_path, monkeypatch, barrier=0)
    conc = run_ship_gates.run_roster(gates)
    serial = run_ship_gates.run_roster(gates, max_workers=1)

    def key(results):
        return [(r.gate, r.rc, r.stdout, r.stderr) for r in results]
    assert key(conc) == key(serial)
    # Non-trivial and in ROSTER order, not completion order.
    assert [r.gate for r in conc] == [name for name, _, _ in _SPEC]
    assert [r.rc for r in conc] == [rc for _, rc, _ in _SPEC]
    assert conc[0].stdout == 'gate_a.py stdout\n'
    assert conc[0].stderr == 'gate_a.py stderr\n'


def test_run_gates_verbose_prints_blocks_in_roster_order(
        tmp_path, monkeypatch, capsys):
    _stub_roster(tmp_path, monkeypatch, barrier=0)
    failures = run_ship_gates.run_gates(
        verbose=True, exclude=('gate_c.py',))
    assert failures == [('gate_b.py', 3), ('gate_d.py', 1)]
    out = capsys.readouterr().out
    assert 'SHIP GATE SKIPPED: gate_c.py' in out
    assert '===== gate_c.py' not in out
    heads = [out.index(f'===== {g}') for g in ('gate_a.py', 'gate_b.py',
                                               'gate_d.py')]
    assert heads == sorted(heads)
    # Each gate's stdout lands inside its own block.
    assert heads[0] < out.index('gate_a.py stdout') < heads[1]
    # One progress line per gate that ran.
    assert out.count('SHIP GATE done: ') == 3


def test_unknown_exclude_is_rejected(tmp_path, monkeypatch):
    _stub_roster(tmp_path, monkeypatch, barrier=0)
    with pytest.raises(SystemExit):
        run_ship_gates.run_gates(exclude=('nope.py',))
