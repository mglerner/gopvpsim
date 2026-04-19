#!/usr/bin/env bash
# Formatted status display for the overnight re-dive chain.
#
# Usage (pinned box, live-redraw every 5s):
#     watch -n 5 -c scripts/overnight_status.sh
#
# Requires the chain to have been launched via scripts/overnight_redive.sh.
# Reads userdata/logs/overnight_status.txt (step level) and the latest
# per-dive log under userdata/logs/2026-04/ (fine-grained progress).
#
# Hardcoded chain PID: pass as first arg to override.
#     scripts/overnight_status.sh 12345
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STATUS_FILE="userdata/logs/overnight_status.txt"
LOG_DIR="userdata/logs/2026-04"
PID="${1:-}"

# Find the chain PID if not provided: look for a running bash running
# overnight_redive.sh.
if [[ -z "$PID" ]]; then
    PID=$(pgrep -f "overnight_redive.sh" 2>/dev/null | head -1)
fi

# ANSI colour helpers (watch -c strips these if it can't render them)
RESET=$'\033[0m'
BOLD=$'\033[1m'
DIM=$'\033[2m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
CYAN=$'\033[36m'
# Bold bright magenta — reserved for the Script ETA line so it's the
# first thing the eye lands on in the box. Distinct from the existing
# green/yellow/cyan palette so it doesn't blur with other status.
ETA_ACCENT=$'\033[1;95m'

# Top / bottom rule. Auto-detect terminal width (works under watch and
# plain shells alike) and cap at 140 so ultrawide terminals don't
# sprawl. Fall back to 80 when detection fails.
WIDTH=$(tput cols 2>/dev/null || echo 80)
if [[ "$WIDTH" -gt 140 ]]; then WIDTH=140; fi
if [[ "$WIDTH" -lt 60 ]]; then WIDTH=60; fi
rule() { printf '%s\n' "$(printf '─%.0s' $(seq 1 $WIDTH))"; }

# Header
printf "%s%s%s\n" "$BOLD$CYAN" "OVERNIGHT RE-DIVE STATUS  ($(date '+%H:%M:%S'))" "$RESET"
rule

# Chain PID + alive check
if [[ -n "$PID" ]] && ps -p "$PID" >/dev/null 2>&1; then
    ETIME=$(ps -p "$PID" -o etime= | tr -d ' ')
    printf "  PID %s  %s%s%s  (elapsed %s)\n" "$PID" "$GREEN" "ALIVE" "$RESET" "$ETIME"
else
    printf "  PID %s  %s%s%s\n" "${PID:-?}" "$RED$BOLD" "DEAD / NOT FOUND" "$RESET"
fi

# Chain step
if [[ -f "$STATUS_FILE" ]]; then
    STATUS_LINE=$(cat "$STATUS_FILE")
    # Colour SUCCESS green, FAIL/FATAL red, STEP yellow
    case "$STATUS_LINE" in
        *SUCCESS*)   COLOUR=$GREEN ;;
        *FAIL*|*FATAL*) COLOUR=$RED ;;
        *STEP*)      COLOUR=$YELLOW ;;
        *)           COLOUR=$RESET ;;
    esac
    printf "  Step: %s%s%s\n" "$COLOUR" "$STATUS_LINE" "$RESET"
fi

# Current dive within the "Running dives" step: grep the wrapper log for
# the latest "[N/M] slug" banner emitted by run_website_dives.py. Also
# compute per-dive elapsed from the per-dive log's first line timestamp.
WRAPPER_LOG=$(ls -t "$LOG_DIR"/overnight_*.log 2>/dev/null | head -1)
LATEST_LOG=$(ls -t "$LOG_DIR"/20260419_*.log 2>/dev/null | grep -v overnight | head -1)

if [[ -n "$WRAPPER_LOG" ]]; then
    DIVE_BANNER=$(grep -E '\[[0-9]+/[0-9]+\] [a-z-]+' "$WRAPPER_LOG" 2>/dev/null | tail -1)
    if [[ -n "$DIVE_BANNER" ]]; then
        # Extract "[N/M] slug" portion
        DIVE_NM=$(echo "$DIVE_BANNER" | grep -oE '\[[0-9]+/[0-9]+\]' | head -1)
        DIVE_SLUG=$(echo "$DIVE_BANNER" | grep -oE '[a-z-]+-(great|ultra|master)-league' | head -1)

        # Per-dive elapsed: derive from the per-dive log's first-line timestamp
        DIVE_ELAPSED=""
        if [[ -n "$LATEST_LOG" && -f "$LATEST_LOG" ]]; then
            FIRST_TS=$(head -1 "$LATEST_LOG" | grep -oE '\[[0-9-]+ [0-9:]+' | tr -d '[')
            if [[ -n "$FIRST_TS" ]]; then
                FIRST_EPOCH=$(date -jf "%Y-%m-%d %H:%M:%S" "$FIRST_TS" +%s 2>/dev/null || echo "")
                if [[ -n "$FIRST_EPOCH" ]]; then
                    NOW=$(date +%s)
                    DIFF=$(( NOW - FIRST_EPOCH ))
                    if (( DIFF < 60 )); then DIVE_ELAPSED="${DIFF}s"
                    elif (( DIFF < 3600 )); then DIVE_ELAPSED="$((DIFF/60))m$((DIFF%60))s"
                    else DIVE_ELAPSED="$((DIFF/3600))h$(((DIFF%3600)/60))m"
                    fi
                fi
            fi
        fi

        printf "  %sDive %s%s%s %s%s%s  elapsed %s%s%s\n" \
            "$BOLD" "$CYAN" "$DIVE_NM" "$RESET" \
            "$BOLD" "${DIVE_SLUG:-?}" "$RESET" \
            "$GREEN" "${DIVE_ELAPSED:-?}" "$RESET"
    fi

    # Whole-script ETA: delegate to scripts/overnight_eta.py which buckets
    # dives by type (GL full / UL full / Forretress pinned), averages
    # completed dives per bucket with fallback baselines, and subtracts
    # the current-dive elapsed so the remaining number tracks forward.
    # Emits two lines on stdout; silent if the log can't be parsed yet.
    ETA_OUT=$(python3 "$REPO_ROOT/scripts/overnight_eta.py" "$WRAPPER_LOG" 2>/dev/null)
    if [[ -n "$ETA_OUT" ]]; then
        # Lines are tagged: SCRIPT: / DIVE: / BUCKETS:. Grep each
        # independently so reorderings in the Python emitter don't
        # break the box. DIVE: is optional (absent between dives).
        ETA_SCRIPT=$(echo "$ETA_OUT" | grep '^SCRIPT:' | sed 's|^SCRIPT: ||')
        ETA_DIVE=$(echo "$ETA_OUT" | grep '^DIVE:' | sed 's|^DIVE: ||')
        ETA_BUCKETS=$(echo "$ETA_OUT" | grep '^BUCKETS:' | sed 's|^BUCKETS: ||')

        # Script ETA is the headline number — bold bright magenta, the
        # answer to "when will this be done?".
        [[ -n "$ETA_SCRIPT" ]] && \
            printf "  %s► SCRIPT ETA: %s%s\n" "$ETA_ACCENT" "$ETA_SCRIPT" "$RESET"
        # Current-dive ETA sits under it in the same accent so the two
        # ETA lines read as a visual pair, with "dive" in cyan to echo
        # the Dive [N/M] header above.
        [[ -n "$ETA_DIVE" ]] && \
            printf "  %s  dive ETA: %s%s\n" "$CYAN" "$ETA_DIVE" "$RESET"
        [[ -n "$ETA_BUCKETS" ]] && \
            printf "    %s%s%s\n" "$DIM" "$ETA_BUCKETS" "$RESET"
    fi
fi
rule

# Latest per-dive log
LATEST_LOG=$(ls -t "$LOG_DIR"/20260419_*.log 2>/dev/null | grep -v overnight | head -1)
if [[ -n "$LATEST_LOG" && -f "$LATEST_LOG" ]]; then
    BASENAME=$(basename "$LATEST_LOG")
    MTIME=$(stat -f "%Sm" -t "%H:%M:%S" "$LATEST_LOG")
    # Dive age in seconds since mtime
    NOW=$(date +%s)
    MT=$(stat -f "%m" "$LATEST_LOG")
    AGE=$(( NOW - MT ))
    if (( AGE < 60 )); then AGE_STR="${AGE}s"; else AGE_STR="$((AGE/60))m$((AGE%60))s"; fi

    printf "  %sLatest dive log:%s %s\n" "$BOLD" "$RESET" "$BASENAME"
    printf "  %slast line %s ago%s\n" "$DIM" "$AGE_STR" "$RESET"

    # Current phase — the most recent non-progress banner. These lines
    # mark moveset / sweep / mirror-slayer-round boundaries and
    # otherwise scroll off within seconds as the progress-% updates
    # arrive. Pinning the latest match above the tail gives you the
    # "what coarse sub-step am I in" answer without waiting for the
    # next banner.
    PHASE=$(grep -E 'Phase [0-9]|Interactive sweep|Mirror slayer|iteration round|Simming' "$LATEST_LOG" 2>/dev/null | tail -1 | \
      sed -E 's|^\[[^]]+\] +[A-Z]+ +[a-z_]+: *||')
    if [[ -n "$PHASE" ]]; then
        # Truncate
        if (( ${#PHASE} > WIDTH - 12 )); then
            PHASE="${PHASE:0:$((WIDTH-15))}..."
        fi
        printf "  %sPhase:%s %s%s%s\n" "$BOLD" "$RESET" "$CYAN" "$PHASE" "$RESET"
    fi

    printf '%s\n' "$(printf '─%.0s' $(seq 1 $WIDTH))"

    # Show last 6 non-blank lines, each truncated to WIDTH
    tail -20 "$LATEST_LOG" 2>/dev/null | grep -v '^[[:space:]]*$' | tail -6 | \
      while IFS= read -r line; do
          # Strip the "[timestamp] LEVEL module:" prefix to save width
          clean=$(echo "$line" | sed -E 's|^\[[^]]+\] +[A-Z]+ +[a-z_]+: *||')
          # Truncate
          if (( ${#clean} > WIDTH - 4 )); then
              clean="${clean:0:$((WIDTH-7))}..."
          fi
          printf "  %s\n" "$clean"
      done
else
    printf "  %sNo per-dive log found yet.%s\n" "$DIM" "$RESET"
fi
rule

# Overnight wrapper log tail (last step boundary transitions)
WRAPPER_LOG=$(ls -t "$LOG_DIR"/overnight_*.log 2>/dev/null | head -1)
if [[ -n "$WRAPPER_LOG" ]]; then
    printf "  %sRecent step transitions:%s\n" "$BOLD" "$RESET"
    grep -E '\[STEP\]|\[DONE\]|\[FAIL\]|\[FATAL\]' "$WRAPPER_LOG" 2>/dev/null | tail -3 | \
      while IFS= read -r line; do
          clean=$(echo "$line" | sed -E 's|^[0-9-]+ ||')
          if (( ${#clean} > WIDTH - 4 )); then
              clean="${clean:0:$((WIDTH-7))}..."
          fi
          case "$clean" in
              *FAIL*|*FATAL*) COL=$RED ;;
              *DONE*)         COL=$GREEN ;;
              *STEP*)         COL=$YELLOW ;;
              *)              COL=$RESET ;;
          esac
          printf "  %s%s%s\n" "$COL" "$clean" "$RESET"
      done
fi
rule

# Recent products — the 5 most recently modified .html files under
# userdata/website/. During a dive the main index plus split-moveset
# files land here incrementally, so this is the "peek at partial
# output" surface. Each row is tagged "new" (modified during the
# current chain run) vs "pre" (older than chain start) so you can
# tell at a glance what this overnight chain has actually produced
# vs what was already sitting around from earlier work. Chain-start
# epoch comes from the wrapper-log filename timestamp, which is
# stable for the lifetime of the run.
HTML_ROOT="userdata/website"

CHAIN_START_EPOCH=""
if [[ -n "$WRAPPER_LOG" ]]; then
    BN=$(basename "$WRAPPER_LOG")
    # Expected: overnight_YYYYMMDD_HHMMSS.log
    if [[ "$BN" =~ overnight_([0-9]{4})([0-9]{2})([0-9]{2})_([0-9]{2})([0-9]{2})([0-9]{2})\.log ]]; then
        CHAIN_START_EPOCH=$(date -jf "%Y-%m-%d %H:%M:%S" \
            "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:${BASH_REMATCH[6]}" \
            +%s 2>/dev/null)
    fi
fi

if [[ -d "$HTML_ROOT" ]]; then
    MAX_PRODUCTS=10
    # Gather "mtime /path" rows sorted by mtime desc, then split into
    # new (>= chain start) and pre (< chain start) buckets. Prioritize
    # new in the display: show all new products (up to MAX_PRODUCTS),
    # fill any slack with pre so the list is still useful before the
    # chain has produced much. During an active run the box is
    # dominated by fresh output; between runs it falls back to "what
    # did I most recently build." Cap of 10 keeps the box from
    # dominating vertically.
    ALL_ENTRIES=$(find "$HTML_ROOT" -name '*.html' -type f -print0 2>/dev/null | \
        xargs -0 stat -f '%m %N' 2>/dev/null | sort -rn)
    NOW_EPOCH=$(date +%s)

    # Classify into new vs pre. Use a portable shell split (no awk
    # dependency on chain-start-epoch being set — skip the threshold
    # check when epoch is empty and treat everything as pre).
    NEW_ENTRIES=""
    PRE_ENTRIES=""
    while IFS= read -r ENTRY; do
        [[ -z "$ENTRY" ]] && continue
        MT="${ENTRY%% *}"
        if [[ -n "$CHAIN_START_EPOCH" && "$MT" -ge "$CHAIN_START_EPOCH" ]]; then
            NEW_ENTRIES+="${ENTRY}"$'\n'
        else
            PRE_ENTRIES+="${ENTRY}"$'\n'
        fi
    done <<< "$ALL_ENTRIES"

    # Build display list: all new (capped), then pre to fill remainder.
    NEW_COUNT=$(printf '%s' "$NEW_ENTRIES" | grep -c . || true)
    if (( NEW_COUNT >= MAX_PRODUCTS )); then
        DISPLAY=$(printf '%s' "$NEW_ENTRIES" | head -"$MAX_PRODUCTS")
    else
        PRE_FILL=$((MAX_PRODUCTS - NEW_COUNT))
        PRE_HEAD=$(printf '%s' "$PRE_ENTRIES" | head -"$PRE_FILL")
        DISPLAY="${NEW_ENTRIES}${PRE_HEAD}"
    fi

    printf "  %sRecent products:%s  %s(new: %d, shown: %d)%s\n" \
        "$BOLD" "$RESET" "$DIM" "$NEW_COUNT" \
        "$(printf '%s' "$DISPLAY" | grep -c . || true)" "$RESET"

    while IFS= read -r ENTRY; do
        [[ -z "$ENTRY" ]] && continue
        MT="${ENTRY%% *}"
        FP="${ENTRY#* }"
        AGE=$(( NOW_EPOCH - MT ))
        if   (( AGE < 60 ));   then AGE_STR="${AGE}s ago"
        elif (( AGE < 3600 )); then AGE_STR="$((AGE/60))m ago"
        else                         AGE_STR="$((AGE/3600))h$(((AGE%3600)/60))m ago"
        fi
        if [[ -n "$CHAIN_START_EPOCH" && "$MT" -ge "$CHAIN_START_EPOCH" ]]; then
            TAG="${GREEN}new${RESET}"
        else
            TAG="${DIM}pre${RESET}"
        fi
        REL="${FP#$REPO_ROOT/}"
        MAX=$((WIDTH - 18))
        if (( ${#REL} > MAX )); then
            REL="...${REL: -$((MAX-3))}"
        fi
        printf "  %s  %s%-9s%s  %s\n" "$TAG" "$DIM" "$AGE_STR" "$RESET" "$REL"
    done <<< "$DISPLAY"
    rule
fi

printf "  %srefresh: watch -n 5 -c scripts/overnight_status.sh%s\n" "$DIM" "$RESET"
