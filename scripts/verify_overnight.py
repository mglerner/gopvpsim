#!/usr/bin/env python
"""Morning-after verification for an overnight re-dive chain.

Usage:
    python scripts/verify_overnight.py
    python scripts/verify_overnight.py --since "2026-06-11 19:37"
    python scripts/verify_overnight.py --markers Sylveon Primeape

Aggregates the mechanical morning checks into one command (born from
the 2026-06-12 morning where they were done by hand):

1. chain status — last line of userdata/logs/overnight_status.txt,
   plus any [FAIL] step lines in the newest overnight_*.log. A failure
   that was diagnosed, fixed and re-verified by hand can be recorded in
   docs/chain_resolutions.toml (see load_resolutions) so it reports as
   RSLV rather than staying red forever. Also scans the same log for
   "[WARN] narrative patch failed" lines (see scan_narrative_warnings):
   run_website_dives patches the species narrative WARN-not-FAIL, so a
   failed patch would otherwise pass the gate silently. Same for
   "Which one to build?: omitted/skipped" lines (see
   scan_which_build_omissions): deep_dive degrades that section to a
   WARNING and still exits 0, so the flagship section can vanish from a
   whole bake with nothing red anywhere. Finally it reads macOS
   `pmset -g log` for system sleep inside the chain window (see
   chain_sleep_report): a lid-close pauses the bake without failing
   anything, and the 2026-09-20 bake's 1.82 h of clamshell sleep was first
   misread as slow render code.
2. freshness — every dive dir under userdata/website/ must have its
   index*.html either all newer than the chain start (re-dived) or all
   older (not in this chain). Mixed vintages mean stale split-file
   orphans that downstream consumers would read as current data.
3. pool sanity — every entry a dive's own opponents_file declares must
   appear in that dive's opponent list (see missing_pool_entries), plus
   the older marker-species check on fresh GL dives. Proof the intended
   opponent pool actually loaded, and that no entry was silently dropped
   by a get_default_moveset failure.
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
import tomllib
from pathlib import Path

from gopvpsim.data import cup_slug_suffix

REPO = Path(__file__).resolve().parent.parent
WEBSITE = REPO / 'userdata' / 'website'
LOGS = REPO / 'userdata' / 'logs'
STATUS_FILE = LOGS / 'overnight_status.txt'
RESOLUTIONS_FILE = REPO / 'docs' / 'chain_resolutions.toml'

# Glob for cup dive dirs. A cup dive slug is FLAT `<species>-<cup>-cup`, and
# data.cup_slug_suffix owns the `<cup>-cup` half -- its docstring names THIS
# glob as one of its three consumers, so derive the pattern from the helper
# instead of re-spelling '-cup' here (the whole point of the helper is that
# the shape is written down once). The cup name stays a wildcard on purpose:
# keying off CUP_REGISTRY would silently skip a dive dir for an unregistered
# cup, and "silently missed" is the failure mode this check exists to prevent.
CUP_DIR_GLOB = f'*-{cup_slug_suffix("*")}'

# Species that entered the GL pool in the most recent refresh; their
# presence in a dive's opponent list proves the new pool loaded. Keep this
# in step with opponent_pools/gl_top50_plus_cs.txt: the 2026-09-20 bake was
# checked against Sylveon and Primeape, which had LEFT the pool on 09-17, so
# the morning gate printed 76 false "markers missing" lines. A test now
# asserts every marker is in the committed pool.
# 2026-09-17 regeneration entrants (+ Umbreon, in the pool throughout):
DEFAULT_MARKERS = ['Charjabug (Shadow)', 'Diggersby', 'Forretress (Shadow)',
                   'Oinkologne (Female)', 'Umbreon']


def newest_chain_log() -> Path | None:
    # Filename-stamp sort via the shared rule (chain_logs) -- the old
    # path sort ordered runs wrong across month dirs (entry 3c).
    from chain_logs import newest_chain_log as _newest
    return _newest(LOGS)


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


def scan_which_build_omissions(log_text: str) -> list[str]:
    """Return one error string per omitted/skipped "Which one to build?" line.

    deep_dive._which_build_sections wraps the whole section render in a bare
    ``except Exception`` and degrades to a single WARNING line -- the dive
    still exits 0, the page still renders, and the chain still prints
    SUCCESS. So the flagship section can be missing from any number of pages
    with nothing red anywhere. Same silent-incompleteness shape as the
    narrative-patch WARN above; same treatment.
    """
    out = []
    for ln in log_text.splitlines():
        if ('Which one to build?: omitted' in ln
                or 'Which one to build?: skipped' in ln):
            out.append(f'which-one-to-build section missing: {ln.strip()}')
    return out


def chain_sleep_report(pmset_text: str | None, start: float,
                       end: float) -> tuple[str, str]:
    """-> (verdict, message) for system sleep inside [start, end).

    verdict is 'ERR' when the machine slept at all inside the chain window,
    'OK' when the power log covers the whole window and shows no sleep, and
    'SKIP' when it cannot say: no pmset (not macOS), pmset failed, an
    unparseable log, or a log that begins after the chain did and shows no
    sleep in the part it does cover. SKIP never counts as a failure.

    Why red: a sleeping chain fails nothing -- every step still passes -- but
    every wall-clock number from that bake (per-dive "Done in", the ETA seed
    table, bake_timing_report) silently includes the slept time. The
    2026-09-20 bake slept 1.82 h across two lid-closes, and the long gaps in
    Jellicent UL and Shadow Charjabug were first blamed on render code. Once
    the timings are understood, record a resolution for this log in
    docs/chain_resolutions.toml (step "system slept") to clear it.
    """
    from pmset_sleep import overlap_seconds, parse_sleep_windows
    if pmset_text is None:
        return 'SKIP', ('system sleep unchecked: `pmset -g log` unavailable '
                        '(not macOS, or pmset failed)')
    windows, first = parse_sleep_windows(pmset_text)
    if first is None:
        return 'SKIP', ('system sleep unchecked: `pmset -g log` output had '
                        'no timestamped lines')
    slept = overlap_seconds(windows, start, end)
    if slept > 0:
        inside = [(s, r) for s, e, r in windows if min(e, end) > max(s, start)]
        lids = [datetime.datetime.fromtimestamp(s).strftime('%m-%d %H:%M')
                for s, r in inside if r == 'Clamshell Sleep']
        lid_txt = (f', lid-close (Clamshell Sleep) at {", ".join(lids)}'
                   if lids else '')
        return 'ERR', (f'system slept {slept:.0f} s ({slept / 3600:.2f} h) '
                       f'during the chain: {len(inside)} sleep entries'
                       f'{lid_txt}; its wall-clock timings include this')
    if first > start:
        began = datetime.datetime.fromtimestamp(first)
        return 'SKIP', (f'system sleep unchecked before {began:%Y-%m-%d %H:%M}'
                        f': `pmset -g log` starts after the chain did (none '
                        f'after that)')
    return 'OK', 'no system sleep in the chain window (pmset -g log)'


VINTAGE_FILE = 'vintage.toml'


def read_vintage(d: Path) -> dict | None:
    """The engine / gamemaster / rankings stamp deep_dive.py left in ``d``.

    None when the dir carries no stamp at all -- a dive rendered before the
    stamp existed, or one whose stamping failed. That is reported as its own
    line rather than silently folded into "consistent", because "no evidence"
    and "evidence of one vintage" are different answers.
    """
    f = d / VINTAGE_FILE
    if not f.exists():
        return None
    try:
        with open(f, 'rb') as fh:
            return tomllib.load(fh)
    except Exception:                                        # noqa: BLE001
        return {}


def vintage_errors(dirs) -> list[str]:
    """One error per MIXED build stamp across the dirs a chain wrote.

    A dive's scores come frozen out of its replay blob, but the render reads
    the live gamemaster and the live rankings, so a TTL refetch part-way
    through a multi-day bake silently changes opponent ranks -- and therefore
    the verdicts a page prints -- between one page and the next. Before this
    check NOTHING would have caught that after the fact: the pages look fine,
    every gate passed, and the only protection was remembering to launch
    through overnight_redive.sh (whose keeper is what prevents it). The
    2026-09-12 bake is the recorded instance.

    ``dirs`` are the dive dirs this chain refreshed. Takes the dirs rather
    than globbing so a dive the chain did NOT touch cannot report a stale
    stamp as a mixed bake.
    """
    seen: dict[str, dict[str, list[str]]] = {
        'engine_hash': {}, 'gamemaster_hash': {}}
    unstamped: list[str] = []
    for d in dirs:
        v = read_vintage(Path(d))
        if not v:
            unstamped.append(Path(d).name)
            continue
        for key in seen:
            seen[key].setdefault(str(v.get(key)), []).append(Path(d).name)
    out = []
    for key, groups in seen.items():
        if len(groups) <= 1:
            continue
        # Name the MINORITY dirs: on a bake that rolled mid-run, those are
        # the pages to look at, and printing all 136 helps nobody.
        ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
        bits = []
        for value, names in ranked:
            shown = ', '.join(sorted(names)[:8])
            more = f' (+{len(names) - 8} more)' if len(names) > 8 else ''
            bits.append(f'{value} x{len(names)} [{shown}{more}]')
        out.append(f'MIXED {key} across this bake: ' + ' | '.join(bits))
    if unstamped:
        shown = ', '.join(sorted(unstamped)[:8])
        more = (f' (+{len(unstamped) - 8} more)' if len(unstamped) > 8 else '')
        out.append(f'no {VINTAGE_FILE} in {len(unstamped)} fresh dive dirs: '
                   f'{shown}{more}')
    return out


def load_resolutions() -> list[dict]:
    """Chain failures that were diagnosed, fixed, and re-verified by hand.

    A step can fail for a reason that is fully understood and already fixed
    in a later commit. But the chain log and overnight_status.txt are
    historical records, so every later run of this gate re-reports the same
    resolved failure. Editing either file to force green would falsify the
    gate; leaving it permanently red is how a *real* failure later gets
    waved off. So the resolution is recorded separately instead.

    Each entry is pinned to ONE chain log plus a step label, carries the
    fix commit and the re-verification evidence, and is PRINTED when it
    matches (as RSLV) rather than silently suppressing. It expires on its
    own: the next chain run writes a new log filename, which no existing
    entry names, so nothing is suppressed going forward.
    """
    if not RESOLUTIONS_FILE.exists():
        return []
    with RESOLUTIONS_FILE.open('rb') as fh:
        return tomllib.load(fh).get('resolution', [])


def match_resolution(resolutions: list[dict], log_name: str,
                     line: str) -> dict | None:
    for res in resolutions:
        if res['chain_log'] == log_name and res['step'] in line:
            return res
    return None


def stale_resolutions(resolutions: list[dict], log_name: str,
                      reported: list[str]) -> list[str]:
    """Entries naming THIS chain log that match none of its reported lines.

    A resolution that names the current log but matches nothing is a
    suppression rule nobody is checking -- a typo'd step label, or a step
    renamed out from under it. Entries naming other logs are simply spent.

    ``reported`` is every line check [1/5] reports, not just the ``[FAIL]``
    ones: the status line and both WARN scans are resolvable too, and keying
    staleness on the [FAIL] lines alone (as the id-collecting version did)
    reported an entry covering a which-build omission as stale -- red
    whether or not the dive behind it had been fixed and re-rendered.
    """
    out = []
    for res in resolutions:
        if res['chain_log'] != log_name:
            continue
        if not any(res['step'] in line for line in reported):
            out.append(f'stale resolution for {log_name}: step '
                       f'{res["step"]!r} matched no reported line')
    return out


def extract_opponents(html_path: Path) -> list[str] | None:
    content = html_path.read_text(errors='replace')
    i = content.find('"opponents": [')
    if i < 0:
        return None
    start = content.index('[', i)
    arr, _end = json.JSONDecoder().raw_decode(content[start:start + 200_000])
    return arr


def missing_pool_entries(opponents: list[str], pool_path: Path) -> list[str]:
    """Declared pool entries whose display name never reached the dive.

    deep_dive.py resolves each pool line's default moveset through
    get_default_moveset() and, on KeyError/ValueError, logs
    "skipping <name>: ..." and drops the entry (deep_dive.py:4145-4153).
    A species deranked out of a league's rankings file therefore vanishes
    from that league's opponent list with only a WARNING -- and no count
    check can catch it, because the mirror entry, TOML anchor opponents,
    atk-weighted variants and active_variants.toml all APPEND, absorbing
    several silent drops before any floor would trip.

    So the assertion is name-set containment, not a count: every display
    name the pool file declares must appear in DATA.opponents. Containment
    is rankings-free -- _parse_opponent_pool_line is pure string parsing
    plus analysis.pretty_name for move-ID overrides -- so it cannot
    self-drop the way a recomputed expected count would.

    Coverage caveat: this proves every DECLARED entry rendered; it does
    NOT prove the pool file is current. A species deranked out of PvPoke's
    rankings AND hand-removed from the pool file still passes. Keeping the
    pool file fresh is the pool-refresh workflow's job (see the header of
    opponent_pools/ul_top60.txt), not this gate's.

    Raises ValueError (from the parser) on a malformed pool line, or
    OSError (from read_text) when the declared pool file is unreadable --
    a renamed/moved opponents_file is exactly the drift this check exists
    to notice. The caller reports either as its own error rather than
    swallowing it, and rather than letting it abort the gate mid-step.
    """
    from deep_dive_lib.opponents import _parse_opponent_pool_line
    have = set(opponents)
    missing = []
    for raw in pool_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        display = _parse_opponent_pool_line(line)[0]
        if display not in have:
            missing.append(display)
    return missing


def missing_markers(opponents, markers) -> list[str]:
    """Markers that no opponent display name names.

    A rendered display name may carry a FORM qualifier, a MOVESET
    annotation, or both -- "Charjabug (Shadow)", "Forretress (Bug Bite)",
    "Forretress (Shadow) (Bug Bite)". A marker names a species AND its form,
    so it matches a name that is the marker exactly or extends it with
    further parentheticals.

    Pre-2026-09-22 this compared ``o.split(' (')[0] == m``, which strips the
    form qualifier along with the moveset. That worked only while every
    marker was a bare species name; the 09-22 marker refresh moved three of
    them to forms ('Charjabug (Shadow)', 'Forretress (Shadow)', 'Oinkologne
    (Female)'), which made them unmatchable, and the gate printed the same
    76 false "markers missing" lines the refresh was meant to clear.
    """
    return [m for m in markers
            if not any(o == m or o.startswith(m + ' (') for o in opponents)]


def dive_pool_map() -> dict[str, Path]:
    """slug -> opponents-file path, from run_website_dives' DIVES list.

    Every dive declares its own pool, so the completeness check is
    per-dive rather than per-league (all 97 DIVES entries carry an
    explicit `opponents_file` today; the `opponents: N` rankings-top-N
    branch is unused). Importing DIVES keeps this single-sourced, the
    way step 4 imports SHIP_GATES and step 5 imports run_iv_guides.
    """
    from run_website_dives import DIVES
    return {d['slug']: REPO / d['opponents_file']
            for d in DIVES if d.get('opponents_file')}


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
    resolutions = load_resolutions()
    log_name = log_path.name if log_path else ''
    reported: list[str] = []

    def report(line: str, err_label: str | None = None) -> None:
        """Print one failing line as RSLV (recorded resolution) or ERR.

        ``err_label`` prefixes the line in the verdict list; a line that
        already describes itself (the two WARN scans build their own) passes
        None. EVERY line that comes through here is resolvable -- a dive
        whose section was fixed and re-rendered by hand is exactly the case
        docs/chain_resolutions.toml exists for.
        """
        reported.append(line)
        res = match_resolution(resolutions, log_name, line)
        if res is None:
            errors.append(f'{err_label}: {line}' if err_label else line)
            print(f'  ERR {line}')
            return
        print(f'  RSLV {line}')
        print(f'       fixed in {res["fix_commit"]}: {res["reason"]}')
        print(f'       re-verified: {res["verified"]}')

    if STATUS_FILE.exists():
        # overnight_status.txt is a single scratch file rewritten by every
        # chain run, so its last line belongs to the newest chain log --
        # which is what lets one resolution entry cover both.
        last = STATUS_FILE.read_text().strip().splitlines()[-1]
        if 'SUCCESS' in last:
            print(f'  OK  status: {last}')
        else:
            report(last, 'chain status')
    else:
        errors.append('overnight_status.txt missing')
        print('  ERR overnight_status.txt missing')
    if log_path:
        log_text = log_path.read_text()
        fails = [ln.strip() for ln in log_text.splitlines()
                 if '[FAIL]' in ln]
        for ln in fails:
            report(ln, 'chain step failed')
        if not fails:
            print('  OK  no [FAIL] step lines')
        narr = scan_narrative_warnings(log_text)
        for ln in narr:
            report(ln)
        if not narr:
            print('  OK  no narrative-patch WARN lines')
        wb = scan_which_build_omissions(log_text)
        for ln in wb:
            report(ln)
        if not wb:
            print('  OK  no which-one-to-build omission lines')
        # Window = chain start .. the log's last write (the chain's end).
        from pmset_sleep import read_pmset_log
        verdict, msg = chain_sleep_report(
            read_pmset_log(), cutoff, log_path.stat().st_mtime)
        if verdict == 'ERR':
            report(msg)
        else:
            print(f'  {verdict:<3} {msg}')
        # Staleness is judged against every line reported above, so an entry
        # may cover any of them -- and is still flagged when it covers none.
        for msg in stale_resolutions(resolutions, log_name, reported):
            errors.append(msg)
            print(f'  ERR {msg}')

    # 2. Freshness ----------------------------------------------------
    # Cover league dives (`*-league`) AND limited-cup dives (`*-cup`) so a cup
    # dive neither trips the guard nor is silently missed (mixed-vintage is an
    # error for both). The GL-only marker/pool-sanity check below is gated on
    # 'great-league' in the dir name, so cup dirs skip it -- cup pools
    # legitimately lack the GL markers.
    print('[2/5] dive-dir freshness')
    fresh_dirs: list[Path] = []
    skipped = 0
    for d in sorted(WEBSITE.glob('*-league')) + sorted(WEBSITE.glob(CUP_DIR_GLOB)):
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

    # 2b. Build vintage -------------------------------------------------
    # mtimes above prove the FILES are of one run; these prove the DATA
    # behind them is of one vintage, which mtimes cannot see.
    vin = vintage_errors(fresh_dirs)
    for ln in vin:
        errors.append(ln)
        print(f'  ERR {ln}')
    if not vin and fresh_dirs:
        print('  OK  one engine + gamemaster vintage across all fresh dirs')

    # 3. Pool sanity --------------------------------------------------
    print('[3/5] pool sanity (markers: ' + ', '.join(args.markers) + ')')
    counts: dict[str, int] = {}
    try:
        pools = dive_pool_map()
    except Exception as e:
        pools = {}
        errors.append(f'DIVES pool map unreadable: {e}')
        print(f'  ERR cannot build DIVES pool map: {e}')
    contained = 0
    unmapped = 0
    for d in fresh_dirs:
        opps = extract_opponents(d / 'index.html')
        if opps is None:
            errors.append(f'{d.name}: no DATA.opponents found')
            print(f'  ERR {d.name}: no DATA.opponents found')
            continue
        counts[d.name] = len(opps)
        # Completeness: every entry the dive's own pool file declares must
        # have survived into DATA.opponents. Subsumes the GL marker check
        # below (all three markers are ordinary pool entries) and extends
        # it to UL/ML/cup, which had no pool guard at all.
        pool = pools.get(d.name)
        if pool is None:
            # Dead today (every dive dir maps to a DIVES slug with an
            # opponents_file), but stated out loud so an unmapped dive
            # -- e.g. one switched to the `opponents: N` top-N branch --
            # can never look covered when it is not.
            unmapped += 1
            print(f'  NOTE {d.name}: no DIVES pool mapping, '
                  f'completeness unchecked')
        else:
            try:
                gone = missing_pool_entries(opps, pool)
            # OSError as well as ValueError: a renamed/moved opponents_file
            # is drift this step should REPORT, not die on -- an uncaught
            # FileNotFoundError here aborts the whole gate mid-step, so
            # steps 4 and 5 never run and the morning check reports nothing.
            except (ValueError, OSError) as e:
                msg = f'{d.name}: pool {pool.name} unusable: {e}'
                errors.append(msg)
                print(f'  ERR {msg}')
            else:
                if gone:
                    msg = f'{d.name}: pool entries missing from dive: {gone}'
                    errors.append(msg)
                    print(f'  ERR {msg}')
                else:
                    contained += 1
        if 'great-league' in d.name:
            missing = missing_markers(opps, args.markers)
            if missing:
                errors.append(f'{d.name}: markers missing: {missing}')
                print(f'  ERR {d.name}: {len(opps)} opponents, '
                      f'missing {missing}')
    if contained:
        print(f'  OK  {contained} fresh dives contain every declared '
              f'pool entry')
    if unmapped:
        print(f'  NOTE {unmapped} fresh dives had no DIVES pool mapping')
    if counts:
        lo, hi = min(counts.values()), max(counts.values())
        print(f'  OK  opponent counts across {len(counts)} fresh dives: '
              f'{lo}..{hi}' if lo != hi else
              f'  OK  all {len(counts)} fresh dives: {lo} opponents')

    # 4. Ship gates ---------------------------------------------------
    # Roster imported from run_ship_gates (single source; entry 3b).
    print('[4/5] ship gates')
    from run_ship_gates import SHIP_GATES
    for gate, argv in SHIP_GATES:
        r = subprocess.run(
            [sys.executable, str(REPO / 'scripts' / gate), *argv],
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
