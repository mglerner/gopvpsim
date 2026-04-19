#!/usr/bin/env bash
# Compact one-shot status probe for the overnight re-dive chain.
#
# Bundles the same checks that Claude's 3-min cron was firing as inline
# Bash (ps, cat status, grep wrapper log, tail latest per-dive log) into
# a single script, so that exactly one Bash(scripts/status_tick.sh)
# allow-rule in .claude/settings.local.json can cover the whole probe.
# That means Claude can tick autonomously while Michael is AFK -- no
# per-command approval prompts -- without granting broad Bash access.
#
# Output (stdout, one summary block, deliberately compact):
#
#   STATUS: ALIVE PID=38169
#   DIVE: [1/10] oinkologne-great-league  elapsed 42m13s
#   PHASE: Interactive sweep [5/5] Tackle / Body Slam, Trailblaze (...)
#   PROGRESS: progress: 46/98 chunks (47%), eta 73s
#
# On terminal states emits a single STATUS: line plus the raw status-file
# content and exits nonzero so the caller can spot completion or failure
# without reading the body:
#
#   STATUS: SUCCESS            (exit 0)
#   STATUS: FAILED ...         (exit 2)
#   STATUS: DEAD (PID not found, chain may have exited)  (exit 1)
#
# Read-only. Touches no state; safe to run concurrently with the chain.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STATUS_FILE="userdata/logs/overnight_status.txt"
LOG_DIR="userdata/logs/2026-04"

# Terminal-state check first: the status file is authoritative for
# SUCCESS/FAIL/FATAL and lets us short-circuit without walking logs.
STATUS_LINE=""
[[ -f "$STATUS_FILE" ]] && STATUS_LINE=$(cat "$STATUS_FILE")

case "$STATUS_LINE" in
    *SUCCESS*)
        echo "STATUS: SUCCESS"
        echo "$STATUS_LINE"
        exit 0
        ;;
    *FAIL*|*FATAL*)
        echo "STATUS: FAILED"
        echo "$STATUS_LINE"
        exit 2
        ;;
esac

# PID liveness. pgrep-match the wrapper script name so we're robust to
# the actual PID number shifting between chain restarts.
PID=$(pgrep -f "overnight_redive.sh" 2>/dev/null | head -1)
if [[ -z "$PID" ]] || ! ps -p "$PID" >/dev/null 2>&1; then
    echo "STATUS: DEAD (no overnight_redive.sh process found)"
    [[ -n "$STATUS_LINE" ]] && echo "LAST: $STATUS_LINE"
    exit 1
fi

echo "STATUS: ALIVE PID=$PID"

# Dive banner from the wrapper log: run_website_dives.py prints
# "[N/M] slug" before each dive starts. Latest match = current dive.
WRAPPER_LOG=$(ls -t "$LOG_DIR"/overnight_*.log 2>/dev/null | head -1)
DIVE_BANNER=""
if [[ -n "$WRAPPER_LOG" && -f "$WRAPPER_LOG" ]]; then
    DIVE_BANNER=$(grep -oE '\[[0-9]+/[0-9]+\] [a-z-]+-(great|ultra|master)-league' "$WRAPPER_LOG" 2>/dev/null | tail -1)
fi

# Per-dive elapsed = now minus the first-line timestamp of the latest
# per-dive log (its mtime would lag, this tracks the true dive-start).
LATEST_LOG=$(ls -t "$LOG_DIR"/20260419_*.log 2>/dev/null | grep -v overnight | head -1)
ELAPSED="?"
if [[ -n "$LATEST_LOG" && -f "$LATEST_LOG" ]]; then
    FIRST_TS=$(head -1 "$LATEST_LOG" | grep -oE '\[[0-9-]+ [0-9:]+' | tr -d '[')
    if [[ -n "$FIRST_TS" ]]; then
        FIRST_EPOCH=$(date -jf "%Y-%m-%d %H:%M:%S" "$FIRST_TS" +%s 2>/dev/null || echo "")
        if [[ -n "$FIRST_EPOCH" ]]; then
            NOW=$(date +%s)
            DIFF=$(( NOW - FIRST_EPOCH ))
            if   (( DIFF < 60 ));   then ELAPSED="${DIFF}s"
            elif (( DIFF < 3600 )); then ELAPSED="$((DIFF/60))m$((DIFF%60))s"
            else                         ELAPSED="$((DIFF/3600))h$(((DIFF%3600)/60))m"
            fi
        fi
    fi
fi
echo "DIVE: ${DIVE_BANNER:-unknown}  elapsed ${ELAPSED}"

# Coarse phase (last Phase/sweep/round banner) + latest fine-grained
# progress line. Strip the "[timestamp] LEVEL module:" prefix so the
# signal fits on one line.
if [[ -n "$LATEST_LOG" && -f "$LATEST_LOG" ]]; then
    PHASE=$(grep -E 'Phase [0-9]|Interactive sweep|Mirror slayer|iteration round' "$LATEST_LOG" 2>/dev/null | tail -1 | sed -E 's|^\[[^]]+\] +[A-Z]+ +[a-z_]+: *||')
    [[ -n "$PHASE" ]] && echo "PHASE: $PHASE"
    PROGRESS=$(tail -1 "$LATEST_LOG" 2>/dev/null | sed -E 's|^\[[^]]+\] +[A-Z]+ +[a-z_]+: *||')
    [[ -n "$PROGRESS" ]] && echo "PROGRESS: $PROGRESS"
fi
