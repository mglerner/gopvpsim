#!/usr/bin/env python
"""Morning-after verification for an overnight re-dive chain.

Usage:
    python scripts/verify_overnight.py
    python scripts/verify_overnight.py --since "2026-06-11 19:37"
    python scripts/verify_overnight.py --markers Sylveon Primeape

Aggregates the mechanical morning checks into one command (born from
the 2026-06-12 morning where they were done by hand):

1. chain status — last line of userdata/logs/overnight_status.txt,
   plus any [FAIL] step lines in the newest overnight_*.log.
2. freshness — every dive dir under userdata/website/ must have its
   index*.html either all newer than the chain start (re-dived) or all
   older (not in this chain). Mixed vintages mean stale split-file
   orphans that downstream consumers would read as current data.
3. pool sanity — marker species must appear in every fresh GL dive's
   opponent list (proof the intended opponent pool actually loaded).
4. ship gates — verify_article_links --ship and
   verify_no_unicode_dashes --ship, run as subprocesses.
5. ML IV guides — every species in the ML pool (run_iv_guides'
   master_top60) must have a fresh _iv_envelope_all9.json, and the
   chain log must carry no "[WARN] ML IV guides" line. The ML bake is a
   best-effort tail step (WARN-not-FAIL by design so one bad guide can't
   abort index+verify), so without this check a partial/OOM-killed ML
   bake would pass the chain-status SUCCESS line silently.

Exit 0 when everything is green; 1 otherwise, with a labeled report.
The judgment work (archive diffs, browser spot-checks, publish notes)
stays human — this script only answers "did it finish and is the
output mechanically sane?".
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WEBSITE = REPO / 'userdata' / 'website'
LOGS = REPO / 'userdata' / 'logs'
STATUS_FILE = LOGS / 'overnight_status.txt'

# Species that entered the GL pool in the most recent refresh; their
# presence in a dive's opponent list proves the new pool loaded.
DEFAULT_MARKERS = ['Sylveon', 'Primeape', 'Umbreon']


def newest_chain_log() -> Path | None:
    logs = sorted(LOGS.glob('*/overnight_*.log'))
    return logs[-1] if logs else None


def chain_start(log_path: Path) -> datetime.datetime:
    m = re.search(r'overnight_(\d{8})_(\d{6})', log_path.name)
    return datetime.datetime.strptime(
        m.group(1) + m.group(2), '%Y%m%d%H%M%S')


def scan_narrative_warnings(log_text: str) -> list[str]:
    """Return one error string per narrative auto-gen patch WARN line.

    run_website_dives.py runs patch_dive_species_narrative.py per dive
    WARN-not-FAIL (a bad narrative patch can't abort later dives), emitting
    "[WARN] narrative patch failed for <slug> ..." to stdout, which
    overnight_redive.sh tees into the scanned chain log. Like the ML WARN,
    neither the [FAIL] scan nor the SUCCESS status line catches it, so
    without this scan a failed patch passes the gate silently.
    """
    return [f'narrative patch warned: {ln.strip()}'
            for ln in log_text.splitlines()
            if 'WARN] narrative patch failed' in ln]


def extract_opponents(html_path: Path) -> list[str] | None:
    content = html_path.read_text(errors='replace')
    i = content.find('"opponents": [')
    if i < 0:
        return None
    start = content.index('[', i)
    arr, _end = json.JSONDecoder().raw_decode(content[start:start + 200_000])
    return arr


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Morning-after overnight-chain verification')
    ap.add_argument('--since', metavar='"YYYY-MM-DD HH:MM"',
                    help='chain start cutoff (default: parsed from the '
                         'newest overnight_*.log filename)')
    ap.add_argument('--markers', nargs='+', default=DEFAULT_MARKERS,
                    help='species that must appear in every fresh GL '
                         f'dive opponent list (default: {DEFAULT_MARKERS})')
    args = ap.parse_args()

    errors: list[str] = []
    log_path = newest_chain_log()

    if args.since:
        since = datetime.datetime.strptime(args.since, '%Y-%m-%d %H:%M')
    elif log_path:
        since = chain_start(log_path)
    else:
        sys.exit('No overnight_*.log found and no --since given.')
    cutoff = since.timestamp()
    print(f'Chain log: {log_path.name if log_path else "(none)"} '
          f'| cutoff {since:%Y-%m-%d %H:%M}\n')

    # 1. Chain status -------------------------------------------------
    print('[1/5] chain status')
    if STATUS_FILE.exists():
        last = STATUS_FILE.read_text().strip().splitlines()[-1]
        ok = 'SUCCESS' in last
        print(f'  {"OK " if ok else "ERR"} status: {last}')
        if not ok:
            errors.append(f'chain status: {last}')
    else:
        errors.append('overnight_status.txt missing')
        print('  ERR overnight_status.txt missing')
    if log_path:
        log_text = log_path.read_text()
        fails = [ln.strip() for ln in log_text.splitlines()
                 if '[FAIL]' in ln]
        for ln in fails:
            errors.append(f'chain step failed: {ln}')
            print(f'  ERR {ln}')
        if not fails:
            print('  OK  no [FAIL] step lines')
        narr = scan_narrative_warnings(log_text)
        for ln in narr:
            errors.append(ln)
            print(f'  ERR {ln}')
        if not narr:
            print('  OK  no narrative-patch WARN lines')

    # 2. Freshness ----------------------------------------------------
    # Cover league dives (`*-league`) AND limited-cup dives (`*-cup`) so a cup
    # dive neither trips the guard nor is silently missed (mixed-vintage is an
    # error for both). The GL-only marker/pool-sanity check below is gated on
    # 'great-league' in the dir name, so cup dirs skip it -- cup pools
    # legitimately lack the GL markers.
    print('[2/5] dive-dir freshness')
    fresh_dirs: list[Path] = []
    skipped = 0
    for d in sorted(WEBSITE.glob('*-league')) + sorted(WEBSITE.glob('*-cup')):
        pages = sorted(d.glob('index*.html'))
        if not pages:
            continue
        fresh = [p for p in pages if p.stat().st_mtime >= cutoff]
        old = [p for p in pages if p.stat().st_mtime < cutoff]
        if fresh and old:
            names = ', '.join(p.name for p in old)
            errors.append(f'{d.name}: mixed vintage — stale: {names}')
            print(f'  ERR {d.name}: {len(fresh)} fresh + '
                  f'{len(old)} STALE ({names})')
        elif fresh:
            fresh_dirs.append(d)
        else:
            skipped += 1
    print(f'  OK  {len(fresh_dirs)} dirs fully fresh, '
          f'{skipped} not in this chain')

    # 3. Pool sanity --------------------------------------------------
    print('[3/5] pool sanity (markers: ' + ', '.join(args.markers) + ')')
    counts: dict[str, int] = {}
    for d in fresh_dirs:
        opps = extract_opponents(d / 'index.html')
        if opps is None:
            errors.append(f'{d.name}: no DATA.opponents found')
            print(f'  ERR {d.name}: no DATA.opponents found')
            continue
        counts[d.name] = len(opps)
        if 'great-league' in d.name:
            missing = [m for m in args.markers
                       if not any(o.split(' (')[0] == m for o in opps)]
            if missing:
                errors.append(f'{d.name}: markers missing: {missing}')
                print(f'  ERR {d.name}: {len(opps)} opponents, '
                      f'missing {missing}')
    if counts:
        lo, hi = min(counts.values()), max(counts.values())
        print(f'  OK  opponent counts across {len(counts)} fresh dives: '
              f'{lo}..{hi}' if lo != hi else
              f'  OK  all {len(counts)} fresh dives: {lo} opponents')

    # 4. Ship gates ---------------------------------------------------
    print('[4/5] ship gates')
    for gate in ('verify_article_links.py', 'verify_no_unicode_dashes.py'):
        r = subprocess.run(
            [sys.executable, str(REPO / 'scripts' / gate), '--ship'],
            capture_output=True, text=True)
        tail = (r.stdout or r.stderr).strip().splitlines()[-1:]
        verdict = 'OK ' if r.returncode == 0 else 'ERR'
        print(f'  {verdict} {gate}: {tail[0] if tail else "(no output)"}')
        if r.returncode != 0:
            errors.append(f'{gate} failed (rc={r.returncode})')

    # 5. ML IV guides -------------------------------------------------
    # The ML bake is a best-effort tail step (run_iv_guides outside step(),
    # WARN-not-FAIL), so neither the [FAIL] scan nor the SUCCESS status line
    # catches a partial/OOM-killed ML run. Check the actual guide outputs
    # against the pool, and surface the chain's own ML WARN line. Import
    # run_iv_guides for the pool/slug logic (DRY -- single source).
    print('[5/5] ML IV guides')
    try:
        import run_iv_guides as rig
        ml_species = rig.read_pool(rig.DEFAULT_POOL)
    except Exception as e:
        ml_species = []
        errors.append(f'ML guide pool unreadable: {e}')
        print(f'  ERR cannot read ML pool: {e}')
    if ml_species:
        dives = REPO / 'userdata' / 'dives'
        missing, stale = [], []
        for sp in ml_species:
            j = dives / f'{rig.json_slug(sp)}_iv_envelope_all9.json'
            if not j.exists():
                missing.append(sp)
            elif j.stat().st_mtime < cutoff:
                stale.append(sp)
        if missing:
            errors.append(f'ML guides never produced ({len(missing)}): {missing}')
            print(f'  ERR {len(missing)} ML guide(s) missing: {missing}')
        if stale:
            errors.append(f'ML guides not refreshed this chain ({len(stale)}): {stale}')
            print(f'  ERR {len(stale)} ML guide(s) stale: {stale}')
        if not missing and not stale:
            print(f'  OK  all {len(ml_species)} ML guides fresh')
    if log_path:
        ml_warn = [ln.strip() for ln in log_path.read_text().splitlines()
                   if 'WARN] ML IV guides' in ln]
        for ln in ml_warn:
            errors.append(f'ML guide step warned: {ln}')
            print(f'  ERR {ln}')

    # Verdict ----------------------------------------------------------
    print()
    if errors:
        print(f'FAIL — {len(errors)} problem(s):')
        for e in errors:
            print(f'  - {e}')
        return 1
    print('ALL GREEN — chain complete, output fresh, gates clean.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
