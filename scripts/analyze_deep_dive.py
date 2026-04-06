#!/usr/bin/env python
"""
Analyze deep dive HTML output: cluster analysis and per-opponent matchup-flip tables.

Reads the embedded DATA and SCORES JSON from an interactive deep dive HTML file
and produces analysis without re-running simulations.

Usage:
    python scripts/analyze_deep_dive.py tinkaton_gh_all9.html [--moveset 0] [--opp-iv pvpoke]
"""
import argparse
import json
import re
import sys
from collections import defaultdict


def load_html_data(html_path):
    """Extract DATA and SCORES from the deep dive HTML."""
    with open(html_path, 'r') as f:
        text = f.read()

    # Extract DATA = {...};
    m = re.search(r'var DATA = ({.*?});\nvar SCORES', text, re.DOTALL)
    if not m:
        sys.exit("Could not find DATA in HTML")
    data = json.loads(m.group(1))

    # Extract SCORES = {...};
    m2 = re.search(r'var SCORES = ({.*?});\n', text, re.DOTALL)
    if not m2:
        sys.exit("Could not find SCORES in HTML")
    scores = json.loads(m2.group(1))

    return data, scores


def get_score(scores_flat, iv_idx, scenario_idx, opp_idx, n_scenarios, n_opponents):
    """Look up a single score from the flat array."""
    return scores_flat[iv_idx * n_scenarios * n_opponents + scenario_idx * n_opponents + opp_idx]


def compute_avg_scores(scores_flat, n_ivs, n_scenarios, n_opponents, scenario_indices=None):
    """Compute average score per IV across selected scenarios and all opponents."""
    if scenario_indices is None:
        scenario_indices = list(range(n_scenarios))
    avgs = []
    for iv in range(n_ivs):
        total = 0
        count = 0
        for si in scenario_indices:
            base = iv * n_scenarios * n_opponents + si * n_opponents
            for oi in range(n_opponents):
                total += scores_flat[base + oi]
                count += 1
        avgs.append(total / count if count else 0)
    return avgs


def find_matchup_flips(scores_flat, n_ivs, n_scenarios, n_opponents, ref_iv_idx,
                       threshold_ivs, scenarios, opponents):
    """
    For each threshold IV, find matchups that flip vs the reference IV.
    A flip = score changes from win (>=500) to loss (<500) or vice versa.
    Returns list of (iv_idx, opp_idx, scenario_idx, ref_score, iv_score, direction).
    """
    flips = []
    for iv_idx in threshold_ivs:
        for si in range(n_scenarios):
            for oi in range(n_opponents):
                ref_score = get_score(scores_flat, ref_iv_idx, si, oi, n_scenarios, n_opponents)
                iv_score = get_score(scores_flat, iv_idx, si, oi, n_scenarios, n_opponents)
                ref_win = ref_score >= 500
                iv_win = iv_score >= 500
                if ref_win != iv_win:
                    direction = 'gain' if iv_win else 'lose'
                    s0, s1 = scenarios[si]
                    flips.append({
                        'iv_idx': iv_idx,
                        'opp_idx': oi,
                        'opp_name': opponents[oi],
                        'scenario': f'{s0}v{s1}',
                        'scenario_idx': si,
                        'ref_score': ref_score,
                        'iv_score': iv_score,
                        'direction': direction,
                    })
    return flips


def cluster_analysis(scores_flat, data, scenario_idx, n_scenarios, n_opponents, n_ivs,
                     top_n=50):
    """
    Analyze what distinguishes the top-scoring IVs in a specific scenario.
    Returns stats about the cluster vs the rest.
    """
    # Compute per-IV average across all opponents for this scenario
    scene_avgs = []
    for iv in range(n_ivs):
        base = iv * n_scenarios * n_opponents + scenario_idx * n_opponents
        total = sum(scores_flat[base + oi] for oi in range(n_opponents))
        scene_avgs.append(total / n_opponents)

    # Sort by score, take top N
    ranked = sorted(range(n_ivs), key=lambda i: scene_avgs[i], reverse=True)
    top_set = set(ranked[:top_n])
    bot_set = set(ranked[top_n:])

    # Compute stat distributions
    def stat_summary(iv_set):
        atks = [data['ivAtk'][i] for i in iv_set]
        defs = [data['ivDef'][i] for i in iv_set]
        hps = [data['ivHp'][i] for i in iv_set]
        sps = [data['ivSp'][i] for i in iv_set]
        return {
            'atk': (min(atks), sum(atks)/len(atks), max(atks)),
            'def': (min(defs), sum(defs)/len(defs), max(defs)),
            'hp': (min(hps), sum(hps)/len(hps), max(hps)),
            'sp': (min(sps), sum(sps)/len(sps), max(sps)),
            'score': (min(scene_avgs[i] for i in iv_set),
                      sum(scene_avgs[i] for i in iv_set)/len(iv_set),
                      max(scene_avgs[i] for i in iv_set)),
        }

    top_stats = stat_summary(top_set)
    all_stats = stat_summary(range(n_ivs))

    # Find which opponents most differentiate the top cluster
    opp_diffs = []
    for oi in range(n_opponents):
        top_avg = sum(scores_flat[iv * n_scenarios * n_opponents + scenario_idx * n_opponents + oi]
                      for iv in top_set) / len(top_set)
        all_avg = sum(scores_flat[iv * n_scenarios * n_opponents + scenario_idx * n_opponents + oi]
                      for iv in range(n_ivs)) / n_ivs
        opp_diffs.append((oi, top_avg - all_avg, top_avg, all_avg))
    opp_diffs.sort(key=lambda x: x[1], reverse=True)

    return {
        'scenario_idx': scenario_idx,
        'top_stats': top_stats,
        'all_stats': all_stats,
        'top_ivs': ranked[:top_n],
        'scene_avgs': scene_avgs,
        'opp_diffs': opp_diffs,
    }


def print_cluster_analysis(analysis, data, scenarios, opponents):
    """Print cluster analysis results."""
    si = analysis['scenario_idx']
    s0, s1 = scenarios[si]
    print(f"\n{'='*70}")
    print(f"  Cluster Analysis: {s0}v{s1} shield scenario")
    print(f"{'='*70}")

    top = analysis['top_stats']
    all_ = analysis['all_stats']

    print(f"\n  Top 50 IVs vs all IVs:")
    print(f"  {'Stat':>6s}   {'Top 50 (min/avg/max)':>30s}   {'All IVs (min/avg/max)':>30s}")
    print(f"  {'-'*70}")
    for stat_name in ['atk', 'def', 'hp', 'sp', 'score']:
        t = top[stat_name]
        a = all_[stat_name]
        fmt = '.2f' if stat_name != 'hp' else '.0f'
        print(f"  {stat_name:>6s}   {t[0]:{fmt}} / {t[1]:{fmt}} / {t[2]:{fmt}}"
              f"          {a[0]:{fmt}} / {a[1]:{fmt}} / {a[2]:{fmt}}")

    # Show top IVs
    print(f"\n  Top 10 IVs for {s0}v{s1}:")
    print(f"  {'Rank':>4s}  {'IVs':>8s}  {'Atk':>7s}  {'Def':>7s}  {'HP':>3s}  {'Score':>7s}  {'Tier':>10s}")
    print(f"  {'-'*55}")
    for rank, iv in enumerate(analysis['top_ivs'][:10]):
        a, d, s = data['ivA'][iv], data['ivD'][iv], data['ivS'][iv]
        tier_idx = data['ivTiers'][iv]
        tier_name = data['tiers'][tier_idx]['name'] if tier_idx >= 0 else ''
        print(f"  {rank+1:4d}  {a:2d}/{d:2d}/{s:2d}  {data['ivAtk'][iv]:7.2f}  "
              f"{data['ivDef'][iv]:7.2f}  {data['ivHp'][iv]:3d}  "
              f"{analysis['scene_avgs'][iv]:7.1f}  {tier_name:>10s}")

    # Opponents that most differentiate the top cluster
    print(f"\n  Opponents that most distinguish top 50 (biggest score gap vs avg):")
    print(f"  {'Opponent':>25s}  {'Top50 avg':>9s}  {'All avg':>9s}  {'Gap':>6s}")
    print(f"  {'-'*55}")
    for oi, diff, top_avg, all_avg in analysis['opp_diffs'][:10]:
        print(f"  {opponents[oi]:>25s}  {top_avg:9.1f}  {all_avg:9.1f}  {diff:+6.1f}")
    print(f"\n  Opponents where top 50 is WORSE than average:")
    for oi, diff, top_avg, all_avg in analysis['opp_diffs'][-5:]:
        print(f"  {opponents[oi]:>25s}  {top_avg:9.1f}  {all_avg:9.1f}  {diff:+6.1f}")


def print_flip_table(flips, data, ref_iv_idx):
    """Print matchup flip table."""
    if not flips:
        print("  No matchup flips found.")
        return

    # Group by IV
    by_iv = defaultdict(list)
    for f in flips:
        by_iv[f['iv_idx']].append(f)

    ref_a = data['ivA'][ref_iv_idx]
    ref_d = data['ivD'][ref_iv_idx]
    ref_s = data['ivS'][ref_iv_idx]

    print(f"\n  Matchup flips vs reference IV ({ref_a}/{ref_d}/{ref_s}):")
    print(f"  (A matchup 'flips' when the outcome crosses the 500-point win/loss boundary)")

    for iv_idx in sorted(by_iv.keys()):
        iv_flips = by_iv[iv_idx]
        a, d, s = data['ivA'][iv_idx], data['ivD'][iv_idx], data['ivS'][iv_idx]
        tier_idx = data['ivTiers'][iv_idx]
        tier_name = data['tiers'][tier_idx]['name'] if tier_idx >= 0 else ''
        gains = [f for f in iv_flips if f['direction'] == 'gain']
        losses = [f for f in iv_flips if f['direction'] == 'lose']

        print(f"\n  {a:2d}/{d:2d}/{s:2d}  (Atk={data['ivAtk'][iv_idx]:.2f}  "
              f"Def={data['ivDef'][iv_idx]:.2f}  HP={data['ivHp'][iv_idx]})"
              f"{'  ' + tier_name if tier_name else ''}")
        print(f"  Gains {len(gains)} / Loses {len(losses)} matchups vs reference")

        if gains:
            print(f"    GAINS:")
            for f in sorted(gains, key=lambda x: x['iv_score'] - x['ref_score'], reverse=True):
                print(f"      {f['scenario']:>3s}  vs {f['opp_name']:<25s}  "
                      f"ref={f['ref_score']:3d} -> {f['iv_score']:3d}  (+{f['iv_score']-f['ref_score']})")
        if losses:
            print(f"    LOSES:")
            for f in sorted(losses, key=lambda x: x['ref_score'] - x['iv_score'], reverse=True):
                print(f"      {f['scenario']:>3s}  vs {f['opp_name']:<25s}  "
                      f"ref={f['ref_score']:3d} -> {f['iv_score']:3d}  ({f['iv_score']-f['ref_score']})")


def main():
    parser = argparse.ArgumentParser(description='Analyze deep dive HTML output')
    parser.add_argument('html', help='Path to interactive deep dive HTML file')
    parser.add_argument('--moveset', type=int, default=0,
                        help='Moveset index to analyze (default: 0 = top moveset)')
    parser.add_argument('--opp-iv', default='pvpoke', choices=['pvpoke', 'rank1'],
                        help='Opponent IV mode (default: pvpoke)')
    parser.add_argument('--top-n', type=int, default=50,
                        help='Number of top IVs for cluster analysis (default: 50)')
    parser.add_argument('--flip-ivs', default='thresholds,top10',
                        help='Which IVs to show flips for: "thresholds" (threshold tiers), '
                             '"top10" (top 10 by avg score), "all" (both), or '
                             'comma-separated IV specs like "0/14/9,2/13/13" (default: thresholds,top10)')
    args = parser.parse_args()

    print(f"Loading data from {args.html}...")
    data, scores = load_html_data(args.html)

    n_ivs = data['nIvs']
    n_scenarios = data['nScenarios']
    n_opponents = data['nOpponents']
    scenarios = [tuple(s) for s in data['scenarios']]
    opponents = data['opponents']
    movesets = data['movesets']

    score_key = f'{args.moveset}_{args.opp_iv}'
    if score_key not in scores:
        print(f"Available score keys: {list(scores.keys())}")
        sys.exit(f"Score key '{score_key}' not found")
    scores_flat = scores[score_key]

    print(f"  Species: {data['species']}")
    print(f"  League: {data['league']}")
    print(f"  Moveset: {movesets[args.moveset]['label']}")
    print(f"  Opponents: {n_opponents} ({data['opponentLabel']})")
    print(f"  Scenarios: {n_scenarios} ({', '.join(f'{s[0]}v{s[1]}' for s in scenarios)})")
    print(f"  IVs: {n_ivs}")

    # --- Overall average rankings ---
    avg_scores = compute_avg_scores(scores_flat, n_ivs, n_scenarios, n_opponents)
    ranked = sorted(range(n_ivs), key=lambda i: avg_scores[i], reverse=True)

    print(f"\n{'='*70}")
    print(f"  Overall Top 20 by Average Score (all {n_scenarios} scenarios)")
    print(f"{'='*70}")
    print(f"  {'Rank':>4s}  {'IVs':>8s}  {'Atk':>7s}  {'Def':>7s}  {'HP':>3s}  {'Avg':>7s}  {'Tier':>10s}")
    print(f"  {'-'*55}")
    for rank, iv in enumerate(ranked[:20]):
        a, d, s = data['ivA'][iv], data['ivD'][iv], data['ivS'][iv]
        tier_idx = data['ivTiers'][iv]
        tier_name = data['tiers'][tier_idx]['name'] if tier_idx >= 0 else ''
        print(f"  {rank+1:4d}  {a:2d}/{d:2d}/{s:2d}  {data['ivAtk'][iv]:7.2f}  "
              f"{data['ivDef'][iv]:7.2f}  {data['ivHp'][iv]:3d}  "
              f"{avg_scores[iv]:7.1f}  {tier_name:>10s}")

    # --- Per-scenario cluster analysis ---
    for si in range(n_scenarios):
        analysis = cluster_analysis(scores_flat, data, si, n_scenarios, n_opponents,
                                    n_ivs, top_n=args.top_n)
        print_cluster_analysis(analysis, data, scenarios, opponents)

    # --- Per-scenario rankings comparison ---
    print(f"\n{'='*70}")
    print(f"  Per-Scenario Top 5 Comparison")
    print(f"{'='*70}")
    header = f"  {'IVs':>8s}"
    for s0, s1 in scenarios:
        header += f"  {s0}v{s1:>3d}"
    header += "  Avg"
    print(header)
    print(f"  {'-'*(10 + 7*n_scenarios + 6)}")

    # Pre-compute per-scenario ranks for all IVs (avoids O(n^2) per IV)
    scene_ranks = []  # scene_ranks[si][iv] = rank in that scenario
    for si in range(n_scenarios):
        scene_scores = []
        for iv2 in range(n_ivs):
            base = iv2 * n_scenarios * n_opponents + si * n_opponents
            total = sum(scores_flat[base + oi] for oi in range(n_opponents))
            scene_scores.append(total)
        sorted_indices = sorted(range(n_ivs), key=lambda i: scene_scores[i], reverse=True)
        ranks = [0] * n_ivs
        for r, idx in enumerate(sorted_indices):
            ranks[idx] = r + 1
        scene_ranks.append(ranks)

    for iv in ranked[:15]:
        a, d, s = data['ivA'][iv], data['ivD'][iv], data['ivS'][iv]
        line = f"  {a:2d}/{d:2d}/{s:2d}"
        for si in range(n_scenarios):
            line += f"  {scene_ranks[si][iv]:5d}"
        avg_rank = next(r for r, idx in enumerate(ranked) if idx == iv) + 1
        line += f"  {avg_rank:4d}"
        print(line)

    # --- Matchup flip table ---
    print(f"\n{'='*70}")
    print(f"  Matchup Flip Table")
    print(f"{'='*70}")

    # Determine reference IV (PvPoke default)
    ref_iv_idx = data['pvpokeRefIvIdx']
    if ref_iv_idx < 0:
        ref_iv_idx = ranked[0]
        print(f"  No PvPoke default IV found; using top-ranked IV as reference")

    # Determine which IVs to show flips for
    flip_iv_indices = set()
    flip_specs = args.flip_ivs.split(',')

    for spec in flip_specs:
        spec = spec.strip()
        if spec == 'thresholds':
            for iv in range(n_ivs):
                if data['ivTiers'][iv] >= 0:
                    flip_iv_indices.add(iv)
        elif spec == 'top10':
            for iv in ranked[:10]:
                flip_iv_indices.add(iv)
        elif '/' in spec:
            parts = spec.split('/')
            if len(parts) == 3:
                ta, td, ts = int(parts[0]), int(parts[1]), int(parts[2])
                for iv in range(n_ivs):
                    if data['ivA'][iv] == ta and data['ivD'][iv] == td and data['ivS'][iv] == ts:
                        flip_iv_indices.add(iv)
                        break

    # Remove reference from flip set
    flip_iv_indices.discard(ref_iv_idx)

    flips = find_matchup_flips(scores_flat, n_ivs, n_scenarios, n_opponents,
                               ref_iv_idx, sorted(flip_iv_indices), scenarios, opponents)
    print_flip_table(flips, data, ref_iv_idx)

    # --- Summary: net flip counts ---
    print(f"\n{'='*70}")
    print(f"  Net Matchup Flip Summary vs Reference ({data['ivA'][ref_iv_idx]}/"
          f"{data['ivD'][ref_iv_idx]}/{data['ivS'][ref_iv_idx]})")
    print(f"{'='*70}")
    by_iv = defaultdict(lambda: {'gains': 0, 'losses': 0})
    for f in flips:
        if f['direction'] == 'gain':
            by_iv[f['iv_idx']]['gains'] += 1
        else:
            by_iv[f['iv_idx']]['losses'] += 1

    print(f"  {'IVs':>8s}  {'Atk':>7s}  {'Def':>7s}  {'HP':>3s}  {'Avg':>7s}  "
          f"{'Gains':>5s}  {'Loses':>5s}  {'Net':>4s}  {'Tier':>10s}")
    print(f"  {'-'*72}")
    for iv in sorted(by_iv.keys(), key=lambda i: by_iv[i]['gains'] - by_iv[i]['losses'],
                     reverse=True):
        a, d, s = data['ivA'][iv], data['ivD'][iv], data['ivS'][iv]
        tier_idx = data['ivTiers'][iv]
        tier_name = data['tiers'][tier_idx]['name'] if tier_idx >= 0 else ''
        g, l = by_iv[iv]['gains'], by_iv[iv]['losses']
        print(f"  {a:2d}/{d:2d}/{s:2d}  {data['ivAtk'][iv]:7.2f}  {data['ivDef'][iv]:7.2f}  "
              f"{data['ivHp'][iv]:3d}  {avg_scores[iv]:7.1f}  {g:5d}  {l:5d}  {g-l:+4d}  {tier_name:>10s}")


if __name__ == '__main__':
    main()
