#!/usr/bin/env python
"""IV-explorer DATA blob: closed-form cutoffs + stat bases for the 31
meta entries (plan product 5).

Design decision (2026-08-11, session 5): the browser receives BAKED
tier-0 cutoffs and never computes damage -- the JS surface shrinks to
stat math (level/CP/effective stats, reused from the parity-tested
POGOCollection) plus ``eff_atk >= cutoff`` comparisons. No damage
constants exist in JS at all, which closes the retyped-constant drift
class by construction (a scan test pins their absence).

Per ordered pair (mine, opp), vs the OPPONENT'S RANK-1 SP ANCHOR (the
page labels this: other opponent spreads shift cutoffs -- the pair
pages carry the full-cohort guarantee story):

* ``bp``: my damage-tier ladder rows (move, tier, atk_cutoff) over my
  attainable effective-atk range (worlds_tier0.tier_table);
* ``bulk``: the opponent's ladder against ME -- rows (opp move, tier,
  def_cutoff); I HOLD the bulkpoint (take < tier) iff my eff def >
  def_cutoff (strict, per def_cutoff's asymmetric contract);
* ``stage_flag``: the pair can move atk/def stages (tier0
  movable_stage_axes) -- stage-0 cutoffs are flagged on the page.

Aegislash is closed_form_excluded and carries ``excluded`` markers
instead of ladders (both as mine and as opponent).

All cutoffs are in EFFECTIVE stat space (shadow applied), matching
iv_rank and the JS stat pipeline.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from gopvpsim.pokemon import (
    iv_rank, get_species, CPM, LEAGUE_CAPS, LEAGUE_MAX_LEVEL,
    SHADOW_ATK_BONUS, SHADOW_DEF_MULT,
)
from gopvpsim.moves import get_moves, parse_types
from gopvpsim.pokemon import find_pokemon_entry

import worlds_bake as wb  # noqa: E402
import worlds_tier0 as t0  # noqa: E402


def _entry_moves(e, fast_db, charged_db):
    fm = dict(fast_db[e['fast_move_id']])
    cms = {cid: dict(charged_db[cid]) for cid in e['charged_move_ids']}
    return fm, cms


def build_data():
    entries = wb.load_meta()
    fast_db, charged_db = get_moves()
    id2name_moves = {}
    per_entry = {}
    for e in entries:
        mon = find_pokemon_entry(e['species'])
        base = get_species(e['species'])
        rk = iv_rank(e['species'], league='great', shadow=e['shadow'])
        r1 = rk[0]
        atks = [r['atk'] for r in rk]
        defs = [r['def_'] for r in rk]
        per_entry[e['species_id']] = {
            'name': e['name'],
            'species': e['species'],
            'shadow': bool(e['shadow']),
            'baseStats': {'atk': base['atk'], 'def': base['def'],
                          'hp': base['hp']},
            'types': parse_types(mon),
            'fast': e['fast_move_id'],
            'charged': list(e['charged_move_ids']),
            'moveNames': {e['fast_move_id']: e['fast_move'],
                          **dict(zip(e['charged_move_ids'],
                                     e['charged_moves']))},
            'anchor': {'ivs': [r1['atk_iv'], r1['def_iv'], r1['sta_iv']],
                       'level': r1['level'], 'atk': r1['atk'],
                       'def': r1['def_'], 'hp': r1['hp']},
            'atk_range': [min(atks), max(atks)],
            'def_range': [min(defs), max(defs)],
            'excluded': t0.closed_form_excluded(e['species']),
        }
        id2name_moves[e['species_id']] = _entry_moves(e, fast_db,
                                                     charged_db)

    pairs = {}
    ids = list(per_entry)
    for mine in ids:
        me = per_entry[mine]
        my_fm, my_cms = id2name_moves[mine]
        for opp in ids:
            if opp == mine:
                continue
            po = per_entry[opp]
            opp_fm, opp_cms = id2name_moves[opp]
            key = f'{mine}|{opp}'
            if me['excluded'] or po['excluded']:
                pairs[key] = {'excluded': True}
                continue
            (f_atk, _f_def), (_o_atk, o_def) = t0.movable_stage_axes(
                (my_fm, list(my_cms.values())),
                (opp_fm, list(opp_cms.values())))
            # Reverse direction axes for the bulk half: can the OPP's
            # atk or MY def move?
            (o_atk2, _), (_, f_def2) = t0.movable_stage_axes(
                (opp_fm, list(opp_cms.values())),
                (my_fm, list(my_cms.values())))
            bp = []
            for mid, mv in [(me['fast'], my_fm)] + list(my_cms.items()):
                if not mv.get('power', 0) > 0:
                    continue
                rows = t0.tier_table(mv, me['types'], po['types'],
                                     po['anchor']['def'],
                                     me['atk_range'][0],
                                     me['atk_range'][1])
                bp.append({'move': mid, 'rows': [
                    {'tier': r['tier'], 'atk': r['atk_cutoff']}
                    for r in rows]})
            bulk = []
            for mid, mv in [(po['fast'], opp_fm)] + list(opp_cms.items()):
                if not mv.get('power', 0) > 0:
                    continue
                d_lo = t0.staged_damage(mv, po['anchor']['atk'],
                                        me['def_range'][1], po['types'],
                                        me['types'])
                d_hi = t0.staged_damage(mv, po['anchor']['atk'],
                                        me['def_range'][0], po['types'],
                                        me['types'])
                rows = [{'tier': d_lo, 'def': None}]
                for d in range(d_lo + 1, d_hi + 1):
                    rows.append({'tier': d, 'def': t0.def_cutoff(
                        mv, po['types'], me['types'], d,
                        po['anchor']['atk'])})
                bulk.append({'move': mid, 'rows': rows})
            pairs[key] = {
                'bp': bp, 'bulk': bulk,
                'stage_flag': bool(f_atk or o_def or o_atk2 or f_def2),
            }
    return {
        'entries': per_entry,
        'pairs': pairs,
        'cpm': {str(k): v for k, v in CPM.items()},
        'leagueCap': LEAGUE_CAPS['great'],
        'maxLevel': LEAGUE_MAX_LEVEL['great'],
        'shadowAtkBonus': SHADOW_ATK_BONUS,
        'shadowDefMult': SHADOW_DEF_MULT,
    }
