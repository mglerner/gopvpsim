#!/usr/bin/env bash
# Publish userdata/website/ to pogodives.com (the primary home; the old
# mglerner.com/pogo-dives path 301-redirects here via a hand-placed .htaccess).
#
# Flow on every run:
#   1. Regenerate userdata/website/index.html from per-dive meta.toml files
#      (so a fresh dive dropped in userdata/website/<slug>/ with a meta.toml
#      is picked up without a separate step).
#   2. Run link verification (scripts/verify_article_links.py --ship)
#      and em/en-dash verification (scripts/verify_no_unicode_dashes.py
#      --ship). Any broken internal link or unicode-dash hit aborts the
#      publish before anything hits the server. Pass --skip-verify to
#      bypass (e.g. publishing an in-progress page where you know a
#      link will dangle temporarily).
#   3. rsync to mglerner.com:/home/mglerner/pogodives.com/ with --delete
#      --delete-excluded, so anything removed locally -- or matching an
#      exclude pattern -- is also removed on the server.
#
# Excluded from the publish: meta.toml (site-index build metadata, not
# user-facing). Server-side copies are removed on next push via
# --delete-excluded.
#
# Default is dry-run. Pass --push to actually send the files.
#
# Usage:
#     scripts/publish_website.sh                  # dry run (safe default)
#     scripts/publish_website.sh --push           # actually push
#     scripts/publish_website.sh --push --skip-verify  # bypass link check

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${REPO_ROOT}/userdata/website/"
DEST="mglerner.com:/home/mglerner/pogodives.com/"

PUSH=false
SKIP_VERIFY=false
for arg in "$@"; do
  case "$arg" in
    --push) PUSH=true ;;
    --skip-verify) SKIP_VERIFY=true ;;
    *) echo "error: unknown arg '$arg'" >&2; exit 2 ;;
  esac
done

if [ ! -d "$SRC" ]; then
  echo "error: $SRC does not exist" >&2
  exit 1
fi

# Completeness gate (added 2026-09-10). rsync runs with --delete, so this
# script MIRRORS: whatever is in $SRC becomes the entire live site, and
# anything missing locally is deleted from the server. That was safe while
# userdata/website was always fully populated. It is not safe now -- the
# 2026-09-09 userdata wipe means a publish part-way through a bake would
# delete every page the bake had not reached yet.
#
# The existing "-d $SRC" check only catches the empty case. This catches the
# PARTIAL case: refuse when the site has materially fewer dive pages than the
# dive list says it should.
EXPECTED_DIVES=$(cd "$REPO_ROOT" && python -c "
import sys; sys.path.insert(0, 'scripts')
from dive_registry import all_dives
print(len(all_dives()))
" 2>/dev/null || echo 0)
ACTUAL_DIVES=$(find "$SRC" -mindepth 2 -maxdepth 2 -name index.html 2>/dev/null | wc -l | tr -d ' ')
if [ "$SKIP_VERIFY" = false ] && [ "$EXPECTED_DIVES" -gt 0 ]; then
  MIN_DIVES=$(( EXPECTED_DIVES * 9 / 10 ))
  if [ "$ACTUAL_DIVES" -lt "$MIN_DIVES" ]; then
    echo "error: refusing to publish an INCOMPLETE site." >&2
    echo "  dive pages found: $ACTUAL_DIVES; expected ~$EXPECTED_DIVES (floor $MIN_DIVES)" >&2
    echo "  rsync runs with --delete, so publishing now would REMOVE the" >&2
    echo "  missing pages from pogodives.com." >&2
    echo "  fix:    finish the bake (scripts/run_website_dives.py)" >&2
    echo "  bypass: re-run with --skip-verify" >&2
    exit 1
  fi
fi

# Card-rerender gate: a renderer-side fix landed after the dives were simmed,
# so the shipped HTML is stale until rebuilt from the replay blobs. The
# sentinel is dropped when that happens and cleared by rerender_dive_cards.py.
# (Bypass with --skip-verify, same as the link/dash checks.)
SENTINEL="${REPO_ROOT}/userdata/.cards_rerender_pending"
if [ "$SKIP_VERIFY" = false ] && [ -f "$SENTINEL" ]; then
  echo "error: dive cards need re-rendering before publish." >&2
  echo "  reason: $(head -1 "$SENTINEL" 2>/dev/null)" >&2
  echo "  fix:    python scripts/rerender_dive_cards.py   (replays the blobs, clears this gate)" >&2
  echo "  bypass: re-run with --skip-verify" >&2
  exit 1
fi

echo "Regenerating reader guides..."
python "${REPO_ROOT}/scripts/build_guides.py"
echo

# Worlds 2026 re-render is OPT-IN as of 2026-08-31. The shipped pages are
# frozen at a Worlds-era engine/gamemaster; re-rendering them from main would
# restamp them against current data without re-simming, i.e. publish pages that
# claim a vintage they were not baked at. Set WORLDS_RERENDER=1 to force it
# (only meaningful with the gamemaster re-pinned per TODO.md). The surfaces
# retire at the Twilight Trails site update -- see scripts/run_ship_gates.py.
if [ "${WORLDS_RERENDER:-0}" = "1" ] && [ -f "${REPO_ROOT}/worlds/planes/manifest.json" ]; then
  echo "Regenerating Worlds 2026 pages (WORLDS_RERENDER=1)..."
  if [ -f "${REPO_ROOT}/worlds/planes/tier2/manifest.json" ]; then
    python "${REPO_ROOT}/scripts/build_worlds_pair_pages.py"
  fi
  python "${REPO_ROOT}/scripts/build_worlds_cmp.py"
  python "${REPO_ROOT}/scripts/build_worlds_explorer.py"
  python "${REPO_ROOT}/scripts/build_worlds_pages.py"
  echo
fi

echo "Regenerating index.html..."
python "${REPO_ROOT}/scripts/build_website_index.py"
echo

if [ "$SKIP_VERIFY" = true ]; then
  echo "Skipping ship gates (--skip-verify)."
else
  echo "Running ship gates (roster: scripts/run_ship_gates.py)..."
  if ! python "${REPO_ROOT}/scripts/run_ship_gates.py"; then
    echo
    echo "error: a ship gate failed -- fix the violations or re-run with --skip-verify" >&2
    exit 1
  fi
  echo
fi

RSYNC_EXCLUDES=(--exclude='meta.toml')

if [ "$PUSH" = true ]; then
  echo "Pushing ${SRC} -> ${DEST}"
  rsync -avzh --delete --delete-excluded "${RSYNC_EXCLUDES[@]}" "$SRC" "$DEST"
  echo
  echo "Done. Site should be live at https://pogodives.com/"
else
  echo "Dry run (pass --push to actually push)"
  echo "Source: ${SRC}"
  echo "Dest:   ${DEST}"
  echo
  rsync -avzhn --delete --delete-excluded "${RSYNC_EXCLUDES[@]}" "$SRC" "$DEST"
  echo
  echo "(dry run - nothing was actually sent; pass --push to publish)"
fi
