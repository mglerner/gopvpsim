"""Boundary/flip analysis engine for IV deep dives.

Pure-analysis functions that partition IV cohorts by stat thresholds
(anchors, matchup boundaries) and detect matchup flips. No HTML
rendering — that stays in deep_dive.py.
"""
import math
import re

import numpy as np

from gopvpsim.moves import BONUS, STAB_MULTIPLIER, type_effectiveness


# Module-level caches for numpy conversions of per-dive IV/score arrays.
# The narrative + tier-cutoff probes are called repeatedly with the same
# data_obj / score_arrays dicts within a dive; converting once amortises
# the ~25ms-per-score-array asarray+reshape over all calls. Keyed by
# id() of the host dict, with each entry ALSO holding a strong reference
# to that dict: the reference pins the object alive, so its id() can
# never be reused by a different dict, and the identity check on read
# makes a collision impossible even if a future "compare dive A vs B"
# path keeps several host dicts live at once (arc S4 fix for the
# id-reuse fragility flagged in project_post_ship_cleanup_pain_points
# #7). Entries persist until _invalidate_np_caches(); dive processes
# host a handful of dicts so the pinning cost is negligible, and tests
# clear between fixtures.
_STAT_NP_CACHE: dict = {}
_SCORE_NP_CACHE: dict = {}


def _np_stats(data_obj):
    """Return (ivAtk, ivDef, ivHp) as numpy arrays, cached per data_obj."""
    key = id(data_obj)
    cached = _STAT_NP_CACHE.get(key)
    if cached is not None and cached[0] is data_obj:
        return cached[1]
    atk = np.asarray(data_obj['ivAtk'])
    def_ = np.asarray(data_obj['ivDef'])
    hp = np.asarray(data_obj['ivHp'])
    _STAT_NP_CACHE[key] = (data_obj, (atk, def_, hp))
    return (atk, def_, hp)


def _np_scores(score_arrays_all, moveset_idx, mode, nIvs, nS, nO):
    """Return reshaped (nIvs, nS, nO) score array, or None if missing.

    Caches per (id(score_arrays_all), moveset_idx, mode); the host dict
    is pinned by the entry (see cache comment above).
    """
    key = (id(score_arrays_all), moveset_idx, mode)
    cached = _SCORE_NP_CACHE.get(key)
    if cached is not None and cached[0] is score_arrays_all:
        return cached[1]
    raw = score_arrays_all.get(f'{moveset_idx}_{mode}')
    if raw is None or len(raw) == 0:
        return None
    arr = np.asarray(raw).reshape(nIvs, nS, nO)
    _SCORE_NP_CACHE[key] = (score_arrays_all, arr)
    return arr


def _invalidate_np_caches():
    """Clear the module-level numpy caches. Tests call this between fixtures."""
    _STAT_NP_CACHE.clear()
    _SCORE_NP_CACHE.clear()


# ---- Utility helpers ----

def pretty_name(raw_id):
    """Convert GIGATON_HAMMER to Gigaton Hammer, FAIRY_WIND to Fairy Wind, etc."""
    return raw_id.replace('_', ' ').title()


def pretty_moveset(label):
    """Convert 'FAIRY_WIND / BULLDOZE, GIGATON_HAMMER' to pretty names."""
    parts = label.split(' / ')
    if len(parts) == 2:
        fast = pretty_name(parts[0].strip())
        charged = ', '.join(pretty_name(c.strip()) for c in parts[1].split(','))
        return f'{fast} / {charged}'
    return label


def pvp_damage(power, atk, def_, effectiveness, stab_mult):
    """PvP damage formula: floor(0.5 * BONUS * power * atk/def * eff * stab) + 1

    Uses the canonical float32-truncated BONUS from moves.py (not a literal
    1.3) so per-hit damage agrees with the engine bit-for-bit at floor()
    boundaries. Callers must build stab_mult from moves.STAB_MULTIPLIER and
    effectiveness from moves.type_effectiveness for the match to hold.
    """
    return math.floor(0.5 * BONUS * power * atk / def_ * effectiveness * stab_mult) + 1


def build_move_tuples(moveset_label, fast_db, charged_db):
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


def stat_cutoffs_from_anchors(anchor_objs):
    """Best-effort stat_cutoffs derived from a bag of ResolvedAnchor.

    Picks the *minimum* threshold per target_stat (the easiest tier to
    clear) so the cutoff reflects the floor that membership in this
    category implies. Returns ``{'atk': float|None, 'def': float|None,
    'hp': None}`` (HP isn't a target_stat for any anchor today).
    Returns None if no anchor has a numeric threshold (pure CMP without
    a numeric threshold_value, etc.).
    """
    atk_vals = [a.threshold_value for a in anchor_objs
                if getattr(a, 'target_stat', None) == 'atk'
                and getattr(a, 'threshold_value', None) is not None]
    def_vals = [a.threshold_value for a in anchor_objs
                if getattr(a, 'target_stat', None) == 'def'
                and getattr(a, 'threshold_value', None) is not None]
    if not atk_vals and not def_vals:
        return None
    return {
        'atk': min(atk_vals) if atk_vals else None,
        'def': min(def_vals) if def_vals else None,
        'hp': None,
    }


# ---- Core analysis functions ----

def find_flips(scores_flat, nIvs, nS, nO, ref_iv, test_ivs, scenarios, opponents,
               bait_mode='bait'):
    """Find matchup flips (crossing 500-point boundary) for test IVs vs reference.

    Each gain/loss entry includes a ``bait_modes`` set so callers can tell
    which bait policy produced the flip after merging across modes.
    """
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
                             'opponent': opponents[oi], 'ref_score': rs, 'iv_score': ts,
                             'bait_modes': {bait_mode}}
                    (gains if ts >= 500 else losses).append(entry)
        if gains or losses:
            flips[iv] = {'gains': gains, 'losses': losses}
    return flips


def merge_flip_dicts(base, new):
    """Merge two flip dicts, unioning ``bait_modes`` on (opponent, scenario) collision.

    Each dict maps ``iv -> {'gains': [...], 'losses': [...]}``.  Entries from
    *new* are merged into *base* in-place.  When the same (opponent, scenario)
    flip appears in both dicts for the same IV and direction, the ``bait_modes``
    sets are unioned rather than creating a duplicate entry.

    Returns *base* for convenience.
    """
    for iv, fd in new.items():
        if iv not in base:
            base[iv] = fd
            continue
        for direction in ('gains', 'losses'):
            existing = base[iv][direction]
            idx = {(e['opponent'], e['scenario']): i for i, e in enumerate(existing)}
            for entry in fd[direction]:
                key = (entry['opponent'], entry['scenario'])
                if key in idx:
                    existing[idx[key]]['bait_modes'] |= entry['bait_modes']
                else:
                    existing.append(entry)
                    idx[key] = len(existing) - 1
    return base


def narrate_flip(focal_atk, focal_def, focal_hp, ref_atk, ref_def, ref_hp,
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
            stab_mult = STAB_MULTIPLIER if mtype in opp_types else 1.0
            dmg_ref = pvp_damage(power, opp_atk, ref_def, eff, stab_mult)
            dmg_focal = pvp_damage(power, opp_atk, focal_def, eff, stab_mult)
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
            stab_mult = STAB_MULTIPLIER if mtype in focal_types else 1.0
            dmg_ref = pvp_damage(power, ref_atk, opp_def, eff, stab_mult)
            dmg_focal = pvp_damage(power, focal_atk, opp_def, eff, stab_mult)
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
        move_pretty = pretty_name(move_id)
        if src_name:
            parts.append(f'bulkpoint: {move_pretty} from {src_name} does '
                         f'{dmg_new} instead of {dmg_old} ({stat} {val_new:.2f})')
        else:
            parts.append(f'breakpoint: {move_pretty} does '
                         f'{dmg_new} instead of {dmg_old} ({stat} {val_new:.2f})')

    for move_id, src_name, dmg_new, dmg_old, stat, val_new, val_old, is_favorable in unfavorable:
        move_pretty = pretty_name(move_id)
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


def aggregate_flips_by_anchor(scores_flat, nIvs, nS, nO,
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

    # Vectorise: reshape scores once, evaluate each anchor's partition via
    # boolean masks over the IV dim, collapse win counts over scenarios.
    # Without this the HP co-condition search dominates narrative compute
    # (see S8a profile 2026-04-17: 236s / 86% of narrative on a 1-moveset
    # Oinkologne dive was concentrated in the per-anchor HP sweep).
    scores_np = np.asarray(scores_flat).reshape(nIvs, nS, nO)
    iv_atk_np = np.asarray(data_obj['ivAtk'])
    iv_def_np = np.asarray(data_obj['ivDef'])
    hp_raw = data_obj.get('ivHp') or []
    iv_hp_np = np.asarray(hp_raw) if len(hp_raw) else None

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

        stat_vals = iv_atk_np if anchor.target_stat == 'atk' else iv_def_np
        if anchor.strict:
            passing_mask = stat_vals > anchor.threshold_value
        else:
            passing_mask = stat_vals >= anchor.threshold_value
        n_pass = int(passing_mask.sum())
        n_fail = nIvs - n_pass
        if n_pass == 0 or n_fail == 0:
            stats['trivial_partition'] += 1
            continue

        wins_for_opp = scores_np[:, :, oi] >= win_threshold  # (nIvs, nS)
        pw = wins_for_opp[passing_mask].sum(axis=0) / n_pass
        fw = wins_for_opp[~passing_mask].sum(axis=0) / n_fail
        clean = (pw >= pass_winrate_min) & (fw <= fail_winrate_max)

        if clean.any():
            flipped_scenarios = [scenarios[si] for si in np.where(clean)[0]]
            stats['emitted'] += 1
            records.append({
                'anchor': anchor,
                'opponent': anchor.opponent,
                'scenarios': flipped_scenarios,
                'direction': 'gain',
                'hp_threshold': None,
                # Canonical IV indices that pass this anchor. Used by
                # the interactive scatter plot's anchor-clear overlay
                # to highlight which spreads actually clear an emitted
                # anchor (separate from the bullet text rendering).
                'passing_ivs': np.where(passing_mask)[0].tolist(),
            })
            continue

        # -- HP co-condition search for def-side anchors --
        # When a def partition alone isn't clean, try adding an HP floor
        # to tighten the passing set. Iterate unique HPs within the
        # passing set from highest to lowest — first clean scenario gives
        # the tightest useful floor; keep relaxing until clean disappears
        # to find the minimum HP.
        if (anchor.target_stat == 'def' and n_pass > 1
                and iv_hp_np is not None):
            pass_hps = sorted(set(iv_hp_np[passing_mask].tolist()))
            best_hp = None
            best_scenarios = []
            for hp_floor in reversed(pass_hps):
                sub_pass_mask = passing_mask & (iv_hp_np >= hp_floor)
                n_sp = int(sub_pass_mask.sum())
                n_sf = nIvs - n_sp
                if n_sp == 0 or n_sf == 0:
                    continue
                # sub_fail = failing ∪ (passing ∧ hp_low), which is ~sub_pass_mask
                # because sub_pass_mask = passing ∧ hp_ok, so ~sub_pass_mask =
                # failing ∨ (passing ∧ hp_low). Equivalent to the original.
                spw = wins_for_opp[sub_pass_mask].sum(axis=0) / n_sp
                sfw = wins_for_opp[~sub_pass_mask].sum(axis=0) / n_sf
                hp_clean = (spw >= pass_winrate_min) & (sfw <= fail_winrate_max)
                if hp_clean.any():
                    best_hp = hp_floor
                    best_scenarios = [scenarios[si]
                                      for si in np.where(hp_clean)[0]]
                else:
                    if best_hp is not None:
                        break
            if best_hp is not None and best_scenarios:
                stats['emitted'] += 1
                pass_and_hp_mask = passing_mask & (iv_hp_np >= best_hp)
                records.append({
                    'anchor': anchor,
                    'opponent': anchor.opponent,
                    'scenarios': best_scenarios,
                    'direction': 'gain',
                    'hp_threshold': best_hp,
                    'passing_ivs': np.where(pass_and_hp_mask)[0].tolist(),
                })
                continue
        stats['no_clean_scenario'] += 1

    if debug_stats is not None:
        debug_stats.update(stats)
    return records


def find_matchup_boundaries(scores_flat, nIvs, nS, nO,
                             data_obj, scenarios, opponents,
                             sweep_stat='def',
                             win_threshold=500,
                             pass_winrate_min=0.75, fail_winrate_max=0.25,
                             min_passing=3):
    """Find the matchup-flipping stat boundary per opponent.

    For each (opponent, scenario), sweep the chosen stat (def or atk)
    thresholds to find the minimum value at which "IVs with stat >= threshold"
    cleanly win and "IVs with stat < threshold" cleanly lose. This finds the
    *actual stat target* a player needs, which is usually higher than the
    damage-tier boundary because multiple damage changes must accumulate
    across a full battle to flip the result.

    When no single-stat partition is clean, tries adding HP co-conditions
    at each candidate threshold (same approach as the anchor HP search).

    Args:
        sweep_stat: 'def' or 'atk' — which stat to sweep as the partition.

    Returns a list of dicts:
        {
          'opponent': str,
          'scenarios': [(s0, s1), ...],
          'threshold': float,
          'stat': 'def' | 'atk',
          'hp_threshold': int | None,
          'n_passing': int,  # how many IVs meet the spec
        }

    Only emits for (opponent, scenario_group) combinations where the
    partition is clean. Scenarios that flip at the same threshold+HP
    are grouped.

    Implementation note (2026-06-10): vectorized. "stat >= threshold"
    partitions are suffixes of the stat-sorted IV order, so every
    threshold's pass/fail win counts come from one reversed cumulative
    sum instead of an O(nIvs) scan per threshold; the HP co-condition
    sweep is the same trick over the HP-sorted order. Threshold and
    hp_threshold values are returned as the ORIGINAL Python objects
    from data_obj (via value maps), so records — and the HTML rendered
    from them — are identical to the pre-vectorization scan loops
    (verified byte-identical via replay_analysis.py on a real dive
    blob, plus the reference-implementation test in
    tests/test_matchup_boundaries.py). This was 95% of dive render
    time once arc S3-S5 made the sims cheap.
    """
    if nIvs == 0 or nO == 0:
        return []

    # Choose which stat to sweep
    if sweep_stat == 'atk':
        stat_vals = data_obj['ivAtk']
    else:
        stat_vals = data_obj['ivDef']
    hp_vals = data_obj.get('ivHp', [])

    stat_np  = np.asarray(stat_vals, dtype=np.float64)
    scores3d = np.asarray(scores_flat, dtype=np.float64).reshape(nIvs, nS, nO)
    wins_all = scores3d >= win_threshold

    # Stat-sorted order: "stat >= uniq[k]" is the suffix starting at
    # first_idx[k]. Map float64 values back to the original Python
    # objects so emitted records match the old implementation exactly.
    order        = np.argsort(stat_np, kind='stable')
    sorted_stats = stat_np[order]
    uniq, first_idx = np.unique(sorted_stats, return_index=True)
    pass_cnt = nIvs - first_idx
    fail_cnt = first_idx.astype(np.int64)
    size_ok  = (pass_cnt >= min_passing) & (fail_cnt > 0)
    stat_value_map = {}
    for v in stat_vals:
        stat_value_map.setdefault(float(v), v)

    have_hp = bool(hp_vals)
    if have_hp:
        hp_np       = np.asarray(hp_vals, dtype=np.float64)
        hp_order    = np.argsort(hp_np, kind='stable')
        hp_sorted   = hp_np[hp_order]
        stat_by_hp  = stat_np[hp_order]
        hp_value_map = {}
        for v in hp_vals:
            hp_value_map.setdefault(float(v), v)

    results = []

    for oi in range(nO):
        opp = opponents[oi]

        for si in range(nS):
            wins = wins_all[:, si, oi]
            total_wins = int(wins.sum())
            if total_wins == 0 or total_wins == nIvs:
                continue  # everyone wins or everyone loses — no flip

            best_stat = None
            best_hp = None

            # Phase 1: lowest threshold where the single-stat partition
            # is clean. pass_wins[k] = wins among {stat >= uniq[k]}.
            wins_sorted = wins[order].astype(np.int64)
            suffix_wins = np.concatenate(
                (np.cumsum(wins_sorted[::-1])[::-1], [0]))
            pass_wins = suffix_wins[first_idx]
            pw = pass_wins / pass_cnt
            fw = (total_wins - pass_wins) / np.maximum(fail_cnt, 1)
            clean = size_ok & (pw >= pass_winrate_min) & (fw <= fail_winrate_max)
            ci = np.flatnonzero(clean)
            if ci.size:
                best_stat = stat_value_map[float(uniq[ci[0]])]
                best_hp = None

            # Phase 2: if no single-stat threshold works, try stat + HP.
            # Walk thresholds ascending; first one with a workable HP
            # floor wins, mirroring the original loop's break.
            if best_stat is None and have_hp:
                # Pre-gates per threshold (identical to the originals):
                # partition sizes, any wins at all, winrate >= 0.3.
                gate = size_ok & (pass_wins > 0) & (pw >= 0.3)
                wins_by_hp = wins[hp_order].astype(np.int64)
                for ui in np.flatnonzero(gate):
                    thresh = uniq[ui]
                    m = stat_by_hp >= thresh
                    # Suffix sums over the HP-sorted order: for a floor
                    # starting at row j, sub_pass = passing IVs with
                    # hp >= floor; sub_fail is its complement.
                    cnt_suf = np.concatenate(
                        (np.cumsum(m[::-1].astype(np.int64))[::-1], [0]))
                    win_suf = np.concatenate(
                        (np.cumsum((wins_by_hp * m)[::-1])[::-1], [0]))
                    pass_hps = np.unique(hp_sorted[m])
                    js = np.searchsorted(hp_sorted, pass_hps, side='left')
                    found_hp = None
                    for k in range(len(pass_hps) - 1, -1, -1):
                        j = js[k]
                        n_sub  = int(cnt_suf[j])
                        n_rest = nIvs - n_sub
                        if n_sub < min_passing or n_rest == 0:
                            continue
                        spw = win_suf[j] / n_sub
                        sfw = (total_wins - win_suf[j]) / n_rest
                        if (spw >= pass_winrate_min
                                and sfw <= fail_winrate_max):
                            found_hp = pass_hps[k]
                        else:
                            if found_hp is not None:
                                break
                    if found_hp is not None:
                        best_stat = stat_value_map[float(thresh)]
                        best_hp = hp_value_map[float(found_hp)]
                        break  # found minimum stat+HP — done

            if best_stat is not None:
                pass_mask = stat_np >= best_stat
                if best_hp is not None:
                    pass_mask &= hp_np >= best_hp
                results.append({
                    'opponent': opp,
                    'scenario': scenarios[si],
                    'threshold': best_stat,
                    'stat': sweep_stat,
                    'hp_threshold': best_hp,
                    'n_passing': int(pass_mask.sum()),
                })

    # Group scenarios that flip at the same (opponent, threshold, hp) spec
    grouped: dict = {}
    for r in results:
        key = (r['opponent'], r['threshold'], r['hp_threshold'])
        if key not in grouped:
            grouped[key] = {
                'opponent': r['opponent'],
                'threshold': r['threshold'],
                'stat': r['stat'],
                'hp_threshold': r['hp_threshold'],
                'n_passing': r['n_passing'],
                'scenarios': [],
            }
        grouped[key]['scenarios'].append(r['scenario'])

    return sorted(grouped.values(),
                  key=lambda r: (r['threshold'], r['opponent']))


# ---- Tier derivation ----


def auto_derive_tiers(anchor_flip_records, data_obj,
                      matchup_boundaries=None):
    """Synthesize threshold tiers from anchor-flip records + matchup boundaries.

    Two sources feed tier derivation:
    1. Anchor-flip records -> per-opponent atk/def damage-tier boundaries.
    2. Matchup boundaries -> full-battle stat targets on def OR atk, clustered
       by IV-count drop + threshold gap within each stat. The highest-
       selectivity cluster corresponds to acidicArisen's "GH Great", the
       next to "GH Good", etc.

    Returns a list of tier dicts matching the shape ``data_obj['tiers']``
    expects: ``{name, color, attack, defense, stamina, desc}``.
    """
    if not anchor_flip_records and not matchup_boundaries:
        return []

    # Collect per-opponent, per-stat minimum thresholds
    # Key: (opponent, target_stat) -> min threshold across all records
    opp_stat_min: dict = {}
    opp_stat_records: dict = {}
    for rec in anchor_flip_records:
        a = rec['anchor']
        tv = getattr(a, 'threshold_value', None)
        if tv is None:
            continue
        key = (rec['opponent'], a.target_stat)
        if key not in opp_stat_min or tv < opp_stat_min[key]:
            opp_stat_min[key] = tv
        opp_stat_records.setdefault(key, []).append(rec)

    if not opp_stat_min and not matchup_boundaries:
        return []

    # Separate into atk-side and def-side opponent groups
    atk_opps = {}  # opponent -> min atk threshold
    def_opps = {}  # opponent -> min def threshold
    for (opp, stat), thresh in opp_stat_min.items():
        if stat == 'atk':
            atk_opps[opp] = thresh
        elif stat == 'def':
            def_opps[opp] = thresh

    # Global floors: minimum threshold across all opponents per stat
    atk_floor = min(atk_opps.values()) if atk_opps else 0
    def_floor = min(def_opps.values()) if def_opps else 0

    # Count how many total matchup-flipping scenarios each opponent group
    # contributes — used to prioritize which opponents get their own tier.
    def _scenario_count(opp, stat):
        key = (opp, stat)
        return sum(len(r['scenarios']) for r in opp_stat_records.get(key, []))

    tiers = []
    color_idx = 0

    def _next_color():
        nonlocal color_idx
        c = f'var(--tier-{color_idx % 8 + 1})'
        color_idx += 1
        return c

    # --- General tier: floor atk + floor def ---
    # Only emit if we have thresholds on both sides, or at least one side
    # has multiple opponents (otherwise the general tier IS the only
    # opponent-specific tier and we'd just duplicate it).
    if (atk_floor > 0 or def_floor > 0) and (len(atk_opps) + len(def_opps) > 1):
        n_atk_opps = len(atk_opps)
        n_def_opps = len(def_opps)
        desc_parts = []
        if n_atk_opps:
            desc_parts.append(f'{n_atk_opps} atk breakpoint opponent'
                              f'{"s" if n_atk_opps != 1 else ""}')
        if n_def_opps:
            desc_parts.append(f'{n_def_opps} bulkpoint opponent'
                              f'{"s" if n_def_opps != 1 else ""}')
        tiers.append({
            'name': 'General',
            'color': _next_color(),
            'attack': atk_floor if atk_floor > 0 else 0,
            'defense': def_floor if def_floor > 0 else 0,
            'stamina': 0,
            'desc': f'Floor across {" + ".join(desc_parts)}. '
                    f'Clears the easiest anchor for every opponent.',
        })

    # --- Per-opponent specialist tiers ---
    # Sort opponents by scenario count (most impactful first), then
    # alphabetically for stability.
    atk_ranked = sorted(atk_opps.keys(),
                        key=lambda o: (-_scenario_count(o, 'atk'), o))
    def_ranked = sorted(def_opps.keys(),
                        key=lambda o: (-_scenario_count(o, 'def'), o))

    # Atk-side specialist tiers: only emit if the opponent's threshold is
    # above the general floor (otherwise it's already covered by General).
    for opp in atk_ranked:
        thresh = atk_opps[opp]
        if len(atk_opps) > 1 and abs(thresh - atk_floor) < 0.01:
            continue  # already in General
        n_scen = _scenario_count(opp, 'atk')
        tiers.append({
            'name': f'{opp} Atk',
            'color': _next_color(),
            'attack': thresh,
            'defense': 0,
            'stamina': 0,
            'desc': f'Atk breakpoint(s) vs {opp} '
                    f'({n_scen} scenario flip{"s" if n_scen != 1 else ""}).',
        })

    # Def-side specialist tiers
    for opp in def_ranked:
        thresh = def_opps[opp]
        if len(def_opps) > 1 and abs(thresh - def_floor) < 0.01:
            continue  # already in General
        n_scen = _scenario_count(opp, 'def')
        tiers.append({
            'name': f'{opp} Bulk',
            'color': _next_color(),
            'attack': 0,
            'defense': thresh,
            'stamina': 0,
            'desc': f'Bulkpoint(s) vs {opp} '
                    f'({n_scen} scenario flip{"s" if n_scen != 1 else ""}).',
        })

    # --- Matchup-boundary-driven tiers (def-side + atk-side) ---
    # Sort boundaries by threshold ascending within each stat and pick tier
    # breaks where the number of qualifying IVs drops significantly — these
    # correspond to acidicArisen-style tiers like "GH Good" (many IVs)
    # vs "GH Great" (few IVs, stricter spec).
    def _mb_candidates(mbs):
        by_thresh: dict = {}
        for mb in mbs:
            by_thresh.setdefault(mb['threshold'], []).append(mb)
        cands = []
        for t in sorted(by_thresh.keys()):
            group = by_thresh[t]
            opps = sorted({m['opponent'] for m in group})
            total_scens = sum(len(m['scenarios']) for m in group)
            hp_vals_in = [m['hp_threshold'] for m in group
                          if m.get('hp_threshold') is not None]
            hp_cut = max(hp_vals_in) if hp_vals_in else 0
            n_pass = max(m['n_passing'] for m in group)
            cands.append({
                'threshold': t, 'hp': hp_cut, 'opps': opps,
                'n_scens': total_scens, 'n_pass': n_pass,
            })
        return cands

    def _pick_tier_breaks(candidates):
        if len(candidates) < 2:
            return candidates if candidates else []
        # Pick tier breaks by two signals:
        # 1. Significant IV-count drop: n_passing < 40% of high-water mark
        # 2. Threshold gap: > 2 points from previous pick AND n < 50%
        picks = [candidates[0]]  # floor
        hwm = candidates[0]['n_pass']
        for i in range(1, len(candidates)):
            curr_n = candidates[i]['n_pass']
            hwm = max(hwm, curr_n)
            iv_drop = hwm > 0 and curr_n < hwm * 0.4
            gap = (candidates[i]['threshold'] - picks[-1]['threshold'] > 2.0
                   and hwm > 0 and curr_n < hwm * 0.5)
            if iv_drop or gap:
                picks.append(candidates[i])
                hwm = curr_n
        # Skip the floor (too many IVs, not selective) unless it's the only one.
        if len(picks) > 1:
            picks = picks[1:]
        return picks

    if matchup_boundaries:
        # Partition by sweep stat
        def_mbs = [mb for mb in matchup_boundaries
                   if mb.get('stat', 'def') == 'def']
        atk_mbs = [mb for mb in matchup_boundaries
                   if mb.get('stat') == 'atk']

        # Def-side: produce "Bulk N+" tiers
        for pick in _pick_tier_breaks(_mb_candidates(def_mbs)):
            opp_str = ', '.join(pick['opps'][:3])
            if len(pick['opps']) > 3:
                opp_str += f' +{len(pick["opps"]) - 3}'
            already_exists = any(
                abs((t.get('defense', 0) or 0) - pick['threshold']) < 1.0
                and not (t.get('attack', 0) or 0)
                for t in tiers
            )
            if already_exists:
                continue
            tiers.append({
                'name': f'Bulk {pick["threshold"]:.0f}+',
                'color': _next_color(),
                'attack': 0,
                'defense': pick['threshold'],
                'stamina': pick['hp'],
                'desc': f'Matchup flips vs {opp_str} '
                        f'({pick["n_scens"]} scenario'
                        f'{"s" if pick["n_scens"] != 1 else ""}, '
                        f'{pick["n_pass"]} IVs).',
            })

        # Atk-side: produce "Atk N+" tiers
        for pick in _pick_tier_breaks(_mb_candidates(atk_mbs)):
            opp_str = ', '.join(pick['opps'][:3])
            if len(pick['opps']) > 3:
                opp_str += f' +{len(pick["opps"]) - 3}'
            already_exists = any(
                abs((t.get('attack', 0) or 0) - pick['threshold']) < 1.0
                and not (t.get('defense', 0) or 0)
                for t in tiers
            )
            if already_exists:
                continue
            tiers.append({
                'name': f'Atk {pick["threshold"]:.0f}+',
                'color': _next_color(),
                'attack': pick['threshold'],
                'defense': 0,
                'stamina': pick['hp'],
                'desc': f'Matchup flips vs {opp_str} '
                        f'({pick["n_scens"]} scenario'
                        f'{"s" if pick["n_scens"] != 1 else ""}, '
                        f'{pick["n_pass"]} IVs).',
            })

    # Rank all non-General tiers by selectivity (fewest qualifying IVs
    # first). The most selective tiers are the ones experts hand-identify
    # — def-side matchup boundaries (26-1218 IVs) naturally outrank
    # broad atk tiers (900-4000 IVs). Keep top 5 + General as fallback.
    general = [t for t in tiers if t['name'] == 'General']
    rest = [t for t in tiers if t['name'] != 'General']
    n_ivs = data_obj.get('nIvs', 1) or 1
    def _selectivity(t):
        ac = t.get('attack', 0) or 0
        dc = t.get('defense', 0) or 0
        hc = t.get('stamina', 0) or 0
        return sum(1 for iv in range(n_ivs)
                   if (ac <= 0 or data_obj['ivAtk'][iv] >= ac)
                   and (dc <= 0 or data_obj['ivDef'][iv] >= dc)
                   and (hc <= 0 or data_obj['ivHp'][iv] >= hc))
    rest.sort(key=_selectivity)
    # Most selective first — they get priority in ivTiers assignment.
    tiers = rest[:5] + general

    return tiers


def synthesize_mirror_tier(
    species, scores_flat, nIvs, nS, nO,
    data_obj, scenarios, opponents,
    resolved_anchors, existing_tiers,
    *, min_clean_scenarios=None, win_threshold=500,
    focal_shadow=False,
):
    """Synthesize a "Species Mirror Bulk" or "Species Mirror Atk" tier
    from auto-anchors when none of the existing tiers references the
    focal species.

    Why a separate post-processing step (vs. relying on
    aggregate_flips_by_anchor): the mirror is a hard partition for the
    standard cleanliness gate (75/25 win-rate split) because failing
    low-def IVs include high-atk compensators that don't reliably lose.
    The aggregator filters these anchors out as "no clean scenario."
    But the cohort-vs-rank-1 head-to-head tells a different story:
    high-def IVs reliably beat the rank-1 SP focal opponent across
    most scenarios, just not "≥75% win and failing ≤25% win"
    cleanly. RyanSwag-era articles ("138.28 Def dominates Top-20 SP
    Dewgong") read on this looser signal.

    Returns ``None`` (no tier added) when:

    - focal species is not in the opponent pool (mirror not simulated),
    - any existing tier name contains the focal species name (already
      surfaced — don't double-count),
    - no auto-anchor for the focal species produces a passing cohort
      that BOTH wins on average against the rank-1 SP focal AND beats
      the failing-cohort mean score, in ``>= min_clean_scenarios``
      scenarios.

    The two-condition gate matters: requiring "passing-cohort mean
    >= win_threshold" alone misses tiers in soft-mirror species where
    most IVs win (no differentiation); requiring "passing-cohort mean
    > failing-cohort mean" alone misses cases where high-def IVs
    score higher but everyone loses (no actual mirror dominance).
    Both together = "this cohort actually wins the mirror, and that
    win is attributable to the stat threshold."

    Returns a single tier dict to APPEND to existing_tiers (does not
    mutate), or ``None``.

    When ``min_clean_scenarios`` is ``None`` (default), it scales with
    ``nS`` to "majority of scenarios": ``ceil(nS * 6/9)``. So a
    nine-scenario all-9 dive needs ≥6/9, a single-scenario dive needs
    ≥1/1, a three-scenario dive needs ≥2/3 — all read as "passing
    cohort wins majority of scenarios against rank-1 SP", the article-
    era "dominates the mirror" threshold relaxed from "every scenario"
    to "most scenarios".
    """
    import logging
    _log = logging.getLogger('deep_dive')
    if min_clean_scenarios is None:
        # Scale to "majority of scenarios": 5/9, 2/3, 1/1.
        # Why "majority" and not "two-thirds": in mirror matches, low-
        # shield-count scenarios (0v0/0v1/0v2 from the focal side) are
        # often structurally unwinnable regardless of bulk — there are
        # too few shields to leverage the def advantage. Requiring 6/9
        # would silently exclude meaningful Mirror Bulk tiers in any
        # contested mirror; "majority" (5/9) catches the equal+
        # shield states where bulk actually pays off.
        min_clean_scenarios = max(1, math.ceil(nS / 2))
    # The true mirror for a shadow focal is the SHADOW pool entry — the
    # plain entry has unmultiplied stats and the non-shadow moveset, so
    # matching it would derive the tier against a different Pokemon.
    mirror_name = f'{species} (Shadow)' if focal_shadow else species
    _log.info(f"  [mirror-synth] starting for mirror={mirror_name!r}, "
              f"{len(opponents)} opponents, {len(resolved_anchors)} resolved anchors, "
              f"{len(existing_tiers)} existing tiers, nS={nS}, "
              f"min_clean={min_clean_scenarios}")
    # Find focal species' opponent index (mirror in opponent pool).
    opp_idx = None
    for oi, name in enumerate(opponents):
        if name == mirror_name:
            opp_idx = oi
            break
    if opp_idx is None:
        _log.info(f"  [mirror-synth] BAIL: mirror {mirror_name!r} not in "
                  f"opponent list (sample: {opponents[:5]})")
        return None

    # Skip if any existing tier already names the focal species — but only
    # THIS form: a name continuing with ' (' is a different form (e.g.
    # focal 'Oinkologne' must not bail on an 'Oinkologne (Female) Bulk'
    # tier), so the match requires the name NOT be followed by ' ('.
    mirror_pat = re.compile(re.escape(mirror_name.lower()) + r'(?! \()')
    for t in existing_tiers:
        if mirror_pat.search((t.get('name', '') or '').lower()):
            _log.info(f"  [mirror-synth] BAIL: existing tier {t.get('name')!r} "
                      f"already names focal species")
            return None

    # Pull mirror auto-anchors for the focal species (both atk and def
    # sides). These are typically generated by build_auto_anchors as
    # auto_<species>_brkp_any (atk) and auto_<species>_blkp_any (def);
    # the Level-3 expansion gives a family of resolved anchors at
    # different damage-tier thresholds.
    mirror_anchors = [a for a in resolved_anchors
                       if a.opponent == mirror_name]
    _log.info(f"  [mirror-synth] {len(mirror_anchors)} mirror anchors found "
              f"(opponent=={mirror_name!r})")
    if not mirror_anchors:
        sample_opps = sorted({getattr(a, 'opponent', None) for a in resolved_anchors
                              if getattr(a, 'opponent', None)})[:8]
        _log.info(f"  [mirror-synth] BAIL: no mirror anchors. "
                  f"sample opponent attrs in resolved: {sample_opps}")
        return None

    scores_np = np.asarray(scores_flat).reshape(nIvs, nS, nO)
    iv_atk_np = np.asarray(data_obj['ivAtk'])
    iv_def_np = np.asarray(data_obj['ivDef'])
    iv_hp_np = np.asarray(data_obj.get('ivHp') or [])
    mirror_scores = scores_np[:, :, opp_idx]  # (nIvs, nS)

    # Gate: "passing cohort wins the mirror on average". Two conditions
    # per scenario:
    #   1. passing-cohort mean score >= win_threshold (cohort wins on
    #      average against rank-1 SP focal in this scenario)
    #   2. passing-cohort mean score > failing-cohort mean (high-def
    #      IVs outperform low-def IVs on this scenario — guards against
    #      "everyone wins the mirror" trivial cases)
    # Count scenarios where BOTH hold; require >= min_clean_scenarios.
    best = None  # (n_clean, threshold, target_stat, n_pass, scens_won, diag)
    diags = []  # for log: per-anchor stats
    for anchor in mirror_anchors:
        target_stat = anchor.target_stat
        threshold = anchor.threshold_value
        if threshold is None or threshold <= 0:
            continue
        stat_vals = iv_atk_np if target_stat == 'atk' else iv_def_np
        if anchor.strict:
            passing_mask = stat_vals > threshold
        else:
            passing_mask = stat_vals >= threshold
        n_pass = int(passing_mask.sum())
        if n_pass == 0 or n_pass == nIvs:
            continue  # trivial partition
        pass_mean = mirror_scores[passing_mask].mean(axis=0)  # (nS,)
        fail_mean = mirror_scores[~passing_mask].mean(axis=0)  # (nS,)
        wins_avg = pass_mean >= win_threshold
        beats_fail = pass_mean > fail_mean
        clean_mask = wins_avg & beats_fail
        n_clean = int(clean_mask.sum())
        diags.append((threshold, target_stat, n_pass, n_clean,
                      pass_mean.copy(), fail_mean.copy()))
        if n_clean < min_clean_scenarios:
            continue
        candidate = (n_clean, threshold, target_stat, n_pass,
                     [scenarios[si] for si, ok in enumerate(clean_mask) if ok])
        if best is None or (candidate[0], candidate[1]) > (best[0], best[1]):
            best = candidate

    # Diagnostic: top 3 anchors by n_clean so we can SEE what the
    # cohort scores look like even when nothing passes the gate.
    diags.sort(key=lambda d: (-d[3], -d[0]))
    for d in diags[:3]:
        thr, ts, npass, nc, pm, fm = d
        _log.info(f"  [mirror-synth] anchor {ts}={thr:.2f} "
                  f"pass={npass}/{nIvs} clean={nc}/{nS} "
                  f"pass_mean={pm.round(0).astype(int).tolist()} "
                  f"fail_mean={fm.round(0).astype(int).tolist()}")

    if best is None:
        _log.info(f"  [mirror-synth] BAIL: no anchor passed the "
                  f">={min_clean_scenarios}/{nS} clean-scenario gate "
                  f"(passing-cohort mean >= {win_threshold} AND > failing-cohort mean; "
                  f"checked {len(mirror_anchors)} mirror anchors)")
        return None

    n_clean, threshold, target_stat, n_pass, scens_won = best
    _log.info(f"  [mirror-synth] WIN: {target_stat}={threshold:.2f} "
              f"clean={n_clean}/{nS} pass={n_pass}/{nIvs}")

    # HP co-floor: take the minimum HP among passing IVs that won the
    # mirror in at least min_clean_scenarios scenarios. Aligns with the
    # existing matchup-boundary code's HP-floor convention.
    hp_floor = 0
    if iv_hp_np.size:
        # Re-derive passing_mask from the winning anchor's stat target.
        # Bulkpoint anchors use strict=True (def > threshold = "you take
        # one less hit"); breakpoint anchors use strict=False (atk >=
        # threshold = "you deal at least N").
        win_anchor_strict = (target_stat == 'def')
        if target_stat == 'def':
            stat_vals = iv_def_np
        else:
            stat_vals = iv_atk_np
        if win_anchor_strict:
            passing_mask = stat_vals > threshold
        else:
            passing_mask = stat_vals >= threshold
        passing_indices = np.where(passing_mask)[0]
        # Per-IV winning scenario count vs the mirror.
        per_iv_wins = (mirror_scores[passing_indices] >= win_threshold).sum(axis=1)
        good_iv_mask = per_iv_wins >= min_clean_scenarios
        if good_iv_mask.any():
            good_hp = iv_hp_np[passing_indices[good_iv_mask]]
            hp_floor = int(good_hp.min())

    # Tier label: "<species> Mirror Bulk" (def-side) /
    # "<species> Mirror Atk" (atk-side). Handles species with
    # parenthesized form names (e.g. "Aegislash (Shield)") cleanly.
    tier_kind = 'Bulk' if target_stat == 'def' else 'Atk'
    tier_name = f'{mirror_name} Mirror {tier_kind}'

    desc = (f'Mirror {tier_kind.lower()}point: passing cohort wins '
            f'{n_clean} of {nS} scenarios vs rank-1 SP {mirror_name} '
            f'({n_pass} IVs pass).')

    return {
        'name': tier_name,
        'color': 'var(--tier-mirror)',  # distinct purple, theme-aware; set
                              # apart from the auto-derive palette so the mirror
                              # tier visually stands out as "different
                              # category" from per-opponent tiers. The Plotly
                              # marker path resolves this var to its theme hex
                              # via deep_dive._TIER_VAR_TO_HEX.
        'attack': threshold if target_stat == 'atk' else 0,
        'defense': threshold if target_stat == 'def' else 0,
        'stamina': hp_floor,
        'desc': desc,
    }


def probe_tier_cutoff_flips(data_obj, score_arrays_all, moveset_idx,
                            atk_cut, def_cut, hp_cut,
                            scenarios, opponents,
                            pass_winrate_min=0.75, fail_winrate_max=0.25):
    """Probe a tier's stat cutoffs directly as a partition point.

    For each (opponent, scenario, opp_iv_mode), partition IVs by whether
    they meet ALL of the tier's cutoffs and check win-rate cleanliness.
    Returns a list of dicts: {opponent, scenario, opp_iv_mode, pass_wr,
    fail_wr}. This catches matchup flips at the tier boundary that fall
    between Level 3 sub-anchor thresholds (e.g. acidicArisen's 143.03 def
    vs Azu, which lies between the damage tiers at 142.34 and 144.41).
    """
    nIvs = data_obj.get('nIvs', 0)
    nS = len(scenarios)
    nO = len(opponents)
    if nIvs == 0 or nO == 0:
        return []

    iv_atk, iv_def, iv_hp = _np_stats(data_obj)
    meets = np.ones(nIvs, dtype=bool)
    if atk_cut > 0:
        meets &= iv_atk >= atk_cut
    if def_cut > 0:
        meets &= iv_def >= def_cut
    if hp_cut > 0:
        meets &= iv_hp >= hp_cut

    n_pass = int(meets.sum())
    n_fail = nIvs - n_pass
    if n_pass == 0 or n_fail == 0:
        return []

    results = []
    all_modes = data_obj.get('oppIvModes', ['pvpoke'])
    for mode in all_modes:
        scores = _np_scores(score_arrays_all, moveset_idx, mode, nIvs, nS, nO)
        if scores is None:
            continue
        wins = scores >= 500
        pw = wins[meets].sum(axis=0) / n_pass
        fw = wins[~meets].sum(axis=0) / n_fail
        sel = (pw >= pass_winrate_min) & (fw <= fail_winrate_max)
        if not sel.any():
            continue
        si_arr, oi_arr = np.where(sel)
        for si_i, oi_i in zip(si_arr.tolist(), oi_arr.tolist()):
            results.append({
                'opponent': opponents[oi_i],
                'scenario': scenarios[si_i],
                'opp_iv_mode': mode,
                'pass_wr': float(pw[si_i, oi_i]),
                'fail_wr': float(fw[si_i, oi_i]),
            })
    return results


# ---- Envelope-position metric (S4) ----

def compute_envelope_positions(categories, sp_ranks, avg_scores,
                               anchor_iv_indices,
                               *,
                               k_nearest=20,
                               min_members=3,
                               min_anchors=5,
                               shape_ratio=1.5):
    """Per-category envelope position vs the Anchor IVs band at matching SP rank.

    For each named IV category, compare each member's battle score against
    the local mean of the Anchor IVs band at the same stat-product rank.
    The per-member deltas have:
        mean_delta - signed distance from the band (+ = above, - = below)
        spread     - stdev of deltas (how tightly members hug an edge vs
                     scatter across it)
        shape      - descriptor:
                       envelope-rider-top     |mean_delta|>=shape_ratio*spread, mean>0
                       envelope-rider-bottom  |mean_delta|>=shape_ratio*spread, mean<0
                       elevated-band-crosser  otherwise, mean>0
                       depressed-band-crosser otherwise, mean<=0
                       sparse                 too few members or too few anchors

    Inputs:
        categories: iterable of IVCategory-like objects (each must have
            ``.name`` and ``.members`` — a list of canonical IV indices).
        sp_ranks: sequence indexable by canonical IV index -> sp_rank (int,
            1 = best). Produced by deep_dive.py at data_obj build time.
        avg_scores: sequence indexable by canonical IV index -> avg battle
            score (float). The caller picks which moveset / opp-iv mode
            the average is taken over.
        anchor_iv_indices: sequence of canonical IV indices in the Anchor
            IVs overlay. Empty or too-small collections produce 'sparse'
            classifications for every category.

    Returns a dict keyed by category name, shape:
        {cat_name: {
            'mean_delta': float,
            'spread':     float,   # 0.0 when spread undefined (n_members==1)
            'shape':      str,
            'n_members':  int,
            'n_anchors':  int,     # total anchor band size
        }}

    Pure function: no I/O, no globals. Categories with zero members are
    skipped entirely.

    The metric is decoupled from the scatter renderer on purpose - the
    S6+ article generator can consume it as a structured fact without
    caring about HTML.
    """
    anchor_set = set(anchor_iv_indices)
    n_anchors = len(anchor_set)

    # Pre-sort anchors by sp_rank once; per-member lookups are
    # binary-search + slice.
    anchor_rank_score = sorted(
        ((sp_ranks[a], avg_scores[a]) for a in anchor_set
         if 0 <= a < len(sp_ranks) and 0 <= a < len(avg_scores)),
        key=lambda p: p[0],
    )
    anchor_ranks = [p[0] for p in anchor_rank_score]
    anchor_score_arr = [p[1] for p in anchor_rank_score]
    n_anchor_band = len(anchor_ranks)

    def _expected_at_rank(rank):
        """Mean of the K anchor scores whose sp_rank is closest to ``rank``.

        Ties on distance are resolved by rank order (sorted list already
        reflects it). Returns None when the band is empty.
        """
        if n_anchor_band == 0:
            return None
        k = min(k_nearest, n_anchor_band)
        # Binary search for insertion point.
        lo, hi = 0, n_anchor_band
        while lo < hi:
            mid = (lo + hi) // 2
            if anchor_ranks[mid] < rank:
                lo = mid + 1
            else:
                hi = mid
        # Two-pointer expand around ``lo`` until we have k entries,
        # always picking the closer neighbor.
        left = lo - 1
        right = lo
        total = 0.0
        picked = 0
        while picked < k and (left >= 0 or right < n_anchor_band):
            if left < 0:
                total += anchor_score_arr[right]
                right += 1
            elif right >= n_anchor_band:
                total += anchor_score_arr[left]
                left -= 1
            else:
                d_left = rank - anchor_ranks[left]
                d_right = anchor_ranks[right] - rank
                if d_left <= d_right:
                    total += anchor_score_arr[left]
                    left -= 1
                else:
                    total += anchor_score_arr[right]
                    right += 1
            picked += 1
        return total / picked if picked else None

    def _mean(vals):
        return sum(vals) / len(vals)

    def _stdev(vals, mean):
        if len(vals) < 2:
            return 0.0
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        return var ** 0.5

    out = {}
    for cat in categories:
        name = getattr(cat, 'name', None)
        members = getattr(cat, 'members', None) or []
        if not name or not members:
            continue
        if n_anchor_band < min_anchors or len(members) < min_members:
            out[name] = {
                'mean_delta': 0.0,
                'spread': 0.0,
                'shape': 'sparse',
                'n_members': len(members),
                'n_anchors': n_anchor_band,
            }
            continue

        deltas = []
        for iv in members:
            if iv < 0 or iv >= len(sp_ranks) or iv >= len(avg_scores):
                continue
            expected = _expected_at_rank(sp_ranks[iv])
            if expected is None:
                continue
            deltas.append(avg_scores[iv] - expected)
        if not deltas:
            out[name] = {
                'mean_delta': 0.0,
                'spread': 0.0,
                'shape': 'sparse',
                'n_members': len(members),
                'n_anchors': n_anchor_band,
            }
            continue

        mean_delta = _mean(deltas)
        spread = _stdev(deltas, mean_delta)
        if abs(mean_delta) >= shape_ratio * spread:
            shape = ('envelope-rider-top' if mean_delta > 0
                     else 'envelope-rider-bottom')
        else:
            shape = ('elevated-band-crosser' if mean_delta > 0
                     else 'depressed-band-crosser')
        out[name] = {
            'mean_delta': mean_delta,
            'spread': spread,
            'shape': shape,
            'n_members': len(members),
            'n_anchors': n_anchor_band,
        }
    return out
