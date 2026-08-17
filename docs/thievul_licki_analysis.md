# Thievul vs Licki IV-robustness analysis (2026-08-16 CD)

Contract + runbook for the `thievul_licki_*` one-off pipeline: full
4096x4096 IV joint grids of Thievul vs the Licki line, built for the
Nickit Community Day "IV tech" question from the HSH discord ("is
6/15/5 the best spread for the Sucker Punch bp on Licki?" / "do you not
want 15 hp"). Human-guided, AI-generated (Claude); every published
number is machine-computed and was adversarially verified (independent
re-sims incl. cells replayed through PvPoke's own JS engine via
`scripts/pvpoke_trace.js`).

## The two opponents ("Licki" is ambiguous)

- **Lickilicky** (GL #1, Rollout / Body Slam + Shadow Ball, L21-24.5
  spreads) -- the meta-relevant reading and the PRIMARY page. The
  matchup is close: 1-1 is nearly literally the Sucker Punch 6->7
  breakpoint (Thievul atk >= ~122.04 vs the rank-1).
- **Lickitung** (GL ~#124, Lick / Body Slam + Power Whip, XL L44.5-50
  spreads) -- the secondary page. With SP/IW+PR + baiting, every
  Thievul IV beats every Lickitung IV whenever Thievul holds >= 1
  shield; IV choice only matters shields-down.

Published pages: `thievul-lickilicky-robustness.html` and
`thievul-lickitung-robustness.html` (root-level in the website tree;
local working copies in `userdata/dives/`). Data + per-run design
contract: `userdata/thievul_licki*/` (gitignored; see DESIGN.md there).

## Pipeline (5 steps, in order)

Pre-existing inputs: the dive replay blob
`userdata/replay/20260815_183454_Thievul_great.replay.pkl.gz` (meta
wins source) and the PINNED gamemaster in `~/Documents/gopvpsim_cache/`
(hash `8f1d6cca5c0f`; the grids were baked against it -- a TTL refetch
pulls a drifted blob and the builder aborts on axis mismatch).

    direnv exec . python scripts/thievul_licki_bake.py --opponent lickilicky --workers 14
    direnv exec . python scripts/thievul_licki_meta.py            # + --verify
    direnv exec . python scripts/thievul_licki_breakpoints.py --opponent lickilicky
    direnv exec . python scripts/thievul_licki_assemble.py --opponent lickilicky
    direnv exec . python scripts/build_thievul_licki_page.py --data-dir userdata/thievul_lickilicky

Same commands with `--opponent lickitung` / the lickitung data dir for
the secondary page. `meta_wins.npz` is opponent-independent and lives
with the lickitung dataset. The bake reuses the Worlds robustness core
(`deep_dive_lib/robustness.plane_task_worker`, signature dedup,
`worlds_planes` packing); win = pvpoke score > 500 strict; both axes in
canonical `iv_rank` stat-product order.

## Conventions the pages must keep (verification-derived)

- Scenario classification is three-way and computed per grid with the
  rule stated on-page: saturated-win / hopeless / sensitive.
- Every coverage number carries cohort AND moveset+bait labels; "best"
  picks disclose their tiebreak chain and tie counts.
- User CSV (Poke Genie) analysis is strictly client-side -- no
  collection data is ever baked into the published HTML.
- ICY_WIND is injected (CD move; the pinned gamemaster predates it) --
  disclosed on-page with both gamemaster hashes.
