#!/usr/bin/env python
"""
IV deep dive: sim all 4096 IV spreads of a focal species against meta opponents.

The user can specify as much or as little of the focal mon's moveset as they want:
  - Full moveset (fast + 2 charged): use exactly that.
  - Fast move only: try all legal charged move pairs.
  - One charged move: try all legal fast moves × all partners for the other slot.
  - Nothing: try all legal moveset combinations.

Opponents can come from:
  - Top N of PvPoke rankings (default)
  - A PvPoke custom group (--group championshipseries)

Two-phase approach:
  Phase 1: Quick screen — sim rank-1 IVs in 1v1 shields against a few opponents
           to prune hopeless movesets down to the top N.
  Phase 2: Full 4096-IV sweep for surviving movesets across all opponents.

Usage:
    python scripts/deep_dive.py <species> [--fast FAST] [--charged MOVE1[,MOVE2]]
                                [--league great|ultra|master]
                                [--opponents N] [--top-movesets N]
                                [--shield-scenario S1,S2]
                                [--shadow]
                                [--group NAME]
                                [--thresholds FILE.json]
                                [--html output.html]

Examples:
    # Full auto: try all movesets, top 20 opponents
    python scripts/deep_dive.py Medicham

    # Tinkaton with upcoming Gigaton Hammer vs Championship Series meta
    python scripts/deep_dive.py Tinkaton --fast FAIRY_WIND \\
        --charged GIGATON_HAMMER,PLAY_ROUGH \\
        --group championshipseries --thresholds thresholds/tinkaton.json \\
        --html tinkaton_gh.html

    # Interactive HTML output
    python scripts/deep_dive.py Medicham --fast COUNTER --charged DYNAMIC_PUNCH,ICE_PUNCH \\
        --html med.html
"""
import argparse
import itertools
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.pokemon import (
    Pokemon, get_pokemon_entry, get_species, iv_rank, CPM, best_level,
    LEAGUE_CAPS, cp as calc_cp, pvpoke_default_ivs,
)
from gopvpsim.moves import get_moves
from gopvpsim.data import (
    load_gamemaster, load_rankings, get_default_moveset, parse_types,
    load_group as fetch_group,
)
from gopvpsim.battle import (
    BattlePokemon, simulate,
    pvpoke_dp, pvpoke_simulate_shield,
)

# ---------------------------------------------------------------------------
# PvPoke custom group loading (via cached fetch from GitHub)
# ---------------------------------------------------------------------------

# Known PvPoke custom groups (from pvpoke/src/data/groups/).
# This list is for --help display; any name can be tried at runtime.
KNOWN_GROUPS = [
    'battlefrontiermaster', 'bayou', 'bfretro', 'catch', 'championshipseries',
    'chrono', 'electric', 'equinox', 'fantasy', 'great', 'jungle',
    'laic2025remix', 'little', 'littlegeneral', 'maelstrom', 'master', 'mega',
    'premiermaster', 'premierultra', 'remix', 'retro', 'spellcraft', 'spring',
    'ultra',
]


def _build_species_id_to_name():
    """Build a mapping from PvPoke speciesId -> speciesName."""
    gm = load_gamemaster()
    return {m['speciesId']: m['speciesName'] for m in gm['pokemon']}


def load_group(group_name):
    """
    Load a PvPoke custom group (fetched from GitHub, cached locally) and
    return list of (speciesName, fast_move_id, [charged_move_ids], is_shadow).
    """
    entries = fetch_group(group_name)

    id_to_name = _build_species_id_to_name()
    result = []
    skipped = []
    for entry in entries:
        sid = entry['speciesId']
        is_shadow = entry.get('shadowType') == 'shadow'
        if sid not in id_to_name:
            base_sid = sid.replace('_shadow', '')
            if base_sid + '_shadow' in id_to_name:
                sid = base_sid + '_shadow'
            elif base_sid in id_to_name and is_shadow:
                sid = base_sid
            else:
                skipped.append(entry['speciesId'])
                continue

        species_name = id_to_name[sid]
        fast_move = entry['fastMove']
        charged_moves = entry['chargedMoves']
        result.append((species_name, fast_move, charged_moves, is_shadow))

    if skipped:
        print(f"  Warning: skipped {len(skipped)} group entries not in gamemaster: "
              f"{', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''}")

    return result


# ---------------------------------------------------------------------------
# Threshold loading and classification
# ---------------------------------------------------------------------------

def load_thresholds(path):
    """
    Load thresholds from a JSON file.

    Format:
        {
            "GH Great": {"attack": 0, "defense": 143.03, "stamina": 138},
            "GH Good":  {"attack": 0, "defense": 141.66, "stamina": 138}
        }

    Thresholds should be ordered from most restrictive to least restrictive.
    A value of 0 means "don't care" for that stat.
    """
    with open(path) as f:
        data = json.load(f)
    # Validate structure
    for name, thresh in data.items():
        for key in ('attack', 'defense', 'stamina'):
            if key not in thresh:
                sys.exit(f"Threshold {name!r} missing required key {key!r}")
    return data


def classify_iv(result, thresholds):
    """
    Return the name of the most restrictive threshold this IV spread meets,
    or None if it doesn't meet any.

    Thresholds are checked in order (most restrictive first).
    A threshold is met if all non-zero stat requirements are satisfied:
      - attack >= threshold attack (if > 0)
      - defense >= threshold defense (if > 0)
      - stamina >= threshold stamina (if > 0)
    """
    for name, thresh in thresholds.items():
        meets = True
        if thresh['attack'] > 0 and result['atk'] < thresh['attack']:
            meets = False
        if thresh['defense'] > 0 and result['def_'] < thresh['defense']:
            meets = False
        if thresh['stamina'] > 0 and result['hp'] < thresh['stamina']:
            meets = False
        if meets:
            return name
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_legal_moves(species_name):
    """Return (fast_move_ids, charged_move_ids) that a species can learn."""
    entry = get_pokemon_entry(species_name)
    return entry['fastMoves'], entry['chargedMoves']


def enumerate_movesets(species_name, user_fast=None, user_charged=None):
    """
    Enumerate moveset combinations based on what the user specified.

    user_fast:    a single fast move ID, or None
    user_charged: list of 1 or 2 charged move IDs, or None

    Returns list of (fast_id, [charged_id1, charged_id2]) tuples.
    Single charged move movesets are included too (some mons only need one).

    User-specified moves are validated against the gamemaster move database
    (not the species' legal list), allowing unreleased CD moves etc.
    """
    legal_fast, legal_charged = get_legal_moves(species_name)
    fast_moves_db, charged_moves_db = get_moves()

    # Determine fast move candidates
    if user_fast:
        if user_fast not in fast_moves_db:
            sys.exit(f"Unknown fast move {user_fast!r} (not in gamemaster)")
        if user_fast not in legal_fast:
            print(f"  Note: {user_fast} is not in {species_name}'s current move pool "
                  f"(CD/legacy move?)")
        fast_candidates = [user_fast]
    else:
        fast_candidates = list(legal_fast)

    # Determine charged move candidates
    if user_charged and len(user_charged) == 2:
        # Full charged moveset specified — validate against gamemaster, not species
        for cm in user_charged:
            if cm not in charged_moves_db:
                sys.exit(f"Unknown charged move {cm!r} (not in gamemaster)")
            if cm not in legal_charged:
                print(f"  Note: {cm} is not in {species_name}'s current move pool "
                      f"(CD/legacy move?)")
        charged_pairs = [tuple(sorted(user_charged))]
    elif user_charged and len(user_charged) == 1:
        # One charged move specified — pair it with all legal partners
        fixed = user_charged[0]
        if fixed not in charged_moves_db:
            sys.exit(f"Unknown charged move {fixed!r} (not in gamemaster)")
        if fixed not in legal_charged:
            print(f"  Note: {fixed} is not in {species_name}'s current move pool "
                  f"(CD/legacy move?)")
        # Include the fixed move in the partner pool
        all_charged = list(set(legal_charged) | {fixed})
        charged_pairs = []
        for other in sorted(all_charged):
            pair = tuple(sorted([fixed, other]))
            if pair not in charged_pairs:
                charged_pairs.append(pair)
    else:
        # No charged moves specified — all pairs from legal list
        charged_pairs = list(itertools.combinations(sorted(legal_charged), 2))
        for cm in sorted(legal_charged):
            charged_pairs.append((cm,))

    movesets = []
    seen = set()
    for fast in fast_candidates:
        for pair in charged_pairs:
            key = (fast, pair)
            if key not in seen:
                seen.add(key)
                movesets.append((fast, list(pair)))
    return movesets


def make_battle_pokemon(species, fast_id, charged_ids, league, shields,
                        atk_iv, def_iv, sta_iv, shadow=False):
    """Build a BattlePokemon from species + IVs + move IDs."""
    pokemon = Pokemon.at_best_level(species, atk_iv, def_iv, sta_iv,
                                    league=league, shadow=shadow)
    fast_moves, charged_moves = get_moves()
    fm = dict(fast_moves[fast_id])
    cms = [dict(charged_moves[cid]) for cid in charged_ids]
    gm = load_gamemaster()
    mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
    types = parse_types(mon)
    return BattlePokemon(
        species=species, types=types,
        atk=pokemon.atk, def_=pokemon.def_, max_hp=pokemon.hp,
        fast_move=fm, charged_moves=cms, shields=shields,
    )


def get_top_opponents(league, n, exclude_species=None):
    """Return top N species from PvPoke rankings for the league."""
    rankings = load_rankings(league)
    opponents = []
    for r in rankings:
        name = r['speciesName']
        if exclude_species and name == exclude_species:
            continue
        opponents.append(name)
        if len(opponents) >= n:
            break
    return opponents


def resolve_opp_ivs(species_name, league, shadow, opp_iv_mode):
    """Return (atk_iv, def_iv, sta_iv) for an opponent based on the IV mode.

    opp_iv_mode:
      'pvpoke'  — PvPoke's default IVs from the gamemaster (what pvpoke.com uses)
      'rank1'   — stat-product rank 1 IVs
    """
    if opp_iv_mode == 'rank1':
        ranked = iv_rank(species_name, league=league, shadow=shadow)
        r1 = ranked[0]
        return r1['atk_iv'], r1['def_iv'], r1['sta_iv']
    else:
        # pvpoke default
        _lv, a, d, s = pvpoke_default_ivs(species_name, league=league)
        return a, d, s


def sim_score(focal_species, fast_id, charged_ids, league, shields_focal,
              shields_opp, atk_iv, def_iv, sta_iv, shadow,
              opp_species, opp_fast, opp_charged, opp_shadow=False,
              opp_iv_mode='pvpoke'):
    """Run one sim and return the focal mon's PvPoke score (0-1000)."""
    bp0 = make_battle_pokemon(focal_species, fast_id, charged_ids, league,
                              shields_focal, atk_iv, def_iv, sta_iv, shadow)

    opp_is_shadow = opp_shadow or opp_species.endswith(' (Shadow)')
    opp_name = opp_species.replace(' (Shadow)', '') if opp_is_shadow else opp_species
    oa, od, os_ = resolve_opp_ivs(opp_name, league, opp_is_shadow, opp_iv_mode)
    bp1 = make_battle_pokemon(opp_name, opp_fast, opp_charged, league,
                              shields_opp, oa, od, os_, shadow=opp_is_shadow)

    result = simulate(bp0, bp1,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp)
    return result.pvpoke_score(0)


def moveset_label(fast_id, charged_ids):
    """Short human-readable moveset label."""
    return f"{fast_id} / {', '.join(charged_ids)}"


# ---------------------------------------------------------------------------
# Phase 1: Quick screen
# ---------------------------------------------------------------------------

def screen_movesets(species, movesets, league, shadow, opponents, opp_movesets,
                    shield_scenarios, top_n, opp_iv_mode='pvpoke'):
    """
    Quick screen: sim rank-1 IVs for each moveset against opponents.
    Return the top N movesets by average score.
    """
    if len(movesets) <= top_n:
        print(f"  Only {len(movesets)} moveset(s) — skipping screen phase.\n")
        return movesets

    print(f"  Phase 1: Screening {len(movesets)} movesets (rank-1 IVs, "
          f"{len(opponents)} opponents, {len(shield_scenarios)} scenario(s))...")
    t0 = time.time()

    # Use rank-1 IVs for screening
    ranked = iv_rank(species, league=league, shadow=shadow)
    r1 = ranked[0]
    a_iv, d_iv, s_iv = r1['atk_iv'], r1['def_iv'], r1['sta_iv']

    scored = []
    for fast_id, charged_ids in movesets:
        total = 0.0
        count = 0
        for opp_name, (opp_fast, opp_charged) in zip(opponents, opp_movesets):
            for s_focal, s_opp in shield_scenarios:
                score = sim_score(species, fast_id, charged_ids, league,
                                  s_focal, s_opp, a_iv, d_iv, s_iv, shadow,
                                  opp_name, opp_fast, opp_charged,
                                  opp_iv_mode=opp_iv_mode)
                total += score
                count += 1
        avg = total / count if count else 0
        scored.append((avg, fast_id, charged_ids))

    scored.sort(reverse=True)
    elapsed = time.time() - t0
    print(f"  Screened in {elapsed:.1f}s. Top movesets:")
    for i, (avg, fast_id, charged_ids) in enumerate(scored[:top_n]):
        print(f"    {i+1:3d}. {moveset_label(fast_id, charged_ids):<45s} avg={avg:.0f}")
    if len(scored) > top_n:
        print(f"    ... ({len(scored) - top_n} more pruned)")
    print()

    return [(fast_id, charged_ids) for _, fast_id, charged_ids in scored[:top_n]]


# ---------------------------------------------------------------------------
# Phase 2: Full IV sweep
# ---------------------------------------------------------------------------

def iv_sweep(species, fast_id, charged_ids, league, shadow,
             opponents, opp_movesets, shield_scenarios, opp_iv_mode='pvpoke'):
    """
    Sim all 4096 IV spreads for one moveset against all opponents.
    Returns list of dicts with IV info + composite score, sorted by score desc.
    """
    base = get_species(species)
    base_atk, base_def, base_sta = base['atk'], base['def'], base['hp']
    max_cp = LEAGUE_CAPS[league]
    fast_moves_db, charged_moves_db = get_moves()

    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
    focal_types = parse_types(focal_mon)
    fm_template = dict(fast_moves_db[fast_id])
    cms_template = [dict(charged_moves_db[cid]) for cid in charged_ids]

    # Cache opponent stats (BattlePokemon is mutated by simulate, but stats are fixed)
    opp_cache = []
    for opp_name, (opp_fast, opp_charged) in zip(opponents, opp_movesets):
        opp_is_shadow = '_shadow' in opp_name.lower().replace(' ', '_')
        opp_clean = opp_name
        oa, od, os_ = resolve_opp_ivs(opp_clean, league, opp_is_shadow, opp_iv_mode)
        opp_pokemon = Pokemon.at_best_level(opp_clean, oa, od, os_,
                                            league=league, shadow=opp_is_shadow)
        opp_mon = next(m for m in gm['pokemon'] if m['speciesName'] == opp_clean)
        opp_types = parse_types(opp_mon)
        opp_fm = dict(fast_moves_db[opp_fast])
        opp_cms = [dict(charged_moves_db[cid]) for cid in opp_charged]
        opp_cache.append({
            'species': opp_clean, 'types': opp_types,
            'atk': opp_pokemon.atk, 'def_': opp_pokemon.def_,
            'hp': opp_pokemon.hp, 'fm': opp_fm, 'cms': opp_cms,
            'shadow': opp_is_shadow,
        })

    from gopvpsim.pokemon import SHADOW_ATK_BONUS, SHADOW_DEF_MULT

    results = []
    n_sims = 0
    for a in range(16):
        for d in range(16):
            for s in range(16):
                lv = best_level(base_atk, base_def, base_sta, a, d, s,
                                max_cp=max_cp, max_level=51.0)
                if lv is None:
                    continue
                cpm = CPM[lv]
                atk_stat = (base_atk + a) * cpm
                def_stat = (base_def + d) * cpm
                if shadow:
                    atk_stat *= SHADOW_ATK_BONUS
                    def_stat *= SHADOW_DEF_MULT
                hp_stat = math.floor((base_sta + s) * cpm)
                mon_cp = calc_cp(base_atk, base_def, base_sta, a, d, s, lv)

                total_score = 0.0
                count = 0
                # Per-opponent scores keyed by (scenario_idx, opp_idx)
                per_opp = {}
                for oi, opp in enumerate(opp_cache):
                    for si, (s_focal, s_opp) in enumerate(shield_scenarios):
                        bp0 = BattlePokemon(
                            species=species, types=focal_types,
                            atk=atk_stat, def_=def_stat, max_hp=hp_stat,
                            fast_move=dict(fm_template),
                            charged_moves=[dict(cm) for cm in cms_template],
                            shields=s_focal,
                        )
                        bp1 = BattlePokemon(
                            species=opp['species'], types=opp['types'],
                            atk=opp['atk'], def_=opp['def_'], max_hp=opp['hp'],
                            fast_move=dict(opp['fm']),
                            charged_moves=[dict(cm) for cm in opp['cms']],
                            shields=s_opp,
                        )
                        result = simulate(bp0, bp1,
                                          charged_policy_0=pvpoke_dp,
                                          charged_policy_1=pvpoke_dp)
                        score = result.pvpoke_score(0)
                        per_opp[(si, oi)] = score
                        total_score += score
                        count += 1
                        n_sims += 1

                avg_score = total_score / count if count else 0
                sp = atk_stat * def_stat * hp_stat
                results.append({
                    'atk_iv': a, 'def_iv': d, 'sta_iv': s,
                    'level': lv, 'cp': mon_cp,
                    'atk': atk_stat, 'def_': def_stat, 'hp': hp_stat,
                    'stat_product': sp,
                    'avg_score': avg_score,
                    'per_opp': per_opp,
                })

    results.sort(key=lambda r: r['avg_score'], reverse=True)
    for i, r in enumerate(results):
        r['battle_rank'] = i + 1

    by_sp = sorted(results, key=lambda r: r['stat_product'], reverse=True)
    for i, r in enumerate(by_sp):
        r['sp_rank'] = i + 1

    return results, n_sims


# ---------------------------------------------------------------------------
# HTML output with threshold highlighting
# ---------------------------------------------------------------------------

# Colors for threshold tiers — most restrictive first, then less restrictive.
# "Other" (no threshold) uses the Viridis colorscale fallback.
THRESHOLD_COLORS = [
    '#FFD700',  # gold — most restrictive tier
    '#00E676',  # bright green — next tier
    '#FF6D00',  # orange
    '#E040FB',  # purple
    '#00B0FF',  # blue
    '#FF1744',  # red
    '#76FF03',  # lime
    '#F50057',  # pink
]


def generate_html(species, league, moveset_results, html_path, thresholds=None,
                  opponent_label=None, shield_scenarios=None, opponent_names=None,
                  opp_iv_mode='pvpoke'):
    """
    Generate an interactive HTML file with Plotly.js scatter plots.

    If thresholds are provided, points are colored by which threshold tier they
    meet (most restrictive first). The legend is interactive — click to
    isolate/hide groups, hover over legend entries to highlight those points.
    """
    # Build threshold tier names and assign colors
    tier_names = list(thresholds.keys()) if thresholds else []
    tier_colors = {}
    for i, name in enumerate(tier_names):
        tier_colors[name] = THRESHOLD_COLORS[i % len(THRESHOLD_COLORS)]

    opp_desc = opponent_label or "PvPoke rankings"

    plots_data = []
    for fast_id, charged_ids, results in moveset_results:
        label = moveset_label(fast_id, charged_ids)

        # Rank-1 reference for matchup diffs (results are sorted by avg_score desc)
        r1 = results[0] if results else None
        ref_per_opp = r1.get('per_opp') if r1 else None
        ref_label = (f"Rank 1 ({r1['atk_iv']}/{r1['def_iv']}/{r1['sta_iv']})"
                     if r1 else None)

        def hover(r, tier=None):
            return _hover_text(r, tier_name=tier, ref_per_opp=ref_per_opp,
                               ref_label=ref_label, opponent_names=opponent_names,
                               shield_scenarios=shield_scenarios)

        if thresholds:
            for r in results:
                r['_tier'] = classify_iv(r, thresholds)

            traces = []

            other = [r for r in results if r['_tier'] is None]
            if other:
                traces.append({
                    'name': 'Other',
                    'x': [r['sp_rank'] for r in other],
                    'y': [r['avg_score'] for r in other],
                    'text': [hover(r) for r in other],
                    'marker_color': [r['avg_score'] for r in other],
                    'use_colorscale': True,
                })

            for tier_name in tier_names:
                tier_results = [r for r in results if r['_tier'] == tier_name]
                if tier_results:
                    thresh = thresholds[tier_name]
                    thresh_desc = _threshold_desc(thresh)
                    traces.append({
                        'name': f'{tier_name} ({thresh_desc})',
                        'x': [r['sp_rank'] for r in tier_results],
                        'y': [r['avg_score'] for r in tier_results],
                        'text': [hover(r, tier_name) for r in tier_results],
                        'marker_color': tier_colors[tier_name],
                        'use_colorscale': False,
                    })

            plots_data.append({'label': label, 'traces': traces, 'results': results})
        else:
            traces = [{
                'name': 'All IVs',
                'x': [r['sp_rank'] for r in results],
                'y': [r['avg_score'] for r in results],
                'text': [hover(r) for r in results],
                'marker_color': [r['avg_score'] for r in results],
                'use_colorscale': True,
            }]
            plots_data.append({'label': label, 'traces': traces, 'results': results})

    # --- Build HTML ---
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{species} {league.title()} League IV Deep Dive</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 20px; background: #1a1a2e; color: #e0e0e0; }}
  h1 {{ color: #e94560; }}
  h2 {{ color: #0f3460; background: #16213e; padding: 8px 12px; border-radius: 4px;
        color: #e0e0e0; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 15px; }}
  .plot-container {{ margin-bottom: 30px; }}
  .summary {{ background: #16213e; padding: 12px; border-radius: 6px;
              margin-bottom: 20px; font-size: 14px; }}
  .summary table {{ border-collapse: collapse; width: 100%; }}
  .summary th, .summary td {{ text-align: left; padding: 4px 10px;
                               border-bottom: 1px solid #0f3460; }}
  .summary th {{ color: #e94560; }}
  .tier-badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px;
                 font-size: 12px; font-weight: bold; margin-left: 4px; }}
  .threshold-info {{ background: #16213e; padding: 10px; border-radius: 6px;
                     margin-bottom: 15px; font-size: 13px; }}
  .threshold-info span {{ font-weight: bold; }}
  details.meta {{ cursor: pointer; }}
  details.meta summary {{ color: #888; font-size: 13px; }}
</style>
</head>
<body>
<h1>{species} — {league.title()} League IV Deep Dive</h1>
<p class="meta">Opponents: {opp_desc}
| Shield scenario(s): {', '.join(f'{s0}v{s1}' for s0, s1 in (shield_scenarios or [(1,1)]))}
| Policy: pvpoke_dp</p>
"""

    # List opponents
    if opponent_names:
        html += '<details class="meta"><summary>Opponent list '
        html += f'({len(opponent_names)} mons)</summary><p style="margin:4px 0 8px 12px">'
        html += ', '.join(opponent_names)
        html += '</p></details>\n'

    # Threshold legend box
    if thresholds:
        html += '<div class="threshold-info">\n'
        html += '<strong>IV Thresholds:</strong><br>\n'
        for tier_name in tier_names:
            thresh = thresholds[tier_name]
            color = tier_colors[tier_name]
            desc = _threshold_desc(thresh)
            html += (f'<span class="tier-badge" style="background:{color};color:#000">'
                     f'{tier_name}</span> {desc}<br>\n')
        html += '<br><em>Hover over legend entries to isolate that tier. '
        html += 'Click to lock the isolation; click again to unlock.</em>\n'
        html += '</div>\n'

    for i, pd in enumerate(plots_data):
        results = pd['results']
        top10 = results[:10]
        html += f'<h2>{pd["label"]}</h2>\n'

        # Summary table with threshold badges
        html += '<div class="summary"><table>\n'
        html += '<tr><th>Battle Rank</th><th>IVs</th><th>Level</th><th>CP</th>'
        html += '<th>Atk</th><th>Def</th><th>HP</th><th>SP Rank</th>'
        html += '<th>Avg Score</th>'
        if thresholds:
            html += '<th>Tier</th>'
        html += '</tr>\n'
        for r in top10:
            tier = r.get('_tier', None)
            tier_html = ''
            if thresholds:
                if tier:
                    color = tier_colors.get(tier, '#666')
                    tier_html = (f'<td><span class="tier-badge" '
                                 f'style="background:{color};color:#000">'
                                 f'{tier}</span></td>')
                else:
                    tier_html = '<td>—</td>'
            html += (f'<tr><td>#{r["battle_rank"]}</td>'
                     f'<td>{r["atk_iv"]}/{r["def_iv"]}/{r["sta_iv"]}</td>'
                     f'<td>{r["level"]}</td><td>{r["cp"]}</td>'
                     f'<td>{r["atk"]:.2f}</td><td>{r["def_"]:.2f}</td><td>{r["hp"]}</td>'
                     f'<td>#{r["sp_rank"]}</td>'
                     f'<td>{r["avg_score"]:.1f}</td>{tier_html}</tr>\n')
        html += '</table></div>\n'
        html += f'<div id="plot{i}" class="plot-container" style="height:550px;"></div>\n'

    # Plotly traces
    html += '<script>\n'
    for i, pd in enumerate(plots_data):
        # Compute fixed axis ranges from all data so they never rescale
        all_x = []
        all_y = []
        for trace in pd['traces']:
            all_x.extend(trace['x'])
            all_y.extend(trace['y'])
        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(all_y), max(all_y)
        x_pad = max(1, (x_max - x_min) * 0.02)
        y_pad = max(0.5, (y_max - y_min) * 0.03)

        traces_js = []
        # Track original opacities per trace for hover restore
        original_opacities = []
        for trace in pd['traces']:
            t = {
                'x': trace['x'],
                'y': trace['y'],
                'text': trace['text'],
                'name': trace['name'],
                'mode': 'markers',
                'type': 'scattergl',
                'hoverinfo': 'text',
            }
            if trace['use_colorscale']:
                opacity = 0.4
                t['marker'] = {
                    'size': 3,
                    'color': trace['marker_color'],
                    'colorscale': 'Viridis',
                    'opacity': opacity,
                }
                if not thresholds:
                    t['marker']['colorbar'] = {'title': 'Avg Score'}
            else:
                opacity = 0.85
                t['marker'] = {
                    'size': 5,
                    'color': trace['marker_color'],
                    'opacity': opacity,
                    'line': {'width': 0.5, 'color': '#000'},
                }
            traces_js.append(t)
            original_opacities.append(opacity)

        layout = {
            'title': pd['label'],
            'xaxis': {
                'title': 'Stat Product Rank (1=best)',
                'range': [x_max + x_pad, x_min - x_pad],  # reversed
                'fixedrange': True,
            },
            'yaxis': {
                'title': 'Avg Battle Score',
                'range': [y_min - y_pad, y_max + y_pad],
                'fixedrange': True,
            },
            'paper_bgcolor': '#1a1a2e',
            'plot_bgcolor': '#16213e',
            'font': {'color': '#e0e0e0'},
            'hovermode': 'closest',
            'legend': {
                'bgcolor': 'rgba(22,33,62,0.8)',
                'bordercolor': '#0f3460',
                'borderwidth': 1,
            },
        }
        # Use .then() to attach legend hover behavior after Plotly finishes rendering.
        # Plotly.restyle is the correct API for per-trace marker updates.
        # We suppress default legend click/doubleclick, and instead use
        # mouseenter/mouseleave on the legend SVG <g class="traces"> elements
        # to isolate one tier at a time without rescaling axes.
        html += f"""
Plotly.newPlot("plot{i}", {json.dumps(traces_js)}, {json.dumps(layout)},
  {{responsive: true}}).then(function(gd) {{
  var origOpacities = {json.dumps(original_opacities)};
  var nTraces = origOpacities.length;
  var lockedIdx = -1;  // -1 = not locked; >= 0 = locked to that trace

  gd.on("plotly_legendclick", function() {{ return false; }});
  gd.on("plotly_legenddoubleclick", function() {{ return false; }});

  function highlightTrace(idx) {{
    for (var j = 0; j < nTraces; j++) {{
      var op = (j === idx) ? Math.min(1.0, origOpacities[j] + 0.15) : 0.03;
      Plotly.restyle(gd, {{"marker.opacity": op}}, [j]);
    }}
  }}

  function restoreAll() {{
    for (var j = 0; j < nTraces; j++) {{
      Plotly.restyle(gd, {{"marker.opacity": origOpacities[j]}}, [j]);
    }}
  }}

  var attempts = 0;
  function attachLegendHover() {{
    var items = gd.querySelectorAll(".legend .traces");
    if (items.length === 0 && attempts < 50) {{
      attempts++;
      setTimeout(attachLegendHover, 100);
      return;
    }}
    items.forEach(function(el, idx) {{
      el.style.cursor = "pointer";
      el.addEventListener("mouseenter", function() {{
        if (lockedIdx < 0) highlightTrace(idx);
      }});
      el.addEventListener("mouseleave", function() {{
        if (lockedIdx < 0) restoreAll();
      }});
      el.addEventListener("click", function() {{
        if (lockedIdx === idx) {{
          lockedIdx = -1;
          restoreAll();
        }} else {{
          lockedIdx = idx;
          highlightTrace(idx);
        }}
      }});
    }});
  }}
  attachLegendHover();
}});
"""

    # Methodology footer
    shield_desc = ', '.join(f'{s0}v{s1}' for s0, s1 in (shield_scenarios or [(1, 1)]))
    n_opponents = len(opponent_names) if opponent_names else '?'
    if opp_iv_mode == 'rank1':
        opp_iv_desc = 'stat-product rank 1 IVs'
    else:
        opp_iv_desc = ("PvPoke's default IVs (the IVs pvpoke.com uses when you "
                       "load a matchup)")
    html += '</script>\n'
    html += f"""
<hr style="border-color:#0f3460; margin-top:40px">
<div style="color:#888; font-size:12px; max-width:800px; margin:10px 0 30px 0; line-height:1.6">
<strong>Methodology</strong><br>
Each of the 4096 possible IV spreads (0&ndash;15 for Atk/Def/Sta) is leveled to the
highest level that stays under the {league.title()} League CP cap ({LEAGUE_CAPS[league]}).
For each IV spread, a battle is simulated against each of the {n_opponents} opponents
in the {opp_desc} pool in the {shield_desc} shield scenario(s), using the
<code>pvpoke_dp</code> policy (PvPoke's simulate-mode dynamic programming policy).
Opponents use {opp_iv_desc} at their best level for this league.
<br><br>
<strong>Avg Battle Score</strong> is the mean of the PvPoke battle scores across all
opponents and shield scenarios. The PvPoke score for a single battle is:
<code>500 &times; (damage dealt / opponent max HP) + 500 &times; (HP remaining / own max HP)</code>.
A score of 500 means a tie; above 500 is a win, below is a loss.
<br><br>
<strong>Battle Rank</strong> is the IV spread's position when all 4096 spreads are
sorted by Avg Battle Score (descending). Battle Rank #1 is the IV spread that performs
best on average against this opponent pool.
<strong>Stat Product Rank</strong> (x-axis) is the traditional PvP IV rank based on
Atk &times; Def &times; HP.
</div>
"""
    html += '</body>\n</html>\n'

    with open(html_path, 'w') as f:
        f.write(html)
    print(f"  HTML written to {html_path}")


def _hover_text(r, tier_name=None, ref_per_opp=None, ref_label=None,
                opponent_names=None, shield_scenarios=None):
    """Build hover text for a single IV result.

    If ref_per_opp is provided (the rank-1 IV's per-opponent scores),
    show which matchups were gained/lost compared to rank 1.
    """
    lines = [
        f"IVs: {r['atk_iv']}/{r['def_iv']}/{r['sta_iv']}",
        f"L{r['level']} CP{r['cp']}",
        f"Atk:{r['atk']:.2f} Def:{r['def_']:.2f} HP:{r['hp']}",
        f"SP Rank: #{r['sp_rank']} | Battle Rank: #{r['battle_rank']}",
        f"Avg Score: {r['avg_score']:.1f}",
    ]
    if tier_name:
        lines.append(f"Tier: {tier_name}")

    # Matchup diffs vs rank 1
    if ref_per_opp and opponent_names and shield_scenarios and 'per_opp' in r:
        my_opp = r['per_opp']
        if my_opp is not ref_per_opp:  # skip for rank 1 itself
            lines.append(f'')
            lines.append(f'vs {ref_label}:')
            for si, (s_focal, s_opp) in enumerate(shield_scenarios):
                gained = []
                lost = []
                for oi, opp_name in enumerate(opponent_names):
                    key = (si, oi)
                    my_score = my_opp.get(key, 0)
                    ref_score = ref_per_opp.get(key, 0)
                    my_win = my_score >= 500
                    ref_win = ref_score >= 500
                    # Short name for display
                    short = opp_name.split('(')[0].strip()[:12]
                    if my_win and not ref_win:
                        gained.append(short)
                    elif not my_win and ref_win:
                        lost.append(short)
                scenario_label = f'{s_focal}v{s_opp}'
                parts = []
                if gained:
                    parts.append(f'+{",".join(gained)}')
                if lost:
                    parts.append(f'-{",".join(lost)}')
                if parts:
                    lines.append(f'  {scenario_label}: {" | ".join(parts)}')
                else:
                    lines.append(f'  {scenario_label}: (same matchups)')

    return '<br>'.join(lines)


def _threshold_desc(thresh):
    """Human-readable description of a threshold."""
    parts = []
    if thresh['attack'] > 0:
        parts.append(f"Atk≥{thresh['attack']}")
    if thresh['defense'] > 0:
        parts.append(f"Def≥{thresh['defense']}")
    if thresh['stamina'] > 0:
        parts.append(f"HP≥{thresh['stamina']}")
    return ', '.join(parts) if parts else '(no requirements)'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='IV deep dive: sim all 4096 IV spreads against meta opponents.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('species', help='Focal species name (e.g. Medicham, Tinkaton)')
    parser.add_argument('--fast', default=None, metavar='MOVE',
                        help='Fast move ID (if omitted, try all legal fast moves)')
    parser.add_argument('--charged', default=None, metavar='MOVE[,MOVE]',
                        help='One or two charged move IDs, comma-separated. '
                             'Moves not yet in the species pool (CD moves) are allowed.')
    parser.add_argument('--league', default='great',
                        choices=['great', 'ultra', 'master'])
    parser.add_argument('--opponents', type=int, default=20, metavar='N',
                        help='Number of top meta opponents from rankings (default: 20). '
                             'Ignored if --group is used.')
    parser.add_argument('--group', default=None, metavar='NAME',
                        help='Use a PvPoke custom group as opponents '
                             '(e.g. championshipseries). Fetched from GitHub, '
                             'cached locally. Known groups: '
                             f'{", ".join(KNOWN_GROUPS[:8])}...')
    parser.add_argument('--top-movesets', type=int, default=5, metavar='N',
                        help='Keep top N movesets after screening (default: 5)')
    parser.add_argument('--shield-scenario', default='1,1', metavar='S1,S2',
                        help='Shield scenario as focal,opponent (default: 1,1). '
                             'Use "all" for 0v0+1v1+2v2.')
    parser.add_argument('--shadow', action='store_true',
                        help='Focal species is shadow')
    parser.add_argument('--opp-ivs', default='pvpoke', choices=['pvpoke', 'rank1'],
                        help='Opponent IV selection: pvpoke (PvPoke default IVs, '
                             'what pvpoke.com uses) or rank1 (stat product rank 1). '
                             'Default: pvpoke.')
    parser.add_argument('--thresholds', default=None, metavar='FILE',
                        help='JSON file with IV thresholds to highlight on plots. '
                             'Format: {"Name": {"attack": N, "defense": N, "stamina": N}}. '
                             'Order from most restrictive to least restrictive.')
    parser.add_argument('--html', default=None, metavar='FILE',
                        help='Write interactive HTML plot to FILE')
    parser.add_argument('--screen-opponents', type=int, default=None, metavar='N',
                        help='Use only top N opponents for phase 1 screen '
                             '(default: same as --opponents)')

    args = parser.parse_args()

    # Parse shield scenarios
    if args.shield_scenario == 'all':
        shield_scenarios = [(0, 0), (1, 1), (2, 2)]
    else:
        parts = args.shield_scenario.split(',')
        if len(parts) != 2:
            sys.exit("--shield-scenario must be S1,S2 (e.g. 1,1) or 'all'")
        shield_scenarios = [(int(parts[0]), int(parts[1]))]

    # Parse charged moves
    user_charged = None
    if args.charged:
        user_charged = [c.strip() for c in args.charged.split(',')]

    # Load thresholds
    thresholds = None
    if args.thresholds:
        thresholds = load_thresholds(args.thresholds)
        print(f"  Loaded {len(thresholds)} threshold tier(s) from {args.thresholds}")

    print(f"\n{'='*60}")
    print(f"  {args.species}{'  (Shadow)' if args.shadow else ''} — "
          f"{args.league.title()} League IV Deep Dive")
    print(f"{'='*60}\n")

    # Enumerate movesets
    movesets = enumerate_movesets(args.species, args.fast, user_charged)
    print(f"  {len(movesets)} moveset combination(s) to evaluate")

    # Get opponents — from group or rankings
    opponent_label = None
    if args.group:
        group_entries = load_group(args.group)
        opponents = []
        opp_movesets_full = []
        for species_name, fast_move, charged_moves, is_shadow in group_entries:
            if species_name == args.species:
                continue
            opponents.append(species_name)
            opp_movesets_full.append((fast_move, charged_moves))
        opponent_label = f"PvPoke group: {args.group} ({len(opponents)} mons)"
        print(f"  Opponents: {opponent_label}")
    else:
        screen_n = args.screen_opponents or args.opponents
        opponents = get_top_opponents(args.league, args.opponents,
                                      exclude_species=args.species)
        opponent_label = f"Top {len(opponents)} from {args.league} rankings"
        print(f"  {len(opponents)} meta opponents (top from {args.league} rankings)")

        # Resolve opponent movesets from rankings defaults
        opp_movesets_full = []
        to_remove = []
        for opp in opponents:
            try:
                opp_fast, opp_charged = get_default_moveset(opp, league=args.league)
                opp_movesets_full.append((opp_fast, opp_charged))
            except KeyError:
                print(f"  Warning: skipping {opp} (no default moveset)")
                to_remove.append(opp)
        for opp in to_remove:
            idx = opponents.index(opp)
            opponents.pop(idx)

    opp_iv_label = 'PvPoke defaults' if args.opp_ivs == 'pvpoke' else 'rank 1 (stat product)'
    print(f"  Shield scenario(s): {shield_scenarios}")
    print(f"  Opponent IVs: {opp_iv_label}")
    if thresholds:
        for name, thresh in thresholds.items():
            print(f"  Threshold: {name} — {_threshold_desc(thresh)}")
    print()

    # Determine screen opponents
    if args.group:
        screen_opponents = opponents
        screen_opp_movesets = opp_movesets_full
    else:
        screen_n = args.screen_opponents or args.opponents
        screen_opponents = opponents[:screen_n]
        screen_opp_movesets = opp_movesets_full[:screen_n]

    # Phase 1: Screen movesets
    opp_iv_mode = args.opp_ivs
    surviving = screen_movesets(
        args.species, movesets, args.league, args.shadow,
        screen_opponents, screen_opp_movesets, shield_scenarios,
        args.top_movesets, opp_iv_mode=opp_iv_mode,
    )

    # Phase 2: Full IV sweep for each surviving moveset
    all_moveset_results = []
    for mi, (fast_id, charged_ids) in enumerate(surviving):
        label = moveset_label(fast_id, charged_ids)
        print(f"  Phase 2 [{mi+1}/{len(surviving)}]: {label}")
        print(f"    Simming 4096 IVs × {len(opponents)} opponents "
              f"× {len(shield_scenarios)} scenario(s)...")
        t0 = time.time()

        results, n_sims = iv_sweep(
            args.species, fast_id, charged_ids, args.league, args.shadow,
            opponents, opp_movesets_full, shield_scenarios,
            opp_iv_mode=opp_iv_mode,
        )

        elapsed = time.time() - t0
        rate = n_sims / elapsed if elapsed > 0 else 0
        print(f"    {n_sims:,} sims in {elapsed:.1f}s ({rate:,.0f} sims/s)")

        # Classify by thresholds if provided
        if thresholds:
            for r in results:
                r['_tier'] = classify_iv(r, thresholds)
            tier_counts = {}
            for r in results:
                t = r.get('_tier')
                if t:
                    tier_counts[t] = tier_counts.get(t, 0) + 1
            print(f"    Threshold hits: {tier_counts if tier_counts else 'none'}")

        # Print top 20
        print(f"\n    Top 20 IV spreads by average battle score:")
        hdr = (f"    {'Rank':>4s}  {'IVs':>8s}  {'Lvl':>5s}  {'CP':>4s}  "
               f"{'Atk':>7s}  {'Def':>7s}  {'HP':>3s}  "
               f"{'SP Rank':>7s}  {'Avg Score':>9s}")
        if thresholds:
            hdr += f"  {'Tier':>12s}"
        print(hdr)
        print(f"    {'-' * (70 + (14 if thresholds else 0))}")
        for r in results[:20]:
            line = (f"    {r['battle_rank']:4d}  "
                    f"{r['atk_iv']:2d}/{r['def_iv']:2d}/{r['sta_iv']:2d}  "
                    f"{r['level']:5.1f}  {r['cp']:4d}  "
                    f"{r['atk']:7.2f}  {r['def_']:7.2f}  {r['hp']:3d}  "
                    f"{'#'+str(r['sp_rank']):>7s}  {r['avg_score']:9.1f}")
            if thresholds:
                tier = r.get('_tier', '')
                line += f"  {tier or '':>12s}"
            print(line)
        print()

        all_moveset_results.append((fast_id, charged_ids, results))

    # HTML output
    if args.html:
        generate_html(args.species, args.league, all_moveset_results, args.html,
                      thresholds=thresholds, opponent_label=opponent_label,
                      shield_scenarios=shield_scenarios,
                      opponent_names=opponents, opp_iv_mode=opp_iv_mode)

    print("Done.\n")


if __name__ == '__main__':
    main()
