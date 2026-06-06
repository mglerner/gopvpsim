#!/usr/bin/env python
"""Audit every PvPoke-oracle matchup in tests/test_battle.py against the
Node harness (scripts/pvpoke_trace.js).

Strategy: the test suite passing already proves our sim == each recorded
fixture, and the xfail cases are exactly the documented sim != PvPoke
divergences. So we don't re-type PvPoke's score matrices here (that would
just re-introduce the typo risk we're auditing for). Instead we run BOTH
our sim and the harness for all 9 shield combos of every oracle matchup
and compare score / winner / chargedLog directly:

  * non-divergence cell, sim == harness  -> fixture validated transitively
  * non-divergence cell, sim != harness  -> NEW divergence, must flag
  * divergence cell,     sim != harness  -> documented divergence intact
  * divergence cell,     sim == harness  -> divergence vanished, flag to un-xfail

Usage:
    python scripts/audit_oracle_harness.py [--pvpoke-root PATH]

Exit 0 if every cell is either an exact match or a still-present documented
divergence; nonzero otherwise.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tests'))
DEFAULT_PVPOKE_ROOT = Path.home() / 'coding' / 'MGLPoGo' / 'pvpoke'
HARNESS = REPO / 'scripts' / 'pvpoke_trace.js'

from test_battle import _make_battle_pokemon, _extract_battle_log  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402


def P(species, fast, charged, ivs, hid, shadow=False):
    """One side of a matchup. `species` is our display name; `hid` is the
    PvPoke speciesId for the harness."""
    return dict(species=species, fast=fast, charged=list(charged),
                ivs=ivs, hid=hid, shadow=shadow)


# Every oracle matchup with a hand-typed PvPoke score/log in test_battle.py.
# xfail_cells: (s1, s2) combos pinned as documented divergences (Aegislash
# bug #3 cascade). Everything else must match the harness exactly.
MATCHUPS = [
    dict(label='medicham_vs_azumarill',
         p1=P('Medicham', 'PSYCHO_CUT', ['DYNAMIC_PUNCH', 'PSYCHIC'], (5, 15, 15), 'medicham'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], (8, 15, 15), 'azumarill')),
    dict(label='azumarill_vs_forretress_sand_rock',
         p1=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], (4, 15, 13), 'azumarill'),
         p2=P('Forretress', 'VOLT_SWITCH', ['SAND_TOMB', 'ROCK_TOMB'], (5, 15, 13), 'forretress')),
    dict(label='azumarill_vs_forretress_rt_only',
         p1=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], (4, 15, 13), 'azumarill'),
         p2=P('Forretress', 'VOLT_SWITCH', ['ROCK_TOMB'], (5, 15, 13), 'forretress')),
    dict(label='beedrill_vs_medicham_fell_stinger',
         p1=P('Beedrill', 'POISON_JAB', ['FELL_STINGER', 'X_SCISSOR'], (4, 15, 15), 'beedrill'),
         p2=P('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], (7, 15, 14), 'medicham')),
    dict(label='corviknight_vs_medicham_air_cutter',
         p1=P('Corviknight', 'AIR_SLASH', ['AIR_CUTTER', 'PAYBACK'], (4, 12, 14), 'corviknight'),
         p2=P('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], (7, 15, 14), 'medicham')),
    dict(label='mienfoo_vs_medicham_high_jump_kick',
         p1=P('Mienfoo', 'LOW_KICK', ['HIGH_JUMP_KICK', 'LOW_SWEEP'], (13, 15, 15), 'mienfoo'),
         p2=P('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], (7, 15, 14), 'medicham')),
    dict(label='corviknight_vs_azumarill_air_cutter_buff',
         p1=P('Corviknight', 'AIR_SLASH', ['AIR_CUTTER', 'PAYBACK'], (4, 12, 14), 'corviknight'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill')),
    dict(label='shadow_swampert_vs_registeel',
         p1=P('Swampert', 'MUD_SHOT', ['HYDRO_CANNON', 'EARTHQUAKE'], (15, 15, 15), 'swampert_shadow', shadow=True),
         p2=P('Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST'], (15, 15, 15), 'registeel')),
    dict(label='corviknight_mirror_both_buff',
         p1=P('Corviknight', 'AIR_SLASH', ['AIR_CUTTER'], (4, 12, 14), 'corviknight'),
         p2=P('Corviknight', 'AIR_SLASH', ['AIR_CUTTER'], (4, 12, 14), 'corviknight')),
    # Morpeko cells 1v1/1v2/2v1/2v2 differ on chargedLog only (score+winner
    # match). PvPoke bug #8: its Battle.js:1536 form-toggle guard makes
    # Morpeko stick in Hangry after the first charged move instead of
    # toggling back. OUR two-way toggle is correct (verified in-game
    # 2026-06-06). See DEVELOPER_NOTES "PvPoke bugs found" #8.
    dict(label='morpeko_vs_azumarill_form_change',
         p1=P('Morpeko (Full Belly)', 'THUNDER_SHOCK', ['AURA_WHEEL_ELECTRIC', 'PSYCHIC_FANGS'], (5, 14, 15), 'morpeko_full_belly'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill'),
         xfail_cells={(1, 1), (1, 2), (2, 1), (2, 2)}),
    dict(label='aegislash_vs_azumarill_form_change',
         p1=P('Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT', ['SHADOW_BALL', 'GYRO_BALL'], (4, 14, 15), 'aegislash_shield'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill'),
         xfail_cells={(0, 1), (0, 2), (1, 1), (1, 2), (2, 1), (2, 2)}),
    dict(label='mimikyu_vs_azumarill_form_change',
         p1=P('Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'], (5, 13, 15), 'mimikyu'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill')),
]

LEAGUE = 'great'


def norm_log(entries):
    """Harness chargedLog tags shadow forms ' (Shadow)'; our _extract_battle_log
    drops it. Strip it so the two are comparable. Form suffixes (Blade,
    Busted, Hangry, Full Belly) are kept by both sides."""
    return [e.replace(' (Shadow)', '') for e in entries]


def run_sim(m, s1, s2):
    a = _make_battle_pokemon(m['p1']['species'], m['p1']['fast'], m['p1']['charged'],
                             LEAGUE, s1, *m['p1']['ivs'], shadow=m['p1']['shadow'])
    d = _make_battle_pokemon(m['p2']['species'], m['p2']['fast'], m['p2']['charged'],
                             LEAGUE, s2, *m['p2']['ivs'], shadow=m['p2']['shadow'])
    r = simulate(a, d, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp, log=True)
    return (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)),
            r.winner, _extract_battle_log(r))


def run_harness(m, s1, s2, root):
    cmd = ['node', str(HARNESS), '--pvpoke-root', str(root), '--cp', '1500',
           '--p1', m['p1']['hid'], '--p1-fast', m['p1']['fast'],
           '--p1-charged', ','.join(m['p1']['charged']),
           '--p1-ivs', '{}/{}/{}'.format(*m['p1']['ivs']), '--p1-shields', str(s1),
           '--p2', m['p2']['hid'], '--p2-fast', m['p2']['fast'],
           '--p2-charged', ','.join(m['p2']['charged']),
           '--p2-ivs', '{}/{}/{}'.format(*m['p2']['ivs']), '--p2-shields', str(s2)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f'harness rc={proc.returncode}: {proc.stderr.strip()}')
    d = json.loads(proc.stdout)
    return (round(d['score'][0]), round(d['score'][1]),
            d['winner'], norm_log(d['chargedLog']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pvpoke-root', type=Path, default=DEFAULT_PVPOKE_ROOT)
    args = ap.parse_args()
    if not args.pvpoke_root.exists():
        sys.stderr.write(f'PvPoke root not found: {args.pvpoke_root}\n')
        return 2

    new_divergences = []   # sim != harness on a cell NOT marked xfail
    vanished = []          # sim == harness on a cell marked xfail
    confirmed_div = []     # sim != harness on an xfail cell (expected)
    n_cells = 0

    for m in MATCHUPS:
        xfail = m.get('xfail_cells', set())
        print(f'\n{m["label"]}')
        for s1 in (0, 1, 2):
            for s2 in (0, 1, 2):
                n_cells += 1
                ss0, ss1, sw, slog = run_sim(m, s1, s2)
                hs0, hs1, hw, hlog = run_harness(m, s1, s2, args.pvpoke_root)
                score_ok = (ss0 == hs0 and ss1 == hs1)
                win_ok = (sw == hw)
                log_ok = (slog == hlog)
                match = score_ok and win_ok and log_ok
                cell = (s1, s2)
                is_xfail = cell in xfail
                if match:
                    tag = 'OK'
                    if is_xfail:
                        tag = 'VANISHED'
                        vanished.append((m['label'], cell))
                else:
                    if is_xfail:
                        tag = 'div(known)'
                        confirmed_div.append((m['label'], cell))
                    else:
                        tag = 'MISMATCH'
                        new_divergences.append(
                            (m['label'], cell,
                             f'sim s0/s1={ss0}/{ss1} win={sw}; '
                             f'harness s0/s1={hs0}/{hs1} win={hw}; '
                             f'log_ok={log_ok}'))
                flag = '' if (match or is_xfail) else '   <<<'
                print(f'  [{s1}v{s2}] {tag:11s} '
                      f'sim({ss0}/{ss1},w{sw})  pvpoke({hs0}/{hs1},w{hw})  '
                      f'log_ok={log_ok}{flag}')

    print('\n' + '=' * 70)
    print(f'cells checked: {n_cells}')
    print(f'confirmed documented divergences: {len(confirmed_div)}')
    for lbl, cell in confirmed_div:
        print(f'    {lbl} {cell}')
    if vanished:
        print(f'\nDIVERGENCES THAT VANISHED (consider un-xfail): {len(vanished)}')
        for lbl, cell in vanished:
            print(f'    {lbl} {cell}')
    if new_divergences:
        print(f'\nNEW / UNDOCUMENTED MISMATCHES: {len(new_divergences)}')
        for lbl, cell, detail in new_divergences:
            print(f'    {lbl} {cell}: {detail}')
    if not new_divergences and not vanished:
        print('\nAll oracle cells match the harness or are still-present '
              'documented divergences.')
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
