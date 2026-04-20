#!/usr/bin/env bash
# Targeted re-dive to retroactively pick up two fixes that shipped
# AFTER the 2026-04-19 overnight chain had already started dives 1-3:
#
#   * d3e2aae: split-movesets landing-page fix (index.html on moveset
#     0 / top-scoring, not the reference moveset).
#   * fdbf6ce: Mirror CMP % + Score Δ vs rank-1 columns on the Top
#     IVs table + scatter hover tooltip.
#
# Dives 4-10 of the overnight chain spawned fresh Python subprocesses
# after both commits landed, so they already have the fixes. The
# three affected dives are Oinkologne (Male) GL, Oinkologne (Female)
# GL, and Tinkaton GL.
#
# Serial execution, ~60-70 min per dive, ~3.3 hours total. Plus the
# downstream pipeline (anchor patcher, article regen, comparison
# render, site index, link verify) adds ~5 min.
#
# Usage:
#   nohup scripts/retrofit_3_dives.sh &
#
# Log: userdata/logs/2026-04/retrofit_YYYYMMDD_HHMMSS.log
# Status: userdata/logs/retrofit_status.txt (single line, tail for
# morning check).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export PYTHONUNBUFFERED=1

TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="userdata/logs/2026-04"
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/retrofit_${TS}.log"
STATUS="userdata/logs/retrofit_status.txt"

echo "retrofit chain PID $$ starting at $(date)" > "$STATUS"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG"
}

status() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" > "$STATUS"
}

step() {
    local label="$1"
    shift
    log "[STEP] $label"
    status "[STEP] $label"
    local t0=$(date +%s)
    "$@" 2>&1 | tee -a "$LOG"
    local rc=${PIPESTATUS[0]}
    local elapsed=$(( $(date +%s) - t0 ))
    if [[ $rc -ne 0 ]]; then
        log "[FAIL] $label (rc=$rc, ${elapsed}s)"
        status "[FAIL] $label after ${elapsed}s"
        exit 1
    fi
    log "[DONE] $label (${elapsed}s)"
}

trap 'rc=$?; log "[FATAL] retrofit aborted (rc=$rc) at line $LINENO"; status "[FATAL] aborted (rc=$rc)"; exit $rc' ERR

log "=== retrofit chain start ==="
log "log: $LOG"
log "status: $STATUS"
log ""
log "Status box (paste into another terminal pane):"
log "  while true; do clear; scripts/overnight_status.sh; sleep 5; done"
log ""

# 1. Re-dive the 2 Oinkologne GL dives. run_website_dives.py's
#    substring filter matches both (Male + Female) via "oinkologne".
step "Re-diving Oinkologne GL pair" \
    python scripts/run_website_dives.py oinkologne

# 2. Re-dive Tinkaton GL. "tinkaton-great" is more specific than
#    "tinkaton" (latter would also match tinkaton-ultra-league).
step "Re-diving Tinkaton GL" \
    python scripts/run_website_dives.py tinkaton-great

# 3. Patch per-opponent anchors in the 3 refreshed dive dirs.
step "Patching per-opponent anchors (3 dirs)" \
    python scripts/patch_dive_opp_anchors.py \
        userdata/website/oinkologne-great-league \
        userdata/website/oinkologne-female-great-league \
        userdata/website/tinkaton-great-league

# 4. Regenerate the Oinkologne CD article (reads both Oink form dives).
step "Regenerating Oinkologne CD article" \
    python scripts/generate_article.py Oinkologne great "Mud Slap"

# 5. Re-render the Oinkologne M-vs-F comparison page.
step "Rendering Oinkologne M-vs-F comparison" \
    python scripts/compare_loadouts.py comparisons/oinkologne-male-vs-female.toml

# 6. Rebuild the site index so fresh mtimes sort correctly.
step "Rebuilding website index" \
    python scripts/build_website_index.py

# 7. Final link-verification sweep.
step "Running article link verification" \
    python scripts/verify_article_links.py --ship

log "=== retrofit chain SUCCESS ==="
status "SUCCESS retrofit chain complete"
