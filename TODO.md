## What we've built

The core simulator now matches PvPoke's simulate-mode score table exactly (±0)
for all 9 shield scenarios. Simulate mode uses `always_shield` + `pvpoke_dp`
(ActionLogic.js DP for charged-move selection). The scripts `scripts/battle.py`
and `scripts/breakpoints.py` are implemented. `--pvpoke-scores` outputs scores
from p0's perspective, matching PvPoke's table format.

---

## Policies to add

* **PvPoke "Selective" baiting** — PvPoke's UI offers a bait toggle; "Selective"
  uses the same ActionLogic.js DP to decide *whether* baiting is worthwhile given
  current state (turnsToLive, bestChargedMove by DPE, minimumCycleThreshold).
  This is independent of simulate mode (which doesn't bait-toggle at all), but
  useful for modeling how PvPoke's recommended play differs from always-shield DP.

* **EV-based baiting** — our own novel policy: parameterize the bait decision by
  an estimated P(opponent shields). P≈0 → fire best-DPE move; P≈1 → bait with
  cheapest. Lets analysts model opponents with known shield tendencies.

* **Team/multi-mon simulation** (low priority) — currently only 1v1; real PvP
  is 3v3 with switching. Add team composition and switch-timing support.

---

## Analysis goals

* **Reproduce SwagTips-style IV deep dives** — articles like the old GamePress
  Carbink and Annihilape PvP IV deep dives (links dead; use Wayback Machine).
  Note: those articles used old move parameters, so we're reproducing the
  *method*, not the specific results. In the Pokemon Go Championship
  Series events, they post graphs of the most commonly used mons and
  their most common movesets. We can use that for our modern deep
  dives, to give us a good set of mons to test against. We should sim
  against those mons. We should also add a flag to our
  DEFAULT_THRESHOLDS to let us know if there are any there that we
  should sim against. When we're doing the competitive meta, we should
  probably sim all 4096 IVs of the competitive mons against the rank
  1s of the competitive mons. Then, when we find interesting IV
  targets, we add those to a list and also check against those. We can
  also do something like look through all 4096 IVs of each of the top
  100 PvP mons vs the common IVs of the competitive mons to see if
  there are any hidden corebreakers. When we're thinking about the
  main competitive mons, it's also worth knowing that people often
  REALLY want to win CAP ties with super common mons, so some atk
  weight is very common. It might be nice to suggest atk-weighted IVs
  for the super common mons.

* **Compare to reddit IV spectrum post** —
  https://www.reddit.com/r/TheSilphArena/comments/z11xr0/theorycrafting_iv_spectrum_graphs/
  Airtable links likely dead; imgur links should work. /u/RyanOfTheDay is Ryan
  Swag, the PvP IV OG — his comments in the thread are especially important.
  Again, move parameters have changed; reproduce the method, not the numbers.

* **Reproduce iv-tech channel analysis** from HSH's Discord.

---

## Testing / validation

* **More PvPoke battle-log comparison tests** — 1-HP discrepancies in HP threshold
  analysis (e.g., Medicham 1v2 flips at HP 139→140 in our sim vs 138 in deep dive)
  suggest subtle simulation differences (energy rounding, CMP resolution, move-timing
  edge cases). Add tests that compare our full battle timeline against PvPoke's battle
  log output for the same matchup/shield scenario, to identify and fix the divergence.
