"""Display-name formatting helpers.

Mercuryish-review-driven (2026-05-17): the gamemaster `speciesName`
format ("Forretress (Shadow)", "Corsola (Galarian)") reads
awkwardly in prose; the modifier-first form ("Shadow Forretress",
"Galarian Corsola") is what readers expect. This module's
`pretty_species()` is the single, leaf-only display transform —
internal lookups still use the gamemaster name; only HTML emission
goes through `pretty_species`.

See `userdata/reviews/phase4_plan.md` for the original design.
"""
from __future__ import annotations

from functools import lru_cache

# Regional/shadow tags that get hoisted from a trailing parenthetical
# to a leading prefix. Order in the output: Shadow first (it's the
# semantic modifier, applied on top of the regional flavor), then the
# regional tag — `Weezing (Galarian) (Shadow)` → `Shadow Galarian
# Weezing`, matching how players actually say it.
_REGIONAL_TAGS = ('Shadow', 'Galarian', 'Alolan', 'Hisuian', 'Paldean')


def _strip_one_regional_suffix(name: str) -> tuple[str, str | None]:
    """If ``name`` ends with ` (Shadow)` / ` (Galarian)` / etc., return
    (stripped_name, tag). Otherwise return (name, None)."""
    for tag in _REGIONAL_TAGS:
        suffix = f' ({tag})'
        if name.endswith(suffix):
            return name[: -len(suffix)], tag
    return name, None


@lru_cache(maxsize=1)
def _female_sibling_bases() -> frozenset[str]:
    """Return the set of bare gamemaster species names whose Female
    sibling form exists in the gamemaster.

    E.g. if the gamemaster has both ``Oinkologne`` and
    ``Oinkologne (Female)``, this set contains ``Oinkologne``.
    The bare male form gets a ``(Male)`` suffix via `pretty_species`
    so the two forms read symmetrically.

    Cached because the gamemaster load is expensive and the female-
    sibling set never changes within a process.
    """
    # Import here to avoid circular imports at module-load time
    # (data.py → pokemon.py → display.py is the import order in some
    # code paths).
    from .data import load_gamemaster

    gm = load_gamemaster()
    bases: set[str] = set()
    suffix = ' (Female)'
    for mon in gm.get('pokemon', []):
        name = mon.get('speciesName', '')
        if name.endswith(suffix):
            bases.add(name[: -len(suffix)])
    return frozenset(bases)


_REGIONAL_TAGS_LOWER = {t.lower(): t for t in _REGIONAL_TAGS}


def pretty_species_from_slug(slug: str) -> str:
    """Convert a lowercase-underscore species slug to a display name.

    Slug format is gamemaster ``speciesName`` lowercased with non-
    alphanumerics replaced by ``_``: ``corsola_galarian``,
    ``quagsire_shadow``, ``weezing_galarian_shadow``, ``mirror``,
    ``mirror_top50``.

    Output follows the same rules as ``pretty_species``: regional
    and shadow tags hoist to a leading prefix, gender disambiguation
    applies if the bare base is a male-female-paired species.

      ``cresselia``                → ``Cresselia``
      ``mirror``                   → ``Mirror``
      ``corsola_galarian``         → ``Galarian Corsola``
      ``quagsire_shadow``          → ``Shadow Quagsire``
      ``weezing_galarian_shadow``  → ``Shadow Galarian Weezing``
      ``oinkologne``               → ``Oinkologne (Male)``  (Female sibling exists)
      ``oinkologne_female``        → ``Oinkologne (Female)``

    Used by anchor display-name derivation so anchor badges read
    with the same convention as opponent strings on the rest of the
    dive page.
    """
    tokens = slug.split('_')
    # Pull off trailing regional/shadow tokens.
    prefixes: list[str] = []
    while tokens and tokens[-1] in _REGIONAL_TAGS_LOWER:
        prefixes.append(_REGIONAL_TAGS_LOWER[tokens.pop()])
    # Special-case "female" as the only non-regional token we promote
    # to a parenthetical (matches gamemaster format).
    female_form = False
    if tokens and tokens[-1] == 'female':
        female_form = True
        tokens.pop()

    # Capitalize remaining tokens for the base species name.
    base = ' '.join(t.capitalize() for t in tokens) if tokens else ''

    # Reconstruct the gamemaster-format name so pretty_species sees
    # what it expects.
    gm_name = base
    if female_form:
        gm_name = f'{gm_name} (Female)'
    for tag in reversed(prefixes):
        gm_name = f'{gm_name} ({tag})'

    return pretty_species(gm_name)


def pretty_species(name: str) -> str:
    """Reformat a gamemaster ``speciesName`` for display.

    Rules applied:

    - Trailing regional/shadow parentheticals (` (Shadow)`,
      ` (Galarian)`, ` (Alolan)`, ` (Hisuian)`, ` (Paldean)`) are
      stripped iteratively and re-emitted as a space-separated prefix.
      Shadow goes outermost; regional tags follow.

          ``Forretress (Shadow)``         → ``Shadow Forretress``
          ``Corsola (Galarian)``          → ``Galarian Corsola``
          ``Weezing (Galarian) (Shadow)`` → ``Shadow Galarian Weezing``

    - Non-regional parentheticals (Shield/Blade, Busted/Disguised,
      Full Belly/Hangry, Super/Large/Small/Average, Female) are left
      alone — they're in-battle form changes or gender variants, not
      regional flavors.

          ``Aegislash (Shield)``  → ``Aegislash (Shield)`` (unchanged)
          ``Mimikyu (Busted)``    → ``Mimikyu (Busted)``  (unchanged)
          ``Oinkologne (Female)`` → ``Oinkologne (Female)`` (unchanged)

    - Bare male forms gain a ``(Male)`` suffix when the gamemaster has
      a Female sibling form. Mirror's mercuryish's symmetry request.

          ``Oinkologne``                → ``Oinkologne (Male)``
          (when ``Oinkologne (Female)`` exists in the gamemaster)

    Idempotent: ``pretty_species(pretty_species(x))`` == ``pretty_species(x)``
    for all valid gamemaster names — the result has its regional tag
    as a prefix (no trailing parenthetical for `_strip_one_regional_suffix`
    to bite on), and the female-sibling check uses the unchanged base.
    """
    prefixes: list[str] = []
    base = name
    while True:
        new_base, tag = _strip_one_regional_suffix(base)
        if tag is None:
            break
        base = new_base
        prefixes.append(tag)

    if prefixes:
        # Shadow on the outside, then regionals. The strip order produces
        # [outer, ..., inner]; e.g. for "Weezing (Galarian) (Shadow)"
        # we strip Shadow first then Galarian, giving ['Shadow',
        # 'Galarian']. That's already the display order.
        ordered = sorted(prefixes,
                         key=lambda p: 0 if p == 'Shadow' else 1)
        result = ' '.join(ordered) + ' ' + base
    else:
        result = base

    # Gender disambiguation. Only fires when:
    #   - The bare base (after regional-strip) is in the female-sibling set
    #   - The name doesn't already carry a ``(Female)`` tag
    #   - The name doesn't carry an in-battle form tag (Shield/Blade/etc.)
    if base in _female_sibling_bases() and '(' not in base:
        result = result + ' (Male)'

    return result
