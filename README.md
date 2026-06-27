# gopvpsim - Pokemon GO PvP battle simulator

A pure-Python Pokemon GO PvP battle simulator focused on breakpoint and
bulkpoint analysis. It powers a set of CLI tools and a static website of
interactive IV / moveset "deep dives" that show which IV spreads cross which
damage thresholds against the meta.

## Built on PvPoke

This project is built on [PvPoke](https://pvpoke.com)
([source](https://github.com/pvpoke/pvpoke)), created by Empoleon_Dynamite and
released under the MIT license. The battle simulator in `src/gopvpsim/battle.py`
is a Python port of PvPoke's open-source battle logic, and all game data (the
gamemaster, move stats, the type chart, and the meta rankings) is fetched from
PvPoke. Scores are cross-checked against PvPoke's own simulate-mode engine.
**This project would not exist without PvPoke.** Please support and credit it.

## Divergences from PvPoke

Our scores match PvPoke's almost everywhere (the oracle audit in
`scripts/audit_oracle_harness.py` is exact on score, winner, and charged-move
log for the large majority of its cells). The simulator is a faithful port;
the handful of intentional differences below each have a reason and a pinned
test or documented guard, and the full root-cause writeups live in
`DEVELOPER_NOTES.md`. These all apply to the default (legacy) turn mechanics.

1. **Best charged move is recomputed every turn, not cached at battle start.**
   PvPoke picks each Pokemon's best charged move once at init and reuses it. We
   recompute it each decision, so it tracks mid-battle changes in the
   opponent's defense (stat-stage drops, or a form change like Aegislash
   Shield -> Blade). PvPoke's cached pick is a worse choice in the
   Aegislash matchups.
2. **Morpeko toggles form on every charged move.** The game, and Morpeko's own
   gamemaster entry, toggles Full Belly <-> Hangry after each charged move.
   PvPoke changes it one way and then sticks in Hangry. Ours matches verified
   in-game behavior.
3. **Aegislash throws Shadow Ball where PvPoke throws Gyro Ball.** Same energy
   cost, but Shadow Ball does strictly more damage against Azumarill, so
   PvPoke's Gyro Ball pick scores lower for itself.
4. **Near-KO plan choice: one big self-debuffing move vs a chain of cheaper
   moves.** In a shields-down endgame our attacker prefers the single nuke
   where PvPoke sometimes prefers a chain of cheaper non-debuffing throws. Ours
   keeps 23 to 30 percentage points more HP in 6 of 7 measured cases (which
   matters for the next Pokemon on a team) and loses one close bulky-defender
   fight, which is pinned as an xfail. Neither plan is universally right.
5. **Battle-length guard.** PvPoke ends a fight on a 240-second display clock
   that mixes turn time with charged-move animation time; ours is a flat
   500-turn cap. Both are infinite-loop guards and neither is reachable in a
   real 1v1, so the simpler guard costs nothing observable.

We also deliberately do NOT replicate one block of PvPoke's decision code (its
non-guaranteed-buff "needsBoost" plan selection): that code is disabled
upstream and never runs, so copying it would make us diverge from PvPoke's
actual behavior rather than match it.

The experimental `mechanics='new'` mode (the 2026-06-23 in-game turn changes)
is OFF by default. PvPoke has not implemented those changes, so there is no
reference to validate it against; everything above and every published score
uses the legacy turn system, which is what matches PvPoke.

### Keeping this list current

- **When you add or remove a divergence, update this section and
  `DEVELOPER_NOTES.md` together.** The `CLAUDE.md` policy ("When our sim
  diverges from PvPoke") already requires every divergence to carry an xfail
  test with a specific reason and an inline code comment; this section is the
  human-readable index of those.
- **Re-vet against PvPoke upstream periodically.** PvPoke's battle logic lives
  in `Battle.js`, `ActionLogic.js`, and `DamageCalculator.js`. We last vetted
  against pvpoke commit `bc532fbda` (2026-06-06; see the "PvPoke re-vetting
  log" in `DEVELOPER_NOTES.md`). On a regular cadence, and before any release
  that quotes PvPoke parity, diff those three files against the last vetted
  commit; if the battle logic changed, re-run the oracle audit
  (`scripts/audit_oracle_harness.py`), then update this list and the
  re-vetting log.

## Built with Claude

This codebase makes heavy use of [Claude](https://www.anthropic.com/claude)
(Anthropic's Claude Code). A large share of the code, tests, documentation, and
analysis tooling was written collaboratively with Claude. Commits authored with
Claude carry a `Co-Authored-By` trailer.

## Layout

- `src/gopvpsim/` - the core library (pure Python): `data.py` (game-data fetch
  + cache), `pokemon.py` (stats / CP / IVs), `moves.py` (damage + type chart),
  `battle.py` (the simulation loop), `breakpoints.py` (threshold analysis).
- `scripts/` - CLI tools and the deep-dive / article / website renderers
  (these may use numba etc. for speed).
- `thresholds/`, `articles/`, `guides/` - data + narrative sources that render
  into the public site.
- `tests/` - battle-correctness tests verified against PvPoke ground truth.

## Setup

Requires Python 3.13+. The environment is `uv`-managed:

```
uv venv
uv pip install -e ".[dev,perf]"
direnv allow
```

See `CLAUDE.md` ("Running Python") for how `python` resolves in different
shells, and the docstrings / `docs/` for the analysis vocabulary
(`docs/concepts.md`) and file formats.

## License

This project is released under the MIT license (see `LICENSE`), Copyright (c)
2026 Michael G. Lerner. PvPoke, on which this project is built, is independently
MIT-licensed and Copyright its own authors (Empoleon_Dynamite); see
[its repository](https://github.com/pvpoke/pvpoke) for details.
