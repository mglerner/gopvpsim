#!/usr/bin/env bash
# Overnight re-dive + article regen + comparison + verify pipeline.
#
# Runs all 8 website dives serially (per run_website_dives.py), patches
# per-opponent anchors, regenerates the Oinkologne CD article, renders
# the two Aegislash form-change comparison pages and the two Aegislash
# first-draft narrative articles (auto-prose, flag before shipping),
# rebuilds the site index, and runs the link verifier.
#
# Usage:
#   nohup scripts/overnight_redive.sh &
#
# Produces:
#   userdata/logs/2026-04/overnight_YYYYMMDD_HHMMSS.log  (full output)
#   userdata/logs/overnight_status.txt                   (single status line)
#
# Morning check: `tail userdata/logs/overnight_status.txt` for pass/fail,
# then scan the log file for per-step elapsed times.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export PYTHONUNBUFFERED=1

TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="userdata/logs/2026-04"
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/overnight_${TS}.log"
STATUS="userdata/logs/overnight_status.txt"

echo "overnight chain PID $$ starting at $(date)" > "$STATUS"

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

trap 'rc=$?; log "[FATAL] overnight chain aborted (rc=$rc) at line $LINENO"; status "[FATAL] aborted (rc=$rc)"; exit $rc' ERR

log "=== overnight chain start ==="
log "log: $LOG"
log "status: $STATUS"
log ""
log "Status box (paste into another terminal pane):"
log "  watch -n 5 -c 'scripts/chain_status.py --chain overnight'              # needs: brew install watch"
log "  while true; do clear; scripts/chain_status.py --chain overnight; sleep 5; done   # no deps"
log ""

# 1. Eight website dives (serial, per run_website_dives.py).
step "Running 8 dives via run_website_dives.py" \
    python scripts/run_website_dives.py

# 2. Back-fill per-opponent #opp-<slug> anchors into every dive dir.
#    Idempotent; for brand-new dives the renderer already emitted ids so
#    this is mostly a no-op, but it's cheap and protects against any
#    dive that was started before the renderer change.
step "Patching per-opponent anchors in all dive dirs" \
    python scripts/patch_dive_opp_anchors.py \
        userdata/website/oinkologne-great-league \
        userdata/website/oinkologne-female-great-league \
        userdata/website/tinkaton-great-league \
        userdata/website/tinkaton-ultra-league \
        userdata/website/aegislash-blade-great-league \
        userdata/website/aegislash-shield-great-league \
        userdata/website/aegislash-blade-ultra-league \
        userdata/website/aegislash-shield-ultra-league \
        userdata/website/forretress-volt-switch-great-league \
        userdata/website/forretress-bug-bite-great-league \
        userdata/website/forretress-shadow-volt-switch-great-league \
        userdata/website/forretress-shadow-bug-bite-great-league

# 3. Oinkologne CD article (per-form Matchup Delta table needs both
#    Male and Female dives fresh, which steps 1 + 2 guarantee).
step "Regenerating Oinkologne CD article" \
    python scripts/generate_article.py Oinkologne great "Mud Slap"

# 4. Oinkologne Male-vs-Female comparison page.
step "Rendering Oinkologne M-vs-F comparison" \
    python scripts/compare_loadouts.py comparisons/oinkologne-male-vs-female.toml

# 5. Aegislash Blade-vs-Shield comparison pages (GL + UL).
step "Rendering Aegislash Blade-vs-Shield GL comparison" \
    python scripts/compare_loadouts.py comparisons/aegislash-blade-vs-shield.toml

step "Rendering Aegislash Blade-vs-Shield UL comparison" \
    python scripts/compare_loadouts.py comparisons/aegislash-blade-vs-shield-ul.toml

# 6. Aegislash first-draft narrative articles (one per league). Auto-
#    generated prose; morning report should flag every authored section
#    before anything ships.
step "Generating Aegislash GL first-draft article" \
    python scripts/write_aegislash_narrative.py great

step "Generating Aegislash UL first-draft article" \
    python scripts/write_aegislash_narrative.py ultra

# 7. Rebuild site index so the new pages show up in the top-level link
#    page.
step "Rebuilding website index" \
    python scripts/build_website_index.py

# 8. Final link-verification sweep. --ship runs the Oinkologne pre-ship
#    surface; links from Aegislash/Tinkaton pages aren't covered by the
#    default ship set but will surface any broken hrefs if present.
step "Running article link verification" \
    python scripts/verify_article_links.py --ship

log "=== overnight chain SUCCESS ==="
status "SUCCESS overnight chain complete"
