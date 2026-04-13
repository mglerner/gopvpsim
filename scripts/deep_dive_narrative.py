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
                primary_stat = (f'{f["def_cut"]:.0f}+ Def' if f['def_cut'] > 0
                                else f'{f["atk_cut"]:.0f}+ Atk' if f['atk_cut'] > 0
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

        # Now find losses: matchups where General wins but this flavor loses.
        # Partition: IVs meeting General but NOT this flavor's cuts.
        # Use the General tier's cuts as baseline.
        losses = _find_losses_vs_general(
            flavor, general, data_obj, score_arrays, moveset_idx,
            scenarios, opponents)

        gains_list = [{'opponent': opp, 'scenarios': sorted(scens)}
                      for opp, scens in sorted(gains_by_opp.items())]
        losses_list = [{'opponent': opp, 'scenarios': sorted(scens)}
                       for opp, scens in sorted(losses.items())]

        tradeoffs[flavor['name']] = {
            'gains': gains_list,
            'losses': losses_list,
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


def _gain_prose(gains):
    """Generate prose describing matchup gains."""
    if not gains:
        return ''
    items = []
    for g in gains[:5]:
        scen = _scenario_str(g['scenarios'])
        items.append(f'the {g["opponent"]} {scen}')
    if len(gains) == 1:
        return f'pick up {items[0]}'
    elif len(gains) <= 3:
        all_items = ', '.join(items[:-1]) + f', and {items[-1]}'
        return f'gain {all_items}'
    else:
        shown = ', '.join(items[:3])
        return f'gain several matchups including {shown}'


def _loss_prose(losses):
    """Generate prose describing matchup losses."""
    if not losses:
        return ''
    items = []
    for l in losses[:5]:
        scen = _scenario_str(l['scenarios'])
        items.append(f'{l["opponent"]} {scen}')
    if len(losses) <= 3:
        return ', '.join(items[:-1]) + f', and {items[-1]}' if len(items) > 1 else items[0]
    else:
        shown = ', '.join(items[:3])
        return f'{shown}, among others'


def _boundary_bullets_for_flavor(flavor, tradeoffs, has_bait_axis=False):
    """Render opponent-centric boundary bullets for a flavor."""
    td = tradeoffs.get(flavor['name'], {})
    boundaries = td.get('boundaries', [])
    if not boundaries:
        return ''

    lines = []
    for b in boundaries[:8]:
        stat_label = 'Atk' if b.get('stat') == 'atk' else 'Def'
        scen_str = ', '.join(f'{s[0]}-{s[1]}' for s in sorted(b['scenarios']))
        bait_modes = b.get('bait_modes', set())
        if has_bait_axis and len(bait_modes) == 1:
            bait_tag = ' no bait' if 'nobait' in bait_modes else ' with bait'
            scen_str += bait_tag
        hp_str = ''
        if b.get('hp_threshold') is not None:
            hp_str = f' with {b["hp_threshold"]} HP'
        opp = b['opponent']
        lines.append(
            f'<li>{b["threshold"]:.2f} {stat_label}{hp_str} '
            f'for the Rank 1 {_opp_colored(opp)} '
            f'({scen_str})</li>'
        )
    return '\n'.join(lines)


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
    lines = []
    for b in relevant[:8]:
        scen_str = ', '.join(f'{s[0]}-{s[1]}' for s in sorted(b['scenarios']))
        bait_modes = b.get('bait_modes', set())
        if has_bait_axis and len(bait_modes) == 1:
            bait_tag = ' no bait' if 'nobait' in bait_modes else ' with bait'
            scen_str += bait_tag
        hp_str = ''
        if b.get('hp_threshold') is not None:
            hp_str = f' with {b["hp_threshold"]}+ HP'
        lines.append(
            f'<li>{b["threshold"]:.2f} Def{hp_str} '
            f'flips {_opp_colored(b["opponent"])} '
            f'({scen_str})</li>'
        )
    return '\n'.join(lines)


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
                 f'IV Flavor Guide</h3>\n')

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
    parts.append(
        f'<p class="dd-narrative-prose">'
        f'In {league_display}, {species} has {len(flavors)} flavors: '
        f'{flavor_list}. In general, the {general["name"]} variation '
        f'may be the flavor of choice, as it plays up {species}\'s '
        f'potential with a balance of bulk and coverage.</p>\n'
    )

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
                                   species, has_bait_axis)
        else:
            # Specialist flavor prose
            _render_specialist_flavor(parts, flavor, gains, losses,
                                     tradeoffs, species, has_bait_axis)

        parts.append('</details>\n')

    parts.append('</div>\n')
    return ''.join(parts)


def _render_general_flavor(parts, flavor, all_matchup_boundaries,
                           species, has_bait_axis):
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
            f'{baseline} is a safe baseline for {species}. ')
    else:
        parts.append(
            f'<p class="dd-narrative-prose">'
            f'The bulk-weighted build is a safe baseline for {species}. ')

    if flavor['atk_cut'] > 0:
        parts.append(
            f'An attack floor of {flavor["atk_cut"]:.2f} Atk provides '
            f'coverage against key opponents. ')

    parts.append(
        f'IVs at or above these thresholds cover the broadest set of '
        f'matchups without needing to specialize.</p>\n')

    # Boundary bullets
    bullets = _general_boundary_bullets(
        all_matchup_boundaries, flavor, has_bait_axis)
    if bullets:
        parts.append(
            f'<ul class="dd-threshold-list">\n{bullets}\n</ul>\n')


def _render_specialist_flavor(parts, flavor, gains, losses,
                              tradeoffs, species, has_bait_axis):
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

    # Opponent-centric boundary bullets
    bullets = _boundary_bullets_for_flavor(
        flavor, tradeoffs, has_bait_axis)
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
            f'Note: {reason} will lose several matchups, '
            f'such as the {loss_text}.</p>\n')
