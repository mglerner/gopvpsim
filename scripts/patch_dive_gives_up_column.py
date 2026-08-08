#!/usr/bin/env python
"""Sync the "Gives up vs #1" collection column in already-rendered deep-dive
HTML to the CURRENT scripts/deep_dive_engine.js, in place (no re-sim).

The engine JS is inlined per-dive at render time, so a source change never
reaches published dives. This brings the column up to date by swapping four
placeholder-free regions to match the current source:

  1. the column helper region (the '// "Gives up vs #1"' block through just
     before `var html = '';`),
  2. the two `extras` header refs ('Gives up vs #1' -> givesUpHeader),
  3. renderSection's header escaping (adds the `\\n`->`<br>` wrap),
  4. updateView's collection-refresh hook (adds renderMatchesList()).

These regions contain none of the engine's per-dive placeholders, so the
per-dive substitutions elsewhere are untouched. Idempotent (skips dives whose
column already matches, detected via `_guMode`), apply-all-or-skip, and reports
files whose column predates this scheme (re-render those).

TWO staleness guards, because the region is copied VERBATIM into HTML this
script never re-renders:

  * `REGION_DEPS` -- the region calls helpers defined OUTSIDE it. A target page
    whose inlined engine predates one of them would be patched into calling an
    undefined function, which throws and kills the whole collection table.
    Such targets are skipped and reported.
  * `REGION_SHA256` -- a pin on the region's current source text. Editing the
    region in deep_dive_engine.js breaks the pin, and the script refuses to run
    until a maintainer re-reads the region, brings `REGION_DEPS` back in line
    with the helpers it now calls, and re-stamps the hash. Without the pin the
    dependency list silently rots as the region grows.

Usage:
  python scripts/patch_dive_gives_up_column.py            # all userdata/website dives
  python scripts/patch_dive_gives_up_column.py PATH ...
"""
import glob
import hashlib
import os
import sys

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deep_dive_engine.js')
VAR_HTML = "  var html = '';"
COMMENT = '// "Gives up vs #1"'

# Every helper the copied region calls but does NOT define, keyed by the
# DEFINITION text that must already be present in the target HTML (both
# deep_dive_engine.js and cmp_panels.js are inlined verbatim into a dive, so a
# plain substring test is exact). Two of these landed AFTER dives were
# published -- scenLabel (engine.js, DRY review 2026-08-05 entry 5) and isWin
# (cmp_panels.js, the WIN_RATING single-sourcing) -- which is precisely the
# hazard this list exists to catch. Re-derive it whenever REGION_SHA256 trips.
REGION_DEPS = {
    'scenLabel': 'function scenLabel(',
    'shortName': 'function shortName(',
    'getScores': 'function getScores(',
    'getActiveScenarioIndices': 'function getActiveScenarioIndices(',
    'selectedOppSet': 'function selectedOppSet(',
    'isWin': 'function isWin(',
}

# sha256 of NEW_REGION as of the last hand-verification of REGION_DEPS above.
REGION_SHA256 = '6ff2edb4fde643f86e871eada738792638068f7bbdd506a8ef422da178163b30'


def _region_bounds(text):
    """(line_start_of_the_'Gives up vs #1'_comment, index_of_`var html = '';`)."""
    c = text.index(COMMENT)
    line_start = text.rfind('\n', 0, c) + 1
    return line_start, text.index(VAR_HTML, line_start)


_SRC = open(ENGINE).read()
_ls, _ve = _region_bounds(_SRC)
NEW_REGION = _SRC[_ls:_ve]
REGION_HASH = hashlib.sha256(NEW_REGION.encode()).hexdigest()

# Out-of-region transforms (old -> new). The header swap hits both refs; the
# other two are single-occurrence lines.
HEADER_OLD = "header: 'Gives up vs #1',"
HEADER_NEW = "header: givesUpHeader,"
ESC_OLD = "escapeHtml(extras[xh].header)"
ESC_NEW = "escapeHtml(extras[xh].header).replace(/\\n/g, '<br>')"
UPDATE_OLD = "  origOpacities = traces.map(function(t) { return t.marker.opacity; });"
UPDATE_NEW = (UPDATE_OLD +
              "\n  // Refresh the collection table so the \"Gives up vs #1\" column tracks the"
              "\n  // y-axis / opp-IV / moveset selection (no-op when no collection is loaded)."
              "\n  renderMatchesList();")


def targets(argv):
    return argv or glob.glob(os.path.join('userdata', 'website', '*', 'index*.html'))


def main():
    if REGION_HASH != REGION_SHA256:
        print(f"REFUSING to patch: the '{COMMENT}' region in "
              f"{os.path.basename(ENGINE)} has changed since this script was "
              f"last verified.\n"
              f"  pinned: {REGION_SHA256}\n  actual: {REGION_HASH}\n"
              "Re-read the region, update REGION_DEPS to list every helper it "
              "calls that is defined OUTSIDE it, then set REGION_SHA256 to the "
              "actual hash above.", file=sys.stderr)
        return 1
    files = targets(sys.argv[1:])
    upgraded = current = skipped = 0
    for path in sorted(files):
        try:
            html = open(path).read()
        except OSError:
            continue
        if '_guMode' in html:
            current += 1
            continue
        if (COMMENT not in html or VAR_HTML not in html
                or HEADER_OLD not in html or ESC_OLD not in html
                or UPDATE_OLD not in html):
            if 'renderMatchesList' in html:
                skipped += 1
                print(f"skip (column predates this scheme): {path}")
            continue
        # The region is copied verbatim, so every helper it calls from outside
        # itself must already exist on this page or the patched column throws.
        missing = sorted(n for n, sig in REGION_DEPS.items() if sig not in html)
        if missing:
            skipped += 1
            print(f"skip (page predates {', '.join(missing)}; re-render "
                  f"instead): {path}")
            continue
        ls, ve = _region_bounds(html)
        html = html[:ls] + NEW_REGION + html[ve:]
        html = html.replace(HEADER_OLD, HEADER_NEW)       # both header refs
        html = html.replace(ESC_OLD, ESC_NEW, 1)
        html = html.replace(UPDATE_OLD, UPDATE_NEW, 1)
        open(path, 'w').write(html)
        upgraded += 1
        print(f"upgraded {path}")
    print(f"\n{len(files)} file(s): {upgraded} upgraded, {current} already current, "
          f"{skipped} skipped.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
