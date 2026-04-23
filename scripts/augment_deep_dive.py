#!/usr/bin/env python
"""
Augment an interactive deep dive HTML with cluster analysis, matchup flip tables,
and methods documentation.

Reads the embedded DATA and SCORES from an existing deep dive HTML, runs automated
analysis, and injects new HTML sections. Saves to a new file.

Usage:
    python scripts/augment_deep_dive.py input.html -o output.html [--moveset 0] [--opp-iv pvpoke]
"""
import argparse
import json
import math
import re
import sys
from collections import defaultdict
from textwrap import dedent


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def load_html_data(html_path):
    """Extract DATA and SCORES JSON from the deep dive HTML."""
    with open(html_path, 'r') as f:
        text = f.read()
    m = re.search(r'var DATA = ({.*?});\nvar SCORES', text, re.DOTALL)
    if not m:
        sys.exit("Could not find DATA in HTML")
    data = json.loads(m.group(1))
    m2 = re.search(r'var SCORES = ({.*?});\n', text, re.DOTALL)
    if not m2:
        sys.exit("Could not find SCORES in HTML")
    scores = json.loads(m2.group(1))
    return data, scores, text


def get_score(scores_flat, iv, si, oi, nS, nO):
    return scores_flat[iv * nS * nO + si * nO + oi]


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def pearson_r(xs, ys):
    """Compute Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx)**2 for x in xs))
    dy = math.sqrt(sum((y - my)**2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def detect_banding(stat_values, scores, stat_name):
    """
    Detect banding structure: group IVs by discrete stat values and check
    if within-group score variance is much lower than between-group variance.

    Returns dict with banding analysis results.
    """
    # Group by discrete stat value
    groups = defaultdict(list)
    for i, (sv, sc) in enumerate(zip(stat_values, scores)):
        # Round to nearest integer for HP, to 2 decimal places for atk/def
        if stat_name == 'hp':
            key = int(sv)
        else:
            key = round(sv, 2)
        groups[key].append(sc)

    if len(groups) < 3:
        return None

    # Compute within-group and between-group variance
    grand_mean = sum(scores) / len(scores)
    n_total = len(scores)

    # Between-group: variance of group means
    group_means = {}
    for key, vals in groups.items():
        group_means[key] = sum(vals) / len(vals)

    ssb = sum(len(vals) * (group_means[key] - grand_mean)**2
              for key, vals in groups.items())
    ssw = sum(sum((v - group_means[key])**2 for v in vals)
              for key, vals in groups.items())

    # F-ratio: high means strong banding
    df_between = len(groups) - 1
    df_within = n_total - len(groups)
    if df_within == 0 or ssw == 0:
        f_ratio = float('inf')
    else:
        f_ratio = (ssb / df_between) / (ssw / df_within)

    # Variance explained (eta-squared)
    ss_total = ssb + ssw
    eta_sq = ssb / ss_total if ss_total > 0 else 0

    # Find the stat values that create the biggest score jumps
    sorted_keys = sorted(group_means.keys())
    jumps = []
    for i in range(len(sorted_keys) - 1):
        k1, k2 = sorted_keys[i], sorted_keys[i + 1]
        diff = group_means[k2] - group_means[k1]
        jumps.append((k1, k2, diff, len(groups[k1]), len(groups[k2])))
    jumps.sort(key=lambda x: abs(x[2]), reverse=True)

    return {
        'stat_name': stat_name,
        'n_groups': len(groups),
        'f_ratio': f_ratio,
        'eta_squared': eta_sq,
        'correlation': pearson_r(stat_values, scores),
        'top_jumps': jumps[:5],
        'group_means': group_means,
    }


def detect_clusters(scores, data, top_n=50):
    """
    Detect natural clusters in score space using gap analysis.

    Looks for gaps in the sorted score distribution that suggest distinct groups.
    Returns cluster boundaries and their characteristics.
    """
    sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    sorted_scores = [scores[i] for i in sorted_indices]

    # Find gaps: differences between consecutive sorted scores
    gaps = []
    for i in range(1, len(sorted_scores)):
        gap = sorted_scores[i - 1] - sorted_scores[i]
        gaps.append((i, gap, sorted_scores[i - 1], sorted_scores[i]))

    # Median gap for comparison
    gap_sizes = [g[1] for g in gaps]
    gap_sizes_sorted = sorted(gap_sizes)
    median_gap = gap_sizes_sorted[len(gap_sizes_sorted) // 2]

    # Significant gaps: > 3x median
    sig_gaps = [(i, gap, above, below) for i, gap, above, below in gaps
                if gap > 3 * median_gap and i <= len(scores) // 4]  # only in top quartile
    sig_gaps.sort(key=lambda x: x[1], reverse=True)

    # Build clusters from significant gaps
    clusters = []
    boundaries = [0] + [g[0] for g in sig_gaps[:5]] + [len(scores)]
    boundaries = sorted(set(boundaries))

    for j in range(len(boundaries) - 1):
        start, end = boundaries[j], boundaries[j + 1]
        cluster_indices = sorted_indices[start:end]
        cluster_scores = sorted_scores[start:end]

        if not cluster_scores:
            continue

        # Characterize the cluster
        atks = [data['ivAtk'][i] for i in cluster_indices]
        defs = [data['ivDef'][i] for i in cluster_indices]
        hps = [data['ivHp'][i] for i in cluster_indices]

        clusters.append({
            'rank_range': (start + 1, end),
            'size': end - start,
            'score_range': (min(cluster_scores), max(cluster_scores)),
            'atk': (min(atks), sum(atks)/len(atks), max(atks)),
            'def': (min(defs), sum(defs)/len(defs), max(defs)),
            'hp': (min(hps), sum(hps)/len(hps), max(hps)),
            'indices': cluster_indices,
        })

    return clusters, sig_gaps[:5]


def opponent_importance(scores_flat, nIvs, nS, nO, scenario_idx, top_set, opponents):
    """
    Rank opponents by how much they differentiate the top set from the population.
    """
    results = []
    for oi in range(nO):
        top_avg = sum(get_score(scores_flat, iv, scenario_idx, oi, nS, nO)
                      for iv in top_set) / len(top_set)
        all_avg = sum(get_score(scores_flat, iv, scenario_idx, oi, nS, nO)
                      for iv in range(nIvs)) / nIvs
        results.append({
            'opponent': opponents[oi],
            'top_avg': top_avg,
            'all_avg': all_avg,
            'gap': top_avg - all_avg,
        })
    results.sort(key=lambda x: abs(x['gap']), reverse=True)
    return results


def find_flips(scores_flat, nIvs, nS, nO, ref_iv, test_ivs, scenarios, opponents):
    """Find matchup flips for test IVs vs reference."""
    flips_by_iv = defaultdict(lambda: {'gains': [], 'losses': []})
    for iv in test_ivs:
        if iv == ref_iv:
            continue
        for si in range(nS):
            for oi in range(nO):
                rs = get_score(scores_flat, ref_iv, si, oi, nS, nO)
                ts = get_score(scores_flat, iv, si, oi, nS, nO)
                if (rs >= 500) != (ts >= 500):
                    entry = {
                        'scenario': f'{scenarios[si][0]}v{scenarios[si][1]}',
                        'opponent': opponents[oi],
                        'ref_score': rs,
                        'iv_score': ts,
                    }
                    if ts >= 500:
                        flips_by_iv[iv]['gains'].append(entry)
                    else:
                        flips_by_iv[iv]['losses'].append(entry)
    return flips_by_iv


def scenario_rank_volatility(scores_flat, data, nIvs, nS, nO):
    """
    Compute how much each IV's rank changes across scenarios.
    Returns per-IV rank vectors and volatility stats.
    """
    # Per-scenario scores and ranks
    scene_ranks = []
    for si in range(nS):
        scene_scores = []
        for iv in range(nIvs):
            base = iv * nS * nO + si * nO
            total = sum(scores_flat[base + oi] for oi in range(nO))
            scene_scores.append(total)
        sorted_idx = sorted(range(nIvs), key=lambda i: scene_scores[i], reverse=True)
        ranks = [0] * nIvs
        for r, idx in enumerate(sorted_idx):
            ranks[idx] = r + 1
        scene_ranks.append(ranks)

    # Overall average ranks
    avg_scores = []
    for iv in range(nIvs):
        total = sum(scores_flat[iv * nS * nO + si * nO + oi]
                    for si in range(nS) for oi in range(nO))
        avg_scores.append(total / (nS * nO))
    avg_sorted = sorted(range(nIvs), key=lambda i: avg_scores[i], reverse=True)
    avg_ranks = [0] * nIvs
    for r, idx in enumerate(avg_sorted):
        avg_ranks[idx] = r + 1

    # Volatility: std dev of ranks across scenarios
    volatilities = []
    for iv in range(nIvs):
        iv_ranks = [scene_ranks[si][iv] for si in range(nS)]
        mean_r = sum(iv_ranks) / nS
        var_r = sum((r - mean_r)**2 for r in iv_ranks) / nS
        volatilities.append({
            'iv': iv,
            'avg_rank': avg_ranks[iv],
            'ranks': iv_ranks,
            'mean_rank': mean_r,
            'std_rank': math.sqrt(var_r),
            'min_rank': min(iv_ranks),
            'max_rank': max(iv_ranks),
            'range': max(iv_ranks) - min(iv_ranks),
        })

    return volatilities, scene_ranks, avg_ranks


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def html_iv_label(data, iv):
    return f"{data['ivA'][iv]}/{data['ivD'][iv]}/{data['ivS'][iv]}"


def html_tier_badge(data, iv):
    ti = data['ivTiers'][iv]
    if ti < 0:
        return ''
    t = data['tiers'][ti]
    return f' <span class="dd-tier-badge" style="background:{t["color"]};color:#000">{t["name"]}</span>'


def generate_analysis_html(data, scores_flat, moveset_idx, opp_iv_mode, scenarios, opponents):
    """Generate the full analysis HTML sections."""
    nIvs = data['nIvs']
    nS = data['nScenarios']
    nO = data['nOpponents']
    moveset_label = data['movesets'][moveset_idx]['label']

    # Reference IV
    ref_iv = data['pvpokeRefIvIdx']
    if ref_iv < 0:
        ref_iv = 0  # fallback

    # Overall average scores
    avg_scores = []
    for iv in range(nIvs):
        total = sum(scores_flat[iv * nS * nO + si * nO + oi]
                    for si in range(nS) for oi in range(nO))
        avg_scores.append(total / (nS * nO))
    ranked = sorted(range(nIvs), key=lambda i: avg_scores[i], reverse=True)

    # ===== METHODS SECTION =====
    methods_html = f"""
<div class="dd-section" id="dd-methods">
<h2 class="dd-h2">Methods</h2>
<p>This analysis augments the interactive scatter plot above with automated statistical
analysis of the {nIvs} IV spreads simulated across {nS} shield scenarios against
{nO} opponents ({data['opponentLabel']}).</p>

<h3 class="dd-h3">Moveset analyzed</h3>
<p><code>{moveset_label}</code> - opponent IVs: {opp_iv_mode}</p>

<h3 class="dd-h3">Techniques used</h3>
<dl class="dd-methods-dl">
  <dt>Banding detection</dt>
  <dd>For each stat (attack, defense, HP) and each scenario, IVs are grouped by their
  discrete stat value. We compute the F-ratio (between-group variance / within-group
  variance) and &eta;&sup2; (variance explained). High F-ratio or &eta;&sup2; indicates that
  the stat creates visible horizontal or vertical bands in the scatter plot - meaning
  IVs with the same stat value cluster at the same score level. We also report the
  Pearson correlation between each stat and the battle score.</dd>

  <dt>Cluster detection (gap analysis)</dt>
  <dd>IVs are sorted by score for each scenario. We scan for gaps between consecutive
  scores that exceed 3&times; the median gap, indicating natural breakpoints where
  performance drops sharply. This identifies distinct performance tiers without
  assuming a fixed number of clusters.</dd>

  <dt>Opponent importance</dt>
  <dd>For each scenario, we compute the average score of the top 50 IVs against each
  opponent, minus the population average against that opponent. Large positive gaps
  indicate opponents where the top cluster gains its advantage; large negative gaps
  indicate opponents where the top cluster sacrifices performance.</dd>

  <dt>Rank volatility</dt>
  <dd>Each IV&rsquo;s rank is computed separately for each scenario. The standard
  deviation and range of ranks across scenarios measures how scenario-dependent
  an IV&rsquo;s performance is. High volatility means the IV is a specialist
  (great in some scenarios, poor in others); low volatility means it&rsquo;s
  a generalist.</dd>

  <dt>Matchup flip analysis</dt>
  <dd>For each IV spread, we count how many matchups cross the 500-point win/loss
  boundary compared to a reference IV (PvPoke default: {html_iv_label(data, ref_iv)}).
  A &ldquo;gain&rdquo; is a matchup the IV wins that the reference loses; a &ldquo;loss&rdquo;
  is the reverse. Net flips = gains &minus; losses. This bridges the gap between
  average-score optimization and threshold-based analysis.</dd>
</dl>
</div>
"""

    # ===== BANDING ANALYSIS =====
    banding_html = """
<div class="dd-section" id="dd-banding">
<h2 class="dd-h2">Banding &amp; Stat Correlations</h2>
<p>Which stats create visible structure (bands/gradients) in the scatter plot?
A high &eta;&sup2; means the stat explains a large fraction of score variance -
you can &ldquo;see&rdquo; it as horizontal or colored bands.</p>
"""

    # Run banding per scenario
    banding_html += '<table class="dd-table"><tr><th>Scenario</th>'
    banding_html += '<th>Atk r</th><th>Atk &eta;&sup2;</th>'
    banding_html += '<th>Def r</th><th>Def &eta;&sup2;</th>'
    banding_html += '<th>HP r</th><th>HP &eta;&sup2;</th>'
    banding_html += '<th>Dominant stat</th></tr>\n'

    for si in range(nS):
        s0, s1 = scenarios[si]
        scene_scores = []
        for iv in range(nIvs):
            base = iv * nS * nO + si * nO
            total = sum(scores_flat[base + oi] for oi in range(nO))
            scene_scores.append(total / nO)

        atk_band = detect_banding(data['ivAtk'], scene_scores, 'atk')
        def_band = detect_banding(data['ivDef'], scene_scores, 'def')
        hp_band = detect_banding([data['ivHp'][i] for i in range(nIvs)], scene_scores, 'hp')

        bands = [('Atk', atk_band), ('Def', def_band), ('HP', hp_band)]
        dominant = max(bands, key=lambda x: x[1]['eta_squared'] if x[1] else 0)

        banding_html += f'<tr><td>{s0}v{s1}</td>'
        for name, b in bands:
            if b:
                r_class = 'dd-strong' if abs(b['correlation']) > 0.3 else ''
                e_class = 'dd-strong' if b['eta_squared'] > 0.3 else ''
                banding_html += (f'<td class="{r_class}">{b["correlation"]:+.3f}</td>'
                                 f'<td class="{e_class}">{b["eta_squared"]:.3f}</td>')
            else:
                banding_html += '<td>-</td><td>-</td>'
        banding_html += f'<td><strong>{dominant[0]}</strong> (&eta;&sup2;={dominant[1]["eta_squared"]:.3f})</td>'
        banding_html += '</tr>\n'

    # Also for average
    avg_atk_band = detect_banding(data['ivAtk'], avg_scores, 'atk')
    avg_def_band = detect_banding(data['ivDef'], avg_scores, 'def')
    avg_hp_band = detect_banding([data['ivHp'][i] for i in range(nIvs)], avg_scores, 'hp')
    avg_bands = [('Atk', avg_atk_band), ('Def', avg_def_band), ('HP', avg_hp_band)]
    avg_dominant = max(avg_bands, key=lambda x: x[1]['eta_squared'] if x[1] else 0)

    banding_html += '<tr style="border-top:2px solid #e94560"><td><strong>Average</strong></td>'
    for name, b in avg_bands:
        if b:
            r_class = 'dd-strong' if abs(b['correlation']) > 0.3 else ''
            e_class = 'dd-strong' if b['eta_squared'] > 0.3 else ''
            banding_html += (f'<td class="{r_class}">{b["correlation"]:+.3f}</td>'
                             f'<td class="{e_class}">{b["eta_squared"]:.3f}</td>')
        else:
            banding_html += '<td>-</td><td>-</td>'
    banding_html += f'<td><strong>{avg_dominant[0]}</strong> (&eta;&sup2;={avg_dominant[1]["eta_squared"]:.3f})</td>'
    banding_html += '</tr></table>\n'

    # Interpretation
    banding_html += """
<div class="dd-callout">
<strong>Reading the table:</strong> <em>r</em> is Pearson correlation (positive = higher stat &rarr;
higher score). &eta;&sup2; is variance explained by discrete stat grouping (0-1 scale).
<span class="dd-strong">Bold values</span> are noteworthy (&gt; 0.3).
</div>

<h3 class="dd-h3">HP banding detail (average score)</h3>
<p>The most visible banding is by HP. Each HP value creates a horizontal stripe in the
scatter plot because many IV combinations share the same HP:</p>
"""
    if avg_hp_band and avg_hp_band['top_jumps']:
        banding_html += '<table class="dd-table dd-narrow"><tr><th>HP below</th><th>HP above</th><th>Score jump</th><th>N below</th><th>N above</th></tr>\n'
        for k1, k2, diff, n1, n2 in avg_hp_band['top_jumps']:
            cls = 'dd-gain' if diff > 0 else 'dd-loss'
            banding_html += f'<tr><td>{int(k1)}</td><td>{int(k2)}</td><td class="{cls}">{diff:+.1f}</td><td>{n1}</td><td>{n2}</td></tr>\n'
        banding_html += '</table>\n'

    banding_html += '</div>\n'

    # ===== CLUSTER ANALYSIS =====
    cluster_html = """
<div class="dd-section" id="dd-clusters">
<h2 class="dd-h2">Cluster Analysis (Per-Scenario)</h2>
<p>For each scenario, we detect natural score clusters by finding large gaps
in the sorted score distribution (&gt;3&times; median gap). This reveals distinct
performance tiers.</p>
"""

    for si in range(nS):
        s0, s1 = scenarios[si]
        scene_scores = []
        for iv in range(nIvs):
            base = iv * nS * nO + si * nO
            total = sum(scores_flat[base + oi] for oi in range(nO))
            scene_scores.append(total / nO)

        clusters, sig_gaps = detect_clusters(scene_scores, data)
        opp_imp = opponent_importance(scores_flat, nIvs, nS, nO, si,
                                      set(sorted(range(nIvs), key=lambda i: scene_scores[i],
                                                 reverse=True)[:50]),
                                      opponents)

        cluster_html += f'<h3 class="dd-h3">{s0}v{s1}'
        if s0 == s1:
            labels = {0: 'no shields', 1: 'even shields', 2: 'double shields'}
            cluster_html += f' ({labels.get(s0, "")})'
        elif s0 > s1:
            cluster_html += ' (shield advantage)'
        else:
            cluster_html += ' (shield disadvantage)'
        cluster_html += '</h3>\n'

        if sig_gaps:
            cluster_html += f'<p>{len(sig_gaps)} significant gap(s) detected. '
            cluster_html += f'Largest gap at rank {sig_gaps[0][0]}: '
            cluster_html += f'{sig_gaps[0][2]:.1f} &rarr; {sig_gaps[0][3]:.1f} '
            cluster_html += f'(gap = {sig_gaps[0][1]:.1f})</p>\n'
        else:
            cluster_html += '<p>No significant gaps detected - smooth score gradient.</p>\n'

        # Top 5 IVs for this scenario
        scene_ranked = sorted(range(nIvs), key=lambda i: scene_scores[i], reverse=True)
        cluster_html += '<table class="dd-table dd-narrow"><tr><th>#</th><th>IVs</th><th>Atk</th><th>Def</th><th>HP</th><th>Score</th><th>Tier</th></tr>\n'
        for rank in range(5):
            iv = scene_ranked[rank]
            cluster_html += (f'<tr><td>{rank+1}</td><td>{html_iv_label(data, iv)}</td>'
                             f'<td>{data["ivAtk"][iv]:.2f}</td><td>{data["ivDef"][iv]:.2f}</td>'
                             f'<td>{data["ivHp"][iv]}</td><td>{scene_scores[iv]:.1f}</td>'
                             f'<td>{html_tier_badge(data, iv)}</td></tr>\n')
        cluster_html += '</table>\n'

        # Top 3 opponent differentiators
        cluster_html += '<p class="dd-small"><strong>Top differentiators:</strong> '
        parts = []
        for od in opp_imp[:3]:
            parts.append(f'{od["opponent"]} ({od["gap"]:+.0f})')
        cluster_html += ', '.join(parts)
        cluster_html += '. <strong>Top sacrifice:</strong> '
        worst = [od for od in opp_imp if od['gap'] < 0]
        if worst:
            parts = []
            for od in worst[:2]:
                parts.append(f'{od["opponent"]} ({od["gap"]:+.0f})')
            cluster_html += ', '.join(parts)
        else:
            cluster_html += 'none'
        cluster_html += '</p>\n'

    cluster_html += '</div>\n'

    # ===== RANK VOLATILITY =====
    print("  Computing rank volatility...")
    volatilities, scene_ranks, avg_ranks_list = scenario_rank_volatility(
        scores_flat, data, nIvs, nS, nO)

    vol_html = """
<div class="dd-section" id="dd-volatility">
<h2 class="dd-h2">Rank Volatility</h2>
<p>How much does each IV&rsquo;s rank change across scenarios? High range = specialist;
low range = generalist. The &ldquo;best&rdquo; IVs are those that rank well on average
<em>and</em> have low volatility.</p>
"""

    # Show top 15 by avg rank with their per-scenario ranks
    vol_html += '<table class="dd-table"><tr><th>IVs</th>'
    for s0, s1 in scenarios:
        vol_html += f'<th>{s0}v{s1}</th>'
    vol_html += '<th>Avg</th><th>Range</th><th>Tier</th></tr>\n'

    top_by_avg = sorted(volatilities, key=lambda v: v['avg_rank'])[:15]
    for v in top_by_avg:
        iv = v['iv']
        vol_html += f'<tr><td>{html_iv_label(data, iv)}</td>'
        for si in range(nS):
            r = v['ranks'][si]
            cls = ''
            if r <= 10:
                cls = ' class="dd-rank-good"'
            elif r > 1000:
                cls = ' class="dd-rank-bad"'
            vol_html += f'<td{cls}>{r}</td>'
        vol_html += f'<td><strong>{v["avg_rank"]}</strong></td>'
        vol_html += f'<td>{v["range"]}</td>'
        vol_html += f'<td>{html_tier_badge(data, iv)}</td></tr>\n'
    vol_html += '</table>\n'

    # Find the most stable top IVs (low range in top 50)
    stable_top = [v for v in volatilities if v['avg_rank'] <= 50]
    stable_top.sort(key=lambda v: v['range'])
    vol_html += '<h3 class="dd-h3">Most stable top-50 IVs (lowest rank range)</h3>\n'
    vol_html += '<table class="dd-table dd-narrow"><tr><th>IVs</th><th>Avg Rank</th><th>Best</th><th>Worst</th><th>Range</th><th>Tier</th></tr>\n'
    for v in stable_top[:10]:
        iv = v['iv']
        vol_html += (f'<tr><td>{html_iv_label(data, iv)}</td><td>{v["avg_rank"]}</td>'
                     f'<td class="dd-rank-good">{v["min_rank"]}</td>'
                     f'<td>{v["max_rank"]}</td><td>{v["range"]}</td>'
                     f'<td>{html_tier_badge(data, iv)}</td></tr>\n')
    vol_html += '</table></div>\n'

    # ===== MATCHUP FLIP TABLE =====
    print("  Computing matchup flips...")
    # Test IVs: top 10 by avg + all threshold IVs + reference's picks
    test_set = set(ranked[:10])
    for iv in range(nIvs):
        if data['ivTiers'][iv] >= 0:
            test_set.add(iv)
    test_set.discard(ref_iv)

    flips = find_flips(scores_flat, nIvs, nS, nO, ref_iv, sorted(test_set),
                       scenarios, opponents)

    flip_html = f"""
<div class="dd-section" id="dd-flips">
<h2 class="dd-h2">Matchup Flip Table</h2>
<p>Matchups that cross the 500-point win/loss boundary vs reference IV
({html_iv_label(data, ref_iv)}, PvPoke default).</p>

<h3 class="dd-h3">Net flip summary</h3>
"""

    # Summary table sorted by net flips
    flip_summary = []
    for iv, fdata in flips.items():
        g, l = len(fdata['gains']), len(fdata['losses'])
        flip_summary.append((iv, g, l, g - l))
    flip_summary.sort(key=lambda x: (-x[3], -x[1]))

    flip_html += '<table class="dd-table"><tr><th>IVs</th><th>Atk</th><th>Def</th><th>HP</th><th>Avg Score</th><th>Gains</th><th>Loses</th><th>Net</th><th>Tier</th></tr>\n'
    for iv, g, l, net in flip_summary[:25]:
        net_cls = 'dd-gain' if net > 0 else ('dd-loss' if net < 0 else '')
        flip_html += (f'<tr><td>{html_iv_label(data, iv)}</td>'
                      f'<td>{data["ivAtk"][iv]:.2f}</td><td>{data["ivDef"][iv]:.2f}</td>'
                      f'<td>{data["ivHp"][iv]}</td><td>{avg_scores[iv]:.1f}</td>'
                      f'<td class="dd-gain">{g}</td><td class="dd-loss">{l}</td>'
                      f'<td class="{net_cls}"><strong>{net:+d}</strong></td>'
                      f'<td>{html_tier_badge(data, iv)}</td></tr>\n')
    flip_html += '</table>\n'

    # Detailed flips for notable IVs
    notable = [(iv, g, l, net) for iv, g, l, net in flip_summary if abs(net) >= 3 or iv in set(ranked[:5])]
    for iv, g, l, net in notable[:8]:
        fdata = flips[iv]
        flip_html += f'<details class="dd-flip-detail"><summary>{html_iv_label(data, iv)}'
        flip_html += f' - <span class="dd-gain">+{g}</span>/<span class="dd-loss">-{l}</span>'
        flip_html += f' (net {net:+d}){html_tier_badge(data, iv)}</summary>\n'

        if fdata['gains']:
            flip_html += '<table class="dd-table dd-narrow"><tr><th>Scen.</th><th>Opponent</th><th>Ref</th><th>This IV</th><th>&Delta;</th></tr>\n'
            for e in sorted(fdata['gains'], key=lambda x: x['iv_score'] - x['ref_score'], reverse=True):
                flip_html += (f'<tr><td>{e["scenario"]}</td><td>{e["opponent"]}</td>'
                              f'<td>{e["ref_score"]}</td><td class="dd-gain">{e["iv_score"]}</td>'
                              f'<td class="dd-gain">+{e["iv_score"]-e["ref_score"]}</td></tr>\n')
            flip_html += '</table>\n'
        if fdata['losses']:
            flip_html += '<table class="dd-table dd-narrow"><tr><th>Scen.</th><th>Opponent</th><th>Ref</th><th>This IV</th><th>&Delta;</th></tr>\n'
            for e in sorted(fdata['losses'], key=lambda x: x['ref_score'] - x['iv_score'], reverse=True):
                flip_html += (f'<tr><td>{e["scenario"]}</td><td>{e["opponent"]}</td>'
                              f'<td>{e["ref_score"]}</td><td class="dd-loss">{e["iv_score"]}</td>'
                              f'<td class="dd-loss">{e["iv_score"]-e["ref_score"]}</td></tr>\n')
            flip_html += '</table>\n'
        flip_html += '</details>\n'

    flip_html += '</div>\n'

    # ===== RECOMMENDATIONS =====
    # Find the best IV by combined avg rank + net flips
    rec_html = """
<div class="dd-section" id="dd-recommendations">
<h2 class="dd-h2">Recommendations</h2>
<p>Combining average score ranking, matchup flip analysis, and rank stability:</p>
"""

    # Top 3 recommendations with reasoning
    rec_candidates = []
    for iv, g, l, net in flip_summary:
        avg_rank = next(r + 1 for r, idx in enumerate(ranked) if idx == iv)
        if avg_rank <= 20 or net >= 3:
            vol = next(v for v in volatilities if v['iv'] == iv)
            rec_candidates.append({
                'iv': iv,
                'avg_rank': avg_rank,
                'avg_score': avg_scores[iv],
                'net_flips': net,
                'gains': g,
                'losses': l,
                'rank_range': vol['range'],
            })

    # Score: weighted combination
    for rc in rec_candidates:
        # Lower avg_rank is better, higher net_flips is better, lower range is better
        rc['composite'] = -rc['avg_rank'] + rc['net_flips'] * 3 - rc['rank_range'] * 0.001

    rec_candidates.sort(key=lambda x: x['composite'], reverse=True)

    rec_html += '<div class="dd-rec-grid">\n'
    labels = ['Best Overall', 'Runner-up', 'Honorable Mention']
    for i, rc in enumerate(rec_candidates[:3]):
        iv = rc['iv']
        rec_html += f'<div class="dd-rec-card">\n'
        rec_html += f'<h4>{labels[i]}: {html_iv_label(data, iv)}{html_tier_badge(data, iv)}</h4>\n'
        rec_html += f'<p>Atk={data["ivAtk"][iv]:.2f}, Def={data["ivDef"][iv]:.2f}, HP={data["ivHp"][iv]}, SP Rank #{data["spRanks"][iv]}</p>\n'
        rec_html += f'<p>Avg score: <strong>#{rc["avg_rank"]}</strong> ({rc["avg_score"]:.1f})</p>\n'
        net_cls = 'dd-gain' if rc['net_flips'] > 0 else 'dd-loss'
        rec_html += f'<p>Flips: <span class="dd-gain">+{rc["gains"]}</span> / <span class="dd-loss">-{rc["losses"]}</span> = <span class="{net_cls}"><strong>{rc["net_flips"]:+d}</strong></span></p>\n'
        rec_html += f'<p>Rank range: {rc["rank_range"]} across scenarios</p>\n'
        rec_html += '</div>\n'
    rec_html += '</div></div>\n'

    return methods_html + banding_html + cluster_html + vol_html + flip_html + rec_html


# ---------------------------------------------------------------------------
# CSS for analysis sections
# ---------------------------------------------------------------------------

ANALYSIS_CSS = """
/* Deep dive analysis sections */
.dd-section { background: #16213e; padding: 16px 20px; border-radius: 8px; margin: 20px 0; }
.dd-h2 { color: #e94560; font-size: 1.3rem; margin: 0 0 12px 0; border-bottom: 1px solid #0f3460; padding-bottom: 6px; }
.dd-h3 { color: #58a6ff; font-size: 1rem; margin: 14px 0 8px 0; }
.dd-table { border-collapse: collapse; margin: 8px 0 12px; font-size: 0.82rem; width: 100%; }
.dd-table.dd-narrow { width: auto; }
.dd-table th, .dd-table td { padding: 4px 8px; border: 1px solid #0f3460; text-align: left; }
.dd-table th { background: #0f3460; color: #58a6ff; font-weight: 600; }
.dd-table td { background: #1a1a2e; }
.dd-table tr:hover td { background: #16213e; }
.dd-gain { color: #3fb950; }
.dd-loss { color: #f85149; }
.dd-strong { font-weight: 700; color: #FFD700; }
.dd-rank-good { color: #3fb950; font-weight: 600; }
.dd-rank-bad { color: #f85149; }
.dd-small { font-size: 0.82rem; color: #8b949e; margin: 4px 0; }
.dd-callout { background: #0f3460; border-left: 3px solid #58a6ff; padding: 8px 12px; margin: 10px 0; border-radius: 0 4px 4px 0; font-size: 0.85rem; }
.dd-tier-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.75rem; font-weight: 600; }
.dd-methods-dl { margin: 8px 0; }
.dd-methods-dl dt { color: #58a6ff; font-weight: 600; margin-top: 8px; }
.dd-methods-dl dd { margin-left: 16px; font-size: 0.88rem; color: #aaa; }
.dd-flip-detail { margin: 6px 0; }
.dd-flip-detail summary { cursor: pointer; padding: 4px 0; font-size: 0.9rem; }
.dd-flip-detail summary:hover { color: #58a6ff; }
.dd-rec-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; margin: 12px 0; }
.dd-rec-card { background: #0f3460; border: 1px solid #1a3a6e; border-radius: 6px; padding: 12px; }
.dd-rec-card h4 { color: #e94560; margin: 0 0 6px; font-size: 1rem; }
.dd-rec-card p { margin: 3px 0; font-size: 0.88rem; }
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Augment deep dive HTML with analysis')
    parser.add_argument('html', help='Input interactive deep dive HTML')
    parser.add_argument('-o', '--output', required=True, help='Output HTML file')
    parser.add_argument('--moveset', type=int, default=0, help='Moveset index (default: 0)')
    parser.add_argument('--opp-iv', default='pvpoke', choices=['pvpoke', 'rank1'])
    args = parser.parse_args()

    print(f"Loading {args.html}...")
    data, scores, html_text = load_html_data(args.html)

    nIvs = data['nIvs']
    nS = data['nScenarios']
    nO = data['nOpponents']
    scenarios = [tuple(s) for s in data['scenarios']]
    opponents = data['opponents']

    score_key = f'{args.moveset}_{args.opp_iv}'
    if score_key not in scores:
        sys.exit(f"Score key '{score_key}' not found. Available: {list(scores.keys())}")
    scores_flat = scores[score_key]

    print(f"  {nIvs} IVs, {nS} scenarios, {nO} opponents")
    print(f"  Moveset: {data['movesets'][args.moveset]['label']}")

    print("  Running analysis...")
    analysis_html = generate_analysis_html(data, scores_flat, args.moveset,
                                           args.opp_iv, scenarios, opponents)

    # Inject CSS into <style> block
    css_inject = ANALYSIS_CSS
    html_out = html_text.replace('</style>', css_inject + '\n</style>', 1)

    # Inject analysis sections before the plot div
    # Find the plot container div
    plot_marker = '<div id="plot"'
    if plot_marker not in html_out:
        # Try alternate markers
        plot_marker = '<div class="plot-container"'
    if plot_marker not in html_out:
        # Insert before the main <script> that has DATA
        plot_marker = '<script>var DATA'

    if plot_marker in html_out:
        # Add a toggle button + the analysis sections
        toggle_html = """
<details class="dd-collapsible" id="dd-analysis">
<summary class="dd-h3" style="cursor:pointer">Deep Dive Analysis</summary>
"""
        analysis_block = toggle_html + analysis_html + '</details>\n'
        html_out = html_out.replace(plot_marker, analysis_block + plot_marker, 1)
    else:
        print("  Warning: could not find injection point, appending before </body>")
        html_out = html_out.replace('</body>', analysis_html + '\n</body>', 1)

    with open(args.output, 'w') as f:
        f.write(html_out)

    print(f"  Written to {args.output}")
    print("Done.")


if __name__ == '__main__':
    main()
