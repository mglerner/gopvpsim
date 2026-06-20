# Dialga-O / Palkia-O GoFest ETM + best-buddy decision (Master League)

Point-in-time experiment, 2026-06-19. Question: GoFest 2026 lets you Elite-TM the
Origin-forme signature moves (Roar of Time, Spacial Rend). Which ETM is worth it,
which IVs to build, and does best-buddy (L51) vs regular (L50) change the call?

Polished writeup: `~/coding/reports/dialga-palkia-origin-etm-ml-2026-06-19.html`.
Raw tables: `userdata/dives/{dialga,palkia}_origin_etm_analysis.md` (gitignored).
Tooling: `scripts/{dialga,palkia}_origin_etm_analysis.py`, `opponent_pools/master_top60.txt`,
and the new `deep_dive.py --max-level` flag. Branch: `dialga-origin-etm-dive`.

## Method

Each Origin forme swept over hundo + every single-/double-point IV drop, x 4 movesets,
x the 2x2 of (my level, opp level) in {L50, L51}, x all 9 shields, vs the PvPoke Master
top-60 (all opponents hundo). 69,120 sims per mon. Wins are out of 540 (9 shields x 60
opponents). Master has no CP cap, so L50/L51 are pure level steps. Scores are this
project's PvPoke 1v1 ratings (the authority); a win is score > opponent score.

## Verdicts

**Dialga-O: do NOT ETM Roar of Time.** You already own a 15/14/15 with RoT. ETM'ing the
15/15/14 beats it by only +0/+1/+1/+1 wins across the four level blocks (~1 matchup in
540). RoT is a stat-clone of Draco Meteor minus the self-debuff, so it gains only Lugia
and the Palkia-O mirror over the free Iron Head/Draco build, losing nothing. Field the
RoT mon you have. Iron Head is mandatory as the second move (ROT/IH 285 vs ROT/Thunder
247). 15/15/14 is actually the better spread: -1 HP costs 0 wins, -1 atk costs 2-3.

**Palkia-O: DO ETM Spacial Rend.** AT/SR (304) > AT/Draco (298) > AT/Hydro (279).
Spacial Rend nets +6 over Draco Meteor (+20 gained, -14 lost), flipping the Kyurem line,
Latios/Latias, Zekrom, Garchomp, Dragonite(Shadow), and the Dialga mirror. Because it is
a cheap 95/55 nuke (not a 1:1 Draco swap), it genuinely changes the fights. Aqua Tail is
the right partner (AT/SR 304 vs Hydro/SR 245).

**Best-buddy: yes for both.** The level race outweighs every IV/move nuance: +7 wins for
Dialga-O and +10 for Palkia-O at L51 vs an L50 field. Being the L50 mon vs an L51 field
costs you. Serious ML opponents are best-buddied; be one too.

**Opposite IV goals (the non-obvious bit).** Dialga-O wants attack (-1 atk = -2/-3 wins;
HP/def nearly free). Palkia-O wants bulk (-1 HP = -4; attack nearly free). Build each mon
to its own curve: high-attack Dialga-O, high-bulk / low-attack-floor Palkia-O.

## Verification

This is an Elite-TM / stardust spend, so all 8 load-bearing numbers were independently
re-derived from the raw tables by separate verifier agents. All confirmed (D1 hp-free,
D2 etm-marginal, D3 rot-vs-draco, D4/P4 best-buddy gains, D5 iron-head, P1 sr-best,
P2 sr-vs-draco net +6, P3 hp-matters). Base stats cross-checked against the gamemaster
(Dialga-O 270/225/205, Palkia-O 286/223/189).

## Caveats

- All opponents modeled as hundo (standard conservative ML assumption; real-spread counts
  shift slightly).
- Meta snapshot pinned 2026-06-19 (PvPoke Master top-60, `opponent_pools/master_top60.txt`).
- GoFest ETM window is roughly July 6-12 2026 but Niantic gives a span, not a precise
  cutoff; reconfirm in-game before spending, and confirm it is an Elite Charged TM.
