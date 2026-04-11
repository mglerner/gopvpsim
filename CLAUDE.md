# PoGo PvP Battle Simulator

## Session startup
At the start of every new session, before doing other work, read these
files so you have current context on what's planned, what's broken, and
what's been verified:

- `TODO.md` — pending features, known bugs, design notes for upcoming work
- `DEVELOPER_NOTES.md` — verification status, PvPoke comparison results,
  known bugs we've found in PvPoke

You don't need to re-read them every turn — once per session is enough.
Mention briefly in your first substantive reply that you've read them
(e.g., "Caught up on TODO.md and DEVELOPER_NOTES.md.") so the user
knows the startup happened.

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
- Core `gopvpsim/` library is pure Python (keeps mobile option open).
  Deep dive scripts (`scripts/`) may use numba/Cython/C extensions for speed.
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
- **Default movesets** — when a test or sim needs "the default moveset" for a
  species in a given league, ALWAYS call `gopvpsim.data.get_default_moveset(
  species, league, shadow=False)` which reads PvPoke's rankings file. Never
  guess from the gamemaster's `fastMoves`/`chargedMoves` lists — those are
  the legal-move *pool* (everything the species can learn), not PvPoke's
  meta recommendation. Guessing from the pool silently produces off-meta
  movesets that look plausible but don't match PvPoke's UI defaults, which
  turns oracle tests against reference writeups into noise. (Learned the
  hard way 2026-04-12 on the Corviknight vs Shadow Sableye oracle test.)

## Documentation
- `docs/concepts.md` — vocabulary used in deep-dive HTML outputs and threshold files
  (spread, anchor, slayer category, breakpoint, bulkpoint, CMP). Read this first.
- `docs/threshold_schema.md` — TOML schema for `thresholds/*.toml` files. Assumes
  familiarity with `concepts.md`.
- `DEVELOPER_NOTES.md` — verification status, PvPoke comparison, bugs found.
- `docs/validations/` — point-in-time experiment writeups.

## Markdown formatting
All `*.md` files in this project should be formatted by `scripts/format_md.py`,
which keeps them readable in a raw text editor (currently: pads pipe-table cells
so columns line up). A PostToolUse hook in `.claude/settings.json` runs it
automatically after Edit/Write/MultiEdit. To format manually: `python
scripts/format_md.py [FILE ...]` (no args = walk the whole repo). The script is
idempotent.

## Out of scope for now
Adaptive/game-tree search (minimax). Web app UI.
