"""Regression: shadow opponents must get their OWN PvPoke-default IVs.

PvPoke stores separate ``defaultIVs`` for shadow speciesIds (the shadow stat
multipliers shift which CP-cap-fitting spread maximizes stat product), and they
genuinely differ from the base for ~37 species. The dive's ``resolve_opp_ivs``
``'pvpoke'`` branch (and ``build_matchup_web``) used to call
``pvpoke_default_ivs`` with the BASE name, ignoring the shadow flag -- so a
shadow opponent in PvPoke-default mode was built at the non-shadow level + IVs
and then had the shadow multipliers applied on top (wrong stats). The ``rank1``
branch already honored shadow; this makes ``pvpoke`` consistent.

Found 2026-06-28 by the round-5 baked-value/context finder fleet (2/2 skeptics).
Live in shipped Ultra-League pages: Shadow Raikou / Shadow Cresselia / Shadow
Giratina (Altered). It flipped a shipped winner -- see the sim test below.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from test_battle import _make_battle_pokemon  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402
from gopvpsim.pokemon import pvpoke_default_ivs  # noqa: E402


@pytest.mark.parametrize("name,league,base,shadow_ivs", [
    ('Raikou', 'ultra', (5, 13, 13), (8, 7, 14)),
    ('Cresselia', 'ultra', (4, 11, 11), (10, 10, 15)),
    ('Giratina (Altered)', 'ultra', (5, 15, 8), (11, 10, 8)),
])
def test_pvpoke_default_ivs_shadow_differs(name, league, base, shadow_ivs):
    """Shadow default IVs differ from base for these shipped UL species."""
    assert pvpoke_default_ivs(name, league=league)[1:] == base
    assert pvpoke_default_ivs(name, league=league, shadow=True)[1:] == shadow_ivs


def test_pvpoke_default_ivs_shadow_fallback():
    """A species with no shadow defaultIVs block falls back to base, no crash."""
    assert (pvpoke_default_ivs('Azumarill', league='ultra', shadow=True)
            == pvpoke_default_ivs('Azumarill', league='ultra'))


def test_resolve_opp_ivs_pvpoke_honors_shadow():
    """The dive's opponent-IV resolver passes shadow through the pvpoke branch."""
    from deep_dive import resolve_opp_ivs
    assert resolve_opp_ivs('Raikou', 'ultra', False, 'pvpoke') == (5, 13, 13)
    assert resolve_opp_ivs('Raikou', 'ultra', True, 'pvpoke') == (8, 7, 14)


def test_shadow_raikou_pvpoke_default_flips_mimikyu_winner():
    """Shipped UL classification: Mimikyu beats PvPoke-default Shadow Raikou at
    2-2. With the (buggy) base IVs 5/13/13 it read as a 470 LOSS; with the
    correct shadow IVs 8/7/14 it is a 707 WIN."""
    mimikyu = _make_battle_pokemon(
        'Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'],
        'ultra', 2, 14, 14, 15)
    raikou = _make_battle_pokemon(
        'Raikou', 'THUNDER_SHOCK', ['WILD_CHARGE', 'AURA_SPHERE'],
        'ultra', 2, 8, 7, 14, shadow=True)
    r = simulate(mimikyu, raikou, charged_policy_0=pvpoke_dp,
                 charged_policy_1=pvpoke_dp, log=True)
    assert r.winner == 0
    assert round(r.pvpoke_score(0)) == 707
