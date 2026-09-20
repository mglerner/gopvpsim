#!/usr/bin/env python
"""Ship gate: run the fast test suite (pytest -m 'not slow').

Added by the 2026-08-09 test-suite review, Phase 1 ("mechanize"): the
1,782-test contract layer previously ran only when a session remembered
to run it -- no gate on any publish path ever invoked pytest.

Two checks in one gate:

1. node must be on PATH. 19 JS-parity tests across 8 files skipif on
   missing node; on a ship machine that silent skip would greenlight
   5,400+ LOC of shipped JS with zero coverage (review finding F4).
   The per-test skipifs stay (dev machines without node still get a
   green local run); the GATE is where absence must be loud.
2. ``pytest tests -q -m 'not slow'`` -- the fast tier. The ``slow``
   marker holds the full gamemaster sweep and the blob-backed render
   tests; everything else runs.

   BUDGET ~7 MINUTES, not the "~44s" this said until 2026-09-20 (397 s
   measured that day on an idle 18-core machine, 549 s under load).
   This gate runs twice around a bake -- once at the launch keyboard on
   every publish path, once as the overnight chain's own last step --
   so the stale number was ~10 minutes of unexplained wait, twice. If
   it needs to come down, `@pytest.mark.render` on the newer
   real-render tests is the lever.

Exit 0 iff both pass.
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    if shutil.which('node') is None:
        print('SHIP GATE: node not on PATH -- the JS-parity tests would '
              'silently skip (19 tests / 8 files covering the shipped JS). '
              'Install node or fix PATH before shipping.', file=sys.stderr)
        return 1
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', str(REPO_ROOT / 'tests'),
         '-q', '-m', 'not slow'],
        cwd=REPO_ROOT)
    return r.returncode


if __name__ == '__main__':
    sys.exit(main())
