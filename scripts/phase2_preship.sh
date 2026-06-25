#!/usr/bin/env bash
# Phase-2 pre-ship runner + waiter (2026-06-25).
#
# Waits for the overnight chain (overnight_redive.sh / run_iv_guides.py) to
# exit, then applies the pre-ship fixes that need a re-sim or re-render,
# rebuilds the site, runs the ship gate, and STOPS at the publish step.
# It never publishes -- the rsync push stays manual / nod-gated.
#
# Fixes folded in (all already committed on dive-ia-rework):
#   re-sim (blob-baked):
#     - Shadow Sableye GL : moveset landing-sort (Drain Punch, not Dazzling Gleam)
#     - 4 UL dives        : Aegislash removed from the UL opponent pool
#   re-render (no re-sim):
#     - 40 dive cards     : pole + greedy-fill dominance, red right-anchored
#                           loss bars, "exit the battle with" wording
#     - 61 ML IV guides   : red loss bars + wording
#   rebuild:
#     - 4 comparison pages + matchup web : standard footer + authorship banner
#     - site index
#
# Usage:  nohup scripts/phase2_preship.sh >/dev/null 2>&1 &
# Watch:  tail -f userdata/logs/phase2_preship.log
#         cat userdata/logs/phase2_ready.txt   (appears only when complete)
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
export PYTHONUNBUFFERED=1
PY=".venv/bin/python"

LOG="userdata/logs/phase2_preship.log"
READY="userdata/logs/phase2_ready.txt"
mkdir -p userdata/logs
: > "$LOG"
rm -f "$READY"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG"; }

# Render/rebuild step: warn + continue on failure (one bad render must not
# abort the whole site rebuild; the morning review + --ship gate catch it).
run() {
    local label="$1"; shift
    log "[STEP] $label"
    local t0 rc=0; t0=$(date +%s)
    "$@" >>"$LOG" 2>&1 || rc=$?
    local el=$(( $(date +%s) - t0 ))
    if [[ $rc -ne 0 ]]; then log "[WARN] $label (rc=$rc, ${el}s) -- see $LOG"; else log "[DONE] $label (${el}s)"; fi
    return 0
}

# Critical step: ABORT phase2 on failure (a failed re-sim must not let stale
# data masquerade as fresh in the shipped site).
crit() {
    local label="$1"; shift
    log "[STEP] $label"
    local t0 rc=0; t0=$(date +%s)
    "$@" >>"$LOG" 2>&1 || rc=$?
    local el=$(( $(date +%s) - t0 ))
    if [[ $rc -ne 0 ]]; then
        log "[FAIL] $label (rc=$rc, ${el}s) -- ABORTING phase2; site left as-is. See $LOG"
        exit 1
    fi
    log "[DONE] $label (${el}s)"
}

# --- 0. Wait for the overnight chain to finish --------------------------
log "=== phase2 waiter armed $(date); waiting for overnight chain to exit ==="
while pgrep -f 'overnight_redive.sh' >/dev/null 2>&1 \
   || pgrep -f 'run_iv_guides.py'   >/dev/null 2>&1; do
    sleep 60
done
log "Overnight chain no longer running. Starting Phase-2 work."

# --- 1. Re-sim the dives needing fresh sim data (CRITICAL) --------------
crit "Re-dive Shadow Sableye GL (landing-sort fix)" \
    $PY scripts/run_website_dives.py shadow-sableye --reserve-cpus 1
crit "Re-dive 4 UL dives (Aegislash removed from pool)" \
    $PY scripts/run_website_dives.py ultra --reserve-cpus 1

# --- 2. Re-render all dive cards from blobs (no re-sim) -----------------
# rerender_dive_cards renders blobs ascending-mtime (latest wins). All 40
# dives were re-dived in today's chain and the 5 above are newer still, so a
# 30h window can never surface a stale dive over a fresh one.
run "Re-render dive cards (pole/greedy/loss-bar/wording)" \
    $PY scripts/rerender_dive_cards.py --since-hours 30 --jobs 6

# --- 3. Re-render the 61 ML IV guides from saved JSONs (no re-sim) ------
log "[STEP] Re-render ML IV guides from saved JSONs"
ml_t0=$(date +%s); ml_ok=0; ml_fail=0
shopt -s nullglob
for j in userdata/dives/*_iv_envelope_all9.json; do
    if $PY scripts/render_iv_envelope_article.py "$j" >>"$LOG" 2>&1; then
        ml_ok=$((ml_ok+1))
    else
        ml_fail=$((ml_fail+1)); log "  [WARN] ML render FAILED: $j"
    fi
done
shopt -u nullglob
log "[DONE] ML IV guides re-rendered: ${ml_ok} ok, ${ml_fail} failed ($(( $(date +%s) - ml_t0 ))s)"

# --- 4. Rebuild comparison pages + matchup web (footer + banner) --------
for t in aegislash-blade-vs-shield forretress-fast-move-shadow \
         jumpluff-regular-vs-shadow ninetales-regular-vs-shadow; do
    run "Rebuild comparison: $t" $PY scripts/compare_loadouts.py "comparisons/$t.toml"
done
run "Rebuild Great League matchup web (footer)" $PY scripts/build_matchup_web.py

# --- 5. Rebuild index + run the ship gate (informational) --------------
run "Rebuild website index" $PY scripts/build_website_index.py
run "Ship link verification (--ship)" $PY scripts/verify_article_links.py --ship

# --- 6. Ready marker -- do NOT publish (push is manual) ----------------
{
    echo "PHASE 2 COMPLETE -- ready to review and publish."
    echo "Finished: $(date)"
    echo
    echo "Review the local site, then publish with:"
    echo "  scripts/publish_website.sh           # dry run (safe)"
    echo "  scripts/publish_website.sh --push     # actually push"
} > "$READY"
log "=== phase2 COMPLETE. Wrote $READY. NOT publishing (push is manual). ==="
