"""Opponent identity: variant registry, pool parsing, IV resolution.

Moved verbatim out of ``scripts/deep_dive.py`` by the DRY review 2026-08-05
entry 12 split (review section H, step 2: both ``sweep`` and ``render`` need
these, so they have to sit below both to avoid a circular import).
``deep_dive.py`` keeps a re-export shim for every name defined here, so
existing importers keep working unchanged.

``_OPPONENT_VARIANT_REGISTRY`` is process-local mutable state (review section
G, invariant 20). ``deep_dive.py``'s shim binds the SAME dict object, so
``.clear()`` / ``.update()`` through either name reach the one registry; a
rebinding monkeypatch does not, which is why the tests that need an empty
registry save/clear/restore instead.
"""
import os
import sys
import tomllib
from pathlib import Path

from gopvpsim.pokemon import iv_rank, pvpoke_default_ivs
from gopvpsim.data import (
    load_rankings, get_default_moveset, species_id,
    get_rankings_for, rankings_cache_path,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import deep_dive_analysis as analysis
import deep_dive_rendering as rendering
from deep_dive_logging import get_logger

logger = get_logger()

parse_mode = rendering.parse_mode


def get_top_opponents(league, n, exclude_species=None):
    """Return top N species from PvPoke rankings for the league."""
    rankings = load_rankings(league)
    opponents = []
    for r in rankings:
        name = r['speciesName']
        if exclude_species and name == exclude_species:
            continue
        opponents.append(name)
        if len(opponents) >= n:
            break
    return opponents


def resolve_opp_ivs(species_name, league, shadow, opp_iv_mode):
    """Return (atk_iv, def_iv, sta_iv) for an opponent based on the IV mode.

    opp_iv_mode:
      'pvpoke'  - PvPoke's default IVs from the gamemaster (what pvpoke.com uses)
      'rank1'   - stat-product rank 1 IVs

    Tolerates composite mode strings like ``'pvpoke:nobait'`` - the bait axis
    is focal-side and has no effect on opponent IV selection, so we strip it.
    """
    opp_iv_mode, _ = parse_mode(opp_iv_mode)
    if opp_iv_mode == 'rank1':
        ranked = iv_rank(species_name, league=league, shadow=shadow)
        r1 = ranked[0]
        return r1['atk_iv'], r1['def_iv'], r1['sta_iv']
    else:
        # pvpoke default -- pass shadow so a shadow opponent gets its OWN
        # PvPoke default IVs (they differ from the base for ~37 species),
        # matching the rank1 branch above. Was shadow-agnostic: shadow
        # opponents got base default IVs, then shadow mults on top (wrong
        # stats; flipped shipped UL winners, e.g. Shadow Raikou/Cresselia).
        _lv, a, d, s = pvpoke_default_ivs(species_name, league=league, shadow=shadow)
        return a, d, s


# Variant-suffix plumbing for attack-weighted opponent sweeps.
#
# Opponents are passed around as display strings. Shadow variants use the
# ' (Shadow)' suffix (handled inline at call sites); attack-weighted variants
# use the parallel suffix below. The parser pulls the base species back out so
# gamemaster lookups keep working; the variant tag signals to the opp_cache
# builder that the IVs should come from the shared spread registry rather than
# resolve_opp_ivs().
ATK_WEIGHTED_SUFFIX = ' (atk-weighted)'

# Moveset-variant opponents (e.g. 'Forretress (Bug Bite)' for a fast-move
# override) get a registry entry at pool-load time so parse_opponent_spec
# can recover the base species. Keyed by display name -> (base, is_shadow).
# Populated by _parse_opponent_pool_line / _apply_active_variants in the main
# process before workers spawn; workers consume opp_cache (pre-resolved) and
# never call parse_opponent_spec directly.
_OPPONENT_VARIANT_REGISTRY = {}


def register_opponent_variant(display_name, base_species, is_shadow):
    """Register a moveset-variant opponent so parse_opponent_spec resolves
    the display name back to its base species + shadow flag.

    Idempotent: re-registering with identical fields is a no-op; conflicts
    raise ValueError so a typo can't silently shadow an earlier entry.
    """
    existing = _OPPONENT_VARIANT_REGISTRY.get(display_name)
    payload = (base_species, is_shadow)
    if existing is not None and existing != payload:
        raise ValueError(
            f"opponent variant {display_name!r} already registered as "
            f"{existing}, cannot reregister as {payload}"
        )
    _OPPONENT_VARIANT_REGISTRY[display_name] = payload


def parse_opponent_spec(opp_name):
    """Split an opponents-list entry into (species, variant, is_shadow).

    Handles four forms:
      'Medicham'                       -> ('Medicham', None,             False)
      'Medicham (Shadow)'              -> ('Medicham', None,             True)
      'Medicham (atk-weighted)'        -> ('Medicham', 'atk_weighted',   False)
      'Forretress (Bug Bite)'          -> ('Forretress','moveset_variant',False)
        (only when registered via register_opponent_variant; otherwise the
        parenthetical falls through and the whole string is treated as a
        speciesName so genuine PvPoke forms like '(Galarian)' still work)

    Shadow + atk-weighted in the same entry is not supported (no meta-relevant
    opponent today is both).
    """
    if opp_name in _OPPONENT_VARIANT_REGISTRY:
        base, is_shadow = _OPPONENT_VARIANT_REGISTRY[opp_name]
        return base, 'moveset_variant', is_shadow
    variant = None
    name = opp_name
    if name.endswith(ATK_WEIGHTED_SUFFIX):
        name = name[:-len(ATK_WEIGHTED_SUFFIX)]
        variant = 'atk_weighted'
    is_shadow = name.endswith(' (Shadow)')
    if is_shadow:
        name = name[:-len(' (Shadow)')]
    return name, variant, is_shadow


def build_opp_meta_ranks(opponent_names, league, cup=None):
    """Per-opponent PvPoke meta rank (1 = best) parallel to opponent_names.

    Each entry is an int rank or None. Ranks come from the live
    ``load_rankings(league)`` list (already score-descending, so list
    position + 1 is the rank), matched by RESOLVED speciesId: a shadow
    opponent picks up its own '<id>_shadow' ranked position, and a
    moveset-variant (e.g. 'Forretress (Bug Bite)') inherits the base
    species' rank (both variants of one species share a rank, which is the
    intended behavior for the top-N buttons -- the panel lists both, and
    a top-N cut includes both). Unranked entries (championship-series
    extras PvPoke doesn't rank, hand-extended focals, anything absent from
    the rankings) are None; the client-side filter sorts them to the end
    and excludes them from the top-N convenience buttons.

    ``cup`` (e.g. 'equinox') sources ranks from that cup's rankings instead
    of the league's overall meta -- so a cup dive's top-N buttons mean "top
    N in the cup", the exact composition the plan intends.

    Returns [] on the (defensive) chance the league has no rankings; the
    caller then emits an all-None list of the right length.
    """
    try:
        rankings = get_rankings_for(league, cup=cup)
    except Exception:
        return [None] * len(opponent_names)
    rank_by_sid = {}
    for i, r in enumerate(rankings):
        sid = r.get('speciesId')
        if sid is not None and sid not in rank_by_sid:
            rank_by_sid[sid] = i + 1
    out = []
    for name in opponent_names:
        sp, _variant, is_shadow = parse_opponent_spec(name)
        try:
            sid = species_id(sp, shadow=is_shadow)
        except Exception:
            sid = None
        out.append(rank_by_sid.get(sid))
    return out


def rankings_snapshot_date(league, cup=None):
    """Vintage of the rankings the meta ranks were read from (YYYY-MM-DD).

    The honest 'as of' date for the top-N labels is when the rankings cache
    was last refreshed, NOT the render date -- overclaiming freshness is the
    exact never-ship-unflagged trap. Falls back to None (JS then omits the
    date) if the cache file can't be stat'd. For a cup dive, the vintage is
    the cup rankings cache file (``rankings_<cup>_<cp>.json``) -- this is the
    "snapshot as of DATE" the archive policy displays.
    """
    import datetime
    try:
        ts = rankings_cache_path(league, cup=cup).stat().st_mtime
    except OSError:
        # Narrow on purpose: a MISSING/unreadable cache file is the only
        # excusable miss here. A renamed cache key or an unknown league now
        # raises instead of silently blanking the archive-vintage banner.
        return None
    return datetime.date.fromtimestamp(ts).isoformat()


def _parse_opponent_pool_line(line):
    """Parse one non-comment, non-blank line from an opponents-file.

    Format:
        SPECIES                              # default moveset (PvPoke)
        SPECIES | fast=ID                    # fast-move override
        SPECIES | charged=A,B                # charged-only override
        SPECIES | fast=ID | charged=A,B      # full moveset override

    SPECIES is the PvPoke speciesName, optionally with a trailing ' (Shadow)'.
    Override keys are case-sensitive ('fast', 'charged'); unknown keys raise.
    Whitespace around the '|' separator and around 'key=value' is tolerated.

    Returns:
        (display_name, base_species, is_shadow, fast_override, charged_override)
        where fast_override / charged_override are None when not present.
        Display name auto-generated for entries with overrides:
            'Forretress | fast=BUG_BITE'           -> 'Forretress (Bug Bite)'
            'Forretress (Shadow) | fast=BUG_BITE'  -> 'Forretress (Shadow) (Bug Bite)'

    Raises ValueError on malformed input.
    """
    parts = [p.strip() for p in line.split('|')]
    species_with_form = parts[0]
    if not species_with_form:
        raise ValueError(f"empty species name in pool line: {line!r}")

    overrides = {}
    for kv in parts[1:]:
        if '=' not in kv:
            raise ValueError(f"override {kv!r} missing '=' (expected key=value)")
        k, v = kv.split('=', 1)
        k, v = k.strip(), v.strip()
        if not k or not v:
            raise ValueError(f"empty key or value in override {kv!r}")
        if k in overrides:
            raise ValueError(f"duplicate override key {k!r} in {line!r}")
        overrides[k] = v

    fast_override = overrides.pop('fast', None)
    charged_str = overrides.pop('charged', None)
    charged_override = (
        [c.strip() for c in charged_str.split(',') if c.strip()]
        if charged_str else None
    )
    if overrides:
        raise ValueError(f"unknown override key(s) {sorted(overrides)} in {line!r}")

    is_shadow = species_with_form.endswith(' (Shadow)')
    base_species = (species_with_form[:-len(' (Shadow)')]
                    if is_shadow else species_with_form)

    if fast_override is None and charged_override is None:
        return species_with_form, base_species, is_shadow, None, None

    suffix_parts = []
    if fast_override is not None:
        suffix_parts.append(analysis.pretty_name(fast_override))
    if charged_override is not None:
        suffix_parts.append('+'.join(
            analysis.pretty_name(c) for c in charged_override))
    display = f"{species_with_form} ({' / '.join(suffix_parts)})"
    return display, base_species, is_shadow, fast_override, charged_override


# ---- Active alt-moveset opponent variants (TOML, project-wide) ----

# parents[2] (not [1]) because this module sits one level deeper than
# deep_dive.py: scripts/deep_dive_lib/opponents.py -> repo root.
ACTIVE_VARIANTS_PATH = Path(__file__).resolve().parents[2] / (
    'opponent_pools/active_variants.toml')


def _apply_active_variants(opponents, opp_movesets_full, league, toml_path=None,
                           skip=False):
    """Append project-wide alt-moveset opponent variants from a TOML file.

    Skipping rules:
    - ``skip=True`` → no-op (returns []).
    - File missing → no-op (returns []).
    - Variant whose ``(base_species, is_shadow)`` doesn't match any opponent
      already in the pool → skipped silently. Lets a single TOML cover
      multiple leagues without manual scoping (a Forretress (BB) entry
      auto-skips on a UL pool that doesn't include Forretress).
    - Variant display name already in ``opponents`` (e.g. from inline
      pipe-syntax) → skipped.

    Mutates ``opponents`` and ``opp_movesets_full`` in place. Registers each
    appended variant via ``register_opponent_variant`` so
    ``parse_opponent_spec`` can recover the base species downstream.

    Returns: list of display names actually appended.
    """
    if skip:
        return []
    if toml_path is None:
        toml_path = ACTIVE_VARIANTS_PATH
    toml_path = Path(toml_path)
    if not toml_path.exists():
        return []

    with open(toml_path, 'rb') as f:
        data = tomllib.load(f)

    # Index existing pool by (base_species, is_shadow) so a variant only
    # appends when its base form is already a meta opponent.
    base_present = set()
    for opp_name in opponents:
        base, _, is_shadow = parse_opponent_spec(opp_name)
        base_present.add((base, is_shadow))

    applied = []
    for v in data.get('variants', []):
        species = v.get('species')
        if not species:
            logger.warning(f"active_variants.toml: skipping entry without 'species'")
            continue
        is_shadow = bool(v.get('shadow', False))
        fast_ov = v.get('fast')
        charged_ov = v.get('charged')
        if fast_ov is None and charged_ov is None:
            logger.warning(f"active_variants.toml: {species} entry has no "
                           f"'fast' or 'charged' override, skipping")
            continue
        if (species, is_shadow) not in base_present:
            continue  # base form not in this pool; quietly skip

        try:
            d_fast, d_charged = get_default_moveset(
                species, league=league, shadow=is_shadow)
        except (KeyError, ValueError) as _e:
            logger.warning(f"active_variants.toml: {species} not in "
                           f"{league} rankings, skipping ({_e})")
            continue
        fast_id = fast_ov if fast_ov is not None else d_fast
        charged_ids = (
            list(charged_ov) if charged_ov is not None else list(d_charged))

        species_with_form = f"{species} (Shadow)" if is_shadow else species
        suffix_parts = []
        if fast_ov is not None:
            suffix_parts.append(analysis.pretty_name(fast_ov))
        if charged_ov is not None:
            suffix_parts.append('+'.join(
                analysis.pretty_name(c) for c in charged_ov))
        display = f"{species_with_form} ({' / '.join(suffix_parts)})"

        if display in opponents:
            continue  # already there from inline pipe-syntax

        opponents.append(display)
        opp_movesets_full.append((fast_id, charged_ids))
        register_opponent_variant(display, species, is_shadow)
        applied.append(display)

    return applied


def _atk_weighted_spread_name(species):
    """Canonical shared-spread name for a species's atk-weighted variant."""
    return f"{species.lower().replace(' ', '_').replace('(', '').replace(')', '')}_atk_weighted"


def variant_ivs(species, variant, league, threshold_registry):
    """Return (atk_iv, def_iv, sta_iv) for a named variant, or None if absent.

    Today only 'atk_weighted' is defined; future variants can follow the same
    shared-spread naming convention.
    """
    if variant != 'atk_weighted' or threshold_registry is None:
        return None
    spread = threshold_registry.get_spread(
        species, league.capitalize(), _atk_weighted_spread_name(species),
    )
    if spread is None:
        return None
    ivs = getattr(spread, 'ivs', None)
    if not ivs:
        return None
    # IvListSpread.ivs is a tuple of (a,d,s) tuples; take the first entry.
    # Multi-IV spreads are an S4b concern; for S4a one spread = one variant.
    return ivs[0]


def expand_opponents_with_variants(opponents, opp_movesets, threshold_registry, league):
    """Append attack-weighted variants for species with a matching shared spread.

    For each base species in ``opponents``, check whether
    ``shared.<League>.spreads.<species>_atk_weighted`` exists. If so, append
    ``'<Species> (atk-weighted)'`` to the opponents list using the same
    moveset as the base entry. Silent on species without a matching spread.

    Returns (opponents_out, opp_movesets_out, added_labels).
    """
    if threshold_registry is None:
        return list(opponents), list(opp_movesets), []
    league_key = league.capitalize()
    already_present = set()
    for name in opponents:
        species, variant, _ = parse_opponent_spec(name)
        if variant == 'atk_weighted':
            already_present.add(species)

    opponents_out = list(opponents)
    opp_movesets_out = list(opp_movesets)
    added = []
    for idx, name in enumerate(list(opponents)):
        species, variant, is_shadow = parse_opponent_spec(name)
        if variant is not None:
            continue
        if is_shadow:
            continue
        if species in already_present:
            continue
        spread_name = _atk_weighted_spread_name(species)
        if threshold_registry.get_spread(species, league_key, spread_name) is None:
            continue
        variant_label = f"{species}{ATK_WEIGHTED_SUFFIX}"
        opponents_out.append(variant_label)
        opp_movesets_out.append(opp_movesets[idx])
        added.append(variant_label)
        already_present.add(species)
    return opponents_out, opp_movesets_out, added
