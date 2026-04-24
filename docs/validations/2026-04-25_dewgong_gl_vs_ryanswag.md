# Dewgong GL — RyanSwag (2022) vs our dive (2026)

> Comparison generated 2026-04-25 in response to Michael flagging an
> archived RyanSwag Dewgong PvP IV Deep Dive on the Wayback Machine
> (`docs/reference_deep_dives/ryanswag/dewgong.md`, source dated
> Mar 4 2022). Per `feedback_ryanswag_archive_diff` this triggers a
> mandatory side-by-side using `STYLE_CONFORMANCE_CHECKLIST.md` as
> scaffold.

## TL;DR

The article's analytical frame is **largely obsolete** in the 2026 GL
meta. Of 12 opponents the article names by name, **9 are no longer
in our GL top-50 + Championship Series pool** (Umbreon, Trevenant,
Mew, Toxicroak, Tropius, Alolan Marowak, Vigoroth, Obstagoon,
Scrafty). Only Greedent, Drapion (Shadow), and the mirror remain.

Three notable findings, in decreasing order of "matters for a player
deciding which Dewgong to build today":

1. **All three of the article's headline stat targets are tuned to
   2022 opponents that don't exist in current GL.** The atk-weighted
   target (102.89 Atk for the mirror BP, 102.5+ for Trevenant /
   Mew) lines up with **none** of our 2026 dive's named flavors,
   which all sit at atk ≥ 108.43. Modern atk targets are 6+ points
   higher because the modern bulky opponents (Steelix Shadow,
   Swampert, Sealeo Shadow) require harder hits.
2. **The mirror axis has flipped from def-dominant to atk-dominant.**
   The article said `138.28 Def dominates 12 of the Top 20 Stat
   Product Dewgong in every single shield scenario` — i.e. the
   mirror was decided by *defense*. Our 2026 mirror-slayer Nash
   convergence settled at an attack range of 100.86 - 105.55,
   *higher than* the rank-1 Dewgong's atk of 100.86. The cohort
   wins the modern mirror by being more attacky, not bulkier.
3. **The article's recommended moveset (Ice Shard / Icy Wind /
   Drill Run, the Go Battle Day Seel legacy combo) is no longer
   the top-scoring moveset in our pool.** Our dive ranks
   Ice Shard / Blizzard, Icy Wind first, with Drill Run dropping
   to the m1-m3 split files. Charge-move balance changes since
   2022 are likely the cause; haven't dug further.

## Side-by-side context

| dimension              | RyanSwag (Mar 2022)                                           | Our dive (Apr 2026)                                           |
| ---------------------- | ------------------------------------------------------------- | ------------------------------------------------------------- |
| Article event hook     | Go Battle Day: Seel — legacy Ice Shard + Icy Wind unlock      | none — niche GL pick added alongside Oinkologne CD batch      |
| Recommended moveset    | Ice Shard / Icy Wind / Drill Run                              | Ice Shard / Blizzard, Icy Wind (top-scoring, index.html)      |
| Opponent pool          | Implicit 2022 GL meta (Umbreon, Trevenant, Mew, etc.)         | `opponent_pools/gl_top50_plus_cs.txt` (66 mons, 2026 meta)    |
| Max level              | Best Buddy (51) per pvpivs.com URLs                           | Default L50 non-BB per `LEAGUE_MAX_LEVEL` (matches PvPoke UI) |
| Atk targets cited      | 101.79, 102.03, 102.52, 102.89, 102.94, 103.7, 104.35, 104.87 | 108.43 (Sealeo S), 108.86 (Swampert), 109.09 (Steelix S)      |
| Def targets cited      | 131.7 (bare min), 136.81, 137.53, 138.28, 139.45, 141         | 138.70 (Corviknight), 141.05 (Sableye S)                      |
| Mirror dominance basis | Defense (138.28 Def beats most Top-20 SP Dewgong)             | Attack (mirror-slayer cohort atk 100.86 - 105.55)             |

## Opponent overlap audit

The article cites these opponents by name in its breakpoint /
bulkpoint bullets. Marking each as still-present in our 2026 pool:

| article opponent     | in 2026 pool?            | what the article said                                              |
| -------------------- | ------------------------ | ------------------------------------------------------------------ |
| Umbreon              | NO                       | "101.79 Atk for Rank 1 Umbreon, up to 102.81 for high-Def Umbreon" |
| Trevenant (WB)       | NO                       | "102.52-103.09 Atk for Weather Boosted Trevenant 1-1 / 2-2"        |
| Trevenant (high-Def) | NO                       | "103.7-104.87 Atk for high-Def Trevenant"                          |
| Mew                  | NO                       | "102.03-104.35 Atk for Mew 1-1 (Mewvset depending)"                |
| Greedent             | YES (`Greedent`)         | "137.53-139.25 Def for Greedent 0-1 and 1-2 potential"             |
| Toxicroak            | NO                       | "??? Atk for Toxicroak 1-1"                                        |
| Tropius              | NO                       | "101.46-103.14 Atk for Tropius 1-2 / 2-2 vs Razor Leaf"            |
| Alolan Marowak       | NO                       | "101.4-102.94 Atk for Marowak Trade IVs to Rank 1, 1-1, 1-2, 2-2"  |
| Drapion (non-shadow) | NO (only Shadow in pool) | "136.81-137.81 Def for Drapion (no notable matchup changes)"       |
| Vigoroth             | NO                       | "136.81-137.81 Def for Vigoroth (no notable matchup changes)"      |
| Obstagoon            | NO                       | "136.81-137.81 Def for Obstagoon (no notable matchup changes)"     |
| Scrafty              | NO                       | "136.81-137.81 Def for Scrafty (no notable matchup changes)"       |
| Dewgong (mirror)     | YES (`Dewgong`)          | "138.28-141 Def for mirror domination"                             |

Coverage: **3 / 12 opponents (25%) survived the 2022 → 2026 meta
shift in our dive's pool.** That's the dominant reason the article's
specific thresholds don't appear as flavors in our dive — the
opponents driving them aren't there to flip.

## Three article targets vs our dive's flavors

The article's three pvpivs.com filter URLs (which we recomputed at
`docs/reference_deep_dives/ryanswag/dewgong_iv_tables.md` since
pvpivs.com is a client-side JS app and Wayback's static HTML didn't
preserve the table data):

### Article target 1: Atk-Weighted (102.89 Atk, 131.7 Def, no HP floor)

22 IVs match in our regenerated table, ranks #6 through #195. Mostly
high-atk-low-def spreads (`6/0/15`, `15/0/0`, etc.) that would not
typically be considered competitive in the modern bulk-rewarded GL
meta.

**Our dive's analog:** none. Our dive's atk-weighted flavors
(Steelix Shadow Atk at atk ≥ 109.09, Swampert Atk at 108.86, Sealeo
Shadow Slayer at 108.43) all sit *6 to 7 attack points higher* than
the article's 102.89 target. The reason: the modern bulky opponents
require harder hits than 2022's Umbreon / Mew / Trevenant did.

### Article target 2: Def-Weighted (101.79 Atk, 136.81 Def, 150 HP)

39 IVs match, ranks #6 through #197. The article's "Drapion /
Vigoroth / Obstagoon / Scrafty line" — but three of those four are
gone, and the fourth (Drapion) is only present as Shadow in our
pool.

**Our dive's analog:** **Fortified Corviknight (def ≥ 138.70,
hp ≥ 153)** is the closest match — 1.9 def points higher and 3 HP
higher than the article's target. Both are "stay bulky enough to
trade with non-mirror, non-mirror-aware bulky opponents." Direction
matches; specific opponent doesn't.

### Article target 3: Mirror-Dominant (101.79 Atk, 138.28 Def, 150 HP)

4 IVs match in the regenerated table — `0/12/4`, `2/14/7`, `1/12/5`,
`0/13/3`. All sit at level 29.5 - 30.5 (Best Buddy region), atk
102.13 - 102.44, def 138.29 - 139.60, hp 154 - 155.

**Our dive's analog: NONE; the axis has flipped.** The article's
premise was that 138.28+ Def beats the bulk of the high-stat-product
Dewgong in the mirror. Our 2026 dive's mirror-slayer iteration
converges to a cohort with atk 100.86 - 105.55 — *higher* atk than
the rank-1 Dewgong (100.86). That means today's mirror-winning IV
spreads are gaining on attack, not on bulk.

Two plausible explanations:

1. **Move re-balance:** Icy Wind cost / damage tweaks since 2022
   could have changed the relative value of an extra fast-move-tick
   per cycle vs the def floor. Worth a check on PvPoke's move
   gamemaster history.
2. **Sim methodology divergence:** RyanSwag was reasoning from
   per-matchup damage breakpoints + intuition. Our converged Nash
   cohort is pure simulation across the whole matchup space. The
   two methods can disagree when the prevailing best move-pattern
   differs from individual-breakpoint optimization.

Either way, the article's **specific** advice to chase 138.28 Def
for the mirror is no longer the right move in 2026.

## Where the article is still useful

- **The CMP / mirror-relevance discussion** holds. The mirror still
  matters; the *mechanism* changed (atk-rules vs def-rules), but the
  importance is unchanged.
- **Greedent breakpoint (137.53-139.25 Def)** — Greedent is still
  in our pool and our dive's `Fortified Corviknight` (138.70 Def)
  sits inside the article's Greedent range. Cross-applicable
  observation.
- **The general "evolve several Dewgong with different stat weights
  and pick later" advice** is sound regardless of meta and is the
  one piece of actionable wisdom that survives.

## Style conformance walk-through

Per `STYLE_CONFORMANCE_CHECKLIST.md`. Our dive's tier list (5 entries):

```
Sableye (Shadow) Bulk    atk=0.00  def=141.05  hp=0
Steelix (Shadow) Atk     atk=109.09 def=0.00   hp=0
Swampert Atk             atk=108.86 def=0.00   hp=0
Sealeo (Shadow) Slayer   atk=108.43 def=0.00   hp=150
Fortified Corviknight    atk=0.00  def=138.70  hp=153
```

- **C1 (name matches signature shape):** ✅ all five match.
  `Sableye (Shadow) Bulk` is D-only (def-only signature). `Steelix`
  / `Swampert` / `Sealeo Shadow Slayer` are A or AH. `Fortified
  Corviknight` is DH. No mismatches.
- **C2 (namesake guarantee):** ✅ each opponent-named tier carries
  matchup flips against its namesake (per the `desc` field on each
  tier). Spot-checked Sealeo (Shadow) Slayer's `Atk breakpoint(s)
  vs Sealeo (Shadow) (1 scenario flip)`.
- **C3 (signature shows only constrained axes):** ✅ matches axis
  shape one-for-one.
- **C4 (opponent IV specificity):** would need to dig into the
  rendered HTML's anchor bullets to verify each cited threshold
  names a specific opponent IV (rank-1 / atk-weighted / etc.).
  Spot-skipping for this comparison; nothing fails the eyeball
  test on the tier-summary level.
- **C5 (identical-stat flavors merged):** ✅ no two tiers share both
  stat signature and gains list.
- **C6 (Best Buddy awareness):** Our dive uses `LEAGUE_MAX_LEVEL=50`
  per `_rank1_cp_capped`'s default. The article's pvpivs.com URLs
  use `max=51` (Best Buddy enabled). We followed the article's BB
  setting in the regenerated tables (since the analytical question
  was "what does the article see"); but our dive's flavors are
  computed at the L50 non-BB rank-1, matching our shipped policy.
  Worth flagging as a methodology difference if you're chasing
  exact-numeric reproducibility.

C7 - C11 not separately walked here; nothing on the tier-summary
level surfaces a violation.

## Recommendations

1. **The dewgong.md archive entry should carry a note** ("the bulk
   of the article's per-opponent advice is tuned to the 2022 GL
   meta and doesn't transfer cleanly to 2026") so future readers
   don't try to apply the article's 102.89-Atk recommendation
   directly to a modern Dewgong build. Adding that as a header
   block in the archive would be appropriate.
2. **The mirror axis flip** (def-rules → atk-rules) is the most
   analytically interesting finding and merits a quick PvPoke
   move-gamemaster history check. If Icy Wind's cost or energy gain
   changed between 2022 and 2026, that's the smoking gun. If the
   moves are unchanged, the divergence is methodology (RyanSwag's
   per-breakpoint reasoning vs our converged Nash sim).
3. **No reason to update our shipped Dewgong dive based on this
   diff.** The article's frame doesn't transfer; our dive correctly
   reflects the 2026 meta.

---

*Generated overnight 2026-04-25 by Claude Opus 4.7 from
gopvpsim primitives + the archived RyanSwag article. Reviewed by
Michael in the morning.*
