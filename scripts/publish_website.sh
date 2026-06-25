#!/usr/bin/env bash
# Publish userdata/website/ to mglerner.com/pogo-dives/.
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
#   3. rsync to mglerner.com:mglerner.com/pogo-dives/ with --delete
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
DEST="mglerner.com:mglerner.com/pogo-dives/"

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

echo "Regenerating index.html..."
python "${REPO_ROOT}/scripts/build_website_index.py"
echo

if [ "$SKIP_VERIFY" = true ]; then
  echo "Skipping link + dash verification (--skip-verify)."
else
  echo "Verifying article links..."
  if ! python "${REPO_ROOT}/scripts/verify_article_links.py" --ship; then
    echo
    echo "error: link verification failed -- fix broken links or re-run with --skip-verify" >&2
    exit 1
  fi
  echo

  echo "Verifying no em/en-dashes in user-facing text..."
  if ! python "${REPO_ROOT}/scripts/verify_no_unicode_dashes.py" --ship -q; then
    echo
    echo "error: em/en-dash check failed -- replace with ASCII hyphens or re-run with --skip-verify" >&2
    exit 1
  fi
  echo
fi

RSYNC_EXCLUDES=(--exclude='meta.toml')

if [ "$PUSH" = true ]; then
  echo "Pushing ${SRC} -> ${DEST}"
  rsync -avzh --delete --delete-excluded "${RSYNC_EXCLUDES[@]}" "$SRC" "$DEST"
  echo
  echo "Done. Site should be live at https://mglerner.com/pogo-dives/"
else
  echo "Dry run (pass --push to actually push)"
  echo "Source: ${SRC}"
  echo "Dest:   ${DEST}"
  echo
  rsync -avzhn --delete --delete-excluded "${RSYNC_EXCLUDES[@]}" "$SRC" "$DEST"
  echo
  echo "(dry run - nothing was actually sent; pass --push to publish)"
fi
