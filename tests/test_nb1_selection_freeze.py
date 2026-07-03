"""NB-1 selection-freeze: the move-selection quantities PvPoke freezes at
resetMoves() (activeChargedMoves ordering, each move's raw ``.dpe``,
bestChargedMove, and the farm-down constants derived from them) are now frozen
in our engine too, computed once per battle at the stage prevailing when
resetMoves would run and reused across every later stat stage
(``BattlePokemon._ensure_dp_init_cache``). Before 2026-07-03 we recomputed all
of them per stat stage from current-stage damage; the NB-1 bounding sweep
(docs/reviews/2026-07-03_nb1_bounding_sweep.md) proved that crossed PvPoke's
init-tuned 0.3/1.5 thresholds mid-fight for non-strategic reasons, in both
directions, including a shipped winner flip against us.

Groups A and B are the ACCEPTANCE test of the fix: after the freeze these must
equal the PvPoke oracle exactly. Group C pins the ONE dpe site kept
intentionally FRESH (the don't-bait dpeRatio carve-out). Group D xfails the
separate OMT ``turns_planned`` divisor infidelity until its own fix lands.

Pinned to the sweep's gamemaster (pvpoke @ 00f0afe7f, gamemaster md5
363e44f3...); the sim-relevant subset (pokemon + moves) of the worktree's live
gamemaster is byte-identical to it (narrowed hash 6a19b26925bd), so the
hard-coded movesets/levels/scores below reproduce without any redirect. All
cells: 15/15/15 both sides, bait-on (PvPoke default) both sides, hard-coded
movesets (never get_default_moveset -- these must not drift with rankings).
Levels quoted in comments are what at_best_level reproduces; asserting the
score pins the level implicitly.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402


def _score0(focal, opp, s_focal, s_opp):
    """focal/opp are (species, fast, [charged], league, shadow) tuples."""
    fsp, ff, fc, fl, fsh = focal
    osp, of, oc, ol, osh = opp
    a = _make_battle_pokemon(fsp, ff, fc, fl, s_focal, 15, 15, 15, shadow=fsh)
    b = _make_battle_pokemon(osp, of, oc, ol, s_opp, 15, 15, 15, shadow=osh)
    a.reset_for_battle(s_focal, opponent=b)
    b.reset_for_battle(s_opp, opponent=a)
    r = simulate(a, b, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp)
    return r.pvpoke_score(0)


# --------------------------------------------------------------------------- #
# Group A -- NB-1 0.3-guard class. MUST equal the PvPoke oracle after the fix. #
# --------------------------------------------------------------------------- #

GREEDENT = ('Greedent', 'MUD_SHOT', ['BODY_SLAM', 'TRAILBLAZE'], 'great', False)
FORRE = ('Forretress', 'VOLT_SWITCH', ['SAND_TOMB', 'ROCK_TOMB'], 'great', False)
FORRE_S = ('Forretress', 'VOLT_SWITCH', ['SAND_TOMB', 'ROCK_TOMB'], 'great', True)
CRADILY = ('Cradily', 'BULLET_SEED', ['ROCK_TOMB', 'GRASS_KNOT'], 'great', False)
ORANGURU = ('Oranguru', 'CONFUSION', ['BRUTAL_SWING', 'TRAILBLAZE'], 'ultra', False)
ORTHWORM = ('Orthworm', 'MUD_SLAP', ['ROCK_TOMB', 'EARTHQUAKE'], 'ultra', False)
WIGGLY = ('Wigglytuff', 'CHARM', ['SWIFT', 'ICY_WIND'], 'great', False)
FLORGES_GL = ('Florges', 'FAIRY_WIND', ['CHILLING_WATER', 'DISARMING_VOICE'], 'great', False)


@pytest.mark.parametrize("focal,opp,sf,so,oracle", [
    # 1: Greedent L22 vs Forretress L23, 1-1. Exemplar: T27 our Trailblaze
    #    (11 dmg) held over Body Slam (17) after Rock Tomb's -1 atk crossed
    #    the 0.3 guard mid-fight. Frozen -> matches oracle.
    (GREEDENT, FORRE, 1, 1, 352),
    # 2: same, 1-2.
    (GREEDENT, FORRE, 1, 2, 272),
    # 3: Forretress (Shadow) L23 vs Cradily L23.5, 1-0. SHIPPED WINNER FLIP:
    #    was ours 413 (LOSS) vs oracle 588 (WIN); frozen -> 588 WIN.
    (FORRE_S, CRADILY, 1, 0, 588),
    # 4: Oranguru L41.5 vs Orthworm L46.5 UL, 1-1 (oracle-better direction).
    (ORANGURU, ORTHWORM, 1, 1, 366),
    # 5: same, 2-0 (was ours-better direction -- freeze gives up the
    #    accidental win to match the reference).
    (ORANGURU, ORTHWORM, 2, 0, 447),
    # 6: Wigglytuff L27 vs Florges L16, 1-1 (was ours-better +56; freeze
    #    matches oracle 576).
    (WIGGLY, FLORGES_GL, 1, 1, 576),
])
def test_group_a_zeroguard_matches_oracle(focal, opp, sf, so, oracle):
    assert _score0(focal, opp, sf, so) == oracle


# --------------------------------------------------------------------------- #
# Group B -- bait-wait 1.5 second site (same class, different threshold).      #
# --------------------------------------------------------------------------- #

FORRE_S_UL = ('Forretress', 'VOLT_SWITCH', ['SAND_TOMB', 'ROCK_TOMB'], 'ultra', True)
FORRE_UL = ('Forretress', 'VOLT_SWITCH', ['SAND_TOMB', 'ROCK_TOMB'], 'ultra', False)


@pytest.mark.parametrize("focal,opp,sf,so,oracle", [
    # 7: Forretress (Shadow) mirror L23 GL, 1-2. Flooring-noise crossing
    #    (ratio 1.495 live vs 1.52 frozen). Frozen -> oracle 296.
    (FORRE_S, FORRE_S, 1, 2, 296),
    # 8: Forretress L47 vs Forretress (Shadow) L47 UL, 1-2. frozen 1.486 vs
    #    live 1.508 crossing. Frozen -> oracle 468.
    (FORRE_UL, FORRE_S_UL, 1, 2, 468),
])
def test_group_b_baitwait_matches_oracle(focal, opp, sf, so, oracle):
    assert _score0(focal, opp, sf, so) == oracle


# --------------------------------------------------------------------------- #
# Group C -- don't-bait dpeRatio staleness site. INTENTIONAL DIVERGENCE, kept  #
# under the fix. We pin OUR scores.                                            #
#                                                                             #
# PvPoke's don't-bait override (ActionLogic.js:857-865) forms its dpeRatio    #
# from move.DAMAGE, which is refreshed only on use -- so one move's damage is #
# current and the other's is init-stale, an internally INCONSISTENT PvPoke    #
# cache bug (a "PvPoke X is arbitrary/buggy because Z" divergence per the     #
# CLAUDE.md policy). We keep our evaluation FRESH and internally consistent    #
# (both moves at the current stage; battle.py, the carve-out block). See      #
# docs/reviews/2026-07-03_nb1_bounding_sweep.md section 2 (carve-out) and     #
# DEVELOPER_NOTES.md divergence #3.                                           #
# --------------------------------------------------------------------------- #

OINK_F = ('Oinkologne (Female)', 'MUD_SLAP', ['BODY_SLAM', 'TRAILBLAZE'],
          'great', False)
FLORGES_UL = ('Florges', 'FAIRY_WIND', ['CHILLING_WATER', 'DISARMING_VOICE'],
              'ultra', False)
SEISMITOAD = ('Seismitoad', 'MUD_SHOT', ['EARTH_POWER', 'ICY_WIND'], 'ultra', False)


def test_group_c9_dontbait_staleness_oinkologne_florges():
    # Oinkologne (Female) L21 vs Florges L16 GL, 2-2. Shipped flip in OUR
    # favor: oracle's override is fed by BodySlam.damage=35 (stale) vs
    # Trailblaze.damage=28 (fresh), ratio 1.607; our consistent ratio 1.286
    # doesn't cross 1.5. Ours 567 (oracle 471 -- PvPoke's stale-cache bug).
    assert _score0(OINK_F, FLORGES_GL, 2, 2) == 567


def test_group_c10_dontbait_staleness_florges_seismitoad():
    # Florges L27 vs Seismitoad L38 UL, 2-1. Ours 866 (oracle 665). CAVEAT:
    # our score here is inflated by a SEPARATE open bug on OUR side -- the
    # opponent-side would_shield=False feeds this override while the actual
    # scenario policy always shields, so we waste our nuke into a shield. That
    # is not "better play"; it is an internal would_shield/always-shield
    # inconsistency (tracked separately). This cell pins current behavior so a
    # future fix to that bug is noticed here, not that ours is correct.
    assert _score0(FLORGES_UL, SEISMITOAD, 2, 1) == 866


# --------------------------------------------------------------------------- #
# Group D -- OMT turns_planned divisor infidelity (battle.py vs              #
# ActionLogic.js:306). Separate unintentional port bug; PvPoke strictly       #
# better. xfail until its own fix lands (that fix forces a cold re-dive).      #
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(reason="OMT turns_planned divisor port infidelity "
                          "(battle.py vs ActionLogic.js:306): we divide "
                          "poke.energy by the cheapest-affordable charged "
                          "move and return False when none is affordable; "
                          "PvPoke divides by activeChargedMoves[0] regardless. "
                          "PvPoke strictly better in all traced cells; fix "
                          "deferred (forces cold re-dive; see TODO / sweep "
                          "doc section 4 Group D).",
                   strict=True)
def test_group_d11_omt_divisor_matches_oracle():
    # Oinkologne (Female) L21 vs Forretress (Shadow) L23 GL, 0-1. Deathbed
    # ttl=4, energy=35: PvPoke divides by promoted slot-0 (45e) -> waits and
    # banks a floating Mud Slap (+24); ours divides by cheapest-affordable
    # (35e) -> fires 3 turns early. Ours 280, oracle 304.
    assert _score0(OINK_F, FORRE_S, 0, 1) == 304
