"""The even-shield scenario set, declared once.

The XehrFelrose convention that the ML IV guide, the owned-collection
breakdown, and the dive's matchup-cluster section all follow is "even
shields only": both sides bring the same number of shields, so the
comparison isolates the spread rather than the shield read. That set was
open-coded three times -- ``iv_envelope_analysis.EVEN_SHIELDS``,
``owned_breakdown.EVEN_SHIELDS``, and
``deep_dive_matchup_clusters.EVEN_SHIELD_PAIRS`` -- with nothing checking
they agreed. Changing the convention (say, dropping 2-2) had to be done in
three files, and a missed one silently sims a different scenario set.

A tuple, not a list: this is a constant that several modules hand straight
to callers as a default argument (``won_set(..., shieldset=EVEN_SHIELDS)``),
where a shared mutable default is a bug waiting to happen.

Stdlib only and imported by nothing, on purpose -- the same rule
``score_pack`` follows, so a spawn-mode worker child can pull it in without
dragging the render/analysis chain along.
"""

EVEN_SHIELDS = ((0, 0), (1, 1), (2, 2))
