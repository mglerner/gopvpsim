"""Rendering helpers for IV deep dive HTML output.

Functions that produce HTML fragments (hover text, tier badges, matchup
bullets, etc.) for injection into the interactive deep dive page.  Pure
HTML generation -- no simulation or analysis logic.
"""
import hashlib
import math
import re

from dataclasses import dataclass, field

import deep_dive_analysis as analysis


# ---------------------------------------------------------------------------
# Shared data types and utilities
# ---------------------------------------------------------------------------

def parse_mode(composite_mode):
    """Decompose a composite mode string into (opp_iv_mode, bait_mode).

    Accepted forms:
      'pvpoke'         -> ('pvpoke', 'bait')     # bait-on default
      'rank1'          -> ('rank1',  'bait')
      'pvpoke:bait'    -> ('pvpoke', 'bait')
      'pvpoke:nobait'  -> ('pvpoke', 'nobait')
      'rank1:nobait'   -> ('rank1',  'nobait')

    Legacy callers that only know the opp-iv axis can pass
    ``'pvpoke'``/``'rank1'`` and get the bait-on default.
    """
    if ':' in composite_mode:
        opp_iv, bait = composite_mode.split(':', 1)
        return opp_iv, bait
    return composite_mode, 'bait'


def compose_mode(opp_iv_mode, bait_mode='bait'):
    """Inverse of ``parse_mode``. Bait-on collapses to the bare opp-iv form
    so existing keys (e.g. ``f'{mi}_pvpoke'``) stay unchanged when bait mode
    isn't part of the sweep."""
    if bait_mode == 'nobait':
        return f'{opp_iv_mode}:nobait'
    return opp_iv_mode


def mode_pretty_label(composite_mode):
    """Human-readable label for a composite mode, e.g. for dropdowns."""
    opp_iv, bait = parse_mode(composite_mode)
    opp_label = 'PvPoke Defaults' if opp_iv == 'pvpoke' else 'Rank 1'
    if bait == 'nobait':
        return f'{opp_label}, no bait'
    return opp_label


@dataclass
class IVCategory:
    """A named IV grouping with explicit provenance.

    Abstracts over the several sources of named IV groupings the deep dive
    already produces (anchor-driven slayer categories, stat-cutoff threshold
    tiers, future matchup-conditional categories) so a single renderer can
    surface them all uniformly. Composite categories (intersections of
    multiple parents) are the framework's payoff: ``13/0/11 is the rare
    bulk-floor slayer`` falls out as ``Atk Slayer ∩ Top 5%`` with one IV.

    Fields are intentionally permissive: a slayer kind populates
    ``source_anchors``, a tier kind populates ``source_tier`` and
    ``stat_cutoffs``, a composite populates ``source_categories``, a
    future matchup kind populates ``matchup_conditions``. The renderer
    inspects whichever fields are set.

    ``member_meta`` carries per-IV info the renderer needs (e.g. mirror
    wins, the original IV triple) without forcing the renderer to plumb
    extra data structures alongside the category list.
    """
    name: str
    kind: str  # 'slayer' | 'tier' | 'structural' | 'composite' | 'matchup'
    members: list  # canonical IV indices, sorted ascending
    description: str = ''
    # Provenance -- exactly which upstream sources built this category.
    source_categories: list = field(default_factory=list)  # composites
    source_anchors: list = field(default_factory=list)     # slayer kinds
    source_tier: object = None                             # tier kinds (str or None)
    # Membership predicates -- declarative; multiple shapes coexist.
    stat_cutoffs: object = None  # dict {'atk', 'def', 'hp'} or None
    matchup_conditions: object = None
    # Per-member info: maps canonical IV index -> dict with whatever
    # the renderer needs (total_wins, avg_score, original triple, etc.).
    member_meta: dict = field(default_factory=dict)


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




def render_notable_ivs_section(categories, data_obj, opp_iv_mode,
                                  notable_max_pct=0.05,
                                  notable_max_count=5,
                                  max_members_shown=5):
    """Render the "Notable IVs" HTML section from a list of IVCategory.

    Surfaces composite (slayer ∩ tier) and matchup categories — the
    intersections that the SwagTips-style structured-IV-categories goal
    is about. Pure slayer and pure tier categories already have
    dedicated UI elsewhere on the page; this section is *additive*,
    not a replacement, for round one.

    Args:
        categories: full list from build_iv_categories(). Pure
            slayer/tier kinds are filtered out at render time so the
            section stays focused on intersections.
        data_obj: the JS-bound data object (for IV labels, sp ranks).
        opp_iv_mode: 'pvpoke' or 'rank1' (used for the prose).
        notable_max_pct: float — categories with member count <= this
            fraction of nIvs are tagged dd-notable. The UI checkbox
            defaults to "show only notable" using this class.
        notable_max_count: hard cap on the notable bucket regardless
            of pct (e.g. ≤ 5 members is always notable).
        max_members_shown: per-card cap on listed members before the
            "expand" toggle.

    Returns: HTML string. Empty string if no notable categories exist.
    """
    n_ivs = data_obj.get('nIvs', 0) or 1
    parent_categories = {c.name: c for c in categories
                         if c.kind in ('slayer', 'tier', 'structural')}
    target = [c for c in categories if c.kind in ('composite', 'matchup')]
    if not target:
        return ''

    # Per-card unique counter so the JS expand toggle can address each
    # card individually. Resets per call to _render_notable_ivs_section,
    # which is fine because the section is rendered once per page.
    card_uid = 0

    # Sort: composites first (the headline), then matchups, with smaller
    # categories first within each kind so the most distinctive cards
    # land at the top of the grid.
    kind_order = {'composite': 0, 'matchup': 1}
    target.sort(key=lambda c: (kind_order.get(c.kind, 99), len(c.members), c.name))

    parts = []
    parts.append('<h3 class="dd-h3" id="dd-notable-ivs">Notable IVs</h3>\n')
    parts.append(
        '<p class="dd-small">Cross-category IVs and notable matchup '
        'wins. Composite cards (slayer&nbsp;∩&nbsp;tier) surface IVs '
        'that satisfy a slayer anchor <em>and</em> a stat-cutoff '
        'threshold tier — the rare intersections that trade some '
        'slayer optimum for a broader-meta floor (or vice versa). '
        'Matchup cards surface non-trivial '
        '(opponent,&nbsp;scenario)&nbsp;partitions for selective '
        'matchups. Pure slayer cards live in the Mirror Slayer '
        'Iteration block below; pure tier cards in the Threshold Tiers '
        'section above. The bait-axis dimension is not yet swept '
        '— see TODO &ldquo;Baiting policy as a deep-dive sim '
        'axis.&rdquo;</p>\n'
    )

    # Notability filter checkbox. Default ON: show only small,
    # distinctive categories. JS toggles a class on the section
    # container; each card carries dd-notable / dd-not-notable.
    parts.append("""<script>
function ddNotableToggle(cb) {
  var sec = document.getElementById('dd-notable-ivs-section');
  if (!sec) return;
  sec.classList.toggle('dd-notable-only', cb.checked);
}
function ddNotableExpand(cardId, btn, nHidden, nVisible) {
  // Per-card "Show all N" / "Collapse" toggle. Flips dd-iv-shown
  // on every dd-iv-hidden row inside this card so the overflow
  // members appear or disappear in place. Same pattern as the
  // slayer-card expand toggle.
  var card = document.getElementById(cardId);
  if (!card) return;
  var rows = card.querySelectorAll('.dd-iv-hidden');
  if (!rows.length) return;
  var nowShown = rows[0].classList.contains('dd-iv-shown');
  rows.forEach(function(r) { r.classList.toggle('dd-iv-shown', !nowShown); });
  btn.textContent = nowShown
    ? ('Show all ' + (nHidden + nVisible))
    : ('Collapse to top ' + nVisible);
}
</script>
""")
    parts.append(
        '<div class="dd-callout"><label>'
        '<input type="checkbox" id="dd-notable-only-cb" checked '
        'onchange="ddNotableToggle(this)"> '
        'Show only notable categories '
        f'(≤ {int(notable_max_pct * 100)}% of cohort or '
        f'≤ {notable_max_count} members). Uncheck to see every '
        'non-trivial intersection.</label></div>\n'
    )

    parts.append(
        '<div id="dd-notable-ivs-section" class="dd-notable-only">\n'
    )
    parts.append('<div class="dd-rec-grid">\n')

    for cat in target:
        n_members = len(cat.members)
        is_notable = (n_members <= notable_max_count
                      or n_members <= notable_max_pct * n_ivs)
        notable_cls = 'dd-notable' if is_notable else 'dd-not-notable'

        card_uid += 1
        card_id = f'dd-notable-card-{card_uid}'
        parts.append(f'<div class="dd-rec-card {notable_cls}" id="{card_id}">\n')
        parts.append(
            f'<h4>{cat.name} '
            f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
            f'({n_members} IV{"s" if n_members != 1 else ""})'
            f'</span></h4>\n'
        )
        # Description and provenance subtitle
        if cat.kind == 'composite':
            cutoffs = format_stat_cutoffs(cat.stat_cutoffs)
            sub = (f'{" + ".join(cat.source_categories)}'
                   + (f' · {cutoffs}' if cutoffs else ''))
            parts.append(f'<p class="dd-small dd-prose">{sub}</p>\n')
        elif cat.kind == 'matchup':
            sub = matchup_subtitle(cat)
            if sub:
                parts.append(f'<p class="dd-small dd-prose">{sub}</p>\n')

        # Member list — sort by total_wins desc when available, else
        # by IV index. Render every member; rows past max_members_shown
        # get the dd-iv-hidden class and the expand button toggles
        # dd-iv-shown on them (matching the slayer-card pattern).
        def _sort_key(idx):
            wins = cat.member_meta.get(idx, {}).get('total_wins', 0)
            return (-wins, idx)
        members_sorted = sorted(cat.members, key=_sort_key)

        # Cap total rendered members to avoid multi-MB HTML for large
        # matchup cards (e.g. 2200 IVs beating Lapras). Top members by
        # wins are the most informative; the rest add bytes but no signal.
        max_members_rendered = 30
        for row_i, m_idx in enumerate(members_sorted[:max_members_rendered]):
            triple = (data_obj['ivA'][m_idx],
                      data_obj['ivD'][m_idx],
                      data_obj['ivS'][m_idx])
            atk = data_obj['ivAtk'][m_idx]
            def_ = data_obj['ivDef'][m_idx]
            hp = data_obj['ivHp'][m_idx]
            sp_rank = data_obj['spRanks'][m_idx]
            label = f'{triple[0]}/{triple[1]}/{triple[2]}'
            row_cls = ' class="dd-iv-hidden"' if row_i >= max_members_shown else ''
            parts.append(
                f'<p{row_cls}><b>{label}</b> &mdash; '
                f'atk {atk:.2f}, def {def_:.2f}, hp {hp}, '
                f'SP&nbsp;#{sp_rank}</p>\n'
            )
            if cat.kind == 'composite':
                prose = composite_tradeoff_prose(
                    m_idx, cat, parent_categories, data_obj
                )
                if prose:
                    prose_cls = ' dd-iv-hidden' if row_i >= max_members_shown else ''
                    parts.append(
                        f'<p class="dd-prose{prose_cls}">{prose}</p>\n'
                    )
        if n_members > max_members_rendered:
            parts.append(
                f'<p class="dd-iv-hidden dd-small">'
                f'… {n_members - max_members_rendered} more not rendered '
                f'(top {max_members_rendered} shown)</p>\n'
            )

        if n_members > max_members_shown:
            n_hidden = n_members - max_members_shown
            parts.append(
                f'<button class="dd-iv-toggle" '
                f'onclick="ddNotableExpand(\'{card_id}\', this, '
                f'{n_hidden}, {max_members_shown})">'
                f'Show all {n_members}'
                f'</button>\n'
            )
        parts.append('</div>\n')  # rec-card

    parts.append('</div>\n')  # rec-grid
    parts.append('</div>\n')  # dd-notable-ivs-section
    return ''.join(parts)


_aggregate_flips_by_anchor = analysis.aggregate_flips_by_anchor


_find_matchup_boundaries = analysis.find_matchup_boundaries








def render_threshold_tier_cards(data_obj, anchor_flip_records,
                                  avg_ranks, flip_map,
                                  max_members_shown=10,
                                  max_members_rendered=50,
                                  override_tiers=None,
                                  score_arrays=None,
                                  moveset_idx=0,
                                  flips_detail=None,
                                  matchup_boundaries=None,
                                  anchor_passing_sink=None):
    """RyanSwag-style threshold tier cards.

    Each tier becomes a card whose headline is the tier's stat-target spec
    (``atk≥X, def≥Y, hp≥Z``) and whose body is the set of anchor-flip
    bullets that the tier's spec actually clears, plus a collapsed table
    of the tier's member IVs.

    Filter rule: an anchor with ``target_stat='atk'`` belongs to a tier iff
    the tier specifies an atk cutoff and that cutoff is ``>=`` the anchor's
    threshold value (i.e. the tier clears the anchor). Symmetric for def.
    Overlap across tiers is intentional.

    Args:
        override_tiers: optional list of tier dicts to use instead of
            ``data_obj['tiers']``. Used by the auto-derive path when the
            TOML doesn't supply tiers.
    """
    tiers = override_tiers if override_tiers is not None else data_obj.get('tiers', [])
    if not tiers:
        return ''
    n_ivs = data_obj.get('nIvs', 0)
    iv_tiers_precomputed = data_obj.get('ivTiers') if override_tiers is None else None
    scenarios = [tuple(s) for s in data_obj.get('scenarios', [])]
    opponents = data_obj.get('opponents', [])

    parts = []
    parts.append('<h3 class="dd-h3" id="dd-threshold-tiers">Threshold Tiers</h3>\n')
    parts.append(
        '<p class="dd-small">Stat-target headlines from <code>thresholds/'
        '*.toml</code>, each grouped with the named anchors its spec '
        'clears and the IV spreads that meet it. Tiers may share bullets '
        '— a stricter tier above also clears everything a looser tier '
        'below clears, and the overlap is intentional. The flat list of '
        'every anchor (regardless of tier) lives in <em>Anchor-Driven '
        'Matchup Flips</em> below.</p>\n'
    )
    parts.append('<div class="dd-rec-grid">\n')

    for ti, t in enumerate(tiers):
        atk_cut = t.get('attack', 0) or 0
        def_cut = t.get('defense', 0) or 0
        hp_cut = t.get('stamina', 0) or 0
        cutoff_bits = []
        if atk_cut > 0:
            cutoff_bits.append(f'atk≥{atk_cut:.2f}')
        if def_cut > 0:
            cutoff_bits.append(f'def≥{def_cut:.2f}')
        if hp_cut > 0:
            cutoff_bits.append(f'hp≥{hp_cut:g}')
        cutoffs_str = ', '.join(cutoff_bits) if cutoff_bits else 'no cutoff'

        # Filter: which anchor records does this tier clear?
        tier_records = []
        for rec in anchor_flip_records:
            a = rec['anchor']
            tv = getattr(a, 'threshold_value', None)
            if tv is None:
                continue
            stat = a.target_stat
            if stat == 'atk' and atk_cut > 0 and atk_cut >= tv:
                tier_records.append(rec)
            elif stat == 'def' and def_cut > 0 and def_cut >= tv:
                tier_records.append(rec)

        # Tier membership: use precomputed ivTiers when available (TOML path),
        # else compute on the fly from stat cutoffs (auto-derive path).
        if iv_tiers_precomputed is not None:
            tier_ivs = [iv for iv in range(n_ivs)
                        if iv_tiers_precomputed[iv] == ti]
        else:
            tier_ivs = []
            for iv in range(n_ivs):
                meets = True
                if atk_cut > 0 and data_obj['ivAtk'][iv] < atk_cut:
                    meets = False
                if def_cut > 0 and data_obj['ivDef'][iv] < def_cut:
                    meets = False
                if hp_cut > 0 and data_obj['ivHp'][iv] < hp_cut:
                    meets = False
                if meets:
                    tier_ivs.append(iv)
        n_members = len(tier_ivs)

        color = t.get('color', '#888')
        # Slug for the "N of yours qualify" placeholder. Must match the
        # JS computation in deep_dive_engine.js updateTierCardCounts.
        import re as _re
        _tier_slug = _re.sub(r'^-|-$', '',
                             _re.sub(r'[^a-z0-9]+', '-', t['name'].lower()))
        parts.append('<div class="dd-rec-card">\n')
        parts.append(
            f'<h4>'
            f'<span class="dd-badge" style="background:{color};color:#000">'
            f'{t["name"]}</span> '
            f'<span class="dd-small" style="font-weight:400;color:#b0b8c4">'
            f'· {cutoffs_str}</span> '
            f'<span class="dd-small" style="font-weight:400;color:#8b949e">'
            f'({n_members} IV{"s" if n_members != 1 else ""})'
            f'</span> '
            f'<span id="tier-card-yours-{_tier_slug}" '
            f'class="dd-small" '
            f'style="font-weight:400;color:#ff40ff;display:none"></span>'
            f'</h4>\n'
        )
        # --- Auto-generated prose summary for the card ---
        if tier_records:
            # Collect unique opponents whose anchors this tier clears
            tier_opps = sorted({r['opponent'] for r in tier_records})
            # Count only — no sink here; the actual rendered bullets
            # below populate the sink.
            n_bullets = len(render_anchor_flip_bullets(tier_records))
            scen_set = set()
            for r in tier_records:
                for s in r['scenarios']:
                    scen_set.add(tuple(s))
            prose_parts = []
            if tier_opps:
                opp_str = ', '.join(tier_opps[:4])
                if len(tier_opps) > 4:
                    opp_str += f', +{len(tier_opps) - 4} more'
                prose_parts.append(
                    f'Clears {n_bullets} anchor'
                    f'{"s" if n_bullets != 1 else ""} across '
                    f'{len(scen_set)} shield scenario'
                    f'{"s" if len(scen_set) != 1 else ""}, '
                    f'covering {opp_str}.'
                )
            if t.get('desc'):
                prose_parts.append(t['desc'])
            if prose_parts:
                parts.append(
                    f'<p class="dd-prose">{" ".join(prose_parts)}</p>\n'
                )
        elif t.get('desc'):
            parts.append(f'<p class="dd-prose">{t["desc"]}</p>\n')

        # --- Anchor-flip bullets (collapsed past 5) ---
        max_bullets_visible = 5
        if tier_records:
            bullets = render_anchor_flip_bullets(
                tier_records, anchor_passing_sink=anchor_passing_sink)
            if bullets:
                tier_card_uid = f'dd-tier-{ti}'
                n_vis = min(len(bullets), max_bullets_visible)
                parts.append('<ul class="dd-threshold-list">\n')
                parts.append('\n'.join(bullets[:n_vis]))
                if len(bullets) > max_bullets_visible:
                    for b in bullets[max_bullets_visible:]:
                        parts.append(
                            f'\n<li class="dd-iv-hidden" '
                            f'data-tier-card="{tier_card_uid}">{b[4:]}'
                        )  # strip leading <li> since we're adding class
                    parts.append('\n</ul>\n')
                    n_hidden = len(bullets) - max_bullets_visible
                    parts.append(
                        f'<button class="dd-slayer-toggle" '
                        f'onclick="(function(btn){{'
                        f'var items=document.querySelectorAll('
                        f'\'[data-tier-card=\\&quot;{tier_card_uid}\\&quot;]\');'
                        f'var shown=items.length>0&&items[0].classList.contains(\'dd-iv-shown\');'
                        f'items.forEach(function(r){{r.classList.toggle(\'dd-iv-shown\',!shown);}});'
                        f'btn.textContent=shown'
                        f'?\'Show all {len(bullets)} anchors\''
                        f':\'Collapse to top {n_vis}\';'
                        f'}})(this)">Show all {len(bullets)} anchors</button>\n'
                    )
                else:
                    parts.append('\n</ul>\n')
        elif cutoff_bits:
            parts.append(
                '<p class="dd-small">No named anchors fall within '
                "this tier's spec.</p>\n"
            )

        # --- Matchup-flipping boundaries covered by this tier ---
        if matchup_boundaries:
            tier_mbs = []
            for mb in matchup_boundaries:
                mb_thresh = mb['threshold']
                mb_stat = mb.get('stat', 'def')
                mb_hp = mb.get('hp_threshold')
                # Does this tier's spec cover this boundary?
                if mb_stat == 'def':
                    if def_cut <= 0 or def_cut < mb_thresh:
                        continue  # tier has no def cutoff or too low
                else:  # atk
                    if atk_cut <= 0 or atk_cut < mb_thresh:
                        continue  # tier has no atk cutoff or too low
                if mb_hp is not None and hp_cut > 0 and hp_cut < mb_hp:
                    continue  # tier's hp isn't high enough
                tier_mbs.append(mb)
            # Filter out opponents already shown by anchor bullets
            anchor_opps = {r['opponent'] for r in tier_records}
            new_mbs = [mb for mb in tier_mbs
                       if mb['opponent'] not in anchor_opps]
            if new_mbs:
                mb_bullets = render_matchup_boundary_bullets(new_mbs)
                if mb_bullets:
                    parts.append(
                        '<p class="dd-small" style="margin-top:6px">'
                        '<b style="color:#3fb950">Matchup-flipping '
                        'boundaries</b> (full-battle stat targets, not '
                        'just damage tiers):</p>\n'
                    )
                    parts.append('<ul class="dd-threshold-list">\n')
                    parts.append('\n'.join(mb_bullets))
                    parts.append('\n</ul>\n')

        # --- Tier-cutoff probe: matchup flips at the tier's own spec ---
        # Catches flips that fall between Level 3 sub-anchor thresholds
        # (e.g. acidicArisen's 143.03 def vs Azu lives between damage
        # tiers at 142.34 and 144.41).
        if score_arrays and (atk_cut > 0 or def_cut > 0):
            probe_results = _probe_tier_cutoff_flips(
                data_obj, score_arrays, moveset_idx,
                atk_cut, def_cut, hp_cut,
                scenarios, opponents,
            )
            if probe_results:
                # Group by opponent, union scenarios
                _probe_opps: dict = {}
                for pr in probe_results:
                    _probe_opps.setdefault(pr['opponent'], set()).add(
                        tuple(pr['scenario']))
                # Filter out opponents already covered by anchor bullets
                _anchor_opps = {r['opponent'] for r in tier_records}
                _new_opps = {o for o in _probe_opps if o not in _anchor_opps}
                if _new_opps:
                    parts.append(
                        '<p class="dd-small" style="margin-top:6px">'
                        '<b style="color:#d29922">Additional matchup flips '
                        'at this tier\'s spec</b> (not explained by a single '
                        'anchor — may involve HP or multi-stat interactions):'
                        '</p>\n'
                    )
                    parts.append('<ul class="dd-threshold-list">\n')
                    for opp in sorted(_new_opps):
                        scens = sorted(_probe_opps[opp])
                        scen_str = ', '.join(f'{s[0]}v{s[1]}' for s in scens)
                        parts.append(
                            f'<li>vs <b>{opp}</b> '
                            f'(<span class="dd-gain">{scen_str}</span>)'
                            f'</li>\n'
                        )
                    parts.append('</ul>\n')

        # --- Member IVs (collapsed, with expand toggle) ---
        if tier_ivs:
            tier_ivs.sort(key=lambda iv: avg_ranks[iv])
            parts.append(
                f'<details class="dd-flip-detail">'
                f'<summary>Member IVs ({n_members})</summary>\n'
            )
            parts.append('<table class="dd-table dd-narrow">\n')
            parts.append(
                '<tr><th>IV</th><th>Atk</th><th>Def</th><th>HP</th>'
                '<th>Avg rank</th>'
                '<th title="Matchup wins gained minus lost vs the '
                'PvPoke default reference IV. Hover each cell for '
                'the gain/loss breakdown.">Net flips</th></tr>\n'
            )
            n_to_render = min(len(tier_ivs), max_members_rendered)
            n_truncated = len(tier_ivs) - n_to_render
            for row_i, iv in enumerate(tier_ivs[:n_to_render]):
                triple = (data_obj['ivA'][iv], data_obj['ivD'][iv],
                          data_obj['ivS'][iv])
                _g, _l, net = flip_map.get(iv, (0, 0, 0))
                nc = 'dd-gain' if net > 0 else ('dd-loss' if net < 0 else '')
                # Build hover text with matchup names when available
                fd = (flips_detail or {}).get(iv)
                if fd:
                    hover_lines = []
                    if fd.get('gains'):
                        gain_names = [f"{e['opponent']} {e['scenario']}"
                                      for e in fd['gains'][:6]]
                        hover_lines.append(f"Gained: {', '.join(gain_names)}")
                        if len(fd['gains']) > 6:
                            hover_lines[-1] += f' +{len(fd["gains"])-6} more'
                    if fd.get('losses'):
                        loss_names = [f"{e['opponent']} {e['scenario']}"
                                      for e in fd['losses'][:6]]
                        hover_lines.append(f"Lost: {', '.join(loss_names)}")
                        if len(fd['losses']) > 6:
                            hover_lines[-1] += f' +{len(fd["losses"])-6} more'
                    flip_hover = '\n'.join(hover_lines) if hover_lines else f'net {net:+d}'
                else:
                    flip_hover = (f'+{_g} gained, -{_l} lost vs reference IV '
                                  f'(net {net:+d})')
                row_cls = (' class="dd-slayer-hidden"'
                           if row_i >= max_members_shown else '')
                parts.append(
                    f'<tr{row_cls}>'
                    f'<td>{triple[0]}/{triple[1]}/{triple[2]}</td>'
                    f'<td>{data_obj["ivAtk"][iv]:.2f}</td>'
                    f'<td>{data_obj["ivDef"][iv]:.2f}</td>'
                    f'<td>{data_obj["ivHp"][iv]}</td>'
                    f'<td>#{avg_ranks[iv]}</td>'
                    f'<td class="{nc}" title="{flip_hover}">'
                    f'{net:+d}</td></tr>\n'
                )
            if n_truncated > 0:
                parts.append(
                    f'<tr class="dd-slayer-hidden"><td colspan="6" '
                    f'class="dd-small">… {n_truncated} more not rendered '
                    f'(top {n_to_render} by avg rank shown)</td></tr>\n'
                )
            parts.append('</table>\n')
            n_expandable = min(n_to_render, n_members)
            if n_expandable > max_members_shown:
                parts.append(
                    f'<button class="dd-slayer-toggle" '
                    f'onclick="(function(btn){{'
                    f'var t=btn.previousElementSibling;'
                    f'var rows=t.querySelectorAll(\'tr.dd-slayer-hidden\');'
                    f'var shown=rows.length>0&&rows[0].classList.contains(\'dd-slayer-shown\');'
                    f'rows.forEach(function(r){{r.classList.toggle(\'dd-slayer-shown\',!shown);}});'
                    f'btn.textContent=shown'
                    f'?\'Show top {n_expandable} IVs\''
                    f':\'Collapse to top {max_members_shown}\';'
                    f'}})(this)">Show top {n_expandable} IVs</button>\n'
                )
            parts.append('</details>\n')
        else:
            # Mirror the existing tier-summary "0 spreads" callout: tell the
            # reader whether nothing reaches the spec or whether everything
            # also clears a stricter tier above (the tier-priority artifact).
            all_meeting = 0
            for iv in range(n_ivs):
                meets = True
                if atk_cut > 0 and data_obj['ivAtk'][iv] < atk_cut:
                    meets = False
                if def_cut > 0 and data_obj['ivDef'][iv] < def_cut:
                    meets = False
                if hp_cut > 0 and data_obj['ivHp'][iv] < hp_cut:
                    meets = False
                if meets:
                    all_meeting += 1
            if all_meeting > 0:
                parts.append(
                    f'<p class="dd-small">{all_meeting} IV spread'
                    f'{"s" if all_meeting != 1 else ""} meet this spec, '
                    f'but all also qualify for a stricter tier above.</p>\n'
                )
            else:
                parts.append(
                    '<p class="dd-small">0 IV spreads can reach this spec '
                    'at this CP cap.</p>\n'
                )

        parts.append('</div>\n')  # rec-card
    parts.append('</div>\n')  # rec-grid
    return ''.join(parts)


def generate_threshold_descriptions(flips, data, avg_scores, ranked, opp_iv_mode):
    """Generate HSH/RyanSwag-style threshold descriptions from flip data.

    Returns list of HTML paragraphs describing key stat thresholds with
    matchup justification.
    """
    # Collect all unique (opponent, scenario) flips across IVs and find
    # which stat change drives the flip
    opp_label = 'PvPoke default' if parse_mode(opp_iv_mode)[0] == 'pvpoke' else 'rank 1'

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


def scenario_ranks(scores_flat, nIvs, nS, nO):
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






_pvp_damage = analysis.pvp_damage


_narrate_flip = analysis.narrate_flip


_build_move_tuples = analysis.build_move_tuples
_pretty_name = analysis.pretty_name
_pretty_moveset = analysis.pretty_moveset










def detect_banding(stat_values, scores, stat_name):
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
            'eta_squared': eta_sq, 'correlation': pearson_r(stat_values, scores),
            'top_jumps': jumps[:5], 'group_means': gmeans}


def detect_clusters(scores, data):
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




_find_flips = analysis.find_flips


def pearson_r(xs, ys):
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx)**2 for x in xs))
    dy = math.sqrt(sum((y - my)**2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0
