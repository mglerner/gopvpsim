"""Sensitivity of the shipped Cramorant strat to each fitted constant.

Answers "is the sheet over-parameterised?" before any re-fit campaign
spends effort tuning constants that do not move results. Perturbs each
constant four ways and reports how many of the 2,394 corpus cells change.

Run: python scripts/cramorant_sensitivity.py    (~1 minute)
Written 2026-09-10 for the post-rebalance re-fit; see
docs/validations/2026-09-10_cramorant_sensitivity.md for that run's numbers.

run_variant() sets module globals and never restores them, so every run
here snapshots and restores the full constant set -- otherwise a
perturbation leaks into the next measurement.
"""
import sys, traceback
sys.path.insert(0, 'scripts')
import cramorant_policy_lab as lab
import gopvpsim.battle as B

CONSTS = [n for n in dir(B) if n.startswith('_POGODIVES_') or n.startswith('_CRAM_')]
SNAP = {n: getattr(B, n) for n in CONSTS}

PERTURB = {
    '_POGODIVES_DIVE_GATE_DPE':       [2.3, 2.6, 3.5, 4.0],
    '_POGODIVES_TANK_AGGRESSIVE':     [1.2, 1.3, 1.6, 1.9],
    '_POGODIVES_TANK_CONSERVATIVE':   [1.8, 2.0, 2.4, 2.6],
    '_POGODIVES_TANK_LEAD':           [0.30, 0.35, 0.45, 10.0],
    '_POGODIVES_GATE_DPT_MAX':        [0.016, 0.019, 0.026, 0.030],
    '_POGODIVES_GATE_MIN_ENERGY':     [35, 45, 50, 55],
    '_POGODIVES_GATE_0V0_MIN_ENERGY': [35, 45, 50, 55],
    '_POGODIVES_GATE_MISSILE_FRAC':   [0.10, 0.12, 0.18, 0.22],
    '_POGODIVES_GATE_MISSILE_FAST':   [3.4, 3.8, 4.6, 5.2],
    '_POGODIVES_TANK_CHEAP_FRAC':     [0.10, 0.12, 0.20, 0.30],
}

pools = {}
for lg in ('great', 'ultra'):
    pools[lg], _ = lab.load_pool(lg)


def restore():
    for n, v in SNAP.items():
        setattr(B, n, v)


def run():
    """One full corpus pass with whatever constants are currently set."""
    out = {}
    for lg in ('great', 'ultra'):
        for c in lab.run_variant('x', dict(lab.PVPOKE_DEFAULTS), lg, pools[lg],
                                 pogodives_focal=True):
            out[(c['league'], c['opp'], c['s1'], c['s2'], c['bait'])] = (
                c['score'], c['winner'])
    return out


restore()
base = run()
restore()
n = len(base)
wins = lambda d: sum(1 for v in d.values() if v[1] == 0)
print(f"corpus cells: {n}   baseline wins: {wins(base)}\n")
print(f"  {'constant':<34}{'shipped':>8}{'max moved':>12}{'  net-W range':>15}")
rows = []
for name, alts in PERTURB.items():
    ship = SNAP.get(name)
    worst, dws, err = 0, [], None
    for a in alts:
        try:
            restore(); setattr(B, name, a)
            got = run()
            worst = max(worst, sum(1 for k in base if base[k] != got.get(k)))
            dws.append(wins(got) - wins(base))
        except Exception as e:
            err = f'{type(e).__name__} at {name}={a}'
            break
        finally:
            restore()
    rows.append((worst, name, ship, dws, err))
for worst, name, ship, dws, err in sorted(rows, reverse=True):
    if err:
        print(f"  {name:<34}{ship!s:>8}   ERROR: {err}")
        continue
    pct = 100.0 * worst / n
    tag = '   <-- near-decorative' if pct < 1.0 else ''
    print(f"  {name:<34}{ship!s:>8}{worst:>7} ({pct:4.1f}%)"
          f"   [{min(dws):+d}, {max(dws):+d}]{tag}")
