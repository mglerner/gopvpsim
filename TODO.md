Extra items on my TODO list

* See if we can reproduce an article like the old SwagTips PVP IV Deep dives. Some recent ones were https://gamepress.gg/pokemongo/carbink-pvp-iv-deep-dive and https://gamepress.gg/pokemongo/annihilape-pvp-iv-deep-dive ... though those links are dead and we'll have to use the wayback machine to get the articles. We need to remember that the actual results from those deep dives will be wrong, as the movesets and move parameters have been updated several times since those were written.

* Implement PvPoke's full dynamic programming charged-move AI (ActionLogic.js). Currently 3 shield scenarios (0v0, Med2vAzu1, Med2vAzu2) are xfailed because our simple heuristics can't match PvPoke's DP-based bestChargedMove sequencing. The DP considers turnsToLive, minimumCycleThreshold, and optimal move sequences rather than greedy per-turn decisions.

* DONE: Add code to think about throwing on optimal timing. Implemented as the optimal_timing charged-move policy in battle.py. Uses the OPTIMAL_TIMING lookup table (keyed on your_fast_turns × their_fast_turns) to fire only at the correct fast-move counts within each charge cycle. Falls back to pvpoke_ai for move selection. As noted, this can lead to losses vs always-fire policies due to extra fast-move damage taken while waiting.

* Allow mons to start a battle with some energy. There are lots of scenarios where, e.g., you win if you are ahead by one or two fast moves ... but lose otherwise.

* Write CLI scripts: scripts/battle.py (simulate a 1v1 matchup and report results across all shield scenarios) and scripts/breakpoints.py (show breakpoints/bulkpoints for a given attacker/move/defender). These are already documented in CLAUDE.md but not yet implemented.

* Implement PvPoke's "Selective" baiting policy: this is the same DP algorithm from ActionLogic.js described above (see the DP TODO item). In PvPoke's UI, "Selective" is the bait toggle setting that uses DP to decide when baiting is worthwhile given the current battle state (turnsToLive, bestChargedMove by actual DPE, minimumCycleThreshold). Resolving the 3 xfailed test scenarios depends on this.

* Add EV-based baiting policy (separate from PvPoke's Selective): parameterize the bait decision by an estimated probability P(opponent shields). If P(shield) ≈ 0, skip the bait and fire best-DPE move; if P(shield) ≈ 1, bait with cheapest. This is our own novel approach, independent of PvPoke's DP.

* Support Shadow Pokemon: shadow multipliers are x1.2 attack and x0.833 defense. This is a major factor in PvP and affects breakpoints/bulkpoints significantly.

* IV ranking: compute rank 1, rank 2, etc. across all 4096 IV combinations (0-15 in each stat) by stat product at best level. This is a core use case -- breakpoint analysis is most useful when you know which IVs are actually attainable and how they rank.

* Team/multi-mon simulation (low priority): currently only 1v1; real PvP is 3v3 with switching. Add support for team composition and switch timing.
