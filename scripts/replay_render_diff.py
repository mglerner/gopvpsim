#!/usr/bin/env python
"""Byte-diff regression harness for the dive renderer (replay blobs -> HTML).

Every render-side change that is meant to be behavior-preserving (a perf
refactor, a dedup, a memo) must leave the rendered dive pages byte-identical.
This script re-renders a fixed set of saved replay blobs with THIS tree's
code and diffs every file the render emits against a stored baseline.

Subcommands
-----------
  baseline --out DIR [--blobs B ...] [--jobs N]
      Render each blob, store every emitted file under DIR/<label>/, snapshot
      the render's external inputs under DIR/inputs/, and write
      DIR/manifest.json (blob paths + sha256, git sha, dirty flag, per-file
      sha256, wall seconds and peak RSS per blob).

  check --baseline DIR --out DIR [--blobs B ...] [--normalize-ids] [--jobs N]
      Re-render the baseline's blobs (or the --blobs subset, given as labels
      like ``tinkaton_great`` or as blob paths) against the BASELINE's frozen
      inputs and diff every file. Prints ``<label>: IDENTICAL`` or
      ``<label>: DIFFERS`` per blob, with each differing file's first differing
      byte offset (in the normalized bytes) and a context snippet; a unified
      diff excerpt (first 40 lines, long lines clipped) goes to
      OUT/diffs/<label>/<file>.diff. Exit 0 iff every blob is IDENTICAL, 1 if
      anything differs (or a file is missing/extra), 2 on a usage/preflight
      error.

Run it from the tree whose code you want to test; it renders with the src/
and scripts/ next to this file. Typical agent loop:

    .venv/bin/python scripts/replay_render_diff.py check \\
        --baseline <scratch>/baselines/<sha> --out <scratch>/<label>/render \\
        --blobs tinkaton_great            # iterate on one blob
    ... then the full set (no --blobs) before each commit.

What a render covers
--------------------
Exactly ``deep_dive.render_dive_html(state)`` on the blob, i.e. what
``scripts/replay_analysis.py BLOB --html PATH`` does: every split-moveset
file (``index.html`` + ``index_m<i>_<slug>.html``), the which-build section,
the clusters section, the embedded dive card, the L51 best-buddy <template>
(active and no-op), and ``vintage.toml``. EVERY file that lands in the dive
directory is captured and compared, not just index.html.

Deliberately NOT covered:
  * The standalone dive card (``card_path``). It is forced to None, which is
    what every production blob carries (no chain script passes --card-out).
    Setting it would also run ``_compute_card_robustness`` -- an opponent-IV
    sim sweep, not render code -- and change the landing page's inline card.
  * ``shared_plotly_dir`` (forced None; the blobs carry None, standalone=True,
    so plotly is inlined from the frozen copy in inputs/).

Frozen inputs (so the diff sees code changes only)
--------------------------------------------------
The render reads live data beyond the blob: the PvPoke gamemaster and
rankings caches (their content hash and mtime are printed in the page
footer and in vintage.toml), sprites, the inlined plotly.min.js, and the
built articles' meta.toml. ``baseline`` snapshots them into DIR/inputs/
(copy2, mtimes preserved) and every render -- baseline and check alike --
reads the snapshot: ``gopvpsim.data.CACHE_DIR`` and
``deep_dive.PLOTLY_CACHE_DIR`` are repointed at it, and the render dir's
``website/articles`` is a symlink to the snapshot's articles/. Network
access is blocked in the render process (a sprite older than the cache TTL
falls back to its cached bytes, exactly as a failed refetch does in
production), and GOPVPSIM_PIN_DATA_CACHE=1 is set. So a refresh of the live
caches during the day can NOT make a check spuriously differ. Repo-tracked
inputs (thresholds/*.toml, the JS files) are code: a change to them is a
render change and SHOULD show up.

Each blob renders in its own fresh subprocess: the toggle-id counters
(below) are module globals that never reset, so rendering two blobs in one
process would make a blob's ids depend on what rendered before it.

Nondeterminism normalization (applied to BOTH sides before comparing)
---------------------------------------------------------------------
NORMALIZERS below is the complete list; each entry records why it exists.
Also normalized: the literal per-run paths of the render root and the
inputs dir (placeholders <RENDER_ROOT> / <INPUTS>; the page footer prints
the rankings cache file's path, which lives in inputs/). Verified
2026-09-25 at HEAD 4c20eae: two HEAD renders of all five default blobs
into different output dirs gave 25/25 HTML files byte-identical RAW, and
the five vintage.toml files differed only in rendered_at; the check
reported IDENTICAL. A negative control (baseline copy with one moveset
name edited and every toggle id shifted by 1000) reported DIFFERS on both
files in mode A and only on the content edit with --normalize-ids.

Cost (same verification, --jobs 5 on a machine shared with other agents):
render wall s / peak RSS per blob: tinkaton_great 238 / 4.9 GB,
jellicent_ultra 395 / 6.3 GB, guzzlord_great 923 / 5.5 GB, melmetal_great
360 / 4.9 GB, cramorant_ultra 579 / 11.6 GB; 5 blobs ~15.5 min wall at
--jobs 5 (~42 min serial). Mind RSS before raising --jobs.

--normalize-ids (mode B)
------------------------
The dive's no-JS "+N more" expanders get page-unique ids from two
module-global counters that are never reset:
    deep_dive_rendering._flip_toggle_seq -> ids 'flip<N>', 'fdet<N>'
    deep_dive_card._toggle_seq           -> ids 'sb<N>',   'cm<N>'
(markup from deep_dive_rendering.cover_toggle_html: id="X" on the checkbox,
for="X" on its label). So a change that skips or reorders a render pass
(e.g. the no-op best-buddy pass 2) renumbers every later id, including in
the NEXT split file. With --normalize-ids, each file is canonicalized
independently: every ``id="P<N>"`` / ``for="P<N>"`` attribute (also with
backslash-escaped quotes) whose value is one of the prefixes above plus
digits is renamed to ``P<k>``, where k is the 1-based order in which that
exact original value first appears in the file, counted separately per
prefix. Consequences: a page that only renumbered compares equal; a
duplicated id (a real bug) still differs, because its two uses collapse to
one canonical value while the reference page's stay distinct; any other
byte change still differs. The per-file count of canonicalized ids is
printed so a vacuous pass (zero ids found) is visible.
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TREE = Path(__file__).resolve().parent.parent
REPO_USERDATA = TREE / 'userdata'

# Newest blob per key in userdata/replay/ as of 2026-09-25. The three GL
# blobs are best-buddy NO-OP dives (state['best_buddy']['noop'] is True and
# every moveset's scores_l51 IS its scores); the two UL blobs are active
# best-buddy dives. Resolved against the MAIN clone's userdata/ (blobs are
# not in git), so a worktree run finds them too.
DEFAULT_BLOBS = [
    '20260920_180117_Tinkaton_great.replay.pkl.gz',    # GL, bb no-op
    '20260921_165157_Jellicent_ultra.replay.pkl.gz',   # UL, bb active
    '20260921_050704_Guzzlord_great.replay.pkl.gz',    # GL, bb no-op
    '20260920_164604_Melmetal_great.replay.pkl.gz',    # GL, bb no-op
    '20260921_191707_Cramorant_ultra.replay.pkl.gz',   # UL, bb active, article link
]
MAIN_CLONE = Path('/Users/mglerner/coding/gopvpsim')
MARKER = '.replay_render_diff'

# (name, pattern, replacement, why). Bytes regexes, applied in order.
# RENDER_ROOT / INPUTS placeholders are handled separately (they are
# per-run literal paths, not patterns) -- see normalize().
NORMALIZERS = [
    ('vintage_rendered_at',
     rb'(rendered_at\s*=\s*")[0-9T:\-]+(")',
     rb'\1<RENDERED_AT>\2',
     'vintage.toml stamps datetime.now() at render time '
     '(deep_dive.write_vintage_stamp).'),
]
_NORMALIZERS_RE = [(n, re.compile(p), r, why) for n, p, r, why in NORMALIZERS]

# Counter-based toggle-id prefixes (see module docstring, --normalize-ids).
ID_PREFIXES = ('flip', 'fdet', 'sb', 'cm')
_ID_RE = re.compile(
    rb'(\b(?:id|for)=\\?")(' + b'|'.join(p.encode() for p in ID_PREFIXES)
    + rb')(\d+)(\\?")')

DIFF_EXCERPT_LINES = 40
DIFF_LINE_CLIP = 400


# --------------------------------------------------------------------------
# Pure helpers (pinned by tests/test_replay_render_diff.py)
# --------------------------------------------------------------------------

def normalize(data, placeholders=()):
    """Apply the documented nondeterminism normalization to ``data`` (bytes).

    ``placeholders`` is a sequence of (literal_path_str, token) pairs: each
    literal occurrence of the path is replaced by the token (used for the
    per-run render root and inputs dir, which differ between baseline and
    check by construction). Longer paths are replaced first.
    """
    for lit, tok in sorted(placeholders, key=lambda p: -len(p[0])):
        if lit:
            data = data.replace(lit.encode(), tok.encode())
    for _name, rx, rep, _why in _NORMALIZERS_RE:
        data = rx.sub(rep, data)
    return data


def canonicalize_ids(data):
    """Renumber counter-based toggle ids in document order (per prefix).

    Returns ``(new_bytes, n_distinct_ids)``. See the module docstring for
    the exact semantics.
    """
    mapping = {}
    per_prefix = {}

    def _sub(m):
        pre, num = m.group(2), m.group(3)
        key = pre + num
        if key not in mapping:
            per_prefix[pre] = per_prefix.get(pre, 0) + 1
            mapping[key] = pre + str(per_prefix[pre]).encode()
        return m.group(1) + mapping[key] + m.group(4)

    return _ID_RE.sub(_sub, data), len(mapping)


def first_diff_offset(a, b):
    """Index of the first differing byte, len of the shorter if one is a
    prefix of the other, or None if equal."""
    if a == b:
        return None
    n = min(len(a), len(b))
    # Chunked compare so multi-MB pages do not walk byte-by-byte in Python.
    step = 1 << 16
    i = 0
    while i < n and a[i:i + step] == b[i:i + step]:
        i += step
    for j in range(i, min(i + step, n)):
        if a[j] != b[j]:
            return j
    return n


def _clip(line, limit=DIFF_LINE_CLIP):
    if len(line) <= limit:
        return line
    return line[:limit] + f'...[+{len(line) - limit} chars]'


def diff_excerpt(a, b, name_a='baseline', name_b='check',
                 max_lines=DIFF_EXCERPT_LINES, context=3, window=400):
    """Unified-diff excerpt (at most ``max_lines`` lines) of two byte strings,
    starting near their first differing line. Only a window of ``window``
    lines from each side is handed to difflib, so a page whose every line
    differs cannot make this quadratic."""
    la = a.decode('utf-8', 'replace').splitlines()
    lb = b.decode('utf-8', 'replace').splitlines()
    i = 0
    while i < len(la) and i < len(lb) and la[i] == lb[i]:
        i += 1
    lo = max(0, i - context)
    wa, wb = la[lo:lo + window], lb[lo:lo + window]
    out = []
    for line in difflib.unified_diff(wa, wb, name_a, name_b, lineterm='',
                                     n=context):
        if line.startswith('@@'):
            # Re-base hunk line numbers onto the full files.
            line = re.sub(r'-(\d+)', lambda m: f'-{int(m.group(1)) + lo}',
                          line, count=1)
            line = re.sub(r'\+(\d+)', lambda m: f'+{int(m.group(1)) + lo}',
                          line, count=1)
        out.append(_clip(line))
        if len(out) >= max_lines:
            break
    return out


def blob_label(blob):
    """'20260920_180117_Tinkaton_great.replay.pkl.gz' -> 'tinkaton_great'."""
    name = Path(blob).name
    for suf in ('.replay.pkl.gz', '.pkl.gz', '.gz'):
        if name.endswith(suf):
            name = name[:-len(suf)]
            break
    parts = name.split('_')
    if len(parts) > 2 and parts[0].isdigit() and parts[1].isdigit():
        parts = parts[2:]
    return '_'.join(parts).lower()


# --------------------------------------------------------------------------
# Render child (one blob per fresh process)
# --------------------------------------------------------------------------

def _block_network():
    import socket

    def _blocked(*a, **k):
        raise OSError('network blocked by replay_render_diff')
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked


def _render_one(args):
    import resource
    os.environ['GOPVPSIM_PIN_DATA_CACHE'] = '1'
    os.environ.pop('DUMP_SYNTH_STATE', None)
    _block_network()
    sys.path.insert(0, str(TREE / 'src'))
    sys.path.insert(0, str(TREE / 'scripts'))
    inputs = Path(args.inputs)
    render_dir = Path(args.render_dir)

    import gopvpsim.data as gd
    orig_cache = gd.CACHE_DIR
    new_cache = inputs / 'data_cache'
    gd.CACHE_DIR = new_cache
    import deep_dive
    from deep_dive_logging import init_logger
    deep_dive.PLOTLY_CACHE_DIR = inputs / 'plotly'
    # Any module that did `from gopvpsim.data import CACHE_DIR` holds the
    # old Path object by value; repoint those too.
    for m in list(sys.modules.values()):
        d = getattr(m, '__dict__', None)
        if isinstance(d, dict):
            for k, v in list(d.items()):
                if v is orig_cache:
                    setattr(m, k, new_cache)

    state = deep_dive.load_replay_state(args.blob)
    state['replay_blob_path'] = os.path.abspath(args.blob)
    init_logger(state['species'], state['league'],
                shadow=state.get('shadow', False),
                log_file=str(render_dir / 'render.log'))
    orig_html = Path(state['html_path'])
    website = render_dir / 'website'
    dive_dir = website / orig_html.parent.name
    dive_dir.mkdir(parents=True, exist_ok=True)
    (website / 'articles').symlink_to(inputs / 'articles')
    state['html_path'] = str(dive_dir / orig_html.name)
    state['card_path'] = None
    state['shared_plotly_dir'] = None
    t0 = time.perf_counter()
    deep_dive.render_dive_html(state)
    wall = time.perf_counter() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = rss / (1024 * 1024) if sys.platform == 'darwin' else rss / 1024
    (render_dir / 'result.json').write_text(json.dumps({
        'dive_dir': dive_dir.name,
        'render_wall_s': round(wall, 1),
        'peak_rss_mb': round(rss_mb),
        'bb_noop': bool((state.get('best_buddy') or {}).get('noop')),
    }))


# --------------------------------------------------------------------------
# Parent orchestration
# --------------------------------------------------------------------------

def _die(msg):
    print(f'replay_render_diff: {msg}', file=sys.stderr)
    sys.exit(2)


def _check_out_dir(out):
    out = Path(out).resolve()
    for forbidden in (TREE.resolve(), MAIN_CLONE.resolve()):
        if out == forbidden or forbidden in out.parents:
            _die(f'--out {out} is inside the repo ({forbidden}); '
                 'use a scratch dir outside it (never userdata/)')
    if out.exists() and any(out.iterdir()) and not (out / MARKER).exists():
        _die(f'--out {out} exists, is non-empty and was not created by '
             'this script; refusing to write into it')
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text('owned by scripts/replay_render_diff.py\n')
    return out


def _resolve_blob(b):
    p = Path(b)
    if p.exists():
        return p.resolve()
    for root in (TREE, MAIN_CLONE):
        q = root / 'userdata' / 'replay' / b
        if q.exists():
            return q.resolve()
    _die(f'blob not found: {b}')


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _git(*args):
    try:
        return subprocess.run(['git', '-C', str(TREE), *args],
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _snapshot_inputs(inputs):
    """Copy the render's live external inputs into ``inputs`` (baseline)."""
    sys.path.insert(0, str(TREE / 'src'))
    import gopvpsim.data as gd
    shutil.copytree(gd.CACHE_DIR, inputs / 'data_cache', symlinks=True,
                    copy_function=shutil.copy2)
    plotly = Path.home() / '.cache' / 'gopvpsim' / 'plotly-2.35.2.min.js'
    src_text = (TREE / 'scripts' / 'deep_dive.py').read_text()
    m = re.search(r'^PLOTLY_FILENAME = "([^"]+)"', src_text, re.M)
    if m:
        plotly = plotly.with_name(m.group(1))
    if not plotly.exists():
        _die(f'plotly cache {plotly} missing; a render would download it')
    (inputs / 'plotly').mkdir(parents=True)
    shutil.copy2(plotly, inputs / 'plotly' / plotly.name)
    arts_src = MAIN_CLONE / 'userdata' / 'website' / 'articles'
    arts = inputs / 'articles'
    arts.mkdir(parents=True)
    n = 0
    if arts_src.is_dir():
        for d in sorted(arts_src.iterdir()):
            if d.is_dir():
                (arts / d.name).mkdir()
                if (d / 'meta.toml').exists():
                    shutil.copy2(d / 'meta.toml', arts / d.name / 'meta.toml')
                    n += 1
    return {'data_cache_from': str(gd.CACHE_DIR), 'plotly_from': str(plotly),
            'articles_from': str(arts_src), 'articles_meta_copied': n}


def _launch(blob, render_dir, inputs):
    if render_dir.exists():
        shutil.rmtree(render_dir)
    render_dir.mkdir(parents=True)
    env = dict(os.environ, GOPVPSIM_PIN_DATA_CACHE='1')
    env.pop('DUMP_SYNTH_STATE', None)
    cmd = [sys.executable, str(Path(__file__).resolve()), '_render-one',
           '--blob', str(blob), '--render-dir', str(render_dir),
           '--inputs', str(inputs)]
    log = open(render_dir / 'child_stdout.log', 'w')
    t0 = time.time()
    proc = subprocess.Popen(cmd, env=env, stdout=log,
                            stderr=subprocess.STDOUT)
    return proc, log, t0


def _collect(render_dir):
    """Map relpath -> Path of every emitted file in the dive dir."""
    res = json.loads((render_dir / 'result.json').read_text())
    dive = render_dir / 'website' / res['dive_dir']
    files = {str(p.relative_to(dive)): p
             for p in sorted(dive.rglob('*')) if p.is_file()}
    return res, dive, files


def _run_renders(jobs_list, jobs, inputs):
    """jobs_list: [(label, blob, render_dir)]. Returns {label: (res, files)}.
    Dies (exit 2) if any render process fails."""
    pending = list(jobs_list)
    running = []
    out = {}
    failed = []
    while pending or running:
        while pending and len(running) < jobs:
            label, blob, rdir = pending.pop(0)
            print(f'  rendering {label} ...', flush=True)
            running.append((label, rdir) + _launch(blob, rdir, inputs))
        still = []
        for label, rdir, proc, log, t0 in running:
            if proc.poll() is None:
                still.append((label, rdir, proc, log, t0))
                continue
            log.close()
            wall = time.time() - t0
            if proc.returncode != 0:
                failed.append(label)
                tail = (rdir / 'child_stdout.log').read_text()[-3000:]
                print(f'  {label}: RENDER FAILED (exit {proc.returncode})\n'
                      f'{tail}', flush=True)
                continue
            res, dive, files = _collect(rdir)
            res['process_wall_s'] = round(wall, 1)
            out[label] = (res, files)
            print(f'  {label}: rendered {len(files)} files in {wall:.1f}s '
                  f'(render {res["render_wall_s"]}s, peak RSS '
                  f'{res["peak_rss_mb"]} MB)', flush=True)
        running = still
        if running:
            time.sleep(0.5)
    if failed:
        _die(f'render failed for: {", ".join(failed)}')
    return out


def cmd_baseline(a):
    out = _check_out_dir(a.out)
    blobs = [_resolve_blob(b) for b in (a.blobs or DEFAULT_BLOBS)]
    inputs = out / 'inputs'
    if inputs.exists():
        shutil.rmtree(inputs)
    inputs.mkdir()
    snap = _snapshot_inputs(inputs)
    jobs_list = [(blob_label(b), b, out / blob_label(b)) for b in blobs]
    t0 = time.time()
    rendered = _run_renders(jobs_list, a.jobs, inputs)
    manifest = {
        'created': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'git_sha': _git('rev-parse', 'HEAD'),
        'git_dirty_paths': (_git('status', '--porcelain') or '').splitlines(),
        'tree': str(TREE),
        'inputs': snap,
        'normalizers': [n for n, *_ in NORMALIZERS],
        'total_wall_s': round(time.time() - t0, 1),
        'jobs': a.jobs,
        'blobs': {},
    }
    for label, blob, rdir in jobs_list:
        res, files = rendered[label]
        manifest['blobs'][label] = {
            'blob': str(blob),
            'blob_sha256': _sha256_file(blob),
            'dive_dir': res['dive_dir'],
            'bb_noop': res['bb_noop'],
            'render_wall_s': res['render_wall_s'],
            'process_wall_s': res['process_wall_s'],
            'peak_rss_mb': res['peak_rss_mb'],
            'files': {rel: {'bytes': p.stat().st_size,
                            'sha256': _sha256_file(p)}
                      for rel, p in files.items()},
        }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print(f'baseline written to {out} ({manifest["total_wall_s"]}s)')
    for label, e in manifest['blobs'].items():
        print(f'  {label}: {len(e["files"])} files, render '
              f'{e["render_wall_s"]}s, peak RSS {e["peak_rss_mb"]} MB')
    return 0


def _select(manifest, wanted):
    labels = list(manifest['blobs'])
    if not wanted:
        return labels
    sel = []
    for w in wanted:
        lab = w if w in labels else blob_label(w)
        if lab not in labels:
            _die(f'--blobs {w!r} is not in the baseline '
                 f'(have: {", ".join(labels)})')
        sel.append(lab)
    return sel


def cmd_check(a):
    base = Path(a.baseline).resolve()
    mf = base / 'manifest.json'
    if not mf.exists():
        _die(f'no manifest.json in {base}')
    out = _check_out_dir(a.out)
    if out == base:
        _die('--out must differ from --baseline')
    manifest = json.loads(mf.read_text())
    labels = _select(manifest, a.blobs)
    inputs = base / 'inputs'
    jobs_list = []
    for lab in labels:
        blob = Path(manifest['blobs'][lab]['blob'])
        if not blob.exists():
            _die(f'baseline blob missing: {blob}')
        jobs_list.append((lab, blob, out / lab))
    head = _git('rev-parse', 'HEAD')
    print(f'check: tree {TREE} @ {head} vs baseline '
          f'{manifest.get("git_sha")} ({len(labels)} blob(s))')
    rendered = _run_renders(jobs_list, a.jobs, inputs)
    diffs_root = out / 'diffs'
    if diffs_root.exists():
        shutil.rmtree(diffs_root)
    all_ok = True
    for lab in labels:
        entry = manifest['blobs'][lab]
        res, files = rendered[lab]
        bdive = base / lab / 'website' / entry['dive_dir']
        cdive = out / lab / 'website' / res['dive_dir']
        ph_b = [(str(base / lab), '<RENDER_ROOT>'),
                (os.path.realpath(base / lab), '<RENDER_ROOT>'),
                (str(inputs), '<INPUTS>'),
                (os.path.realpath(inputs), '<INPUTS>')]
        ph_c = [(str(out / lab), '<RENDER_ROOT>'),
                (os.path.realpath(out / lab), '<RENDER_ROOT>'),
                (str(inputs), '<INPUTS>'),
                (os.path.realpath(inputs), '<INPUTS>')]
        bnames = set(entry['files'])
        cnames = set(files)
        problems = []
        for rel in sorted(bnames - cnames):
            problems.append(f'    MISSING in check: {rel}')
        for rel in sorted(cnames - bnames):
            problems.append(f'    EXTRA in check:   {rel}')
        id_notes = []
        for rel in sorted(bnames & cnames):
            ba = normalize((bdive / rel).read_bytes(), ph_b)
            ca = normalize((cdive / rel).read_bytes(), ph_c)
            if a.normalize_ids:
                ba, nb = canonicalize_ids(ba)
                ca, nc = canonicalize_ids(ca)
                id_notes.append(f'{rel}: {nb}/{nc} ids')
            off = first_diff_offset(ba, ca)
            if off is None:
                continue
            lo = max(0, off - 60)
            problems.append(
                f'    {rel}: first differing byte at offset {off:,} '
                f'(baseline {len(ba):,} B, check {len(ca):,} B)\n'
                f'      baseline: {ba[lo:off + 60]!r}\n'
                f'      check:    {ca[lo:off + 60]!r}')
            dpath = diffs_root / lab / (rel + '.diff')
            dpath.parent.mkdir(parents=True, exist_ok=True)
            dpath.write_text('\n'.join(diff_excerpt(
                ba, ca, f'baseline/{rel}', f'check/{rel}')) + '\n')
            problems.append(f'      diff excerpt: {dpath}')
        status = 'DIFFERS' if problems else 'IDENTICAL'
        all_ok &= not problems
        print(f'{lab}: {status} ({len(cnames)} files; render '
              f'{res["render_wall_s"]}s vs baseline {entry["render_wall_s"]}s)')
        if a.normalize_ids:
            print('    --normalize-ids canonicalized (baseline/check): '
                  + '; '.join(id_notes))
        for p in problems:
            print(p)
    print('RESULT:', 'IDENTICAL' if all_ok else 'DIFFERS')
    return 0 if all_ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split('\n')[0],
        epilog='See the module docstring (top of this file) for what '
               'is covered, the frozen inputs, the normalization list and '
               'the exact --normalize-ids semantics.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('baseline', help='render blobs and store a baseline')
    b.add_argument('--out', required=True, help='baseline dir (outside repo)')
    b.add_argument('--blobs', nargs='+', help='blob paths or names in '
                   'userdata/replay/ (default: the five DEFAULT_BLOBS)')
    b.add_argument('--jobs', type=int, default=1,
                   help='blobs rendered concurrently (default 1; each '
                        'render peaks at several GB RSS)')
    c = sub.add_parser('check', help='re-render and byte-diff vs a baseline')
    c.add_argument('--baseline', required=True)
    c.add_argument('--out', required=True, help='check dir (outside repo)')
    c.add_argument('--blobs', nargs='+',
                   help='subset, as labels (tinkaton_great) or blob paths')
    c.add_argument('--normalize-ids', action='store_true',
                   help='mode B: canonicalize counter-based toggle ids')
    c.add_argument('--jobs', type=int, default=1)
    r = sub.add_parser('_render-one', help='internal: one blob per process')
    r.add_argument('--blob', required=True)
    r.add_argument('--render-dir', required=True)
    r.add_argument('--inputs', required=True)
    a = ap.parse_args(argv)
    if a.cmd == '_render-one':
        _render_one(a)
        return 0
    os.environ['GOPVPSIM_PIN_DATA_CACHE'] = '1'
    if a.jobs < 1:
        _die('--jobs must be >= 1')
    return cmd_baseline(a) if a.cmd == 'baseline' else cmd_check(a)


if __name__ == '__main__':
    sys.exit(main())
