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

Usage:
  python scripts/patch_dive_gives_up_column.py            # all userdata/website dives
  python scripts/patch_dive_gives_up_column.py PATH ...
"""
import glob
import os
import sys

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deep_dive_engine.js')
VAR_HTML = "  var html = '';"
COMMENT = '// "Gives up vs #1"'


def _region_bounds(text):
    """(line_start_of_the_'Gives up vs #1'_comment, index_of_`var html = '';`)."""
    c = text.index(COMMENT)
    line_start = text.rfind('\n', 0, c) + 1
    return line_start, text.index(VAR_HTML, line_start)


_SRC = open(ENGINE).read()
_ls, _ve = _region_bounds(_SRC)
NEW_REGION = _SRC[_ls:_ve]

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


if __name__ == '__main__':
    main()
