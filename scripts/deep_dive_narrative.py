"""SwagTips-style IV Flavor Guide narrative renderer.

Derives named "flavors" (play-style archetypes like "Premium Bulk" or
"Lickitung Slayer") from the existing tier/boundary/anchor data and
renders them as accessible prose in a purple-bordered HTML zone.

Modeled on RyanSwag's GamePress PvP IV Deep Dive series.
"""

from deep_dive_analysis import probe_tier_cutoff_flips


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


def _stat_signature(atk, def_, hp):
    """Format a stat signature string like '135.72 Def, 117 HP'."""
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


def _flavor_name_for_tier(name, atk, def_):
    """Map a tier name to a SwagTips-style flavor name.

    Auto-derived tier names (General, Lickitung Atk, Bulk 140+) get
    transformed.  TOML-defined names (GH Great, etc.) pass through
    as-is since the user chose them deliberately.
    """
    if name == 'General':
        return 'Premium Bulk'

    # Auto-derived opponent-specific patterns
    if atk > 0:
        opp = _opponent_from_tier_name(name)
        if opp:
            return f'{opp} Slayer'
        if name.startswith('Atk '):
            return 'Attack Weight'
    elif def_ > 0:
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

    flavors = []
    for t in effective_tiers:
        atk = t.get('attack', 0) or 0
        def_ = t.get('defense', 0) or 0
        hp = t.get('stamina', 0) or 0
        name = t.get('name', '')
        is_general = (name == 'General')
        flavor_name = _flavor_name_for_tier(name, atk, def_)
        stat_sig = _stat_signature(atk, def_, hp)

        flavors.append({
            'name': flavor_name,
            'stat_sig': stat_sig,
            'atk_cut': atk,
            'def_cut': def_,
            'hp_cut': hp,
            'is_general': is_general,
            'recommended': False,
            'tier_color': t.get('color', '#888'),
            'tier_desc': t.get('desc', ''),
            'n_qualifying': _count_qualifying(data_obj, atk, def_, hp),
        })

    # Enrich flavors with HP co-conditions from matchup boundaries.
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
            # Find matchup boundaries near this flavor's threshold
            hp_vals = []
            for mb in all_matchup_boundaries:
                if mb.get('stat', 'def') == stat and abs(mb['threshold'] - cut) < 5.0:
                    if mb.get('hp_threshold') is not None:
                        hp_vals.append(mb['hp_threshold'])
            if hp_vals:
                hp = min(hp_vals)  # most inclusive HP requirement
                f['hp_cut'] = hp
                f['stat_sig'] = _stat_signature(f['atk_cut'], f['def_cut'], hp)
                f['n_qualifying'] = _count_qualifying(data_obj,
                                                      f['atk_cut'], f['def_cut'], hp)

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
    general = [f for f in flavors if f['is_general']]
    rest = sorted([f for f in flavors if not f['is_general']],
                  key=lambda f: f['n_qualifying'])
    result = general + rest[:3]

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
        for opp, gen_scens in general_gains.items():
            flavor_scens = gains_by_opp.get(opp, set())
            lost_scens = gen_scens - flavor_scens
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


def _find_losses_vs_general(flavor, general, data_obj, score_arrays,
                            moveset_idx, scenarios, opponents):
    """Find matchups where General-but-not-flavor IVs win but flavor IVs lose."""
    nIvs = data_obj.get('nIvs', 0)
    nS = len(scenarios)
    nO = len(opponents)

    # Partition: "general only" = meets General cuts but not flavor cuts
    # "flavor" = meets flavor cuts
    flavor_ivs = []
    general_only_ivs = []
    for iv in range(nIvs):
        meets_flavor = True
        meets_general = True
        if flavor['atk_cut'] > 0 and data_obj['ivAtk'][iv] < flavor['atk_cut']:
            meets_flavor = False
        if flavor['def_cut'] > 0 and data_obj['ivDef'][iv] < flavor['def_cut']:
            meets_flavor = False
        if flavor['hp_cut'] > 0 and data_obj['ivHp'][iv] < flavor['hp_cut']:
            meets_flavor = False
        if general['atk_cut'] > 0 and data_obj['ivAtk'][iv] < general['atk_cut']:
            meets_general = False
        if general['def_cut'] > 0 and data_obj['ivDef'][iv] < general['def_cut']:
            meets_general = False
        if general['hp_cut'] > 0 and data_obj['ivHp'][iv] < general['hp_cut']:
            meets_general = False

        if meets_flavor:
            flavor_ivs.append(iv)
        elif meets_general:
            general_only_ivs.append(iv)

    if not flavor_ivs or not general_only_ivs:
        return {}

    losses = {}  # opp -> set of scenario tuples
    all_modes = data_obj.get('oppIvModes', ['pvpoke'])
    for mode in all_modes:
        key = f'{moveset_idx}_{mode}'
        scores_flat = score_arrays.get(key, [])
        if not scores_flat:
            continue
        for si, scen in enumerate(scenarios):
            for oi, opp in enumerate(opponents):
                # Flavor IVs should mostly LOSE
                flavor_wr = sum(
                    1 for iv in flavor_ivs
                    if scores_flat[iv * nS * nO + si * nO + oi] >= 500
                ) / len(flavor_ivs)
                # General-only IVs should mostly WIN
                general_wr = sum(
                    1 for iv in general_only_ivs
                    if scores_flat[iv * nS * nO + si * nO + oi] >= 500
                ) / len(general_only_ivs)
                if general_wr >= 0.75 and flavor_wr <= 0.25:
                    losses.setdefault(opp, set()).add(tuple(scen))

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
        if old_name == 'Attack Weight' and len(consolidated) >= 1:
            # Name after the opponent with the most scenario flips
            best = max(consolidated,
                       key=lambda g: len(g['scenarios']))
            base = _base_species(best['opponent'])
            new_name = f'{base} Slayer'
            flavor['name'] = new_name
            # Update tradeoffs key
            if old_name in tradeoffs:
                tradeoffs[new_name] = tradeoffs.pop(old_name)
        elif old_name == 'High Bulk' and len(consolidated) >= 1:
            best = max(consolidated,
                       key=lambda g: len(g['scenarios']))
            base = _base_species(best['opponent'])
            new_name = f'Fortified {base}'
            flavor['name'] = new_name
            if old_name in tradeoffs:
                tradeoffs[new_name] = tradeoffs.pop(old_name)

    # Drop flavors whose gains are a strict subset of another flavor
    # on the same stat axis.  E.g. "Fortified Lickilicky" (gains: Lickilicky,
    # Sealeo) is redundant when "Fortified Corviknight" (gains: Corviknight,
    # Lickilicky, Sealeo) exists.
    to_remove = set()
    non_general = [f for f in flavors if not f['is_general']]
    for i, fi in enumerate(non_general):
        td_i = tradeoffs.get(fi['name'], {})
        gains_i = {g['opponent'] for g in td_i.get('gains', [])}
        if not gains_i:
            continue
        for j, fj in enumerate(non_general):
            if i == j:
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
# Prose rendering
# ---------------------------------------------------------------------------

def _scenario_str(scenarios):
    """Format scenario list as '0-0, 1-1, 2-2'."""
    return ', '.join(f'{s[0]}-{s[1]}' for s in sorted(scenarios))


def _opp_colored(name):
    """Wrap opponent name in a colored span."""
    # Use a simple hash for consistent coloring
    colors = ['#58a6ff', '#f85149', '#3fb950', '#d29922', '#bc8cff',
              '#f0883e', '#e8e6e3', '#79c0ff', '#7ee787', '#d2a8ff']
    idx = hash(name) % len(colors)
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
                           'shadow_note': ''})
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


def _general_boundary_bullets(all_matchup_boundaries, flavor, has_bait_axis=False):
    """Render def-side boundary bullets relevant to the General/bulk flavor."""
    if not all_matchup_boundaries:
        return ''
    # For General, show def-side boundaries near the flavor's def cut
    relevant = []
    for mb in all_matchup_boundaries:
        if mb.get('stat', 'def') == 'def':
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
                          data_obj, opp_label, has_bait_axis=False):
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
    parts.append(f'<h3 style="color:#9b59b6;margin:0 0 10px 0">'
                 f'IV Flavor Guide (Simulation)</h3>\n')

    # Single-flavor case: just a stat baseline summary
    if len(flavors) == 1:
        f = flavors[0]
        parts.append(f'<p class="dd-narrative-prose">'
                     f'In {league_display}, {species} favors high bulk. '
                     f'{f["stat_sig"]} is a safe baseline.</p>\n')
        bullets = _general_boundary_bullets(
            all_matchup_boundaries, f, has_bait_axis)
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
            f'<summary style="font-weight:600;color:#e0d0f0;cursor:pointer">'
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

    parts.append('</div>\n')
    return ''.join(parts)


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
    elif flavor['def_cut'] > 0 and flavor['n_qualifying'] > 0:
        # No detected losses but strict def requirement - note IV scarcity
        parts.append(
            f'<p class="dd-narrative-loss">'
            f'Note: Only {flavor["n_qualifying"]} IV spreads reach this '
            f'Def target, so it may require specific IV luck.</p>\n')
