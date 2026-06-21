#!/usr/bin/env python
"""Patch the "Gives up vs #1" collection column into already-rendered deep-dive
HTML in place.

The deep-dive engine JS is inlined verbatim into each rendered HTML at build
time, so editing scripts/deep_dive_engine.js does NOT update published dives.
This applies the same three insertions (the _cellGivesUp helper + the column in
the per-tier and Slayer collection sections) directly to each HTML's inlined
engine, matching the exact anchor strings.

Apply-all-or-skip per file: a file is patched only if all three anchors are
present (so the column wiring can never reference an undefined helper).
Idempotent (skips files already containing _cellGivesUp). Files whose inlined
engine predates the anchors are reported as skipped -- re-render those if wanted.

Usage:
  python scripts/patch_dive_gives_up_column.py                # all userdata/website dives
  python scripts/patch_dive_gives_up_column.py PATH ...       # specific HTML files
"""
import glob
import os
import sys

# --- The helper block (valid JS; need not byte-match the source, just be
# correct). Inserted right before `var html = '';` in renderMatchesList. ---
HELPER = r'''  // "Gives up vs #1": the collection-table version of the IV-guide "what you
  // give up" breakdown -- matchups the rank-1 spread wins but this owned IV
  // loses, over the selected shield scenarios. Reuses the scatter hover's
  // SCORES indexing (score >= 500 = win). On-grid only; off-grid '-'.
  var HELP_GIVES_UP = 'Matchups the rank-1 (stat-product #1) IV wins but this ' +
    'one loses, over the selected shield scenarios. Hover the number to list ' +
    'them. "0" = gives up nothing; "-" = off-grid IV (not simulated).';
  function _cellGivesUp(rc) {
    var iv = rc.canonicalIvIdx;
    if (iv == null || iv < 0) return '-';
    var refIv = (DATA.rank1RefIvIdx != null && DATA.rank1RefIvIdx >= 0)
                ? DATA.rank1RefIvIdx : DATA.pvpokeRefIvIdx;
    if (refIv == null || refIv < 0) return '-';
    if (iv === refIv) return '<span style="color:#9be89b">rank-1</span>';
    var scores = getScores(state.movesetIdx, state.oppIvMode);
    if (!scores) return '-';
    var sis = getActiveScenarioIndices();
    var lost = [];
    for (var gk = 0; gk < sis.length; gk++) {
      var gsi = sis[gk];
      var gsc = DATA.scenarios[gsi];
      var glab = gsc[0] + 'v' + gsc[1];
      for (var goi = 0; goi < nO; goi++) {
        var refW = scores[refIv * nS * nO + gsi * nO + goi] >= 500;
        var myW = scores[iv * nS * nO + gsi * nO + goi] >= 500;
        if (refW && !myW) lost.push(shortName(DATA.opponents[goi]) + ' ' + glab);
      }
    }
    if (lost.length === 0) return '<span style="color:#9be89b">0</span>';
    var gCap = 14;
    var gShown = lost.slice(0, gCap).join(', ');
    if (lost.length > gCap) gShown += ', +' + (lost.length - gCap) + ' more';
    var gColor = lost.length <= 3 ? '#d4a017' : '#e07b7b';
    return '<span style="color:' + gColor + '" title="' +
           gShown.replace(/"/g, '&quot;') + '">' + lost.length + '</span>';
  }
'''

# --- Anchor 1: the otherTiersExcept function, immediately before `var html`. ---
A1_OLD = (
    "  function otherTiersExcept(rc, excludeTier) {\n"
    "    var out = [];\n"
    "    for (var ot = 0; ot < (rc.matched || []).length; ot++) {\n"
    "      if (rc.matched[ot] !== excludeTier) out.push(rc.matched[ot]);\n"
    "    }\n"
    "    return out;\n"
    "  }\n"
    "\n"
    "  var html = '';"
)
A1_NEW = A1_OLD.replace("\n  var html = '';", "\n" + HELPER + "\n  var html = '';")

# --- Anchor 2: the per-tier section `extras` (the 'Also in' column). ---
A2_OLD = (
    "        [\n"
    "          { header: 'Also in', cls: 'wrap', cell: function(rc) {\n"
    "              var also = otherTiersExcept(rc, currentTierName);\n"
    "              if (rc.slayerCats && rc.slayerCats.length > 0) {\n"
    "                also = also.concat(rc.slayerCats);\n"
    "              }\n"
    "              return listOrDash(also);\n"
    "          } }\n"
    "        ],"
)
A2_NEW = A2_OLD.replace(
    "          } }\n        ],",
    "          } },\n"
    "          { header: 'Gives up vs #1', cell: _cellGivesUp, help: HELP_GIVES_UP }\n"
    "        ],")

# --- Anchor 3: the Slayer-IVs section `extras`. ---
A3_OLD = (
    "      { header: 'Top-Mirror CMP %', cell: _cellTopMirror,    help: HELP_TOP_MIRROR_CMP },\n"
    "      { header: 'Matchups Kept',    cell: _cellMatchupsKept, help: HELP_MATCHUPS_KEPT }\n"
    "    ]"
)
A3_NEW = A3_OLD.replace(
    "help: HELP_MATCHUPS_KEPT }\n    ]",
    "help: HELP_MATCHUPS_KEPT },\n"
    "      { header: 'Gives up vs #1',   cell: _cellGivesUp,      help: HELP_GIVES_UP }\n"
    "    ]")

PAIRS = [(A1_OLD, A1_NEW), (A2_OLD, A2_NEW), (A3_OLD, A3_NEW)]


def targets(argv):
    if argv:
        return argv
    return glob.glob(os.path.join('userdata', 'website', '*', 'index*.html'))


def main():
    files = targets(sys.argv[1:])
    patched = already = skipped = 0
    for path in sorted(files):
        try:
            html = open(path).read()
        except OSError:
            continue
        if '_cellGivesUp' in html:
            already += 1
            continue
        if not all(old in html for old, _new in PAIRS):
            # Missing an anchor (older engine vintage) -> leave untouched.
            if 'renderMatchesList' in html:
                skipped += 1
                print(f"skip (anchors not all present): {path}")
            continue
        for old, new in PAIRS:
            html = html.replace(old, new, 1)
        open(path, 'w').write(html)
        patched += 1
        print(f"patched {path}")
    print(f"\n{len(files)} file(s): {patched} patched, {already} already, "
          f"{skipped} skipped (need re-render).")


if __name__ == '__main__':
    main()
