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


def _gm_species_types(gm: Optional[dict], species_name: str) -> list[str]:
    """Return the species' type list (all non-'none' types), lowercased.

    Falls back to empty list when species is missing or gm is None. Matches
    on speciesName exactly (caller passes display-form name).
    """
    if not gm or not species_name:
        return []
    for p in gm.get('pokemon') or []:
        if (p.get('speciesName') or '') == species_name:
            types = p.get('types') or []
            if isinstance(types, str):
                types = [types]
            return [t.lower() for t in types if t and t != 'none']
    return []


def _gm_species_form_change_target(gm: Optional[dict], species_name: str) -> Optional[dict]:
    """If the species has a ``formChange`` field, return ``(target_id, trigger)``.

    Returns a 2-tuple ``(alternativeFormId, trigger_label)`` or None when
    no formChange. The gamemaster stores formChange as a dict with keys
    ``alternativeFormId`` (e.g. ``"aegislash_blade"``) and ``trigger``
    (e.g. ``"activate_charged"``, ``"activate_shield"``).
    """
    if not gm or not species_name:
        return None
    for p in gm.get('pokemon') or []:
        if (p.get('speciesName') or '') == species_name:
            fc = p.get('formChange')
            if isinstance(fc, dict):
                target = fc.get('alternativeFormId')
                trigger = fc.get('trigger') or ''
                if target:
                    return (target, trigger)
            elif isinstance(fc, list) and fc and isinstance(fc[0], str):
                # Legacy shape — list-of-strings fallback.
                return (fc[0], '')
            elif isinstance(fc, str) and fc:
                return (fc, '')
            return None
    return None


def _gm_species_by_id(gm: Optional[dict], species_id: str) -> Optional[dict]:
    """Fetch a species dict by speciesId, or None."""
    if not gm or not species_id:
        return None
    for p in gm.get('pokemon') or []:
        if (p.get('speciesId') or '') == species_id:
            return p
    return None


def _gm_fast_move(gm: Optional[dict], move_id: str) -> Optional[dict]:
    """Fetch a fast move dict by moveId or name (lowercase match), or None."""
    if not gm or not move_id:
        return None
    target = move_id.strip().lower()
    for m in gm.get('moves') or []:
        if (m.get('moveId') or '').lower() == target:
            return m
        if (m.get('name') or '').lower() == target:
            return m
    return None


# --------------------------------------------------------------------
# Type effectiveness (B3a cause-and-effect layer)
# --------------------------------------------------------------------

def _type_effectiveness_mult(move_type: Optional[str],
                             defender_types: list[str]) -> Optional[float]:
    """Wrap ``gopvpsim.moves.type_effectiveness`` with graceful failure.

    Returns None when the move type is missing, defender_types is empty,
    or the type lookup fails. Import is lazy so this module stays
    importable without the sim package present (unit-test friendliness).
    """
    if not move_type or not defender_types:
        return None
    try:
        from gopvpsim.moves import type_effectiveness as _te
        return _te(move_type.lower(),
                   [t.lower() for t in defender_types if t])
    except (KeyError, ImportError, Exception):
        return None


def _fmt_eff_multiplier(mult: Optional[float]) -> Optional[str]:
    """Format a type-effectiveness multiplier as a ``×1.6`` style string.

    Returns None for near-neutral values (between 0.95 and 1.05). Uses
    PvP's base multipliers (1.6 / 0.625 / 2.56 / 0.39) rounded to one
    decimal place where practical.
    """
    if mult is None:
        return None
    if 0.95 <= mult <= 1.05:
        return None
    # Common PvP multipliers render cleanly at one decimal place.
    rounded_1 = round(mult, 1)
    if abs(mult - rounded_1) < 0.005:
        return f'×{rounded_1}'
    return f'×{mult:.2f}'.rstrip('0').rstrip('.')


def _effectiveness_note_offense(move_display: str, move_type: Optional[str],
                                attacker_types: list[str],
                                bucket_type: str) -> Optional[str]:
    """Offensive-effectiveness note for a type bucket.

    "Mud Slap (Ground) hits Steel ×1.6" when the move type is super-
    effective (or resisted) against the bucket type. Adds "STAB" when
    the move shares a type with the attacker. Returns None for neutral
    matchups (no information to add).
    """
    if not move_type or not bucket_type:
        return None
    mult = _type_effectiveness_mult(move_type, [bucket_type])
    suffix = _fmt_eff_multiplier(mult)
    if suffix is None:
        return None
    stab_tag = ' STAB' if (move_type.lower() in [t.lower() for t in attacker_types]) else ''
    return f'{move_display} ({move_type.capitalize()}{stab_tag}) hits {bucket_type.capitalize()} {suffix}.'


def _effectiveness_note_defense(attacker_types: list[str],
                                bucket_type: str) -> Optional[str]:
    """Defensive-effectiveness note for a type bucket.

    "{bucket_type} damage hits Steel ×1.6" when the bucket's type is super-
    effective against the attacker's defensive typing. Returns None for
    neutral matchups.
    """
    if not attacker_types or not bucket_type:
        return None
    mult = _type_effectiveness_mult(bucket_type, attacker_types)
    suffix = _fmt_eff_multiplier(mult)
    if suffix is None:
        return None
    type_disp = '/'.join(t.capitalize() for t in attacker_types)
    return f'{bucket_type.capitalize()} damage hits {type_disp} {suffix}.'


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


# --------------------------------------------------------------------
# B3b: form-change mechanical description
# --------------------------------------------------------------------

def render_form_change(species: str, gm: Optional[dict]) -> str:
    """Render a one-sentence form-change mechanical note, or ''.

    Detects the gamemaster's ``formChange`` field on the species. When
    present, looks up the post-transform species' base stats and emits:

        "{Species} is a form-change Pokemon. Starting stats A/D/HP;
         transforms to A'/D'/HP' on the first charged move."

    When the attacker's default fast move has power 0 (pure energy
    generation), appends a sentence describing that mechanic — it's
    the most reader-facing aspect of form-change species like
    Aegislash Shield.
    """
    fc_info = _gm_species_form_change_target(gm, species)
    if fc_info is None:
        return ''
    target_id, trigger = fc_info
    start_stats = _gm_species_base_stats(gm, species)
    if start_stats is None:
        return ''
    target_species = _gm_species_by_id(gm, target_id)
    if target_species is None:
        return ''
    tbs = target_species.get('baseStats') or {}
    ta, td, th = tbs.get('atk'), tbs.get('def'), tbs.get('hp')
    if ta is None or td is None or th is None:
        return ''
    # Trigger phrase — map the gamemaster's terse trigger id to reader prose.
    trigger_phrase = {
        'activate_charged': 'on the first charged move',
        'activate_shield': 'when the opponent shields a charged move',
    }.get(trigger, 'under its form-change trigger')
    sa, sd, sh = start_stats
    parts = [
        f'**{species}** is a form-change Pokemon. '
        f'Starting stats {sa}/{sd}/{sh}; transforms to '
        f'{int(ta)}/{int(td)}/{int(th)} {trigger_phrase}.'
    ]
    # Optional: zero-power fast move note (Aegislash Shield is the canonical case).
    fast_ids = (target_species.get('fastMoves') or [])  # post-transform fast moves often match pre
    # Prefer the starting form's fast moves when listed.
    start_species = None
    for p in (gm.get('pokemon') or []):
        if (p.get('speciesName') or '') == species:
            start_species = p
            break
    if start_species:
        fast_ids = start_species.get('fastMoves') or fast_ids
    for fid in fast_ids:
        fm = _gm_fast_move(gm, fid)
        if fm and (fm.get('power') or 0) == 0:
            ept = 0.0
            eg = fm.get('energyGain') or 0
            cd = fm.get('cooldown') or 0  # ms
            turns = max(1, int((cd or 0) / 500)) if cd else 1
            ept = eg / turns if turns else 0.0
            fname = fm.get('name') or fid
            parts.append(
                f'Default fast move {fname} has power 0 — pure energy '
                f'generation at {ept:.1f} EPT, no damage.'
            )
            break
    return ' '.join(parts)


# --------------------------------------------------------------------
# B3c: scenario-count shield analysis
# --------------------------------------------------------------------

def render_meta_coverage(
    species: str,
    dive: dict,
    moveset: dict,
    *,
    league: Optional[str] = None,
) -> str:
    """Render a one-sentence shield-scenario rollup, or ''.

    Given the moveset to read from (typically the CD moveset in CD
    mode, or the top-scoring moveset in standalone mode), count how
    many of the 9 scenarios win (>=50%), find the strongest and
    weakest, and emit a short Meta-coverage sentence:

        "Aggregate GL win rate X% across N opponents. Wins Y of 9
         shield scenarios; strongest at 2v0 (Z%), weakest at 0v2 (W%)."

    Returns '' when the moveset lacks per_scenario_win_rate or the
    dive lacks scenarios.
    """
    rates = moveset.get('per_scenario_win_rate') or []
    scenarios = dive.get('scenarios') or []
    if not rates or not scenarios or len(rates) != len(scenarios):
        return ''
    aggregate = moveset.get('win_rate', 0.0) * 100.0
    opponents = dive.get('opponents') or []
    wins = sum(1 for r in rates if r >= 0.5)
    best_i = max(range(len(rates)), key=lambda i: rates[i])
    worst_i = min(range(len(rates)), key=lambda i: rates[i])
    def _short(sc):
        try:
            return f'{sc[0]}v{sc[1]}'
        except Exception:
            return str(sc)
    best_sc = _short(scenarios[best_i])
    worst_sc = _short(scenarios[worst_i])
    league_txt = _league_label(league).replace(' aggregate', '')
    return (
        f'**Meta coverage.** Aggregate {league_txt} win rate '
        f'{aggregate:.1f}% across {len(opponents)} opponents. '
        f'Wins {wins} of 9 shield scenarios; strongest at '
        f'{best_sc} ({rates[best_i] * 100:.0f}%), weakest at '
        f'{worst_sc} ({rates[worst_i] * 100:.0f}%).'
    )


# --------------------------------------------------------------------
# B3d: move pool narrative
# --------------------------------------------------------------------

def render_move_pool_line(
    species: str,
    moveset: dict,
    gm: Optional[dict],
) -> str:
    """Render a one-line move-pool summary for the dive narrative.

    Reads the fast + charge moves from the moveset's label, tags each
    with its gamemaster type + STAB status + zero-power / self-debuff
    flags. Format:

        "**Move pool.** Fast: Psycho Cut (Psychic, 0 pwr, 4.0 EPT, the
         defining mechanic). Charged: Gyro Ball (Steel STAB, 80/50),
         Shadow Ball (Ghost STAB, 100/50)."

    Returns '' when the moveset has no parseable label.
    """
    label = moveset.get('label') or ''
    if '/' not in label:
        return ''
    species_types = _gm_species_types(gm, species)
    fast_part, charged_part = label.split('/', 1)
    fast_id = fast_part.strip()
    charged_ids = [c.strip() for c in charged_part.split(',') if c.strip()]

    fm = _gm_fast_move(gm, fast_id)
    fast_txt = ''
    if fm:
        fname = fm.get('name') or fast_id
        ftype = (fm.get('type') or '').capitalize()
        fpow = fm.get('power') or 0
        eg = fm.get('energyGain') or 0
        cd = fm.get('cooldown') or 0
        turns = max(1, int(cd / 500)) if cd else 1
        ept = eg / turns if turns else 0.0
        stab_tag = ' STAB' if fm.get('type', '').lower() in species_types else ''
        zero_note = (', the defining mechanic'
                     if fpow == 0 else '')
        fast_txt = f'{fname} ({ftype}{stab_tag}, {fpow} pwr, {ept:.1f} EPT{zero_note})'

    charged_descs: list[str] = []
    for cid in charged_ids:
        cm = _gm_fast_move(gm, cid)  # same lookup shape
        if not cm:
            continue
        cname = cm.get('name') or cid
        ctype = (cm.get('type') or '').capitalize()
        cpow = cm.get('power') or 0
        cenergy = cm.get('energy') or 0
        stab_tag = ' STAB' if cm.get('type', '').lower() in species_types else ''
        # buffs/debuffs flag from gamemaster (simple presence check).
        effect_bits: list[str] = []
        buffs = cm.get('buffs') or []
        if buffs:
            # Distinguish self-buff (positive, user target) vs self-debuff (negative, user)
            # vs opponent debuff. The gamemaster stores [atk_delta, def_delta]; combined
            # with buffTarget.
            target = cm.get('buffTarget') or ''
            try:
                any_pos = any(float(b) > 0 for b in buffs)
                any_neg = any(float(b) < 0 for b in buffs)
            except (TypeError, ValueError):
                any_pos = any_neg = False
            if target == 'self':
                if any_pos:
                    effect_bits.append('self-buff')
                if any_neg:
                    effect_bits.append('self-debuff')
            elif target == 'opponent':
                if any_neg:
                    effect_bits.append('opp-debuff')
                if any_pos:
                    effect_bits.append('opp-buff')
        eff_txt = f', {"/".join(effect_bits)}' if effect_bits else ''
        charged_descs.append(
            f'{cname} ({ctype}{stab_tag}, {cpow}/{cenergy}{eff_txt})')

    parts = ['**Move pool.**']
    if fast_txt:
        parts.append(f'Fast: {fast_txt}.')
    if charged_descs:
        parts.append('Charged: ' + ', '.join(charged_descs) + '.')
    return ' '.join(parts) if len(parts) > 1 else ''


def _top_scoring_moveset(dive: dict) -> Optional[dict]:
    """Return the moveset with the highest aggregate win_rate, or None.

    Standalone-mode analog of the CD moveset: when there's no CD move
    to compare against, the reader still wants the numbers for the
    "best" moveset the dive found. ``dive.movesets`` is not guaranteed
    to be sorted, so compare explicitly.
    """
    movesets = dive.get('movesets') or []
    if not movesets:
        return None
    return max(movesets, key=lambda m: m.get('win_rate', 0.0))


def render_intro(
    species: str,
    dive: dict,
    *,
    cd_move_fast: Optional[str] = None,
    baseline_move_fast: Optional[str] = None,
    league: Optional[str] = None,
    cd_date: Optional[str] = None,
    form_comparison: bool = False,
    include_supplement: bool = True,
    gm: Optional[dict] = None,
) -> str:
    """Render the ``[Species.intro]`` body as plain prose.

    Two modes selected by the presence of ``cd_move_fast`` /
    ``baseline_move_fast``:

    * **CD mode** (both supplied): stat frame + CD-move coverage +
      aggregate vs baseline delta + biggest gains/drops + optional
      form-comparison pointer + cd_date line.
    * **Standalone mode** (either missing, or the two are equal): stat
      frame + aggregate win rate of the top-scoring moveset, no baseline
      comparison. Used for non-CD species like Aegislash where there's
      no move swap to narrate.

    The caller can always pass neither; the renderer falls back to
    standalone mode using the highest-win-rate moveset in the dive.

    Additionally (B3 paragraph stack), when gamemaster data is
    supplied the returned string may contain multi-paragraph content
    separated by ``\\n\\n``:

    * Form-change mechanical note (when species has ``formChange``).
    * The main intro sentences (above).
    * Meta-coverage scenario analysis (suppressed when
      ``include_supplement=False``).
    * Move-pool one-liner (suppressed when
      ``include_supplement=False``).

    ``include_supplement=False`` is the article caller's setting --
    the article already has dedicated ``§meta-coverage``,
    ``§fast-moves``, and ``§charged-moves`` sections, so adding the
    compact paragraphs to the intro would duplicate them. The dive has
    no such siblings; it keeps the default ``True`` to supplement the
    intro.

    Callers render the whole block via ``format_body()``; paragraphs
    stay separate in the rendered HTML.

    Returns empty string only when no moveset can be identified at
    all (dive has zero movesets).
    """
    # Pick the "featured" moveset. CD mode: the one carrying cd_move_fast.
    # Standalone: top-scoring. Baseline, when present, drives delta prose.
    cd_ms: Optional[dict] = None
    base_ms: Optional[dict] = None
    if cd_move_fast:
        cd_ms = _pick_moveset(dive, cd_move_fast)
    if baseline_move_fast and baseline_move_fast != cd_move_fast:
        base_ms = _pick_moveset(dive, baseline_move_fast)

    # Fall back to top-scoring moveset if CD not found or not provided.
    is_cd_mode = (cd_ms is not None and base_ms is not None
                  and cd_move_fast != baseline_move_fast)
    featured_ms = cd_ms or _top_scoring_moveset(dive)
    if featured_ms is None:
        return ''

    paragraphs: list[str] = []

    # ---- Paragraph 0: form-change mechanical note (if applicable). ----
    fc_note = render_form_change(species, gm)
    if fc_note:
        paragraphs.append(fc_note)

    # ---- Paragraph 1: the main intro sentence(s). ----
    sentences: list[str] = []

    # Stat line.
    stats_txt = species
    base_stats = _gm_species_base_stats(gm, species)
    if base_stats is not None:
        a, d, h = base_stats
        stats_txt = f'{species} ({a}/{d}/{h})'

    if is_cd_mode:
        cd_type = _gm_move_type(gm, cd_move_fast)
        cd_display = _gm_move_display(gm, cd_move_fast)
        if cd_type:
            sentences.append(
                f'{stats_txt}. **{cd_display}** adds '
                f'{cd_type.capitalize()}-type coverage.'
            )
        else:
            sentences.append(
                f'{stats_txt}. **{cd_display}** is the new fast-move option.')

        # Aggregate w/ baseline delta.
        cd_wr_pct = cd_ms.get('win_rate', 0.0) * 100.0
        base_wr_pct = base_ms.get('win_rate', 0.0) * 100.0
        delta_pp = cd_wr_pct - base_wr_pct
        base_display = _gm_move_display(gm, baseline_move_fast)
        sentences.append(
            f'{_league_label(league)} win rate: {cd_wr_pct:.1f}% '
            f'({base_display} baseline: {base_wr_pct:.1f}%, '
            f'{_fmt_delta_pp(delta_pp)}).'
        )

        # Biggest gains / drops (flip-filtered).
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
                + ', '.join(f'{g["display"]} {_fmt_delta_pp(g["delta_pp"])}'
                            for g in gains)
                + '.'
            )
        if drops:
            sentences.append(
                'Biggest drops: '
                + ', '.join(f'{d["display"]} {_fmt_delta_pp(d["delta_pp"])}'
                            for d in drops)
                + '.'
            )

        if form_comparison:
            sentences.append(
                'Which form to prioritize on CD day is covered in the '
                'form-comparison section below.'
            )

        if cd_date:
            sentences.append(f'Community Day: {cd_date}.')
    elif not fc_note:
        # Standalone mode without a form-change paragraph. Emit a bare
        # stats line as the opener so the Overview block has something
        # before Meta coverage kicks in. When fc_note is present it
        # already carries the stats; no redundant opener needed.
        sentences.append(f'{stats_txt}.')

    if sentences:
        paragraphs.append(' '.join(sentences))

    if include_supplement:
        # ---- Paragraph 2: meta-coverage scenario rollup. ----
        mc_note = render_meta_coverage(
            species, dive, featured_ms, league=league)
        if mc_note:
            paragraphs.append(mc_note)

        # ---- Paragraph 3: move-pool one-liner. ----
        mp_note = render_move_pool_line(species, featured_ms, gm)
        if mp_note:
            paragraphs.append(mp_note)

    return '\n\n'.join(paragraphs)


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


def _standalone_entries(dive: dict, ms: dict,
                        *, wins: bool, top_n: int = 10) -> list[dict]:
    """Synthesize per-opp entries for standalone mode.

    Returns a list shaped like ``_per_opp_deltas`` output but without
    the delta (base_wr is treated as 0, delta_pp is win-rate in pp).
    ``wins=True`` returns opponents with ``cd_wr >= 0.5`` sorted desc;
    ``wins=False`` returns ``cd_wr < 0.5`` sorted asc. Caps at top_n.
    """
    opponents = dive.get('opponents') or []
    wrs = ms.get('per_opponent_win_rate') or []
    n = min(len(opponents), len(wrs))
    entries = []
    for i in range(n):
        wr = wrs[i]
        hit = (wins and wr >= 0.5) or (not wins and wr < 0.5)
        if not hit:
            continue
        entries.append({
            'opp': opponents[i],
            'display': _opp_display_name(opponents[i]),
            'cd_wr': wr,
            'base_wr': 0.0,
            'delta_pp': wr * 100.0,  # cosmetic: shows absolute % in standalone
            'flipped_in': wins,
            'flipped_out': not wins,
        })
    entries.sort(key=lambda e: e['cd_wr'], reverse=wins)
    return entries[:top_n]


def _fmt_wr_pct(wr: float) -> str:
    """Format an absolute win rate as '82%' for standalone-mode lists."""
    return f'{wr * 100.0:.0f}%'


def render_good_at(
    species: str,
    dive: dict,
    *,
    cd_move_fast: Optional[str] = None,
    baseline_move_fast: Optional[str] = None,
    gm: Optional[dict] = None,
) -> str:
    """Render ``meta_role.good_at`` as a type-bucketed matchup list.

    Two modes:

    * **CD mode** (both moves supplied and different): flip list — only
      opponents where ``cd_wr >= 0.5 AND base_wr < 0.5``, sorted by
      per-opp ppt delta desc.
    * **Standalone mode** (no CD swap): top ~10 matchups by absolute
      win rate (``cd_wr >= 0.5``), sorted desc.

    Groups by opponent primary type. Within each bucket, appends an
    offensive-effectiveness note (B3a cause-and-effect) when the
    featured move's type is super-effective (or resisted) against the
    bucket's primary type. Returns '' when no qualifying opponents.
    """
    featured_ms: Optional[dict]
    base_ms = None
    use_delta = False
    if cd_move_fast and baseline_move_fast and cd_move_fast != baseline_move_fast:
        featured_ms = _pick_moveset(dive, cd_move_fast)
        base_ms = _pick_moveset(dive, baseline_move_fast)
        use_delta = (featured_ms is not None and base_ms is not None)
    else:
        featured_ms = _pick_moveset(dive, cd_move_fast) if cd_move_fast else None
        if featured_ms is None:
            featured_ms = _top_scoring_moveset(dive)
    if featured_ms is None:
        return ''

    if use_delta:
        deltas = _per_opp_deltas(dive, featured_ms, base_ms)
        entries = sorted(
            [d for d in deltas if d['flipped_in']],
            key=lambda d: d['delta_pp'], reverse=True,
        )
        header = (f'Wins {species} picks up by adding '
                  f'{_gm_move_display(gm, cd_move_fast)}:')
    else:
        entries = _standalone_entries(dive, featured_ms, wins=True)
        header = f'Matchups {species} wins:'
    if not entries:
        return ''

    attacker_types = _gm_species_types(gm, species)
    # Infer the featured move used for the offensive-effectiveness note:
    # CD mode -> the CD fast move; standalone -> the featured moveset's fast.
    featured_fast_id = (cd_move_fast if cd_move_fast
                        else _fast_move_from_label(featured_ms.get('label') or ''))
    featured_fast_type = _gm_move_type(gm, featured_fast_id)
    featured_fast_display = _gm_move_display(gm, featured_fast_id)

    paras = [header]
    for type_label, bucket_entries in _group_by_primary_type(entries, gm):
        if use_delta:
            opp_strs = ', '.join(
                f'{e["display"]} ({_fmt_delta_pp(e["delta_pp"])})'
                for e in bucket_entries
            )
        else:
            opp_strs = ', '.join(
                f'{e["display"]} ({_fmt_wr_pct(e["cd_wr"])})'
                for e in bucket_entries
            )
        line = (f'{opp_strs}.' if type_label == 'Other'
                else f'vs {type_label}-type: {opp_strs}.')
        # B3a: append effectiveness suffix when the featured move is
        # super-effective (or resisted) against this bucket's type.
        if type_label != 'Other':
            eff_note = _effectiveness_note_offense(
                featured_fast_display, featured_fast_type,
                attacker_types, type_label.lower())
            if eff_note:
                line = line[:-1] + f' — {eff_note}'
        paras.append(line)
    return '\n\n'.join(paras)


def render_bad_at(
    species: str,
    dive: dict,
    *,
    cd_move_fast: Optional[str] = None,
    baseline_move_fast: Optional[str] = None,
    gm: Optional[dict] = None,
) -> str:
    """Render ``meta_role.bad_at`` as the symmetric bad-matchup list.

    CD mode: flip-out list (baseline was a win, CD is a loss).
    Standalone mode: bottom ~10 matchups by absolute win rate
    (``cd_wr < 0.5``).

    Appends a defensive-effectiveness note per type bucket (B3a): "X
    damage hits {attacker types} ×M" when the bucket's primary type
    is super-effective against the attacker's defensive typing.
    """
    featured_ms: Optional[dict]
    base_ms = None
    use_delta = False
    if cd_move_fast and baseline_move_fast and cd_move_fast != baseline_move_fast:
        featured_ms = _pick_moveset(dive, cd_move_fast)
        base_ms = _pick_moveset(dive, baseline_move_fast)
        use_delta = (featured_ms is not None and base_ms is not None)
    else:
        featured_ms = _pick_moveset(dive, cd_move_fast) if cd_move_fast else None
        if featured_ms is None:
            featured_ms = _top_scoring_moveset(dive)
    if featured_ms is None:
        return ''

    if use_delta:
        deltas = _per_opp_deltas(dive, featured_ms, base_ms)
        entries = sorted(
            [d for d in deltas if d['flipped_out']],
            key=lambda d: d['delta_pp'],
        )
        header = (f'Wins {species} gives up by switching to '
                  f'{_gm_move_display(gm, cd_move_fast)}:')
    else:
        entries = _standalone_entries(dive, featured_ms, wins=False)
        header = f'Matchups {species} loses:'
    if not entries:
        return ''

    attacker_types = _gm_species_types(gm, species)

    paras = [header]
    for type_label, bucket_entries in _group_by_primary_type(entries, gm):
        if use_delta:
            opp_strs = ', '.join(
                f'{e["display"]} ({_fmt_delta_pp(e["delta_pp"])})'
                for e in bucket_entries
            )
        else:
            opp_strs = ', '.join(
                f'{e["display"]} ({_fmt_wr_pct(e["cd_wr"])})'
                for e in bucket_entries
            )
        line = (f'{opp_strs}.' if type_label == 'Other'
                else f'vs {type_label}-type: {opp_strs}.')
        if type_label != 'Other':
            eff_note = _effectiveness_note_defense(
                attacker_types, type_label.lower())
            if eff_note:
                line = line[:-1] + f' — {eff_note}'
        paras.append(line)
    return '\n\n'.join(paras)


# --------------------------------------------------------------------
# Narrative-dict convenience: fill empty A-fields
# --------------------------------------------------------------------

def fill_narrative_a_fields(
    narrative: dict,
    dive: dict,
    *,
    species: str,
    cd_move_fast: Optional[str] = None,
    baseline_move_fast: Optional[str] = None,
    league: Optional[str] = None,
    cd_date: Optional[str] = None,
    form_comparison: bool = False,
    include_supplement: bool = True,
    gm: Optional[dict] = None,
) -> dict:
    """Fill empty intro.body / meta_role.good_at / meta_role.bad_at in place.

    Two operating modes selected by the moves supplied:

    * **CD mode** (both ``cd_move_fast`` and ``baseline_move_fast`` set,
      and different): templates narrate the CD-vs-baseline delta.
    * **Standalone mode** (either missing, or the two equal): templates
      narrate the species' top-scoring moveset by absolute win rate.
      Used for non-CD species like Aegislash where there's no move swap
      to compare.

    Leaves non-empty TOML prose alone (a human override always wins).
    Sets ``authored_by = 'auto'`` on any block that gets auto-filled
    so the renderer picks the neutral auto-gen sidebar colour. Drops
    any prior free-form ``author`` attribution since the content is
    now deterministically data-derived.

    Returns the same narrative dict for caller chaining.
    """
    # No early-return gate. Standalone mode fires when cd/baseline are
    # missing or equal; the renderers handle both modes internally.

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
        include_supplement=include_supplement,
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
