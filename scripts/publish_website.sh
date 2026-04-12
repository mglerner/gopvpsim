#!/usr/bin/env bash
# Publish userdata/website/ to mglerner.com/pogo-dives/.
#
# Flow on every run:
#   1. Regenerate userdata/website/index.html from per-dive meta.toml files
#      (so a fresh dive dropped in userdata/website/<slug>/ with a meta.toml
#      is picked up without a separate step).
#   2. rsync to mglerner.com:mglerner.com/pogo-dives/ with --delete, so
#      anything removed locally is also removed on the server.
#
# Default is dry-run. Pass --push to actually send the files.
#
# Usage:
#     scripts/publish_website.sh           # dry run (safe default)
#     scripts/publish_website.sh --push    # actually push

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${REPO_ROOT}/userdata/website/"
DEST="mglerner.com:mglerner.com/pogo-dives/"

if [ ! -d "$SRC" ]; then
  echo "error: $SRC does not exist" >&2
  exit 1
fi

echo "Regenerating index.html..."
python "${REPO_ROOT}/scripts/build_website_index.py"
echo

if [ "${1:-}" = "--push" ]; then
  echo "Pushing ${SRC} -> ${DEST}"
  rsync -avzh --delete "$SRC" "$DEST"
  echo
  echo "Done. Site should be live at https://mglerner.com/pogo-dives/"
else
  echo "Dry run (pass --push to actually push)"
  echo "Source: ${SRC}"
  echo "Dest:   ${DEST}"
  echo
  rsync -avzhn --delete "$SRC" "$DEST"
  echo
  echo "(dry run - nothing was actually sent; pass --push to publish)"
fi
