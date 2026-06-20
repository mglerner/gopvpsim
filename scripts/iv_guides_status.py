#!/usr/bin/env python
"""Pretty progress for a run_iv_guides.py batch. Designed for `watch -c`.

Parses the batch log (default userdata/logs/iv_guides_batch.log) for the
'[n/N] OK/FAIL Species (M.M min)' lines the driver prints, counts live
iv_envelope_analysis.py workers, and shows done/running/pending, throughput,
recent completions, and a rough ETA.

Usage:
  watch -c -n 5 .venv/bin/python scripts/iv_guides_status.py
  python scripts/iv_guides_status.py [path/to/batch.log]
"""
import os
import re
import subprocess
import sys

LOG = sys.argv[1] if len(sys.argv) > 1 else 'userdata/logs/iv_guides_batch.log'

C = {'r': '\033[0m', 'b': '\033[1m', 'dim': '\033[2m', 'grn': '\033[32m',
     'red': '\033[31m', 'yel': '\033[33m', 'cyn': '\033[36m', 'mag': '\033[35m'}


def col(s, c):
    return f"{C[c]}{s}{C['r']}"


def live_workers():
    try:
        out = subprocess.run(['pgrep', '-f', 'iv_envelope_analysis'],
                             capture_output=True, text=True).stdout
        return len([x for x in out.split() if x.strip()])
    except Exception:
        return 0


def _species_from_cmd(cmd):
    """Pull the focal species out of an iv_envelope_analysis.py command line,
    dropping flags (handles species with spaces, e.g. 'Palkia (Shadow)')."""
    after = cmd.split('iv_envelope_analysis.py', 1)[-1].split()
    toks, i = [], 0
    while i < len(after):
        t = after[i]
        if t in ('--all-shields', '--no-cache'):
            i += 1
        elif t == '--pool':
            i += 2
        else:
            toks.append(t)
            i += 1
    return ' '.join(toks) or '?'


def active_dives():
    """One row per live worker: (species, cpu%float, cpu_time, wall_elapsed).
    cpu% near 100 and cpu_time tracking wall_elapsed = healthy; cpu% ~0 or
    cpu_time frozen between ticks = stalled."""
    try:
        out = subprocess.run(
            ['ps', '-axo', 'pid=,%cpu=,time=,etime=,command='],
            capture_output=True, text=True).stdout
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        if 'iv_envelope_analysis.py' not in line or 'pgrep' in line:
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        _pid, cpu, cputime, etime, cmd = parts
        try:
            cpuf = float(cpu)
        except ValueError:
            cpuf = 0.0
        rows.append((_species_from_cmd(cmd), cpuf, cputime, etime))
    rows.sort(key=lambda r: r[0].lower())
    return rows


def main():
    if not os.path.exists(LOG):
        print(col(f"no batch log at {LOG} yet", 'dim'))
        return

    total = concurrency = None
    done = []                      # (ok: bool, species, minutes, info)
    line_re = re.compile(
        r'^\[(\d+)/(\d+)\]\s+(OK|FAIL)\s+(.+?)\s+\(([\d.]+)\s*min\)\s*(.*)$')
    finished_line = None
    with open(LOG) as f:
        for line in f:
            line = line.rstrip('\n')
            m = re.search(r'running up to (\d+) concurrent', line)
            if m:
                concurrency = int(m.group(1))
            m = re.match(r'(\d+) species to generate', line)
            if m:
                total = int(m.group(1))
            m = line_re.match(line)
            if m:
                total = int(m.group(2))
                done.append((m.group(3) == 'OK', m.group(4),
                             float(m.group(5)), m.group(6).strip()))
            if line.startswith('Done in '):
                finished_line = line

    running = live_workers()
    n_done = len(done)
    n_ok = sum(1 for d in done if d[0])
    n_fail = n_done - n_ok
    tot = total or (n_done + running)
    pending = max(0, tot - n_done - running)
    times = [d[2] for d in done]
    avg = sum(times) / len(times) if times else 0.0

    print(col('ML IV Guides — batch progress', 'b'))
    bar_w = 32
    frac = (n_done / tot) if tot else 0
    fill = int(bar_w * frac)
    bar = col('█' * fill, 'grn') + col('░' * (bar_w - fill), 'dim')
    print(f"  [{bar}] {col(f'{n_done}/{tot}', 'b')}  ({frac*100:4.1f}%)")

    ok_s = col(f'ok {n_ok}', 'grn')
    fail_s = col(f'fail {n_fail}', 'red' if n_fail else 'dim')
    run_s = col(f'running {running}', 'cyn')
    pend_s = col(f'pending {pending}', 'yel')
    print(f"  {ok_s}   {fail_s}   {run_s}   {pend_s}")

    if avg:
        # rough ETA: remaining work spread over the concurrency slots.
        remaining = tot - n_done
        slots = concurrency or max(1, running)
        eta = remaining * avg / max(1, slots)
        print(f"  {col('avg', 'dim')} {avg:.1f} min/guide   "
              f"{col('eta', 'dim')} ~{eta:.0f} min "
              f"({eta/60:.1f} h) at {slots}-wide")

    dives = active_dives()
    if dives:
        print(col('  active workers (cpu% · cpu-time · wall-elapsed):', 'dim'))
        for sp, cpu, cputime, etime in dives:
            warn = cpu < 20
            cpu_s = col(f'{cpu:4.0f}%', 'red' if warn else 'grn')
            flag = col('  <- LOW CPU, may be stalled', 'red') if warn else ''
            print(f"    {sp:<24} {cpu_s}  {cputime:>9} cpu  "
                  f"{etime:>10} elapsed{flag}")
        print(col('    (cpu-time should climb each tick and track elapsed; '
                  'if elapsed >> cpu-time the machine slept)', 'dim'))

    if done:
        print(col('  recent:', 'dim'))
        for ok, sp, mins, info in done[-6:]:
            tag = col('OK  ', 'grn') if ok else col('FAIL', 'red')
            extra = col(f'  {info}', 'red') if (not ok and info) else ''
            print(f"    {tag} {sp:<26} {mins:5.1f} min{extra}")

    if finished_line:
        print('\n  ' + col(finished_line, 'mag'))


if __name__ == '__main__':
    main()
