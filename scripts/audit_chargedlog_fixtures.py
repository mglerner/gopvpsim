#!/usr/bin/env python3
"""Audit existing test_battle.py chargedLog fixtures vs the PvPoke harness.

For each oracle-style test that asserts on `expected_log`, run every
parametrize case through both `scripts/pvpoke_trace.js` (PvPoke ground
truth) and our `gopvpsim.battle.simulate(..., pvpoke_dp)`, then
classify each fixture as one of:

  CLEAN       fixture == ours == PvPoke
  STALE       fixture == ours != PvPoke (fixture captured against our
              old output; needs updating to match PvPoke)
  DIVERGENCE  fixture != ours and ours != PvPoke (silent mismatch:
              fixture was captured against an even older sim output,
              and our current behavior also disagrees with PvPoke)
  US-ONLY     fixture == PvPoke != ours (we regressed since the
              fixture was authored)

The first two categories cover everything the chargedLog assertion
catches today. STALE entries should be updated to PvPoke ground truth.
DIVERGENCE / US-ONLY entries deserve localization sessions.

Run: python scripts/audit_chargedlog_fixtures.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO))

from gopvpsim.battle import simulate, pvpoke_dp
from tests.test_battle import _make_battle_pokemon, _extract_battle_log

PVPOKE_ROOT = Path.home() / 'coding' / 'MGLPoGo' / 'pvpoke'
HARNESS = REPO / 'scripts' / 'pvpoke_trace.js'


# (test_name, p1_species, p1_fast, p1_ch, p1_ivs, p2_species, p2_fast,
#  p2_ch, p2_ivs, p1_pvpoke_id, p2_pvpoke_id, cases)
# cases: list of (sh1, sh2, expected_log)
TESTS = [
    {
        'name': 'medicham_vs_azumarill',
        'p1': ('Medicham', 'PSYCHO_CUT', ['DYNAMIC_PUNCH', 'PSYCHIC'], (5, 15, 15)),
        'p2': ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], (8, 15, 15)),
        'pv1': 'medicham', 'pv2': 'azumarill',
        # (sh1, sh2, expected_log)
        'cases': [
            (0, 0, ['Medicham: Psychic', 'Azumarill: Hydro Pump', 'Medicham: Psychic', 'Azumarill: Ice Beam']),
            (0, 1, ['Medicham: Psychic (shielded)', 'Azumarill: Hydro Pump', 'Medicham: Psychic', 'Azumarill: Ice Beam']),
            (0, 2, ['Medicham: Psychic (shielded)', 'Azumarill: Hydro Pump', 'Medicham: Psychic (shielded)', 'Azumarill: Ice Beam']),
            (1, 0, ['Medicham: Psychic', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Hydro Pump', 'Medicham: Psychic']),
            (1, 1, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Hydro Pump', 'Medicham: Dynamic Punch']),
            (1, 2, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic (shielded)', 'Azumarill: Hydro Pump', 'Medicham: Dynamic Punch']),
            (2, 0, ['Medicham: Psychic', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Hydro Pump (shielded)', 'Medicham: Psychic']),
            (2, 1, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic', 'Azumarill: Ice Beam (shielded)', 'Medicham: Dynamic Punch', 'Azumarill: Ice Beam', 'Medicham: Dynamic Punch']),
            (2, 2, ['Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Psychic (shielded)', 'Azumarill: Ice Beam (shielded)', 'Medicham: Dynamic Punch', 'Medicham: Dynamic Punch', 'Azumarill: Hydro Pump']),
        ],
    },
    {
        'name': 'azumarill_vs_forretress_sand_rock',
        'p1': ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], (4, 15, 13)),
        'p2': ('Forretress', 'VOLT_SWITCH', ['SAND_TOMB', 'ROCK_TOMB'], (5, 15, 13)),
        'pv1': 'azumarill', 'pv2': 'forretress',
        'cases': [
            (0, 0, ['Forretress: Sand Tomb', 'Azumarill: Hydro Pump', 'Forretress: Sand Tomb', 'Forretress: Sand Tomb']),
            (0, 1, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb', 'Azumarill: Ice Beam', 'Forretress: Sand Tomb']),
            (0, 2, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb']),
            (1, 0, ['Forretress: Sand Tomb', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Ice Beam']),
            (1, 1, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb']),
            (1, 2, ['Forretress: Sand Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb']),
            (2, 0, ['Forretress: Sand Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Sand Tomb (shielded)', 'Forretress: Sand Tomb', 'Azumarill: Ice Beam']),
            (2, 1, ['Forretress: Sand Tomb (shielded)', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb']),
            (2, 2, ['Forretress: Sand Tomb (shielded)', 'Azumarill: Ice Beam (shielded)', 'Forretress: Sand Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb']),
        ],
    },
    {
        'name': 'azumarill_vs_forretress_rt_only',
        'p1': ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], (4, 15, 13)),
        'p2': ('Forretress', 'VOLT_SWITCH', ['ROCK_TOMB'], (5, 15, 13)),
        'pv1': 'azumarill', 'pv2': 'forretress',
        'cases': [
            (0, 0, ['Forretress: Rock Tomb', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam']),
            (0, 1, ['Forretress: Rock Tomb', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam']),
            (0, 2, ['Forretress: Rock Tomb', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Hydro Pump (shielded)']),
            (1, 0, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam', 'Forretress: Rock Tomb']),
            (1, 1, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Ice Beam', 'Forretress: Rock Tomb']),
            (1, 2, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb']),
            (2, 0, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb (shielded)', 'Forretress: Rock Tomb', 'Azumarill: Hydro Pump']),
            (2, 1, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump', 'Forretress: Rock Tomb']),
            (2, 2, ['Forretress: Rock Tomb (shielded)', 'Azumarill: Ice Beam (shielded)', 'Forretress: Rock Tomb (shielded)', 'Azumarill: Hydro Pump (shielded)', 'Forretress: Rock Tomb']),
        ],
    },
    {
        'name': 'beedrill_vs_medicham_fell_stinger',
        'p1': ('Beedrill', 'POISON_JAB', ['FELL_STINGER', 'X_SCISSOR'], (4, 15, 15)),
        'p2': ('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], (7, 15, 14)),
        'pv1': 'beedrill', 'pv2': 'medicham',
        'cases': [
            (0, 0, ['Beedrill: X-Scissor', 'Medicham: Ice Punch', 'Beedrill: X-Scissor']),
            (0, 1, ['Beedrill: X-Scissor (shielded)', 'Medicham: Ice Punch', 'Beedrill: X-Scissor', 'Medicham: Ice Punch']),
            (0, 2, ['Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch', 'Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch', 'Beedrill: X-Scissor']),
            (1, 0, ['Beedrill: X-Scissor', 'Medicham: Ice Punch (shielded)', 'Beedrill: X-Scissor']),
            (1, 1, ['Beedrill: X-Scissor (shielded)', 'Medicham: Ice Punch (shielded)', 'Beedrill: X-Scissor', 'Medicham: Ice Punch', 'Beedrill: Fell Stinger']),
            (1, 2, ['Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch (shielded)', 'Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch', 'Beedrill: X-Scissor']),
            (2, 0, ['Beedrill: X-Scissor', 'Medicham: Ice Punch (shielded)', 'Beedrill: X-Scissor']),
            (2, 1, ['Beedrill: X-Scissor (shielded)', 'Medicham: Ice Punch (shielded)', 'Beedrill: X-Scissor', 'Medicham: Ice Punch (shielded)', 'Beedrill: Fell Stinger']),
            (2, 2, ['Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch (shielded)', 'Beedrill: Fell Stinger (shielded)', 'Medicham: Ice Punch (shielded)', 'Beedrill: X-Scissor']),
        ],
    },
    {
        'name': 'mienfoo_vs_medicham_high_jump_kick',
        'p1': ('Mienfoo', 'LOW_KICK', ['HIGH_JUMP_KICK', 'LOW_SWEEP'], (13, 15, 15)),
        'p2': ('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], (7, 15, 14)),
        'pv1': 'mienfoo', 'pv2': 'medicham',
        'cases': [
            (0, 0, ['Mienfoo: High Jump Kick', 'Medicham: Dynamic Punch']),
            (0, 1, ['Mienfoo: High Jump Kick (shielded)', 'Medicham: Dynamic Punch']),
            (0, 2, ['Mienfoo: Low Sweep (shielded)', 'Medicham: Dynamic Punch']),
            (1, 0, ['Mienfoo: High Jump Kick', 'Medicham: Ice Punch (shielded)', 'Mienfoo: High Jump Kick']),
            (1, 1, ['Mienfoo: High Jump Kick (shielded)', 'Medicham: Ice Punch (shielded)', 'Mienfoo: High Jump Kick', 'Medicham: Ice Punch']),
            (1, 2, ['Mienfoo: Low Sweep (shielded)', 'Medicham: Ice Punch (shielded)', 'Mienfoo: High Jump Kick (shielded)', 'Medicham: Ice Punch']),
            (2, 0, ['Mienfoo: High Jump Kick', 'Mienfoo: Low Sweep', 'Medicham: Dynamic Punch (shielded)']),
            (2, 1, ['Mienfoo: High Jump Kick (shielded)', 'Mienfoo: Low Sweep']),
            (2, 2, ['Mienfoo: Low Sweep (shielded)', 'Mienfoo: High Jump Kick (shielded)']),
        ],
    },
    {
        'name': 'corviknight_vs_azumarill_air_cutter_buff',
        'p1': ('Corviknight', 'AIR_SLASH', ['AIR_CUTTER', 'PAYBACK'], (4, 12, 14)),
        'p2': ('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13)),
        'pv1': 'corviknight', 'pv2': 'azumarill',
        'cases': [
            (0, 0, ['Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
            (0, 1, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
            (0, 2, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
            (1, 0, ['Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam']),
            (1, 1, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam']),
            (1, 2, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam']),
            (2, 0, ['Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
            (2, 1, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Air Cutter']),
            (2, 2, ['Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter (shielded)', 'Azumarill: Ice Beam (shielded)', 'Corviknight: Air Cutter', 'Azumarill: Ice Beam', 'Corviknight: Payback']),
        ],
    },
    {
        'name': 'corviknight_mirror_both_buff',
        'p1': ('Corviknight', 'AIR_SLASH', ['AIR_CUTTER'], (4, 12, 14)),
        'p2': ('Corviknight', 'AIR_SLASH', ['AIR_CUTTER'], (4, 12, 14)),
        'pv1': 'corviknight', 'pv2': 'corviknight',
        'cases': [
            (0, 0, ['Corviknight: Air Cutter'] * 8),
            (0, 1, ['Corviknight: Air Cutter (shielded)'] + ['Corviknight: Air Cutter'] * 7),
            (0, 2, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)'] + ['Corviknight: Air Cutter'] * 5),
            (1, 0, ['Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)'] + ['Corviknight: Air Cutter'] * 6),
            (1, 1, ['Corviknight: Air Cutter (shielded)'] * 2 + ['Corviknight: Air Cutter'] * 8),
            (1, 2, ['Corviknight: Air Cutter (shielded)'] * 3 + ['Corviknight: Air Cutter'] * 7),
            (2, 0, ['Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)'] + ['Corviknight: Air Cutter'] * 4),
            (2, 1, ['Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter (shielded)', 'Corviknight: Air Cutter', 'Corviknight: Air Cutter (shielded)'] + ['Corviknight: Air Cutter'] * 6),
            (2, 2, ['Corviknight: Air Cutter (shielded)'] * 4 + ['Corviknight: Air Cutter'] * 6),
        ],
    },
]


def run_harness(spec, sh1, sh2):
    p1 = spec['p1']; p2 = spec['p2']
    cmd = [
        'node', str(HARNESS),
        '--pvpoke-root', str(PVPOKE_ROOT),
        '--cp', '1500',
        '--p1', spec['pv1'], '--p1-fast', p1[1],
        '--p1-charged', ','.join(p1[2]),
        '--p1-ivs', '/'.join(str(x) for x in p1[3]),
        '--p1-shields', str(sh1),
        '--p2', spec['pv2'], '--p2-fast', p2[1],
        '--p2-charged', ','.join(p2[2]),
        '--p2-ivs', '/'.join(str(x) for x in p2[3]),
        '--p2-shields', str(sh2),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None, f'harness err: {proc.stderr[:200]}'
    d = json.loads(proc.stdout)
    # Strip "(Shadow)" / "(Busted)" tags PvPoke adds; our extractor preserves
    # what our sim writes. Comparison should normalize species names if both
    # sides agree. For now just return raw.
    return d['chargedLog'], None


def run_ours(spec, sh1, sh2):
    p1 = spec['p1']; p2 = spec['p2']
    bp1 = _make_battle_pokemon(p1[0], p1[1], list(p1[2]), 'great', sh1, *p1[3])
    bp2 = _make_battle_pokemon(p2[0], p2[1], list(p2[2]), 'great', sh2, *p2[3])
    r = simulate(bp1, bp2,
                 charged_policy_0=pvpoke_dp,
                 charged_policy_1=pvpoke_dp,
                 log=True)
    return _extract_battle_log(r)


def main():
    summary = {'CLEAN': 0, 'STALE': 0, 'DIVERGENCE': 0, 'US-ONLY': 0, 'ERR': 0}
    detail = []

    for spec in TESTS:
        for sh1, sh2, expected in spec['cases']:
            try:
                ours = run_ours(spec, sh1, sh2)
            except Exception as e:
                summary['ERR'] += 1
                detail.append((spec['name'], sh1, sh2, 'ERR-OURS', str(e), None, None))
                continue
            pv, err = run_harness(spec, sh1, sh2)
            if err:
                summary['ERR'] += 1
                detail.append((spec['name'], sh1, sh2, 'ERR-PV', err, None, None))
                continue
            ours_eq_fix = (ours == expected)
            pv_eq_fix = (pv == expected)
            ours_eq_pv = (ours == pv)
            if ours_eq_fix and pv_eq_fix:
                cls = 'CLEAN'
            elif ours_eq_fix and not pv_eq_fix:
                cls = 'STALE'
            elif not ours_eq_fix and pv_eq_fix:
                cls = 'US-ONLY'
            else:
                cls = 'DIVERGENCE'
            summary[cls] += 1
            detail.append((spec['name'], sh1, sh2, cls, expected, ours, pv))

    print('=== Per-test summary ===')
    by_test = {}
    for d in detail:
        by_test.setdefault(d[0], {'CLEAN':0,'STALE':0,'DIVERGENCE':0,'US-ONLY':0,'ERR-OURS':0,'ERR-PV':0})
        by_test[d[0]][d[3]] += 1
    for tn, counts in by_test.items():
        cstr = ' '.join(f'{k}={v}' for k,v in counts.items() if v)
        print(f'  {tn:50s} {cstr}')

    print(f'\n=== Total ===')
    for k,v in summary.items():
        print(f'  {k:12s} {v}')

    print(f'\n=== Non-CLEAN cases ===')
    for tn, sh1, sh2, cls, exp, ours, pv in detail:
        if cls == 'CLEAN':
            continue
        print(f'\n[{cls}] {tn} ({sh1},{sh2})')
        if cls.startswith('ERR'):
            print(f'  err: {exp[:200]}')
            continue
        print(f'  fix: {exp}')
        print(f'  our: {ours}')
        print(f'  pv:  {pv}')


if __name__ == '__main__':
    main()
