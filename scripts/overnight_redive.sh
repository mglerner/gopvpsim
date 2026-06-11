#!/usr/bin/env bash
# Overnight re-dive + article regen + comparison + verify pipeline.
#
# Runs all 19 website dives serially (per run_website_dives.py;
# Oinkologne M/F GL, Tinkaton GL/UL, Aegislash Blade/Shield GL,
# Forretress normal/shadow x Volt-Switch/Bug-Bite GL, Dewgong GL,
# Stunfisk GL, Galarian Corsola GL, plus 2026-06-02 new-season
# additions: Shadow Sableye GL (4 movesets via shared-dir split,
# Foul Play paired with all 4 legal partners), Seismitoad GL,
# Jumpluff GL + Shadow Jumpluff GL, Kanto Ninetales GL +
# Shadow Kanto Ninetales GL),
# patches per-opponent anchors, regenerates the Oinkologne CD article,
# renders the two Aegislash form-change comparison pages and the two
# Aegislash first-draft narrative articles (auto-prose, flag before
# shipping), rebuilds the site index, and runs the link verifier.
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
    # `|| rc=$?` keeps a failing step from tripping `set -e` inside this
    # function — without it, bash exits HERE and (because ERR traps are
    # not inherited by functions absent `set -E`) neither the [FAIL]
    # branch below nor the FATAL trap ever writes a terminal status.
    # That silent-death mode misattributed the 2026-06-11 Aegislash
    # (Blade) dive crash to a laptop sleep, twice.
    local rc=0
    "$@" 2>&1 | tee -a "$LOG" || rc=$?
    local elapsed=$(( $(date +%s) - t0 ))
    if [[ $rc -ne 0 ]]; then
        log "[FAIL] $label (rc=$rc, ${elapsed}s)"
        status "[FAIL] $label after ${elapsed}s"
        exit 1
    fi
    log "[DONE] $label (${elapsed}s)"
}

# -E so the ERR trap also fires for failures inside functions (it is
# not inherited by them otherwise).
set -E
trap 'rc=$?; log "[FATAL] overnight chain aborted (rc=$rc) at line $LINENO"; status "[FATAL] aborted (rc=$rc)"; exit $rc' ERR

log "=== overnight chain start ==="
log "log: $LOG"
log "status: $STATUS"
log ""
log "Status box (paste into another terminal pane):"
log "  watch -n 5 -c 'scripts/chain_status.py --chain overnight'              # needs: brew install watch"
log "  while true; do clear; scripts/chain_status.py --chain overnight; sleep 5; done   # no deps"
log ""

# 1. Twelve website dives (serial, per run_website_dives.py). Aegislash GL
#    rejoined the chain 2026-04-21 so the 2026-04-21 rename refactor
#    (drop compound <br> tier names, auto-gen standalone-mode narrative
#    for non-CD species) reaches every shipped dive.
step "Running 19 dives via run_website_dives.py" \
    python scripts/run_website_dives.py

# The scripts/patch_dive_*.py patchers are retrofit-only tools: they
# existed to carry a feature (opp anchors, Member IVs enhance, Top IVs
# CMP union, Mirror CMP tolerance) back into HTMLs shipped before the
# renderer/engine change landed. All four are now baked into the
# renderer + engine.js, so a successful Step 1 re-dive produces fresh
# HTMLs that already carry the behavior. The patchers remain available
# for ad-hoc retrofits of HTMLs outside this list; they are intentionally
# NOT in the overnight chain so an unexpected "[no-match]" log line from
# a healthy overnight doesn't read as a failure.

# 2. Oinkologne CD article (per-form Matchup Delta table needs both
#    Male and Female dives fresh, which Step 1 guarantees).
step "Regenerating Oinkologne CD article" \
    python scripts/generate_article.py Oinkologne great "Mud Slap"

# 3. Oinkologne Male-vs-Female comparison page.
step "Rendering Oinkologne M-vs-F comparison" \
    python scripts/compare_loadouts.py comparisons/oinkologne-male-vs-female.toml

# 4. Aegislash Blade-vs-Shield comparison page (GL only).
# UL dropped 2026-05-17 per mercuryish review (S2): not competitively
# viable, dropped from the site.
step "Rendering Aegislash Blade-vs-Shield GL comparison" \
    python scripts/compare_loadouts.py comparisons/aegislash-blade-vs-shield.toml

# 5. Forretress 4-way comparison: fast-move x shadow. Reads data from
#    the 4 Forretress dive dirs the chain produced in step 1.
step "Rendering Forretress fast-move x shadow comparison" \
    python scripts/compare_loadouts.py comparisons/forretress-fast-move-shadow.toml

# 5a. Jumpluff regular-vs-Shadow comparison (added 2026-06-03). Reads
#     from the jumpluff-great-league and shadow-jumpluff-great-league
#     dive dirs the chain produced in step 1.
step "Rendering Jumpluff regular-vs-Shadow comparison" \
    python scripts/compare_loadouts.py comparisons/jumpluff-regular-vs-shadow.toml

# 5b. Kanto Ninetales regular-vs-Shadow comparison (added 2026-06-03).
#     Reads from the ninetales-great-league and shadow-ninetales-great-
#     league dive dirs the chain produced in step 1.
step "Rendering Kanto Ninetales regular-vs-Shadow comparison" \
    python scripts/compare_loadouts.py comparisons/ninetales-regular-vs-shadow.toml

# 6. Aegislash first-draft narrative article (GL only). Auto-generated
#    prose; morning report should flag every authored section before
#    anything ships. UL dropped 2026-05-17 per mercuryish review (S2).
step "Generating Aegislash GL first-draft article" \
    python scripts/write_aegislash_narrative.py great

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
