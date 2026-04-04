#!/usr/bin/env python
"""
Look up move stats from the gamemaster.

Usage:
    python scripts/moves.py BUBBLE
    python scripts/moves.py PSYCHO_CUT DYNAMIC_PUNCH GIGATON_HAMMER

If no arguments are given, lists all moves.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.moves import get_moves


def fmt_move(move_type, move):
    if move_type == 'fast':
        return (
            f"  {move['moveId']:<30} type={move['type']:<10} "
            f"power={move['power']:<5} energyGain={move['energyGain']:<4} "
            f"turns={move.get('_turns', move.get('turns', '?'))}"
        )
    else:
        buffs = ''
        if move.get('buffs'):
            target = move.get('buffTarget', '?')
            buffs = f"  buffs={move['buffs']} ({target}, {move.get('buffApplyChance','?')})"
        return (
            f"  {move['moveId']:<30} type={move['type']:<10} "
            f"power={move['power']:<5} energy={move['energy']:<4}{buffs}"
        )


def main():
    fast_moves, charged_moves = get_moves()

    queries = [q.upper() for q in sys.argv[1:]]

    if not queries:
        print("\n=== FAST MOVES ===")
        for mid in sorted(fast_moves):
            print(fmt_move('fast', fast_moves[mid]))
        print("\n=== CHARGED MOVES ===")
        for mid in sorted(charged_moves):
            print(fmt_move('charged', charged_moves[mid]))
        return

    for q in queries:
        if q in fast_moves:
            m = fast_moves[q]
            print(f"\n[FAST] {fmt_move('fast', m).strip()}")
        elif q in charged_moves:
            m = charged_moves[q]
            print(f"\n[CHARGED] {fmt_move('charged', m).strip()}")
        else:
            print(f"\n{q}: NOT FOUND")


if __name__ == '__main__':
    main()
