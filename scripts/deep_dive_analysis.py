"""Boundary/flip analysis engine for IV deep dives.

Pure-analysis functions that partition IV cohorts by stat thresholds
(anchors, matchup boundaries) and detect matchup flips. No HTML
rendering — that stays in deep_dive.py.
"""
import math

from gopvpsim.moves import type_effectiveness


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
    """PvP damage formula: floor(0.5 * 1.3 * power * atk/def * eff * stab) + 1"""
    return math.floor(0.5 * 1.3 * power * atk / def_ * effectiveness * stab_mult) + 1


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
            stab_mult = 1.2 if mtype in opp_types else 1.0
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
            stab_mult = 1.2 if mtype in focal_types else 1.0
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
                'hp_threshold': None,
                # Canonical IV indices that pass this anchor. Used by
                # the interactive scatter plot's anchor-clear overlay
                # to highlight which spreads actually clear an emitted
                # anchor (separate from the bullet text rendering).
                'passing_ivs': list(passing),
            })
        else:
            # -- HP co-condition search for def-side anchors --
            # When a def partition alone isn't clean, try adding an HP
            # floor to tighten the passing set. For each candidate HP
            # value (unique HPs in the passing set, descending), re-check
            # all scenarios. Emit the LOWEST HP that produces at least one
            # clean scenario — that's the minimum HP needed alongside the
            # def threshold.
            if anchor.target_stat == 'def' and len(passing) > 1:
                hp_vals = data_obj.get('ivHp', [])
                if hp_vals:
                    # Unique HP values in the passing set, ascending
                    pass_hps = sorted({hp_vals[iv] for iv in passing})
                    best_hp = None
                    best_scenarios = []
                    # Search from highest HP down — first hit with a clean
                    # scenario is the tightest useful HP floor. Then relax
                    # downward to find the minimum HP that still flips.
                    for hp_floor in reversed(pass_hps):
                        sub_pass = [iv for iv in passing
                                    if hp_vals[iv] >= hp_floor]
                        sub_fail_extra = [iv for iv in passing
                                          if hp_vals[iv] < hp_floor]
                        sub_fail = failing + sub_fail_extra
                        if not sub_pass or not sub_fail:
                            continue
                        hp_flipped = []
                        for si in range(nS):
                            pw = sum(
                                1 for iv in sub_pass
                                if scores_flat[iv * nS * nO + si * nO + oi]
                                >= win_threshold
                            ) / len(sub_pass)
                            fw = sum(
                                1 for iv in sub_fail
                                if scores_flat[iv * nS * nO + si * nO + oi]
                                >= win_threshold
                            ) / len(sub_fail)
                            if (pw >= pass_winrate_min
                                    and fw <= fail_winrate_max):
                                hp_flipped.append(scenarios[si])
                        if hp_flipped:
                            best_hp = hp_floor
                            best_scenarios = hp_flipped
                            # Keep going lower to find the minimum HP
                        else:
                            if best_hp is not None:
                                break  # went too low, previous was min
                    if best_hp is not None and best_scenarios:
                        stats['emitted'] += 1
                        stats['no_clean_scenario'] -= 1
                        records.append({
                            'anchor': anchor,
                            'opponent': anchor.opponent,
                            'scenarios': best_scenarios,
                            'direction': 'gain',
                            'hp_threshold': best_hp,
                            'passing_ivs': [
                                iv for iv in passing
                                if hp_vals[iv] >= best_hp],
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
    """
    if nIvs == 0 or nO == 0:
        return []

    # Choose which stat to sweep
    if sweep_stat == 'atk':
        stat_vals = data_obj['ivAtk']
    else:
        stat_vals = data_obj['ivDef']
    hp_vals = data_obj.get('ivHp', [])
    unique_stats = sorted({stat_vals[iv] for iv in range(nIvs)})

    results = []

    for oi in range(nO):
        opp = opponents[oi]

        for si in range(nS):
            # Precompute win/loss for each IV in this (opp, scenario)
            wins = [scores_flat[iv * nS * nO + si * nO + oi] >= win_threshold
                    for iv in range(nIvs)]

            # Sweep def thresholds ascending. For each threshold, count
            # pass/fail wins efficiently using running totals.
            # total_wins = sum of wins across all IVs
            total_wins = sum(1 for w in wins if w)
            if total_wins == 0 or total_wins == nIvs:
                continue  # everyone wins or everyone loses — no flip

            best_stat = None
            best_hp = None

            # Walk unique_stats ascending. At each threshold, passing =
            # IVs with stat >= threshold. We want the LOWEST value where
            # the partition is clean.
            for stat_thresh in unique_stats:
                passing = [iv for iv in range(nIvs)
                           if stat_vals[iv] >= stat_thresh]
                failing = [iv for iv in range(nIvs)
                           if stat_vals[iv] < stat_thresh]
                if len(passing) < min_passing or not failing:
                    continue

                pw = sum(1 for iv in passing if wins[iv]) / len(passing)
                fw = sum(1 for iv in failing if wins[iv]) / len(failing)

                if pw >= pass_winrate_min and fw <= fail_winrate_max:
                    best_stat = stat_thresh
                    best_hp = None
                    break  # found minimum — done

            # If no single-stat threshold works, try stat + HP
            if best_stat is None and hp_vals:
                for stat_thresh in unique_stats:
                    s_passing = [iv for iv in range(nIvs)
                                 if stat_vals[iv] >= stat_thresh]
                    s_failing = [iv for iv in range(nIvs)
                                 if stat_vals[iv] < stat_thresh]
                    if len(s_passing) < min_passing or not s_failing:
                        continue
                    # Check if there's ANY signal — do the passing IVs
                    # win more often than failing ones?
                    pw_raw = sum(1 for iv in s_passing if wins[iv])
                    if pw_raw == 0:
                        continue  # no wins in passing set at all
                    if pw_raw / len(s_passing) < 0.3:
                        continue  # too low to be tightenable

                    # Try HP thresholds within the stat-passing set
                    pass_hps = sorted({hp_vals[iv] for iv in s_passing})
                    found_hp = None
                    for hp_floor in reversed(pass_hps):
                        sub_pass = [iv for iv in s_passing
                                    if hp_vals[iv] >= hp_floor]
                        sub_fail = s_failing + [
                            iv for iv in s_passing
                            if hp_vals[iv] < hp_floor]
                        if len(sub_pass) < min_passing or not sub_fail:
                            continue
                        spw = sum(1 for iv in sub_pass
                                  if wins[iv]) / len(sub_pass)
                        sfw = sum(1 for iv in sub_fail
                                  if wins[iv]) / len(sub_fail)
                        if (spw >= pass_winrate_min
                                and sfw <= fail_winrate_max):
                            found_hp = hp_floor
                        else:
                            if found_hp is not None:
                                break
                    if found_hp is not None:
                        best_stat = stat_thresh
                        best_hp = found_hp
                        break  # found minimum stat+HP — done

            if best_stat is not None:
                n_pass = sum(
                    1 for iv in range(nIvs)
                    if stat_vals[iv] >= best_stat
                    and (best_hp is None or hp_vals[iv] >= best_hp)
                )
                results.append({
                    'opponent': opp,
                    'scenario': scenarios[si],
                    'threshold': best_stat,
                    'stat': sweep_stat,
                    'hp_threshold': best_hp,
                    'n_passing': n_pass,
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

TIER_COLORS_AUTO = [
    '#58a6ff',  # blue  — general
    '#f85149',  # red   — atk specialist
    '#3fb950',  # green — def specialist
    '#d29922',  # gold  — premium
    '#bc8cff',  # purple
    '#f0883e',  # orange
]


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
        c = TIER_COLORS_AUTO[color_idx % len(TIER_COLORS_AUTO)]
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

    passing = []
    failing = []
    for iv in range(nIvs):
        meets = True
        if atk_cut > 0 and data_obj['ivAtk'][iv] < atk_cut:
            meets = False
        if def_cut > 0 and data_obj['ivDef'][iv] < def_cut:
            meets = False
        if hp_cut > 0 and data_obj['ivHp'][iv] < hp_cut:
            meets = False
        (passing if meets else failing).append(iv)

    if not passing or not failing:
        return []

    results = []
    all_modes = data_obj.get('oppIvModes', ['pvpoke'])
    for mode in all_modes:
        key = f'{moveset_idx}_{mode}'
        scores_flat = score_arrays_all.get(key, [])
        if not scores_flat:
            continue
        for si, scen in enumerate(scenarios):
            for oi, opp in enumerate(opponents):
                pw = sum(1 for iv in passing
                         if scores_flat[iv * nS * nO + si * nO + oi] >= 500
                         ) / len(passing)
                fw = sum(1 for iv in failing
                         if scores_flat[iv * nS * nO + si * nO + oi] >= 500
                         ) / len(failing)
                if pw >= pass_winrate_min and fw <= fail_winrate_max:
                    results.append({
                        'opponent': opp,
                        'scenario': scen,
                        'opp_iv_mode': mode,
                        'pass_wr': pw,
                        'fail_wr': fw,
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
