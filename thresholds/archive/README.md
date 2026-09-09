# Archived spreads

**58 STAT-CUTOFF spreads**, retired 2026-09-09 when the Twilight Trails move
rebalance invalidated them. **Nothing loads this directory** — the threshold
loader globs `thresholds/*.toml`, which does not recurse, so these files are
inert by construction rather than by convention.

## What was retired, and what was kept

The 74 authored spreads split cleanly on a line that matters more than
"human-sourced":

| kind | what it is | rebalance | count |
| ------------ | ------------------------------------------------ | ----------- | ----- |
| stat-cutoff  | a DERIVED threshold ("143.03 def flips Azu 1-2") | invalidated | **58 retired** |
| IV-list      | a named IV combo someone actually runs           | untouched   | **15 kept live** |

A derived cutoff is only true against a specific opponent kit, so a move change
can move it. An IV combo is an **observed fact** — `[[7, 15, 14]]` is what a
player runs, and no move rebalance rewrites it. Most IV-list spreads exist as
CMP (Charge Move Priority — the attack-stat tiebreaker when both players fire a
charged move on the same turn) reference targets, and CMP is decided by attack
stat alone, with moves playing no part at all.

One stat-cutoff spread was kept live: Azumarill's `"Slight Atk"`, because the
`cmp_vs_slight_atk` anchor resolves against it. Its *bulk* cutoffs are as stale
as the rest — only the attack figure the CMP anchor reads is still meaningful.
Re-derive it with the other 58.

Retiring all 74 was the first plan, and the dangling references caught it: four
CMP anchors (`annihilape`, `azumarill`, `medicham`, `sylveon`) stopped
resolving, which is what exposed that some spreads are live infrastructure
rather than published claims.

## Why they were retired

A spread cutoff is the stat at which a specific matchup flips, which makes it
true only against a specific opponent kit. The rebalance changed a move in the
default moveset of **32 of the 86 opponents** named across the threshold files,
so most cutoffs no longer land on a real breakpoint.

Staleness was not the strongest reason. 579 of these entries carry a `source`
field, most pointing at HomeSliceHenry's Discord. Keeping them live would have
left a named community member's attribution attached to numbers the rebalance
had made wrong.

Within the stat-cutoff group, retirement was deliberately **all** of them
rather than the provably-stale subset. 65 of the 74 were provably suspect; the
remaining 9 came back clean only because the check resolved default movesets in
Great league, and `baxcalibur` is not a Great-league file. Unverified is not the
same as safe.

## What is worth keeping here

The numbers are disposable. The `description` fields are not:

    attack = 0 / defense = 143.03 / stamina = 138
    description = "Premium bulk: Azu bulkpoint + Medicham survival + all
                   lower def checks."

`143.03` is dead. *"Azu bulkpoint + Medicham survival + all lower def checks"*
is a **specification** — it re-derives mechanically once a bake recomputes
those anchors, and it encodes the human judgment about which thresholds matter,
which is the part that cannot be regenerated. Read these files as a work queue.

Some specs will survive the round trip unchanged: Azumarill's kit is untouched
(`BUBBLE`, `ICE_BEAM`, `PLAY_ROUGH` all unchanged), so a spec whose components
are all Azu-derived re-derives to the same number.

## Reconstructing the engine they were true under

Each archived file carries this in its own header, repeated here:

| | |
| --------------- | ----------------------------------------------------------- |
| pvpoke commit   | `79d04af74` (last vetted pre-rebalance)                      |
| turn system     | **legacy** — the live game stopped running it on 2026-09-02  |
| gamemaster      | `cd ~/coding/pvpoke && git show 79d04af74:src/data/gamemaster.json` |
| our engine      | repo `fba4d4c`; engine-hash files are `battle.py`, `_dp_jit.py`, `moves.py`, `formchange.py`, `pokemon.py` |

The turn system is the easy one to miss. These came from community in-game
testing under the **legacy** clock, so re-deriving one needs both the old
gamemaster and `--mechanics legacy`. A number reproduced under only one of the
two is not a reproduction.

## Downstream

`../gobattlekit/tools/threshold_export/export_thresholds.py` reads
`league_thresholds.spreads` to build its expert targets. With spreads empty it
degrades gracefully (`expert_targets(spreads_lt) if spreads_lt else []`) and
the bundled schema is unchanged, but the app ships **no** expert targets until
new spreads are derived.
