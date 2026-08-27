# Worlds-dive Discord post — bullet draft (prepared overnight 2026-08-24)

**SKIPPED (Michael, 2026-08-27): this post is not happening — do not
re-pitch.** Kept for reference only; the numbers below predate the
35-entry matrix (they say 33 entries / 528 pairings / 505 amber). The
surviving editorial lead is a Corviknight vs Shadow Quagsire
per-spread scatter for r/TheSilphArena (see TODO.md, Worlds section).

Draft material for Michael's 2026-08-25 Discord post about the Worlds
robustness pages (pogodives.com). Chat-draft, exploration-mode — edit
freely, numbers verified against the shipped pages as noted.

## Candidate bullets

- Worlds runs this weekend (Aug 28-30), so I built an IV-robustness
  map of the whole Worlds meta: all 528 pairings of the 33 realistic
  entries, every shield scenario, both bait modes — with full
  4096-spread grids wherever the outcome turned out to be IV-dependent.
- Headline finding: 505 of 528 pairings have at least one shield
  scenario where IVs can flip the result. "This matchup is a win" is
  a statement about SPREADS, not species, far more often than the
  usual tier-list framing admits.
- The one to stare at: **Corviknight vs Shadow Quagsire in the
  0-shield scenarios**. Across the full 4096-IV grid ~81% of
  Corviknight spreads win the 0s — but the top-512 stat-product
  builds are all over the place (individual coverage runs literally
  0% to 100%), and the winning direction is INVERTED from the usual
  rank-1 instinct: correlation with attack is -0.65, with HP +0.64.
  Bulk wins the 0s; the standard high-SP builds mostly don't. The
  grid makes it visible at a glance:
  https://pogodives.com/corviknight-quagsire-shadow-robustness.html
  [VERIFY URL against the live site before posting]
- Everything on the hub is regenerable and honesty-railed: measured
  false-negative rates printed on the page, exact spread counts, and
  the pinned gamemaster vintage disclosed (Worlds runs on the
  pre-rebalance-window data everything was baked against).
- Hub: https://pogodives.com/worlds.html [VERIFY exact hub URL]

## Numbers verified from the shipped artifacts

- 528 pairs / 33 entries / 505 amber: TODO.md Worlds section (final
  overnight audit 2026-08-20, 1.36B sims).
- Corvi/Quag 0-0 stats: embedded data of
  `userdata/website/corviknight-quagsire-shadow-robustness.html`
  (win_frac_all 0.8092; top-512 cov 0.0-100.0; corr_atk -0.645,
  corr_hp +0.639; movesets Corvi SA/AC+PAY vs rank-1 Shadow Quag).
- The "0s" claim is confirmed: 0-0 is a SENSITIVE cell in both bait
  modes on that page (1-1 and 2-2 also sensitive in bait mode).

## Cautions before posting

- Verify both URLs against the live site (local filenames may differ
  from live paths).
- If any Worlds surface needs re-rendering for screenshots, RE-PIN the
  gamemaster first (`git -C ../pvpoke show
  f60a41199:src/data/gamemaster.json >
  ~/Documents/gopvpsim_cache/gamemaster.json`) — the cache is currently
  on the Cramorant vintage.
