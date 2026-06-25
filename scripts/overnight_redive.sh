#!/usr/bin/env bash
# Overnight re-dive + article regen + comparison + verify pipeline.
#
# Runs all 40 website dives serially (the focal list lives in
# run_website_dives.DIVES -- 36 GL + 4 UL as of the 2026-06-25 refresh),
# patches per-opponent anchors, renders the Aegislash form-change comparison
# page + first-draft narrative article and the Forretress/Jumpluff/Ninetales
# comparison pages, bakes the Master-league ML IV guides (run_iv_guides.py,
# whole master_top60 pool), rebuilds the Great League matchup web, rebuilds
# the site index, and runs the link verifier.
#
# 2026-06-25 changes: the Oinkologne CD article + Male-vs-Female comparison
# steps were removed (both pages archived/deleted from the site -- see
# TODO.md); the ML IV-guide bake was added as a (long, ~7h cold) tail step;
# the dives + guides run with all cores (--reserve-cpus 0 / --reserve 0) for
# the unattended overnight window.
#
# Usage:
#   nohup scripts/overnight_redive.sh &
#
# Produces:
#   userdata/logs/2026-04/overnight_YYYYMMDD_HHMMSS.log  (full output)
#   userdata/logs/overnight_status.txt                   (single status line)
#
# Morning check: `python scripts/verify_overnight.py` — one-shot
# aggregate of chain status, dive-dir freshness (stale split-orphan
# detection), opponent-pool sanity markers, and both ship gates.
# (`tail userdata/logs/overnight_status.txt` is the raw pass/fail line;
# scan the log file for per-step elapsed times.)
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

# 1. Twenty website dives (serial, per run_website_dives.py). Aegislash GL
#    rejoined the chain 2026-04-21 so the 2026-04-21 rename refactor
#    (drop compound <br> tier names, auto-gen standalone-mode narrative
#    for non-CD species) reaches every shipped dive.
step "Running 40 dives via run_website_dives.py" \
    python scripts/run_website_dives.py --reserve-cpus 0

# The retrofit-only patch_dive_*.py patchers were deleted in the S7
# cleanup (2026-06-12): everything they carried is baked into the
# renderer + engine.js, and a successful Step 1 re-dive produces fresh
# HTMLs natively. patch_dive_species_narrative.py (run inside
# run_website_dives.py) is the only surviving patcher.

# (Steps 2 & 3 -- the Oinkologne CD article and Male-vs-Female comparison --
#  were removed 2026-06-25. The male Oinkologne dive is no longer in DIVES, so
#  both pages would have shipped stale male data; both are archived/deleted
#  from the site. See TODO.md.)

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

# 7. Great League matchup web (cross-species all-pairs matrix). Standalone
#    page with its own pool sim (~9s), not derived from the dives, but
#    rebuilt here so the published matrix carries the current engine's
#    scores. Added 2026-06-15 after it was found stale at a pre-shadow-CMP
#    vintage because it had been missing from this chain.
step "Building Great League matchup web" \
    python scripts/build_matchup_web.py

# 7b. Master-league ML IV guides (run_iv_guides.py, whole master_top60 pool).
#     Independent ~7h COLD job (the fresh 2026-06-25 PvPoke pull changed the
#     gamemaster hash, orphaning the won-set caches), sequenced AFTER the dives
#     so the two never oversubscribe the cores. --reserve 0: all cores for the
#     unattended window. --no-index-refresh: the chain's own index rebuild
#     (Step 8, next) owns index.html, so the per-guide rebuilds don't race it.
#
#     Run OUTSIDE step() ON PURPOSE: run_iv_guides.py exits 1 if ANY single
#     guide fails (sys.exit at its tail), which through step()'s FATAL trap
#     would abort the final index+verify steps and lose the new Reshiram (Shadow)
#     guide from the index. A single bad guide must not kill the rest, so this
#     block only WARNs on a non-zero rc and lets the chain continue.
log "[STEP] ML IV guides (run_iv_guides.py, master_top60, all cores)"
status "[STEP] ML IV guides"
ml_t0=$(date +%s)
ml_rc=0
python scripts/run_iv_guides.py --no-index-refresh --reserve 0 2>&1 | tee -a "$LOG" || ml_rc=$?
ml_elapsed=$(( $(date +%s) - ml_t0 ))
if [[ $ml_rc -ne 0 ]]; then
    log "[WARN] ML IV guides reported failures (rc=$ml_rc, ${ml_elapsed}s) -- continuing to index+verify; grep the log for 'FAILED' lines"
    status "[WARN] ML guides had failures after ${ml_elapsed}s"
else
    log "[DONE] ML IV guides (${ml_elapsed}s)"
fi

# 8. Rebuild site index so the new pages (incl. the new Reshiram (Shadow) ML
#    guide) show up in the top-level link page.
step "Rebuilding website index" \
    python scripts/build_website_index.py

# 9. Final link-verification sweep. --ship runs the Oinkologne pre-ship
#    surface; links from Aegislash/Tinkaton pages aren't covered by the
#    default ship set but will surface any broken hrefs if present.
step "Running article link verification" \
    python scripts/verify_article_links.py --ship

log "=== overnight chain SUCCESS ==="
status "SUCCESS overnight chain complete"
