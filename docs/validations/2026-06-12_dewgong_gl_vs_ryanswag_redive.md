# Dewgong GL re-dive (2026-06-11 chain) vs RyanSwag archive — delta check

> Mandatory archive diff per `feedback_ryanswag_archive_diff` /
> STYLE_CONFORMANCE_CHECKLIST.md C12, triggered by the S6 full
> re-dive (perf+correctness arc, chain of 2026-06-11). This doc is a
> **delta** against the full side-by-side at
> `docs/validations/2026-04-25_dewgong_gl_vs_ryanswag.md`; read that
> first for the 2022-article context. Dewgong is the only re-dived
> species in this chain with a local RyanSwag archive (the published
> Stunfisk dive is the regular form, not Galarian; the other archive
> species have no published dives).

Three things changed under the dive since 2026-04-25: the pool
refresh (66 → 71, June rebalance churn), arc S1-S5 (form-change
plumbing, mirror-slayer redesign), and the 2026-06-11 engine
correctness fixes. Several 04-25 conclusions moved.

## What changed since the 2026-04-25 diff

### 1. Umbreon is back in the pool — the article's headline atk axis is live again

The 04-25 diff dismissed the article's 101.79-102.81 Atk Umbreon
breakpoints because Umbreon had left the pool. The June rebalance
put it back. The fresh dive now surfaces Umbreon thresholds
natively:

| surface                    | our 2026 number                                        | article (2022)                             |
| -------------------------- | ------------------------------------------------------ | ------------------------------------------ |
| Matchup flip, Umbreon 0v1  | 101.08 Atk + 154 HP                                    | 101.79 ("Rank 1" base)                     |
| Matchup flip, Umbreon 0v0  | 104.84 Atk                                             | up to 102.81 (high-Def Umbreon milestones) |
| Damage tier (Drill Run BP) | 105.04 Atk                                             | n/a (different movesets)                   |
| Def-side bulk anchors      | 123.65-125.69 Def + HP floors per Umbreon charged move | not cited                                  |

**Classification: article direction right, numbers superseded
(ours-right on current data).** The "slight atk weight pays off vs
Umbreon" axis survives the four-year gap; the specific values moved
with Umbreon's 2026 moveset/stats. The 04-25 claim that our
atk-weighted flavors "all sit at atk ≥ 108.43" is now only true of
the bulky-opponent tiers (Kingdra 109.35, Jumpluff-S 109.19,
Forretress-S 109.23, Greedent 108.84) — the Umbreon flips restore a
low-atk target band (101-105) the 04-25 dive didn't have.

### 2. The mirror def target now has a named flavor — 04-25 recommendation closed

04-25 flagged a "visibility gap": our sim reproduced the article's
138.28-Def mirror-domination claim but no tier surfaced it, and
recommended a `thresholds/dewgong.toml` bulkpoint anchor. The gap
closed without TOML: the mirror-synth tier (`f39aa00`, review R1)
auto-synthesizes **Dewgong Mirror Bulk (140.61 Def, 152 HP)** on all
three moveset pages, with the card reporting "passing cohort wins 7
of 9 scenarios vs rank-1 SP Dewgong." That lands inside the
article's 138.28-141 mirror-domination range.

**Classification: converged — both right.** The article's 2022
numeric target and our 2026 synth tier describe the same def wall.
No TOML needed; drop the 04-25 recommendation #2.

### 3. The article's moveset is back on our landing page

04-25 finding #3 said the article's Go Battle Day legacy combo
(Ice Shard / Icy Wind / Drill Run) was no longer top-scoring (we
ranked Blizzard + Icy Wind first). The June move rebalance cut
Drill Run 80 power/45 energy → 70/40, and the fresh dive's landing
moveset is now **Ice Shard / Drill Run, Icy Wind** — effectively the
article's combo. **Classification: obsolete 04-25 finding; the
rebalance, not a renderer/sim change, did it.**

### 4. Greedent def breakpoint reproduces almost exactly

Article: 137.53-139.25 Def for Greedent 0-1 / 1-2 potential. Fresh
dive: **137.56 Def flips Greedent (2v1)** and **138.91 Def for the
Greedent (Bite) damage tier**, plus an atk-side **Greedent Atk tier
at 108.84** the article didn't have. The def numbers sit squarely in
the article's range; the shield scenario drifted (2v1 vs 0-1/1-2)
with four years of moveset changes. **Classification: both
defensible — numeric convergence, scenario drift.**

### 5. Pool survivors reshuffled

Drapion (Shadow) — one of the three article opponents surviving in
04-25 — left in the June refresh. Article-opponent overlap is still
3/12, now Umbreon + Greedent + the mirror. The other nine (Trevenant,
Mew, Toxicroak, Tropius, A-Marowak, Vigoroth, Obstagoon, Scrafty,
non-shadow Drapion) remain absent; the bulk of the article's
per-opponent advice stays 2022-bound.

### 6. Tier-list churn vs the April dive (context, not a divergence)

April tiers (Sableye-S Bulk / Steelix-S Atk / Swampert Atk /
Sealeo-S Slayer / Fortified Corviknight) → June landing tiers
(Kingdra Atk / Jumpluff-S Atk / Forretress-S Atk / Fortified
Corviknight / Greedent Atk / Dewgong Mirror Bulk). Driven by the
pool refresh (Kingdra + Kingdra-S entered; Sealeo-S-class anchors
displaced) plus the mirror-synth tier. Pool-shift explains it; no
renderer anomaly (the "Session 2 validation-note principle").

## Style conformance spot-check (fresh HTML, landing page)

- **C1** name-vs-signature: ✅ all six (A-only tiers named `* Atk`;
  Fortified Corviknight and Dewgong Mirror Bulk are DH).
- **C2** namesake: ✅ Fortified Corviknight's summary desc cites
  Quagsire-S/Talonflame, but the card prose leads with "the
  Corviknight 0-1, 1-2" — namesake present. Checked because the
  desc looked like a violation; it isn't.
- **C3** constrained axes only: ✅.
- **C5** identical-sig merge: ✅ no duplicate (sig, gains) pairs.
- **C7** gain AND loss prose: ✅ ("will cost several matchups, such
  as the Aegislash (Shield) 2-2 ...").
- **C8** one [Recommended] per league: ✅ General Good only (the tag
  renders twice — summary table + detail card — same tier).

## Net verdict

No sim or renderer action items. The re-dive *strengthened*
agreement with the archive: two of the article's three numeric
targets (mirror def wall, Greedent def range) now reproduce inside
the article's own ranges, and the third (Umbreon atk weight) is
directionally restored with updated numbers. The 04-25 doc's
recommendation #2 (TOML mirror anchor) is closed by the synth tier;
its reader's-caveat in `dewgong.md` ("9 of 12 opponents gone") is
updated with an addendum pointing here.
