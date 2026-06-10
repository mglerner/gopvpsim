#!/usr/bin/env python
"""Re-render a dive's HTML from a saved replay blob, without re-simming.

deep_dive.py dumps its full render-input state (moveset data + scores,
thresholds, slayer iteration result, narrative, ...) to
userdata/replay/*.replay.pkl.gz right after sims complete (skip with
--no-replay-dump). This script loads that blob and re-runs the exact
same render path (deep_dive.render_dive_html), so iterating on
renderer / analysis-section code costs seconds instead of a full
re-sim. The sim data in the blob is immutable; only display/analysis
code changes are picked up.

Usage:
    # Re-render in place (overwrite the dive's original HTML output):
    python scripts/replay_analysis.py userdata/replay/20260610_..._great.replay.pkl.gz

    # Render to a different path (e.g. /tmp for side-by-side diffing):
    python scripts/replay_analysis.py BLOB --html /tmp/replay_test.html
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deep_dive  # noqa: E402
from deep_dive_logging import init_logger  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description='Re-render a dive HTML from a saved replay blob '
                    '(no re-simming).')
    parser.add_argument('blob', help='Path to a *.replay.pkl.gz file '
                                     'written by deep_dive.py')
    parser.add_argument('--html', default=None, metavar='PATH',
                        help='Override the output HTML path (default: the '
                             "dive's original output path)")
    args = parser.parse_args()

    state = deep_dive.load_replay_state(args.blob)
    init_logger(state['species'], state['league'],
                shadow=state.get('shadow', False), log_file='/dev/null')

    if args.html:
        state['html_path'] = args.html
    out_parent = os.path.dirname(os.path.abspath(state['html_path']))
    if out_parent:
        os.makedirs(out_parent, exist_ok=True)

    print(f"Replaying {state['species']} ({state['league']}) "
          f"-> {state['html_path']}")
    t0 = time.time()
    deep_dive.render_dive_html(state)
    print(f"Re-rendered in {time.time() - t0:.1f}s")


if __name__ == '__main__':
    main()
