"""Tests for the dive-card renderer (scripts/deep_dive_card.py) and the
opponent-IV robustness helper (deep_dive.opp_iv_robustness).

build_card_model is a pure transform of (data_obj + card_ctx), so most of
this needs no simulation. opp_iv_robustness does sim, but on a tiny top-k
cohort it is fast and we assert its weighting structure rather than a
specific (gamemaster-dependent) win count.
"""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import deep_dive_card as dc  # noqa: E402

DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"
_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)

from gopvpsim.pokemon import iv_rank  # noqa: E402


def _synthetic():
    data_obj = {
        'species': 'Corviknight', 'league': 'great', 'shadow': True,
        'cpCap': 1500,
        'movesets': [{'label': 'SAND_ATTACK / AIR_CUTTER, PAYBACK',
                      'prettyLabel': 'Sand Attack / Air Cutter, Payback'}],
        'ivA': [0, 1], 'ivD': [15, 13], 'ivS': [14, 11],
        'ivAtk': [104.5, 116.3], 'ivDef': [132.1, 126.3],
        'ivHp': [140, 138], 'ivCp': [1498, 1499], 'spRanks': [1, 57],
    }
    ctx = {
        'rec_candidates': [{'iv': 0, 'style': 'Max Bulk'},
                           {'iv': 1, 'style': 'Attack Weight'}],
        'rec_idx': 0, 'flips': {}, 'flip_map': {}, 'has_bait_axis': False,
        'opp_label': 'PvPoke default',
        'key_wins': [('Azumarill', 612.0), ('Stunfisk (Galarian)', 540.0)],
        'key_losses': [('Medicham', 430.0)],
        'single_iv_winrate': {'frac': 0.62, 'pool': 50, 'scenarios': 9},
    }
    return data_obj, ctx


def test_build_card_model_fields():
    data_obj, ctx = _synthetic()
    m = dc.build_card_model(
        data_obj, ctx, types=['steel', 'flying'],
        robust_winrate={'frac': 0.58, 'pool': 48, 'k': 512, 'scenarios': 9})
    # shadow display + types title-cased + moveset prettied
    assert m.species_display == 'Shadow Corviknight'
    assert m.shadow is True
    assert m.types == ['Steel', 'Flying']
    assert m.moveset == 'Sand Attack / Air Cutter, Payback'
    # three (here two) spreads pulled in rec order, with the right IVs/stats
    assert [s.iv_str for s in m.spreads] == ['0/15/14', '1/13/11']
    assert m.spreads[0].style == 'Max Bulk'
    assert m.spreads[0].sp_rank == 1
    assert abs(m.spreads[0].def_ - 132.1) < 1e-6
    # win-rate percentages round to whole numbers
    assert m.single_iv.pct == '62%'
    assert m.robust.pct == '58%'
    assert m.robust.k == 512
    # key wins/losses carried through, opponent names prettified
    assert m.key_wins[0][0] == 'Azumarill'
    assert any('Galarian' in n for n, _ in m.key_wins)
    assert m.key_losses[0][0] == 'Medicham'


def test_shadow_flag_from_explicit_param():
    """Regression: data_obj has NO 'shadow' key (the real render path), so the
    shadow prefix must come from the explicit shadow= param, not data_obj."""
    data_obj, ctx = _synthetic()
    del data_obj['shadow']            # mirror the live render path
    m = dc.build_card_model(data_obj, ctx, types=['steel', 'flying'],
                            shadow=True)
    assert m.species_display == 'Shadow Corviknight'
    assert m.shadow is True
    m2 = dc.build_card_model(data_obj, ctx, types=['steel', 'flying'],
                             shadow=False)
    assert m2.species_display == 'Corviknight'
    assert m2.shadow is False


def test_build_card_model_no_robust():
    data_obj, ctx = _synthetic()
    m = dc.build_card_model(data_obj, ctx, types=['steel', 'flying'])
    assert m.robust is None
    assert m.single_iv is not None


def test_render_standalone_is_self_contained():
    data_obj, ctx = _synthetic()
    m = dc.build_card_model(data_obj, ctx, types=['steel', 'flying'])
    html = dc.render_card_html(m, standalone=True)
    assert html.lstrip().startswith('<!DOCTYPE html>')
    assert '<html' in html and '</html>' in html
    assert '.ddcard' in html          # CARD_CSS is inlined
    assert 'Shadow Corviknight' in html
    # the card avoids the tooltip registry -> no unresolved data-t refs
    assert 'data-t=' not in html


def test_render_embedded_is_a_section():
    data_obj, ctx = _synthetic()
    m = dc.build_card_model(data_obj, ctx, types=['steel', 'flying'])
    emb = dc.render_card_html(m, standalone=False)
    assert emb.lstrip().startswith('<section class="ddcard"')
    assert '<html' not in emb          # relies on the page's CARD_CSS


def test_no_sprite_fallback_renders():
    data_obj, ctx = _synthetic()
    m = dc.build_card_model(data_obj, ctx, types=['steel', 'flying'],
                            sprite_uri=None)
    emb = dc.render_card_html(m, standalone=False)
    assert 'ddcard-spriteph' in emb    # CSS fallback block, not an <img>
    assert '<img' not in emb


def test_opp_iv_robustness_weighting():
    """total == (number of top-k opponent IVs) x n_scenarios for a
    fixed-form opponent, regardless of how dedup collapses them; wins is a
    valid sub-count."""
    focal_ivs = tuple(iv_rank('Corviknight', league='great', shadow=True)[0][k]
                      for k in ('atk_iv', 'def_iv', 'sta_iv'))
    k = 32
    scenarios = [(1, 1), (2, 2)]
    n_ivs = len(iv_rank('Azumarill', league='great', shadow=False)[:k])
    res = deep_dive.opp_iv_robustness(
        'Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'], True,
        focal_ivs, 'Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], False,
        'great', scenarios, k=k)
    assert res is not None
    wins, total = res
    assert total == n_ivs * len(scenarios)
    assert 0.0 <= wins <= total


def test_compute_card_robustness_covers_all_with_movesets():
    """With opp_movesets threaded from the dive, EVERY opponent is covered --
    including the unranked shadow self-mirror that get_default_moveset would
    drop. This is what unifies the single-IV / robustness denominators."""
    focal_ivs = tuple(iv_rank('Corviknight', league='great', shadow=True)[0][k]
                      for k in ('atk_iv', 'def_iv', 'sta_iv'))
    opps = ['Azumarill', 'Corviknight (Shadow)']
    movesets = [('BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH']),
                ('SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'])]
    res = deep_dive._compute_card_robustness(
        'Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'], True,
        focal_ivs, 'great', opps, [(1, 1)], opp_movesets=movesets, k=8)
    assert res is not None
    assert res['pool'] == 2          # both covered, incl. the unranked mirror
    # Without movesets, the unranked shadow mirror is dropped (fallback path).
    res2 = deep_dive._compute_card_robustness(
        'Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'], True,
        focal_ivs, 'great', opps, [(1, 1)], opp_movesets=None, k=8)
    assert res2['pool'] == 1         # only Azumarill resolves via defaults


def test_opp_iv_robustness_signature_dedup_is_exact():
    """The damage-signature dedup must give bit-identical (wins, total) to the
    no-dedup reference, while using strictly fewer sims -- including the
    shadow-MISMATCH case (shadow focal vs non-shadow opponent), where the
    signature module's effective-atk CMP column could in principle diverge
    from the engine's cmp_atk. Locks both correctness and that dedup fires."""
    from gopvpsim.data import get_default_moveset
    focal_ivs = tuple(iv_rank('Corviknight', league='great', shadow=True)[0][k]
                      for k in ('atk_iv', 'def_iv', 'sta_iv'))
    fbp = deep_dive.make_battle_pokemon(
        'Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'],
        'great', 2, *focal_ivs, shadow=True)
    scen = [(1, 1), (0, 2), (2, 0)]
    for name, sh in [('Azumarill', False), ('Quagsire', True)]:
        of, oc = get_default_moveset(name, league='great', shadow=sh)
        rk = iv_rank(name, league='great', shadow=sh)[:64]
        g_sig = deep_dive._opp_robustness_groups(
            fbp, 'Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'], True,
            focal_ivs, name, of, oc, sh, 'great', rk, dedup='signature')
        g_non = deep_dive._opp_robustness_groups(
            fbp, 'Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'], True,
            focal_ivs, name, of, oc, sh, 'great', rk, dedup='none')
        assert sum(len(g) for g in g_sig) == 64        # partition is complete
        assert len(g_sig) < len(g_non)                 # dedup actually fires
        args = ('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'], True,
                focal_ivs, name, of, oc, sh, 'great', scen)
        r_sig = deep_dive.opp_iv_robustness(*args, k=64, dedup='signature')
        r_non = deep_dive.opp_iv_robustness(*args, k=64, dedup='none')
        assert r_sig == r_non, f'{name}: signature {r_sig} != none {r_non}'


def test_opp_iv_robustness_form_change_branch():
    """Lock the per_iv=True path: a form-change opponent (Aegislash, whose
    Blade-side stats diverge) must be detected and still satisfy the weighting
    invariant (each top-k IV is its own group, so total == n_ivs x scenarios)."""
    assert deep_dive._species_has_form_change('Aegislash (Shield)') is True
    focal_ivs = tuple(iv_rank('Corviknight', league='great', shadow=True)[0][k]
                      for k in ('atk_iv', 'def_iv', 'sta_iv'))
    k = 16
    scenarios = [(1, 1)]
    n_ivs = len(iv_rank('Aegislash (Shield)', league='great', shadow=False)[:k])
    res = deep_dive.opp_iv_robustness(
        'Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'], True,
        focal_ivs, 'Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT',
        ['SHADOW_BALL', 'GYRO_BALL'], False, 'great', scenarios, k=k)
    assert res is not None
    wins, total = res
    assert total == n_ivs * len(scenarios)
    assert 0.0 <= wins <= total
