#!/usr/bin/env python3
"""
In-place patch of the embedded engine JS inside generated dive HTMLs.

Generation of a full dive takes many minutes; when a bug is found in
``scripts/deep_dive_engine.js`` that only affects rendering (and not
the underlying sim data), this script reproduces the placeholder
substitution that ``_interactive_js_engine`` does and swaps the
engine <script> block in-place for each dive HTML passed on the
command line.

Only the engine script block is replaced. The data blobs
(DATA / SCORES_B64), the user-collection module, and the analysis
HTML remain unchanged, so the output file size and the underlying
results are preserved exactly.

Usage::

    python scripts/patch_dive_engine.py path/to/dive1.html path/to/dive2.html

Exit code is non-zero if any file couldn't be patched.
"""
import json
import os
import re
import sys


def _subs_from_data(data):
    """Reproduce the placeholder substitution dict from
    ``_interactive_js_engine`` using values read back out of the HTML's
    embedded DATA blob. Keeps the patcher independent of the dive's
    original generation command line."""
    tiers = data.get('tiers', []) or []
    tier_colors_js = json.dumps([t.get('color', '#888') for t in tiers])
    tier_names_js = json.dumps([t.get('name', '?') for t in tiers])
    n_scenarios = data.get('nScenarios', 1)
    scenario_mode_default = '"avg"' if n_scenarios > 1 else '"0"'
    scenarios = data.get('scenarios', [[1, 1]])
    s0, s1 = scenarios[0] if scenarios else (1, 1)
    shield_desc_default = f'{s0}v{s1}'
    league_title = data.get('league', 'great').title()
    league_cp_cap = data.get('cpCap', 1500)
    opp_desc = data.get('opponentLabel', 'PvPoke rankings').replace("'", "\\'")
    opp_iv_modes = data.get('oppIvModes', ['pvpoke']) or ['pvpoke']
    opp_iv_mode_default = opp_iv_modes[0]
    return {
        '__SCENARIO_MODE_DEFAULT__': scenario_mode_default,
        '__OPP_IV_MODE_DEFAULT__':   opp_iv_mode_default,
        '__TIER_COLORS_JS__':        tier_colors_js,
        '__TIER_NAMES_JS__':         tier_names_js,
        '__SHIELD_DESC_DEFAULT__':   shield_desc_default,
        '__LEAGUE_TITLE__':          league_title,
        '__LEAGUE_CP_CAP__':         str(league_cp_cap),
        '__OPP_DESC_ESCAPED__':      opp_desc,
    }


def patch_one(html_path, engine_src):
    """Patch a single dive HTML in-place. Returns True on success."""
    with open(html_path) as f:
        html = f.read()

    m = re.search(r'var DATA = (\{.*?\});\n', html)
    if not m:
        print(f'  SKIP {html_path}: no DATA blob found', file=sys.stderr)
        return False
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        print(f'  SKIP {html_path}: DATA blob unparseable ({e})', file=sys.stderr)
        return False

    subs = _subs_from_data(data)
    new_engine = engine_src
    for k, v in subs.items():
        new_engine = new_engine.replace(k, v)

    # Find the script block containing buildHoverText (the engine).
    script_re = re.compile(r'<script>(.*?)</script>', re.DOTALL)
    matches = list(script_re.finditer(html))
    engine_idx = None
    for i, sm in enumerate(matches):
        if 'buildHoverText' in sm.group(1):
            engine_idx = i
            break
    if engine_idx is None:
        print(f'  SKIP {html_path}: engine block not found', file=sys.stderr)
        return False

    old_m = matches[engine_idx]
    new_html = (html[:old_m.start()] +
                '<script>\n' + new_engine + '\n</script>' +
                html[old_m.end():])

    with open(html_path, 'w') as f:
        f.write(new_html)
    size = os.path.getsize(html_path)
    print(f'  patched {os.path.basename(html_path)}: {size:,} bytes')
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    engine_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'deep_dive_engine.js',
    )
    with open(engine_path) as f:
        engine_src = f.read()

    failures = 0
    for arg in sys.argv[1:]:
        if not os.path.isfile(arg):
            print(f'  SKIP {arg}: not a file', file=sys.stderr)
            failures += 1
            continue
        ok = patch_one(arg, engine_src)
        if not ok:
            failures += 1
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
