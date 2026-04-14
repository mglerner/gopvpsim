#!/usr/bin/env python3
"""Sanity check scripts/pvpoke_trace.js against recorded PvPoke oracle data.

Walks the 9 Medicham/Azu + 9 Azu/Forr-full + 9 Azu/Forr-RT-only shield
scenarios from tests/test_battle.py, invokes the Node harness for each,
and asserts the harness reproduces PvPoke's published score and winner.

PvPoke scores are pulled from the comment matrices in test_battle.py
(lines 464-468, 511-515, 572-575) -- those values were read off
pvpoke.com/battle/ directly and are the only cross-checkable oracle
data we have. The expected_log tuples in the test file are our Python
sim's output, not PvPoke's; they are NOT asserted here.

Usage:
    python scripts/verify_pvpoke_harness.py [--pvpoke-root PATH]

Exits 0 on all-match, nonzero with a diff report on any divergence.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PVPOKE_ROOT = Path.home() / 'coding' / 'MGLPoGo' / 'pvpoke'
HARNESS = REPO / 'scripts' / 'pvpoke_trace.js'


@dataclass(frozen=True)
class Spec:
    species: str
    fast: str
    charged: tuple[str, ...]
    ivs: tuple[int, int, int]   # atk/def/hp


@dataclass(frozen=True)
class Case:
    label: str
    p1: Spec
    p2: Spec
    shields: tuple[int, int]          # (p1, p2)
    expected_score_side: int          # which side the oracle score is for (0 or 1)
    expected_score: int               # PvPoke's published score for that side
    expected_winner: int              # 0 or 1


MED = Spec('medicham',  'PSYCHO_CUT', ('DYNAMIC_PUNCH', 'PSYCHIC'),     (5, 15, 15))
AZU = Spec('azumarill', 'BUBBLE',     ('ICE_BEAM',      'HYDRO_PUMP'),  (8, 15, 15))
# Azu for Forr matchups uses different IVs per the test file
AZU_F = Spec('azumarill',  'BUBBLE',      ('ICE_BEAM', 'HYDRO_PUMP'), (4, 15, 13))
FORR  = Spec('forretress', 'VOLT_SWITCH', ('SAND_TOMB', 'ROCK_TOMB'),  (5, 15, 13))
FORR_RT = Spec('forretress', 'VOLT_SWITCH', ('ROCK_TOMB',),            (5, 15, 13))


# PvPoke score matrices copied from test_battle.py comments.
# Each row: shields_med (or shields_azu for Azu/Forr); each col: shields_opp.
# Winner is derived: p1 wins iff p1_score > 500.

# Medicham vs Azumarill (test_battle.py:464-468)
# Row: Med shields, Col: Azu shields. Value: Azu's PvPoke rating.
MED_AZU_AZU_SCORES = {
    (0, 0): 608, (0, 1): 730, (0, 2): 851,
    (1, 0): 475, (1, 1): 603, (1, 2): 724,
    (2, 0): 235, (2, 1): 411, (2, 2): 605,
}

# Azu vs Forretress (sand + rock), test_battle.py:511-515
# Row: Azu shields, Col: Forr shields. Value: Azu's PvPoke rating.
AZU_FORR_AZU_SCORES = {
    (0, 0): 492, (0, 1): 312, (0, 2): 222,
    (1, 0): 657, (1, 1): 429, (1, 2): 226,
    (2, 0): 612, (2, 1): 496, (2, 2): 242,
}

# Azu vs Forretress (RT-only), test_battle.py:572-575
AZU_FORR_RT_AZU_SCORES = {
    (0, 0): 480, (0, 1): 277, (0, 2): 218,
    (1, 0): 480, (1, 1): 277, (1, 2): 218,
    (2, 0): 575, (2, 1): 445, (2, 2): 265,
}


def build_cases() -> list[Case]:
    cases: list[Case] = []
    # Medicham (p1) vs Azumarill (p2): oracle gives Azu's score (p2 side).
    for (sm, sa), azu_score in MED_AZU_AZU_SCORES.items():
        winner = 1 if azu_score > 500 else 0
        cases.append(Case(
            label=f'med{sm}_azu{sa}',
            p1=MED, p2=AZU, shields=(sm, sa),
            expected_score_side=1, expected_score=azu_score,
            expected_winner=winner,
        ))
    # Azu (p1) vs Forr (p2) - full moveset. Oracle gives Azu's score (p1 side).
    for (sa, sf), azu_score in AZU_FORR_AZU_SCORES.items():
        winner = 0 if azu_score > 500 else 1
        cases.append(Case(
            label=f'azu{sa}_forr{sf}_full',
            p1=AZU_F, p2=FORR, shields=(sa, sf),
            expected_score_side=0, expected_score=azu_score,
            expected_winner=winner,
        ))
    # Azu vs Forr - RT only.
    for (sa, sf), azu_score in AZU_FORR_RT_AZU_SCORES.items():
        winner = 0 if azu_score > 500 else 1
        cases.append(Case(
            label=f'azu{sa}_forr{sf}_rtonly',
            p1=AZU_F, p2=FORR_RT, shields=(sa, sf),
            expected_score_side=0, expected_score=azu_score,
            expected_winner=winner,
        ))
    return cases


def run_harness(case: Case, pvpoke_root: Path) -> dict:
    cmd = [
        'node', str(HARNESS),
        '--pvpoke-root', str(pvpoke_root),
        '--cp', '1500',
        '--p1', case.p1.species,
        '--p1-fast', case.p1.fast,
        '--p1-charged', ','.join(case.p1.charged),
        '--p1-ivs', '{}/{}/{}'.format(*case.p1.ivs),
        '--p1-shields', str(case.shields[0]),
        '--p2', case.p2.species,
        '--p2-fast', case.p2.fast,
        '--p2-charged', ','.join(case.p2.charged),
        '--p2-ivs', '{}/{}/{}'.format(*case.p2.ivs),
        '--p2-shields', str(case.shields[1]),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f'harness failed for {case.label}:\n{proc.stderr}'
        )
    return json.loads(proc.stdout)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--pvpoke-root', type=Path, default=DEFAULT_PVPOKE_ROOT)
    args = ap.parse_args()

    if not args.pvpoke_root.exists():
        sys.stderr.write(f'PvPoke root not found: {args.pvpoke_root}\n')
        return 2

    cases = build_cases()
    failures: list[str] = []
    for case in cases:
        try:
            out = run_harness(case, args.pvpoke_root)
        except RuntimeError as e:
            failures.append(f'[{case.label}] {e}')
            print(f'  {case.label:28s}  ERROR')
            continue
        got_score  = out['score'][case.expected_score_side]
        got_winner = out['winner']
        score_ok   = got_score == case.expected_score
        winner_ok  = got_winner == case.expected_winner
        tag = 'OK' if (score_ok and winner_ok) else 'FAIL'
        side = f'p{case.expected_score_side + 1}'
        print(f'  {case.label:28s}  {tag}   '
              f'{side}_score={got_score} (want {case.expected_score})  '
              f'winner={got_winner} (want {case.expected_winner})')
        if not (score_ok and winner_ok):
            failures.append(
                f'{case.label}: {side}_score {got_score} vs {case.expected_score}, '
                f'winner {got_winner} vs {case.expected_winner}'
            )

    print()
    if failures:
        print(f'{len(failures)} / {len(cases)} FAILED')
        for f in failures:
            print(f'  {f}')
        return 1
    print(f'All {len(cases)} oracle cases match PvPoke.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
