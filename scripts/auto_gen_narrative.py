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
                # Legacy shape - list-of-strings fallback.
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
# JRE-shape BLUF verdict (role classifier + meta-coverage tier)
# --------------------------------------------------------------------

def _meta_coverage_tier(wins_of_9: int) -> str:
    """Bucket scenario-win count into a meta-coverage tier label.

    Thresholds: >=6 "strong", 3-5 "situational", <=2 "niche". Buckets
    deliberately shallow -- BLUF is a header, the follow-up "Meta
    coverage" paragraph carries the precise count and best/worst
    scenario.
    """
    if wins_of_9 >= 6:
        return 'strong'
    if wins_of_9 >= 3:
        return 'situational'
    return 'niche'


def _role_from_even_scenarios(rates, scenarios) -> str:
    """Classify role by best-even-shield scenario: closer / switch / lead / flex.

    Restricts to the three even-shield scenarios (0v0, 1v1, 2v2) because
    asymmetric-shield best-cases ("I have 2 shields, opponent has 0") are
    usually a tautology, not a role signal. The even-shield scenario with
    the highest win rate is the one the reader should build around:

    * 0v0 best -> ``closer`` (shields-down cleanup / finishing)
    * 1v1 best -> ``switch`` (mid-shield trade engine)
    * 2v2 best -> ``lead`` (lead-slot pressure with shields up)
    * no even-shield data (or a tie no even scenario wins) -> ``flex``
    """
    best: Optional[tuple[int, int]] = None
    best_rate = -1.0
    for r, sc in zip(rates, scenarios):
        try:
            my_s, opp_s = sc[0], sc[1]
        except (TypeError, IndexError):
            continue
        if my_s != opp_s:
            continue
        if r > best_rate:
            best_rate = r
            best = (int(my_s), int(opp_s))
    if best == (0, 0):
        return 'closer'
    if best == (1, 1):
        return 'switch'
    if best == (2, 2):
        return 'lead'
    return 'flex'


def render_bluf_verdict(
    species: str,
    dive: dict,
    featured_ms: dict,
    *,
    cd_move_fast: Optional[str],
    baseline_move_fast: Optional[str],
    cd_ms: Optional[dict],
    base_ms: Optional[dict],
    league: Optional[str],
    gm: Optional[dict],
    include_stats: bool,
) -> str:
    """Render a one-sentence Bottom-Line-Up-Front verdict, or ''.

    Shape::

        {Species} [(A/D/H)] is a {role} {league} pick at {coverage}
        meta coverage[, shifting from {base_wr}% ({base_move}) to
        {cd_wr}% ({cd_move})].

    Role = closer/switch/lead/flex by best even-shield scenario (see
    ``_role_from_even_scenarios``). Coverage tier = strong/situational/
    niche by scenario-win count. Pure data-derived per the
    ``feedback_autogen_shape_not_voice`` register -- no editorial
    judgement on whether the species "should" be invested in; the reader
    gets the role + coverage + shift and decides.

    Standalone mode (no CD swap, or same fast move both sides) drops the
    ``shifting from ... to ...`` tail but keeps the role + coverage
    classifier. ``include_stats=False`` suppresses the ``(A/D/H)`` tuple
    (used when a form-change paragraph has already named the stats).
    Returns '' when ``per_scenario_win_rate`` is missing or empty.
    """
    rates = featured_ms.get('per_scenario_win_rate') or []
    scenarios = dive.get('scenarios') or []
    if not rates or not scenarios or len(rates) != len(scenarios):
        return ''
    wins = sum(1 for r in rates if r >= 0.5)
    coverage = _meta_coverage_tier(wins)
    role = _role_from_even_scenarios(rates, scenarios)
    lg_short = _league_label(league).replace(' aggregate', '')

    stats_prefix = species
    base_stats = _gm_species_base_stats(gm, species)
    if include_stats and base_stats is not None:
        a, d, h = base_stats
        stats_prefix = f'{species} ({a}/{d}/{h})'

    is_cd_mode = (cd_ms is not None and base_ms is not None
                  and cd_move_fast and baseline_move_fast
                  and cd_move_fast != baseline_move_fast)
    tail = ''
    if is_cd_mode:
        cd_wr = cd_ms.get('win_rate', 0.0) * 100.0
        base_wr = base_ms.get('win_rate', 0.0) * 100.0
        cd_disp = _gm_move_display(gm, cd_move_fast)
        base_disp = _gm_move_display(gm, baseline_move_fast)
        tail = (f', shifting from {base_wr:.1f}% ({base_disp}) to '
                f'{cd_wr:.1f}% ({cd_disp})')
    return (f'{stats_prefix} is a {role} {lg_short} pick at {coverage} '
            f'meta coverage{tail}.')


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
    generation), appends a sentence describing that mechanic - it's
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
    # Trigger phrase - map the gamemaster's terse trigger id to reader prose.
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
                f'Default fast move {fname} has power 0 - 1 damage per '
                f'hit via PvP\'s minimum-damage floor, primarily energy '
                f'generation at {ept:.1f} EPT.'
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

def _fast_role_phrase(power: int, ept: float) -> str:
    """One-phrase fast-move role label derived from power + EPT.

    Four buckets (matches JRE-style move-pool prose where each move gets
    a one-phrase role rather than a raw stat dump):

    * ``the defining energy-only fast move`` -- power 0 (Psycho Cut on
      Aegislash Shield et al.; the mechanic IS the move).
    * ``a high-EPT pressure fast move`` -- EPT >= 4.0 (spam-bait feeders
      like Counter, Mud-Slap-isn't-here).
    * ``a balanced fast move`` -- EPT 3.0-3.9 (damage and energy both
      fine; Mud Slap et al.).
    * ``a damage-focused fast move`` -- EPT < 3.0 (Razor Leaf, Charm --
      the fast move itself is the win condition).
    """
    if power == 0:
        return 'the defining energy-only fast move'
    if ept >= 4.0:
        return 'a high-EPT pressure fast move'
    if ept >= 3.0:
        return 'a balanced fast move'
    return 'a damage-focused fast move'


def _charge_energy_tier(energy: int) -> str:
    """One-word energy-tier label: low-energy / mid-energy / high-energy / nuke-cost.

    PvP bait/closer taxonomy: <=35 cheap spammable bait, 40-50 mid,
    55-65 high-energy commit, >=70 nuke-cost (often capped by a 1-bar).
    """
    if energy <= 35:
        return 'low-energy'
    if energy <= 50:
        return 'mid-energy'
    if energy <= 65:
        return 'high-energy'
    return 'nuke-cost'


def _charge_effect_phrase(cm: dict) -> str:
    """Short "with a {effect}" phrase for a charge move, or ''.

    Returns ``self-buff`` / ``self-debuff`` / ``opponent-debuff`` /
    ``opponent-buff`` (combined with ``/`` when a move has both signs).
    Reads ``buffs`` + ``buffTarget`` directly from the gamemaster dict;
    returns '' when no effect is present.
    """
    buffs = cm.get('buffs') or []
    if not buffs:
        return ''
    target = cm.get('buffTarget') or ''
    try:
        any_pos = any(float(b) > 0 for b in buffs)
        any_neg = any(float(b) < 0 for b in buffs)
    except (TypeError, ValueError):
        return ''
    bits: list[str] = []
    if target == 'self':
        if any_pos:
            bits.append('self-buff')
        if any_neg:
            bits.append('self-debuff')
    elif target == 'opponent':
        if any_neg:
            bits.append('opponent-debuff')
        if any_pos:
            bits.append('opponent-buff')
    if not bits:
        return ''
    return ' with a ' + '/'.join(bits)


def render_move_pool_line(
    species: str,
    moveset: dict,
    gm: Optional[dict],
) -> str:
    """Render a 2-3 sentence move-pool prose paragraph for the dive narrative.

    Reads fast + charge moves from the moveset's label and narrates role,
    STAB / coverage, energy tier, and buff effect per move. Shape (JRE
    move-pool-section register, auto-gen SHAPE not voice per
    ``feedback_autogen_shape_not_voice``)::

        **Move pool.** {Fast} is {fast-role} ({type/STAB}, {ept} EPT).
        {Charge1} is a {energy-tier} {STAB option/Type coverage} move
        ({power} damage, {energy} energy)[ with a {effect}]. {Charge2}
        ...

    Each charge move gets its own sentence so readers can scan role +
    cost + effect without parsing a comma-dense list. Returns '' when the
    moveset has no parseable label.
    """
    label = moveset.get('label') or ''
    if '/' not in label:
        return ''
    species_types = _gm_species_types(gm, species)
    fast_part, charged_part = label.split('/', 1)
    fast_id = fast_part.strip()
    charged_ids = [c.strip() for c in charged_part.split(',') if c.strip()]

    sentences: list[str] = []

    # ---- Fast move ----
    fm = _gm_fast_move(gm, fast_id)
    if fm:
        fname = fm.get('name') or fast_id
        ftype = (fm.get('type') or '').capitalize()
        fpow = fm.get('power') or 0
        eg = fm.get('energyGain') or 0
        cd_ms = fm.get('cooldown') or 0
        turns = max(1, int(cd_ms / 500)) if cd_ms else 1
        ept = eg / turns if turns else 0.0
        is_stab = (fm.get('type') or '').lower() in species_types
        role_phrase = _fast_role_phrase(fpow, ept)
        if fpow == 0:
            sentences.append(f'{fname} is {role_phrase} at {ept:.1f} EPT.')
        elif is_stab and ftype:
            sentences.append(
                f'{fname} is {role_phrase} ({ftype} STAB, {ept:.1f} EPT).')
        elif ftype:
            sentences.append(
                f'{fname} is {role_phrase} ({ftype} coverage, '
                f'{ept:.1f} EPT).')
        else:
            sentences.append(f'{fname} is {role_phrase} at {ept:.1f} EPT.')

    # ---- Charge moves (one sentence each) ----
    for cid in charged_ids:
        cm = _gm_fast_move(gm, cid)  # same lookup shape
        if not cm:
            continue
        cname = cm.get('name') or cid
        ctype = (cm.get('type') or '').capitalize()
        cpow = cm.get('power') or 0
        cenergy = cm.get('energy') or 0
        is_stab = (cm.get('type') or '').lower() in species_types
        etier = _charge_energy_tier(cenergy)
        if is_stab:
            role_txt = 'STAB option'
        elif ctype:
            role_txt = f'{ctype} coverage option'
        else:
            role_txt = 'charged move'
        effect_txt = _charge_effect_phrase(cm)
        sentences.append(
            f'{cname} is a {etier} {role_txt} '
            f'({cpow} damage, {cenergy} energy){effect_txt}.'
        )

    if not sentences:
        return ''
    return '**Move pool.** ' + ' '.join(sentences)


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

    # ---- Paragraph 1: BLUF verdict + CD-specific follow-up sentences. ----
    sentences: list[str] = []

    # BLUF verdict leads the paragraph: "{Species} is a {role} {league}
    # pick at {coverage} meta coverage[, shifting from X% to Y% with
    # ...]." Role + coverage tier come from per_scenario_win_rate; the
    # shift tail only fires in CD mode. When the form-change paragraph
    # already names the stats (fc_note non-empty), suppress the
    # ``(A/D/H)`` prefix so readers don't see the tuple twice.
    bluf = render_bluf_verdict(
        species, dive, featured_ms,
        cd_move_fast=cd_move_fast,
        baseline_move_fast=baseline_move_fast,
        cd_ms=cd_ms, base_ms=base_ms,
        league=league, gm=gm,
        include_stats=(not fc_note),
    )
    if bluf:
        sentences.append(bluf)

    if is_cd_mode:
        # Still useful after the BLUF: name the TYPE of coverage the new
        # fast move adds (BLUF names the move, not its type).
        cd_type = _gm_move_type(gm, cd_move_fast)
        cd_display = _gm_move_display(gm, cd_move_fast)
        if cd_type:
            sentences.append(
                f'**{cd_display}** adds {cd_type.capitalize()}-type coverage.'
            )

        # Biggest gains / drops (flip-filtered). BLUF carries the
        # aggregate shift; this sentence answers "where did it come from?"
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
                + ', '.join(_opp_str_flip_range(g) for g in gains)
                + '.'
            )
        if drops:
            sentences.append(
                'Biggest drops: '
                + ', '.join(_opp_str_flip_range(d) for d in drops)
                + '.'
            )

        if form_comparison:
            sentences.append(
                'Which form to prioritize on CD day is covered in the '
                'form-comparison section below.'
            )

        if cd_date:
            sentences.append(f'Community Day: {cd_date}.')
    elif not sentences and not fc_note:
        # Standalone mode with no BLUF (e.g. per_scenario_win_rate missing)
        # and no form-change paragraph: fall back to a bare stats opener so
        # the Overview block has something before Meta coverage kicks in.
        stats_txt = species
        base_stats = _gm_species_base_stats(gm, species)
        if base_stats is not None:
            a, d, h = base_stats
            stats_txt = f'{species} ({a}/{d}/{h})'
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

        # ---- Paragraph 4: envelope-shape text-gestalt (F8). ----
        # Only fires when the dive carries S4/P3 envelope-positions data
        # (older dives predating commit 2b15357 return ''). Substitutes
        # for a static scatter image on the article side per §11.4
        # path (e); see ``docs/jre_ryanswag_comparison.md``.
        #
        # Reader's-guide pointer is only emitted for the dive caller
        # (include_supplement=True); the article caller suppresses this
        # paragraph entirely via include_supplement=False, so the
        # dive-relative ../guides/... path is safe.
        featured_idx = _featured_moveset_index(dive, featured_ms)
        if featured_idx is not None:
            env_note = render_envelope_summary(dive, featured_idx)
            if env_note:
                env_note += (
                    ' See the [Envelope Position guide]'
                    '(../guides/envelope-position/) for what '
                    '"ride above the band" means.'
                )
                paragraphs.append(env_note)

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


def _opp_str_flip_range(e: dict) -> str:
    """Format a CD-mode opponent entry as ``Display base%→cd%``.

    Used by ``render_good_at`` / ``render_bad_at`` in CD mode to show the
    raw before/after win rates instead of just the signed delta. The
    range carries the delta implicitly and is more concrete -- a reader
    sees 17%→66% and knows the matchup was losing by a wide margin
    and now wins convincingly, information the ``+49pp`` delta hides.
    RyanSwag-register cause-and-effect prose (F8 per §11.3 of
    ``docs/jre_ryanswag_comparison.md``).
    """
    base_pct = int(round(e.get('base_wr', 0.0) * 100))
    cd_pct = int(round(e.get('cd_wr', 0.0) * 100))
    return f'{e["display"]} {base_pct}%→{cd_pct}%'


def _cause_effect_offense_lead(move_display: str, move_type: Optional[str],
                               attacker_types: list[str], bucket_type: str,
                               opp_strs: str) -> Optional[str]:
    """Cause-and-effect lead sentence for a super-effective bucket in CD mode.

    Returns e.g. ``"Mud Slap (Ground STAB) flips the Steel bucket ×1.6:
    {opp_strs}."`` when the move type hits the bucket super-effectively
    (multiplier > 1). Returns None for neutral or resisted buckets
    (callers fall back to the existing ``vs {Type}-type:`` frame with
    the optional suffix effectiveness note).
    """
    if not move_type or not bucket_type:
        return None
    mult = _type_effectiveness_mult(move_type, [bucket_type])
    if mult is None or mult <= 1.05:
        return None
    suffix = _fmt_eff_multiplier(mult)
    if suffix is None:
        return None
    stab_tag = ' STAB' if (move_type.lower() in
                           [t.lower() for t in attacker_types]) else ''
    return (f'{move_display} ({move_type.capitalize()}{stab_tag}) flips the '
            f'{bucket_type.capitalize()} bucket {suffix}: {opp_strs}.')


def _cause_effect_defense_lead(attacker_types: list[str], bucket_type: str,
                               opp_strs: str) -> Optional[str]:
    """Cause-and-effect lead for a bucket that hits the attacker super-effectively.

    Used by ``render_bad_at`` in CD mode. Returns None when the bucket's
    type is neutral or resisted vs the attacker's defensive typing
    (callers fall back to the existing ``vs {Type}-type:`` frame).
    """
    if not attacker_types or not bucket_type:
        return None
    mult = _type_effectiveness_mult(bucket_type, attacker_types)
    if mult is None or mult <= 1.05:
        return None
    suffix = _fmt_eff_multiplier(mult)
    if suffix is None:
        return None
    type_disp = '/'.join(t.capitalize() for t in attacker_types)
    return (f'{bucket_type.capitalize()} damage hits {type_disp} {suffix}: '
            f'{opp_strs}.')


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

    * **CD mode** (both moves supplied and different): flip list - only
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
            opp_strs = ', '.join(_opp_str_flip_range(e) for e in bucket_entries)
        else:
            opp_strs = ', '.join(
                f'{e["display"]} ({_fmt_wr_pct(e["cd_wr"])})'
                for e in bucket_entries
            )
        # F8: in CD mode, if the featured move is super-effective vs this
        # bucket's type, lead with a cause-and-effect sentence naming the
        # move + typing + multiplier. Reader learns the *why* of the flip
        # bucket in the first phrase, not as a trailing ``- note``. For
        # neutral buckets and for standalone mode, keep the
        # ``vs {Type}-type:`` frame plus optional trailing effectiveness
        # note (covers the resisted case).
        ce_lead = None
        if use_delta and type_label != 'Other':
            ce_lead = _cause_effect_offense_lead(
                featured_fast_display, featured_fast_type,
                attacker_types, type_label.lower(), opp_strs)
        if ce_lead is not None:
            line = ce_lead
        else:
            line = (f'{opp_strs}.' if type_label == 'Other'
                    else f'vs {type_label}-type: {opp_strs}.')
            if type_label != 'Other':
                eff_note = _effectiveness_note_offense(
                    featured_fast_display, featured_fast_type,
                    attacker_types, type_label.lower())
                if eff_note:
                    line = line[:-1] + f' - {eff_note}'
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
            opp_strs = ', '.join(_opp_str_flip_range(e) for e in bucket_entries)
        else:
            opp_strs = ', '.join(
                f'{e["display"]} ({_fmt_wr_pct(e["cd_wr"])})'
                for e in bucket_entries
            )
        # F8: defensive cause-and-effect -- when the bucket's type hits
        # our attacker's defensive typing super-effectively, lead with the
        # damage-effectiveness sentence. Mirror of the offensive path in
        # ``render_good_at``. Neutral/resisted buckets fall back to the
        # ``vs {Type}-type:`` frame with the existing trailing suffix.
        ce_lead = None
        if use_delta and type_label != 'Other':
            ce_lead = _cause_effect_defense_lead(
                attacker_types, type_label.lower(), opp_strs)
        if ce_lead is not None:
            line = ce_lead
        else:
            line = (f'{opp_strs}.' if type_label == 'Other'
                    else f'vs {type_label}-type: {opp_strs}.')
            if type_label != 'Other':
                eff_note = _effectiveness_note_defense(
                    attacker_types, type_label.lower())
                if eff_note:
                    line = line[:-1] + f' - {eff_note}'
        paras.append(line)
    return '\n\n'.join(paras)


# --------------------------------------------------------------------
# F8: Meta Role wrap paragraph (STYLE_CONFORMANCE C11)
# --------------------------------------------------------------------

def render_wrap(
    species: str,
    dive: dict,
    *,
    cd_move_fast: Optional[str] = None,
    baseline_move_fast: Optional[str] = None,
    league: Optional[str] = None,
    gm: Optional[dict] = None,
) -> str:
    """Render a 1-2 sentence Meta Role closing paragraph, or ''.

    CD mode only: synthesises the headline aggregate-score shift plus the
    gain/drop counts and top-named opponents as a pure-data summary. Used
    to end the Meta Role block with a "landing" sentence in RyanSwag's
    mature format (STYLE_CONFORMANCE C11 wrap-up).

    Shape::

        **{Move}** shifts {species} from {base}% baseline to {cd}%
        {League} aggregate. Gains {N_in} matchups (top: {top_3_in});
        drops {N_out} (top: {top_3_out}).

    No editorial judgment ('you should', 'the meta will', etc.) per the
    ship-mode narrative policy in CLAUDE.md. Standalone mode returns ''
    because there is no baseline to shift from.
    """
    if not (cd_move_fast and baseline_move_fast
            and cd_move_fast != baseline_move_fast):
        return ''
    cd_ms = _pick_moveset(dive, cd_move_fast)
    base_ms = _pick_moveset(dive, baseline_move_fast)
    if cd_ms is None or base_ms is None:
        return ''

    cd_pct = cd_ms.get('win_rate', 0.0) * 100.0
    base_pct = base_ms.get('win_rate', 0.0) * 100.0
    cd_disp = _gm_move_display(gm, cd_move_fast)
    lg_short = _league_label(league).replace(' aggregate', '')

    deltas = _per_opp_deltas(dive, cd_ms, base_ms)
    gains = sorted([d for d in deltas if d['flipped_in']],
                   key=lambda d: d['delta_pp'], reverse=True)
    drops = sorted([d for d in deltas if d['flipped_out']],
                   key=lambda d: d['delta_pp'])

    sentences = [
        f'**{cd_disp}** shifts {species} from {base_pct:.1f}% baseline '
        f'to {cd_pct:.1f}% {lg_short} aggregate.'
    ]
    tail_bits: list[str] = []
    if gains:
        top_g = ', '.join(g['display'] for g in gains[:3])
        tail_bits.append(
            f'Gains {len(gains)} matchup{"s" if len(gains) != 1 else ""} '
            f'(top: {top_g})'
        )
    if drops:
        top_d = ', '.join(d['display'] for d in drops[:3])
        tail_bits.append(
            f'drops {len(drops)} (top: {top_d})'
        )
    if tail_bits:
        sentences.append('; '.join(tail_bits) + '.')
    return ' '.join(sentences)


# --------------------------------------------------------------------
# F8: Envelope-shape prose (text-gestalt substitute for static scatter)
# --------------------------------------------------------------------

def render_envelope_summary(
    dive: dict,
    moveset_idx: int,
) -> str:
    """Render a 1-2 sentence IV envelope-shape summary, or ''.

    Consumes ``dive['envelopePositions'][str(moveset_idx)]`` (produced by
    ``deep_dive_analysis.compute_envelope_positions`` -- see S4/P3 in
    ``scripts/deep_dive_rendering.py`` commit 2b15357). Each entry carries
    a ``shape`` classifier ('envelope-rider-top', 'envelope-rider-bottom',
    'elevated-band-crosser', 'depressed-band-crosser', 'sparse') and a
    ``mean_delta`` signed distance from the Anchor IVs band.

    Output describes how many named categories ride above the band vs
    below, with the standout in each direction named. This is the
    text-gestalt substitute for the static scatter we declined in
    §11.4 path (e) -- it lands the envelope shape through words for
    readers who don't click through to the interactive plot.

    Returns '' when envelope data is absent (older dives predating P3),
    when every category is sparse, or when moveset_idx isn't keyed.
    """
    env_map = (dive.get('envelopePositions') or {}).get(str(moveset_idx))
    if not env_map or not isinstance(env_map, dict):
        return ''
    riders_top: list[tuple[str, float]] = []
    riders_bottom: list[tuple[str, float]] = []
    n_cross = 0
    for name, entry in env_map.items():
        if not isinstance(entry, dict):
            continue
        shape = entry.get('shape')
        if shape == 'envelope-rider-top':
            riders_top.append((name, float(entry.get('mean_delta', 0.0))))
        elif shape == 'envelope-rider-bottom':
            riders_bottom.append((name, float(entry.get('mean_delta', 0.0))))
        elif shape in ('elevated-band-crosser', 'depressed-band-crosser'):
            n_cross += 1
        # 'sparse' and unknown shapes are skipped: the tag renderer
        # skips them too, and their delta isn't diagnostic.

    total_classified = len(riders_top) + len(riders_bottom) + n_cross
    if total_classified == 0:
        return ''

    riders_top.sort(key=lambda x: -x[1])
    riders_bottom.sort(key=lambda x: x[1])

    bits: list[str] = []
    if riders_top:
        top_name, top_d = riders_top[0]
        bits.append(
            f'{len(riders_top)} of {total_classified} named categor'
            f'{"ies" if total_classified != 1 else "y"} ride above the '
            f'anchor band (led by **{top_name}** at +{top_d:.1f} avg)'
        )
    if riders_bottom:
        bot_name, bot_d = riders_bottom[0]
        bits.append(
            f'{len(riders_bottom)} ride below (led by **{bot_name}** at '
            f'{bot_d:.1f} avg)'
        )
    if n_cross:
        bits.append(
            f'{n_cross} straddle'
        )
    if not bits:
        return ''
    return f'**Envelope shape.** {"; ".join(bits)}.'


def _featured_moveset_index(dive: dict, featured_ms: Optional[dict]) -> Optional[int]:
    """Return the canonical index of ``featured_ms`` in ``dive.movesets``.

    ``envelopePositions`` is keyed by stringified moveset index; the
    caller needs it to look up the envelope map for the featured
    moveset. Returns None when the moveset isn't in the list.
    """
    if featured_ms is None:
        return None
    movesets = dive.get('movesets') or []
    for i, m in enumerate(movesets):
        if m is featured_ms:
            return i
    return None


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
    # F8 wrap paragraph (STYLE_CONFORMANCE C11): ends the Meta Role block
    # with a 1-2 sentence synthesis of the aggregate shift + gain/drop
    # counts. Standalone mode (no CD swap) returns '' so the field stays
    # empty and the renderer skips the extra paragraph.
    _auto_fill(meta_role, 'wrap', render_wrap(
        species, dive,
        cd_move_fast=cd_move_fast,
        baseline_move_fast=baseline_move_fast,
        league=league,
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
