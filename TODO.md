## Battle simulator

* **Fix bestChargedMove selection** — Root cause of remaining 3 test failures.
  Replicate PvPoke's `move.damage` caching lifecycle so bestChargedMove
  defaults to cheapest move at init (matching PvPoke's undefined→NaN behavior).
  Needs focused session. See DEVELOPER_NOTES.md for details.

* **File PvPoke bug reports** — Two bugs found in PvPoke's JS:
  1. BattleState `.hp`/`.oppHealth` naming inconsistency (dead-code dominance checks)
  2. bestChargedMove using `move.damage` (undefined at init) instead of `move.power`

## Policies to add

* **PvPoke "Selective" baiting** — PvPoke's UI offers a bait toggle; "Selective"
  uses the same ActionLogic.js DP to decide *whether* baiting is worthwhile given
  current state (turnsToLive, bestChargedMove by DPE, minimumCycleThreshold).

* **Random buff/debuff** — For chance-based buffs (< 1), PvPoke uses a
  deterministic buffApplyMeter that fires every 1/chance activations. We should
  also support running many sims with random rolls, to find win conditions
  (e.g. if first Air Cutter boosts, you win, otherwise you lose). Options:
  deterministic (current), random, always-hit, never-hit, double-boost.

* **EV-based baiting** — our own novel policy: parameterize the bait decision by
  an estimated P(opponent shields). P~0 → fire best-DPE move; P~1 → bait with
  cheapest.

## Tests to add

* **Shadow pokemon** — verify shadow mons correctly do more damage and take more.

* **Both mons with buff/debuff** — e.g. Corviknight mirror with Air Cutter +
  Payback on both sides.

* **Form Change** — Morpeko. Low priority.

* **Default movesets** — figure out why we don't default to PvPoke's default
  movesets and fix it. Important for deep dive defaults.

## Analysis goals

* **Reproduce SwagTips-style IV deep dives** — articles like the old GamePress
  Carbink and Annihilape PvP IV deep dives. Use Pokemon Go Championship Series
  event data (most common mons/movesets) as the modern test pool. Sim all 4096
  IVs of competitive mons against rank 1s, find interesting IV targets, check
  for hidden corebreakers. Consider atk-weighted IVs for CMP tie priority.

* **Compare to reddit IV spectrum post** —
  https://www.reddit.com/r/TheSilphArena/comments/z11xr0/theorycrafting_iv_spectrum_graphs/
  Reproduce the method (move parameters have changed since then).

* **Reproduce iv-tech channel analysis** from HSH's Discord.

## Low priority

* **Team/multi-mon simulation** — currently only 1v1; real PvP is 3v3 with
  switching. Add team composition and switch-timing support.
