#!/usr/bin/env bash
# Re-dive every species currently published on the website so the
# shipped HTMLs pick up engine-code changes (new DATA fields, new
# columns, hover fixes, etc.). Chained with && per the serial-dives
# policy (CPU-saturating; do NOT run two in parallel).
#
# Usage:
#     scripts/redive-shipped.sh                 # 12 dives, ~8 hours
#     scripts/redive-shipped.sh --publish       # re-dive, then
#                                               # scripts/publish_website.sh --push
#
# Monitor from a second terminal:
#     tail -f userdata/logs/latest.log
#
# If a dive fails the `&&` chain aborts and subsequent dives are
# skipped -- fix the failure, re-run. Each dive's HTML writes
# atomically so a partial re-dive leaves the prior dive intact.
#
# Canonical invocations pulled from the most recent successful log
# per species (2026-04-22). Keep in sync when you change the canonical
# flags for a dive.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PUBLISH=false
for arg in "$@"; do
  case "$arg" in
    --publish) PUBLISH=true ;;
    *) echo "error: unknown arg '$arg'" >&2; exit 2 ;;
  esac
done

START=$(date +%s)
echo "=== redive-shipped starting at $(date) ==="
echo "12 dives chained with &&. Live tail: tail -f userdata/logs/latest.log"
echo

WEBSITE="userdata/website"
GL_POOL="opponent_pools/gl_top50_plus_cs.txt"
UL_POOL="opponent_pools/ul_top60_plus_aegislash.txt"
CS_POOL="opponent_pools/cs_2026_orlando_top32.txt"

SLAYER_FLAGS="--mirror-slayer --mirror-slayer-metric all --mirror-slayer-rounds 4 --mirror-slayer-pool 30 --mirror-slayer-show 20"
COMMON="--shield-scenario 1,1 --opp-ivs both --interactive --standalone --split-movesets --bait both --reserve-cpus 1 $SLAYER_FLAGS"

# 1. Tinkaton GL
python scripts/deep_dive.py Tinkaton \
  --league great --opponents 20 --opponents-file "$GL_POOL" \
  --top-movesets 5 \
  --reference FAIRY_WIND,BULLDOZE,PLAY_ROUGH \
  --html "$WEBSITE/tinkaton-great-league/index.html" \
  $COMMON \
&& \
# 2. Tinkaton UL
python scripts/deep_dive.py Tinkaton \
  --league ultra --opponents 20 --opponents-file "$UL_POOL" \
  --top-movesets 5 --no-thresholds \
  --reference auto \
  --html "$WEBSITE/tinkaton-ultra-league/index.html" \
  $COMMON \
&& \
# 3. Oinkologne GL
python scripts/deep_dive.py Oinkologne \
  --league great --opponents 20 --opponents-file "$GL_POOL" \
  --top-movesets 5 \
  --reference TACKLE,BODY_SLAM,TRAILBLAZE \
  --html "$WEBSITE/oinkologne-great-league/index.html" \
  $COMMON \
&& \
# 4. Oinkologne (Female) GL
python scripts/deep_dive.py 'Oinkologne (Female)' \
  --league great --opponents 20 --opponents-file "$GL_POOL" \
  --top-movesets 5 \
  --reference TACKLE,BODY_SLAM,TRAILBLAZE \
  --html "$WEBSITE/oinkologne-female-great-league/index.html" \
  $COMMON \
&& \
# 5. Aegislash Blade GL
python scripts/deep_dive.py 'Aegislash (Blade)' \
  --fast PSYCHO_CUT --charged SHADOW_BALL,GYRO_BALL \
  --league great --opponents 20 --opponents-file "$CS_POOL" \
  --top-movesets 5 --no-thresholds \
  --reference PSYCHO_CUT,SHADOW_BALL,GYRO_BALL \
  --html "$WEBSITE/aegislash-blade-great-league/index.html" \
  $COMMON \
&& \
# 6. Aegislash Shield GL (pinned moveset, top-movesets 1)
python scripts/deep_dive.py 'Aegislash (Shield)' \
  --fast AEGISLASH_CHARGE_PSYCHO_CUT --charged SHADOW_BALL,GYRO_BALL \
  --league great --opponents 20 --opponents-file "$CS_POOL" \
  --top-movesets 1 --no-thresholds \
  --reference AEGISLASH_CHARGE_PSYCHO_CUT,SHADOW_BALL,GYRO_BALL \
  --html "$WEBSITE/aegislash-shield-great-league/index.html" \
  $COMMON \
&& \
# 7. Aegislash Blade UL
python scripts/deep_dive.py 'Aegislash (Blade)' \
  --fast PSYCHO_CUT --charged SHADOW_BALL,FLASH_CANNON \
  --league ultra --opponents 20 --opponents-file "$UL_POOL" \
  --top-movesets 5 --no-thresholds \
  --reference PSYCHO_CUT,SHADOW_BALL,FLASH_CANNON \
  --html "$WEBSITE/aegislash-blade-ultra-league/index.html" \
  $COMMON \
&& \
# 8. Aegislash Shield UL (top-movesets 5, default moveset discovery)
python scripts/deep_dive.py 'Aegislash (Shield)' \
  --league ultra --opponents 20 --opponents-file "$UL_POOL" \
  --top-movesets 5 --no-thresholds \
  --reference AEGISLASH_CHARGE_PSYCHO_CUT,SHADOW_BALL,FLASH_CANNON \
  --html "$WEBSITE/aegislash-shield-ultra-league/index.html" \
  $COMMON \
&& \
# 9. Forretress GL (Bug Bite)
python scripts/deep_dive.py Forretress \
  --fast BUG_BITE --charged SAND_TOMB,ROCK_TOMB \
  --league great --opponents 20 --opponents-file "$CS_POOL" \
  --top-movesets 1 --no-thresholds \
  --reference BUG_BITE,SAND_TOMB,ROCK_TOMB \
  --html "$WEBSITE/forretress-bug-bite-great-league/index.html" \
  $COMMON \
&& \
# 10. Forretress GL (Volt Switch)
python scripts/deep_dive.py Forretress \
  --fast VOLT_SWITCH --charged SAND_TOMB,ROCK_TOMB \
  --league great --opponents 20 --opponents-file "$CS_POOL" \
  --top-movesets 1 --no-thresholds \
  --reference VOLT_SWITCH,SAND_TOMB,ROCK_TOMB \
  --html "$WEBSITE/forretress-volt-switch-great-league/index.html" \
  $COMMON \
&& \
# 11. Forretress Shadow GL (Bug Bite)
python scripts/deep_dive.py Forretress \
  --fast BUG_BITE --charged SAND_TOMB,ROCK_TOMB --shadow \
  --league great --opponents 20 --opponents-file "$CS_POOL" \
  --top-movesets 1 --no-thresholds \
  --reference BUG_BITE,SAND_TOMB,ROCK_TOMB \
  --html "$WEBSITE/forretress-shadow-bug-bite-great-league/index.html" \
  $COMMON \
&& \
# 12. Forretress Shadow GL (Volt Switch)
python scripts/deep_dive.py Forretress \
  --fast VOLT_SWITCH --charged SAND_TOMB,ROCK_TOMB --shadow \
  --league great --opponents 20 --opponents-file "$CS_POOL" \
  --top-movesets 1 --no-thresholds \
  --reference VOLT_SWITCH,SAND_TOMB,ROCK_TOMB \
  --html "$WEBSITE/forretress-shadow-volt-switch-great-league/index.html" \
  $COMMON

END=$(date +%s)
ELAPSED=$((END - START))
printf "\n=== all 12 dives complete in %dh %dm %ds (at %s) ===\n" \
  $((ELAPSED/3600)) $(((ELAPSED%3600)/60)) $((ELAPSED%60)) "$(date)"

if [ "$PUBLISH" = true ]; then
  echo
  echo "=== publishing with scripts/publish_website.sh --push ==="
  scripts/publish_website.sh --push
fi
