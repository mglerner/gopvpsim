"""Rendering helpers for IV deep dive HTML output.

Functions that produce HTML fragments (hover text, tier badges, matchup
bullets, etc.) for injection into the interactive deep dive page.  Pure
HTML generation -- no simulation or analysis logic.
"""
import hashlib

import deep_dive_analysis as analysis


def hover_text(r, tier_name=None, ref_per_opp=None, ref_label=None,
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



def threshold_desc(thresh):
    """Human-readable description of a threshold."""
    parts = []
    if thresh['attack'] > 0:
        parts.append(f"Atk≥{thresh['attack']}")
    if thresh['defense'] > 0:
        parts.append(f"Def≥{thresh['defense']}")
    if thresh['stamina'] > 0:
        parts.append(f"HP≥{thresh['stamina']}")
    return ', '.join(parts) if parts else '(no requirements)'



def opp_importance(scores_flat, nIvs, nS, nO, si, top_set, opponents):
    """Rank opponents by how much they differentiate top_set from population."""
    results = []
    for oi in range(nO):
        top_avg = sum(scores_flat[iv * nS * nO + si * nO + oi] for iv in top_set) / len(top_set)
        all_avg = sum(scores_flat[iv * nS * nO + si * nO + oi] for iv in range(nIvs)) / nIvs
        results.append({'opponent': opponents[oi], 'top_avg': top_avg, 'all_avg': all_avg, 'gap': top_avg - all_avg})
    results.sort(key=lambda x: abs(x['gap']), reverse=True)
    return results



def iv_label(data, iv):
    return f"{data['ivA'][iv]}/{data['ivD'][iv]}/{data['ivS'][iv]}"



def tier_badge_html(data, iv):
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



def prose_flip_summary(flip_data, max_gains=3, max_losses=2):
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



def format_stat_cutoffs(cutoffs):
    """Render an IVCategory.stat_cutoffs dict as a human-readable string,
    e.g. ``atk≥128, hp≥139``. Returns '' if no constraints are set."""
    if not cutoffs:
        return ''
    parts = []
    if cutoffs.get('atk'):
        parts.append(f"atk≥{cutoffs['atk']:g}")
    if cutoffs.get('def'):
        parts.append(f"def≥{cutoffs['def']:g}")
    if cutoffs.get('hp'):
        parts.append(f"hp≥{cutoffs['hp']:g}")
    return ', '.join(parts)



def composite_tradeoff_prose(member_idx, comp_cat, parent_categories, data_obj):
    """Auto-generate the per-member tradeoff prose for a composite category.

    The Annihilape 13/0/11 wording is the literal target:
        "Sole Atk Slayer that also clears the Top 5% bulk floor (HP≥139).
         Trades mirror dominance (45/132 wins, vs 132/132 for the top
         survivors) for the broader-meta bulk floor."

    Inputs:
        member_idx: canonical IV index of the member to describe.
        comp_cat: the composite IVCategory.
        parent_categories: dict of name → IVCategory for the parent
            slayer/tier categories the composite was built from. Used
            to compute the "max wins in cohort" baseline.
        data_obj: for stat lookups (used by callers; this helper itself
            only reads parent_categories).

    Returns a single string sentence (HTML-safe; no tags).
    """
    if not comp_cat.source_categories or len(comp_cat.source_categories) < 2:
        return ''
    slayer_name, tier_name = comp_cat.source_categories[0], comp_cat.source_categories[1]
    slayer_parent = parent_categories.get(slayer_name)
    n_in_comp = len(comp_cat.members)

    # Identity sentence
    if n_in_comp == 1:
        identity = (f"The sole {slayer_name} that also clears "
                    f"the {tier_name} threshold")
    else:
        identity = (f"One of {n_in_comp} {slayer_name} members "
                    f"that also clear the {tier_name} threshold")
    cutoffs = format_stat_cutoffs(comp_cat.stat_cutoffs)
    if cutoffs:
        identity += f" ({cutoffs})"
    identity += '.'

    # Tradeoff sentence — compute against the slayer cohort's max wins.
    tradeoff = ''
    if slayer_parent and slayer_parent.member_meta:
        all_wins = [
            meta.get('total_wins', 0)
            for meta in slayer_parent.member_meta.values()
        ]
        max_wins = max(all_wins) if all_wins else 0
        this_wins = (slayer_parent.member_meta.get(member_idx, {})
                     .get('total_wins', 0))
        if max_wins > 0 and this_wins < max_wins:
            tradeoff = (f" Trades mirror dominance ({this_wins}/{max_wins} wins, "
                        f"vs {max_wins}/{max_wins} for the top {slayer_name} "
                        f"survivors) for the {tier_name} cutoff.")
        elif max_wins > 0 and this_wins == max_wins:
            tradeoff = (f" Carries top {slayer_name} mirror wins "
                        f"({this_wins}/{max_wins}) AND clears the {tier_name} "
                        f"cutoff — no tradeoff.")
    return identity + tradeoff



def matchup_subtitle(cat):
    """Render an IVCategory.matchup_conditions list as a one-line summary
    (e.g. ``rank 1 Lickitung · 0v0 · no-bait dim. not yet swept``).
    Returns '' for non-matchup categories."""
    if not cat.matchup_conditions:
        return ''
    bits = []
    for c in cat.matchup_conditions:
        opp = c.get('opponent', '?')
        opp_iv = c.get('opponent_ivs', '?')
        oppiv_label = ('PvPoke default' if opp_iv == 'pvpoke'
                        else 'rank 1' if opp_iv == 'rank1' else opp_iv)
        scen = c.get('scenario', (0, 0))
        bait = c.get('bait')
        outcome = c.get('outcome', 'win')
        b = f'{oppiv_label} {opp} · {scen[0]}v{scen[1]} · {outcome}'
        if bait is None:
            b += ' (bait dim. not yet swept)'
        else:
            b += f' · {bait}'
        bits.append(b)
    return ' | '.join(bits)



def render_matchup_boundary_bullets(boundaries):
    """Render matchup-flipping boundaries as HTML <li> bullets.

    Format: "141.66 Def + 138 HP flips Medicham (1v1, 1v2) [85 IVs]"
    """
    lines = []
    for b in boundaries:
        scen_str = ', '.join(
            f'{s[0]}v{s[1]}' for s in sorted(b['scenarios']))
        hp_str = ''
        if b.get('hp_threshold') is not None:
            hp_str = (f' + <span class="dd-strong">'
                      f'{b["hp_threshold"]} HP</span>')
        stat_label = 'Atk' if b.get('stat') == 'atk' else 'Def'
        lines.append(
            f'<li><span class="dd-strong">'
            f'{b["threshold"]:.2f} {stat_label}</span>{hp_str} '
            f'flips <b>{b["opponent"]}</b> '
            f'(<span class="dd-gain">{scen_str}</span>) '
            f'<span class="dd-small">[{b["n_passing"]} IVs]</span></li>'
        )
    return lines



def anchor_group_id(parent, opponent, target_stat, move_id):
    """Deterministic short id for an anchor bullet's (parent, opponent,
    target_stat, move_id) group. Used as a DOM attribute so JS can
    look up which of the user's canonical IVs pass this specific
    bullet and fill in a "— yours: 0/15/15, 1/14/15" annotation.
    """
    import hashlib as _hl
    key = '|'.join(str(x) for x in (parent, opponent, target_stat, move_id or ''))
    return 'af-' + _hl.md5(key.encode('utf-8')).hexdigest()[:10]



def render_anchor_flip_bullets(records, anchor_passing_sink=None):
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

    When ``anchor_passing_sink`` is a dict, each emitted bullet
    populates it with ``{anchor_id: sorted(passing_iv_idx_list)}``
    where the passing set is the union across all sub-anchors in the
    group. The sink-provided path also injects a
    ``<span class="user-anchor-hits" data-anchor-id="…"></span>``
    placeholder into every bullet so the JS can fill it in with
    "— yours: a/d/s, a/d/s" after a Poke Genie CSV is loaded.
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
                move_str = f' ({analysis.pretty_name(first.move_id)})'

            # Scenarios: union across sub-anchors of the same group
            # (different damage tiers of the same move usually flip
            # the same scenarios, but if they diverge we show all).
            scen_set = set()
            for r in recs:
                for s in r['scenarios']:
                    scen_set.add(tuple(s))
            scen_strs = ', '.join(f'{s[0]}v{s[1]}' for s in sorted(scen_set))

            # HP co-condition: if any record in the group carries an
            # hp_threshold, show it alongside the def threshold.
            hp_thresholds = [r.get('hp_threshold') for r in recs
                             if r.get('hp_threshold') is not None]
            hp_str = ''
            if hp_thresholds:
                hp_str = (f' + <span class="dd-strong">{min(hp_thresholds)}'
                          f' HP</span>')

            # Anchor id + passing-IV union for the user-collection
            # annotation layer. Only populated when a sink was passed.
            anchor_span = ''
            if anchor_passing_sink is not None:
                anchor_id = anchor_group_id(
                    first.parent, recs[0]['opponent'],
                    first.target_stat, first.move_id,
                )
                # Union passing_ivs across every sub-anchor in the group.
                # Any IV in the union meets at least one sub-anchor's
                # flip condition for this (parent, opponent, move) bullet.
                union = set()
                for r in recs:
                    for iv in r.get('passing_ivs', []) or []:
                        union.add(iv)
                # Store once per anchor_id. If the same id appears in
                # multiple grouping passes (e.g. tier-filtered + flat
                # list), the underlying record set is identical, so
                # overwriting is a no-op.
                anchor_passing_sink[anchor_id] = sorted(union)
                anchor_span = (
                    f' <span class="user-anchor-hits" '
                    f'data-anchor-id="{anchor_id}"></span>'
                )

            lines.append(
                f'<li><span class="dd-strong">{min_thresh:.2f} {stat_label}</span>'
                f'{hp_str} '
                f'for <b>{anchor_label}</b>{move_str} vs {recs[0]["opponent"]} '
                f'(<span class="dd-gain">{scen_strs}</span>)'
                f'{anchor_span}</li>'
            )
    return lines


