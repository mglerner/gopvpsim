# Retired comparison pages

These TOMLs are kept but NO LONGER BUILT by any chain. They are still valid
inputs to `scripts/compare_loadouts.py` and can be run by hand if their source
dives are ever re-added to the dive list.

## Removed 2026-09-12 (Twilight Trails dive-list rebuild)

| TOML                             | missing source dive                          |
| -------------------------------- | -------------------------------------------- |
| `forretress-fast-move-shadow`    | `forretress-shadow-volt-switch-great-league` |
| `jumpluff-regular-vs-shadow`     | `shadow-jumpluff-great-league`               |

Both dives were dropped from `scripts/dive_registry.py` when the opponent
pools were rebuilt for the Twilight Trails season, so `compare_loadouts.py`
raised `FileNotFoundError: No dive HTML in <dir> matches loadout ...` and took
the whole chain step with it.

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
