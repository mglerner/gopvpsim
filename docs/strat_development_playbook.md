# Strategy-development playbook

Distilled from the Cramorant PoGoDives campaign (2026-08-24/25; full
record: `docs/validations/cramorant_policy_lab_2026_08_24.md` + the
plan doc). The process that worked, in order, with the traps we hit.

## The loop

1. **Grid-sweep the knob space** over the standard pools, both bait
   modes, all 9 shield cells (`scripts/cramorant_policy_lab.py`
   pattern: named variants, per-cell JSON, baseline knob-leak
   tripwire). Compute is cheap; spend the budget on analysis.
2. **Adversarial analysis, dual-metric from the start**: winner flips
   AND rating are different objectives -- a strat can buy wins with
   rating (ours does) or pad rating onto won fights (D1-frac35 did).
   Never sell one metric as the other; report both, per shield cell.
3. **RENDER THE DELTAS AND LOOK AT THEM** (Michael 2026-08-25 -- this
   step is load-bearing). The 3x3 per-scenario scatter (x = SP rank,
   y = per-IV delta) + histograms surfaced, in one glance, what the
   aggregate tables had not prioritized: the uniform shield-ahead
   cost column, the 2-2 rank crossover, and breakpoint bimodality.
   Iterate: plot -> human hypothesis -> mechanism rule -> corpus.
   Report vehicle: ~/coding/reports (the
   gopvpsim-cramorant-pogodives-vs-pvpoke page is the template).
4. **Mechanism, not names** (double argument: post-hoc species/cell
   lists overfit, AND rebalances invalidate name-lists while
   mechanism rules re-derive from the new numbers at battle time).
5. **Holdout everything tuned**: league-crossed (tune GL / validate
   UL and swap), plus IV spreads and both builds. A condition that
   only helps where it was fitted dies. Selection over many
   candidates is winner's-curse bait -- demand sign-stability across
   crossings, not argmax.
6. **Skeptic verdict before shipping** -- independent agents attack
   the draft conclusion from the raw cells. Every round's verdict
   changed the record (stale loser roster, frontier-not-dominance
   framing, rating-vs-flip reframes).
7. **Thread, then RE-verify**: wrapper-based discovery adapts the
   actual decision only; the shipped rule also threads the DP's
   would_shield model, which can shift cells. Re-run the corpus on
   the threaded engine before freezing.

## Traps (all hit live, all cost time)

- **Identical-to-reference across every variant = plumbing smell, not
  a null result.** The round-6 wrappers were silently discarded by a
  parameter default; the "clean null" was inert code. Always include
  a liveness check (one variant must differ from reference).
- **Live-state vs start-state conditioning**: a live-state revert
  ("when ahead on shields, play standard") cannibalized even-start
  fights through TRANSIENT shield leads (-117..-160 wins). Start-
  scenario conditioning composes cleanly (a reverted cell IS the
  baseline cell -- subset search costs zero sims, and the composition
  is checkable: 0 mismatches / 10,368 cells).
- **Threshold parameterization must cover the probe set**: D3's
  110/120 cutoffs sat below every probed spread's max HP -- the
  "no effect" result was probe-coverage artifact, not evidence.
- **Delta bimodality = breakpoint populations**, not noise: the 2-0
  modes split on an attack breakpoint (~125.4 GL) with a razor
  transition. Strategy deltas are piecewise-constant over breakpoint
  cells; which strat a spread wants can flip at a damage tier.
- **Fitted constants are mechanism-shaped but data-tuned**: re-verify
  them after any move rebalance (tests/test_rebalance_tripwire.py
  fires the checklist).
- **Dedup-signature fence**: policy-rule inputs must be functions of
  the dedup-signature components, or the 4096-sweep silently merges
  profiles that fight different battles. Enforced by the
  dedup-under-policy equality run.

## Cost calibration (for planning)

Grid rounds run in ~minutes (the whole 80-variant x 4-round campaign
was ~1.5M sims); the analysis/verdict workflows are the slow part
(~10-30 min each). Rendering the delta report costs zero sims when
both tiers are cache-warm.
