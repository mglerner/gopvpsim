"""Auto-generate Species narrative prose from dive data.

Replaces Claude-drafted prose in `thresholds/*.toml` and `articles/*.toml`
with deterministic templates that pull the same facts straight from the
sim. Drops editorial adjectives that the sim can't justify, keeps the
numbers that readers actually use.

Surface:

* ``render_intro(species, dive, *, cd_move_fast, baseline_move_fast, ...)``
  - Stats frame + aggregate win-rate delta + top-3 gains / drops.
* ``render_good_at(species, dive, *, cd_move_fast, baseline_move_fast, ...)``
  - Opponents flipped into wins by the CD move, grouped by primary type.
* ``render_bad_at(species, dive, *, cd_move_fast, baseline_move_fast, ...)``
  - Mirror for opponents flipped out of wins.
* ``classify_atk_weight(iv, rank1)``
  - Label a Notable IV spread as rank-1 / no-atk / slight / heavy / bulk-max.

**Honesty gate.** For flip-claiming language (``render_good_at`` /
``render_bad_at``) an opponent only appears when its aggregate win-rate
actually crosses the 50% line between baseline and CD -- not just
moves by a lot. This enforces the ``docs/auto_gen_narrative_plan.md``
"Quality concern" criterion: prefer silence over a false flip. The
``render_intro`` stat-line lists biggest *gains* / *drops* by ppt
(descriptive, not flip-claiming) but restricts them to true flips when
possible so the three bullets align with what the ``good_at`` / ``bad_at``
sections will claim below.

Output is plain text (optionally with ``**bold**`` / ``*italic*``), shaped
for ``render_article.format_body()``. No HTML.
"""
from __future__ import annotations

from typing import Iterable, Optional


# --------------------------------------------------------------------
# Moveset picking
# --------------------------------------------------------------------

def _fast_move_from_label(label: str) -> str:
    """Extract the fast move id (first ``/``-segment) from a moveset label.

    'MUD_SLAP / TRAILBLAZE, HIGH_HORSEPOWER' -> 'MUD_SLAP'. The dive
    HTML's ``DATA.movesets[0].label`` uses this shape; splits on the
    literal "/" and trims, matching ``generate_article._moveset_fast_move``.
    """
    return (label or '').split('/', 1)[0].strip().upper()


def _pick_moveset(dive: dict, fast_move_id: str) -> Optional[dict]:
    """Return the moveset summary whose fast move matches.

    Matches case-insensitively on the DATA.movesets[0].label fast-move
    segment (everything before the first ``/``). Returns ``None`` when
    no sibling carries that fast move; callers then fall back to an
    empty-prose body.
    """
    if not fast_move_id:
        return None
    target = fast_move_id.strip().upper()
    for m in dive.get('movesets') or []:
        if _fast_move_from_label(m.get('label') or '') == target:
            return m
    return None


# --------------------------------------------------------------------
# Gamemaster helpers (optional; caller can pass a pre-loaded dict)
# --------------------------------------------------------------------

def _gm_move_type(gm: Optional[dict], move_id_or_name: str) -> Optional[str]:
    """Look up a move's type in the gamemaster, case-insensitive.

    Returns the lowercase type string (e.g. "ground"), or None when the
    move is unknown or no gamemaster was supplied. Matches on moveId
    first then falls back to display name.
    """
    if not gm or not move_id_or_name:
        return None
    target = move_id_or_name.strip().lower()
    for m in gm.get('moves') or []:
        if (m.get('moveId') or '').lower() == target:
            return (m.get('type') or '').lower() or None
        if (m.get('name') or '').lower() == target:
            return (m.get('type') or '').lower() or None
    return None


def _gm_move_display(gm: Optional[dict], move_id_or_name: str) -> str:
    """Return a human display name for a move id, falling back to ``Title_Case``.

    'MUD_SLAP' -> 'Mud Slap' when the move is missing from gm or gm is None.
    """
    if gm:
        target = (move_id_or_name or '').strip().lower()
        for m in gm.get('moves') or []:
            if (m.get('moveId') or '').lower() == target:
                name = m.get('name')
                if name:
                    return name
            if (m.get('name') or '').lower() == target:
                return m.get('name')
    raw = (move_id_or_name or '').strip()
    if not raw:
        return ''
    return ' '.join(w.capitalize() for w in raw.replace('_', ' ').split())


def _gm_species_primary_type(gm: Optional[dict], species_name: str) -> Optional[str]:
    """Lookup a species' primary type (for opponent-bucket grouping).

    Accepts either the display name (``Stunfisk (Galarian)``) or the
    speciesId (``stunfisk_galarian``). Returns the first non-none type
    from the gamemaster's types field, lowercased. Returns ``None`` when
    the species is unknown or gm is missing.
    """
    if not gm or not species_name:
        return None
    as_id = (species_name.lower()
             .replace(' ', '_')
             .replace('(', '')
             .replace(')', ''))
    for p in gm.get('pokemon') or []:
        if (p.get('speciesId') or '') == as_id:
            types = p.get('types') or []
            if isinstance(types, str):
                types = [types]
            for t in types:
                if t and t != 'none':
                    return t.lower()
            return None
        if (p.get('speciesName') or '') == species_name:
            types = p.get('types') or []
            if isinstance(types, str):
                types = [types]
            for t in types:
                if t and t != 'none':
                    return t.lower()
            return None
    return None


def _gm_species_base_stats(gm: Optional[dict], species_name: str) -> Optional[tuple[int, int, int]]:
    """Return ``(atk, def, hp)`` base stats for the species, or None."""
    if not gm or not species_name:
        return None
    for p in gm.get('pokemon') or []:
        if (p.get('speciesName') or '') == species_name:
            bs = p.get('baseStats') or {}
            a, d, h = bs.get('atk'), bs.get('def'), bs.get('hp')
            if a is not None and d is not None and h is not None:
                return (int(a), int(d), int(h))
    return None


# --------------------------------------------------------------------
# Opponent delta arithmetic
# --------------------------------------------------------------------

def _opp_display_name(opp) -> str:
    """Robust opponent-name access across dive-data shapes.

    DATA.opponents carries either strings or dicts (depending on dive
    vintage); prefer ``displayName`` / ``name`` fields then fall back to
    the raw string.
    """
    if isinstance(opp, dict):
        return (opp.get('displayName')
                or opp.get('name')
                or opp.get('speciesName')
                or opp.get('speciesId')
                or '')
    return str(opp) if opp is not None else ''


def _opp_species_key(opp) -> str:
    """Best-effort key for a gamemaster lookup (prefers speciesId then name)."""
    if isinstance(opp, dict):
        return (opp.get('speciesId')
                or opp.get('speciesName')
                or opp.get('displayName')
                or opp.get('name')
                or '')
    return str(opp) if opp is not None else ''


def _per_opp_deltas(dive: dict, cd_ms: dict, base_ms: dict) -> list[dict]:
    """Per-opponent CD-vs-baseline win-rate comparison.

    Both movesets share the dive's canonical opponent list so indices
    align 1:1. Returns one entry per opponent with raw win rates, the
    ppt delta (CD minus baseline), and a ``flipped_in`` / ``flipped_out``
    flag capturing whether the aggregate win rate actually crossed 50%.
    Opponents missing from either moveset's per_opponent_win_rate are
    silently skipped.
    """
    opponents = dive.get('opponents') or []
    cd_wrs = cd_ms.get('per_opponent_win_rate') or []
    base_wrs = base_ms.get('per_opponent_win_rate') or []
    n = min(len(opponents), len(cd_wrs), len(base_wrs))
    out: list[dict] = []
    for i in range(n):
        cd_wr = cd_wrs[i]
        base_wr = base_wrs[i]
        delta_pp = (cd_wr - base_wr) * 100.0
        out.append({
            'opp': opponents[i],
            'display': _opp_display_name(opponents[i]),
            'cd_wr': cd_wr,
            'base_wr': base_wr,
            'delta_pp': delta_pp,
            'flipped_in': (cd_wr >= 0.5) and (base_wr < 0.5),
            'flipped_out': (cd_wr < 0.5) and (base_wr >= 0.5),
        })
    return out


# --------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------

def _fmt_delta_pp(delta_pp: float) -> str:
    """Format a delta as a signed pp string (``+12pp`` / ``-7pp`` / ``0pp``)."""
    rounded = int(round(delta_pp))
    if rounded > 0:
        return f'+{rounded}pp'
    if rounded < 0:
        return f'{rounded}pp'
    return '0pp'


def _league_label(league: Optional[str]) -> str:
    """League aggregate-win-rate label: 'GL aggregate' / 'UL aggregate' / 'Aggregate'."""
    key = (league or '').strip().lower()
    if key == 'great':
        return 'GL aggregate'
    if key == 'ultra':
        return 'UL aggregate'
    if key == 'master':
        return 'ML aggregate'
    return 'Aggregate'


def render_intro(
    species: str,
    dive: dict,
    *,
    cd_move_fast: str,
    baseline_move_fast: str,
    league: Optional[str] = None,
    cd_date: Optional[str] = None,
    form_comparison: bool = False,
    gm: Optional[dict] = None,
) -> str:
    """Render the ``[Species.intro]`` body as plain prose.

    Four optional sentences, space-separated:

    1. Stat frame + CD-move coverage type (gamemaster lookup).
    2. Aggregate win rate w/ CD vs baseline, signed ppt delta.
    3. Biggest gains (top-3 per-opponent ppt improvements, flip-filtered).
    4. Biggest drops (top-3 per-opponent ppt regressions, flip-filtered).

    Gains / drops lines are skipped when no true-flip opponent exists.
    Returns empty string when the CD or baseline moveset isn't in the
    dive (caller skips the block).

    ``form_comparison=True`` adds an article-mode sentence pointing at
    the form-comparison section below. Dive-mode leaves it off.
    """
    cd_ms = _pick_moveset(dive, cd_move_fast)
    base_ms = _pick_moveset(dive, baseline_move_fast)
    if cd_ms is None or base_ms is None:
        return ''

    sentences: list[str] = []

    # 1. Stat line.
    stats_txt = species
    base_stats = _gm_species_base_stats(gm, species)
    if base_stats is not None:
        a, d, h = base_stats
        stats_txt = f'{species} ({a}/{d}/{h})'
    cd_type = _gm_move_type(gm, cd_move_fast)
    cd_display = _gm_move_display(gm, cd_move_fast)
    if cd_type:
        sentences.append(
            f'{stats_txt}. **{cd_display}** adds '
            f'{cd_type.capitalize()}-type coverage.'
        )
    else:
        sentences.append(f'{stats_txt}. **{cd_display}** is the new fast-move option.')

    # 2. Aggregate line.
    cd_wr_pct = cd_ms.get('win_rate', 0.0) * 100.0
    base_wr_pct = base_ms.get('win_rate', 0.0) * 100.0
    delta_pp = cd_wr_pct - base_wr_pct
    base_display = _gm_move_display(gm, baseline_move_fast)
    sentences.append(
        f'{_league_label(league)} win rate: {cd_wr_pct:.1f}% '
        f'({base_display} baseline: {base_wr_pct:.1f}%, '
        f'{_fmt_delta_pp(delta_pp)}).'
    )

    # 3/4. Biggest gains / drops (flip-filtered).
    deltas = _per_opp_deltas(dive, cd_ms, base_ms)
    gains = sorted(
        [d for d in deltas if d['flipped_in']],
        key=lambda d: d['delta_pp'], reverse=True,
    )[:3]
    drops = sorted(
        [d for d in deltas if d['flipped_out']],
        key=lambda d: d['delta_pp'],
    )[:3]
    if gains:
        sentences.append(
            'Biggest gains: '
            + ', '.join(f'{g["display"]} {_fmt_delta_pp(g["delta_pp"])}' for g in gains)
            + '.'
        )
    if drops:
        sentences.append(
            'Biggest drops: '
            + ', '.join(f'{d["display"]} {_fmt_delta_pp(d["delta_pp"])}' for d in drops)
            + '.'
        )

    if form_comparison:
        sentences.append(
            'Which form to prioritize on CD day is covered in the '
            'form-comparison section below.'
        )

    if cd_date:
        sentences.append(f'Community Day: {cd_date}.')

    return ' '.join(sentences)


def _group_by_primary_type(
    deltas: Iterable[dict],
    gm: Optional[dict],
) -> list[tuple[str, list[dict]]]:
    """Bucket opponent-delta entries by primary type (lowercased).

    Returns a sorted list of ``(type_or_'Other', [entry, ...])`` tuples.
    ``'Other'`` holds entries whose species couldn't be looked up (no
    gm, or unknown species). Within a bucket, entries keep their input
    order (callers sort first, then group).
    """
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for d in deltas:
        key = (_gm_species_primary_type(gm, _opp_species_key(d['opp']))
               or 'Other')
        key_label = key.capitalize() if key != 'Other' else 'Other'
        if key_label not in buckets:
            buckets[key_label] = []
            order.append(key_label)
        buckets[key_label].append(d)
    return [(t, buckets[t]) for t in order]


def render_good_at(
    species: str,
    dive: dict,
    *,
    cd_move_fast: str,
    baseline_move_fast: str,
    gm: Optional[dict] = None,
) -> str:
    """Render ``meta_role.good_at`` as a type-bucketed flip list.

    Returns empty string when no opponent meets the flip-in criterion
    (``cd_wr >= 0.5 AND base_wr < 0.5``). Groups by the opponent's
    primary type; buckets are emitted in the order they first appear
    (sorted by delta desc within each bucket). CSV-style comma-
    separated opponent list per type, one bullet line per type.
    """
    cd_ms = _pick_moveset(dive, cd_move_fast)
    base_ms = _pick_moveset(dive, baseline_move_fast)
    if cd_ms is None or base_ms is None:
        return ''
    deltas = _per_opp_deltas(dive, cd_ms, base_ms)
    flipped = sorted(
        [d for d in deltas if d['flipped_in']],
        key=lambda d: d['delta_pp'], reverse=True,
    )
    if not flipped:
        return ''
    cd_display = _gm_move_display(gm, cd_move_fast)

    paras = [f'Wins {species} picks up by adding {cd_display}:']
    for type_label, entries in _group_by_primary_type(flipped, gm):
        opp_strs = ', '.join(
            f'{e["display"]} ({_fmt_delta_pp(e["delta_pp"])})'
            for e in entries
        )
        if type_label == 'Other':
            paras.append(f'{opp_strs}.')
        else:
            paras.append(f'vs {type_label}-type: {opp_strs}.')
    return '\n\n'.join(paras)


def render_bad_at(
    species: str,
    dive: dict,
    *,
    cd_move_fast: str,
    baseline_move_fast: str,
    gm: Optional[dict] = None,
) -> str:
    """Render ``meta_role.bad_at`` as the symmetric flip-out list.

    Opponents where baseline was a win and CD is a loss. Same grouping
    and format as :func:`render_good_at`. Empty string when no
    opponent meets the flip-out criterion.
    """
    cd_ms = _pick_moveset(dive, cd_move_fast)
    base_ms = _pick_moveset(dive, baseline_move_fast)
    if cd_ms is None or base_ms is None:
        return ''
    deltas = _per_opp_deltas(dive, cd_ms, base_ms)
    flipped = sorted(
        [d for d in deltas if d['flipped_out']],
        key=lambda d: d['delta_pp'],  # most negative first
    )
    if not flipped:
        return ''
    cd_display = _gm_move_display(gm, cd_move_fast)

    paras = [f'Wins {species} gives up by switching to {cd_display}:']
    for type_label, entries in _group_by_primary_type(flipped, gm):
        opp_strs = ', '.join(
            f'{e["display"]} ({_fmt_delta_pp(e["delta_pp"])})'
            for e in entries
        )
        if type_label == 'Other':
            paras.append(f'{opp_strs}.')
        else:
            paras.append(f'vs {type_label}-type: {opp_strs}.')
    return '\n\n'.join(paras)


# --------------------------------------------------------------------
# Narrative-dict convenience: fill empty A-fields
# --------------------------------------------------------------------

def fill_narrative_a_fields(
    narrative: dict,
    dive: dict,
    *,
    species: str,
    cd_move_fast: str,
    baseline_move_fast: str,
    league: Optional[str] = None,
    cd_date: Optional[str] = None,
    form_comparison: bool = False,
    gm: Optional[dict] = None,
) -> dict:
    """Fill empty intro.body / meta_role.good_at / meta_role.bad_at in place.

    Leaves non-empty TOML prose alone (a human override always wins).
    Strips the ``author`` / ``authored_by`` metadata from any block
    that gets auto-filled so the rendered output doesn't display a
    stale "Drafted by Claude..." attribution. Caller is expected to
    have already cleared the Claude-drafted content per
    ``docs/auto_gen_narrative_plan.md`` step 3; this helper is
    robust to either state.

    Returns the same narrative dict for caller chaining.
    """
    if not cd_move_fast or not baseline_move_fast:
        return narrative

    def _auto_fill(block: dict, field: str, value: str) -> None:
        existing = (block.get(field) or '').strip()
        if existing:
            return
        if not value:
            return
        block[field] = value
        # Drop any prior free-form `author = "..."` attribution, since the
        # content is now deterministically data-derived; tag provenance via
        # `authored_by = "auto"` so the renderer picks the neutral
        # auto-gen sidebar colour instead of the gold "authored-human"
        # default.
        block.pop('author', None)
        block['authored_by'] = 'auto'

    intro = narrative.setdefault('intro', {})
    _auto_fill(intro, 'body', render_intro(
        species, dive,
        cd_move_fast=cd_move_fast,
        baseline_move_fast=baseline_move_fast,
        league=league,
        cd_date=cd_date,
        form_comparison=form_comparison,
        gm=gm,
    ))

    meta_role = narrative.setdefault('meta_role', {})
    _auto_fill(meta_role, 'good_at', render_good_at(
        species, dive,
        cd_move_fast=cd_move_fast,
        baseline_move_fast=baseline_move_fast,
        gm=gm,
    ))
    _auto_fill(meta_role, 'bad_at', render_bad_at(
        species, dive,
        cd_move_fast=cd_move_fast,
        baseline_move_fast=baseline_move_fast,
        gm=gm,
    ))

    return narrative


# --------------------------------------------------------------------
# Atk-weight classifier for Notable IVs
# --------------------------------------------------------------------

ATK_WEIGHT_TIPS = {
    'rank-1': 'Stat-product-max IV for this league',
    'no atk weight': 'Same Atk as rank-1; bulk within 2 points',
    'slight atk weight': 'Atk up to +3 over rank-1; bulk -3 to -8',
    'heavy atk weight': 'Atk >+3 over rank-1; bulk more than -8',
    'bulk-max': 'Atk ≤ rank-1 with higher bulk',
    'atk tilt': 'Above rank-1 Atk; other shapes the buckets do not catch',
}


def atk_weight_tip(label: str) -> str:
    """Short one-line explanation of an atk-weight label, for hover tooltips."""
    return ATK_WEIGHT_TIPS.get(label, '')


def classify_atk_weight(iv: dict, rank1: dict) -> str:
    """Label an IV spread by its attack/bulk tilt relative to rank-1.

    Buckets (matches RyanSwag's T2 vocabulary, see the 2026-04-16
    methodology gap analysis):

    * ``rank-1`` -- same atk, def, sta as the stat-product-max spread.
    * ``no atk weight`` -- same atk, bulk within 2 points.
    * ``slight atk weight`` -- atk up to 3 above, bulk down by 3-8.
    * ``heavy atk weight`` -- atk more than 3 above, bulk down >8.
    * ``bulk-max`` -- atk below or equal, bulk higher than rank-1.
    * ``atk tilt`` -- fallthrough for shapes the buckets above don't catch.

    ``iv`` and ``rank1`` accept either the battle-stat dict keys
    (``atk``, ``def_``, ``hp``) or the alternate spellings (``def``,
    ``sta``) used in other modules. Heuristic thresholds are the
    first-cut values from ``docs/auto_gen_narrative_plan.md``; revisit
    once we see the distribution of labels across real dives.
    """
    def _g(d: dict, *keys: str) -> float:
        for k in keys:
            if k in d:
                return float(d[k])
        return 0.0

    iv_atk = _g(iv, 'atk')
    iv_def = _g(iv, 'def_', 'def')
    iv_sta = _g(iv, 'sta', 'hp')
    r1_atk = _g(rank1, 'atk')
    r1_def = _g(rank1, 'def_', 'def')
    r1_sta = _g(rank1, 'sta', 'hp')

    atk_delta = iv_atk - r1_atk
    bulk_delta = (iv_def + iv_sta) - (r1_def + r1_sta)

    if abs(atk_delta) < 0.01 and abs(bulk_delta) < 0.01:
        return 'rank-1'
    if abs(atk_delta) < 0.01 and bulk_delta >= -2:
        return 'no atk weight'
    if atk_delta <= 0 and bulk_delta > 0:
        return 'bulk-max'
    if 0 < atk_delta <= 3 and bulk_delta >= -8:
        return 'slight atk weight'
    if atk_delta > 3 and bulk_delta < -8:
        return 'heavy atk weight'
    return 'atk tilt'
