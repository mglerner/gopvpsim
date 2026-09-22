# Retired comparison pages

These TOMLs are kept but NO LONGER BUILT by any chain. They are still valid
inputs to `scripts/compare_loadouts.py` and can be run by hand if their source
dives are ever re-added to the dive list.

## Removed 2026-09-12 (Twilight Trails dive-list rebuild)

| TOML                          | source dive                                  | status of that dive                |
| ----------------------------- | -------------------------------------------- | ---------------------------------- |
| `forretress-fast-move-shadow` | `forretress-shadow-volt-switch-great-league` | dive back; TOML REMOVED 2026-09-22 |
| `jumpluff-regular-vs-shadow`  | `shadow-jumpluff-great-league`               | still missing                      |

Both dives were dropped from `scripts/dive_registry.py` when the opponent
pools were rebuilt for the Twilight Trails season, so `compare_loadouts.py`
raised `FileNotFoundError: No dive HTML in <dir> matches loadout ...` and took
the whole chain step with it.

**Decision, 2026-09-22 (Michael): the Forretress comparison is REMOVED, not
parked.** `forretress-fast-move-shadow.toml` is deleted from this directory
(recoverable from git history at 3206ba4). Its source dive is back in the
registry and baked, so the page could be rebuilt any time; it comes back only
if the Volt Switch vs Bug Bite split turns out to matter in the current
season. `shadow-jumpluff-great-league` did not come back and
`jumpluff-regular-vs-shadow` stays retired.

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
