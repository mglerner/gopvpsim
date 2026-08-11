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

Exit 0 iff every gate passes.
"""
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

# (script name, extra args). Every gate takes --ship and exits nonzero
# on violations. Keep output quiet where the gate supports it -- the
# callers surface tails, not transcripts.
# (script name, FULL argument tuple). Not every gate takes --ship, so each
# entry carries its complete argv.
SHIP_GATES = (
    # Fast test suite + loud node-presence check FIRST: fail on broken
    # code in ~44s before the multi-minute link scan. Wired 2026-08-09
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
    # Worlds 2026 surfaces (season-scoped; retires with worlds/):
    # manifest stamps + coverage, pair-page/deferred agreement, hub FN
    # numbers fresh, *_great.toml collision glob. Wired 2026-08-11
    # (session 5).
    ('verify_worlds.py', ('--quiet',)),
)


def run_gates(verbose=True):
    """Run every gate; return list of (gate, returncode) failures."""
    failures = []
    for gate, argv in SHIP_GATES:
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / gate), *argv],
            capture_output=not verbose, text=True)
        if r.returncode != 0:
            failures.append((gate, r.returncode))
            if not verbose:  # surface the evidence on failure
                sys.stderr.write(r.stdout or '')
                sys.stderr.write(r.stderr or '')
    return failures


def main():
    failures = run_gates(verbose='-q' not in sys.argv[1:])
    for gate, rc in failures:
        print(f'SHIP GATE FAILED: {gate} (rc={rc})', file=sys.stderr)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
