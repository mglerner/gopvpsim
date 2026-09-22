# Retired comparison pages

These TOMLs are kept but NO LONGER BUILT by any chain. They are still valid
inputs to `scripts/compare_loadouts.py` and can be run by hand if their source
dives are ever re-added to the dive list.

## Removed 2026-09-12 (Twilight Trails dive-list rebuild)

| TOML                          | source dive                                  | status of that dive |
| ----------------------------- | -------------------------------------------- | ------------------- |
| `forretress-fast-move-shadow` | `forretress-shadow-volt-switch-great-league` | BACK, and baked     |
| `jumpluff-regular-vs-shadow`  | `shadow-jumpluff-great-league`               | still missing       |

Both dives were dropped from `scripts/dive_registry.py` when the opponent
pools were rebuilt for the Twilight Trails season, so `compare_loadouts.py`
raised `FileNotFoundError: No dive HTML in <dir> matches loadout ...` and took
the whole chain step with it.

**Correction, 2026-09-20 (pre-dive grid, lens 3), updated 2026-09-22.** That
is no longer true of Forretress, and the remaining caveat has now cleared too.
The 2026-09-17 pool rebuild put Forretress (Shadow) back in
`gl_top50_plus_cs.txt`, so `forretress-shadow-volt-switch-great-league`
derives again and is one of the registry's 136 dives -- the only reason
`forretress-fast-move-shadow` was retired is gone. **The dive has since
baked**: `userdata/website/forretress-shadow-volt-switch-great-league/
index.html`, `rendered_at = "2026-09-21T07:31:13"` (engine `9ac12a2754a1`,
gamemaster `6d6e9a7bc32d`). So the comparison is now reinstatable by the
recipe below with nothing left to wait for -- it is still deliberately NOT
reinstated here, because that is **Michael's decision**, not a blocked
prerequisite. `shadow-jumpluff-great-league` did not come back and
`jumpluff-regular-vs-shadow` stays retired, as does
`oinkologne-male-vs-female` (the MALE Oinkologne did not return; only the
female did).

Michael's call (2026-09-12): fine not to carry these as standard. Removed from
`overnight_redive.sh` (steps 5 and 5a) and `phase2_preship.sh` rather than
patched, because the underlying dives are gone by choice, not by accident.

**To bring one back:** re-add the dive to `dive_registry.py`, bake it, then run
`python scripts/compare_loadouts.py comparisons/<slug>.toml`. Check the TOML's
`moveset_label` still matches what the dive actually bakes -- the rebalance
moved default movesets, and a stale label produces the same
`FileNotFoundError` even when the dive dir exists.

Still built by the chain: `aegislash-blade-vs-shield`,
`ninetales-regular-vs-shadow`.
