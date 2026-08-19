#!/usr/bin/env python
"""Run the joint-IV analysis pipeline for one pair config, end to end.

Chains the post-bake steps (the bake itself is long and runs detached;
this runner ABORTS if the pair's grids are not fully baked):

    meta -> breakpoints -> assemble -> denial -> page

Each step is the standalone script run as a subprocess (their own
verification blocks and aborts are the gates); output is teed to
<data_dir>/pipeline.log. The meta step is skipped loudly when the pair
config declares no replay_blob (the page renders those panels
honest-absent). Steps whose output already exists are re-run anyway --
they are minutes, and re-running keeps them consistent with the
freshest upstream artifact (idempotent by construction).

Usage:
    python scripts/joint_iv_run.py pairs/<pair>.toml [--skip-meta]
"""
import argparse
import json
import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from joint_iv_config import load_pair  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('pair', help='pairs/<pair>.toml config path')
    ap.add_argument('--skip-meta', action='store_true',
                    help='skip the meta-wins extraction even when a '
                         'replay blob is configured')
    args = ap.parse_args()
    cfg = load_pair(args.pair)
    pair_arg = str(cfg.path)

    manifest_path = cfg.data_dir / 'manifest.json'
    if not manifest_path.exists():
        sys.exit(f'ABORT: no bake manifest in {cfg.data_dir} -- bake first '
                 '(scripts/joint_iv_bake.py)')
    manifest = json.loads(manifest_path.read_text())
    unbaked = [g.label for g in cfg.grids
               if g.label not in manifest.get('grids', {})
               or not (cfg.data_dir / cfg.grid_filename(g.label)).exists()]
    if unbaked:
        sys.exit(f'ABORT: grids not baked yet: {unbaked}')

    log_path = cfg.data_dir / 'pipeline.log'
    log = open(log_path, 'a')

    def run(step, extra=()):
        cmd = [sys.executable, str(REPO / 'scripts' / step), pair_arg,
               *extra]
        print(f'== {step}', flush=True)
        log.write(f'== {time.strftime("%F %T")} {" ".join(cmd)}\n')
        log.flush()
        r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
        if r.returncode == 3 and step == 'joint_iv_meta.py':
            # Distinct code: the replay blob has no cube for this pair's
            # moveset -- an honest absence (page panels render absent),
            # not a failure. The reason is in the pipeline log.
            print(f'== {step} SKIPPED: no matching moveset cube in the '
                  f'replay blob (see {log_path})', flush=True)
            return False
        if r.returncode != 0:
            print(f'ABORT: {step} failed (exit {r.returncode}); see '
                  f'{log_path}', flush=True)
            sys.exit(r.returncode)
        return True

    have_meta = False
    if args.skip_meta or cfg.replay_blob is None:
        why = ('--skip-meta' if args.skip_meta
               else 'no replay_blob in the pair config')
        print(f'== joint_iv_meta.py SKIPPED ({why}); the page renders the '
              'meta panels honest-absent', flush=True)
    else:
        have_meta = run('joint_iv_meta.py', ('--verify',))
    run('joint_iv_breakpoints.py')
    run('joint_iv_assemble.py')
    run('joint_iv_denial.py')
    # An honestly-absent meta_wins is the one input the page may build
    # without; --allow-missing renders those panels as visible absences.
    run('build_joint_iv_page.py',
        () if have_meta else ('--allow-missing',))
    print(f'pipeline complete; log at {log_path}', flush=True)


if __name__ == '__main__':
    main()
