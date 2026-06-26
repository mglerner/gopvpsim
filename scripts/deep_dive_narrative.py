"""SwagTips-style IV Flavor Guide narrative renderer.

Derives named "flavors" (play-style archetypes like "Premium Bulk" or
"Lickitung Slayer") from the existing tier/boundary/anchor data and
renders them as accessible prose in a purple-bordered HTML zone.

Modeled on RyanSwag's GamePress PvP IV Deep Dive series.
"""

import math

import numpy as np

from deep_dive_analysis import (
    _np_scores,
    _np_stats,
    probe_tier_cutoff_flips,
)
from fast_move_class import charmer_context_line, is_charmer_fast_move


# ---------------------------------------------------------------------------
# Catch probability (geometric distribution)
# ---------------------------------------------------------------------------

def _catches_for_probability(n_qualifying, total_ivs, p):
    """Number of catches needed for probability p of at least one qualifying IV.

    Uses the geometric distribution:  k = ceil(log(1-p) / log(1 - n/total))
    Returns None if n_qualifying <= 0 or >= total_ivs.
    """
    if n_qualifying <= 0 or n_qualifying >= total_ivs:
        return None
    q = 1 - n_qualifying / total_ivs
    if q <= 0 or q >= 1:
        return None
    return math.ceil(math.log(1 - p) / math.log(q))


def _catch_phrase(n_qualifying, total_ivs):
    """Human-readable catch probability string like '~14-28 for a 50-75% chance'.

    Returns '' if the math doesn't apply.
    """
    k50 = _catches_for_probability(n_qualifying, total_ivs, 0.50)
    k75 = _catches_for_probability(n_qualifying, total_ivs, 0.75)
    if k50 is None:
        return ''
    if k50 <= 1:
        return 'almost any will do'
    if (k75 if k75 is not None else k50) > 500:
        return 'very rare'
    noun = 'catch' if k50 == 1 else 'catches'
    if k50 == k75 or k75 is None:
        return f'~{k50} {noun} for a 50% chance'
    return f'~{k50}-{k75} for a 50-75% chance'


# ---------------------------------------------------------------------------
# Flavor derivation
# ---------------------------------------------------------------------------

def _opponent_from_tier_name(name):
    """Extract the opponent name from an auto-derived tier name.

    Tier names from auto_derive_tiers look like:
      "Lickitung Atk", "Azu Bulk", "Atk 123+", "Bulk 140+", "General"
    """
    # Opponent-specific atk tiers: "{Opp} Atk"
    if name.endswith(' Atk'):
        return name[:-4].strip()
    # Opponent-specific def tiers: "{Opp} Bulk"
    if name.endswith(' Bulk'):
        return name[:-5].strip()
    return None


def _axis_shape(atk, def_, hp):
    """Return the constrained-axis shape as a string ('ADH', 'DH', 'A', ...)."""
    s = ''
    if atk > 0:
        s += 'A'
    if def_ > 0:
        s += 'D'
    if hp > 0:
        s += 'H'
    return s


def _stat_signature(atk, def_, hp):
    """Format a stat signature like '135.72 Def, 117 HP'.

    Shows every actively-constrained axis (value > 0); omits axes where
    the value is zero. Per STYLE_ANALYSIS.md "Stat Signature Rule", the
    signature must reflect the real constraint set -- any 2-axis pair is
    valid (Atk+Def without HP, Atk+HP without Def, Def+HP without Atk).
    """
    parts = []
    if atk > 0:
        parts.append(f'{atk:.2f} Atk')
    if def_ > 0:
        parts.append(f'{def_:.2f} Def')
    if hp > 0:
        parts.append(f'{int(hp)} HP')
    return ', '.join(parts)


def _count_qualifying(data_obj, atk_cut, def_cut, hp_cut):
    """Count IVs meeting all stat cuts."""
    n = 0
    for iv in range(data_obj.get('nIvs', 0)):
        if atk_cut > 0 and data_obj['ivAtk'][iv] < atk_cut:
            continue
        if def_cut > 0 and data_obj['ivDef'][iv] < def_cut:
            continue
        if hp_cut > 0 and data_obj['ivHp'][iv] < hp_cut:
            continue
        n += 1
    return n


def _flavor_name_for_tier(name, atk, def_, hp):
    """Map a tier name + final axis shape to a SwagTips-style flavor name.

    Per STYLE_ANALYSIS.md "Stat Signature Rule" the tier name family must
    match the constraint-set shape:

        Name family             Signature shape
        ----------------------- -----------------
        `* Bulk` / `Fortified`  DH (or D, H)
        `* Slayer` (pure)       AH or AD
        `* Slayer` (BP-paired)  ADH
        `General Good`          ADH
        `Attack Weight`         A only
        `Premium Bulk`          DH (or D, H)

    The axis shape (atk/def/hp) is computed *after* HP enrichment so the
    name reflects the final constraint set, not the raw auto-derived tier
    cuts.

    TOML-defined names (GL-General Good, Slight Atk Weight, etc.) pass
    through as-is since the user chose them deliberately.

    Synth-tier names ("<Species> Mirror Bulk" / "<Species> Mirror Atk")
    also pass through. They look like "<Opp> Bulk" / "<Opp> Atk" to the
    naive opponent stripper, which would rewrite "Dewgong Mirror Bulk"
    to "Fortified Dewgong Mirror" — replacing a clean synth name with
    a phrase that reads like Dewgong Mirror is an opponent. Detect
    "<word> Mirror Bulk|Atk" up front and skip flavoring.
    """
    shape = _axis_shape(atk, def_, hp)

    # Synth mirror-tier names pass through unchanged.
    if name.endswith(' Mirror Bulk') or name.endswith(' Mirror Atk'):
        return name

    if name == 'General':
        # Bulk family requires DH / D / H. Anything with Atk becomes
        # General Good (ADH) or Attack Weight (A-only).
        if 'A' in shape and ('D' in shape or 'H' in shape):
            return 'General Good'
        if shape == 'A':
            return 'Attack Weight'
        return 'Premium Bulk'

    # Auto-derived opponent-specific patterns
    if 'A' in shape:
        opp = _opponent_from_tier_name(name)
        if opp:
            return f'{opp} Slayer'
        if name.startswith('Atk '):
            return 'Attack Weight'
    elif 'D' in shape:
        opp = _opponent_from_tier_name(name)
        if opp:
            return f'Fortified {opp}'
        if name.startswith('Bulk '):
            return 'High Bulk'

    # TOML-defined or unrecognized name: pass through
    return name


def derive_narrative_flavors(effective_tiers, all_matchup_boundaries, data_obj):
    """Map tier dicts to named IV flavors for narrative rendering.

    Returns a list of FlavorSpec dicts, broadest (recommended) first,
    then sorted by selectivity (fewest qualifying IVs first).

    When no tier is named "General", the broadest tier (most qualifying
    IVs) is promoted to the recommended/general role.
    """
    if not effective_tiers:
        return []

    # Stage 1: build preliminary flavor dicts; defer name + stat_sig until
    # after HP enrichment so both can be picked from the final axis shape.
    flavors = []
    for t in effective_tiers:
        atk = t.get('attack', 0) or 0
        def_ = t.get('defense', 0) or 0
        hp = t.get('stamina', 0) or 0
        name = t.get('name', '')
        is_general = (name == 'General')

        flavors.append({
            'tier_name': name,
            'name': '',
            'stat_sig': '',
            'atk_cut': atk,
            'def_cut': def_,
            'hp_cut': hp,
            'is_general': is_general,
            'recommended': False,
            'tier_color': t.get('color', 'var(--text-muted)'),
            'tier_desc': t.get('desc', ''),
            'n_qualifying': _count_qualifying(data_obj, atk, def_, hp),
        })

    # Stage 2: enrich flavors with HP co-conditions from matchup boundaries.
    # Per-opponent tiers from auto_derive_tiers don't carry HP, but the
    # matchup boundaries at nearby thresholds often do.
    if all_matchup_boundaries:
        for f in flavors:
            if f['hp_cut'] > 0:
                continue  # already has HP
            stat = 'def' if f['def_cut'] > 0 else 'atk' if f['atk_cut'] > 0 else None
            cut = f['def_cut'] or f['atk_cut']
            if not stat or not cut:
                continue
            hp_vals = []
            for mb in all_matchup_boundaries:
                if mb.get('stat', 'def') == stat and abs(mb['threshold'] - cut) < 5.0:
                    if mb.get('hp_threshold') is not None:
                        hp_vals.append(mb['hp_threshold'])
            if hp_vals:
                hp = min(hp_vals)  # most inclusive HP requirement
                f['hp_cut'] = hp
                f['n_qualifying'] = _count_qualifying(
                    data_obj, f['atk_cut'], f['def_cut'], hp)

    # Stage 3: name and signature are two views of the same final
    # constraint set; compute them together from the enriched axis shape.
    for f in flavors:
        f['name'] = _flavor_name_for_tier(
            f['tier_name'], f['atk_cut'], f['def_cut'], f['hp_cut'])
        f['stat_sig'] = _stat_signature(
            f['atk_cut'], f['def_cut'], f['hp_cut'])

    # If no tier is named General, promote the broadest one
    has_general = any(f['is_general'] for f in flavors)
    if not has_general and flavors:
        broadest = max(flavors, key=lambda f: f['n_qualifying'])
        broadest['is_general'] = True

    # Mark the general flavor as recommended
    for f in flavors:
        if f['is_general']:
            f['recommended'] = True

    # Sort: General/recommended first, then by selectivity (fewest
    # qualifying IVs = most interesting).  Cap at 4 total (General + 3)
    # to keep the narrative scannable - RyanSwag typically wrote 2-3.
    # Drop flavors with 0 qualifying IVs -- the stat threshold is
    # unreachable at this league's CP cap, so the tier is meaningless.
    general = [f for f in flavors if f['is_general']]
    rest = sorted([f for f in flavors if not f['is_general']
                   and f['n_qualifying'] > 0],
                  key=lambda f: f['n_qualifying'])
    result = general + rest[:3]

    # The mirror-synth tier always makes the cut (feedback memory
    # synth_mirror_tier_in_iv_flavor_guide: readers want the
    # mirror-axis story in the Flavor Guide itself, not only in
    # Threshold Tiers). It is typically broad — low selectivity — so
    # the cap above used to cut it silently (2026-06-11 review, R1
    # drop site #1). Append-only: nothing else is displaced.
    def _is_mirror_flavor(f):
        return (f['name'].endswith(' Mirror Bulk')
                or f['name'].endswith(' Mirror Atk'))
    if not any(_is_mirror_flavor(f) for f in result):
        _mirror_extra = next((f for f in rest[3:] if _is_mirror_flavor(f)),
                             None)
        if _mirror_extra is not None:
            result.append(_mirror_extra)

    # Disambiguate duplicate names by appending stat info
    seen = {}
    for f in result:
        seen.setdefault(f['name'], []).append(f)
    for name, group in seen.items():
        if len(group) > 1:
            for f in group:
                primary_stat = (f'{f["def_cut"]:.2f}+ Def' if f['def_cut'] > 0
                                else f'{f["atk_cut"]:.2f}+ Atk' if f['atk_cut'] > 0
                                else '')
                if primary_stat:
                    f['name'] = f'{name} ({primary_stat})'

    return result


# ---------------------------------------------------------------------------
# Trade-off analysis
# ---------------------------------------------------------------------------

def compute_flavor_tradeoffs(flavors, data_obj, score_arrays, moveset_idx,
                             scenarios, opponents,
                             all_matchup_boundaries=None):
    """For each non-General flavor, find matchups gained and lost vs General.

    Returns dict: flavor_name -> {gains: [...], losses: [...]}
    Each gain/loss: {opponent, scenarios: [(s0,s1),...], bait_modes: set}
    """
    general = next((f for f in flavors if f['is_general']), None)
    if not general:
        return {}

    # First, compute what General itself gains (used for loss detection)
    general_results = probe_tier_cutoff_flips(
        data_obj, score_arrays, moveset_idx,
        general['atk_cut'], general['def_cut'], general['hp_cut'],
        scenarios, opponents,
    )
    general_gains = {}  # opp -> set of scenario tuples
    for r in general_results:
        general_gains.setdefault(r['opponent'], set()).add(
            tuple(r['scenario']))

    tradeoffs = {}
    for flavor in flavors:
        if flavor['is_general']:
            continue

        # Use probe_tier_cutoff_flips to find clean win-rate partitions
        # at this flavor's stat cuts
        results = probe_tier_cutoff_flips(
            data_obj, score_arrays, moveset_idx,
            flavor['atk_cut'], flavor['def_cut'], flavor['hp_cut'],
            scenarios, opponents,
        )

        # Group by opponent, collecting scenarios
        gains_by_opp = {}  # opp -> set of scenario tuples
        for r in results:
            gains_by_opp.setdefault(r['opponent'], set()).add(
                tuple(r['scenario']))

        # Find losses via two methods:
        # 1. Direct: partition IVs by flavor vs general-only, check win rates
        losses = _find_losses_vs_general(
            flavor, general, data_obj, score_arrays, moveset_idx,
            scenarios, opponents)
        # 2. Indirect: matchups General gains that this flavor does NOT gain.
        #    This catches cases where the flavor's stricter cuts narrow the
        #    IV pool so much that the win-rate test can't fire cleanly.
        #    BUT: the probe not firing only means the flavor's cuts don't
        #    cleanly PARTITION the matchup — its members may still win it
        #    comfortably (e.g. an atk-only cut on a bulk-driven matchup).
        #    Only call it a loss when the flavor cohort actually loses it
        #    (win rate < 0.5 in every available opp-IV mode); the old
        #    pure set-difference rendered confident "the drop in bulk
        #    will cost the X matchup" prose for matchups the cohort wins
        #    (2026-06-11 review, R2).
        flavor_wr = _flavor_max_winrates(
            flavor, data_obj, score_arrays, moveset_idx, scenarios, opponents)
        scen_index = {tuple(s): si for si, s in enumerate(scenarios)}
        opp_index = {o: oi for oi, o in enumerate(opponents)}
        for opp, gen_scens in general_gains.items():
            flavor_scens = gains_by_opp.get(opp, set())
            lost_scens = gen_scens - flavor_scens
            if lost_scens and flavor_wr is not None:
                oi = opp_index.get(opp)
                if oi is not None:
                    lost_scens = {sc for sc in lost_scens
                                  if flavor_wr[scen_index[sc], oi] < 0.5}
            if lost_scens:
                losses.setdefault(opp, set()).update(lost_scens)

        gains_list = [{'opponent': opp, 'scenarios': sorted(scens)}
                      for opp, scens in sorted(gains_by_opp.items())]
        losses_list = [{'opponent': opp, 'scenarios': sorted(scens)}
                       for opp, scens in sorted(losses.items())]

        tradeoffs[flavor['name']] = {
            'gains': gains_list,
            'losses': losses_list,
        }

    # Store General's gains for the narrative intro
    general_gains_list = [{'opponent': opp, 'scenarios': sorted(scens)}
                          for opp, scens in sorted(general_gains.items())]
    tradeoffs[general['name']] = {
        'gains': general_gains_list,
        'losses': [],
    }

    # Attach relevant matchup boundaries to all flavors (including general)
    if all_matchup_boundaries:
        _attach_boundaries(flavors, tradeoffs, all_matchup_boundaries)

    return tradeoffs


def _flavor_max_winrates(flavor, data_obj, score_arrays, moveset_idx,
                         scenarios, opponents):
    """(nS, nO) win-rate of the flavor's cohort, MAX over opp-IV modes.

    Returns None when stats/scores are unavailable or the cohort is
    empty. Used to gate the indirect loss method: a matchup only counts
    as a flavor loss when the cohort loses it in EVERY available mode.
    """
    nIvs = data_obj.get('nIvs', 0)
    nS = len(scenarios)
    nO = len(opponents)
    if nIvs == 0 or nO == 0:
        return None
    iv_atk, iv_def, iv_hp = _np_stats(data_obj)
    mask = np.ones(nIvs, dtype=bool)
    if flavor['atk_cut'] > 0:
        mask &= iv_atk >= flavor['atk_cut']
    if flavor['def_cut'] > 0:
        mask &= iv_def >= flavor['def_cut']
    if flavor['hp_cut'] > 0:
        mask &= iv_hp >= flavor['hp_cut']
    n = int(mask.sum())
    if n == 0:
        return None
    best = None
    for mode in data_obj.get('oppIvModes', ['pvpoke']):
        scores = _np_scores(score_arrays, moveset_idx, mode, nIvs, nS, nO)
        if scores is None:
            continue
        wr = (scores[mask] >= 500).sum(axis=0) / n
        best = wr if best is None else np.maximum(best, wr)
    return best


def _find_losses_vs_general(flavor, general, data_obj, score_arrays,
                            moveset_idx, scenarios, opponents):
    """Find matchups where General-but-not-flavor IVs win but flavor IVs lose."""
    nIvs = data_obj.get('nIvs', 0)
    nS = len(scenarios)
    nO = len(opponents)
    if nIvs == 0 or nO == 0:
        return {}

    iv_atk, iv_def, iv_hp = _np_stats(data_obj)

    def _meets_cuts(ac, dc, hc):
        m = np.ones(nIvs, dtype=bool)
        if ac > 0:
            m &= iv_atk >= ac
        if dc > 0:
            m &= iv_def >= dc
        if hc > 0:
            m &= iv_hp >= hc
        return m

    flavor_mask = _meets_cuts(flavor['atk_cut'], flavor['def_cut'],
                              flavor['hp_cut'])
    general_mask = _meets_cuts(general['atk_cut'], general['def_cut'],
                               general['hp_cut'])
    general_only_mask = general_mask & ~flavor_mask

    n_flavor = int(flavor_mask.sum())
    n_general_only = int(general_only_mask.sum())
    if n_flavor == 0 or n_general_only == 0:
        return {}

    losses = {}  # opp -> set of scenario tuples
    all_modes = data_obj.get('oppIvModes', ['pvpoke'])
    for mode in all_modes:
        scores = _np_scores(score_arrays, moveset_idx, mode, nIvs, nS, nO)
        if scores is None:
            continue
        wins = scores >= 500
        flavor_wr = wins[flavor_mask].sum(axis=0) / n_flavor
        general_wr = wins[general_only_mask].sum(axis=0) / n_general_only
        sel = (general_wr >= 0.75) & (flavor_wr <= 0.25)
        if not sel.any():
            continue
        si_arr, oi_arr = np.where(sel)
        for si_i, oi_i in zip(si_arr.tolist(), oi_arr.tolist()):
            losses.setdefault(opponents[oi_i], set()).add(
                tuple(scenarios[si_i]))

    return losses


def _attach_boundaries(flavors, tradeoffs, all_matchup_boundaries):
    """Attach relevant matchup boundaries to each flavor's tradeoffs.

    Also attaches boundaries to the general flavor (under a separate
    'general_boundaries' key in tradeoffs) even though it has no
    gains/losses entry.
    """
    general = next((f for f in flavors if f['is_general']), None)

    for flavor in flavors:
        fname = flavor['name']

        # Ensure there's a tradeoffs entry (general may not have one)
        if fname not in tradeoffs:
            tradeoffs[fname] = {'gains': [], 'losses': []}
        td = tradeoffs[fname]

        # Find boundaries that match this flavor's stat range
        relevant = []
        for mb in all_matchup_boundaries:
            stat = mb.get('stat', 'def')
            thresh = mb['threshold']
            if flavor['is_general']:
                # General gets all boundaries
                relevant.append(mb)
            elif stat == 'atk' and flavor['atk_cut'] > 0:
                if abs(thresh - flavor['atk_cut']) < 5.0:
                    relevant.append(mb)
            elif stat == 'def' and flavor['def_cut'] > 0:
                if abs(thresh - flavor['def_cut']) < 5.0:
                    relevant.append(mb)

        td['boundaries'] = relevant


def refine_flavor_names(flavors, tradeoffs):
    """Rename generic flavors based on their dominant tradeoff gains.

    "Attack Weight" -> "{Opp} Slayer" when one opponent dominates gains.
    "High Bulk" -> "Fortified {Opp}" when one opponent dominates gains.
    Must be called after compute_flavor_tradeoffs.
    """
    for flavor in flavors:
        if flavor['is_general']:
            continue
        td = tradeoffs.get(flavor['name'], {})
        gains = td.get('gains', [])
        if not gains:
            continue
        # Consolidate shadow variants for counting
        consolidated = _consolidate_shadow(gains)
        if not consolidated:
            continue
        old_name = flavor['name']
        new_name = None
        naming_opp = None
        if old_name.startswith('Attack Weight') and len(consolidated) >= 1:
            best = max(consolidated,
                       key=lambda g: len(g['scenarios']))
            naming_opp = _base_species(best['opponent'])
            new_name = f'{naming_opp} Slayer'
        elif old_name.startswith('High Bulk') and len(consolidated) >= 1:
            best = max(consolidated,
                       key=lambda g: len(g['scenarios']))
            naming_opp = _base_species(best['opponent'])
            new_name = f'Fortified {naming_opp}'

        if new_name:
            flavor['name'] = new_name
            if old_name in tradeoffs:
                tradeoffs[new_name] = tradeoffs.pop(old_name)
            # Move the naming opponent to the front of the gains list
            # so it's guaranteed to appear in the prose summary.
            td = tradeoffs.get(new_name, {})
            gains = td.get('gains', [])
            if gains and naming_opp:
                front = [g for g in gains
                         if _base_species(g['opponent']) == naming_opp]
                rest = [g for g in gains
                        if _base_species(g['opponent']) != naming_opp]
                td['gains'] = front + rest
            # Rewrite tier_desc to match the renamed opponent. The
            # desc was copied from auto_derive_tiers' matchup-boundary
            # path, which attributes flips by stat-sweep (a different
            # computation than the anchor-flip-driven gain consolidation
            # used to pick naming_opp). Without this rewrite, the tier
            # name says "Fortified Corviknight" while the desc says
            # "vs Quagsire (1 scenario, 23 IVs)" — name and desc point
            # to different opponents.
            if naming_opp and gains:
                primary_scens = sum(
                    len(g['scenarios']) for g in gains
                    if _base_species(g['opponent']) == naming_opp)
                other_opps = sorted({_base_species(g['opponent'])
                                      for g in gains
                                      if _base_species(g['opponent']) != naming_opp})
                desc_parts = [
                    f'{"Bulkpoint(s)" if new_name.startswith("Fortified ") else "Atk gain(s)"} '
                    f'vs {naming_opp} '
                    f'({primary_scens} scenario'
                    f'{"s" if primary_scens != 1 else ""})'
                ]
                if other_opps:
                    desc_parts.append(
                        f'+ {len(other_opps)} secondary '
                        f'opponent{"s" if len(other_opps) != 1 else ""}')
                flavor['tier_desc'] = ' '.join(desc_parts) + '.'

    # Drop wash specialists: if the naming opponent appears in losses at
    # >= the gain-scenario count, the "slayer/fortified" label is
    # misleading (e.g. gains Forretress 1-1 but loses Forretress 2-2).
    to_remove_wash = set()
    for f in flavors:
        if f['is_general']:
            continue
        name = f['name']
        if name.endswith(' Slayer'):
            naming_opp = name[:-len(' Slayer')]
        elif name.startswith('Fortified '):
            naming_opp = name[len('Fortified '):]
        else:
            continue
        td = tradeoffs.get(name, {})
        gain_scens = {tuple(s) for g in td.get('gains', [])
                      for s in g.get('scenarios', [])
                      if _base_species(g['opponent']) == naming_opp}
        loss_scens = {tuple(s) for l in td.get('losses', [])
                      for s in l.get('scenarios', [])
                      if _base_species(l['opponent']) == naming_opp}
        if loss_scens and len(loss_scens) >= len(gain_scens):
            to_remove_wash.add(name)
    if to_remove_wash:
        flavors[:] = [f for f in flavors if f['name'] not in to_remove_wash]
        for name in to_remove_wash:
            tradeoffs.pop(name, None)

    # Drop flavors whose gains are a strict subset of another flavor
    # on the same stat axis.  E.g. "Fortified Lickilicky" (gains: Lickilicky,
    # Sealeo) is redundant when "Fortified Corviknight" (gains: Corviknight,
    # Lickilicky, Sealeo) exists.
    to_remove = set()
    non_general = [f for f in flavors if not f['is_general']]

    def _shape(f):
        return _axis_shape(f.get('atk_cut', 0) or 0,
                           f.get('def_cut', 0) or 0,
                           f.get('hp_cut', 0) or 0)

    for i, fi in enumerate(non_general):
        # Mirror-synth tiers are never dedup'd away: the mirror cohort
        # is deliberately NOT a clean partition (see
        # synthesize_mirror_tier), so its clean-partition gains are
        # often a subset of a Fortified flavor's — but the mirror-axis
        # story is wanted in the guide regardless (2026-06-11 review,
        # R1 drop site #2; mirrors the _flavor_name_for_tier
        # passthrough exemption).
        if (fi['name'].endswith(' Mirror Bulk')
                or fi['name'].endswith(' Mirror Atk')):
            continue
        td_i = tradeoffs.get(fi['name'], {})
        gains_i = {g['opponent'] for g in td_i.get('gains', [])}
        if not gains_i:
            continue
        for j, fj in enumerate(non_general):
            if i == j:
                continue
            # Same stat axis only — the comment above always claimed
            # this but the code never checked, so a def-axis flavor
            # could be removed because its gains were a subset of an
            # ATK-axis flavor's (review R1).
            if _shape(fi) != _shape(fj):
                continue
            td_j = tradeoffs.get(fj['name'], {})
            gains_j = {g['opponent'] for g in td_j.get('gains', [])}
            # fi's gains are a strict subset of fj's gains
            if gains_i < gains_j:
                to_remove.add(fi['name'])
                break
    if to_remove:
        flavors[:] = [f for f in flavors if f['name'] not in to_remove]

    # Re-disambiguate names after renaming
    seen = {}
    for f in flavors:
        seen.setdefault(f['name'], []).append(f)
    for name, group in seen.items():
        if len(group) > 1:
            for f in group:
                primary_stat = (f'{f["def_cut"]:.2f}+ Def' if f['def_cut'] > 0
                                else f'{f["atk_cut"]:.2f}+ Atk' if f['atk_cut'] > 0
                                else '')
                if primary_stat:
                    f['name'] = f'{name} ({primary_stat})'


# ---------------------------------------------------------------------------
# Namesake guarantee (item 1 from post-S5 S5a plan)
# ---------------------------------------------------------------------------

def _naming_opponents(flavor_name):
    """Extract naming opponent(s) from a Slayer / Fortified flavor name.

    Handles:
      "Lapras Slayer"                       -> ["Lapras"]
      "Fortified Lapras"                    -> ["Lapras"]
      "Lapras / Shadow Lapras Slayer"       -> ["Lapras", "Lapras (Shadow)"]
      "Lapras Slayer (123.74+ Atk)"         -> ["Lapras"]

    Returns an empty list for non-opponent-named flavors (Premium Bulk,
    General Good, Attack Weight, High Bulk, etc.).
    """
    name = flavor_name
    paren = name.find(' (')
    if paren >= 0 and (name.endswith(' Def)') or name.endswith(' Atk)')):
        name = name[:paren]
    name = name.strip()

    def _expand_part(part):
        part = part.strip()
        if not part:
            return None
        if part.startswith('Shadow '):
            return part[len('Shadow '):] + ' (Shadow)'
        return part

    if name.endswith(' Slayer'):
        stub = name[:-len(' Slayer')].strip()
    elif name.startswith('Fortified '):
        stub = name[len('Fortified '):].strip()
    else:
        return []

    opps = []
    for part in stub.split(' / '):
        expanded = _expand_part(part)
        if expanded and expanded not in opps:
            opps.append(expanded)
    return opps


def _synthesize_namesake_gain(flavor, naming_opp, all_matchup_boundaries,
                               anchor_flip_records=None):
    """Find the closest gain source against naming_opp to add to gains.

    Searches two data streams:
      1. Matchup boundaries (stat-sweep based)
      2. Anchor-flip records (resolved-TOML-anchor based)
    An opponent-named tier that made it into the narrative is evidence
    that one of these streams carries the matchup; we just need to pull
    the closest entry. Returns a gain entry ``{opponent, scenarios}`` or
    ``None`` if no suitable source exists.
    """
    cut_stat = 'atk' if flavor['atk_cut'] > 0 else 'def'
    cut_val = flavor['atk_cut'] or flavor['def_cut']

    best = None  # (distance, opponent, scenarios_tuple_list)
    if all_matchup_boundaries:
        for mb in all_matchup_boundaries:
            if _base_species(mb['opponent']) != naming_opp:
                continue
            if mb.get('stat', 'def') != cut_stat:
                continue
            dist = abs(mb['threshold'] - cut_val) if cut_val else 0
            if cut_val and dist > 10.0:
                continue
            scens = sorted(tuple(s) for s in mb.get('scenarios', []))
            if not scens:
                continue
            if best is None or dist < best[0]:
                best = (dist, mb['opponent'], scens)

    if anchor_flip_records:
        for rec in anchor_flip_records:
            if _base_species(rec['opponent']) != naming_opp:
                continue
            anchor = rec.get('anchor')
            target = getattr(anchor, 'target_stat', None) if anchor else None
            if target and target != cut_stat:
                continue
            thresh = getattr(anchor, 'threshold_value', None) if anchor else None
            dist = abs(thresh - cut_val) if (thresh and cut_val) else 0
            if cut_val and thresh and dist > 10.0:
                continue
            scens = sorted(tuple(s) for s in rec.get('scenarios', []))
            if not scens:
                continue
            if best is None or dist < best[0]:
                best = (dist, rec['opponent'], scens)

    if not best:
        return None
    return {'opponent': best[1], 'scenarios': best[2]}


def enforce_namesake_guarantee(flavors, tradeoffs, all_matchup_boundaries,
                                anchor_flip_records=None):
    """Ensure every opponent-named flavor has that opponent in its gains.

    Per STYLE_CONFORMANCE_CHECKLIST.md C2: a tier named after an opponent
    must reference at least one matchup against that opponent in its
    gains/prose. If the matchup-flip layer didn't attribute a gain to the
    namesake, synthesize one from the closest relevant matchup boundary
    or anchor-flip record and prepend it so the opening prose mentions
    the namesake.

    The tier's *name* already encodes the opponent (auto_derive_tiers
    built it from one of these two streams), so at least one of them
    should carry a usable entry. If neither does, leave gains as-is.
    """
    for flavor in flavors:
        if flavor['is_general']:
            continue
        naming_opps = _naming_opponents(flavor['name'])
        if not naming_opps:
            continue
        td = tradeoffs.setdefault(flavor['name'], {'gains': [], 'losses': []})
        gains = td.setdefault('gains', [])
        gain_bases = {_base_species(g['opponent']) for g in gains}
        # Compare at base-species level. A flavor named
        # "Fortified Quagsire (Shadow)" is satisfied by a gain against
        # either Quagsire or Quagsire (Shadow) -- both collapse to
        # base 'Quagsire'. Without this strip the check always misses
        # for shadow-suffixed tier names.
        naming_bases = [_base_species(n) for n in naming_opps]
        for naming_base in naming_bases:
            if naming_base in gain_bases:
                continue
            synth = _synthesize_namesake_gain(
                flavor, naming_base, all_matchup_boundaries,
                anchor_flip_records=anchor_flip_records)
            if synth:
                gains.insert(0, synth)
                gain_bases.add(_base_species(synth['opponent']))
        # Even when the namesake is already present, it may be buried
        # behind alphabetically-earlier opponents. Front-move every
        # namesake entry so the opening prose leads with "the {namesake}".
        if naming_bases:
            nb_set = set(naming_bases)
            front = [g for g in gains if _base_species(g['opponent']) in nb_set]
            rest = [g for g in gains if _base_species(g['opponent']) not in nb_set]
            if front and rest:
                td['gains'] = front + rest


# ---------------------------------------------------------------------------
# Identical-stat flavor merge (item 2 / C5 from checklist)
# ---------------------------------------------------------------------------

def _stat_sig_key(flavor):
    """Tuple key for stat-signature equality."""
    return (round(flavor['atk_cut'], 2),
            round(flavor['def_cut'], 2),
            int(flavor['hp_cut']))


def _gains_sig_key(td):
    """Frozenset key for gains-list equality, keyed on (opponent, scenarios).

    Opponent includes shadow flag so Lapras vs Lapras (Shadow) gains don't
    collide when they're really separate matchups.
    """
    entries = []
    for g in td.get('gains', []):
        scens = tuple(sorted(tuple(s) for s in g.get('scenarios', [])))
        entries.append((g['opponent'], scens))
    return frozenset(entries)


def _merge_flavor_names(names):
    """Combine Slayer/Fortified names sharing a family into one.

    "Lapras Slayer" + "Lapras (Shadow) Slayer" -> "Lapras / Shadow Lapras Slayer"
    "Fortified Altaria" + "Fortified Altaria (Shadow)" ->
        "Fortified Altaria / Shadow Altaria"

    Returns None if names don't share a family.
    """
    if not names:
        return None

    def _normalize_opp(stub):
        if stub.endswith(' (Shadow)'):
            return 'Shadow ' + stub[:-len(' (Shadow)')].strip()
        return stub.strip()

    if all(n.endswith(' Slayer') for n in names):
        stubs = [n[:-len(' Slayer')].strip() for n in names]
        parts = []
        for s in stubs:
            for p in s.split(' / '):
                norm = _normalize_opp(p)
                if norm and norm not in parts:
                    parts.append(norm)
        return ' / '.join(parts) + ' Slayer'

    if all(n.startswith('Fortified ') for n in names):
        stubs = [n[len('Fortified '):].strip() for n in names]
        parts = []
        for s in stubs:
            for p in s.split(' / '):
                norm = _normalize_opp(p)
                if norm and norm not in parts:
                    parts.append(norm)
        return 'Fortified ' + ' / '.join(parts)

    return None


def merge_identical_stat_flavors(flavors, tradeoffs):
    """Merge flavors sharing stat signature AND gains list.

    Canonical Oinkologne case: Lapras Slayer + Lapras (Shadow) Slayer at
    identical (123.74 Atk, 149 HP) with identical gains -> "Lapras /
    Shadow Lapras Slayer".

    Negative test: Fortified Lapras (105.19 Def, 153 HP) has a different
    stat signature and MUST NOT merge. Guard: merge key is
    ``(stat_sig, gains_sig)`` exact equality, so DH-axis flavors don't
    collide with AH-axis flavors.
    """
    if len(flavors) < 2:
        return

    groups = {}
    for f in flavors:
        if f['is_general']:
            continue
        td = tradeoffs.get(f['name'], {})
        key = (_stat_sig_key(f), _gains_sig_key(td))
        groups.setdefault(key, []).append(f)

    merged_away = set()  # id()s of flavors absorbed into their group primary
    for key, group in groups.items():
        if len(group) < 2:
            continue
        combined = _merge_flavor_names([g['name'] for g in group])
        if not combined:
            continue  # family mismatch -- leave separate

        primary, others = group[0], group[1:]
        old_name = primary['name']
        primary_td = tradeoffs.get(old_name, {})
        if old_name != combined:
            tradeoffs[combined] = primary_td
            tradeoffs.pop(old_name, None)
        primary['name'] = combined

        for other in others:
            other_td = tradeoffs.pop(other['name'], {}) or {}
            primary_td.setdefault('losses', [])
            primary_td.setdefault('boundaries', [])
            existing_loss_keys = {
                (e['opponent'],
                 tuple(sorted(tuple(s) for s in e.get('scenarios', []))))
                for e in primary_td['losses']
            }
            for lost in other_td.get('losses', []):
                lost_key = (
                    lost['opponent'],
                    tuple(sorted(tuple(s) for s in lost.get('scenarios', [])))
                )
                if lost_key not in existing_loss_keys:
                    primary_td['losses'].append(lost)
                    existing_loss_keys.add(lost_key)
            for mb in other_td.get('boundaries', []):
                if mb not in primary_td['boundaries']:
                    primary_td['boundaries'].append(mb)
            merged_away.add(id(other))

    flavors[:] = [f for f in flavors if id(f) not in merged_away]


# ---------------------------------------------------------------------------
# Prose rendering
# ---------------------------------------------------------------------------

def _scenario_str(scenarios):
    """Format scenario list as '0-0, 1-1, 2-2'."""
    return ', '.join(f'{s[0]}-{s[1]}' for s in sorted(scenarios))


def _opp_colored(name):
    """Wrap opponent name in a colored span."""
    # md5, not builtin hash(): str hashing is PYTHONHASHSEED-randomized
    # per process, which made these colors differ run-to-run (and broke
    # replay-vs-original HTML equality, which is how it was caught —
    # arc S4). Same approach as deep_dive_rendering._opp_color.
    import hashlib
    # Opponent-keyed (md5 of the opponent name): use the unified opponent
    # palette --opp-1..--opp-12, mod 12, matching deep_dive_rendering._opp_color
    # so the same opponent gets the same hue across renderers.
    colors = [f'var(--opp-{i})' for i in range(1, 13)]
    idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(colors)
    return f'<span style="color:{colors[idx]};font-weight:600">{name}</span>'


def _base_species(name):
    """Strip Shadow/XL/etc. suffixes to get the base species name."""
    for suffix in (' (Shadow)', ' (XL)'):
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def _consolidate_shadow(entries):
    """Merge shadow and non-shadow entries that share a base species + scenarios.

    Input: list of {opponent, scenarios} dicts.
    Output: list of {opponent, scenarios, shadow_note} dicts where shadow
    variants with identical scenario sets are folded in.
    """
    from collections import OrderedDict
    grouped = OrderedDict()
    for e in entries:
        base = _base_species(e['opponent'])
        is_shadow = e['opponent'] != base
        scen_key = tuple(tuple(s) for s in sorted(e['scenarios']))
        if base not in grouped:
            grouped[base] = {'base': base, 'scenarios': {},
                             'has_normal': False, 'has_shadow': False}
        g = grouped[base]
        g['scenarios'].setdefault(scen_key, set())
        if is_shadow:
            g['has_shadow'] = True
            g['scenarios'][scen_key].add('shadow')
        else:
            g['has_normal'] = True
            g['scenarios'][scen_key].add('normal')

    result = []
    for base, g in grouped.items():
        # If both normal + shadow exist with identical scenarios, consolidate
        all_scens = set(g['scenarios'].keys())
        both_forms = g['has_normal'] and g['has_shadow']
        all_same = both_forms and all(
            {'normal', 'shadow'} <= forms for forms in g['scenarios'].values())
        if all_same:
            scens = sorted(set(s for sk in all_scens for s in sk))
            result.append({'opponent': base, 'scenarios': scens,
                           'shadow_note': ' (incl. Shadow)'})
        else:
            # Emit separately but in order
            for e in entries:
                if _base_species(e['opponent']) == base:
                    result.append({'opponent': e['opponent'],
                                   'scenarios': e['scenarios'],
                                   'shadow_note': ''})
    return result


def _gain_prose(gains):
    """Generate prose describing matchup gains."""
    if not gains:
        return ''
    consolidated = _consolidate_shadow(gains)
    items = []
    for g in consolidated[:5]:
        scen = _scenario_str(g['scenarios'])
        items.append(f'the {g["opponent"]}{g["shadow_note"]} {scen}')
    if len(consolidated) == 1:
        return f'pick up {items[0]}'
    elif len(consolidated) <= 4:
        all_items = ', '.join(items[:-1]) + f', and {items[-1]}'
        return f'gain {all_items}'
    else:
        shown = ', '.join(items[:3])
        return f'gain several matchups including {shown}'


def _loss_prose(losses):
    """Generate prose describing matchup losses."""
    if not losses:
        return ''
    consolidated = _consolidate_shadow(losses)
    items = []
    for entry in consolidated[:5]:
        scen = _scenario_str(entry['scenarios'])
        items.append(f'{entry["opponent"]}{entry["shadow_note"]} {scen}')
    if len(consolidated) <= 3:
        return ', '.join(items[:-1]) + f', and {items[-1]}' if len(items) > 1 else items[0]
    else:
        shown = ', '.join(items[:3])
        return f'{shown}, among others'


def _boundary_bullets_for_flavor(flavor, tradeoffs, has_bait_axis=False,
                                  general_boundaries=None):
    """Render opponent-centric boundary bullets for a flavor.

    When *general_boundaries* is provided, skip boundaries that are
    already shown in the General flavor's bullets (dedup by opponent +
    threshold + stat).
    """
    td = tradeoffs.get(flavor['name'], {})
    boundaries = td.get('boundaries', [])
    if not boundaries:
        return ''

    # Build a set of (base_opponent, stat, threshold) keys already in General
    gen_keys = set()
    if general_boundaries:
        for gb in general_boundaries:
            gen_keys.add((_base_species(gb['opponent']),
                          gb.get('stat', 'def'),
                          round(gb['threshold'], 2)))

    # Group by (threshold, stat) to consolidate shadow variants
    by_key = {}
    for b in boundaries:
        key = (round(b['threshold'], 2), b.get('stat', 'def'))
        by_key.setdefault(key, []).append(b)

    lines = []
    for (thresh, stat), group in sorted(by_key.items()):
        stat_label = 'Atk' if stat == 'atk' else 'Def'
        # Merge opponents at this threshold
        opp_info = {}
        hp_vals = []
        bait_sets = set()
        for b in group:
            base = _base_species(b['opponent'])
            is_shadow = b['opponent'] != base
            # Skip if already in General
            if (base, stat, thresh) in gen_keys:
                continue
            opp_info.setdefault(base, {'scens': set(), 'shadow': False})
            for s in b['scenarios']:
                opp_info[base]['scens'].add(tuple(s))
            if is_shadow:
                opp_info[base]['shadow'] = True
            if b.get('hp_threshold') is not None:
                hp_vals.append(b['hp_threshold'])
            bait_sets.update(b.get('bait_modes', set()))

        for opp_base, info in opp_info.items():
            scen_str = ', '.join(f'{s[0]}-{s[1]}' for s in sorted(info['scens']))
            if has_bait_axis and len(bait_sets) == 1:
                bait_tag = ' no bait' if 'nobait' in bait_sets else ' with bait'
                scen_str += bait_tag
            hp_str = ''
            if hp_vals:
                hp_str = f' with {min(hp_vals)} HP'
            shadow_note = ' (incl. Shadow)' if info['shadow'] else ''
            lines.append(
                f'<li>{group[0]["threshold"]:.2f} {stat_label}{hp_str} '
                f'for the {_opp_colored(opp_base)}{shadow_note} '
                f'({scen_str})</li>'
            )
        if len(lines) >= 8:
            break
    return '\n'.join(lines[:8])


def _general_boundary_bullets(all_matchup_boundaries, flavor, has_bait_axis=False,
                              stat='def'):
    """Render boundary bullets on the flavor's primary axis (def for the
    General/bulk flavor, atk for an atk-leaning sole flavor)."""
    if not all_matchup_boundaries:
        return ''
    relevant = []
    for mb in all_matchup_boundaries:
        if mb.get('stat', 'def') == stat:
            relevant.append(mb)
    if not relevant:
        return ''

    # Sort by threshold ascending
    relevant.sort(key=lambda b: b['threshold'])
    # Consolidate shadow variants at the same threshold
    by_thresh = {}
    for b in relevant:
        key = round(b['threshold'], 2)
        by_thresh.setdefault(key, []).append(b)

    lines = []
    for thresh_key in sorted(by_thresh.keys()):
        group = by_thresh[thresh_key]
        # Merge opponents sharing this threshold
        opp_scens = {}
        hp_vals = []
        bait_sets = set()
        for b in group:
            base = _base_species(b['opponent'])
            is_shadow = b['opponent'] != base
            opp_scens.setdefault(base, {'scens': set(), 'shadow': False})
            for s in b['scenarios']:
                opp_scens[base]['scens'].add(tuple(s))
            if is_shadow:
                opp_scens[base]['shadow'] = True
            if b.get('hp_threshold') is not None:
                hp_vals.append(b['hp_threshold'])
            bait_sets.update(b.get('bait_modes', set()))

        hp_str = ''
        if hp_vals:
            hp_str = f' with {min(hp_vals)}+ HP'

        # When multiple opponents share the same threshold, group them
        opp_items = list(opp_scens.items())
        if len(opp_items) > 1:
            opp_parts = []
            for opp_base, info in opp_items:
                scen_str = ', '.join(f'{s[0]}-{s[1]}' for s in sorted(info['scens']))
                shadow_note = ' (incl. Shadow)' if info['shadow'] else ''
                opp_parts.append(f'{_opp_colored(opp_base)}{shadow_note} ({scen_str})')
            lines.append(
                f'<li>{group[0]["threshold"]:.2f} Def{hp_str} '
                f'for {", ".join(opp_parts)}</li>'
            )
        else:
            opp_base, info = opp_items[0]
            scen_str = ', '.join(f'{s[0]}-{s[1]}' for s in sorted(info['scens']))
            if has_bait_axis and len(bait_sets) == 1:
                bait_tag = ' no bait' if 'nobait' in bait_sets else ' with bait'
                scen_str += bait_tag
            shadow_note = ' (incl. Shadow)' if info['shadow'] else ''
            lines.append(
                f'<li>{group[0]["threshold"]:.2f} Def{hp_str} '
                f'for the {_opp_colored(opp_base)}{shadow_note} '
                f'({scen_str})</li>'
            )
        if len(lines) >= 8:
            break
    return '\n'.join(lines[:8])


def render_narrative_zone(flavors, tradeoffs, all_matchup_boundaries,
                          data_obj, opp_label, has_bait_axis=False,
                          moveset_idx=0):
    """Render the SwagTips-style IV Flavor Guide as an HTML string.

    Returns HTML string, or '' if there's nothing interesting to narrate.
    """
    if not flavors:
        return ''

    species = data_obj.get('species', 'this Pokemon')
    league = data_obj.get('league', 'Great League')
    # Prettify league name
    league_display = {'great': 'Great League', 'ultra': 'Ultra League',
                      'master': 'Master League'}.get(league, league)

    parts = []
    parts.append('<div class="dd-narrative-zone">\n')
    parts.append(f'<h3 style="color:var(--zone-narrative);margin:0 0 10px 0">'
                 f'IV Flavor Guide (Simulation)</h3>\n')
    parts.append(
        '<p style="margin:0 0 10px 0;font-size:0.82rem;font-style:italic;'
        'color:var(--text-muted);line-height:1.5">'
        'Auto-generated from simulation matchup data. Flavor names '
        '(e.g. "Premium Bulk", "Fortified {Opp}", "{Opp} Slayer") are '
        'derived from which opponents each IV cluster beats, not from '
        'the expert-authored '
        '<a href="#dd-threshold-tiers" style="color:var(--zone-narrative)">Threshold '
        'Tiers</a> section above. This IV Flavor Guide and the '
        'Threshold Tiers answer different questions and may not line '
        'up 1:1. '
        'New to flavor cards? The '
        '<a href="../guides/iv-flavor-guide/" style="color:var(--zone-narrative)">IV '
        'Flavor Guide</a> walks through the six name families and the '
        'trade-off layout.'
        '</p>\n'
    )

    # Charmer-class fast move framing (post-S5 S5a item 4). When the
    # moveset's fast move is a charmer (Charm / Razor Leaf / Waterfall /
    # Dragon Breath / Fairy Wind), stat product usually matters more than
    # Atk breakpoints. Surface that default so readers don't chase atk
    # weight on a species that wants bulk.
    ms_list = data_obj.get('movesets') or []
    if 0 <= moveset_idx < len(ms_list):
        label = ms_list[moveset_idx].get('label', '')
        fast_part = label.split(' / ')[0] if ' / ' in label else label
        if is_charmer_fast_move(fast_part):
            parts.append(
                f'<p class="dd-narrative-prose" '
                f'style="margin:0 0 10px 0;font-size:0.88rem;'
                f'color:var(--text)">'
                f'{charmer_context_line(species)}'
                f'</p>\n'
            )

    # Single-flavor case: just a stat baseline summary
    if len(flavors) == 1:
        f = flavors[0]
        # Describe the flavor's ACTUAL axis — the old branch hardcoded
        # "favors high bulk" (and def-only boundaries) even for an
        # atk-cut sole flavor (2026-06-11 review, R13).
        shape = _axis_shape(f.get('atk_cut', 0) or 0,
                            f.get('def_cut', 0) or 0,
                            f.get('hp_cut', 0) or 0)
        atk_leaning = 'A' in shape and 'D' not in shape
        lean = 'favors attack weight' if atk_leaning else 'favors high bulk'
        parts.append(f'<p class="dd-narrative-prose">'
                     f'In {league_display}, {species} {lean}. '
                     f'{f["stat_sig"]} is a safe baseline.</p>\n')
        bullets = _general_boundary_bullets(
            all_matchup_boundaries, f, has_bait_axis,
            stat='atk' if atk_leaning else 'def')
        if bullets:
            parts.append(f'<ul class="dd-threshold-list">\n{bullets}\n</ul>\n')
        parts.append('</div>\n')
        return ''.join(parts)

    # Multi-flavor: full narrative
    # Intro paragraph
    flavor_names = [f'{f["name"]}' for f in flavors]
    if len(flavor_names) == 2:
        flavor_list = f'{flavor_names[0]} and {flavor_names[1]}'
    else:
        flavor_list = (', '.join(flavor_names[:-1])
                       + f', and {flavor_names[-1]}')

    general = next((f for f in flavors if f['is_general']), flavors[0])

    # Build opponent list for the intro from General's gains + boundary opponents
    gen_td = tradeoffs.get(general['name'], {})
    gen_gains = gen_td.get('gains', [])
    gen_opp_names = []
    if gen_gains:
        consolidated = _consolidate_shadow(gen_gains)
        gen_opp_names = [f'{g["opponent"]}{g["shadow_note"]}'
                         for g in consolidated[:5]]
    # If gains are sparse, supplement from matchup boundary opponents
    if len(gen_opp_names) < 3 and all_matchup_boundaries:
        boundary_opps = set()
        for mb in all_matchup_boundaries:
            if mb.get('stat', 'def') == 'def':
                boundary_opps.add(_base_species(mb['opponent']))
        for opp in sorted(boundary_opps):
            if opp not in gen_opp_names:
                gen_opp_names.append(opp)
            if len(gen_opp_names) >= 5:
                break
    if gen_opp_names:
        if len(gen_opp_names) == 1:
            opp_phrase = gen_opp_names[0]
        elif len(gen_opp_names) <= 3:
            opp_phrase = (', '.join(gen_opp_names[:-1])
                          + f', and {gen_opp_names[-1]}')
        else:
            opp_phrase = (', '.join(gen_opp_names[:3])
                          + f', among others')
        intro_tail = (f', as it plays up {species}\'s potential vs '
                      f'{opp_phrase}')
    else:
        intro_tail = (f', as it balances bulk and attack coverage')

    parts.append(
        f'<p class="dd-narrative-prose">'
        f'In {league_display}, {species} has {len(flavors)} flavors: '
        f'{flavor_list}. In general, the {general["name"]} variation '
        f'may be the flavor of choice{intro_tail}.</p>\n'
    )

    # IV overview table
    total_ivs = data_obj.get('nIvs', 4096)
    overview_rows = []
    for f in flavors:
        n = f['n_qualifying']
        pct = n / total_ivs * 100 if total_ivs > 0 else 0
        cp = _catch_phrase(n, total_ivs)
        rec = ' [Recommended]' if f['recommended'] else ''
        name_str = f['name']
        overview_rows.append(
            f'<tr><td style="color:var(--heading);font-weight:600">{name_str}{rec}</td>'
            f'<td style="text-align:right">{n}</td>'
            f'<td style="text-align:right">{pct:.1f}%</td>'
            f'<td>{cp}</td></tr>'
        )
    if overview_rows:
        parts.append(
            '<table class="dd-narrative-overview" style="margin:8px 0 12px 0;'
            'border-collapse:collapse;font-size:0.85rem;width:100%">\n'
            '<tr style="color:var(--text-muted);border-bottom:1px solid var(--border)">'
            '<th style="text-align:left;padding:2px 8px">Flavor</th>'
            '<th style="text-align:right;padding:2px 8px">IVs</th>'
            '<th style="text-align:right;padding:2px 8px">%</th>'
            '<th style="text-align:left;padding:2px 8px">Catches needed</th>'
            '</tr>\n'
        )
        for row in overview_rows:
            parts.append(row + '\n')
        parts.append('</table>\n')

    # Collect General's boundaries for dedup in specialist bullets
    gen_td = tradeoffs.get(general['name'], {})
    gen_boundaries = gen_td.get('boundaries', [])

    # Per-flavor sections
    for i, flavor in enumerate(flavors):
        fname = flavor['name']
        stat_sig = flavor['stat_sig']
        rec_badge = (' <span class="dd-narrative-rec">[Recommended]</span>'
                     if flavor['recommended'] else '')
        is_first = (i == 0)

        # Skip stat_sig in the summary when the name already embeds it
        # (e.g. "High Bulk (142+ Def)" already has the def threshold)
        name_has_stat = ('+' in fname and ('Def' in fname or 'Atk' in fname))
        summary_label = fname if name_has_stat else f'{fname} ({stat_sig})'

        # General flavor is open by default
        open_attr = ' open' if is_first else ''
        parts.append(
            f'<details class="dd-collapsible"{open_attr}>\n'
            f'<summary style="font-weight:600;color:var(--heading);cursor:pointer">'
            f'{summary_label}{rec_badge}</summary>\n'
        )

        td = tradeoffs.get(fname, {})
        gains = td.get('gains', [])
        losses = td.get('losses', [])

        if flavor['is_general']:
            # General flavor prose
            _render_general_flavor(parts, flavor, all_matchup_boundaries,
                                   species, has_bait_axis, tradeoffs)
        else:
            # Specialist flavor prose
            _render_specialist_flavor(parts, flavor, gains, losses,
                                     tradeoffs, species, has_bait_axis,
                                     general_boundaries=gen_boundaries)

        parts.append('</details>\n')

    # Rank-1 self-check line (RyanSwag addition per post-S5 S5a plan).
    # Compare the stat-product rank-1 IV's own spread against each tier's
    # cuts so the reader can see at a glance whether they're trading stat
    # product for threshold reach or not.
    rank1_line = _render_rank1_self_check(flavors, data_obj, species)
    if rank1_line:
        parts.append(rank1_line)

    parts.append('</div>\n')
    return ''.join(parts)


def _render_rank1_self_check(flavors, data_obj, species):
    """Render a one-line rank-1 self-check against the recommended tier.

    Per RyanSwag's Wigglytuff walk-through, the section ends with a
    check of rank-1's own spread against the tier's thresholds so the
    reader can decide whether rank-1 is "good enough" or whether they
    need a specific IV target.

    Returns an empty string when rank-1 info isn't available.
    """
    ref_iv = data_obj.get('rank1RefIvIdx', -1)
    if ref_iv < 0 or 'ivAtk' not in data_obj:
        return ''
    try:
        r_atk_iv = data_obj['ivA'][ref_iv]
        r_def_iv = data_obj['ivD'][ref_iv]
        r_hp_iv = data_obj['ivS'][ref_iv]
    except (KeyError, IndexError, TypeError):
        # IV triple fields may not be present; fall back to skipping.
        r_atk_iv = r_def_iv = r_hp_iv = None

    r_atk = data_obj['ivAtk'][ref_iv]
    r_def = data_obj['ivDef'][ref_iv]
    r_hp = data_obj['ivHp'][ref_iv]

    recommended = next((f for f in flavors if f.get('recommended')), None)
    if not recommended:
        recommended = next((f for f in flavors if f['is_general']), None)
    if not recommended:
        return ''

    shortfalls = []  # list of (axis_label, need, have)
    if recommended['atk_cut'] > 0 and r_atk < recommended['atk_cut']:
        shortfalls.append(('Atk', f'{recommended["atk_cut"]:.2f}',
                           f'{r_atk:.2f}'))
    if recommended['def_cut'] > 0 and r_def < recommended['def_cut']:
        shortfalls.append(('Def', f'{recommended["def_cut"]:.2f}',
                           f'{r_def:.2f}'))
    if recommended['hp_cut'] > 0 and r_hp < recommended['hp_cut']:
        shortfalls.append(('HP', f'{int(recommended["hp_cut"])}',
                           f'{int(r_hp)}'))

    # Format the rank-1 spread. Prefer IV triple (e.g. "0/15/15") if
    # available; fall back to stat triple.
    if r_atk_iv is not None and r_def_iv is not None and r_hp_iv is not None:
        spread_str = f'{r_atk_iv}/{r_def_iv}/{r_hp_iv}'
    else:
        spread_str = f'{r_atk:.2f}/{r_def:.2f}/{int(r_hp)}'

    if not shortfalls:
        return (
            f'<p class="dd-narrative-prose" '
            f'style="margin-top:10px;font-size:0.88rem">'
            f'Rank-1 {species} ({spread_str}) meets the '
            f'{recommended["name"]} thresholds.'
            f'</p>\n'
        )

    # Summarize shortfalls; keep it readable when multiple axes fall short.
    if len(shortfalls) == 1:
        axis, need, have = shortfalls[0]
        delta_clause = f'falls short on {axis} (needs {need}, has {have})'
    else:
        phrases = [f'{a} (needs {n}, has {h})' for a, n, h in shortfalls]
        delta_clause = 'falls short on ' + ', '.join(phrases[:-1]) + f' and {phrases[-1]}'

    return (
        f'<p class="dd-narrative-prose" '
        f'style="margin-top:10px;font-size:0.88rem">'
        f'Rank-1 {species} ({spread_str}) {delta_clause} vs the '
        f'{recommended["name"]} threshold. If you have rank-1, '
        f'you are trading threshold reach for max stat product.'
        f'</p>\n'
    )


def _render_general_flavor(parts, flavor, all_matchup_boundaries,
                           species, has_bait_axis, tradeoffs=None):
    """Render prose for the General/Premium Bulk flavor."""
    stat_parts = []
    if flavor['def_cut'] > 0:
        stat_parts.append(f'{flavor["def_cut"]:.2f} Def')
    if flavor['hp_cut'] > 0:
        stat_parts.append(f'{int(flavor["hp_cut"])} HP')

    if stat_parts:
        baseline = ' and '.join(stat_parts)
        parts.append(
            f'<p class="dd-narrative-prose">'
            f'{baseline} is a safe baseline for {species}')
    else:
        parts.append(
            f'<p class="dd-narrative-prose">'
            f'The bulk-weighted build is a safe baseline for {species}')

    if flavor['atk_cut'] > 0:
        parts.append(
            f', with an attack floor of {flavor["atk_cut"]:.2f} Atk '
            f'for coverage against key opponents')

    parts.append(f'.</p>\n')

    # HP significance callout
    if flavor['hp_cut'] > 0 and all_matchup_boundaries:
        hp_opps = set()
        for mb in all_matchup_boundaries:
            if mb.get('hp_threshold') is not None:
                hp_opps.add(_base_species(mb['opponent']))
        # Also check if species appears as mirror
        mirror_name = species.lower().replace(' ', '_')
        has_mirror = any(_base_species(mb['opponent']).lower().replace(' ', '_') == mirror_name
                         for mb in (all_matchup_boundaries or [])
                         if mb.get('hp_threshold') is not None)
        if hp_opps or has_mirror:
            hp_sentence = f'{int(flavor["hp_cut"])} HP is also a safe spot'
            opp_list = sorted(hp_opps)[:3]
            if has_mirror:
                hp_sentence += f', helping secure the mirror'
                if opp_list:
                    hp_sentence += (f' and key matchups vs '
                                    + ', '.join(opp_list[:2]))
            elif opp_list:
                hp_sentence += (f', enabling key matchups vs '
                                + ', '.join(opp_list[:3]))
            parts.append(f'<p class="dd-narrative-prose">{hp_sentence}.</p>\n')

    # Boundary bullets
    bullets = _general_boundary_bullets(
        all_matchup_boundaries, flavor, has_bait_axis)
    if bullets:
        parts.append(
            f'<ul class="dd-threshold-list">\n{bullets}\n</ul>\n')


def _render_specialist_flavor(parts, flavor, gains, losses,
                              tradeoffs, species, has_bait_axis,
                              general_boundaries=None):
    """Render prose for a specialist (Slayer/Fortified) flavor."""
    # Opening prose
    if flavor['atk_cut'] > 0:
        # Attack-weighted specialist
        gain_text = _gain_prose(gains)
        if gain_text:
            parts.append(
                f'<p class="dd-narrative-prose">'
                f'The "{flavor["name"]}" {species} trades the comfort of '
                f'bulk in order to {gain_text}. '
                f'{species} would need {flavor["atk_cut"]:.2f} Atk')
            if flavor['hp_cut'] > 0:
                parts.append(
                    f' while maintaining {int(flavor["hp_cut"])} HP')
            parts.append(f'.</p>\n')
        else:
            parts.append(
                f'<p class="dd-narrative-prose">'
                f'The "{flavor["name"]}" {species} pushes attack to '
                f'{flavor["atk_cut"]:.2f} Atk')
            if flavor['hp_cut'] > 0:
                parts.append(
                    f' while maintaining {int(flavor["hp_cut"])} HP')
            parts.append(f'.</p>\n')
    else:
        # Defense-weighted specialist
        gain_text = _gain_prose(gains)
        if gain_text:
            parts.append(
                f'<p class="dd-narrative-prose">'
                f'The "{flavor["name"]}" {species} fortifies its bulk to '
                f'{gain_text}. This requires {flavor["def_cut"]:.2f} Def')
            if flavor['hp_cut'] > 0:
                parts.append(f' with {int(flavor["hp_cut"])} HP')
            parts.append(f'.</p>\n')
        else:
            parts.append(
                f'<p class="dd-narrative-prose">'
                f'The "{flavor["name"]}" build targets '
                f'{flavor["def_cut"]:.2f} Def')
            if flavor['hp_cut'] > 0:
                parts.append(f' with {int(flavor["hp_cut"])} HP')
            parts.append(f'.</p>\n')

    # Opponent-centric boundary bullets (deduplicated vs General)
    bullets = _boundary_bullets_for_flavor(
        flavor, tradeoffs, has_bait_axis,
        general_boundaries=general_boundaries)
    if bullets:
        parts.append(
            f'<ul class="dd-threshold-list">\n{bullets}\n</ul>\n')

    # Loss note
    if losses:
        loss_text = _loss_prose(losses)
        if flavor['atk_cut'] > 0:
            reason = 'The drop in bulk'
        else:
            reason = 'The higher stat requirement'
        parts.append(
            f'<p class="dd-narrative-loss">'
            f'Note: {reason} will cost several matchups, '
            f'such as the {loss_text}.</p>\n')
    elif flavor['n_qualifying'] > 0 and flavor['n_qualifying'] < 50:
        # No detected losses but strict stat requirement - note IV scarcity
        parts.append(
            f'<p class="dd-narrative-loss">'
            f'Note: Only {flavor["n_qualifying"]} IV spreads reach this '
            f'target, so it may require specific IV luck.</p>\n')
