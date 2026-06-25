"""Mirror-slayer iteration and slayer archetype classification.

Iterative slayer discovery: repeatedly simulate the focal species against
its own top meta picks, converging on a mirror opponent population. The
population's role is to supply per-IV mirror performance and the CMP%
denominator — the first-class outputs are the two slayer archetypes built
by ``build_slayer_archetypes`` (Anchors-First and CMP-First), which are
closed-form over the anchor resolver and need no extra sims.
"""
import multiprocessing
import os
import sys

from gopvpsim.pokemon import (
    Pokemon, best_level, CPM,
    LEAGUE_CAPS, LEAGUE_MAX_LEVEL,
)
from gopvpsim.moves import get_moves, type_effectiveness
from gopvpsim.data import load_gamemaster, load_rankings, get_default_moveset, parse_types
from gopvpsim.battle import BattlePokemon, simulate, pvpoke_dp, pvpoke_simulate_shield
from gopvpsim.formchange import attach_form_change
from gopvpsim.anchors import resolve_anchors, tag_iv, ResolvedAnchor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deep_dive_logging import get_logger, worker_log_setup

logger = get_logger()


# Injected by deep_dive.py after import (defined there, used here).
compute_iv_metadata = None

# Shared worker state for multiprocessing pool
_worker_state = {}


def discover_slayer_thresholds(results, opponent_idx, n_scenarios):
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
        import logging
        logging.getLogger('deep_dive').debug(
            f'discover_slayer_thresholds: only '
            f'{len(results) if results else 0} results (<50); '
            f'skipping threshold discovery')
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


def slayer_worker_init(species, focal_types,
                         max_cp, shadow, fm_template, cms_template,
                         shield_scenarios, log_path=None, verbose=False,
                         focal_mon=None):
    worker_log_setup(log_path, verbose=verbose)
    _slayer_state['species'] = species
    _slayer_state['focal_types'] = focal_types
    _slayer_state['max_cp'] = max_cp
    _slayer_state['shadow'] = shadow
    _slayer_state['fm_template'] = fm_template
    _slayer_state['cms_template'] = cms_template
    _slayer_state['shield_scenarios'] = shield_scenarios
    _slayer_state['focal_mon'] = focal_mon


def slayer_iter_worker(args):
    """
    Process a chunk of focal stat profiles against a list of opponent IVs.
    Returns dict of (profile_key, opp_iv_idx) -> tuple of scores.
    profile_key is a (atk, def_, hp) tuple. The parent expands these to
    all matching focal_idx values.
    """
    focal_profile_chunk, opponents = args
    # focal_profile_chunk: list of (profile_key, atk, def_, hp, a, d, s, lv)
    # opponents: list of (opp_iv_idx, (opp_atk, opp_def, opp_hp, a, d, s, lv))
    ws = _slayer_state
    species = ws['species']
    focal_types = ws['focal_types']
    fm_template = ws['fm_template']
    cms_template = ws['cms_template']
    shield_scenarios = ws['shield_scenarios']
    focal_mon = ws['focal_mon']
    league_cp = ws['max_cp']
    shadow = ws['shadow']

    results = {}
    for profile_key, atk_stat, def_stat, hp_stat, a_iv, d_iv, s_iv, lv in focal_profile_chunk:
        for opp_iv_idx, opp_data in opponents:
            opp_atk, opp_def, opp_hp, opp_a, opp_d, opp_s, opp_lv = opp_data
            scores = []
            # One BattlePokemon pair per (profile, opponent), reset between
            # scenarios — keeps the damage/DP caches warm across the
            # shield-scenario axis instead of rebuilding them per sim.
            bp0 = BattlePokemon(
                species=species, types=focal_types,
                atk=atk_stat, def_=def_stat, max_hp=hp_stat,
                shadow=shadow,
                fast_move=dict(fm_template),
                charged_moves=[dict(cm) for cm in cms_template],
            )
            attach_form_change(bp0, focal_mon, a_iv, d_iv, s_iv, lv,
                               league_cp, shadow)
            bp1 = BattlePokemon(
                species=species, types=focal_types,
                atk=opp_atk, def_=opp_def, max_hp=opp_hp,
                shadow=shadow,
                fast_move=dict(fm_template),
                charged_moves=[dict(cm) for cm in cms_template],
            )
            attach_form_change(bp1, focal_mon, opp_a, opp_d, opp_s, opp_lv,
                               league_cp, shadow)
            for s_focal, s_opp in shield_scenarios:
                bp0.reset_for_battle(s_focal, opponent=bp1)
                bp1.reset_for_battle(s_opp, opponent=bp0)
                res = simulate(bp0, bp1,
                               charged_policy_0=pvpoke_dp,
                               charged_policy_1=pvpoke_dp)
                scores.append(round(res.pvpoke_score(0)))
            results[(profile_key, opp_iv_idx)] = tuple(scores)
    return results


def build_focal_meta(species, league, shadow, iv_floor=None,
                     focal_max_level=None):
    """Compute (atk, def, hp, iv_idx) for all valid focal IVs.

    Returns (iv_to_idx, iv_meta_tuples) where iv_meta_tuples is a list of
    (a, d, s, atk, def, hp, level). Thin wrapper around compute_iv_metadata
    for backwards compatibility with the slayer iteration code. ``iv_floor``
    is passed through to prune the focal IV space. ``focal_max_level`` raises
    the level cap (best-buddy/L51); since BOTH mirror sides are built from this
    meta, it lifts the whole cohort to the best-buddy level for a like-for-like
    best-buddy mirror.
    """
    iv_meta_dicts = compute_iv_metadata(species, league, shadow=shadow,
                                        iv_floor=iv_floor,
                                        focal_max_level=focal_max_level)
    iv_to_idx = {}
    iv_meta = []
    for idx, m in enumerate(iv_meta_dicts):
        iv_to_idx[(m['atk_iv'], m['def_iv'], m['sta_iv'])] = idx
        iv_meta.append((m['atk_iv'], m['def_iv'], m['sta_iv'],
                        m['atk'], m['def_'], m['hp'], m['level']))
    return iv_to_idx, iv_meta


def _cut_pool(focal_scores, top_per_round):
    """Cut a sorted focal_scores list to the round pool.

    Takes the top ``top_per_round`` rows and extends only through rows that
    EXACTLY tie the cutoff row's (frac_wins, avg_score) key. With the graded
    metric, exact ties are rare, so the pool cap holds — unlike the old
    keep-all-at-cutoff-win-count rule, which kept thousands of integer-tied
    rows and made Round 1 cost ~80% of a dive's sim budget.
    """
    if len(focal_scores) <= top_per_round:
        return list(focal_scores)
    cut = focal_scores[top_per_round - 1]
    cut_key = (cut['frac_wins'], cut['avg_score'])
    top = focal_scores[:top_per_round]
    for r in focal_scores[top_per_round:]:
        if (r['frac_wins'], r['avg_score']) != cut_key:
            break  # sorted input — ties with the cutoff row are contiguous
        top.append(r)
    return top


def iterative_slayer_discovery(species, league, shadow, fast_id, charged_ids,
                                shield_scenarios, initial_opp_iv,
                                max_rounds=4, top_per_round=10, cache=None,
                                metric='all', iv_floor=None,
                                log_path=None, verbose=False,
                                reserve_cpus=0, focal_max_level=None):
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
        'all_scores': dict keyed by (a, d, s) IV triple -> (total_wins,
                      frac_wins, avg_score, n_pairs) for EVERY focal IV,
                      scored against the last round's opponent population.
                      This is
                      the per-IV mirror-performance surface the archetype
                      builder and the winsMirror y-axis consume — the Nash
                      cohort's role is supplying this population, not being
                      the optimization target.
        'rounds_run': how many rounds executed
        'converged': bool
        'cache_stats': string from cache
    """
    import multiprocessing
    # slayer_cache is in the same scripts/ directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from slayer_cache import SlayerCache

    iv_to_idx, iv_meta = build_focal_meta(species, league, shadow,
                                            iv_floor=iv_floor,
                                            focal_max_level=focal_max_level)
    n_focal = len(iv_meta)

    fast_moves_db, charged_moves_db = get_moves()
    fm_template = dict(fast_moves_db[fast_id])
    cms_template = [dict(charged_moves_db[cid]) for cid in charged_ids]

    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
    focal_types = parse_types(focal_mon)

    max_cp = LEAGUE_CAPS[league]

    if cache is None:
        cache = SlayerCache(disk=False)

    # Pre-compute focal profile groups: profile_key -> list of focal_idx values
    # IVs with identical (atk, def, hp) produce identical battles, so we only
    # need to sim one representative per profile and copy the result to the rest.
    # EXCEPT for form-change species: the alt form's stats depend on the raw
    # IVs + level (Blade-side whole-level rounding), so every IV spread sims
    # separately (measured cost 1.1-1.35x more profiles).
    form_per_iv = focal_mon.get('formChange') is not None

    def _profile_key(focal_idx):
        a_, d_, s_, at, df, hp, lv = iv_meta[focal_idx]
        pk = (round(at, 4), round(df, 4), int(hp))
        if form_per_iv:
            pk += (a_, d_, s_, lv)
        return pk

    focal_profile_to_ivs = {}  # profile_key -> [focal_idx, ...]
    focal_profile_data = {}    # profile_key -> (atk, def, hp, a, d, s, lv)
    for focal_idx in range(n_focal):
        a_, d_, s_, at, df, hp, lv = iv_meta[focal_idx]
        pk = _profile_key(focal_idx)
        focal_profile_to_ivs.setdefault(pk, []).append(focal_idx)
        if pk not in focal_profile_data:
            focal_profile_data[pk] = (at, df, hp, a_, d_, s_, lv)
    n_unique_profiles = len(focal_profile_data)

    # Round 0: initial opponent IV
    initial_iv = initial_opp_iv  # (a, d, s)
    if initial_iv not in iv_to_idx:
        # Initial opponent not in our IV list (shouldn't happen)
        return {'error': f'Initial opponent IV {initial_iv} not in valid IVs'}

    current_opponent_indices = [iv_to_idx[initial_iv]]
    history = []
    converged = False
    last_focal_scores = []

    import time as _time
    n_workers = min(max(1, multiprocessing.cpu_count() - reserve_cpus), 16)
    total_round_sims = 0  # accumulated across rounds for an estimate

    for round_idx in range(max_rounds):
        round_start = _time.time()
        # Build opponent meta (atk, def, hp, a, d, s, lv) for current
        # round's opponents (IVs + level feed attach_form_change in the
        # worker; no-op for species without form changes)
        opp_data_list = []
        for opp_idx in current_opponent_indices:
            a, d, s, atk_, def_, hp_, lv = iv_meta[opp_idx]
            opp_data_list.append((opp_idx, (atk_, def_, hp_, a, d, s, lv)))

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
            profile_list = [(pk, *dat)
                            for pk, dat in focal_profile_data.items()]
            # Split into ~100 chunks (capped by len(profile_list)). With
            # imap_unordered the pool grabs the next chunk as workers free
            # up — finer granularity → more frequent progress reports and
            # better load balancing on uneven workloads.
            n_chunks_target = 100
            chunk_size = max(1, (len(profile_list) + n_chunks_target - 1) // n_chunks_target)
            chunks = [profile_list[i:i+chunk_size] for i in range(0, len(profile_list), chunk_size)]

            init_args = (species, focal_types,
                         max_cp, shadow, fm_template, cms_template,
                         shield_scenarios, log_path, verbose, focal_mon)
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

        # Score each focal IV vs current opponents. Two metrics per IV:
        #   total_wins — integer scenario-win count (display continuity).
        #   frac_wins  — graded per-opponent credit (scenarios won / counted
        #                scenarios), summed across opponents. Same fractional
        #                formulation as the Matchups Kept column (bb6f63e).
        #                Integer win counts vs few opponents produce massive
        #                exact ties (the Round-1 8.2M-sim explosion, 2026-06-10);
        #                the fractional metric plus avg-score tiebreak makes
        #                ties rare so --mirror-slayer-pool is actually honored.
        focal_scores = []
        for focal_idx in range(n_focal):
            total_wins = 0
            total_frac = 0.0
            total_score = 0
            n_pairs = 0
            for opp_idx, _ in opp_data_list:
                cached = cache.get(focal_idx, opp_idx)
                if cached is None:
                    continue

                if metric == 'even':
                    wins = sum(1 for i in even_indices if cached[i] >= 500)
                    frac = wins / n_even if n_even else 0.0
                elif metric == 'even-strict':
                    # Counts only IVs that win ALL even scenarios vs this opponent
                    won_all_even = all(cached[i] >= 500 for i in even_indices)
                    wins = n_even if won_all_even else 0
                    frac = 1.0 if won_all_even else 0.0
                else:  # 'all' and any unknown metric
                    wins = sum(1 for s in cached if s >= 500)
                    frac = wins / len(cached) if cached else 0.0

                avg = sum(cached) / len(cached)
                total_wins += wins
                total_frac += frac
                total_score += avg
                n_pairs += 1
            if n_pairs == 0:
                continue
            avg_score = total_score / n_pairs
            a, d, s, atk_, def_, hp_, _lv = iv_meta[focal_idx]
            focal_scores.append({
                'focal_idx': focal_idx,
                'iv': (a, d, s),
                'atk': atk_, 'def_': def_, 'hp': hp_,
                'total_wins': total_wins,
                'frac_wins': total_frac,
                'avg_score': avg_score,
                'n_pairs': n_pairs,
            })

        # Sort by fractional wins desc, then avg score desc
        focal_scores.sort(key=lambda x: (-x['frac_wins'], -x['avg_score']))

        top = _cut_pool(focal_scores, top_per_round)

        last_focal_scores = focal_scores
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
        # (Form-change species use the per-IV _profile_key, so no two
        # distinct IV spreads collapse there.)
        seen_profiles = {}
        for r in top:
            profile = _profile_key(r['focal_idx'])
            if profile not in seen_profiles:
                seen_profiles[profile] = r['focal_idx']
        current_opponent_indices = list(seen_profiles.values())

    return {
        'history': history,
        'final': history[-1] if history else [],
        'all_scores': {
            r['iv']: (r['total_wins'], r['frac_wins'], r['avg_score'],
                      r['n_pairs'])
            for r in last_focal_scores
        },
        'rounds_run': len(history),
        'converged': converged,
        'cache_stats': cache.stats(),
    }


def build_slayer_archetypes(results, resolved_anchors=None, iter_result=None,
                            top_mirror_n=50, cmp_first_n=20):
    """Classify the full IV space into the two first-class slayer archetypes.

    Both archetypes are sim-free given the anchor resolver and the sweep
    results — anchor membership is closed-form from (atk, def), and CMP% is
    an atk comparison against an opponent population. The Nash iteration's
    role is reduced to supplying per-IV mirror performance (via
    ``iter_result['all_scores']``) and the niche Nash-cohort CMP column;
    it is no longer the optimization target.

    Archetype 1 — **Anchors-First Slayer**: hit the important break/bulk
        points first, then win CMP as much as possible. Members = IVs that
        clear the maximum achievable number of *counted* anchor parents;
        ranked by Top-Mirror CMP%, then atk.
    Archetype 2 — **CMP-First Slayer** (the "lab mon"): win CMP as the first
        priority, pick up anchors as a secondary goal. Members = top
        ``cmp_first_n`` rows by (atk, avg_score). No anchor filter — the
        per-row checklist reports what each spread clears vs sacrifices.

    Counted parents: explicit (non-``auto_``) parents always count;
    auto-generated parents count only when selective (cleared by < 50% of
    the IV space). This is the slayer-card signal-loss fix — an auto anchor
    that everyone clears can't define the archetype.

    Args:
        results: full per-IV sweep result dicts (must carry atk_iv/def_iv/
            sta_iv, atk, def_, hp, avg_score; level/cp optional).
        resolved_anchors: list of ResolvedAnchor from resolve_anchors().
        iter_result: dict from iterative_slayer_discovery (may be None);
            supplies 'all_scores' (mirror wins) and 'final' (Nash cohort).
        top_mirror_n: cohort size for Top-Mirror CMP% (matches the JS
            TOP_MIRROR_N so the table column agrees with the Top IVs table).
        cmp_first_n: CMP-First membership cap.

    Returns dict of archetype name -> list of row dicts sorted by the
    archetype's lexicographic key. Rows carry the survivor-dict shape
    (iv, atk, def_, hp, total_wins, avg_score, _anchor_tags) plus
    frac_wins, n_parents_cleared, n_counted_parents, top_mirror_cmp,
    nash_cmp. Anchors-First is empty when no counted parent is cleared
    by any IV (renderer hides it).
    """
    if not results:
        return {}
    resolved_anchors = resolved_anchors or []
    n = len(results)

    # Tag every IV; tally per-parent pass rates over the full IV space.
    tags_by_i = []
    parent_pass_counts: dict = {}
    for r in results:
        tags = tag_iv(r['atk'], r['def_'], resolved_anchors)
        tags_by_i.append(tags)
        for parent in tags:
            parent_pass_counts[parent] = parent_pass_counts.get(parent, 0) + 1

    counted_parents = set()
    for a in resolved_anchors:
        p = a.parent
        if p in counted_parents:
            continue
        if p.startswith('auto_'):
            rate = parent_pass_counts.get(p, 0) / n
            if rate >= 0.5:
                continue  # non-selective auto anchor — everyone clears it
        counted_parents.add(p)

    # CMP% helpers — semantics match the JS (_computeTopMirrorCmpPct /
    # _computeMirrorCmpPct): both sides rounded to 2dp, ties count as
    # beats, focal included in its own cohort.
    from bisect import bisect_right

    def _cmp_pct(atk, cohort_sorted):
        if not cohort_sorted:
            return None
        return 100.0 * bisect_right(cohort_sorted, round(atk, 2)) / len(cohort_sorted)

    by_score = sorted(results, key=lambda r: -r['avg_score'])
    top_mirror_atks = sorted(round(r['atk'], 2) for r in by_score[:top_mirror_n])
    nash_atks = []
    if iter_result and iter_result.get('final'):
        nash_atks = sorted(round(s['atk'], 2) for s in iter_result['final']
                           if s.get('atk') is not None)
    all_scores = (iter_result or {}).get('all_scores') or {}

    rows = []
    for i, r in enumerate(results):
        triple = (r['atk_iv'], r['def_iv'], r['sta_iv'])
        tags = tags_by_i[i]
        n_cleared = sum(1 for p in tags if p in counted_parents)
        mw = all_scores.get(triple)
        rows.append({
            'iv': triple,
            'atk': r['atk'], 'def_': r['def_'], 'hp': r['hp'],
            'level': r.get('level'), 'cp': r.get('cp'),
            'avg_score': r['avg_score'],
            'total_wins': mw[0] if mw else 0,
            'frac_wins': mw[1] if mw else 0.0,
            'n_pairs': mw[3] if mw else 0,
            '_anchor_tags': tags,
            'n_parents_cleared': n_cleared,
            'n_counted_parents': len(counted_parents),
            'top_mirror_cmp': _cmp_pct(r['atk'], top_mirror_atks),
            'nash_cmp': _cmp_pct(r['atk'], nash_atks),
        })

    anchors_first: list = []
    if counted_parents:
        max_cleared = max(r['n_parents_cleared'] for r in rows)
        if max_cleared > 0:
            anchors_first = [r for r in rows
                             if r['n_parents_cleared'] == max_cleared]
            anchors_first.sort(
                key=lambda r: (-(r['top_mirror_cmp'] or 0), -r['atk'],
                               -r['avg_score']))

    cmp_first = sorted(rows, key=lambda r: (-round(r['atk'], 2),
                                            -r['avg_score']))[:cmp_first_n]

    return {
        'Anchors-First Slayer': anchors_first,
        'CMP-First Slayer': cmp_first,
    }


# ---------------------------------------------------------------------------
# Structured IV categories — unified registry over slayer categories,
# threshold tiers, and their intersections (composites). Future kinds:
# 'matchup' for "beats opp X in scenario Y" categories once the
# baiting-axis sweep TODO lands.
# ---------------------------------------------------------------------------
