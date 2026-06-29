"""Regression pins for the bandaid[910] best-charged-move fix (2026-06-29).

The [910] "defer self-debuffing charged move" gate used to wait on the
defender's MAX-DAMAGE charged move; PvPoke (ActionLogic.js:929) waits on the
defender's bestChargedMove. The fix routes it through _estimate_best_cm.

These two matchups are the verified behavioral deltas (default movesets,
pvpoke_dp both sides, default pvpoke_simulate_shield policy):

  - Pangoro vs Lickitung, GL 0-0: 907 -> 715. Winner-stable (Pangoro wins
    either way) but NOT score-stable — a real turn/HP difference. Lickitung's
    bestChargedMove is Body Slam (higher DPE); its max-damage move is Power
    Whip. Pre-fix Pangoro waited on Power Whip; post-fix it waits on Body Slam.

  - Moltres (Galarian) vs Dondozo, UL 1-1: 478 -> 538. A WINNER FLIP
    (pre-fix Moltres loses 478<521; post-fix Moltres wins 538>461). Moltres-G
    owns Brave Bird (self-debuffing) so the [910] gate fires.

If either pin changes, the engine's [910] defer behavior moved — investigate
before updating (this is the score-coincidence guard CLAUDE.md warns about).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.battle import BattlePokemon, simulate, pvpoke_dp
from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS
from gopvpsim.moves import get_moves


def _bp(species, fast_id, charged_ids, league, shields, shadow=False):
    pk = Pokemon.at_best_level(species, 15, 15, 15, league=league, shadow=shadow)
    fast_moves, charged_moves = get_moves()
    fm = dict(fast_moves[fast_id])
    cms = [dict(charged_moves[c]) for c in charged_ids]
    return BattlePokemon.from_pokemon(pk, fm, cms, shields=shields,
                                      league_cp=LEAGUE_CAPS[league])


def test_pangoro_lickitung_gl_0_0_uses_bestcm_not_maxdmg():
    """GL 0-0: 715 post-fix (was 907 with the max-damage bug). Pangoro still
    wins, but with HALF the HP remaining — pin HP too, not just the winner,
    so a score-coincidence can't pass."""
    pang = _bp('Pangoro', 'KARATE_CHOP', ['CLOSE_COMBAT', 'NIGHT_SLASH'],
               'great', 0)
    lick = _bp('Lickitung', 'LICK', ['BODY_SLAM', 'POWER_WHIP'], 'great', 0)
    res = simulate(pang, lick, charged_policy_0=pvpoke_dp,
                   charged_policy_1=pvpoke_dp)
    assert res.winner == 0
    assert round(res.pvpoke_score(0)) == 715
    # post-fix Pangoro finishes with 56/130 HP (pre-fix was 106/130).
    assert res.hp_remaining[0] == 56
    assert res.hp_remaining[1] == 0


def test_moltres_galarian_dondozo_ul_1_1_winner_flip():
    """UL 1-1: 538 post-fix (was 478). The fix FLIPS the winner — pre-fix
    Moltres-G loses, post-fix it wins."""
    molt = _bp('Moltres (Galarian)', 'SUCKER_PUNCH', ['FLY', 'BRAVE_BIRD'],
               'ultra', 1)
    dond = _bp('Dondozo', 'WATERFALL', ['SURF', 'OUTRAGE'], 'ultra', 1)
    res = simulate(molt, dond, charged_policy_0=pvpoke_dp,
                   charged_policy_1=pvpoke_dp)
    assert res.winner == 0, "post-fix Moltres (Galarian) must WIN the UL 1-1"
    assert round(res.pvpoke_score(0)) == 538
