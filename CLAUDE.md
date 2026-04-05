# PoGo PvP Battle Simulator

## Project goal
A pure Python library for Pokemon Go PvP battle simulation, focused on
breakpoint/bulkpoint analysis. Will be used by CLI scripts and eventually
a BeeWare mobile app.

## Architecture
- `data.py` — load and cache PvPoke's gamemaster.json
- `pokemon.py` — stat calculation (CP, level, IV, stat product)
- `moves.py` — move data, damage formula, type effectiveness
- `battle.py` — battle simulation loop with pluggable shield/bait policies
- `breakpoints.py` — breakpoint and bulkpoint analysis

## Key design decisions
- Pure Python, no C extensions (BeeWare/iOS compatibility)
- Data sourced from PvPoke's open-source JSON (github.com/pvpoke/pvpoke)
- Battle policies are pluggable — shield decisions, bait decisions, and
  charge move timing are separate from the core simulation loop
- Damage formula: floor(0.5 * 1.3 * Power * Atk/Def * Effectiveness * STAB) + 1
  (the 1.3 is PvPoke's global PvP bonus multiplier; chargeMultiplier=1 in simulation)
- Validate all stat calculations against PvPoke before writing battle logic

## Charge move timing
Always finish current fast move before throwing a charge move (don't waste turns).
Charge move timing policy is pluggable.

## Baiting
Start with fixed heuristic (throw cheap move first). Later: EV-based baiting
parameterized by opponent shield probability.

## Shielding
Pluggable policy. Simulate all three shield scenarios (0-0, 1-1, 2-2).

## CLI scripts
- `scripts/battle.py` — simulate a 1v1 matchup across all 9 shield scenarios
  Flags: `--stats`, `--show-damage`, `--trace-dp`, `--trace-shields`, `--debug`, `--pvpoke-scores`
- `scripts/breakpoints.py` — show breakpoints/bulkpoints for a given attacker/move/defender

## Testing
- `python -m pytest tests/test_battle.py -q` — run all battle tests (99/102 passing)
- Tests verify scores against PvPoke ground truth from pvpoke.com/battle/

## Out of scope for now
Adaptive/game-tree search (minimax). Web app UI.
