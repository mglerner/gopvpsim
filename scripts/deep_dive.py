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
from gopvpsim.moves import get_moves, type_effectiveness, stab
from gopvpsim.data import (
    load_gamemaster, load_rankings, get_default_moveset, parse_types,
    load_group as fetch_group,
)
from gopvpsim.battle import (
    BattlePokemon, simulate,
    pvpoke_dp, pvpoke_simulate_shield,
)
from gopvpsim.thresholds import (
    ThresholdRegistry, load_file as load_threshold_file, as_legacy_dict,
)
from gopvpsim.anchors import (
    resolve_anchors, tag_iv, ResolvedAnchor, build_auto_anchors,
    derive_short_name,
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


def discover_slayer_thresholds(results, opponent_idx, n_scenarios, opponent_name=None):
    """
    Discover IV thresholds optimized to beat a specific opponent.

    Ranks each IV by the number of shield scenarios it WINS (score >= 500)
    against the target opponent, breaking ties by average score. This
    surfaces "slayer" tiers — IVs that flip the most matchups in their
    favor against a specific opponent.

    Returns (thresholds_dict, slayer_results) where slayer_results is the
    list of (wins, avg_score, result) tuples sorted by win count desc.
    Threshold = minimum stat values among IVs that achieve the top win count.
    Only stats meaningfully separate the winners from losers are reported.
    """
    if not results or len(results) < 50:
        return {}, []

    # Score each IV by win count + avg score vs the target opponent
    scored = []
    for r in results:
        po = r.get('per_opp', {})
        scen_scores = [po.get((si, opponent_idx), 0) for si in range(n_scenarios)]
        wins = sum(1 for s in scen_scores if s >= 500)
        avg = sum(scen_scores) / n_scenarios if n_scenarios else 0
        scored.append((wins, avg, r))
    scored.sort(key=lambda x: (-x[0], -x[1]))

    if not scored:
        return {}, []

    max_wins = scored[0][0]
    if max_wins == 0:
        # Can't beat this opponent at all
        return {}, scored

    # All IVs that achieve the maximum win count
    winners = [r for w, _, r in scored if w == max_wins]
    losers = [r for w, _, r in scored if w < max_wins]

    if not winners or not losers:
        # Either everyone or no one wins — no meaningful threshold
        return {}, scored

    # For each stat, find the range that separates winners from losers
    win_atk = sorted(r['atk'] for r in winners)
    win_def = sorted(r['def_'] for r in winners)
    win_hp = sorted(r['hp'] for r in winners)
    lose_atk_max = max(r['atk'] for r in losers)
    lose_def_max = max(r['def_'] for r in losers)
    lose_hp_max = max(r['hp'] for r in losers)

    # The most useful threshold is the MINIMUM stat among winners — that's the
    # "you need at least this much" requirement. But we only want to report
    # a stat if losers also exist with HIGHER values (meaning the stat alone
    # doesn't determine the win — but it's still a necessary floor).
    # A stat is "discriminating" if winners have a higher minimum than the
    # population median.
    n_results = len(results)
    pop_atk_med = sorted(r['atk'] for r in results)[n_results // 2]
    pop_def_med = sorted(r['def_'] for r in results)[n_results // 2]
    pop_hp_med = sorted(r['hp'] for r in results)[n_results // 2]

    win_atk_min = win_atk[0]
    win_def_min = win_def[0]
    win_hp_min = win_hp[0]

    thresh = {'attack': 0, 'defense': 0, 'stamina': 0}
    # Report stat thresholds where the winner minimum is meaningfully above
    # the population median (so it's actually a constraint).
    if win_atk_min > pop_atk_med * 1.005:
        thresh['attack'] = round(win_atk_min, 2)
    if win_def_min > pop_def_med * 1.005:
        thresh['defense'] = round(win_def_min, 2)
    if win_hp_min > pop_hp_med:
        thresh['stamina'] = int(win_hp_min)

    return thresh, scored


# ---------------------------------------------------------------------------
# Iterative slayer discovery (mirror match Nash-style iteration)
# ---------------------------------------------------------------------------

# Worker state for slayer iteration multiprocessing
_slayer_state = {}


def _slayer_worker_init(species, focal_types, base_atk, base_def, base_sta,
                         max_cp, shadow, fm_template, cms_template,
                         shield_scenarios):
    _slayer_state['species'] = species
    _slayer_state['focal_types'] = focal_types
    _slayer_state['base_atk'] = base_atk
    _slayer_state['base_def'] = base_def
    _slayer_state['base_sta'] = base_sta
    _slayer_state['max_cp'] = max_cp
    _slayer_state['shadow'] = shadow
    _slayer_state['fm_template'] = fm_template
    _slayer_state['cms_template'] = cms_template
    _slayer_state['shield_scenarios'] = shield_scenarios


def _slayer_iter_worker(args):
    """
    Process a chunk of focal stat profiles against a list of opponent IVs.
    Returns dict of (profile_key, opp_iv_idx) -> tuple of scores.
    profile_key is a (atk, def_, hp) tuple. The parent expands these to
    all matching focal_idx values.
    """
    focal_profile_chunk, opponents = args
    # focal_profile_chunk: list of (profile_key, atk, def_, hp)
    # opponents: list of (opp_iv_idx, (opp_atk, opp_def, opp_hp))
    ws = _slayer_state
    species = ws['species']
    focal_types = ws['focal_types']
    fm_template = ws['fm_template']
    cms_template = ws['cms_template']
    shield_scenarios = ws['shield_scenarios']

    results = {}
    for profile_key, atk_stat, def_stat, hp_stat in focal_profile_chunk:
        for opp_iv_idx, opp_data in opponents:
            opp_atk, opp_def, opp_hp = opp_data
            scores = []
            for s_focal, s_opp in shield_scenarios:
                bp0 = BattlePokemon(
                    species=species, types=focal_types,
                    atk=atk_stat, def_=def_stat, max_hp=hp_stat,
                    fast_move=dict(fm_template),
                    charged_moves=[dict(cm) for cm in cms_template],
                    shields=s_focal,
                )
                bp1 = BattlePokemon(
                    species=species, types=focal_types,
                    atk=opp_atk, def_=opp_def, max_hp=opp_hp,
                    fast_move=dict(fm_template),
                    charged_moves=[dict(cm) for cm in cms_template],
                    shields=s_opp,
                )
                res = simulate(bp0, bp1,
                               charged_policy_0=pvpoke_dp,
                               charged_policy_1=pvpoke_dp)
                scores.append(round(res.pvpoke_score(0)))
            results[(profile_key, opp_iv_idx)] = tuple(scores)
    return results


def _build_focal_meta(species, league, shadow):
    """Compute (atk, def, hp, iv_idx) for all valid focal IVs.

    Returns (iv_to_idx, iv_meta_tuples) where iv_meta_tuples is a list of
    (a, d, s, atk, def, hp). Thin wrapper around compute_iv_metadata for
    backwards compatibility with the slayer iteration code.
    """
    iv_meta_dicts = compute_iv_metadata(species, league, shadow=shadow)
    iv_to_idx = {}
    iv_meta = []
    for idx, m in enumerate(iv_meta_dicts):
        iv_to_idx[(m['atk_iv'], m['def_iv'], m['sta_iv'])] = idx
        iv_meta.append((m['atk_iv'], m['def_iv'], m['sta_iv'],
                        m['atk'], m['def_'], m['hp']))
    return iv_to_idx, iv_meta


def iterative_slayer_discovery(species, league, shadow, fast_id, charged_ids,
                                shield_scenarios, initial_opp_iv,
                                max_rounds=4, top_per_round=10, cache=None,
                                metric='all'):
    """
    Iterative slayer discovery: find IVs that beat the mirror match through
    Nash-style iteration.

    Round 0: test all 4096 focal IVs vs the initial opponent (e.g. PvPoke
             default). Find the top N by win count.
    Round k: test all 4096 focal IVs vs the previous round's top N opponents.
             Find the new top N by total wins across all current opponents.
    Stop when: top set converges, or max_rounds reached.

    Returns dict with:
        'history': list of per-round top sets (each is list of (focal_idx, total_wins, avg_score, atk, def, hp))
        'final': the final top set (list of dicts)
        'rounds_run': how many rounds executed
        'converged': bool
        'cache_stats': string from cache
    """
    import multiprocessing
    # slayer_cache is in the same scripts/ directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from slayer_cache import SlayerCache

    iv_to_idx, iv_meta = _build_focal_meta(species, league, shadow)
    n_focal = len(iv_meta)

    fast_moves_db, charged_moves_db = get_moves()
    fm_template = dict(fast_moves_db[fast_id])
    cms_template = [dict(charged_moves_db[cid]) for cid in charged_ids]

    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
    focal_types = parse_types(focal_mon)

    base = get_species(species)
    base_atk, base_def, base_sta = base['atk'], base['def'], base['hp']
    max_cp = LEAGUE_CAPS[league]

    if cache is None:
        cache = SlayerCache(disk=False)

    # Pre-compute focal profile groups: profile_key -> list of focal_idx values
    # IVs with identical (atk, def, hp) produce identical battles, so we only
    # need to sim one representative per profile and copy the result to the rest.
    def _profile_key(focal_idx):
        a_, d_, s_, at, df, hp = iv_meta[focal_idx]
        return (round(at, 4), round(df, 4), int(hp))

    focal_profile_to_ivs = {}  # profile_key -> [focal_idx, ...]
    focal_profile_data = {}    # profile_key -> (atk, def, hp) for sim
    for focal_idx in range(n_focal):
        a_, d_, s_, at, df, hp = iv_meta[focal_idx]
        pk = (round(at, 4), round(df, 4), int(hp))
        focal_profile_to_ivs.setdefault(pk, []).append(focal_idx)
        if pk not in focal_profile_data:
            focal_profile_data[pk] = (at, df, hp)
    n_unique_profiles = len(focal_profile_data)

    # Round 0: initial opponent IV
    initial_iv = initial_opp_iv  # (a, d, s)
    if initial_iv not in iv_to_idx:
        # Initial opponent not in our IV list (shouldn't happen)
        return {'error': f'Initial opponent IV {initial_iv} not in valid IVs'}

    current_opponent_indices = [iv_to_idx[initial_iv]]
    history = []
    converged = False

    import time as _time
    n_workers = min(multiprocessing.cpu_count(), 16)
    total_round_sims = 0  # accumulated across rounds for an estimate

    for round_idx in range(max_rounds):
        round_start = _time.time()
        # Build opponent meta (atk, def, hp) for current round's opponents
        opp_data_list = []
        for opp_idx in current_opponent_indices:
            a, d, s, atk_, def_, hp_ = iv_meta[opp_idx]
            opp_data_list.append((opp_idx, (atk_, def_, hp_)))

        # Determine which (focal, opp) pairs need sim (cache miss).
        # We dedup BOTH sides:
        # - Focals are deduped via focal_profile_to_ivs (same stats = same battle)
        # - Opponents are already deduped because the caller does dedup before
        #   passing current_opponent_indices.
        # For each opp, check if any of its focal-profile representatives are missing.
        opps_needing_sim = []
        for opp_idx, opp_data in opp_data_list:
            # Check if any representative is missing for this opponent
            any_missing = False
            for pk, ivs in focal_profile_to_ivs.items():
                rep = ivs[0]
                if (rep, opp_idx) not in cache.data:
                    any_missing = True
                    break
            if any_missing:
                opps_needing_sim.append((opp_idx, opp_data))

        n_profiles = len(focal_profile_data)
        n_scen = len(shield_scenarios)
        # Estimate sim count: profiles * cache-missing opponents * scenarios
        n_round_sims = n_profiles * len(opps_needing_sim) * n_scen

        if opps_needing_sim:
            print(f"    Round {round_idx}: {len(opp_data_list)} opponents "
                  f"({len(opps_needing_sim)} need sim), "
                  f"{n_profiles} unique focal profiles, "
                  f"~{n_round_sims:,} sims to run", flush=True)

            # Build the focal profile chunks. We sim each unique (atk, def, hp)
            # exactly once per opponent. After workers return, we expand the
            # results to all focal IVs that share that profile.
            profile_list = [(pk, dat[0], dat[1], dat[2])
                            for pk, dat in focal_profile_data.items()]
            # Split into ~100 chunks (capped by len(profile_list)). With
            # imap_unordered the pool grabs the next chunk as workers free
            # up — finer granularity → more frequent progress reports and
            # better load balancing on uneven workloads.
            n_chunks_target = 100
            chunk_size = max(1, (len(profile_list) + n_chunks_target - 1) // n_chunks_target)
            chunks = [profile_list[i:i+chunk_size] for i in range(0, len(profile_list), chunk_size)]

            init_args = (species, focal_types, base_atk, base_def, base_sta,
                         max_cp, shadow, fm_template, cms_template, shield_scenarios)
            sim_start = _time.time()
            with multiprocessing.Pool(
                processes=n_workers,
                initializer=_slayer_worker_init,
                initargs=init_args,
            ) as pool:
                worker_args = [(chunk, opps_needing_sim) for chunk in chunks]
                # Use imap_unordered so we can report progress as workers finish
                chunk_results = []
                completed = 0
                last_print = sim_start
                for result in pool.imap_unordered(_slayer_iter_worker, worker_args):
                    chunk_results.append(result)
                    completed += 1
                    now = _time.time()
                    # Print every 10s or every chunk, whichever is less frequent
                    if now - last_print >= 10 or completed == len(chunks):
                        elapsed = now - sim_start
                        frac = completed / len(chunks)
                        eta = (elapsed / frac) * (1 - frac) if frac > 0 else 0
                        print(f"      sim progress: {completed}/{len(chunks)} chunks "
                              f"({frac*100:.0f}%), elapsed {elapsed:.0f}s, "
                              f"eta {eta:.0f}s", flush=True)
                        last_print = now

            sim_elapsed = _time.time() - sim_start
            print(f"      sim done in {sim_elapsed:.1f}s "
                  f"({n_round_sims / max(sim_elapsed, 0.01):,.0f} sims/s)", flush=True)

            # Merge into cache, expanding profile results to all matching focal IVs
            merge_start = _time.time()
            for chunk in chunk_results:
                for (profile_key, opp_idx), scores in chunk.items():
                    for focal_idx in focal_profile_to_ivs[profile_key]:
                        cache.put(focal_idx, opp_idx, scores)
            merge_elapsed = _time.time() - merge_start
            if merge_elapsed > 1.0:
                print(f"      cache merge: {merge_elapsed:.1f}s", flush=True)
        else:
            print(f"    Round {round_idx}: {len(opp_data_list)} opponents, all cache hits",
                  flush=True)

        # Identify even-scenario indices for the metric
        even_indices = [i for i, (s0, s1) in enumerate(shield_scenarios) if s0 == s1]
        n_even = len(even_indices)

        # Score each focal IV vs current opponents
        focal_scores = []
        for focal_idx in range(n_focal):
            total_wins = 0
            even_wins_per_opp = []  # for "even-strict" mode
            total_score = 0
            n_pairs = 0
            for opp_idx, _ in opp_data_list:
                cached = cache.get(focal_idx, opp_idx)
                if cached is None:
                    continue

                if metric == 'all':
                    wins = sum(1 for s in cached if s >= 500)
                elif metric == 'even':
                    wins = sum(1 for i in even_indices if cached[i] >= 500)
                elif metric == 'even-strict':
                    # Counts only IVs that win ALL even scenarios vs this opponent
                    won_all_even = all(cached[i] >= 500 for i in even_indices)
                    wins = n_even if won_all_even else 0
                    even_wins_per_opp.append(won_all_even)
                else:
                    wins = sum(1 for s in cached if s >= 500)

                avg = sum(cached) / len(cached)
                total_wins += wins
                total_score += avg
                n_pairs += 1
            if n_pairs == 0:
                continue
            avg_score = total_score / n_pairs
            a, d, s, atk_, def_, hp_ = iv_meta[focal_idx]
            focal_scores.append({
                'focal_idx': focal_idx,
                'iv': (a, d, s),
                'atk': atk_, 'def_': def_, 'hp': hp_,
                'total_wins': total_wins,
                'avg_score': avg_score,
                'n_pairs': n_pairs,
            })

        # Sort by total wins desc, then avg score desc
        focal_scores.sort(key=lambda x: (-x['total_wins'], -x['avg_score']))

        # Keep ALL IVs tied with the top_per_round threshold's win count.
        # When many IVs share the same max win count (common in mirror analysis
        # where ~80% of IVs win the same scenarios), we keep the full tied pool
        # rather than tie-breaking by avg score (which biases toward HP-heavy
        # IVs that win their losses by smaller margins).
        if len(focal_scores) > top_per_round:
            cutoff_wins = focal_scores[top_per_round - 1]['total_wins']
            top = [r for r in focal_scores if r['total_wins'] >= cutoff_wins]
        else:
            top = focal_scores

        history.append(top)

        # Convergence check: same focal_idx set as previous round
        new_set = frozenset(r['focal_idx'] for r in top)
        if round_idx > 0:
            prev_set = frozenset(r['focal_idx'] for r in history[round_idx - 1])
            if new_set == prev_set:
                converged = True
                break

        # Set up next round's opponents from the survivor pool.
        # Dedup by effective stats: IVs with identical (atk, def, hp) produce
        # literally identical battles, so we only need ONE per unique profile
        # as an opponent. The full survivor list is preserved in history[]
        # so users still see all the equivalent IVs in the final categories.
        seen_profiles = {}
        for r in top:
            profile = (round(r['atk'], 4), round(r['def_'], 4), int(r['hp']))
            if profile not in seen_profiles:
                seen_profiles[profile] = r['focal_idx']
        current_opponent_indices = list(seen_profiles.values())

    return {
        'history': history,
        'final': history[-1] if history else [],
        'rounds_run': len(history),
        'converged': converged,
        'cache_stats': cache.stats(),
    }


def categorize_slayers(survivors, resolved_anchors=None, iv_meta_list=None, top_n=None):
    """
    Classify slayer survivors into three strategic categories, using anchor
    tagging for Atk and CMP slayers and the structural HP+def heuristic for
    Bulk slayers.

    Each survivor dict is mutated to add an ``_anchor_tags`` field mapping the
    TOML parent anchor name to the list of ResolvedAnchors it passes (so the
    HTML renderer can display what each IV actually clears).

    Categories:
      Atk Slayer — at least one damage_breakpoint anchor passed. If no
                   survivor clears any BP anchor, this category is empty and
                   the HTML renderer hides it.
      CMP Slayer — at least one cmp anchor passed. Same empty-hide rule.
      Bulk Slayer — HP and def both at or above survivor median (structural)
                    OR clears at least one named bulkpoint anchor. Always
                    shown; the structural pool is the default fallback when
                    no bulkpoint anchors are configured.

    Survivors in multiple categories appear in each (cross-category badges in
    the HTML make the overlap visible).

    Args:
        survivors: list of survivor dicts from iterative_slayer_discovery.
        resolved_anchors: list of ResolvedAnchor objects from
            gopvpsim.anchors.resolve_anchors(). Empty/None means no anchor
            tagging — Atk/CMP categories will be empty.
        top_n: deprecated — full sorted lists are returned; the HTML layer
            handles truncation and expand-all.

    Returns dict of category name -> list of survivor dicts (full, sorted).
    """
    if not survivors:
        return {}

    resolved_anchors = resolved_anchors or []

    # Tag each survivor with the anchors it passes (mutates the dict)
    for r in survivors:
        tags = tag_iv(r['atk'], r['def_'], resolved_anchors)
        r['_anchor_tags'] = tags

    # Structural medians for Bulk slayer classification
    n = len(survivors)
    defs = sorted(r['def_'] for r in survivors)
    hps = sorted(r['hp'] for r in survivors)
    def_med = defs[n // 2]
    hp_med = hps[n // 2]

    atk_slayers: list = []
    bulk_slayers: list = []
    cmp_slayers: list = []

    for r in survivors:
        tags = r['_anchor_tags']
        # Partition anchor tags by kind using the ResolvedAnchor.kind field
        has_bp = any(
            any(a.kind == 'damage_breakpoint' for a in subs)
            for subs in tags.values()
        )
        has_cmp = any(
            any(a.kind == 'cmp' for a in subs)
            for subs in tags.values()
        )
        has_bulkpoint = any(
            any(a.kind == 'bulkpoint' for a in subs)
            for subs in tags.values()
        )
        if has_bp:
            atk_slayers.append(r)
        if has_cmp:
            cmp_slayers.append(r)
        # Bulk Slayer membership: structural HP+def above median OR clears
        # at least one named bulkpoint anchor.
        if (r['hp'] >= hp_med and r['def_'] >= def_med) or has_bulkpoint:
            bulk_slayers.append(r)

    # Sort each by total_wins desc, then by the relevant tiebreaker.
    # Atk Slayer tiebreaks by atk (higher = clears more BPs typically).
    # CMP Slayer tiebreaks by atk too (CMP is about raw atk).
    # Bulk Slayer tiebreaks by hp+def.
    atk_slayers.sort(key=lambda r: (-r['total_wins'], -r['atk']))
    bulk_slayers.sort(key=lambda r: (-r['total_wins'], -(r['hp'] + r['def_'])))
    cmp_slayers.sort(key=lambda r: (-r['total_wins'], -r['atk']))

    return {
        'Atk Slayer': atk_slayers,
        'Bulk Slayer': bulk_slayers,
        'CMP Slayer': cmp_slayers,
    }


def auto_discover_thresholds(results, n_tiers=2):
    """
    Discover threshold tiers automatically from simulation results.

    Analyzes the top-performing IVs to find stat values that distinguish
    them from the rest. For each stat, if the top group's 25th percentile
    is notably above the population median, that stat becomes a floor
    threshold. We use the 25th percentile (not minimum) to be robust to
    outliers.

    results: list of dicts from iv_sweep (sorted by avg_score desc)
    n_tiers: number of tiers to generate (default 2)
    """
    if not results or len(results) < 50:
        return {}

    n = len(results)

    # Tier 1: "Top 5%" — top 5% by avg score (renamed from "Premium" to
    # avoid clashing with the community use of "premium" in IV deep dives,
    # which means something more specific than a top-percentile bucket).
    # Tier 2: "Good" — top 20% by score
    tier_cuts = [max(5, n // 20), max(20, n // 5)][:n_tiers]
    tier_names = ['Top 5%', 'Good'][:n_tiers]

    # Population stats (medians)
    pop_atk = sorted(r['atk'] for r in results)
    pop_def = sorted(r['def_'] for r in results)
    pop_hp = sorted(r['hp'] for r in results)
    pop_atk_med = pop_atk[n // 2]
    pop_def_med = pop_def[n // 2]
    pop_hp_med = pop_hp[n // 2]

    thresholds = {}
    for cut, name in zip(tier_cuts, tier_names):
        top = results[:cut]

        # 25th percentile of top group (robust floor)
        top_atk = sorted(r['atk'] for r in top)
        top_def = sorted(r['def_'] for r in top)
        top_hp = sorted(r['hp'] for r in top)
        p25 = max(0, len(top) // 4)
        top_atk_p25 = top_atk[p25]
        top_def_p25 = top_def[p25]
        top_hp_p25 = top_hp[p25]

        thresh = {'attack': 0, 'defense': 0, 'stamina': 0}

        # A stat is a meaningful threshold if the top group's p25 is above
        # the population median by more than 1%
        if top_atk_p25 > pop_atk_med * 1.01:
            thresh['attack'] = round(top_atk_p25, 2)
        if top_def_p25 > pop_def_med * 1.01:
            thresh['defense'] = round(top_def_p25, 2)
        if top_hp_p25 > pop_hp_med + 1:
            thresh['stamina'] = int(top_hp_p25)

        if any(v > 0 for v in thresh.values()):
            thresholds[name] = thresh

    return thresholds


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
            if other == fixed:
                continue  # skip duplicate (e.g. GH paired with itself)
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
    """Short human-readable moveset label with pretty names."""
    fast = _pretty_name(fast_id)
    charged = ', '.join(_pretty_name(c) for c in charged_ids)
    return f"{fast} / {charged}"


def moveset_label_raw(fast_id, charged_ids):
    """Raw moveset label for internal parsing (e.g. _build_move_tuples)."""
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
    if top_n == 0 or len(movesets) <= top_n:
        print(f"  {len(movesets)} moveset(s) — skipping screen phase.\n")
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
# Phase 2: Full IV sweep (parallelized, deduped by stat profile)
# ---------------------------------------------------------------------------

# Worker state for multiprocessing (set via initializer, avoids pickling per call)
_worker_state = {}


def compute_iv_metadata(species, league, shadow=False):
    """
    Compute metadata for all valid IV spreads of a species/league.

    Returns list of dicts (one per valid IV) with keys:
        atk_iv, def_iv, sta_iv, level, cp, atk, def_, hp, stat_product
    The list is in canonical iteration order (a=0..15, d=0..15, s=0..15),
    skipping IVs that exceed CP cap at level 1.
    """
    from gopvpsim.pokemon import SHADOW_ATK_BONUS, SHADOW_DEF_MULT
    base = get_species(species)
    base_atk, base_def, base_sta = base['atk'], base['def'], base['hp']
    max_cp = LEAGUE_CAPS[league]

    iv_meta = []
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
                iv_meta.append({
                    'atk_iv': a, 'def_iv': d, 'sta_iv': s,
                    'level': lv, 'cp': mon_cp,
                    'atk': atk_stat, 'def_': def_stat, 'hp': hp_stat,
                    'stat_product': atk_stat * def_stat * hp_stat,
                })
    return iv_meta


def group_ivs_by_stat_profile(iv_meta_list):
    """
    Group IVs by effective (atk, def, hp) so we sim each profile once.

    Returns:
        profile_to_indices: dict of (atk, def, hp) -> [iv_idx, ...]
        profile_data: dict of (atk, def, hp) -> (atk, def, hp) for sim
                      (these are the high-precision values; the key uses rounded)
    """
    profile_to_indices = {}
    profile_data = {}
    for idx, meta in enumerate(iv_meta_list):
        key = (round(meta['atk'], 4), round(meta['def_'], 4), int(meta['hp']))
        profile_to_indices.setdefault(key, []).append(idx)
        if key not in profile_data:
            profile_data[key] = (meta['atk'], meta['def_'], meta['hp'])
    return profile_to_indices, profile_data


def _sweep_worker_init(species, focal_types, fm_template, cms_template,
                       opp_cache, shield_scenarios):
    """Initialize shared state in each sweep worker process."""
    _worker_state['species'] = species
    _worker_state['focal_types'] = focal_types
    _worker_state['fm_template'] = fm_template
    _worker_state['cms_template'] = cms_template
    _worker_state['opp_cache'] = opp_cache
    _worker_state['shield_scenarios'] = shield_scenarios


def _sweep_worker(profile_chunk):
    """
    Sim a chunk of focal stat profiles against the cached opponent list.

    profile_chunk: list of (profile_key, atk, def, hp) tuples.
    Returns dict of profile_key -> per_opp (which is dict of (scenario_idx, opp_idx) -> score).
    """
    ws = _worker_state
    species = ws['species']
    focal_types = ws['focal_types']
    fm_template = ws['fm_template']
    cms_template = ws['cms_template']
    opp_cache = ws['opp_cache']
    shield_scenarios = ws['shield_scenarios']

    results = {}
    n_sims = 0
    for profile_key, atk_stat, def_stat, hp_stat in profile_chunk:
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
                per_opp[(si, oi)] = result.pvpoke_score(0)
                n_sims += 1
        results[profile_key] = per_opp
    return results, n_sims


def iv_sweep(species, fast_id, charged_ids, league, shadow,
             opponents, opp_movesets, shield_scenarios, opp_iv_mode='pvpoke'):
    """
    Sim all 4096 IV spreads for one moveset against all opponents.
    Parallelized across focal stat profiles (deduped by atk/def/hp) using
    multiprocessing — IVs with identical effective stats produce identical
    battles, so we sim each profile once and copy the result to all
    matching IVs (~1.7x speedup).

    Returns (results, n_sims, canonical_scores, canonical_meta) where results
    is one dict per IV, sorted by avg_score desc.
    """
    import multiprocessing

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

    # Pre-compute IV metadata and group by stat profile (focal-side dedup)
    iv_meta = compute_iv_metadata(species, league, shadow=shadow)
    profile_to_indices, profile_data = group_ivs_by_stat_profile(iv_meta)
    profile_list = [(pk, dat[0], dat[1], dat[2]) for pk, dat in profile_data.items()]

    # Parallel sim: ~100 chunks across the worker pool. imap_unordered
    # hands chunks out as workers free up — finer granularity gives more
    # frequent progress reports and better load balancing.
    n_workers = min(multiprocessing.cpu_count(), 16)
    n_chunks_target = 100
    chunk_size = max(1, (len(profile_list) + n_chunks_target - 1) // n_chunks_target)
    chunks = [profile_list[i:i+chunk_size] for i in range(0, len(profile_list), chunk_size)]

    import time as _time
    sim_start = _time.time()
    chunk_results = []
    with multiprocessing.Pool(
        processes=n_workers,
        initializer=_sweep_worker_init,
        initargs=(species, focal_types, fm_template, cms_template,
                  opp_cache, shield_scenarios),
    ) as pool:
        last_print = sim_start
        completed = 0
        for result in pool.imap_unordered(_sweep_worker, chunks):
            chunk_results.append(result)
            completed += 1
            now = _time.time()
            if now - last_print >= 10 and completed < len(chunks):
                elapsed = now - sim_start
                frac = completed / len(chunks)
                eta = (elapsed / frac) * (1 - frac)
                print(f"      progress: {completed}/{len(chunks)} chunks "
                      f"({frac*100:.0f}%), eta {eta:.0f}s", flush=True)
                last_print = now

    # Merge profile results
    profile_per_opp = {}
    n_sims = 0
    for prof_res, chunk_sims in chunk_results:
        profile_per_opp.update(prof_res)
        n_sims += chunk_sims

    # Build per-IV results by expanding profile sims to all matching IVs.
    # The list is built in canonical iteration order (matches iv_meta order).
    n_scenarios = len(shield_scenarios)
    n_opponents = len(opp_cache)
    results = []
    for idx, meta in enumerate(iv_meta):
        pk = (round(meta['atk'], 4), round(meta['def_'], 4), int(meta['hp']))
        per_opp = profile_per_opp[pk]
        # Compute avg_score for this IV (same for all IVs sharing the profile)
        total_score = sum(per_opp.values())
        count = len(per_opp)
        avg_score = total_score / count if count else 0
        result = dict(meta)  # copy a, d, s, level, cp, atk, def_, hp, stat_product
        result['avg_score'] = avg_score
        result['per_opp'] = per_opp
        results.append(result)

    # Build canonical-order score array (in iv_meta order, same as results list)
    canonical_scores = []
    canonical_meta = []  # [(a,d,s, lv, cp, atk, def_, hp), ...]
    for r in results:
        canonical_meta.append((
            r['atk_iv'], r['def_iv'], r['sta_iv'],
            r['level'], r['cp'],
            r['atk'], r['def_'], r['hp'],
        ))
        for si in range(n_scenarios):
            for oi in range(n_opponents):
                canonical_scores.append(round(r['per_opp'][(si, oi)]))

    # Now sort and rank
    results.sort(key=lambda r: r['avg_score'], reverse=True)
    for i, r in enumerate(results):
        r['battle_rank'] = i + 1

    by_sp = sorted(results, key=lambda r: r['stat_product'], reverse=True)
    for i, r in enumerate(by_sp):
        r['sp_rank'] = i + 1

    return results, n_sims, canonical_scores, canonical_meta


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


PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"


def _plotly_script_tag(standalone):
    """Return the <script> tag for Plotly.js — CDN link or inlined source."""
    if not standalone:
        return f'<script src="{PLOTLY_CDN}"></script>'
    import urllib.request
    import ssl
    import certifi
    print("  Downloading Plotly.js for standalone HTML...")
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(PLOTLY_CDN, context=ctx) as r:
        plotly_src = r.read().decode()
    return f'<script>{plotly_src}</script>'


def generate_html(species, league, moveset_results, html_path, thresholds=None,
                  opponent_label=None, shield_scenarios=None, opponent_names=None,
                  opp_iv_mode='pvpoke', standalone=False, cli_args_str=None):
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
    for entry in moveset_results:
        fast_id, charged_ids, results = entry[0], entry[1], entry[2]
        label = moveset_label(fast_id, charged_ids)

        # Reference IV for matchup diffs: use the IV that matches the opp_iv_mode.
        # If opp_iv_mode=pvpoke, compare against PvPoke default IVs for this species.
        # If opp_iv_mode=rank1, compare against stat-product rank 1.
        ref_result = None
        if opp_iv_mode == 'rank1':
            # Rank 1 by stat product
            ref_result = min(results, key=lambda r: r['sp_rank'])
            ref_label = (f"SP Rank 1 ({ref_result['atk_iv']}/"
                         f"{ref_result['def_iv']}/{ref_result['sta_iv']})")
        else:
            # PvPoke default IVs
            _lv, da, dd, ds = pvpoke_default_ivs(species, league=league)
            for r in results:
                if (r['atk_iv'] == da and r['def_iv'] == dd
                        and r['sta_iv'] == ds):
                    ref_result = r
                    break
            ref_label = (f"Default ({da}/{dd}/{ds})"
                         if ref_result else None)
        ref_per_opp = ref_result.get('per_opp') if ref_result else None

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
    # Embed CLI invocation as an HTML comment near the top so
    # `grep '<!-- CLI:' file.html` works for forensic comparison.
    cli_comment = ''
    if cli_args_str:
        from html import escape as _esc_cmt
        cli_comment = f'<!-- CLI: {_esc_cmt(cli_args_str)} -->\n'

    html = f"""<!DOCTYPE html>
{cli_comment}<html>
<head>
<meta charset="utf-8">
<title>{species} {league.title()} League IV Deep Dive</title>
{_plotly_script_tag(standalone)}
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
    # Footer: equivalent CLI invocation, kept at the bottom so it's
    # discoverable but doesn't compete with the actual analysis content.
    if cli_args_str:
        from html import escape as _esc
        html += '<details class="meta" style="margin-top:30px;border-top:1px solid #0f3460;padding-top:10px">'
        html += '<summary>Run parameters (CLI invocation)</summary>'
        html += '<pre style="margin:8px 0;background:#16213e;'
        html += 'padding:10px;border-radius:4px;color:#e0e0e0;font-size:12px;'
        html += 'white-space:pre-wrap;word-break:break-all">'
        html += _esc(cli_args_str)
        html += '</pre></details>\n'

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
# Reference moveset resolution
# ---------------------------------------------------------------------------

def resolve_reference_moveset(species, league, shadow, ref_arg):
    """Return (fast_id, [charged_ids]) for the reference moveset, or None.

    ref_arg: 'auto' (PvPoke default), 'none' (skip), or 'FAST,CHARGED1,CHARGED2'
    """
    if ref_arg == 'none':
        return None
    if ref_arg == 'auto':
        try:
            fast, charged = get_default_moveset(species, league=league, shadow=shadow)
            return fast, charged
        except KeyError:
            print(f"  Warning: no default moveset for {species} in {league} rankings; "
                  f"skipping reference")
            return None
    # Explicit: FAST,CHARGED1,CHARGED2
    parts = [p.strip() for p in ref_arg.split(',')]
    if len(parts) == 3:
        return parts[0], parts[1:]
    sys.exit(f"--reference must be 'auto', 'none', or FAST,CHARGED1,CHARGED2, got {ref_arg!r}")


# ---------------------------------------------------------------------------
# Deep dive analysis (banding, clusters, flips, volatility)
# ---------------------------------------------------------------------------

def _pearson_r(xs, ys):
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx)**2 for x in xs))
    dy = math.sqrt(sum((y - my)**2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0


def _detect_banding(stat_values, scores, stat_name):
    """Detect banding: group IVs by discrete stat value, compute F-ratio and eta^2."""
    groups = {}
    for sv, sc in zip(stat_values, scores):
        key = int(sv) if stat_name == 'hp' else round(sv, 2)
        groups.setdefault(key, []).append(sc)
    if len(groups) < 3:
        return None
    grand_mean = sum(scores) / len(scores)
    n_total = len(scores)
    gmeans = {k: sum(v)/len(v) for k, v in groups.items()}
    ssb = sum(len(v) * (gmeans[k] - grand_mean)**2 for k, v in groups.items())
    ssw = sum(sum((x - gmeans[k])**2 for x in v) for k, v in groups.items())
    df_b, df_w = len(groups) - 1, n_total - len(groups)
    f_ratio = (ssb / df_b) / (ssw / df_w) if df_w and ssw else float('inf')
    eta_sq = ssb / (ssb + ssw) if (ssb + ssw) else 0
    sorted_keys = sorted(gmeans)
    jumps = []
    for i in range(len(sorted_keys) - 1):
        k1, k2 = sorted_keys[i], sorted_keys[i + 1]
        jumps.append((k1, k2, gmeans[k2] - gmeans[k1], len(groups[k1]), len(groups[k2])))
    jumps.sort(key=lambda x: abs(x[2]), reverse=True)
    return {'stat_name': stat_name, 'n_groups': len(groups), 'f_ratio': f_ratio,
            'eta_squared': eta_sq, 'correlation': _pearson_r(stat_values, scores),
            'top_jumps': jumps[:5], 'group_means': gmeans}


def _detect_clusters(scores, data):
    """Gap analysis: find natural breakpoints in sorted score distribution."""
    si = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ss = [scores[i] for i in si]
    gaps = [(i, ss[i-1] - ss[i]) for i in range(1, len(ss))]
    gap_vals = sorted(g[1] for g in gaps)
    med = gap_vals[len(gap_vals) // 2]
    sig = [(i, g) for i, g in gaps if g > 3 * med and i <= len(scores) // 4]
    sig.sort(key=lambda x: x[1], reverse=True)
    boundaries = sorted(set([0] + [g[0] for g in sig[:5]] + [len(scores)]))
    clusters = []
    for j in range(len(boundaries) - 1):
        s, e = boundaries[j], boundaries[j + 1]
        idx = si[s:e]
        scs = ss[s:e]
        if not scs:
            continue
        clusters.append({
            'rank_range': (s + 1, e), 'size': e - s,
            'score_range': (min(scs), max(scs)),
            'atk': (min(data['ivAtk'][i] for i in idx), sum(data['ivAtk'][i] for i in idx)/len(idx), max(data['ivAtk'][i] for i in idx)),
            'def': (min(data['ivDef'][i] for i in idx), sum(data['ivDef'][i] for i in idx)/len(idx), max(data['ivDef'][i] for i in idx)),
            'hp': (min(data['ivHp'][i] for i in idx), sum(data['ivHp'][i] for i in idx)/len(idx), max(data['ivHp'][i] for i in idx)),
            'indices': idx,
        })
    return clusters, sig[:5]


def _opp_importance(scores_flat, nIvs, nS, nO, si, top_set, opponents):
    """Rank opponents by how much they differentiate top_set from population."""
    results = []
    for oi in range(nO):
        top_avg = sum(scores_flat[iv * nS * nO + si * nO + oi] for iv in top_set) / len(top_set)
        all_avg = sum(scores_flat[iv * nS * nO + si * nO + oi] for iv in range(nIvs)) / nIvs
        results.append({'opponent': opponents[oi], 'top_avg': top_avg, 'all_avg': all_avg, 'gap': top_avg - all_avg})
    results.sort(key=lambda x: abs(x['gap']), reverse=True)
    return results


def _find_flips(scores_flat, nIvs, nS, nO, ref_iv, test_ivs, scenarios, opponents):
    """Find matchup flips (crossing 500-point boundary) for test IVs vs reference."""
    flips = {}
    for iv in test_ivs:
        if iv == ref_iv:
            continue
        gains, losses = [], []
        for si in range(nS):
            for oi in range(nO):
                rs = scores_flat[ref_iv * nS * nO + si * nO + oi]
                ts = scores_flat[iv * nS * nO + si * nO + oi]
                if (rs >= 500) != (ts >= 500):
                    entry = {'scenario': f'{scenarios[si][0]}v{scenarios[si][1]}',
                             'opponent': opponents[oi], 'ref_score': rs, 'iv_score': ts}
                    (gains if ts >= 500 else losses).append(entry)
        if gains or losses:
            flips[iv] = {'gains': gains, 'losses': losses}
    return flips


def _scenario_ranks(scores_flat, nIvs, nS, nO):
    """Compute per-scenario ranks and overall average ranks/scores."""
    scene_ranks = []
    for si in range(nS):
        ss = [sum(scores_flat[iv * nS * nO + si * nO + oi] for oi in range(nO)) for iv in range(nIvs)]
        order = sorted(range(nIvs), key=lambda i: ss[i], reverse=True)
        ranks = [0] * nIvs
        for r, idx in enumerate(order):
            ranks[idx] = r + 1
        scene_ranks.append(ranks)
    avg_scores = [sum(scores_flat[iv * nS * nO + si * nO + oi] for si in range(nS) for oi in range(nO)) / (nS * nO) for iv in range(nIvs)]
    avg_order = sorted(range(nIvs), key=lambda i: avg_scores[i], reverse=True)
    avg_ranks = [0] * nIvs
    for r, idx in enumerate(avg_order):
        avg_ranks[idx] = r + 1
    return scene_ranks, avg_ranks, avg_scores, avg_order


def _iv_label(data, iv):
    return f"{data['ivA'][iv]}/{data['ivD'][iv]}/{data['ivS'][iv]}"


def _tier_badge_html(data, iv):
    """Show badges for ALL tiers this IV meets, not just the primary one."""
    all_tiers = data.get('ivAllTiers', [])
    if iv < len(all_tiers) and all_tiers[iv]:
        badges = []
        for ti in all_tiers[iv]:
            t = data['tiers'][ti]
            badges.append(f'<span class="dd-badge" style="background:{t["color"]};color:#000">{t["name"]}</span>')
        return ' ' + ' '.join(badges)
    # Fallback to single tier
    ti = data['ivTiers'][iv]
    if ti < 0:
        return ''
    t = data['tiers'][ti]
    return f' <span class="dd-badge" style="background:{t["color"]};color:#000">{t["name"]}</span>'


def _pvp_damage(power, atk, def_, effectiveness, stab_mult):
    """PvP damage formula: floor(0.5 * 1.3 * power * atk/def * eff * stab) + 1"""
    return math.floor(0.5 * 1.3 * power * atk / def_ * effectiveness * stab_mult) + 1


def _narrate_flip(focal_atk, focal_def, focal_hp, ref_atk, ref_def, ref_hp,
                  opp_atk, opp_def, opp_name,
                  focal_moves, opp_moves,
                  focal_types, opp_types,
                  is_gain):
    """
    Identify which move's per-hit damage changed between ref and focal IV stats,
    and return a narrative string explaining *why* the flip happened.

    Only reports damage changes that explain the flip direction:
    - For gains: bulkpoints (taking less damage) or breakpoints (dealing more)
    - For losses: lost bulkpoints (taking more damage) or lost breakpoints (dealing less)

    If no per-hit damage change explains the flip, notes the HP difference
    as the likely cause.

    is_gain: True if this IV gains the matchup vs reference, False if it loses it.
    """
    favorable = []
    unfavorable = []

    # Opponent's moves hitting focal at focal_def vs ref_def (bulkpoints)
    if focal_def != ref_def:
        for move_id, power, mtype in opp_moves:
            eff = type_effectiveness(mtype, focal_types)
            stab_mult = 1.2 if mtype in opp_types else 1.0
            dmg_ref = _pvp_damage(power, opp_atk, ref_def, eff, stab_mult)
            dmg_focal = _pvp_damage(power, opp_atk, focal_def, eff, stab_mult)
            if dmg_ref != dmg_focal:
                takes_less = dmg_focal < dmg_ref
                entry = (move_id, opp_name, dmg_focal, dmg_ref, 'Def',
                         focal_def, ref_def, takes_less)
                if takes_less:  # bulkpoint gain — favorable for gaining matchups
                    favorable.append(entry)
                else:
                    unfavorable.append(entry)

    # Focal's moves hitting opp at focal_atk vs ref_atk (breakpoints)
    if focal_atk != ref_atk:
        for move_id, power, mtype in focal_moves:
            eff = type_effectiveness(mtype, opp_types)
            stab_mult = 1.2 if mtype in focal_types else 1.0
            dmg_ref = _pvp_damage(power, ref_atk, opp_def, eff, stab_mult)
            dmg_focal = _pvp_damage(power, focal_atk, opp_def, eff, stab_mult)
            if dmg_ref != dmg_focal:
                deals_more = dmg_focal > dmg_ref
                entry = (move_id, None, dmg_focal, dmg_ref, 'Atk',
                         focal_atk, ref_atk, deals_more)
                if deals_more:  # breakpoint gain — favorable
                    favorable.append(entry)
                else:
                    unfavorable.append(entry)

    # Show ALL damage changes, labeled by direction, plus HP diff.
    # This lets the user see combinations (e.g. gained a bulkpoint but lost HP).
    parts = []

    for move_id, src_name, dmg_new, dmg_old, stat, val_new, val_old, is_favorable in favorable:
        move_pretty = _pretty_name(move_id)
        if src_name:
            parts.append(f'bulkpoint: {move_pretty} from {src_name} does '
                         f'{dmg_new} instead of {dmg_old} ({stat} {val_new:.2f})')
        else:
            parts.append(f'breakpoint: {move_pretty} does '
                         f'{dmg_new} instead of {dmg_old} ({stat} {val_new:.2f})')

    for move_id, src_name, dmg_new, dmg_old, stat, val_new, val_old, is_favorable in unfavorable:
        move_pretty = _pretty_name(move_id)
        if src_name:
            parts.append(f'lost bulkpoint: {move_pretty} from {src_name} does '
                         f'{dmg_new} instead of {dmg_old} ({stat} {val_new:.2f})')
        else:
            parts.append(f'lost breakpoint: {move_pretty} does '
                         f'{dmg_new} instead of {dmg_old} ({stat} {val_new:.2f})')

    hp_diff = focal_hp - ref_hp
    if hp_diff != 0:
        parts.append(f'HP {focal_hp} vs {ref_hp} ({hp_diff:+d})')

    return '<br>'.join(parts)


def _build_move_tuples(moveset_label, fast_db, charged_db):
    """Parse moveset label into list of (move_id, power, type) tuples."""
    # Label format: "FAIRY_WIND / BULLDOZE, GIGATON_HAMMER"
    parts = moveset_label.split(' / ')
    if len(parts) != 2:
        return []
    fast_id = parts[0].strip()
    charged_ids = [c.strip() for c in parts[1].split(',')]
    moves = []
    if fast_id in fast_db:
        m = fast_db[fast_id]
        moves.append((fast_id, m['power'], m['type']))
    for cid in charged_ids:
        if cid in charged_db:
            m = charged_db[cid]
            moves.append((cid, m['power'], m['type']))
    return moves


def _pretty_name(raw_id):
    """Convert GIGATON_HAMMER to Gigaton Hammer, FAIRY_WIND to Fairy Wind, etc."""
    return raw_id.replace('_', ' ').title()


def _pretty_moveset(label):
    """Convert 'FAIRY_WIND / BULLDOZE, GIGATON_HAMMER' to pretty names."""
    parts = label.split(' / ')
    if len(parts) == 2:
        fast = _pretty_name(parts[0].strip())
        charged = ', '.join(_pretty_name(c.strip()) for c in parts[1].split(','))
        return f'{fast} / {charged}'
    return label


def _prose_flip_summary(flip_data, max_gains=3, max_losses=2):
    """Generate a natural-language summary of matchup gains/losses.

    Returns a string like "gains Togekiss 1v2, G. Stunfisk 2v0; loses Steelix 0v2, 1v2"
    """
    parts = []
    gains = flip_data.get('gains', [])
    losses = flip_data.get('losses', [])
    if gains:
        # Sort by delta descending
        top = sorted(gains, key=lambda e: e['iv_score'] - e['ref_score'], reverse=True)[:max_gains]
        gain_strs = [f'{e["opponent"]} {e["scenario"]}' for e in top]
        extra = len(gains) - len(top)
        s = 'gains ' + ', '.join(gain_strs)
        if extra > 0:
            s += f' (+{extra} more)'
        parts.append(s)
    if losses:
        top = sorted(losses, key=lambda e: e['ref_score'] - e['iv_score'], reverse=True)[:max_losses]
        loss_strs = [f'{e["opponent"]} {e["scenario"]}' for e in top]
        extra = len(losses) - len(top)
        s = 'loses ' + ', '.join(loss_strs)
        if extra > 0:
            s += f' (+{extra} more)'
        parts.append(s)
    return '; '.join(parts) if parts else 'no matchup flips'


def _aggregate_flips_by_anchor(scores_flat, nIvs, nS, nO,
                                resolved_anchors, data_obj, scenarios, opponents,
                                win_threshold=500,
                                pass_winrate_min=0.75, fail_winrate_max=0.25,
                                debug_stats=None):
    """Find shield scenarios in which a named anchor cleanly partitions
    matchup wins/losses against the anchor's named opponent.

    For each ResolvedAnchor with an opponent set, partition all IVs into
    pass/fail by ``anchor.passes(focal_atk, focal_def)``. For each shield
    scenario, check whether passing IVs ~always win the matchup vs that
    opponent and failing IVs ~always lose it (or the symmetric case for
    a "lost matchup" anchor — currently we only emit the gain direction).

    Returns a list of records:
        {
          'anchor': ResolvedAnchor,
          'opponent': str,
          'scenarios': [(shields_focal, shields_opp), ...],
          'direction': 'gain',  # passing IVs win, failing IVs lose
        }

    Anchors with no opponent, anchors where everyone or no one passes, and
    anchors where no scenario meets the cleanliness thresholds are skipped.
    """
    # Build case-insensitive opponent index lookup so TOML and opponent-list
    # naming differences (Annihilape vs annihilape) don't silently drop hits.
    opp_idx_by_name = {}
    for oi, name in enumerate(opponents):
        opp_idx_by_name[name] = oi
        opp_idx_by_name[name.lower()] = oi

    # Counters so callers can diagnose why an anchor list produced few bullets.
    stats = {
        'considered': 0, 'no_opponent': 0, 'unknown_opponent': 0,
        'trivial_partition': 0, 'no_clean_scenario': 0, 'emitted': 0,
    }

    records = []
    for anchor in resolved_anchors:
        stats['considered'] += 1
        if not anchor.opponent:
            stats['no_opponent'] += 1
            continue
        oi = opp_idx_by_name.get(anchor.opponent)
        if oi is None:
            oi = opp_idx_by_name.get(anchor.opponent.lower())
        if oi is None:
            stats['unknown_opponent'] += 1
            continue

        passing = []
        failing = []
        for iv in range(nIvs):
            atk = data_obj['ivAtk'][iv]
            def_ = data_obj['ivDef'][iv]
            if anchor.passes(atk, def_):
                passing.append(iv)
            else:
                failing.append(iv)
        if not passing or not failing:
            stats['trivial_partition'] += 1
            continue  # anchor isn't a real partition for this cohort

        flipped_scenarios = []
        for si in range(nS):
            pass_wins = sum(
                1 for iv in passing
                if scores_flat[iv * nS * nO + si * nO + oi] >= win_threshold
            ) / len(passing)
            fail_wins = sum(
                1 for iv in failing
                if scores_flat[iv * nS * nO + si * nO + oi] >= win_threshold
            ) / len(failing)
            if pass_wins >= pass_winrate_min and fail_wins <= fail_winrate_max:
                flipped_scenarios.append(scenarios[si])

        if flipped_scenarios:
            stats['emitted'] += 1
            records.append({
                'anchor': anchor,
                'opponent': anchor.opponent,
                'scenarios': flipped_scenarios,
                'direction': 'gain',
                # Canonical IV indices that pass this anchor. Used by
                # the interactive scatter plot's anchor-clear overlay
                # to highlight which spreads actually clear an emitted
                # anchor (separate from the bullet text rendering).
                'passing_ivs': list(passing),
            })
        else:
            stats['no_clean_scenario'] += 1

    if debug_stats is not None:
        debug_stats.update(stats)
    return records


def _render_anchor_flip_bullets(records):
    """Render anchor-flip records as RyanSwag-style HTML <li> bullets.

    Grouping grain is ``(parent, opponent, target_stat, move_id)``.
    Within each group we take the *minimum* threshold value: Level 3
    parents expand into one sub-anchor per (move, damage tier), and a
    higher-tier sub-anchor is automatically subsumed by its lower-tier
    sibling for matchup-flipping purposes (anything that crosses the
    high tier necessarily crosses the low one). The min threshold is
    "the smallest stat at which this move starts driving any flip
    against this opponent" — the actionable number.

    Result: one bullet per (parent, opponent, move) triple, e.g.
        "96.62 Def for lickilicky bulk (Hyper Beam) vs Lickilicky (0v1, 1v2)"
    Sub-anchors with no ``move_id`` (Level 1/2 anchors) keep their
    own bullet and omit the move parenthetical entirely.

    Bullets are sorted within each (parent, opponent) family by
    threshold ascending so increasing-stat bulkpoints read top-to-bottom
    in the order a player would clear them.
    """
    # Group: (parent, opponent, target_stat, move_id) -> list of records.
    groups: dict = {}
    order: list = []  # preserve first-seen order for stable output
    for rec in records:
        a = rec['anchor']
        key = (a.parent, rec['opponent'], a.target_stat, a.move_id)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(rec)

    # Sort groups within each (parent, opponent) family by min threshold
    # so a parent with multiple moves reads in ascending stat order.
    def _group_sort_key(key):
        recs = groups[key]
        min_thresh = min(r['anchor'].threshold_value for r in recs)
        # Primary: parent+opponent groups stay together (preserve original
        # first-seen order via index). Secondary: ascending threshold.
        return (order.index(key) // 1000, key[0], key[1], min_thresh)
    # Stable group ordering: keep parents+opponents in original first-seen
    # order, then sort within by min threshold. Use a two-pass approach
    # so different parents/opponents don't interleave.
    family_order: list = []
    families: dict = {}
    for key in order:
        family = (key[0], key[1], key[2])  # parent, opponent, target_stat
        if family not in families:
            families[family] = []
            family_order.append(family)
        families[family].append(key)
    for family in family_order:
        families[family].sort(
            key=lambda k: min(r['anchor'].threshold_value for r in groups[k])
        )

    lines = []
    for family in family_order:
        for key in families[family]:
            recs = groups[key]
            first = recs[0]['anchor']
            stat_label = 'Atk' if first.target_stat == 'atk' else 'Def'
            anchor_label = first.parent_display_name or first.label or first.parent

            min_thresh = min(r['anchor'].threshold_value for r in recs)

            move_str = ''
            if first.move_id:
                move_str = f' ({_pretty_name(first.move_id)})'

            # Scenarios: union across sub-anchors of the same group
            # (different damage tiers of the same move usually flip
            # the same scenarios, but if they diverge we show all).
            scen_set = set()
            for r in recs:
                for s in r['scenarios']:
                    scen_set.add(tuple(s))
            scen_strs = ', '.join(f'{s[0]}v{s[1]}' for s in sorted(scen_set))

            lines.append(
                f'<li><span class="dd-strong">{min_thresh:.2f} {stat_label}</span> '
                f'for <b>{anchor_label}</b>{move_str} vs {recs[0]["opponent"]} '
                f'(<span class="dd-gain">{scen_strs}</span>)</li>'
            )
    return lines


def _generate_threshold_descriptions(flips, data, avg_scores, ranked, opp_iv_mode):
    """Generate HSH/RyanSwag-style threshold descriptions from flip data.

    Returns list of HTML paragraphs describing key stat thresholds with
    matchup justification.
    """
    # Collect all unique (opponent, scenario) flips across IVs and find
    # which stat change drives the flip
    opp_label = 'PvPoke default' if opp_iv_mode == 'pvpoke' else 'rank 1'

    # Group flips by opponent+scenario to find common themes
    opp_scene_gains = {}  # (opp, scene) -> list of (iv, delta)
    opp_scene_losses = {}
    for iv, fd in flips.items():
        for e in fd['gains']:
            key = (e['opponent'], e['scenario'])
            opp_scene_gains.setdefault(key, []).append((iv, e['iv_score'] - e['ref_score']))
        for e in fd['losses']:
            key = (e['opponent'], e['scenario'])
            opp_scene_losses.setdefault(key, []).append((iv, e['ref_score'] - e['iv_score']))

    lines = []

    # Attack thresholds: flips where higher-atk IVs gain matchups
    # Defense/HP thresholds: flips where higher-bulk IVs gain matchups
    # We identify these by checking the stat profile of IVs that gain vs lose

    # Most common gain matchups (by how many IVs gain them)
    gain_counts = sorted(opp_scene_gains.items(), key=lambda x: len(x[1]), reverse=True)
    for (opp, scene), iv_deltas in gain_counts[:6]:
        n = len(iv_deltas)
        avg_delta = sum(d for _, d in iv_deltas) / n
        # What stat distinguishes IVs that get this gain?
        gain_ivs = [iv for iv, _ in iv_deltas]
        gain_atk = sum(data['ivAtk'][iv] for iv in gain_ivs) / len(gain_ivs)
        gain_def = sum(data['ivDef'][iv] for iv in gain_ivs) / len(gain_ivs)
        gain_hp = sum(data['ivHp'][iv] for iv in gain_ivs) / len(gain_ivs)
        pop_atk = sum(data['ivAtk'][iv] for iv in ranked[:50]) / 50
        pop_def = sum(data['ivDef'][iv] for iv in ranked[:50]) / 50
        pop_hp = sum(data['ivHp'][iv] for iv in ranked[:50]) / 50

        # Which stat differs most?
        diffs = [('Atk', gain_atk - pop_atk, gain_atk),
                 ('Def', gain_def - pop_def, gain_def),
                 ('HP', gain_hp - pop_hp, gain_hp)]
        dominant = max(diffs, key=lambda x: abs(x[1]))

        if abs(dominant[1]) < 0.5 and dominant[0] != 'HP':
            stat_note = ''
        elif dominant[1] > 0:
            stat_note = f' (favors higher {dominant[0]}, avg {dominant[2]:.1f})'
        else:
            stat_note = f' (favors lower {dominant[0]}, avg {dominant[2]:.1f})'

        lines.append(
            f'<li><b>{opp} {scene}</b> &mdash; '
            f'{n} of top IVs gain this matchup vs {opp_label} opponent '
            f'(avg +{avg_delta:.0f} score){stat_note}</li>'
        )

    # Most common loss matchups
    loss_counts = sorted(opp_scene_losses.items(), key=lambda x: len(x[1]), reverse=True)
    if loss_counts:
        lines.append('<li class="dd-loss-item"><b>Common losses:</b> ')
        loss_parts = []
        for (opp, scene), iv_deltas in loss_counts[:4]:
            n = len(iv_deltas)
            loss_parts.append(f'{opp} {scene} ({n} IVs)')
        lines.append(', '.join(loss_parts) + '</li>')

    return lines


def generate_analysis_sections(data_obj, score_arrays, moveset_idx, opp_iv_mode,
                               shield_scenarios, opponent_names,
                               slayer_iter_result=None):
    """Generate the full analysis HTML for injection into the interactive page.

    Returns (css_str, results_html_str, analysis_html_str).
    results_html is always visible ("Deep Dive Results").
    analysis_html goes behind the toggle ("Deep Dive Analysis").
    """
    nIvs = data_obj['nIvs']
    nS = data_obj['nScenarios']
    nO = data_obj['nOpponents']
    scenarios = [tuple(s) for s in data_obj['scenarios']]
    opponents = opponent_names or data_obj.get('opponents', [])
    score_key = f'{moveset_idx}_{opp_iv_mode}'
    scores_flat = score_arrays.get(score_key, [])
    if not scores_flat:
        return '', '', '<!-- analysis: no scores available -->'
    moveset_label = data_obj['movesets'][moveset_idx]['label']
    ref_iv = data_obj['pvpokeRefIvIdx']
    if ref_iv < 0:
        ref_iv = 0

    print("  Generating analysis sections...")

    # Resolved anchors are needed by both the slayer-iteration block (much
    # further down) and the new anchor-driven matchup-flip section (rendered
    # right after Key Matchup Thresholds). Extract once here.
    resolved_anchors_top = []
    if slayer_iter_result:
        resolved_anchors_top = slayer_iter_result.get('resolved_anchors', []) or []

    # Set up breakpoint narration: load move data, species types, opponent info
    fast_db, charged_db = get_moves()
    gm = load_gamemaster()
    focal_entry = next((m for m in gm['pokemon']
                        if m['speciesName'] == data_obj.get('species', '')), None)
    focal_types = parse_types(focal_entry) if focal_entry else []
    focal_moves = _build_move_tuples(moveset_label, fast_db, charged_db)

    # Cache opponent info for narration: {name: (atk, def, types, moves)}
    opp_info_cache = {}
    league = data_obj.get('league', 'great')
    for opp_name in opponents:
        try:
            opp_clean = opp_name
            opp_is_shadow = '_shadow' in opp_name.lower().replace(' ', '_')
            oa, od, os_ = resolve_opp_ivs(opp_clean, league, opp_is_shadow, opp_iv_mode)
            opp_pokemon = Pokemon.at_best_level(opp_clean, oa, od, os_,
                                                league=league, shadow=opp_is_shadow)
            opp_entry = next((m for m in gm['pokemon']
                              if m['speciesName'] == opp_clean), None)
            opp_types = parse_types(opp_entry) if opp_entry else []
            # Get opponent's default moveset moves
            try:
                opp_fast, opp_charged = get_default_moveset(opp_clean, league=league,
                                                            shadow=opp_is_shadow)
                opp_moves_list = []
                if opp_fast in fast_db:
                    fm = fast_db[opp_fast]
                    opp_moves_list.append((opp_fast, fm['power'], fm['type']))
                for cid in opp_charged:
                    if cid in charged_db:
                        cm = charged_db[cid]
                        opp_moves_list.append((cid, cm['power'], cm['type']))
            except (KeyError, ValueError):
                opp_moves_list = []
            opp_info_cache[opp_name] = {
                'atk': opp_pokemon.atk, 'def_': opp_pokemon.def_,
                'types': opp_types, 'moves': opp_moves_list,
            }
        except Exception:
            pass  # skip opponents we can't resolve

    ref_atk = data_obj['ivAtk'][ref_iv]
    ref_def = data_obj['ivDef'][ref_iv]

    scene_ranks, avg_ranks, avg_scores, ranked = _scenario_ranks(scores_flat, nIvs, nS, nO)

    # ---- CSS ----
    css = """
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
.dd-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.75rem; font-weight: 600; }
.dd-methods-dl { margin: 8px 0; }
.dd-methods-dl dt { color: #58a6ff; font-weight: 600; margin-top: 8px; }
.dd-methods-dl dd { margin-left: 16px; font-size: 0.88rem; color: #aaa; }
.dd-flip-detail { margin: 6px 0; }
.dd-flip-detail summary { cursor: pointer; padding: 4px 0; font-size: 0.9rem; }
.dd-flip-detail summary:hover { color: #58a6ff; }
.dd-rec-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr)); gap: 12px; margin: 12px 0; }
.dd-rec-card { background: #0f3460; border: 1px solid #1a3a6e; border-radius: 6px; padding: 12px; }
.dd-rec-card h4 { color: #e94560; margin: 0 0 6px; font-size: 1rem; }
.dd-rec-card p { margin: 3px 0; font-size: 0.88rem; }
.dd-prose { font-size: 0.88rem; color: #b0b8c4; margin: 4px 0 8px 0; font-style: italic; }
.dd-threshold-list { list-style: none; padding: 0; margin: 8px 0; }
.dd-threshold-list li { padding: 4px 0 4px 12px; border-left: 2px solid #0f3460; margin: 4px 0; font-size: 0.88rem; }
.dd-threshold-list .dd-loss-item { border-left-color: #f85149; }
.dd-opp-label { color: #8b949e; font-size: 0.75rem; }
.dd-slayer-top td { background: #1e2d4a; }
.dd-slayer-top td:first-child { border-left: 3px solid #58a6ff; }
.dd-slayer-hidden { display: none; }
.dd-slayer-hidden.dd-slayer-shown { display: table-row; }
.dd-slayer-toggle { background:#0f3460; color:#58a6ff; border:1px solid #1a3a6e;
  padding:4px 10px; border-radius:4px; cursor:pointer; font-size:0.8rem;
  margin-top:4px; }
.dd-slayer-toggle:hover { background:#1a3a6e; color:#fff; }
.dd-anchor-tag { display:inline-block; background:#0f3460; color:#58a6ff;
  padding:1px 6px; border-radius:3px; font-size:0.72rem; margin:1px 2px 1px 0;
  font-family:monospace; cursor:help; }
.dd-anchor-tag:hover { background:#1a3a6e; color:#fff; }
.dd-anchor-tag-count { color:#d29922; font-weight:600; }
.dd-anchor-tags-cell { max-width: 480px; }
.dd-anchor-tags-cell .dd-anchor-tag { vertical-align: baseline; }
/* The badges live inside an inner <div> rather than directly in the <td>
   because <td> uses display: table-cell, which silently ignores max-height
   in every major browser. Capping the cell to ~2 lines requires a real
   block-level wrapper. The wrapper itself is click-toggleable: clicking
   anywhere on the cell whitespace flips that one cell between compact
   and expanded; clicking a specific badge triggers its hover tooltip
   instead (badges keep cursor:help to signal hover-only). */
.dd-anchor-tags-inner { white-space: normal; line-height: 1.5;
  cursor: pointer; }
/* Compact mode: cap tag cells at ~2 lines so survivor rows stay readable.
   The "Expand all tags" toggle in the slayer section header removes this
   class from every inner div to reveal the full badge wall. */
.dd-anchor-tags-inner.dd-tags-compact { max-height: 3em; overflow: hidden;
  position: relative; }
.dd-anchor-tags-inner.dd-tags-compact::after { content: ""; position: absolute;
  bottom: 0; left: 0; right: 0; height: 1.5em; pointer-events: none;
  background: linear-gradient(transparent, #16213e); }
.dd-tags-toggle { background:#0f3460; color:#58a6ff; border:1px solid #1a3a6e;
  padding:4px 10px; border-radius:4px; cursor:pointer; font-size:0.8rem;
  margin:6px 0; }
.dd-tags-toggle:hover { background:#1a3a6e; color:#fff; }
.dd-filter-hidden { display: none !important; }
.dd-filter-toggle { background:#0f3460; color:#58a6ff; border:1px solid #1a3a6e;
  padding:4px 10px; border-radius:4px; cursor:pointer; font-size:0.8rem;
  margin:6px 0 4px 0; }
.dd-filter-toggle:hover { background:#1a3a6e; color:#fff; }
.dd-filter-panel { background:#0a1a30; border:1px solid #1a3a6e; border-radius:4px;
  padding:8px 10px; margin:4px 0 8px 0; font-size:0.78rem; }
.dd-filter-panel-group { margin-bottom:6px; padding-bottom:4px;
  border-bottom:1px solid #16213e; }
.dd-filter-panel-group:last-child { border-bottom:none; }
.dd-filter-master { font-weight:600; color:#58a6ff; display:block; }
.dd-filter-children { margin:2px 0 0 18px; display:flex; flex-wrap:wrap;
  gap:4px 10px; }
.dd-filter-children label { font-family:monospace; font-size:0.72rem;
  color:#b0b8c4; cursor:pointer; }
.dd-filter-children label:hover { color:#fff; }
.dd-filter-controls { margin-top:6px; padding-top:6px; border-top:1px solid #16213e;
  display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
.dd-filter-controls button { background:#1a3a6e; color:#fff; border:none;
  padding:3px 8px; border-radius:3px; cursor:pointer; font-size:0.75rem; }
.dd-filter-controls button:hover { background:#264a8a; }
.dd-filter-status { color:#8b949e; font-size:0.72rem; margin-left:auto; }
.dd-auto-marker { color:#d29922; font-size:0.7rem; font-weight:400;
  font-style:italic; }
"""

    opp_label = 'PvPoke default' if opp_iv_mode == 'pvpoke' else 'rank 1'

    # ======== RESULTS (always visible — "Deep Dive Results") ========
    results_parts = []

    # ---- Compute flips (needed by both results and analysis) ----
    test_set = set(ranked[:10])
    for iv in range(nIvs):
        if data_obj['ivTiers'][iv] >= 0:
            test_set.add(iv)
    test_set.discard(ref_iv)
    flips = _find_flips(scores_flat, nIvs, nS, nO, ref_iv, sorted(test_set), scenarios, opponents)
    flip_summary = [(iv, len(f['gains']), len(f['losses']), len(f['gains']) - len(f['losses'])) for iv, f in flips.items()]
    flip_summary.sort(key=lambda x: (-x[3], -x[1]))
    flip_map = {iv: (g, l, net) for iv, g, l, net in flip_summary}
    hp_list = [data_obj['ivHp'][i] for i in range(nIvs)]

    # ======== Build recommendation candidates ========
    rec_candidates = []
    for iv in ranked[:50]:
        g, l, net = flip_map.get(iv, (0, 0, 0))
        rng = max(scene_ranks[si][iv] for si in range(nS)) - min(scene_ranks[si][iv] for si in range(nS))
        score = -avg_ranks[iv] + net * 3 - rng * 0.001
        rec_candidates.append({'iv': iv, 'avg_rank': avg_ranks[iv], 'avg_score': avg_scores[iv],
                                'gains': g, 'losses': l, 'net': net, 'range': rng, 'score': score})
    rec_candidates.sort(key=lambda x: x['score'], reverse=True)

    # Assign descriptive tier names based on stat profile
    for rc in rec_candidates:
        iv = rc['iv']
        atk, def_, hp = data_obj['ivAtk'][iv], data_obj['ivDef'][iv], data_obj['ivHp'][iv]
        pop_atk = sum(data_obj['ivAtk'][i] for i in ranked[:20]) / 20
        pop_def = sum(data_obj['ivDef'][i] for i in ranked[:20]) / 20
        pop_hp = sum(data_obj['ivHp'][i] for i in ranked[:20]) / 20
        if atk > pop_atk + 0.5:
            rc['style'] = 'Attack Weight'
        elif def_ > pop_def + 2:
            rc['style'] = 'High Defense'
        elif hp > pop_hp + 2:
            rc['style'] = 'High HP'
        elif rc['net'] > 5:
            rc['style'] = 'Matchup Hunter'
        elif rc['range'] < 500:
            rc['style'] = 'Generalist'
        else:
            rc['style'] = 'Balanced'

    # ======== RESULTS section (always visible) ========

    # -- IV Recommendations --
    results_parts.append(f'<div class="dd-section" id="dd-recommendations">\n')
    results_parts.append(f'<h2 class="dd-h2">Deep Dive Results</h2>\n')
    results_parts.append(f'<p>Recommendations based on average score, matchup flips, and rank stability '
                         f'vs {opp_label} opponents. Moveset: {_pretty_moveset(moveset_label)}.</p>\n')

    results_parts.append('<div class="dd-rec-grid">\n')
    for i, rc in enumerate(rec_candidates[:3]):
        iv = rc['iv']
        nc = 'dd-gain' if rc['net'] > 0 else ('dd-loss' if rc['net'] < 0 else '')
        fd = flips.get(iv, {'gains': [], 'losses': []})
        prose = _prose_flip_summary(fd, max_gains=2, max_losses=1)
        results_parts.append(f'<div class="dd-rec-card">\n')
        results_parts.append(f'<h4>{rc["style"]}: {_iv_label(data_obj, iv)}{_tier_badge_html(data_obj, iv)}</h4>\n')
        results_parts.append(f'<p>Atk={data_obj["ivAtk"][iv]:.2f}, Def={data_obj["ivDef"][iv]:.2f}, HP={data_obj["ivHp"][iv]}, SP #{data_obj["spRanks"][iv]}</p>\n')
        results_parts.append(f'<p>Avg score rank: <b>#{rc["avg_rank"]}</b> ({rc["avg_score"]:.1f})</p>\n')
        results_parts.append(f'<p>Flips vs {opp_label} ref: <span class="dd-gain">+{rc["gains"]}</span>/<span class="dd-loss">-{rc["losses"]}</span> = <span class="{nc}"><b>{rc["net"]:+d}</b></span></p>\n')
        results_parts.append(f'<p class="dd-prose">{prose}</p>\n')
        # Breakpoint narrations for top gains/losses
        focal_atk_rc = data_obj['ivAtk'][iv]
        focal_def_rc = data_obj['ivDef'][iv]
        focal_hp_rc = data_obj['ivHp'][iv]
        ref_hp_val = data_obj['ivHp'][ref_iv]
        bp_lines = []
        for is_gain, entries in [(True, fd.get('gains', [])[:2]), (False, fd.get('losses', [])[:1])]:
            for e in entries:
                opp_name = e['opponent']
                if opp_name in opp_info_cache and focal_moves:
                    oi = opp_info_cache[opp_name]
                    narr = _narrate_flip(
                        focal_atk_rc, focal_def_rc, focal_hp_rc,
                        ref_atk, ref_def, ref_hp_val,
                        oi['atk'], oi['def_'], opp_name,
                        focal_moves, oi['moves'],
                        focal_types, oi['types'],
                        is_gain=is_gain,
                    )
                    if narr:
                        bp_lines.append(narr)
        if bp_lines:
            results_parts.append(f'<p class="dd-small"><b style="color:#58a6ff">Key changes</b><br>{"<br>".join(bp_lines)}</p>\n')
        results_parts.append('</div>\n')
    results_parts.append('</div>\n')

    # -- Threshold tier summary (all tiers, including empty ones) --
    if data_obj.get('tiers'):
        results_parts.append('<h3 class="dd-h3">Threshold Tier Summary</h3>\n')
        for ti, t in enumerate(data_obj['tiers']):
            tier_ivs = [iv for iv in range(nIvs) if data_obj['ivTiers'][iv] == ti]
            results_parts.append(f'<div class="dd-callout">\n')
            results_parts.append(f'<b><span class="dd-badge" style="background:{t["color"]};color:#000">{t["name"]}</span></b> '
                                 f'({t["desc"]})')
            if not tier_ivs:
                # (#1/#11) Show tiers even when empty, explain why
                # Count IVs that meet this threshold ignoring tier priority
                all_meeting = 0
                for iv in range(nIvs):
                    meets = True
                    if t.get('attack', 0) > 0 and data_obj['ivAtk'][iv] < t['attack']:
                        meets = False
                    if t.get('defense', 0) > 0 and data_obj['ivDef'][iv] < t['defense']:
                        meets = False
                    if t.get('stamina', 0) > 0 and data_obj['ivHp'][iv] < t['stamina']:
                        meets = False
                    if meets:
                        all_meeting += 1
                if all_meeting > 0:
                    results_parts.append(f' &mdash; {all_meeting} IV spreads meet these stats, '
                                         f'but all also qualify for a more restrictive tier above')
                else:
                    results_parts.append(f' &mdash; 0 IV spreads can reach these stats at this CP cap')
            else:
                results_parts.append(f' &mdash; {len(tier_ivs)} IV spreads qualify')
                best_in_tier = max(tier_ivs, key=lambda iv: flip_map.get(iv, (0, 0, 0))[2])
                g, l, net = flip_map.get(best_in_tier, (0, 0, 0))
                fd = flips.get(best_in_tier, {'gains': [], 'losses': []})
                prose = _prose_flip_summary(fd, max_gains=2, max_losses=1)
                results_parts.append(f'<br>Best in tier: <b>{_iv_label(data_obj, best_in_tier)}</b> '
                                     f'(avg #{avg_ranks[best_in_tier]}, net flips {net:+d})')
                results_parts.append(f'<br><span class="dd-prose">{prose}</span>')
            results_parts.append('\n</div>\n')

    # -- Key Matchup Thresholds --
    threshold_descs = _generate_threshold_descriptions(flips, data_obj, avg_scores, ranked, opp_iv_mode)
    if threshold_descs:
        results_parts.append(f'<h3 class="dd-h3">Key Matchup Thresholds</h3>\n')
        results_parts.append(f'<p>Matchups that flip vs {opp_label} opponents, '
                             f'ordered by how many top IVs benefit:</p>\n')
        results_parts.append('<ul class="dd-threshold-list">\n')
        results_parts.append('\n'.join(threshold_descs))
        results_parts.append('\n</ul>\n')

    # -- Anchor-Driven Matchup Flips (RyanSwag-style, phase 1) --
    # New aggregator: groups shield scenarios under each named anchor +
    # opponent so the bullets read like the GamePress IV deep dives.
    # Lives alongside the heuristic Key Matchup Thresholds section above
    # for at least one session — different lens on the same flip data,
    # decide later whether to merge or replace.
    if resolved_anchors_top:
        anchor_flip_debug = {}
        anchor_flip_records = _aggregate_flips_by_anchor(
            scores_flat, nIvs, nS, nO,
            resolved_anchors_top, data_obj, scenarios, opponents,
            debug_stats=anchor_flip_debug,
        )
        print(f"  Anchor-flip aggregator: {anchor_flip_debug}")
        if anchor_flip_records:
            anchor_bullets = _render_anchor_flip_bullets(anchor_flip_records)
            results_parts.append('<h3 class="dd-h3">Anchor-Driven Matchup Flips</h3>\n')
            results_parts.append(
                '<p>Named anchors (from <code>thresholds/*.toml</code> or the '
                'auto-fallback layer) that cleanly partition matchup wins/losses '
                f'against their opponent. Each bullet lists the shield scenarios '
                f'in which IVs clearing the anchor reliably win and IVs failing '
                f'it reliably lose. Vs {opp_label} opponents.</p>\n'
            )
            results_parts.append(
                '<p class="dd-small">Format: <em>threshold</em> for <em>anchor name</em> '
                'vs <em>opponent</em> (<em>shield scenarios where the partition holds</em>). '
                'Bait/farm and move-restriction dimensions are not yet swept — '
                'see TODO &ldquo;Baiting policy as a deep-dive sim axis&rdquo;.</p>\n'
            )
            results_parts.append('<ul class="dd-threshold-list">\n')
            results_parts.append('\n'.join(anchor_bullets))
            results_parts.append('\n</ul>\n')

    # -- Mirror Slayer Iteration --
    if slayer_iter_result and slayer_iter_result.get('final'):
        results_parts.append(f'<h3 class="dd-h3">Mirror Slayer Iteration</h3>\n')
        metric_label = slayer_iter_result.get('metric', 'all')
        max_rounds_arg = slayer_iter_result.get('max_rounds_arg', 4)
        metric_explain = {
            'all': 'all 9 shield scenarios count toward win totals',
            'even': 'only even shields (0v0/1v1/2v2) count toward win totals',
            'even-strict': 'only IVs that win ALL three even shields against an opponent get credit',
        }.get(metric_label, '')
        results_parts.append(f'<p>Nash-style iterative discovery of IVs that beat the '
                             f'{data_obj.get("species", "mirror")} mirror match. '
                             f'Each round tests focal IVs against the previous round\'s top winners. '
                             f'Survivors are classified into RyanSwag\'s three patterns.</p>\n')
        results_parts.append(f'<p class="dd-small"><b>Metric:</b> <code>{metric_label}</code> '
                             f'({metric_explain}) | <b>Max rounds:</b> {max_rounds_arg}</p>\n')
        rounds_run = slayer_iter_result.get('rounds_run', 0)
        converged = slayer_iter_result.get('converged', False)
        results_parts.append(f'<p class="dd-small">{rounds_run} rounds run '
                             f'({"converged" if converged else "max rounds reached"}). '
                             f'{slayer_iter_result.get("cache_stats", "")}</p>\n')

        # Per-round summary table
        history = slayer_iter_result.get('history', [])
        if history:
            results_parts.append('<table class="dd-table dd-narrow">\n')
            results_parts.append('<tr><th>Round</th><th>Survivors</th><th>Max Wins</th><th>Top Avg Score</th></tr>\n')
            for ri, top in enumerate(history):
                if not top:
                    continue
                results_parts.append(f'<tr><td>{ri}</td><td>{len(top)}</td>'
                                     f'<td>{top[0]["total_wins"]}</td>'
                                     f'<td>{top[0]["avg_score"]:.1f}</td></tr>\n')
            results_parts.append('</table>\n')

        # Categorized survivors
        categories = slayer_iter_result.get('categories', {})
        resolved_anchors = slayer_iter_result.get('resolved_anchors', []) or []

        # Summarize resolved anchors (for the intro paragraph and
        # Level 3 sub-anchor distribution report).
        anchor_parents: dict[str, list] = {}
        for a in resolved_anchors:
            anchor_parents.setdefault(a.parent, []).append(a)

        CATEGORY_DESCRIPTIONS = {
            'Atk Slayer': 'IVs that clear at least one named damage '
                          'breakpoint against a notable opponent. Membership '
                          'is binary per breakpoint: an IV is in this '
                          'category iff its effective attack reaches the '
                          'minimum needed to deal one extra damage with some '
                          'move against some named opponent &mdash; not just '
                          '&ldquo;has higher attack than other survivors.&rdquo; '
                          'Each row&rsquo;s Tags column lists the specific '
                          'breakpoint(s) cleared (hover for the move&nbsp;+&nbsp;'
                          'tier detail). <strong>Hidden if no survivor '
                          'clears any named breakpoint</strong> &mdash; an '
                          'empty Atk Slayer box means no anchors fired '
                          'against the current opponent set.',
            'Bulk Slayer': 'IVs that either (a) have HP and defense both at '
                           'or above the survivor-pool median (structural '
                           'high-bulk pool, always shown) <strong>or</strong> '
                           '(b) clear at least one named <em>bulkpoint</em> '
                           'anchor against a notable opponent &mdash; '
                           'reaching a defense tier at which one of the '
                           'opponent&rsquo;s threat moves deals strictly '
                           'less damage to the focal. Each row&rsquo;s Tags '
                           'column shows which bulkpoint(s) the IV clears '
                           '(badges with the &ldquo;b&rdquo; suffix or '
                           '&ldquo;&uarr;&rdquo; reference markers); hover '
                           'for the move&nbsp;+&nbsp;damage&nbsp;tier '
                           'detail. The structural pool is the default '
                           'fallback when no bulkpoint anchors are '
                           'configured for the species.',
            'CMP Slayer': 'IVs whose raw attack beats at least one named '
                          'CMP anchor (e.g., the max attack of a reference '
                          'cohort). Wins Charge Move Priority against the '
                          'cohort when both fire a charged move on the same '
                          'turn. <strong>Hidden if no survivor clears any '
                          'CMP anchor</strong>.',
        }

        if categories:
            # Build a map of IV -> set of non-empty categories it appears in
            iv_categories = {}
            for cat_name, cat_ivs in categories.items():
                if not cat_ivs:
                    continue
                for r in cat_ivs:
                    iv_categories.setdefault(r['iv'], set()).add(cat_name)

            if resolved_anchors:
                n_parents = len(anchor_parents)
                n_subs = len(resolved_anchors)
                results_parts.append(
                    f'<p class="dd-small">Each survivor is tagged with the '
                    f'set of named anchors it passes. {n_parents} parent '
                    f'anchor(s) resolved to {n_subs} concrete threshold '
                    f'check(s) — Level&nbsp;3 discover-mode anchors expand '
                    f'into a family of sub-anchors (one per discovered '
                    f'(move,&nbsp;tier) breakpoint). See the Tags column in '
                    f'each category for per-IV detail. IVs that fit '
                    f'<em>multiple</em> categories are marked with extra '
                    f'cross-category badges.</p>\n'
                )
            else:
                results_parts.append(
                    '<p class="dd-small">No named anchors are configured '
                    'for this species/league (or none resolved against the '
                    'survivor cohort). Atk Slayer and CMP Slayer will be '
                    'empty; Bulk Slayer remains as a structural '
                    'HP+def-above-median view. Add anchors to the species '
                    '<code>thresholds/*.toml</code> file to enable '
                    'breakpoint-based categorization.</p>\n'
                )

            # JS for the filter panel — defined once, used by all cards.
            results_parts.append("""<script>
function ddSlayerApplyFilter(cardId) {
  var table = document.getElementById(cardId + '-table');
  if (!table) return;
  var checked = new Set();
  document.querySelectorAll('.dd-anchor-cb[data-card="' + cardId + '"]:checked').forEach(function(cb) {
    checked.add(cb.getAttribute('data-anchor-idx'));
  });
  var showAllCb = document.querySelector('.dd-show-all-mons[data-card="' + cardId + '"]');
  var showAll = showAllCb ? showAllCb.checked : false;
  var visible = 0, total = 0;
  table.querySelectorAll('tr[data-anchors]').forEach(function(row) {
    total++;
    var passes;
    if (showAll) {
      passes = true;
    } else {
      var raw = row.getAttribute('data-anchors') || '';
      var rowAnchors = raw.split(' ').filter(Boolean);
      if (rowAnchors.length === 0) {
        passes = false;
      } else {
        passes = rowAnchors.some(function(a) { return checked.has(a); });
      }
    }
    row.classList.toggle('dd-filter-hidden', !passes);
    if (passes) visible++;
  });
  document.querySelectorAll('.dd-anchor-master[data-card="' + cardId + '"]').forEach(function(master) {
    var grp = master.getAttribute('data-parent-grp');
    var children = document.querySelectorAll('.dd-anchor-cb[data-card="' + cardId + '"][data-parent-grp="' + grp + '"]');
    var n = 0, t = 0;
    children.forEach(function(c) { t++; if (c.checked) n++; });
    master.checked = (n === t);
    master.indeterminate = (n > 0 && n < t);
  });
  var counter = document.getElementById(cardId + '-visible-count');
  if (counter) counter.textContent = visible + ' / ' + total;
}
function ddSlayerToggleMaster(cb) {
  var card = cb.getAttribute('data-card');
  var grp = cb.getAttribute('data-parent-grp');
  var checked = cb.checked;
  document.querySelectorAll('.dd-anchor-cb[data-card="' + card + '"][data-parent-grp="' + grp + '"]').forEach(function(c) { c.checked = checked; });
  ddSlayerApplyFilter(card);
}
function ddSlayerResetFilter(cardId, defaultShowAll) {
  document.querySelectorAll('.dd-anchor-cb[data-card="' + cardId + '"]').forEach(function(c) { c.checked = true; });
  var sa = document.querySelector('.dd-show-all-mons[data-card="' + cardId + '"]');
  if (sa) sa.checked = defaultShowAll;
  ddSlayerApplyFilter(cardId);
}
function ddSlayerToggleFilterPanel(cardId) {
  var p = document.getElementById(cardId + '-filter');
  if (!p) return;
  var hidden = (p.style.display === 'none' || p.style.display === '');
  p.style.display = hidden ? 'block' : 'none';
}
function ddToggleTagsCompact(btn) {
  // Toggle the dd-tags-compact class on every inner tag wrapper across all
  // slayer cards. The wrapper is a <div> nested inside the <td> because
  // <td> uses display:table-cell which ignores max-height. Default state
  // is "compact" (capped at ~2 lines with a fade gradient at the bottom).
  // Click expands to full height so the badge wall is fully visible.
  // Mixed prior state (some cells individually toggled) is collapsed onto
  // a single state based on the first cell's current class.
  var inners = document.querySelectorAll('.dd-anchor-tags-inner');
  if (!inners.length) return;
  var nowExpanded = inners[0].classList.contains('dd-tags-compact');
  inners.forEach(function(c) { c.classList.toggle('dd-tags-compact', !nowExpanded); });
  btn.textContent = nowExpanded ? 'Compact tags' : 'Expand all tags';
}
function ddToggleTagsCompactCell(event) {
  // Per-cell click toggle. Flips the dd-tags-compact class on just the
  // clicked inner wrapper. Ignores clicks that originated inside an
  // anchor badge so badge hover tooltips keep working without
  // accidentally collapsing or expanding the cell. The bulk button
  // still works on top of any per-cell state — it forces every cell to
  // a single state based on the first cell.
  if (event.target.closest('.dd-anchor-tag')) return;
  event.currentTarget.classList.toggle('dd-tags-compact');
}
</script>
""")

            results_parts.append(
                '<button class="dd-tags-toggle" '
                'onclick="ddToggleTagsCompact(this)">Expand all tags</button>\n'
            )
            results_parts.append('<div class="dd-rec-grid">\n')
            CAT_ABBREV = {'Atk Slayer': 'A', 'Bulk Slayer': 'B', 'CMP Slayer': 'C'}
            CAT_COLORS = {'Atk Slayer': '#f85149', 'Bulk Slayer': '#3fb950',
                          'CMP Slayer': '#d29922'}
            # Unique ID per card to scope filter JS — moveset index + category index.
            _table_uid = 0
            _ms_prefix = f"ms{moveset_idx}"
            for cat_name, cat_ivs in categories.items():
                if not cat_ivs:
                    continue  # hide empty categories (Atk/CMP when no anchors fired)
                desc = CATEGORY_DESCRIPTIONS.get(cat_name, '')
                n_total = len(cat_ivs)
                n_visible = min(n_total, 10)  # top N visible by default
                # Top-quartile highlighting: first ceil(n_total / 4) rows
                n_quartile = max(1, (n_total + 3) // 4)

                _table_uid += 1
                card_id = f"{_ms_prefix}-slayer-{_table_uid}"

                # Determine which anchor kinds apply to this category card.
                # Bulk Slayer surfaces all kinds (bulkpoint anchors are its
                # native kind; bp/cmp tags also show as cross-info).
                want_kinds = {
                    'Atk Slayer': {'damage_breakpoint'},
                    'CMP Slayer': {'cmp'},
                    'Bulk Slayer': {'damage_breakpoint', 'cmp', 'bulkpoint'},
                }.get(cat_name, {'damage_breakpoint', 'cmp', 'bulkpoint'})

                # Build the per-card sub-anchor index. anchor_parents was computed
                # earlier (line ~2348) from resolved_anchors. We filter to only
                # sub-anchors whose kind matches this category, and assign each a
                # stable integer index for the data-anchors row attribute and the
                # filter checkboxes. Order: parent name asc, then threshold asc.
                card_anchor_index: dict[tuple, int] = {}
                card_parent_to_subs: dict[str, list] = {}
                for parent in sorted(anchor_parents.keys()):
                    relevant_subs = [s_ for s_ in anchor_parents[parent]
                                     if s_.kind in want_kinds]
                    if not relevant_subs:
                        continue
                    relevant_subs.sort(key=lambda x: x.threshold_value)
                    for sub in relevant_subs:
                        key = (parent, sub.label or sub.name)
                        if key in card_anchor_index:
                            continue
                        idx = len(card_anchor_index)
                        card_anchor_index[key] = idx
                        card_parent_to_subs.setdefault(parent, []).append((idx, sub))

                # Per-card default for "show all mons":
                # Bulk Slayer is structural, so untagged rows must be visible by
                # default. Atk/CMP Slayer membership requires anchor pass, so
                # default off.
                any_tagless = any(
                    not any(
                        any(s_.kind in want_kinds for s_ in subs)
                        for subs in r.get('_anchor_tags', {}).values()
                    )
                    for r in cat_ivs
                )
                default_show_all = any_tagless
                show_all_attr = ' checked' if default_show_all else ''

                results_parts.append(f'<div class="dd-rec-card">\n')
                results_parts.append(
                    f'<h4>{cat_name} '
                    f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
                    f'({n_total} survivor{"s" if n_total != 1 else ""})'
                    f'</span></h4>\n'
                )
                if desc:
                    results_parts.append(f'<p class="dd-small dd-prose">{desc}</p>\n')

                # Filter panel toggle button + collapsed panel body
                if card_anchor_index:
                    n_anchors_total = len(card_anchor_index)
                    results_parts.append(
                        f'<button class="dd-filter-toggle" '
                        f'onclick="ddSlayerToggleFilterPanel(\'{card_id}\')">'
                        f'Filter anchors ({n_anchors_total})'
                        f'</button>\n'
                    )
                    results_parts.append(
                        f'<div class="dd-filter-panel" id="{card_id}-filter" '
                        f'style="display:none">\n'
                    )
                    for parent, subs_list in card_parent_to_subs.items():
                        results_parts.append('<div class="dd-filter-panel-group">\n')
                        is_auto = parent.startswith('auto_')
                        auto_marker = (
                            ' <span class="dd-auto-marker">(auto)</span>'
                            if is_auto else ''
                        )
                        results_parts.append(
                            f'<label class="dd-filter-master">'
                            f'<input type="checkbox" class="dd-anchor-master" '
                            f'data-card="{card_id}" data-parent-grp="{parent}" '
                            f'checked '
                            f'onchange="ddSlayerToggleMaster(this)"> '
                            f'{parent} ({len(subs_list)}){auto_marker}'
                            f'</label>\n'
                        )
                        results_parts.append('<div class="dd-filter-children">\n')
                        for idx, sub in subs_list:
                            label = sub.label or sub.name
                            results_parts.append(
                                f'<label><input type="checkbox" class="dd-anchor-cb" '
                                f'data-card="{card_id}" data-parent-grp="{parent}" '
                                f'data-anchor-idx="{idx}" checked '
                                f'onchange="ddSlayerApplyFilter(\'{card_id}\')"> '
                                f'{label}</label>\n'
                            )
                        results_parts.append('</div>\n')  # children
                        results_parts.append('</div>\n')  # group
                    # Controls row
                    sa_default_js = 'true' if default_show_all else 'false'
                    results_parts.append('<div class="dd-filter-controls">\n')
                    results_parts.append(
                        f'<button onclick="ddSlayerResetFilter(\'{card_id}\', '
                        f'{sa_default_js})">Reset</button>\n'
                    )
                    results_parts.append(
                        f'<label><input type="checkbox" class="dd-show-all-mons" '
                        f'data-card="{card_id}"{show_all_attr} '
                        f'onchange="ddSlayerApplyFilter(\'{card_id}\')"> '
                        f'Show all mons (ignore filter)</label>\n'
                    )
                    results_parts.append(
                        f'<span class="dd-filter-status">visible: '
                        f'<span id="{card_id}-visible-count">{n_total} / {n_total}</span>'
                        f'</span>\n'
                    )
                    results_parts.append('</div>\n')  # controls
                    results_parts.append('</div>\n')  # filter-panel

                # Table
                results_parts.append(
                    f'<table class="dd-table dd-narrow" id="{card_id}-table">\n'
                )
                results_parts.append(
                    '<tr><th>IVs</th><th>Atk</th><th>Def</th><th>HP</th>'
                    '<th>Wins</th><th>Avg</th><th>Also</th><th>Tags</th></tr>\n'
                )
                for idx, r in enumerate(cat_ivs):
                    a, d, s = r['iv']
                    # Cross-category badges
                    others = sorted(iv_categories.get(r['iv'], set()) - {cat_name})
                    badges = ''
                    for o in others:
                        ab = CAT_ABBREV.get(o, '?')
                        col = CAT_COLORS.get(o, '#888')
                        badges += (
                            f'<span class="dd-badge" '
                            f'style="background:{col};color:#000" '
                            f'title="{o}">{ab}</span> '
                        )

                    # Ultra-short tag rendering: one badge per parent.
                    # Badge VISIBLE TEXT uses derive_short_name() — typically
                    # 3-6 characters (e.g. "lic", "mirb", "lic↑lur", "c:lur").
                    # The badge HOVER tooltip carries the long form
                    # (parent_display_name) plus the per-sub-anchor labels
                    # (e.g. "close_combat→125, rage_fist→78"), so the
                    # abbreviation stays decipherable. The cell-level title=
                    # also includes the full parent name for fallback hover.
                    tag_bits = []
                    row_anchor_indices = []
                    # Per-row counters for the cell-level summary tooltip.
                    # Each parent contributes once to its kind bucket and
                    # n_subs to the total sub-anchor count.
                    n_parents_by_kind = {
                        'damage_breakpoint': 0,
                        'bulkpoint': 0,
                        'cmp': 0,
                    }
                    n_total_subs = 0
                    for parent in sorted(r.get('_anchor_tags', {}).keys()):
                        subs = r['_anchor_tags'][parent]
                        relevant = [s_ for s_ in subs if s_.kind in want_kinds]
                        if not relevant:
                            continue
                        labels = sorted({s_.label or s_.name for s_ in relevant})
                        for s_ in relevant:
                            key = (parent, s_.label or s_.name)
                            if key in card_anchor_index:
                                row_anchor_indices.append(card_anchor_index[key])
                        # Long form (filter panel + tooltip) and short form
                        # (visible badge text). Both derive from the parent
                        # name; long form is also stored on the resolved
                        # anchor as parent_display_name in case the TOML
                        # set it explicitly.
                        long_name = (relevant[0].parent_display_name or parent)
                        short = derive_short_name(parent)
                        n_subs = len(labels)
                        if n_subs == 1:
                            badge_text = short
                            sub_labels_text = labels[0]
                            # For single-sub-anchor parents (Level 1, Level 2,
                            # CMP) the badge has no count suffix and the
                            # tooltip leads with "clears <single sub-anchor>".
                            hover_first_line = (
                                f'{long_name} \u00b7 clears {sub_labels_text}'
                            )
                        else:
                            badge_text = (f'{short}'
                                          f'<span class="dd-anchor-tag-count">'
                                          f'\u00d7{n_subs}</span>')
                            sub_labels_text = ", ".join(labels)
                            # For Level 3 discover-mode parents the badge
                            # shows "<short>×N"; the tooltip explains that
                            # ×N means "this IV passes N of the parent's
                            # sub-anchors" so the abbreviation isn't cryptic.
                            hover_first_line = (
                                f'{long_name} \u00b7 '
                                f'clears {n_subs} sub-anchors'
                            )
                        # Hover tooltip on the badge: long display name +
                        # explicit count meaning + full anchor name +
                        # the sub-anchor labels.
                        hover_text = (
                            f'{hover_first_line}\n'
                            f'{parent}\n'
                            f'{sub_labels_text}'
                        )
                        hover_attr = hover_text.replace('"', '&quot;')
                        tag_bits.append(
                            f'<span class="dd-anchor-tag" title="{hover_attr}">'
                            f'{badge_text}</span>'
                        )
                        # Tally for the cell-level summary tooltip. Use the
                        # kind from the first relevant ResolvedAnchor (all
                        # share kind for a given parent).
                        kind = relevant[0].kind
                        if kind in n_parents_by_kind:
                            n_parents_by_kind[kind] += 1
                        n_total_subs += n_subs
                    tags_cell = ' '.join(tag_bits) if tag_bits else '&mdash;'
                    # Cell-level title is now a one-line summary instead of
                    # the previous per-parent dump (which was 2000+ chars
                    # and literally taller than a screen for rows with 40+
                    # parents). Per-badge tooltips still hold the per-anchor
                    # detail, so this summary just gives an at-a-glance
                    # signal of how many parents the row clears and the
                    # kind breakdown.
                    n_total_parents = sum(n_parents_by_kind.values())
                    if n_total_parents == 0:
                        cell_title_attr = 'No anchors cleared'
                    else:
                        kind_parts = []
                        if n_parents_by_kind['damage_breakpoint']:
                            kind_parts.append(
                                f"{n_parents_by_kind['damage_breakpoint']} brkp"
                            )
                        if n_parents_by_kind['bulkpoint']:
                            kind_parts.append(
                                f"{n_parents_by_kind['bulkpoint']} blkp"
                            )
                        if n_parents_by_kind['cmp']:
                            kind_parts.append(
                                f"{n_parents_by_kind['cmp']} cmp"
                            )
                        cell_title_attr = (
                            f'Clears {n_total_parents} anchors '
                            f'({" \u00b7 ".join(kind_parts)}) '
                            f'\u00b7 {n_total_subs} sub-anchors total. '
                            f'Hover any badge for per-anchor detail.'
                        )
                    data_anchors = ' '.join(str(i) for i in sorted(set(row_anchor_indices)))

                    # Row classes: collapse-hidden beyond top N until expanded;
                    # highlighted if in the top quartile.
                    row_cls_parts = []
                    if idx < n_quartile:
                        row_cls_parts.append('dd-slayer-top')
                    if idx >= n_visible:
                        row_cls_parts.append('dd-slayer-hidden')
                    row_cls = f'class="{" ".join(row_cls_parts)}" ' if row_cls_parts else ''

                    results_parts.append(
                        f'<tr {row_cls}data-anchors="{data_anchors}">'
                        f'<td>{a}/{d}/{s}</td>'
                        f'<td>{r["atk"]:.2f}</td>'
                        f'<td>{r["def_"]:.2f}</td>'
                        f'<td>{r["hp"]}</td>'
                        f'<td class="dd-gain">{r["total_wins"]}</td>'
                        f'<td>{r["avg_score"]:.1f}</td>'
                        f'<td>{badges}</td>'
                        f'<td class="dd-anchor-tags-cell" '
                        f'title="{cell_title_attr}">'
                        f'<div class="dd-anchor-tags-inner dd-tags-compact" '
                        f'onclick="ddToggleTagsCompactCell(event)">'
                        f'{tags_cell}</div></td></tr>\n'
                    )
                results_parts.append('</table>\n')

                # Expand-all toggle if there are hidden rows
                if n_total > n_visible:
                    results_parts.append(
                        f'<button class="dd-slayer-toggle" '
                        f'onclick="(function(btn){{'
                        f'var t=document.getElementById(\'{card_id}-table\');'
                        f'var rows=t.querySelectorAll(\'tr.dd-slayer-hidden\');'
                        f'var shown=rows.length>0 && rows[0].classList.contains(\'dd-slayer-shown\');'
                        f'rows.forEach(function(r){{r.classList.toggle(\'dd-slayer-shown\', !shown);}});'
                        f'btn.textContent=shown?\'Show all {n_total}\':\'Collapse to top {n_visible}\';'
                        f'}})(this)" >'
                        f'Show all {n_total}'
                        f'</button>\n'
                    )
                results_parts.append('</div>\n')  # rec-card
            results_parts.append('</div>\n')  # rec-grid

            # Level 3 sub-anchor distribution: for each Level 3 parent, show
            # how many survivors clear each sub-anchor. This is the
            # "discover-mode" output — what BPs and bulkpoints actually
            # matter here. Includes both damage_breakpoint (atk-side) and
            # bulkpoint (def-side) Level 3 parents; the per-row "Threshold"
            # cell is annotated with " atk" or " def" so the two kinds are
            # visually distinct in a single combined table.
            level3_parents = []
            for parent, subs in anchor_parents.items():
                if len(subs) > 1 and all(
                    s_.kind in ('damage_breakpoint', 'bulkpoint') for s_ in subs
                ):
                    level3_parents.append((parent, subs))
            if level3_parents and slayer_iter_result.get('final'):
                all_survivors = slayer_iter_result['final']
                results_parts.append(
                    '<h4 class="dd-h3" style="margin-top:16px">'
                    'Level&nbsp;3 sub-anchor distribution '
                    '(breakpoints + bulkpoints)</h4>\n'
                )
                results_parts.append(
                    '<p class="dd-small">For each discover-mode anchor, how '
                    'many survivors in the full cohort clear each '
                    '(move,&nbsp;tier) sub-anchor. Atk-side rows are '
                    'breakpoints (focal&nbsp;atk needed to deal more damage); '
                    'def-side rows are bulkpoints (focal&nbsp;def needed to '
                    'take less damage). Use this to identify which '
                    'sub-anchors actually matter for this species — '
                    'high-count rows are the ones worth promoting '
                    'to Level&nbsp;1 in the TOML.</p>\n'
                )
                for parent, subs in sorted(level3_parents):
                    results_parts.append(
                        f'<details class="dd-flip-detail">'
                        f'<summary><strong>{parent}</strong> '
                        f'<span class="dd-small">({len(subs)} sub-anchors)'
                        f'</span></summary>\n'
                    )
                    results_parts.append('<table class="dd-table dd-narrow">\n')
                    results_parts.append(
                        '<tr><th>Sub-anchor</th><th>Threshold</th>'
                        '<th>Clears</th><th>%</th></tr>\n'
                    )
                    # Sort sub-anchors by threshold ascending (easier tiers first)
                    subs_sorted = sorted(subs, key=lambda x: x.threshold_value)
                    for sub in subs_sorted:
                        n_clear = sum(
                            1 for sv in all_survivors
                            if sub.passes(sv['atk'], sv['def_'])
                        )
                        pct = 100.0 * n_clear / len(all_survivors) if all_survivors else 0
                        # Annotate threshold with which stat it targets so
                        # bp/blkp aren't visually conflated.
                        stat_label = 'atk' if sub.target_stat == 'atk' else 'def'
                        results_parts.append(
                            f'<tr><td>{sub.label}</td>'
                            f'<td>{sub.threshold_value:.2f} {stat_label}</td>'
                            f'<td>{n_clear}/{len(all_survivors)}</td>'
                            f'<td>{pct:.0f}%</td></tr>\n'
                        )
                    results_parts.append('</table>\n')
                    results_parts.append('</details>\n')

    results_parts.append('</div>\n')

    # ======== ANALYSIS section (behind toggle) ========
    analysis_parts = []

    # -- Toggle button --
    analysis_parts.append("""
<div style="margin: 10px 0;">
  <button onclick="var s=document.getElementById('dd-analysis');s.style.display=s.style.display==='none'?'block':'none';this.textContent=s.style.display==='none'?'Show Deep Dive Analysis':'Hide Deep Dive Analysis'"
          style="background:#e94560;color:#fff;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;font-size:14px">
    Show Deep Dive Analysis
  </button>
</div>
<div id="dd-analysis" style="display:none">
""")

    # -- Alpha features (banding + clusters) — hidden by default --
    analysis_parts.append("""
<div style="margin: 8px 0;">
  <label style="font-size:12px;color:#888"><input type="checkbox" id="alpha-chk"
    onchange="var d=this.checked?'block':'none';document.getElementById('dd-alpha').style.display=d;var m=document.getElementById('dd-alpha-methods');if(m)m.style.display=d;"
  > Show experimental analysis (banding, clusters)</label>
</div>
<div id="dd-alpha" style="display:none">
""")

    # -- Banding (#3: sort by η², label opp IV mode) --
    analysis_parts.append(f'<div class="dd-section" id="dd-banding">\n')
    analysis_parts.append(f'<h2 class="dd-h2">Banding &amp; Stat Correlations</h2>\n')
    analysis_parts.append(f'<p>Which stats create visible bands in the scatter plot? '
                          f'Sorted by &eta;&sup2; (variance explained). '
                          f'Computed vs <b>{opp_label}</b> opponent IVs.</p>\n')

    # Compute all banding data first, then sort by avg η²
    banding_rows = []
    for si_or_avg in list(range(nS)) + ['avg']:
        if si_or_avg == 'avg':
            sc = avg_scores
            label = '<strong>Average</strong>'
            is_avg = True
        else:
            si = si_or_avg
            sc = [sum(scores_flat[iv * nS * nO + si * nO + oi] for oi in range(nO)) / nO for iv in range(nIvs)]
            s0, s1 = scenarios[si]
            label = f'{s0}v{s1}'
            is_avg = False
        bands = [('Atk', _detect_banding(data_obj['ivAtk'], sc, 'atk')),
                 ('Def', _detect_banding(data_obj['ivDef'], sc, 'def')),
                 ('HP', _detect_banding(hp_list, sc, 'hp'))]
        dominant = max(bands, key=lambda x: x[1]['eta_squared'] if x[1] else 0)
        max_eta = dominant[1]['eta_squared'] if dominant[1] else 0
        banding_rows.append({'label': label, 'bands': bands, 'dominant': dominant,
                             'max_eta': max_eta, 'is_avg': is_avg})

    # Sort non-avg rows by max η² descending (#3)
    non_avg = [r for r in banding_rows if not r['is_avg']]
    avg_row = [r for r in banding_rows if r['is_avg']]
    non_avg.sort(key=lambda r: r['max_eta'], reverse=True)
    sorted_rows = non_avg + avg_row

    analysis_parts.append('<table class="dd-table"><tr><th>Scenario</th><th>Atk <em>r</em></th><th>Atk &eta;&sup2;</th><th>Def <em>r</em></th><th>Def &eta;&sup2;</th><th>HP <em>r</em></th><th>HP &eta;&sup2;</th><th>Dominant</th></tr>\n')
    for row in sorted_rows:
        style = ' style="border-top:2px solid #e94560"' if row['is_avg'] else ''
        line = f'<tr{style}><td>{row["label"]}</td>'
        for name, b in row['bands']:
            if b:
                rc = ' class="dd-strong"' if abs(b['correlation']) > 0.3 else ''
                ec = ' class="dd-strong"' if b['eta_squared'] > 0.3 else ''
                line += f'<td{rc}>{b["correlation"]:+.3f}</td><td{ec}>{b["eta_squared"]:.3f}</td>'
            else:
                line += '<td>-</td><td>-</td>'
        d = row['dominant']
        line += f'<td><strong>{d[0]}</strong> ({d[1]["eta_squared"]:.3f})</td></tr>\n'
        analysis_parts.append(line)
    analysis_parts.append('</table>\n')

    # HP banding detail (#4: add narrative column)
    avg_hp_band = _detect_banding(hp_list, avg_scores, 'hp')
    if avg_hp_band and avg_hp_band['top_jumps']:
        analysis_parts.append('<h3 class="dd-h3">Largest HP band jumps (average score)</h3>\n')
        analysis_parts.append('<table class="dd-table dd-narrow"><tr><th>HP below</th><th>HP above</th><th>Score jump</th><th>Likely cause</th></tr>\n')
        for k1, k2, diff, n1, n2 in avg_hp_band['top_jumps'][:5]:
            cls = 'dd-gain' if diff > 0 else 'dd-loss'
            # (#4) Narrative: what causes this jump? Check which opponents' matchups change most
            hp_below_ivs = [i for i in range(nIvs) if data_obj['ivHp'][i] == int(k1)]
            hp_above_ivs = [i for i in range(nIvs) if data_obj['ivHp'][i] == int(k2)]
            cause = ''
            if hp_below_ivs and hp_above_ivs:
                # Find opponents where score changes most between the two HP groups
                opp_diffs = []
                for oi in range(nO):
                    below_avg = sum(sum(scores_flat[iv * nS * nO + si * nO + oi] for si in range(nS)) / nS for iv in hp_below_ivs) / len(hp_below_ivs)
                    above_avg = sum(sum(scores_flat[iv * nS * nO + si * nO + oi] for si in range(nS)) / nS for iv in hp_above_ivs) / len(hp_above_ivs)
                    opp_diffs.append((opponents[oi], above_avg - below_avg))
                opp_diffs.sort(key=lambda x: abs(x[1]), reverse=True)
                top_causes = [f'{o} ({d:+.0f})' for o, d in opp_diffs[:2] if abs(d) > 1]
                cause = ', '.join(top_causes) if top_causes else 'distributed across opponents'
            analysis_parts.append(f'<tr><td>{int(k1)}</td><td>{int(k2)}</td><td class="{cls}">{diff:+.1f}</td><td class="dd-small">{cause}</td></tr>\n')
        analysis_parts.append('</table>\n')
    analysis_parts.append('</div>\n')

    # -- Clusters per scenario (#5: label opp IV mode, #6: list top IVs for graph reference, #7: clarify methodology) --
    analysis_parts.append(f'<div class="dd-section" id="dd-clusters">\n<h2 class="dd-h2">Cluster Analysis (Per-Scenario)</h2>\n')
    analysis_parts.append(f'<p>Computed vs <b>{opp_label}</b> opponent IVs. '  # (#5)
                          f'Clusters are detected by sorting all {nIvs} IVs by their average score '  # (#7)
                          f'for a given scenario and scanning for score gaps that exceed 3&times; '
                          f'the median gap between consecutive IVs. Unlike k-means, this does not '
                          f'assume a fixed number of clusters &mdash; it finds natural breakpoints '
                          f'where performance drops sharply. '
                          f'The top-5 IVs listed below can be located on the graph above by hovering '  # (#6)
                          f'to find the matching stat product and score.</p>\n')
    for si in range(nS):
        s0, s1 = scenarios[si]
        sc = [sum(scores_flat[iv * nS * nO + si * nO + oi] for oi in range(nO)) / nO for iv in range(nIvs)]
        clusters, sig_gaps = _detect_clusters(sc, data_obj)
        top50 = set(sorted(range(nIvs), key=lambda i: sc[i], reverse=True)[:50])
        opp_imp = _opp_importance(scores_flat, nIvs, nS, nO, si, top50, opponents)
        scene_label = f'{s0}v{s1}'
        if s0 == s1:
            scene_label += {0: ' (no shields)', 1: ' (even)', 2: ' (double shield)'}.get(s0, '')
        elif s0 > s1:
            scene_label += ' (shield adv.)'
        else:
            scene_label += ' (shield disadv.)'
        analysis_parts.append(f'<h3 class="dd-h3">{scene_label}</h3>\n')
        scene_ranked = sorted(range(nIvs), key=lambda i: sc[i], reverse=True)
        if sig_gaps:
            # Top cluster = IVs above the first gap
            top_cluster_size = sig_gaps[0][0]
            top_cluster_ivs = scene_ranked[:top_cluster_size]
            tc_sp_min = min(data_obj['spRanks'][iv] for iv in top_cluster_ivs)
            tc_sp_max = max(data_obj['spRanks'][iv] for iv in top_cluster_ivs)
            tc_score_min = sc[scene_ranked[top_cluster_size - 1]]
            tc_score_max = sc[scene_ranked[0]]
            analysis_parts.append(f'<p>{len(sig_gaps)} significant gap(s). '
                                  f'Top cluster: {top_cluster_size} IVs, '
                                  f'scores {tc_score_min:.0f}&ndash;{tc_score_max:.0f} '
                                  f'(SP ranks {tc_sp_min}&ndash;{tc_sp_max}). '
                                  f'<b>On graph:</b> look for Y &ge; {tc_score_min:.0f} '
                                  f'with SP rank {tc_sp_min}&ndash;{tc_sp_max} on X axis.</p>\n')
        else:
            analysis_parts.append('<p>Smooth gradient (no gaps &gt; 3&times; median).</p>\n')
        analysis_parts.append('<table class="dd-table dd-narrow"><tr><th>#</th><th>IVs</th><th>Atk</th><th>Def</th><th>HP</th><th>SP</th><th>Score</th><th>Tier</th></tr>\n')
        for rank in range(5):
            iv = scene_ranked[rank]
            sp = data_obj['ivSp'][iv]
            analysis_parts.append(f'<tr><td>{rank+1}</td><td>{_iv_label(data_obj, iv)}</td><td>{data_obj["ivAtk"][iv]:.2f}</td><td>{data_obj["ivDef"][iv]:.2f}</td><td>{data_obj["ivHp"][iv]}</td><td>{sp:.0f}</td><td>{sc[iv]:.1f}</td><td>{_tier_badge_html(data_obj, iv)}</td></tr>\n')
        analysis_parts.append('</table>\n')
        pos = [d for d in opp_imp if d['gap'] > 0][:3]
        neg = [d for d in opp_imp if d['gap'] < 0][:2]
        pos_str = ', '.join(f'{d["opponent"]} ({d["gap"]:+.0f})' for d in pos)
        neg_str = ', '.join(f'{d["opponent"]} ({d["gap"]:+.0f})' for d in neg)
        line = f'<p class="dd-small"><b>Top differentiators:</b> {pos_str}'
        if neg:
            line += f' | <b>Sacrifices:</b> {neg_str}'
        analysis_parts.append(line + '</p>\n')
    analysis_parts.append('</div>\n')

    # -- Close alpha features div --
    analysis_parts.append('</div>\n')

    # -- Rank volatility (#8: label opp IV mode, #9: hover text) --
    analysis_parts.append(f'<div class="dd-section" id="dd-volatility">\n<h2 class="dd-h2">Rank Volatility</h2>\n')
    analysis_parts.append(f'<p>Each IV is ranked separately for each shield scenario '
                          f'(vs <b>{opp_label}</b> opponent IVs). '  # (#8)
                          f'The numbers in the table are that IV\'s rank out of {nIvs} '  # (#9)
                          f'for each scenario. '
                          f'High range = scenario specialist; low range = generalist.</p>\n')
    analysis_parts.append('<table class="dd-table"><tr><th>IVs</th>')
    for s0, s1 in scenarios:
        # (#9) Hover text explaining each column
        analysis_parts.append(f'<th title="Rank out of {nIvs} IVs in the {s0}v{s1} shield scenario (1 = best)">{s0}v{s1}</th>')
    analysis_parts.append(f'<th title="Overall rank when averaging across all scenarios">Avg</th>'
                          f'<th title="Difference between best and worst scenario rank (lower = more consistent)">Range</th>'
                          f'<th>Tier</th></tr>\n')
    for iv in ranked[:15]:
        row = f'<tr><td>{_iv_label(data_obj, iv)}</td>'
        ranks_for_iv = [scene_ranks[si][iv] for si in range(nS)]
        for r in ranks_for_iv:
            cls = ''
            if r <= 10:
                cls = ' class="dd-rank-good"'
            elif r > 1000:
                cls = ' class="dd-rank-bad"'
            row += f'<td{cls} title="Rank {r} out of {nIvs}">{r}</td>'
        rng = max(ranks_for_iv) - min(ranks_for_iv)
        row += f'<td><b>{avg_ranks[iv]}</b></td><td>{rng}</td><td>{_tier_badge_html(data_obj, iv)}</td></tr>\n'
        analysis_parts.append(row)
    analysis_parts.append('</table>\n')

    # Most stable top-50
    top50_vols = [(iv, max(scene_ranks[si][iv] for si in range(nS)) - min(scene_ranks[si][iv] for si in range(nS))) for iv in ranked[:50]]
    top50_vols.sort(key=lambda x: x[1])
    analysis_parts.append('<h3 class="dd-h3">Most stable top-50 IVs</h3>\n')
    analysis_parts.append('<table class="dd-table dd-narrow"><tr><th>IVs</th><th>Avg</th><th>Best</th><th>Worst</th><th title="Best rank minus worst rank">Range</th><th>Tier</th></tr>\n')
    for iv, rng in top50_vols[:8]:
        best = min(scene_ranks[si][iv] for si in range(nS))
        worst = max(scene_ranks[si][iv] for si in range(nS))
        analysis_parts.append(f'<tr><td>{_iv_label(data_obj, iv)}</td><td>{avg_ranks[iv]}</td><td class="dd-rank-good">{best}</td><td>{worst}</td><td>{rng}</td><td>{_tier_badge_html(data_obj, iv)}</td></tr>\n')
    analysis_parts.append('</table></div>\n')

    # -- Matchup flip table --
    analysis_parts.append(f'<div class="dd-section" id="dd-flips">\n<h2 class="dd-h2">Matchup Flip Table</h2>\n')
    analysis_parts.append(f'<p>Matchups crossing 500-point boundary vs reference '
                          f'({_iv_label(data_obj, ref_iv)}, {opp_label}).</p>\n')

    analysis_parts.append('<table class="dd-table"><tr><th>IVs</th><th>Atk</th><th>Def</th><th>HP</th><th>Avg</th><th>Gains</th><th>Loses</th><th>Net</th><th>Tier</th></tr>\n')
    for iv, g, l, net in flip_summary[:25]:
        nc = 'dd-gain' if net > 0 else ('dd-loss' if net < 0 else '')
        analysis_parts.append(f'<tr><td>{_iv_label(data_obj, iv)}</td><td>{data_obj["ivAtk"][iv]:.2f}</td><td>{data_obj["ivDef"][iv]:.2f}</td><td>{data_obj["ivHp"][iv]}</td><td>{avg_scores[iv]:.1f}</td><td class="dd-gain">{g}</td><td class="dd-loss">{l}</td><td class="{nc}"><b>{net:+d}</b></td><td>{_tier_badge_html(data_obj, iv)}</td></tr>\n')
    analysis_parts.append('</table>\n')

    # Detail flips for notable IVs — with breakpoint narration
    notable = [x for x in flip_summary if abs(x[3]) >= 3 or x[0] in set(ranked[:5])]
    for iv, g, l, net in notable[:8]:
        fd = flips[iv]
        prose = _prose_flip_summary(fd)
        analysis_parts.append(f'<details class="dd-flip-detail"><summary>{_iv_label(data_obj, iv)} &mdash; <span class="dd-gain">+{g}</span>/<span class="dd-loss">-{l}</span> (net {net:+d}){_tier_badge_html(data_obj, iv)}</summary>\n')
        analysis_parts.append(f'<p class="dd-prose">{prose}</p>\n')
        focal_atk_iv = data_obj['ivAtk'][iv]
        focal_def_iv = data_obj['ivDef'][iv]
        focal_hp_iv = data_obj['ivHp'][iv]
        ref_hp_val2 = data_obj['ivHp'][ref_iv]
        for label, entries, cls, is_gain in [('Gains', fd['gains'], 'dd-gain', True),
                                              ('Losses', fd['losses'], 'dd-loss', False)]:
            if entries:
                entries_sorted = sorted(entries, key=lambda e: abs(e['iv_score'] - e['ref_score']), reverse=True)
                analysis_parts.append(f'<table class="dd-table dd-narrow"><tr><th>Scen.</th><th>Opponent</th><th>Ref</th><th>IV</th><th>&Delta;</th><th>Why</th></tr>\n')
                for e in entries_sorted:
                    d = e['iv_score'] - e['ref_score']
                    narr = ''
                    opp_name = e['opponent']
                    if opp_name in opp_info_cache and focal_moves:
                        oi = opp_info_cache[opp_name]
                        narr = _narrate_flip(
                            focal_atk_iv, focal_def_iv, focal_hp_iv,
                            ref_atk, ref_def, ref_hp_val2,
                            oi['atk'], oi['def_'], opp_name,
                            focal_moves, oi['moves'],
                            focal_types, oi['types'],
                            is_gain=is_gain,
                        )
                    analysis_parts.append(f'<tr><td>{e["scenario"]}</td><td>{e["opponent"]}</td><td>{e["ref_score"]}</td><td class="{cls}">{e["iv_score"]}</td><td class="{cls}">{d:+d}</td><td class="dd-small">{narr}</td></tr>\n')
                analysis_parts.append('</table>\n')
        analysis_parts.append('</details>\n')
    analysis_parts.append('</div>\n')

    # -- Methods (moved to bottom per #2) --
    # Alpha methods only show when the experimental checkbox is on (linked via JS)
    analysis_parts.append(f"""
<div class="dd-section" id="dd-methods">
<h2 class="dd-h2">Methods</h2>
<p>Automated analysis of {nIvs} IV spreads across {nS} shield scenarios against
{nO} opponents ({data_obj.get('opponentLabel', '')}).</p>
<p><strong>Moveset:</strong> {_pretty_moveset(moveset_label)} | <strong>Opp IVs:</strong> {opp_iv_mode}
| <strong>Reference IV:</strong> {_iv_label(data_obj, ref_iv)} (PvPoke default)</p>
<dl class="dd-methods-dl">
  <dt>Rank volatility</dt>
  <dd>Each IV is ranked 1&ndash;{nIvs} for each scenario independently. The range (best rank minus
  worst rank) shows how scenario-dependent performance is. Low range = generalist; high range = specialist.</dd>
  <dt>Matchup flip analysis</dt>
  <dd>For each IV, we check every (opponent, scenario) pair and compare to the reference IV
  ({_iv_label(data_obj, ref_iv)}, {opp_label}). A &ldquo;flip&rdquo; occurs when one IV wins
  (score &ge; 500) and the other loses (&lt; 500). Net flips = gains &minus; losses.</dd>
  <dt>Breakpoint/bulkpoint narration</dt>
  <dd>For each flip, we compute per-hit damage from each move at the focal IV and reference IV
  stats. Damage changes are reported as breakpoints (your moves do more damage), bulkpoints
  (opponent moves do less damage), or their losses. HP differences are also shown.</dd>
</dl>
<div id="dd-alpha-methods" style="display:none">
<h3 class="dd-h3">Experimental methods</h3>
<dl class="dd-methods-dl">
  <dt>Banding detection</dt>
  <dd>IVs grouped by discrete stat value. F-ratio and &eta;&sup2; (fraction of total score
  variance explained by stat grouping, 0&ndash;1 scale) measure how much each stat creates
  visible bands. Pearson <em>r</em> shows correlation direction (positive = higher stat &rarr; higher score).</dd>
  <dt>Cluster detection (gap analysis)</dt>
  <dd>All {nIvs} IVs are sorted by their average score for a given scenario. We compute the
  score difference between each consecutive pair. The median of these differences is the
  &ldquo;typical&rdquo; gap. Gaps exceeding 3&times; the median indicate a natural break between
  performance tiers. This is <em>not</em> k-means or similar &mdash; it assumes no fixed cluster
  count and finds breakpoints where performance drops sharply.</dd>
  <dt>Opponent importance</dt>
  <dd>For each scenario, the average score of the top 50 IVs against each opponent is compared
  to the population average. Large positive gaps show which opponents the top cluster dominates;
  negative gaps show where it sacrifices performance.</dd>
</dl>
</div>
</div>
""")

    # Close the analysis toggle div
    analysis_parts.append('</div>\n')

    return css, ''.join(results_parts), ''.join(analysis_parts)


# ---------------------------------------------------------------------------
# Interactive HTML output
# ---------------------------------------------------------------------------

def generate_interactive_html(species, league, moveset_data, html_path,
                              thresholds=None, opponent_label=None,
                              shield_scenarios=None, opponent_names=None,
                              opp_iv_modes=None, reference_idx=-1,
                              standalone=False, slayer_iter_result=None,
                              cli_args_str=None):
    """Generate a single-page interactive HTML with JS-driven dropdowns.

    moveset_data: list of dicts, each with:
        'label': str (e.g. "COUNTER / DYNAMIC_PUNCH, ICE_PUNCH")
        'scores': dict of opp_iv_mode -> flat score list (canonical order)
        'meta': canonical_meta list (shared across modes for same moveset)
    """
    opp_iv_modes = opp_iv_modes or ['pvpoke']
    shield_scenarios = shield_scenarios or [(1, 1)]
    opponent_names = opponent_names or []
    n_ivs = len(moveset_data[0]['meta']) if moveset_data else 0
    n_scenarios = len(shield_scenarios)
    n_opponents = len(opponent_names)

    # Build threshold tier info
    tier_names = list(thresholds.keys()) if thresholds else []
    tier_info = []
    for i, name in enumerate(tier_names):
        color = THRESHOLD_COLORS[i % len(THRESHOLD_COLORS)]
        thresh = thresholds[name]
        tier_info.append({
            'name': name,
            'color': color,
            'attack': thresh['attack'],
            'defense': thresh['defense'],
            'stamina': thresh['stamina'],
            'desc': _threshold_desc(thresh),
        })

    # Build the DATA object for JS
    # IV metadata: shared across all movesets (same species = same valid IVs)
    meta = moveset_data[0]['meta']
    iv_a = [m[0] for m in meta]
    iv_d = [m[1] for m in meta]
    iv_s = [m[2] for m in meta]
    iv_lv = [m[3] for m in meta]
    iv_cp = [m[4] for m in meta]
    iv_atk = [round(m[5], 2) for m in meta]
    iv_def = [round(m[6], 2) for m in meta]
    iv_hp = [m[7] for m in meta]
    iv_sp = [round(m[5] * m[6] * m[7], 1) for m in meta]

    # Compute stat product ranks (same for all movesets)
    sp_sorted = sorted(range(n_ivs), key=lambda i: iv_sp[i], reverse=True)
    sp_ranks = [0] * n_ivs
    for rank, idx in enumerate(sp_sorted):
        sp_ranks[idx] = rank + 1

    # Classify IVs by threshold tier
    # iv_tiers: primary tier (most restrictive match, for coloring) — -1 = none
    # iv_all_tiers: list of ALL matching tier indices (for filtering and tables)
    iv_tiers = [-1] * n_ivs
    iv_all_tiers = [[] for _ in range(n_ivs)]
    if thresholds:
        for i in range(n_ivs):
            for ti, (tname, thresh) in enumerate(thresholds.items()):
                meets = True
                if thresh['attack'] > 0 and iv_atk[i] < thresh['attack']:
                    meets = False
                if thresh['defense'] > 0 and iv_def[i] < thresh['defense']:
                    meets = False
                if thresh['stamina'] > 0 and iv_hp[i] < thresh['stamina']:
                    meets = False
                if meets:
                    iv_all_tiers[i].append(ti)
                    if iv_tiers[i] == -1:
                        iv_tiers[i] = ti  # first (most restrictive) match for coloring

    # Find canonical IV indices for the reference IV spreads
    # PvPoke default IVs for this species
    pvpoke_ref_iv_idx = -1
    rank1_ref_iv_idx = -1
    try:
        _lv, da, dd, ds = pvpoke_default_ivs(species, league=league)
        for i in range(n_ivs):
            if iv_a[i] == da and iv_d[i] == dd and iv_s[i] == ds:
                pvpoke_ref_iv_idx = i
                break
    except (ValueError, KeyError):
        pass
    # Rank 1 by stat product
    if n_ivs > 0:
        rank1_ref_iv_idx = min(range(n_ivs), key=lambda i: sp_ranks[i])

    data_obj = {
        'species': species,
        'league': league,
        'cpCap': LEAGUE_CAPS[league],
        'nIvs': n_ivs,
        'nScenarios': n_scenarios,
        'nOpponents': n_opponents,
        'scenarios': [[s0, s1] for s0, s1 in shield_scenarios],
        'opponents': opponent_names,
        'oppIvModes': opp_iv_modes,
        'opponentLabel': opponent_label or 'PvPoke rankings',
        'referenceIdx': reference_idx,
        'tiers': tier_info,
        'movesets': [{'label': md['label'], 'prettyLabel': _pretty_moveset(md['label'])} for md in moveset_data],
        # Reference IV indices (for matchup diff in hover text)
        'pvpokeRefIvIdx': pvpoke_ref_iv_idx,
        'rank1RefIvIdx': rank1_ref_iv_idx,
        # IV metadata
        'ivA': iv_a, 'ivD': iv_d, 'ivS': iv_s,
        'ivLv': iv_lv, 'ivCp': iv_cp,
        'ivAtk': iv_atk, 'ivDef': iv_def, 'ivHp': iv_hp,
        'ivSp': iv_sp, 'spRanks': sp_ranks, 'ivTiers': iv_tiers, 'ivAllTiers': iv_all_tiers,
    }

    # Score arrays: one per (moveset_idx, opp_iv_mode)
    score_arrays = {}
    for mi, md in enumerate(moveset_data):
        for mode in opp_iv_modes:
            key = f'{mi}_{mode}'
            score_arrays[key] = md['scores'][mode]

    # Compute cluster gap Y-values per (moveset, opp_iv_mode, scenario)
    # These are the score thresholds where significant gaps appear in the
    # sorted score distribution. Used by JS to draw horizontal lines on the plot.
    cluster_gaps = {}  # key: "mi_mode" -> list of lists (one per scenario)
    for mi, md in enumerate(moveset_data):
        for mode in opp_iv_modes:
            key = f'{mi}_{mode}'
            sf = score_arrays[key]
            per_scenario = []
            for si in range(n_scenarios):
                # Compute per-IV average score for this scenario
                scene_scores = []
                for iv in range(n_ivs):
                    base = iv * n_scenarios * n_opponents + si * n_opponents
                    total = sum(sf[base + oi] for oi in range(n_opponents))
                    scene_scores.append(total / n_opponents)
                # Sort descending, find gaps
                sorted_sc = sorted(scene_scores, reverse=True)
                gaps = [sorted_sc[i-1] - sorted_sc[i] for i in range(1, len(sorted_sc))]
                if gaps:
                    gap_sorted = sorted(gaps)
                    median_gap = gap_sorted[len(gap_sorted) // 2]
                    # Gap Y-values: the score BELOW the gap (i.e. the top of the lower cluster)
                    sig = []
                    for i, g in enumerate(gaps):
                        if g > 3 * median_gap and i < n_ivs // 4:
                            sig.append(round(sorted_sc[i+1], 1))  # score just below the gap
                    per_scenario.append(sig[:5])  # max 5 gaps per scenario
                else:
                    per_scenario.append([])
            cluster_gaps[key] = per_scenario
    data_obj['clusterGaps'] = cluster_gaps

    # Slayer IV overlay: extract canonical IV indices that landed in any
    # slayer category from the iterative-slayer-discovery result. Rendered
    # as a separate legend entry on the scatter plot with a distinct
    # marker shape (star-diamond) so users can see what avg-score trade
    # a "slayer-quality" spread costs vs the avg-score-optimal cluster.
    # Slayer membership is fundamentally a different optimization target
    # than avg score (mirror-match wins under even-strict), so the two
    # often don't coincide — visualizing the gap is the whole point.
    # The slayer iteration stores ``iv`` as a (a_iv, d_iv, s_iv) triple
    # (see line ~529 in iterative_slayer_discovery), but the JS plot
    # indexes IVs by their canonical position in iv_a/iv_d/iv_s. Build a
    # reverse lookup so we can translate triples → canonical indices.
    iv_idx_by_triple = {(iv_a[i], iv_d[i], iv_s[i]): i for i in range(n_ivs)}
    slayer_cats_by_idx: dict = {}
    if slayer_iter_result and slayer_iter_result.get('categories'):
        for cat_name, cat_rows in slayer_iter_result['categories'].items():
            for r in (cat_rows or []):
                iv_triple = r.get('iv')
                if iv_triple is None:
                    continue
                idx = iv_idx_by_triple.get(tuple(iv_triple))
                if idx is None:
                    continue
                slayer_cats_by_idx.setdefault(idx, []).append(cat_name)
    data_obj['slayerIvs'] = sorted(slayer_cats_by_idx.keys())
    # Stringify keys so json.dumps emits a clean JS object (JS treats
    # both numeric and string keys identically for object access).
    data_obj['slayerCatsByIv'] = {
        str(idx): sorted(set(cats)) for idx, cats in slayer_cats_by_idx.items()
    }

    # Anchor-clear IV overlay: union the canonical IV indices that pass
    # any anchor for which _aggregate_flips_by_anchor emitted a record.
    # The aggregator runs again inside generate_analysis_sections for
    # the bullet rendering — running it here too is cheap and avoids
    # plumbing its output through a side channel. Per-IV "which anchors
    # cleared" data populates the hover tooltip.
    #
    # Only fires when slayer iteration is on (resolved_anchors come from
    # slayer_iter_result); without --mirror-slayer the anchor-clear
    # overlay is silently empty. See TODO entry "RyanSwag-style matchup
    # flip annotations" for the longer-term plan to surface anchors
    # without requiring a slayer iteration.
    # Selectivity gate: an anchor counts toward overlay membership only
    # if it's "actually selective" — i.e., passed by less than half the
    # IV pool. The bullets layer keeps all emitted anchors (an
    # easy-to-clear breakpoint is still informational about where the
    # damage tier lands), but for the overlay, "every IV clears
    # something" is degenerate noise. Without this filter, e.g. a
    # Lickilicky Hyper Beam bulkpoint at def 96.62 — which essentially
    # every spread satisfies — would mark every point on the scatter
    # as anchor-cleared and defeat the highlighting purpose.
    SELECTIVITY_MAX_PASS_RATE = 0.5
    anchor_cleared_by_idx: dict = {}
    if slayer_iter_result:
        ra = slayer_iter_result.get('resolved_anchors', []) or []
        if ra:
            mset_key = f'0_{opp_iv_modes[0]}'
            sf = score_arrays.get(mset_key, [])
            if sf:
                # Build a stub data_obj-shaped dict the aggregator can read.
                # It only needs ivAtk/ivDef.
                stub = {'ivAtk': iv_atk, 'ivDef': iv_def}
                records = _aggregate_flips_by_anchor(
                    sf, n_ivs, n_scenarios, n_opponents,
                    ra, stub, shield_scenarios, opponent_names,
                )
                for rec in records:
                    passing = rec.get('passing_ivs', [])
                    if not passing:
                        continue
                    pass_rate = len(passing) / n_ivs if n_ivs else 0.0
                    if pass_rate > SELECTIVITY_MAX_PASS_RATE:
                        continue  # too easy — skip for overlay purposes
                    label = (rec['anchor'].parent_display_name
                             or rec['anchor'].label
                             or rec['anchor'].parent)
                    for iv in passing:
                        anchor_cleared_by_idx.setdefault(iv, set()).add(label)
    data_obj['anchorClearIvs'] = sorted(anchor_cleared_by_idx.keys())
    data_obj['anchorClearByIv'] = {
        str(idx): sorted(labels) for idx, labels in anchor_cleared_by_idx.items()
    }

    opp_desc = opponent_label or 'PvPoke rankings'
    shield_desc = ', '.join(f'{s0}v{s1}' for s0, s1 in shield_scenarios)

    # --- Build HTML ---
    plotly_tag = _plotly_script_tag(standalone)
    # Embed the equivalent CLI invocation as an HTML comment near the top so
    # `grep '<!-- CLI:' file.html` works for forensic comparison without
    # adding visible page chrome.
    cli_comment = ''
    if cli_args_str:
        from html import escape as _esc_cmt
        cli_comment = f'<!-- CLI: {_esc_cmt(cli_args_str)} -->\n'

    html = f"""<!DOCTYPE html>
{cli_comment}<html>
<head>
<meta charset="utf-8">
<title>{species} {league.title()} League IV Deep Dive</title>
{plotly_tag}
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 20px; background: #1a1a2e; color: #e0e0e0; }}
  h1 {{ color: #e94560; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 15px; }}
  details.meta {{ cursor: pointer; }}
  details.meta summary {{ color: #888; font-size: 13px; }}
  .controls {{ background: #16213e; padding: 10px 14px; border-radius: 6px;
               margin-bottom: 15px; display: flex; gap: 18px; align-items: center;
               flex-wrap: wrap; }}
  .controls label {{ font-size: 13px; color: #aaa; }}
  .controls select {{ background: #0f3460; color: #e0e0e0; border: 1px solid #1a3a6e;
                      padding: 4px 8px; border-radius: 4px; font-size: 13px; }}
  .plot-container {{ margin-bottom: 20px; }}
  .summary {{ background: #16213e; padding: 12px; border-radius: 6px;
              margin-bottom: 20px; font-size: 13px; overflow-x: auto; }}
  .summary table {{ border-collapse: collapse; width: 100%; }}
  .summary th, .summary td {{ text-align: left; padding: 3px 8px;
                               border-bottom: 1px solid #0f3460; white-space: nowrap; }}
  .summary th {{ color: #e94560; }}
  .tier-badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px;
                 font-size: 11px; font-weight: bold; }}
  .threshold-info {{ background: #16213e; padding: 10px; border-radius: 6px;
                     margin-bottom: 15px; font-size: 13px; }}
  .threshold-info span {{ font-weight: bold; }}
  .methodology {{ color: #888; font-size: 12px; max-width: 800px;
                  margin: 10px 0 30px 0; line-height: 1.6; }}
</style>
</head>
<body>
<h1>{species} — {league.title()} League IV Deep Dive</h1>
<p class="meta">Opponents: {opp_desc}
| Shield scenario(s): {shield_desc} | Policy: pvpoke_dp</p>
"""

    # Opponent list
    if opponent_names:
        html += '<details class="meta"><summary>Opponent list '
        html += f'({len(opponent_names)} mons)</summary><p style="margin:4px 0 8px 12px">'
        html += ', '.join(opponent_names)
        html += '</p></details>\n'

    # Threshold info folded into controls (legend shows tier name + desc)
    # No separate threshold-info box needed — graph legend has full detail

    # Controls
    html += '<div class="controls">\n'
    if len(moveset_data) > 1:
        html += '  <label>Moveset: <select id="moveset-sel" onchange="updateView()">\n'
        for mi, md in enumerate(moveset_data):
            ref_tag = ' (reference)' if mi == reference_idx else ''
            html += f'    <option value="{mi}">{_pretty_moveset(md["label"])}{ref_tag}</option>\n'
        html += '  </select></label>\n'

    if n_scenarios > 1:
        html += '  <label>Shields: <select id="scenario-sel" onchange="updateView()">\n'
        html += '    <option value="avg">All (avg)</option>\n'
        for si, (s0, s1) in enumerate(shield_scenarios):
            sel = ' selected' if n_scenarios == 1 else ''
            html += f'    <option value="{si}"{sel}>{s0}v{s1}</option>\n'
        html += '  </select></label>\n'

    if len(opp_iv_modes) > 1:
        html += '  <label>Opponent IVs: <select id="oppiv-sel" onchange="updateView()">\n'
        for mode in opp_iv_modes:
            label = 'PvPoke Defaults' if mode == 'pvpoke' else 'Rank 1'
            html += f'    <option value="{mode}">{label}</option>\n'
        html += '  </select></label>\n'
    html += '  <label>Color: <select id="color-sel" onchange="updateView()">\n'
    html += '    <option value="threshold">Threshold tiers</option>\n'
    html += '    <option value="hp">HP</option>\n'
    html += '    <option value="def">Defense</option>\n'
    html += '    <option value="atk">Attack</option>\n'
    html += '    <option value="score">Score</option>\n'
    html += '  </select></label>\n'
    html += '  <label style="font-size:12px;color:#aaa"><input type="checkbox" id="cluster-chk" onchange="updateView()" style="margin-left:12px"> Show clusters</label>\n'
    if thresholds:
        html += '  <span style="font-size:11px;color:#888;margin-left:8px">Threshold tiers shown in graph legend. Hover to isolate; click to lock.</span>\n'
    html += '</div>\n'

    # Plot first, then summary table below
    html += '<div id="plot" class="plot-container" style="height:550px;"></div>\n'
    html += '<div id="summary" class="summary"></div>\n'

    # Methodology footer
    html += '<div id="methodology" class="methodology"></div>\n'

    # Deep dive analysis sections (banding, clusters, flips, etc.)
    analysis_css, results_html, analysis_html = generate_analysis_sections(
        data_obj, score_arrays, 0, opp_iv_modes[0],
        shield_scenarios, opponent_names,
        slayer_iter_result=slayer_iter_result)
    # Inject analysis CSS into the style block (replace closing tag we already emitted)
    html = html.replace('</style>\n</head>', analysis_css + '\n</style>\n</head>', 1)
    # Results section is always visible; analysis is behind a toggle
    html += results_html
    html += analysis_html

    # Embed data
    html += f'<script>var DATA = {json.dumps(data_obj)};\n'
    html += f'var SCORES = {json.dumps(score_arrays)};\n'
    html += '</script>\n'

    # JS engine
    html += '<script>\n'
    html += _interactive_js_engine(n_scenarios, n_opponents, opp_iv_modes,
                                   reference_idx, tier_info, opp_desc, league,
                                   shield_scenarios)
    html += '</script>\n'

    # Footer: equivalent CLI invocation, kept at the bottom of the page so
    # it's discoverable but doesn't compete with the actual analysis content.
    if cli_args_str:
        from html import escape as _esc
        html += '<details class="meta" style="margin-top:30px;border-top:1px solid #0f3460;padding-top:10px">'
        html += '<summary>Run parameters (CLI invocation)</summary>'
        html += '<pre style="margin:8px 0;background:#16213e;'
        html += 'padding:10px;border-radius:4px;color:#e0e0e0;font-size:12px;'
        html += 'white-space:pre-wrap;word-break:break-all">'
        html += _esc(cli_args_str)
        html += '</pre></details>\n'

    html += '</body>\n</html>\n'

    with open(html_path, 'w') as f:
        f.write(html)
    print(f"  Interactive HTML written to {html_path}")


_JS_ENGINE_PATH = os.path.join(os.path.dirname(__file__), 'deep_dive_engine.js')


def _interactive_js_engine(n_scenarios, n_opponents, opp_iv_modes, reference_idx,
                           tier_info, opp_desc, league, shield_scenarios):
    """Return the JS code for the interactive deep dive page.

    The JS body lives in ``scripts/deep_dive_engine.js`` so it can be
    edited as plain JavaScript (with syntax highlighting, no Python
    f-string brace escaping). Eight placeholders inside that file get
    replaced at runtime with the per-dive values below.
    """
    tier_colors_js = json.dumps([t['color'] for t in tier_info])
    tier_names_js = json.dumps([t['name'] for t in tier_info])
    scenario_mode_default = '"avg"' if n_scenarios > 1 else '"0"'
    shield_desc_default = f'{shield_scenarios[0][0]}v{shield_scenarios[0][1]}'
    opp_desc_escaped = opp_desc.replace("'", "\\'")

    with open(_JS_ENGINE_PATH) as _f:
        body = _f.read()
    substitutions = {
        '__SCENARIO_MODE_DEFAULT__': scenario_mode_default,
        '__OPP_IV_MODE_DEFAULT__': opp_iv_modes[0],
        '__TIER_COLORS_JS__': tier_colors_js,
        '__TIER_NAMES_JS__': tier_names_js,
        '__SHIELD_DESC_DEFAULT__': shield_desc_default,
        '__LEAGUE_TITLE__': league.title(),
        '__LEAGUE_CP_CAP__': str(LEAGUE_CAPS[league]),
        '__OPP_DESC_ESCAPED__': opp_desc_escaped,
    }
    for placeholder, value in substitutions.items():
        body = body.replace(placeholder, value)
    # Match the original f-string output: one leading newline (already
    # in the extracted body) and one trailing newline.
    return body + '\n'


def format_cli_args(args, parser) -> str:
    """Build the *fully-resolved* equivalent command from a parsed Namespace.

    Walks the parser's actions in declaration order and emits **every** flag
    with its actual value, including flags whose value happens to equal the
    current parser default. This is intentional: defaults can change between
    runs, so a string that omits "default" flags becomes ambiguous when read
    later — you can't tell whether `--mirror-slayer-pool` was unset (and got
    today's default) or set to today's default explicitly.

    The fully-resolved form is verbose but unambiguous: re-reading the HTML
    next month after a default has changed still tells you exactly what value
    was used. This output is the forensic record, not necessarily a
    convenient copy-paste — though it IS pasteable and will reproduce the
    same run.

    Boolean flags are emitted only when True (False is the implicit absence),
    since there's no `--no-X` form for store_true / store_false flags here.
    Flags whose value is None are skipped because there's no syntax for
    "explicitly set to None" on the command line.
    """
    parts = ["python scripts/deep_dive.py"]
    positional: list[str] = []
    flags: list[str] = []
    for action in parser._actions:
        # Skip the implicit help action
        if action.dest == 'help':
            continue
        val = getattr(args, action.dest, None)
        # Positional args (no option strings)
        if not action.option_strings:
            if val is not None:
                positional.append(_shell_quote(str(val)))
            continue
        flag = action.option_strings[0]
        if isinstance(action, argparse._StoreTrueAction):
            # store_true: only emit when True (False = absent on the cmdline)
            if val:
                flags.append(flag)
            continue
        if isinstance(action, argparse._StoreFalseAction):
            # store_false: emit only when explicitly False
            if not val:
                flags.append(flag)
            continue
        # None means "not set and no default to record"
        if val is None:
            continue
        if action.nargs in (None, '?', 0) or action.nargs == argparse.OPTIONAL:
            if isinstance(val, list):
                # action='append' — emit one occurrence per value
                for item in val:
                    flags.append(f'{flag} {_shell_quote(str(item))}')
            else:
                flags.append(f'{flag} {_shell_quote(str(val))}')
        else:
            # nargs='+', '*', or numeric — join with spaces
            if isinstance(val, (list, tuple)):
                joined = ' '.join(_shell_quote(str(v)) for v in val)
            else:
                joined = _shell_quote(str(val))
            flags.append(f'{flag} {joined}')
    return ' '.join(parts + positional + flags)


def _shell_quote(s: str) -> str:
    """Quote a string for shell display only when needed."""
    # Conservative: quote anything containing shell-meaningful characters.
    if not s:
        return "''"
    safe = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./,=:")
    if all(c in safe for c in s):
        return s
    # Use single quotes; escape any embedded single quotes the POSIX way.
    return "'" + s.replace("'", "'\"'\"'") + "'"


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
                        help='Keep top N movesets after Phase 1 screening (default: 5). '
                             'Screening sims the stat-product rank 1 IV against '
                             'opponents for each candidate moveset, then keeps the '
                             'top N by average score. Only the survivors go through '
                             'the full 4096-IV sweep. Set to 0 to skip screening '
                             'and sweep all candidate movesets.')
    parser.add_argument('--shield-scenario', default='1,1', metavar='S1,S2',
                        help='Shield scenario as focal,opponent (default: 1,1). '
                             'Use "all" for all 9 scenarios (0v0 through 2v2), '
                             'or "even" for 0v0+1v1+2v2.')
    parser.add_argument('--shadow', action='store_true',
                        help='Focal species is shadow')
    parser.add_argument('--opp-ivs', default='pvpoke', choices=['pvpoke', 'rank1', 'both'],
                        help='Opponent IV selection: pvpoke (PvPoke default IVs, '
                             'what pvpoke.com uses), rank1 (stat product rank 1), '
                             'or both (run both, selectable in interactive HTML). '
                             'Default: pvpoke.')
    parser.add_argument('--thresholds', default=None, metavar='FILE',
                        help='Threshold file with spreads (stat-cutoff or IV-list) '
                             'and anchors (cmp, damage_breakpoint) for the species. '
                             'Accepts .toml (full schema; see docs/threshold_schema.md) '
                             'or legacy .json (flat stat-cutoff form, no anchors). '
                             'Extension auto-detected.')
    parser.add_argument('--anchor-file', default=None, metavar='FILE', action='append',
                        dest='anchor_files',
                        help='Additional threshold file merged on top of --thresholds. '
                             'Repeatable; later files win on name collision. '
                             'Use for one-off anchor experiments without editing '
                             'the canonical per-species file.')
    parser.add_argument('--anchor', default=None, metavar='SPEC', action='append',
                        dest='inline_anchors',
                        help='Inline anchor definition, format '
                             '"name:kind=K,key=value,...". Repeatable; last wins '
                             'on name collision. For inline cmp cohorts use '
                             'ivs=15/3/2;15/2/4;...  For Level 3 damage_breakpoint '
                             'moves filter use moves=COUNTER;LOW_KICK. '
                             'See docs/threshold_schema.md for full key reference.')
    parser.add_argument('--html', default=None, metavar='FILE',
                        help='Write interactive HTML plot to FILE')
    parser.add_argument('--interactive', action='store_true',
                        help='Generate interactive HTML with dropdowns for moveset, '
                             'shield scenario, and opp IV mode switching. '
                             'Runs all shield scenarios and reference moveset.')
    parser.add_argument('--reference', default='auto', metavar='SPEC',
                        help='Reference moveset for comparison: auto (PvPoke default, '
                             'shown in interactive mode), none (skip), or '
                             'FAST,CHARGED1,CHARGED2. Default: auto.')
    parser.add_argument('--standalone', action='store_true',
                        help='Inline Plotly.js into the HTML so the file works '
                             'offline with no CDN dependency (~4MB larger)')
    parser.add_argument('--screen-opponents', type=int, default=None, metavar='N',
                        help='Use only top N opponents for phase 1 screen '
                             '(default: same as --opponents)')
    parser.add_argument('--mirror-slayer', action=argparse.BooleanOptionalAction,
                        default=True,
                        help='Run iterative slayer discovery for the focal species '
                             '(Nash-style mirror match iteration). Adds ~2-5 min to '
                             'the deep dive but classifies survivors into Atk Slayer, '
                             'Bulk Slayer, and CMP Slayer categories. Results are '
                             'cached on disk for fast re-runs. ENABLED by default; '
                             'pass --no-mirror-slayer to skip.')
    parser.add_argument('--mirror-slayer-metric', default='all',
                        choices=['all', 'even', 'even-strict'],
                        help='Slayer iteration metric: "all" counts wins across all '
                             '9 scenarios (default), "even" counts only 0v0/1v1/2v2, '
                             '"even-strict" requires winning ALL 3 even scenarios.')
    parser.add_argument('--mirror-slayer-rounds', type=int, default=4,
                        help='Max rounds for mirror slayer iteration (default 4). '
                             'Set to 1 for "beat the typical opponent" mode (no '
                             'Nash iteration).')
    parser.add_argument('--mirror-slayer-pool', type=int, default=30,
                        help='Number of survivors to keep per iteration round '
                             '(default 30). Larger = more inclusive surviving '
                             'cohort, more IVs reported in final categories.')
    parser.add_argument('--mirror-slayer-show', type=int, default=20,
                        help='Number of IVs to show per category in final output '
                             '(default 20).')
    parser.add_argument('--no-cache', action='store_true',
                        help='Disable disk cache for slayer iteration')

    args = parser.parse_args()

    # Capture the equivalent command line for forensic reproducibility.
    # Printed to console and embedded in HTML output so any future reader can
    # see exactly what flags produced a given dive (including defaults that
    # have since changed).
    cli_args_str = format_cli_args(args, parser)
    print(f"CLI: {cli_args_str}")

    # Parse shield scenarios
    ALL_NINE = [(s0, s1) for s0 in range(3) for s1 in range(3)]
    EVEN_THREE = [(0, 0), (1, 1), (2, 2)]
    if args.shield_scenario == 'all':
        shield_scenarios = ALL_NINE
    elif args.shield_scenario == 'even':
        shield_scenarios = EVEN_THREE
    else:
        parts = args.shield_scenario.split(',')
        if len(parts) != 2:
            sys.exit("--shield-scenario must be S1,S2 (e.g. 1,1), 'all', or 'even'")
        shield_scenarios = [(int(parts[0]), int(parts[1]))]

    # Parse charged moves
    user_charged = None
    if args.charged:
        user_charged = [c.strip() for c in args.charged.split(',')]

    # Load thresholds.
    #
    # Two parallel representations are maintained during the transition from
    # the legacy flat-JSON format to the richer TOML spreads+anchors schema:
    #   - `threshold_registry`: full TOML-backed ThresholdRegistry (used by
    #     the new slayer anchor system via gopvpsim.anchors).
    #   - `thresholds`: legacy flat dict {name: {attack, defense, stamina}}
    #     that the existing tier-coloring / classify_iv / HTML tier rendering
    #     code paths expect. For TOML files we derive this via
    #     as_legacy_dict() from the registry; stat-cutoff spreads map 1:1,
    #     IV-list spreads are skipped (they have no stat-cutoff equivalent).
    thresholds = None
    threshold_registry = None
    if args.thresholds:
        try:
            threshold_registry = load_threshold_file(
                args.thresholds, species=args.species, league=args.league.capitalize(),
            )
        except Exception as e:
            print(f"  Warning: failed to load {args.thresholds}: {e}")
            threshold_registry = None

    # Overlay --anchor-file files on top (repeatable; later wins on collision)
    if threshold_registry is not None and args.anchor_files:
        from gopvpsim.thresholds import load_toml as _load_toml_overlay
        for overlay_path in args.anchor_files:
            try:
                overlay = _load_toml_overlay(overlay_path)
                threshold_registry = threshold_registry.merge(overlay)
                print(f"  Merged anchor-file overlay: {overlay_path}")
            except Exception as e:
                print(f"  Warning: failed to merge {overlay_path}: {e}")

    # Allow --anchor / --anchor-file to work without --thresholds by
    # starting from an empty registry.
    if threshold_registry is None and (args.anchor_files or args.inline_anchors):
        from gopvpsim.thresholds import ThresholdRegistry as _TR
        threshold_registry = _TR()

    # Apply --anchor inline flags (repeatable; last wins on collision)
    if threshold_registry is not None and args.inline_anchors:
        from gopvpsim.thresholds import (
            parse_inline_anchor, SpeciesThresholds, LeagueThresholds,
            ThresholdRegistry, IvListSpread, CmpAnchor,
        )
        # We build a synthetic one-species overlay containing all inline
        # anchors for this species/league, then merge it in.
        lt_overlay = LeagueThresholds(league=args.league.capitalize())
        for spec in args.inline_anchors:
            try:
                a_name, anchor = parse_inline_anchor(spec)
            except Exception as e:
                print(f"  Warning: --anchor {spec!r}: {e}")
                continue
            # If an inline cmp anchor carried its own IV list, inject a
            # synthetic spread that the anchor points at.
            inline_ivs = getattr(anchor, '_inline_ivs', None)
            if isinstance(anchor, CmpAnchor) and inline_ivs:
                spread_name = anchor.spread  # "__inline__<name>"
                lt_overlay.spreads[spread_name] = IvListSpread(
                    name=spread_name,
                    ivs=tuple(tuple(iv) for iv in inline_ivs),
                    description=f"Inline cohort for --anchor {a_name}",
                )
            lt_overlay.anchors[a_name] = anchor
            print(f"  Inline anchor: {a_name} ({anchor.kind})")
        if lt_overlay.spreads or lt_overlay.anchors:
            sp_overlay = SpeciesThresholds(
                species=args.species,
                leagues={args.league.capitalize(): lt_overlay},
            )
            overlay_reg = ThresholdRegistry(by_species={args.species: sp_overlay})
            threshold_registry = threshold_registry.merge(overlay_reg)

    # Derive the legacy flat dict for tier-coloring paths that still expect it.
    if threshold_registry is not None:
        thresholds = as_legacy_dict(
            threshold_registry, args.species, args.league.capitalize(),
        ) or None
        n_spreads = len(thresholds) if thresholds else 0
        n_anchors = 0
        sp = threshold_registry.species(args.species)
        if sp is not None:
            lt = sp.leagues.get(args.league.capitalize())
            if lt is not None:
                n_anchors = len(lt.anchors)
        if args.thresholds:
            print(f"  Thresholds: {n_spreads} stat-cutoff spread(s), "
                  f"{n_anchors} anchor(s) (from {args.thresholds})")

    print(f"\n{'='*60}")
    print(f"  {args.species}{'  (Shadow)' if args.shadow else ''} — "
          f"{args.league.title()} League IV Deep Dive")
    print(f"{'='*60}\n")

    # Enumerate movesets
    movesets = enumerate_movesets(args.species, args.fast, user_charged)
    print(f"  {len(movesets)} moveset combination(s) to evaluate")

    # Get opponents — from group or rankings
    # Always include the focal species so we can do mirror slayer analysis.
    opponent_label = None
    focal_in_opponents = False
    if args.group:
        group_entries = load_group(args.group)
        opponents = []
        opp_movesets_full = []
        for species_name, fast_move, charged_moves, is_shadow in group_entries:
            opponents.append(species_name)
            opp_movesets_full.append((fast_move, charged_moves))
            if species_name == args.species:
                focal_in_opponents = True
        # Append focal species if not already in group
        if not focal_in_opponents:
            try:
                focal_fast, focal_charged = get_default_moveset(
                    args.species, league=args.league, shadow=args.shadow)
                opponents.append(args.species)
                opp_movesets_full.append((focal_fast, focal_charged))
                focal_in_opponents = True
                print(f"  (added {args.species} to opponents for mirror analysis)")
            except (KeyError, ValueError):
                pass
        opponent_label = f"PvPoke group: {args.group} ({len(opponents)} mons)"
        print(f"  Opponents: {opponent_label}")
    else:
        screen_n = args.screen_opponents or args.opponents
        opponents = get_top_opponents(args.league, args.opponents)
        # Always include focal species for mirror analysis (append if not in top N)
        if args.species not in opponents:
            opponents.append(args.species)
            print(f"  (added {args.species} to opponents for mirror analysis)")
        focal_in_opponents = True
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

    opp_iv_labels = {'pvpoke': 'PvPoke defaults', 'rank1': 'rank 1 (stat product)', 'both': 'both (PvPoke + rank 1)'}
    opp_iv_label = opp_iv_labels.get(args.opp_ivs, args.opp_ivs)
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
    # For screening and the initial sweep, use 'pvpoke' when 'both' is requested
    opp_iv_mode = 'pvpoke' if args.opp_ivs == 'both' else args.opp_ivs
    surviving = screen_movesets(
        args.species, movesets, args.league, args.shadow,
        screen_opponents, screen_opp_movesets, shield_scenarios,
        args.top_movesets, opp_iv_mode=opp_iv_mode,
    )

    # Phase 2: Full IV sweep for each surviving moveset
    all_moveset_results = []
    main_slayer_iter_result = None  # populated by first moveset's --mirror-slayer pass
    for mi, (fast_id, charged_ids) in enumerate(surviving):
        label = moveset_label(fast_id, charged_ids)
        print(f"  Phase 2 [{mi+1}/{len(surviving)}]: {label}")
        print(f"    Simming 4096 IVs × {len(opponents)} opponents "
              f"× {len(shield_scenarios)} scenario(s)...")
        t0 = time.time()

        results, n_sims, canonical_scores, canonical_meta = iv_sweep(
            args.species, fast_id, charged_ids, args.league, args.shadow,
            opponents, opp_movesets_full, shield_scenarios,
            opp_iv_mode=opp_iv_mode,
        )

        elapsed = time.time() - t0
        rate = n_sims / elapsed if elapsed > 0 else 0
        print(f"    {n_sims:,} sims in {elapsed:.1f}s ({rate:,.0f} sims/s)")

        # Auto-discover thresholds from the first moveset if none provided
        if thresholds is None and mi == 0:
            auto = auto_discover_thresholds(results)
            if auto:
                thresholds = auto
                print(f"    Auto-discovered {len(thresholds)} threshold tier(s):")
                for name, thresh in thresholds.items():
                    print(f"      {name}: {_threshold_desc(thresh)}")

        # Slayer discovery: always check for mirror slayer thresholds on first moveset
        if mi == 0:
            mirror_idx = None
            for oi, opp_name in enumerate(opponents):
                if opp_name == args.species or opp_name.replace(' (Shadow)', '') == args.species:
                    mirror_idx = oi
                    break
            if mirror_idx is not None:
                slayer_thresh, slayer_scored = discover_slayer_thresholds(
                    results, mirror_idx, len(shield_scenarios), args.species
                )
                if slayer_scored:
                    # Community nicknames for slayer builds. Default = full species name.
                    SLAYER_NICKNAMES = {
                        'Annihilape': 'Ape',
                        'Galarian Stunfisk': 'GFisk',
                        'Stunfisk (Galarian)': 'GFisk',
                    }
                    short = SLAYER_NICKNAMES.get(args.species, args.species)
                    slayer_name = f'{short} Slayer'

                    max_wins = slayer_scored[0][0]
                    n_winners = sum(1 for w, _, _ in slayer_scored if w == max_wins)
                    n_total = len(slayer_scored)
                    n_scen = len(shield_scenarios)

                    if slayer_thresh and any(v > 0 for v in slayer_thresh.values()):
                        print(f"    {slayer_name}: {n_winners}/{n_total} IVs win {max_wins}/{n_scen} mirror scenarios")
                        print(f"      Required floor: {_threshold_desc(slayer_thresh)}")
                        # Cost analysis: best slayer IV's avg score vs best avg score IV
                        top_slayer = slayer_scored[0][2]
                        top_avg_iv = results[0]
                        avg_diff = top_slayer['avg_score'] - top_avg_iv['avg_score']
                        print(f"      Best slayer IV: {top_slayer['atk_iv']}/{top_slayer['def_iv']}/{top_slayer['sta_iv']} "
                              f"(avg score {top_slayer['avg_score']:.1f}, "
                              f"vs avg-best {top_avg_iv['avg_score']:.1f}, cost {avg_diff:+.1f})")
                        if thresholds is None:
                            thresholds = {}
                        if slayer_name not in thresholds:
                            new_thresholds = {slayer_name: slayer_thresh}
                            new_thresholds.update(thresholds)
                            thresholds = new_thresholds
                    elif max_wins == n_scen:
                        print(f"    {slayer_name}: all IVs win the mirror — no slayer threshold needed")
                    elif max_wins == 0:
                        print(f"    {slayer_name}: no IV beats the mirror")
                    else:
                        print(f"    {slayer_name}: {n_winners}/{n_total} IVs win {max_wins}/{n_scen} mirror scenarios "
                              f"but no clear stat floor distinguishes them")

        # Iterative slayer discovery (Nash-style) on the first moveset
        slayer_iter_result = None
        if mi == 0 and args.mirror_slayer and mirror_idx is not None:
            print(f"  Mirror slayer iteration (metric={args.mirror_slayer_metric}, "
                  f"max_rounds={args.mirror_slayer_rounds}):")
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from slayer_cache import SlayerCache, compute_cache_key
            base = get_species(args.species)
            base_stats_dict = {'atk': base['atk'], 'def': base['def'], 'hp': base['hp']}
            fast_moves_db, charged_moves_db = get_moves()
            cache_key = compute_cache_key(
                args.species, args.league, args.shadow,
                fast_moves_db.get(fast_id, {}),
                [charged_moves_db.get(cid, {}) for cid in charged_ids],
                base_stats_dict,
                shield_scenarios=shield_scenarios,
            )
            slayer_cache = SlayerCache(cache_key=cache_key, disk=not args.no_cache)

            # Round 0 opponent: PvPoke default
            try:
                _lv, da, dd, ds = pvpoke_default_ivs(args.species, league=args.league)
                initial_opp_iv = (da, dd, ds)
            except (KeyError, ValueError):
                initial_opp_iv = None

            if initial_opp_iv:
                t_iter = time.time()
                slayer_iter_result = iterative_slayer_discovery(
                    args.species, args.league, args.shadow,
                    fast_id, charged_ids, shield_scenarios,
                    initial_opp_iv,
                    max_rounds=args.mirror_slayer_rounds,
                    top_per_round=args.mirror_slayer_pool,
                    cache=slayer_cache,
                    metric=args.mirror_slayer_metric,
                )
                # Stash the metric/rounds for HTML rendering
                slayer_iter_result['metric'] = args.mirror_slayer_metric
                slayer_iter_result['max_rounds_arg'] = args.mirror_slayer_rounds
                slayer_cache.save()
                elapsed_iter = time.time() - t_iter
                print(f"    {slayer_iter_result['rounds_run']} rounds in {elapsed_iter:.1f}s "
                      f"({'converged' if slayer_iter_result['converged'] else 'max rounds'})")
                print(f"    {slayer_iter_result['cache_stats']}")
                # Show per-round top counts
                for ri, top in enumerate(slayer_iter_result['history']):
                    if not top:
                        continue
                    max_w = top[0]['total_wins']
                    n_at_max = sum(1 for r in top if r['total_wins'] == max_w)
                    # How many unique stat profiles (deduped opponents for next round)
                    n_unique = len({(round(r['atk'], 4), round(r['def_'], 4), int(r['hp'])) for r in top})
                    print(f"    Round {ri}: {len(top)} IVs in pool "
                          f"({n_unique} unique stat profiles, "
                          f"{n_at_max} at max wins {max_w}, "
                          f"top avg score: {top[0]['avg_score']:.1f})")

                # Resolve anchors so categorize_slayers can tag each survivor
                # with what it clears. Two layers feed the resolver:
                #   1. Explicit anchors from --thresholds + --anchor-file +
                #      --anchor (already in threshold_registry).
                #   2. Auto-generated fallback anchors (built per-run from
                #      the dive's opponent set + survivor cohort) for any
                #      anchor kind the user did NOT explicitly provide.
                survivors = slayer_iter_result['final']
                resolved = []
                if survivors:
                    try:
                        focal_entry_for_anchors = next(
                            m for m in load_gamemaster()['pokemon']
                            if m['speciesName'] == args.species
                        )
                        focal_types_for_anchors = parse_types(focal_entry_for_anchors)
                        fm_dict = fast_moves_db.get(fast_id) or {}
                        cm_dicts = [charged_moves_db[c] for c in charged_ids
                                    if c in charged_moves_db]
                        moves_for_anchors = []
                        if fm_dict:
                            moves_for_anchors.append(fm_dict)
                        moves_for_anchors.extend(cm_dicts)
                        # The BP scan range should span the full possible
                        # focal atk space for this species, not the cohort
                        # range. With a converged cohort atk range collapses
                        # to almost a single point and Level 3 enumeration
                        # finds nothing — the interesting BPs lie BELOW the
                        # cohort (already cleared by every survivor), and we
                        # want to tag each survivor with which ones it passes.
                        all_ivs = iv_rank(
                            args.species, league=args.league, shadow=args.shadow,
                        )
                        all_atks = [iv['atk'] for iv in all_ivs]
                        atk_min = min(all_atks)
                        atk_max = max(all_atks)
                        all_defs = [iv['def_'] for iv in all_ivs]
                        def_min = min(all_defs)
                        def_max = max(all_defs)

                        # Determine which anchor kinds the user already
                        # provided so the auto-fallback only fills gaps.
                        existing_kinds: set[str] = set()
                        if threshold_registry is not None:
                            sp_explicit = threshold_registry.species(args.species)
                            if sp_explicit is not None:
                                lt_explicit = sp_explicit.leagues.get(
                                    args.league.capitalize()
                                )
                                if lt_explicit is not None:
                                    for a in lt_explicit.anchors.values():
                                        existing_kinds.add(a.kind)

                        survivor_iv_tuples = [r['iv'] for r in survivors]
                        auto_overlay = build_auto_anchors(
                            species=args.species,
                            league=args.league,
                            opponent_species=list(opponents),
                            fast_move_id=fast_id,
                            survivor_ivs=survivor_iv_tuples,
                            existing_anchor_kinds=existing_kinds,
                        )
                        # Merge: auto is the base, explicit overlays it so
                        # any user-provided anchor wins on collision (we
                        # already gate by kind so collisions shouldn't
                        # happen, but defense in depth).
                        if threshold_registry is None:
                            effective_registry = auto_overlay
                        else:
                            effective_registry = auto_overlay.merge(threshold_registry)

                        # Count how many auto vs explicit for the log line
                        n_auto_anchors = 0
                        sp_auto = auto_overlay.species(args.species)
                        if sp_auto is not None:
                            lt_auto = sp_auto.leagues.get(
                                args.league.capitalize()
                            )
                            if lt_auto is not None:
                                n_auto_anchors = len(lt_auto.anchors)

                        resolved = resolve_anchors(
                            effective_registry, args.species, args.league,
                            moves_for_anchors, focal_types_for_anchors,
                            atk_min, atk_max,
                            def_min=def_min, def_max=def_max,
                            focal_shadow=args.shadow,
                        )
                        if resolved:
                            n_parents = len({r.parent for r in resolved})
                            n_auto_parents = len({
                                r.parent for r in resolved
                                if r.parent.startswith('auto_')
                            })
                            print(f"    Resolved {len(resolved)} anchors "
                                  f"({n_parents} parents, "
                                  f"{n_auto_parents} auto-generated)")
                    except Exception as e:
                        print(f"    Warning: anchor resolution failed: {e}")
                        resolved = []

                # Stash on the iter_result for HTML rendering
                slayer_iter_result['resolved_anchors'] = resolved

                categories = categorize_slayers(
                    survivors, resolved_anchors=resolved,
                )
                # Build cross-category map (IV -> set of category names)
                iv_categories = {}
                for cn, civs in categories.items():
                    for r in civs:
                        iv_categories.setdefault(r['iv'], set()).add(cn)
                CAT_AB = {'Atk Slayer': 'A', 'Bulk Slayer': 'B', 'CMP Slayer': 'C'}
                print(f"    Final survivors classified into "
                      f"{sum(1 for v in categories.values() if v)} categories:")
                for cat_name, cat_ivs in categories.items():
                    if not cat_ivs:
                        continue
                    # Console view: show top `mirror_slayer_show` per category
                    shown = cat_ivs[:args.mirror_slayer_show]
                    print(f"      {cat_name} ({len(shown)} of {len(cat_ivs)}):")
                    for r in shown:
                        a, d, s = r['iv']
                        others = sorted(iv_categories.get(r['iv'], set()) - {cat_name})
                        also = ' [+' + ''.join(CAT_AB.get(o, '?') for o in others) + ']' if others else ''
                        # Anchor-tag labels for Atk / CMP rows
                        tag_bits = []
                        for parent, subs in sorted(r.get('_anchor_tags', {}).items()):
                            labels = [a.label or a.name for a in subs]
                            tag_bits.append(f"{parent}[{','.join(labels)}]")
                        tag_str = ' ' + ' '.join(tag_bits) if tag_bits else ''
                        print(f"        {a:2d}/{d:2d}/{s:2d}  "
                              f"atk={r['atk']:.2f} def={r['def_']:.2f} hp={r['hp']}  "
                              f"wins {r['total_wins']}/"
                              f"{r['n_pairs']*len(shield_scenarios)} "
                              f"avg {r['avg_score']:.1f}{also}{tag_str}")
                # Stash for HTML rendering
                slayer_iter_result['categories'] = categories
                main_slayer_iter_result = slayer_iter_result

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

        all_moveset_results.append((fast_id, charged_ids, results,
                                     canonical_scores, canonical_meta))

    # HTML output
    if args.html:
        if args.interactive:
            # Interactive mode: embed all data, JS-driven dropdowns
            # Determine opp IV modes to run
            if args.opp_ivs == 'both':
                opp_iv_modes_to_run = ['pvpoke', 'rank1']
            else:
                opp_iv_modes_to_run = [opp_iv_mode]

            # Force all shield scenarios for interactive mode
            if shield_scenarios == [(1, 1)]:
                print("  Interactive mode: auto-expanding to all 9 shield scenarios")
                shield_scenarios = ALL_NINE
                # Re-run sweeps with all scenarios
                all_moveset_results = []
                for mi, (fast_id, charged_ids) in enumerate(surviving):
                    label = moveset_label(fast_id, charged_ids)
                    scores_by_mode = {}
                    meta = None
                    for mode in opp_iv_modes_to_run:
                        mode_label = 'PvPoke defaults' if mode == 'pvpoke' else 'rank 1'
                        print(f"  Interactive sweep [{mi+1}/{len(surviving)}] "
                              f"{label} (opp IVs: {mode_label}, all shields)...")
                        t0 = time.time()
                        results, n_sims, cs, cm = iv_sweep(
                            args.species, fast_id, charged_ids, args.league, args.shadow,
                            opponents, opp_movesets_full, shield_scenarios,
                            opp_iv_mode=mode,
                        )
                        elapsed = time.time() - t0
                        rate = n_sims / elapsed if elapsed > 0 else 0
                        print(f"    {n_sims:,} sims in {elapsed:.1f}s ({rate:,.0f} sims/s)")
                        scores_by_mode[mode] = cs
                        if meta is None:
                            meta = cm
                    all_moveset_results.append((fast_id, charged_ids, results,
                                                scores_by_mode, meta))
            else:
                # Already ran with the right scenarios, repack data
                new_results = []
                for fast_id, charged_ids, results, cs, cm in all_moveset_results:
                    scores_by_mode = {opp_iv_mode: cs}
                    # Run additional mode if needed
                    if args.opp_ivs == 'both':
                        other_mode = 'rank1' if opp_iv_mode == 'pvpoke' else 'pvpoke'
                        print(f"  Running {moveset_label(fast_id, charged_ids)} "
                              f"with opp IVs: {other_mode}...")
                        t0 = time.time()
                        _, n2, cs2, _ = iv_sweep(
                            args.species, fast_id, charged_ids, args.league, args.shadow,
                            opponents, opp_movesets_full, shield_scenarios,
                            opp_iv_mode=other_mode,
                        )
                        elapsed = time.time() - t0
                        print(f"    {n2:,} sims in {elapsed:.1f}s")
                        scores_by_mode[other_mode] = cs2
                    new_results.append((fast_id, charged_ids, results,
                                        scores_by_mode, cm))
                all_moveset_results = new_results

            # Resolve and run reference moveset
            reference_idx = -1
            ref_moveset = resolve_reference_moveset(
                args.species, args.league, args.shadow, args.reference)
            if ref_moveset:
                ref_fast, ref_charged = ref_moveset
                ref_label = moveset_label(ref_fast, ref_charged)
                # Check if reference is already a surviving moveset
                for mi, entry in enumerate(all_moveset_results):
                    existing_label = moveset_label(entry[0], entry[1])
                    if existing_label == ref_label:
                        reference_idx = mi
                        break
                if reference_idx < 0:
                    # Run reference sweep
                    print(f"  Reference sweep: {ref_label}")
                    ref_scores_by_mode = {}
                    ref_meta = None
                    for mode in opp_iv_modes_to_run:
                        t0 = time.time()
                        ref_results, ref_n, ref_cs, ref_cm = iv_sweep(
                            args.species, ref_fast, ref_charged, args.league, args.shadow,
                            opponents, opp_movesets_full, shield_scenarios,
                            opp_iv_mode=mode,
                        )
                        elapsed = time.time() - t0
                        rate = ref_n / elapsed if elapsed > 0 else 0
                        print(f"    {ref_n:,} sims in {elapsed:.1f}s ({rate:,.0f} sims/s)")
                        ref_scores_by_mode[mode] = ref_cs
                        if ref_meta is None:
                            ref_meta = ref_cm
                    reference_idx = len(all_moveset_results)
                    all_moveset_results.append((ref_fast, ref_charged, ref_results,
                                                ref_scores_by_mode, ref_meta))

            # Build moveset_data for interactive HTML
            moveset_data = []
            for entry in all_moveset_results:
                fast_id, charged_ids = entry[0], entry[1]
                scores_by_mode = entry[3]
                meta = entry[4]
                moveset_data.append({
                    'label': moveset_label_raw(fast_id, charged_ids),
                    'scores': scores_by_mode,
                    'meta': meta,
                })

            generate_interactive_html(
                args.species, args.league, moveset_data, args.html,
                thresholds=thresholds, opponent_label=opponent_label,
                shield_scenarios=shield_scenarios,
                opponent_names=opponents,
                opp_iv_modes=opp_iv_modes_to_run,
                reference_idx=reference_idx,
                standalone=args.standalone,
                slayer_iter_result=main_slayer_iter_result,
                cli_args_str=cli_args_str,
            )
        else:
            # Static mode (original behavior)
            generate_html(args.species, args.league, all_moveset_results, args.html,
                          thresholds=thresholds, opponent_label=opponent_label,
                          shield_scenarios=shield_scenarios,
                          opponent_names=opponents, opp_iv_mode=opp_iv_mode,
                          standalone=args.standalone,
                          cli_args_str=cli_args_str)

    print("Done.\n")


if __name__ == '__main__':
    main()
