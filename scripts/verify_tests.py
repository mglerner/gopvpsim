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

   BUDGET ~5 MINUTES (310 s measured 2026-09-22 on an idle 18-core
   machine: 2,751 passed, 8 skipped, 156 deselected, 13 xfailed).
   Assume ~1.4x on a busy machine -- the previous 397 s baseline
   measured 549 s under load. This gate runs twice around a bake --
   once at the launch keyboard on every publish path, once as the
   overnight chain's own last step -- so a stale number here is
   unexplained wait, twice over. It said "~44s" until 2026-09-20 and
   "~7 min" until 2026-09-22, when the five fast-tier tests over ~10 s
   picked up `@pytest.mark.slow` (397 s -> 310 s).

   If it needs to come down further, the lever is
   `tests/test_deep_dive_brief.py`: ~245 s of the 310, about 170
   blob-backed tests at 1-9 s each, none individually over ~10 s.
   Marking the module `slow` would take this gate to roughly 1 min but
   drops ~170 published-prose contracts out of every publish path --
   a coverage call, not a timing one. NOT the lever: `@pytest.mark.
   render` on the `small_dive_html` consumers (25 s of shared session
   fixture). The testing policy keeps `render` separate from `slow`,
   and `-m "not slow"` does not deselect it, so marking one consumer
   slow just moves the render onto the next one.

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
