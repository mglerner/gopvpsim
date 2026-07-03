"""Regression pins for the both-self-debuff PvPoke divergence cluster (KEEP).

The bug-#3 oracle surfaced ~117 pre-existing divergences on the broader
both-self-debuff population (Lurantis, Blaziken, Flareon; non-default
movesets). Investigation: docs/reviews/2026-06-28_both_self_debuff_divergence
_cluster.md, re-measured 2026-07-03 on c7f9ba2 (post-bandaid[910]-fix
ffb582b) -- all 8 GL flip rows reproduced byte-identical, and the fix's total
footprint on this 864-cell population was 4 score-only cells, every one moved
to exact PvPoke agreement.

Verdict per the CLAUDE.md "When our sim diverges from PvPoke" gate: KEEP.
Every winner-flip in the population (8 GL non-default + 1 ML default-moveset)
is ours-WIN / PvPoke-LOSE, zero the other way; the traced mechanism is
PvPoke leading with a worse-typed self-debuffing nuke where we hold it (the
documented Divergence-#3 / self-debuff-timing family). Matching PvPoke would
flip 9 focal wins to losses.

These tests pin OUR verified-correct scores (PvPoke's scores for the same
cells, oracle-measured 2026-07-03 against pvpoke 00f0afe7f, are in the
comments). Movesets are HARD-CODED move IDs on purpose: default movesets
resolve via live-refreshed rankings (1-day TTL) and would silently drift.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402


def _run(p0, p1, s0, s1):
    p0.reset_for_battle(s0, opponent=p1)
    p1.reset_for_battle(s1, opponent=p0)
    # Same harness as the investigation doc's scan: explicit pvpoke_dp on
    # both sides (bare simulate() defaults to a different charged policy).
    return simulate(p0, p1,
                    charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp)


def test_lurantis_vs_cresselia_gl_flip_pin():
    # GL 1-0: ours 691/308 (Lurantis wins); PvPoke 477/522 (Lurantis loses).
    lur = _make_battle_pokemon('Lurantis', 'LEAFAGE',
                               ['LEAF_STORM', 'SUPER_POWER'],
                               'great', 1, 15, 15, 15)
    cre = _make_battle_pokemon('Cresselia', 'PSYCHO_CUT',
                               ['GRASS_KNOT', 'MOONBLAST'],
                               'great', 0, 15, 15, 15)
    r = _run(lur, cre, 1, 0)
    assert r.pvpoke_score(0) == 691
    assert r.winner == 0


def test_blaziken_vs_bastiodon_gl_flip_pin():
    # GL 1-0: ours 646/353 (Blaziken wins); PvPoke 416/583 (Blaziken loses).
    bla = _make_battle_pokemon('Blaziken', 'EMBER',
                               ['BRAVE_BIRD', 'OVERHEAT'],
                               'great', 1, 15, 15, 15)
    bas = _make_battle_pokemon('Bastiodon', 'SMACK_DOWN',
                               ['STONE_EDGE', 'FLAMETHROWER'],
                               'great', 0, 15, 15, 15)
    r = _run(bla, bas, 1, 0)
    assert r.pvpoke_score(0) == 646
    assert r.winner == 0


def test_braviary_vs_lugia_ml_default_moveset_flip_pin():
    # ML 2-0: ours 695/304 (Braviary wins); PvPoke 417/582 (Braviary loses).
    # The one default-moveset winner-flip in the population (pre-existing
    # w.r.t. ffb582b; PvPoke throws double-resisted Close Combat into
    # psychic/flying where we lead Brave Bird). Moveset = the 2026-07-03
    # ML defaults, frozen here.
    bra = _make_battle_pokemon('Braviary', 'AIR_SLASH',
                               ['CLOSE_COMBAT', 'BRAVE_BIRD'],
                               'master', 2, 15, 15, 15)
    lug = _make_battle_pokemon('Lugia', 'DRAGON_TAIL',
                               ['AEROBLAST', 'FLY'],
                               'master', 0, 15, 15, 15)
    r = _run(bra, lug, 2, 0)
    assert r.pvpoke_score(0) == 695
    assert r.winner == 0


def test_zacian_vs_swampert_ul_bandaid910_agreement_pin():
    # UL 1-0: ours 625/374 == PvPoke 625/374 (exact agreement). Before the
    # bandaid[910] fix (ffb582b) we scored 519 here -- this pin guards the
    # fix's effect on the cluster's population (the investigation doc's
    # stale "ours 519" number is dead; do not resurrect it).
    zac = _make_battle_pokemon('Zacian (Hero)', 'SNARL',
                               ['WILD_CHARGE', 'CLOSE_COMBAT'],
                               'ultra', 1, 15, 15, 15)
    swa = _make_battle_pokemon('Swampert', 'MUD_SHOT',
                               ['HYDRO_CANNON', 'EARTHQUAKE'],
                               'ultra', 0, 15, 15, 15)
    r = _run(zac, swa, 1, 0)
    assert r.pvpoke_score(0) == 625
    assert r.winner == 0
