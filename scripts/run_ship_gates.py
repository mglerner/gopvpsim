#!/usr/bin/env python
"""THE ship-gate roster: every check a publishable site tree must pass.

Four entry points run ship gates -- publish_website.sh (pre-rsync),
overnight_redive.sh (chain step 9), phase2_preship.sh (pre-review), and
verify_overnight.py (morning check [4/5]). Before this module, each
carried its own list, and two of the four silently skipped the
unicode-dash gate -- a chain could print SUCCESS with violations
present (DRY review 2026-08-05 entry 3b). The roster now lives HERE;
entry points either exec this script (shell) or import SHIP_GATES
(python). Add a new gate by adding one tuple.

The gates run CONCURRENTLY (run_roster; 2026-09-25). Each is its own
subprocess and none depends on another, so the step costs the slowest
gate (the fast test tier, ~310-414 s) instead of the sum (~885 s
measured in the 2026-09-20 chain). Output: each gate's stdout/stderr
is captured; one "done" line per gate prints as it finishes (so a long
run shows progress), then each gate's full output prints as a block in
ROSTER order once all have finished. Blocks rather than a live
prefixed stream because the link scanner alone prints thousands of
per-file lines, and interleaving those with pytest's progress would be
unreadable.

Exit 0 iff every gate passes.
"""
import subprocess
import sys
import time
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

# (script name, extra args). Every gate takes --ship and exits nonzero
# on violations. Keep output quiet where the gate supports it -- the
# callers surface tails, not transcripts.
# (script name, FULL argument tuple). Not every gate takes --ship, so each
# entry carries its complete argv.
SHIP_GATES = (
    # Fast test suite + loud node-presence check. The slowest gate by far
    # (~310 s idle, ~414 s in the 2026-09-20 chain; see verify_tests.py),
    # so it sets the step's wall time now that gates run concurrently --
    # roster order is only the order the reports print in. Wired 2026-08-09
    # (test-suite review Phase 1) -- before this, no publish path ever
    # ran pytest; the 1,782-test contract layer was convention-only.
    ('verify_tests.py', ()),
    ('verify_article_links.py', ('--ship',)),
    ('verify_no_unicode_dashes.py', ('--ship', '-q')),
    # Dev-count sentinels render into the published guides
    # ({{dev:test_count}}, {{dev:pvpoke_cells_exact}}, ...) -- a stale
    # sentinel is a public wrong number. Wired in 2026-08-06 after the
    # final gate found it uncalled anywhere and a month stale.
    ('verify_dev_counts.py', ('--quiet',)),
    # Worlds 2026 surfaces: gate REMOVED from the roster 2026-08-31.
    # Worlds ran 2026-08-28..30. The shipped pages are frozen at engine
    # 5839391a7596 / gamemaster 8f1d6cca5c0f / worlds_code c1395dfa10b9,
    # so verify_worlds fails on all six stamps from main -- and because
    # this roster is shared by all four entry points, it blocked EVERY
    # publish path, not just a Worlds one. Michael's call (2026-08-31):
    # the surfaces RETIRE at the Twilight Trails site update; until then
    # they stay published exactly as shipped. scripts/verify_worlds.py
    # is unchanged -- run it by hand if the surfaces are ever rebaked.
)


GateResult = namedtuple('GateResult', 'gate rc stdout stderr elapsed')


def run_roster(gates, max_workers=None, on_done=None):
    """Run ``gates`` ((script, argv) pairs) concurrently, one thread each.

    Every gate is a separate script, so a thread per gate that just waits
    on its subprocess is all the parallelism needed. Returns GateResults
    in ROSTER order, whatever order the gates finished in -- callers
    report in that order and their rc logic sees the same list a serial
    loop would have produced. ``max_workers=1`` runs them one at a time,
    in roster order. ``on_done(result)`` is called from the main thread
    as each gate finishes.
    """
    def run(gate, argv):
        t0 = time.monotonic()
        r = subprocess.run([sys.executable, str(SCRIPTS / gate), *argv],
                           capture_output=True, text=True)
        return GateResult(gate, r.returncode, r.stdout, r.stderr,
                          time.monotonic() - t0)

    if not gates:
        return []
    with ThreadPoolExecutor(max_workers or len(gates)) as ex:
        futures = {ex.submit(run, g, a): i for i, (g, a) in enumerate(gates)}
        results = [None] * len(gates)
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
            if on_done:
                on_done(results[futures[fut]])
    return results


def run_gates(verbose=True, exclude=()):
    """Run every gate concurrently; return list of (gate, returncode) failures.

    Failures are listed in roster order. With ``verbose``, each gate's full
    output prints as a block (roster order) after all finish, preceded by
    one progress line per gate as it completes; without it, only a failing
    gate's output is written, to stderr (as before).

    ``exclude`` names gates to SKIP, by script filename. Added 2026-09-12 for
    ``publish_website.sh --partial``: a mid-bake publish legitimately fails
    verify_tests.py (rendered-artifact assertions about pages the bake has not
    produced), but the link and dash gates are exactly the ones you want then.
    Before this, --partial called those two gates directly and broke the
    "entry points route through the roster" invariant in
    tests/test_ship_gate_roster.py -- the whole point of which is that gates
    cannot silently drift out of an entry point's coverage. Skipping BY NAME
    through the roster keeps that property: the roster is still the single
    list, and a skip is visible in the output.
    """
    skipped = [g for g in exclude if g not in dict(SHIP_GATES)]
    if skipped:
        raise SystemExit(f'unknown gate(s) in exclude: {skipped}')
    for gate, _ in SHIP_GATES:
        if gate in exclude:
            print(f'SHIP GATE SKIPPED: {gate}')
    gates = [(g, a) for g, a in SHIP_GATES if g not in exclude]

    def progress(r):
        print(f'SHIP GATE done: {r.gate} rc={r.rc} ({r.elapsed:.0f} s)',
              flush=True)

    if verbose:
        print(f'Running {len(gates)} ship gates concurrently: '
              f'{", ".join(g for g, _ in gates)}', flush=True)
    results = run_roster(gates, on_done=progress if verbose else None)
    failures = []
    for r in results:
        if r.rc != 0:
            failures.append((r.gate, r.rc))
        if verbose:
            print(f'\n===== {r.gate}: rc={r.rc}, {r.elapsed:.0f} s =====',
                  flush=True)
            sys.stdout.write(r.stdout)
            sys.stdout.flush()
            sys.stderr.write(r.stderr)
            sys.stderr.flush()
        elif r.rc != 0:  # surface the evidence on failure
            sys.stderr.write(r.stdout or '')
            sys.stderr.write(r.stderr or '')
    return failures


def main():
    argv = sys.argv[1:]
    exclude = []
    for a in argv:
        if a.startswith('--exclude='):
            exclude += [g for g in a.split('=', 1)[1].split(',') if g]
    failures = run_gates(verbose='-q' not in argv, exclude=tuple(exclude))
    for gate, rc in failures:
        print(f'SHIP GATE FAILED: {gate} (rc={rc})', file=sys.stderr)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
