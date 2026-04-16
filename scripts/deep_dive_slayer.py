"""Mirror-slayer iteration and IV categorization.

Iterative slayer discovery: repeatedly simulate the focal species against
its own top meta picks, converging on the IV cohort that wins the most
mirror-like matchups. The surviving IVs are then categorized into named
groups (Atk Slayer, CMP Slayer, Bulk Slayer) based on their stat profiles
and anchor pass/fail patterns.
"""
import multiprocessing
import os
import sys

from gopvpsim.pokemon import (
    Pokemon, get_species, best_level, CPM,
    LEAGUE_CAPS, LEAGUE_MAX_LEVEL,
)
from gopvpsim.moves import get_moves, type_effectiveness
from gopvpsim.data import load_gamemaster, load_rankings, get_default_moveset, parse_types
from gopvpsim.battle import BattlePokemon, simulate, pvpoke_dp, pvpoke_simulate_shield
from gopvpsim.anchors import resolve_anchors, tag_iv, ResolvedAnchor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deep_dive_logging import get_logger, worker_log_setup

logger = get_logger()


# Injected by deep_dive.py after import (defined there, used here).
compute_iv_metadata = None

# Shared worker state for multiprocessing pool
_worker_state = {}


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


def slayer_worker_init(species, focal_types, base_atk, base_def, base_sta,
                         max_cp, shadow, fm_template, cms_template,
                         shield_scenarios, log_path=None, verbose=False):
    worker_log_setup(log_path, verbose=verbose)
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


def slayer_iter_worker(args):
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


def build_focal_meta(species, league, shadow, iv_floor=None):
    """Compute (atk, def, hp, iv_idx) for all valid focal IVs.

    Returns (iv_to_idx, iv_meta_tuples) where iv_meta_tuples is a list of
    (a, d, s, atk, def, hp). Thin wrapper around compute_iv_metadata for
    backwards compatibility with the slayer iteration code. ``iv_floor``
    is passed through to prune the focal IV space.
    """
    iv_meta_dicts = compute_iv_metadata(species, league, shadow=shadow,
                                        iv_floor=iv_floor)
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
                                metric='all', iv_floor=None,
                                log_path=None, verbose=False):
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

    iv_to_idx, iv_meta = build_focal_meta(species, league, shadow,
                                            iv_floor=iv_floor)
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
            logger.info(f"    Round {round_idx}: {len(opp_data_list)} opponents "
                        f"({len(opps_needing_sim)} need sim), "
                        f"{n_profiles} unique focal profiles, "
                        f"~{n_round_sims:,} sims to run")

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
                         max_cp, shadow, fm_template, cms_template,
                         shield_scenarios, log_path, verbose)
            sim_start = _time.time()
            with multiprocessing.Pool(
                processes=n_workers,
                initializer=slayer_worker_init,
                initargs=init_args,
            ) as pool:
                worker_args = [(chunk, opps_needing_sim) for chunk in chunks]
                # Use imap_unordered so we can report progress as workers finish
                chunk_results = []
                completed = 0
                last_print = sim_start
                for result in pool.imap_unordered(slayer_iter_worker, worker_args):
                    chunk_results.append(result)
                    completed += 1
                    now = _time.time()
                    # Print every 10s or every chunk, whichever is less frequent
                    if now - last_print >= 10 or completed == len(chunks):
                        elapsed = now - sim_start
                        frac = completed / len(chunks)
                        eta = (elapsed / frac) * (1 - frac) if frac > 0 else 0
                        logger.info(f"      sim progress: {completed}/{len(chunks)} chunks "
                                    f"({frac*100:.0f}%), elapsed {elapsed:.0f}s, "
                                    f"eta {eta:.0f}s")
                        last_print = now

            sim_elapsed = _time.time() - sim_start
            logger.info(f"      sim done in {sim_elapsed:.1f}s "
                        f"({n_round_sims / max(sim_elapsed, 0.01):,.0f} sims/s)")

            # Merge into cache, expanding profile results to all matching focal IVs
            merge_start = _time.time()
            for chunk in chunk_results:
                for (profile_key, opp_idx), scores in chunk.items():
                    for focal_idx in focal_profile_to_ivs[profile_key]:
                        cache.put(focal_idx, opp_idx, scores)
            merge_elapsed = _time.time() - merge_start
            if merge_elapsed > 1.0:
                logger.info(f"      cache merge: {merge_elapsed:.1f}s")
        else:
            logger.info(f"    Round {round_idx}: {len(opp_data_list)} opponents, all cache hits")

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


# ---------------------------------------------------------------------------
# Structured IV categories — unified registry over slayer categories,
# threshold tiers, and their intersections (composites). Future kinds:
# 'matchup' for "beats opp X in scenario Y" categories once the
# baiting-axis sweep TODO lands.
# ---------------------------------------------------------------------------
