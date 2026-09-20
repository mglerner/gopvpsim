# Retired comparison pages

These TOMLs are kept but NO LONGER BUILT by any chain. They are still valid
inputs to `scripts/compare_loadouts.py` and can be run by hand if their source
dives are ever re-added to the dive list.

## Removed 2026-09-12 (Twilight Trails dive-list rebuild)

| TOML                          | missing source dive                          |
| ----------------------------- | -------------------------------------------- |
| `forretress-fast-move-shadow` | `forretress-shadow-volt-switch-great-league` |
| `jumpluff-regular-vs-shadow`  | `shadow-jumpluff-great-league`               |

Both dives were dropped from `scripts/dive_registry.py` when the opponent
pools were rebuilt for the Twilight Trails season, so `compare_loadouts.py`
raised `FileNotFoundError: No dive HTML in <dir> matches loadout ...` and took
the whole chain step with it.

**Correction, 2026-09-20 (pre-dive grid, lens 3).** That is no longer true of
Forretress. The 2026-09-17 pool rebuild put Forretress (Shadow) back in
`gl_top50_plus_cs.txt`, so `forretress-shadow-volt-switch-great-league`
derives again and is one of the registry's 136 dives -- the only reason
`forretress-fast-move-shadow` was retired is gone. It is ELIGIBLE to be
reinstated once that dive bakes, by the recipe below; it is deliberately NOT
reinstated here, because that is Michael's call and the dive has not baked
yet. `shadow-jumpluff-great-league` did not come back and
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
