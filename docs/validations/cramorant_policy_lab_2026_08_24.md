# Cramorant policy lab — round-1 campaign results (2026-08-24 overnight)

Plan of record: `docs/cramorant_policy_plan.md`. Lab:
`scripts/cramorant_policy_lab.py`. Raw data (gitignored):
`userdata/cramorant_lab/*.json` (~36 MB each); full analyst + skeptic
reports: `userdata/cramorant_lab/reports/strat_{A1..A4,S1,S2}.md`.
Everything below was produced by a 4-analyst + 2-skeptic adversarial
workflow over the raw cell data; every load-bearing number was
re-derived independently by at least one skeptic.

## Setup

Focal: Cramorant Peck / Dive + Fly. Corpus: the standard GL pool (78
opponents) + UL pool (66), PvPoke default IVs both sides, all 9 shield
cells x both focal bait modes = 2,592 cells per variant per round.
Grid: 80 knob variants over `_CRAM_DIVE_GATE_DPE` {0, 1.5, 3, inf} x
`_CRAM_DIVE_GATE_HP` {1.0, 1.3} x `_CRAM_TANK_MULT` {1.4, 1.8, 2.2,
2.6, inf} x `_CRAM_DELAY_GORGING` {off, on}. Rounds: (1) normal
PvPoke-modeled opponents; (2) opponents WITHHOLD non-lethal charged
moves vs a prey-holder; (2b) withhold + lethal-Dive-shield fix; (3)
normal + lethal-Dive-shield fix. IV robustness: the finalists re-run at
focal spreads 0/15/14, 15/15/15, 5/5/5 (4 GL / 3 independent UL blocks
— PvPoke's UL default IS 15/15/15).

**Metric caveat (pinned):** `net_vs_baseline` counts ordinal outcome
moves (L->D priced like L->W). For the champion, headline +111 =
strict win-flips +74, with ~35% of "gains" only loss->draw; the
all-three-opponent-models "hard net" floor is +64. Quote accordingly.

## The four findings

1. **Prey tanking is the big, real effect — and a genuine value fork.**
   Lowering the tank threshold (shield less, eat charged hits while
   holding prey) drives most of the gain: tank 1.4 nets +36..+63 over
   1.8/2.2 at every dive gate (round 1), survives species-level
   clustered bootstrap (champion +111, 95% CI [+69, +152]), holdout
   splits, and an adaptive shield-breaking opponent skeptic 1 built
   independently. BUT it buys wins by spending rating and HP: GL mean
   score-delta sign-flips across IV spreads at 1.4, won-matchup HP cost
   doubles vs 1.8, and ~90 more no-flip cells collapse by >=100 rating.
   Tank 1.8 keeps 84% of the strict win-flip gain, is GL-rating-positive
   on all four spreads, and is tied-#1 under the withhold counter.
2. **The dive gate's IDEA is right; PvPoke's constant is wrong.**
   Retuning 1.5 -> 3.0 is worth +48 net and +18,667 aggregate rating
   over PvPoke's gate. The empirical separation plateau is [2.30, 3.51],
   so 3.0 is not a knife-edge. Against ALWAYS-dive the gate's edge is
   small but sign-stable (+3..+7 in every round and spread, never
   negative) — and it is essentially the Kingdra story (water/dragon
   double-resists Dive); frame it as "gate >= always, by a hair," not
   "gate beats always." A type-based discriminator ("dive unless Fly is
   SE") was tested and REFUTED (-9 vs the ratio gate; wrong on both
   members of its own decision bucket).
3. **The HP gate is noise.** 1.0-vs-1.3 moves 33 sign-unstable cells,
   flips with single held-out opponents, and loses on every economy
   metric. Keep PvPoke's 1.3.
4. **Delay-for-Gorging is catastrophic** (marginal -72 normal, -125
   withhold) — PvPoke was right not to ship it. Off, permanently.

## Structure of the gains (all IV-invariant)

- **It is a shield-economy policy.** All gains sit where shields are on
  the board: 1-1 +41, 2-2 +42, 1-2 +37 (of the champion's +111); the
  0-0 cell is -8 and the Cramorant-shield-ahead column is a small
  persistent tax (1-0 -6, 2-1 -4, 2-0 -2). "Meaningfully better once
  shields are on the board, mildly worse when Cramorant is
  shield-ahead" is the honest one-line description.
- **Broad, not lucky:** 48 opponents net-positive (max +6 each), 11
  negative, 85 unmoved. 23 opponents positive in ALL four IV spreads —
  the bulky-water/normal block Dive punishes (Seaking, Feraligatr,
  Dondozo, Sealeo, Jellicent, Lapras, Blastoise...). Exactly 5
  opponents are negative in all four spreads (GL Shadow Shelgon, UL
  Giratina-A both flavors, UL Shadow Hydreigon, GL Shadow Lapras; sum
  -59) — the deterministic price, and the target for any follow-up
  refinement.
- **Robust to opponent models:** round 3 (lethal-Dive bug fixed)
  reproduces round 1 almost exactly (baselines differ in only 5 cells;
  Spearman 0.9991 — cite one round, footnote the other, do NOT count
  them as two confirmations). Under the withhold counter (round 2) the
  knobs still net +138 — withholding actually helps baseline Cramorant
  more than it denies (+628 baseline W-L vs +233), and the tank knob
  goes flat there (opponents rarely throw into prey), so the tank
  effect is specifically about punishing opponents who DO throw.
- **IV-spread stability:** no inversion in any of 16 spread x league x
  variant blocks. Champion floor +81 (GL 5/5/5, where low bulk
  amplifies the tank knob's downside); UL nets are IV-invariant
  (48/49/47). Round 2b (withhold + lethal-Dive fix — the CLEAN
  adversarial round, replacing round 2's bug-carrying opponent model
  per skeptic 2's requirement): the dpe-3.0 family nets +138..+143
  over its own baseline (1561W/96D/935L) at EVERY tank value — both
  finalists land +138/+139, within noise of the round's +143 top. The
  recommendation does not depend on the opponent bug or on the
  opponents' willingness to throw into prey.

## Frozen recommendation — the "PoGoDives strat" knob set

PROVISIONAL (final tank call is Michael's — see the fork below):

    _CRAM_DIVE_GATE_DPE = 3.0     (retuned from PvPoke's 1.5)
    _CRAM_DIVE_GATE_HP  = 1.3     (PvPoke default; 1.0 is noise)
    _CRAM_TANK_MULT     = 1.8     (provisional; see fork)
    _CRAM_DELAY_GORGING = False

**DECISION FOR MICHAEL — tank 1.4 vs 1.8.** Both skeptics say
SUPPORTED-WITH-CHANGES and split exactly here:

| criterion                           | tank 1.4 (max wins)   | tank 1.8 (provisional) |
| ----------------------------------- | --------------------- | ---------------------- |
| round-1 net (champion family)       | +111 (floor +81)      | +78 (floor +54)        |
| strict win-flips kept               | 100%                  | ~84%                   |
| GL mean rating delta across spreads | sign-flips (-3..+2.8) | positive (+2.7..+6.5)  |
| won-matchup HP cost                 | 2x of 1.8             | half of 1.4            |
| withhold round                      | mid-pack              | tied #1                |
| rank across all 8 spread-blocks     | #1 in all 8 (flips)   | #1 on rating economy   |

1.4 is the pure win-maximizer; 1.8 is the page-defensible pick (never
rating-negative, half the HP bill — consistent with the project's MG
near-KO precedent of valuing post-KO carry-over). Whichever ships, the
other gets documented as a named variant, and the disclosures below
ship with it.

**Required disclosures on any shipped surface** (never-unflagged rule):
the shield-ahead tax (0-0 -8, 1-0 -6, 2-1 -4); the named regressions
(UL Shadow Feraligatr 1-1 614->500 W->D, GL Grumpig 2-2 599->378 W->L,
GL Shadow Shelgon 1-0 805->443); wins-bought-with-rating on the 1.4
variant; and that the Azumarill narrative is FALSE in rounds 1/3 (zero
flips; it flips only under withhold, 0-shield cells only).

## Overlay implementation notes (next, supervised session)

- `pogodives_dp` / `pogodives_shield` per the plan doc, with the
  test-pinned byte-identical pvpoke fallback and cache key
  normalization. NOTE: the current knob GLOBALS are insufficient for
  the overlay — they'd apply to BOTH sides in a Cramorant mirror (and
  to Cramorant opponents in other dives). The overlay must thread
  per-side knobs (e.g. a per-BattlePokemon policy attribute read at the
  decision sites), which is an engine change: own hash bump + a
  no-cramorant-either-side migration predicate.
- Upstream bug-report drafts (the two moveID typos + the lethal-Dive
  inversion) can now cite round-3/2b measurements. Also worth an
  upstream note: PvPoke's own 1.5 gate and 2.2 tank constants are
  measurably dominated within its own opponent model.

## Addendum: the Dive+Surf build (round 4, 2026-08-24 late)

Our shipped dives rank Peck / Dive + Surf as Cramorant's #1 build in
both leagues, so the grid was re-run on it
(`userdata/cramorant_lab/round4_divesurf.json`). Results:

- **The dive gate is inert on this build** (Surf/Dive DPE ratio ~1.33
  sits below 1.5 and 3.0 alike; dpe 1.5/3/inf produce identical
  cells). The gate knob only matters for builds carrying a non-gulp
  charged move — consistent with A4's semantics.
- **The tank knob is the entire effect, and the 1.4-vs-1.8 gap WIDENS:
  +108 vs +48 net** (baseline 1310W/174D/1108L). On the build we
  actually showcase, tank 1.8 keeps well under half of the ordinal
  gain — material input for the pending tank decision. The Dive+Surf
  rating ledger (mean dScore vs baseline): tank 1.4 GL -2.66 / UL
  -2.14, tank 1.8 GL -0.53 / UL -0.07 — the same wins-bought-with-
  rating shape as Dive+Fly, but on this build BOTH variants are
  rating-negative and 1.4's bill is ~4x. The fork sharpens: on the
  showcased build, 1.4 buys 2.2x the flips at 4x the rating cost.
- Delay-for-Gorging is only mildly negative here (both charged moves
  are prey triggers, so the delay semantics differ) — still no reason
  to ship it.
- Baseline W-L: Dive+Surf 1310/1108 vs Dive+Fly 1360/1127 against the
  same pools — the dive's avg-score ranking of Dive+Surf as #1 is not
  a raw-win-count claim; worth a look when reviewing the dive pages.

## Addendum 2: the adaptive tank rule dissolves the 1.4-vs-1.8 fork
(round 5, 2026-08-25 morning; Michael's state-aware suggestion)

Rule A ("tank at 1.4 unless Cramorant's HP-fraction lead exceeds a
threshold, then PvPoke's 2.2") was swept at lead thresholds
25/33/40/50% and verified across the withhold+ldfix round, the
Dive+Surf build, and IV spreads 0/15/14 + 5/5/5
(`userdata/cramorant_lab/round5*.json`). Rule B (post-hit HP floor)
is dominated and dropped; lead25 gives up too many flips on Dive+Surf.

Net flips (vs each round's own baseline):

| round             | tank1.4 | lead33 | lead40 | lead50 | tank1.8 |
| ----------------- | ------- | ------ | ------ | ------ | ------- |
| default D+F       | +109    | +109   | +109   | +109   | +78     |
| withhold+ldfix    | +139    | +139   | +139   | +139   | +139    |
| Dive+Surf         | +102    | +102   | +102   | +102   | +48     |
| IVs 0/15/14       | +113    | +111   | +113   | +115   | +85     |
| IVs 5/5/5         | +98     | +89    | +93    | +95    | +54     |

Won-cell dScore (HP-economy proxy; higher = less rating spent in
matchups both win): lead33 is ~25% cheaper than tank1.4 in every
normal round (-15.5/-10.0/-14.0/-17.5 vs -20.2/-14.5/-19.0/-24.2);
lead40 sits between lead33 and 1.4.

**Both lead33 and lead40 DOMINATE static tank1.4** (equal or
near-equal flips, strictly better economy) and beat tank1.8's flips
massively (esp. Dive+Surf +102 vs +48) at modest economy cost. The
old fork is superseded; the remaining choice (lead33 = economy lean,
lead40 = flips lean) is soft -- every point on the dial beats both
static options on at least one axis.

Caveats for the overlay build: (a) the only flip give-back is the
frail 5/5/5 spread (lead proxy is HP-fraction-based; -4..-9 flips
there) -- disclose, or revisit the proxy if it ever matters; (b) these
runs adapt the ACTUAL shield decision only; the shipped overlay
threads the rule into would_shield's model too and MUST re-verify
after threading (the model/actual mismatch could shift cells).

**DECIDED (Michael 2026-08-25): adaptA lead40 ships** (max-wins tier
mission, strictly better economy than the old max-wins pick); lead33
stays the named alternative. Final confirmation rides the overlay's
post-threading re-verification.

## Addendum 3: threaded-engine confirmation (overlay session, 2026-08-25)

The overlay landed (`pogodives_dp`/`pogodives_shield`, per-side
`_pogodives` marking at simulate() start, the adaptive rule threaded
into BOTH the actual shield decision and would_shield's model). The
round-7 re-verification (`userdata/cramorant_lab/round7_threaded_*`)
reproduces the wrapper-based results almost exactly (model threading
moved one cell at IVs 0/15/14): lead40 matches static-1.4's flips on
default/Dive+Surf/withhold (+109/+102/+139), gives back 2-5 flips on
the two probe spreads, and keeps the ~15-20% won-cell rating advantage
(-17.3 vs -20.2 default; -19.6 vs -24.2 at 5/5/5). The 35-45 plateau
holds; lead30 is too conservative. **lead40 is FINAL.** Enforcement
now in code: tests/test_pogodives.py (fallback invariant on
non-Cramorant pairs incl. Aegislash, per-side marking semantics, the
three-way adaptive discrimination, cache key normalization + the
registry-lives-in-a-hashed-module pin).
