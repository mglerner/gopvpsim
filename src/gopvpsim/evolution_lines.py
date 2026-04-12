"""
Evolution line lookup.

Builds ``{final_species: [pre, ..., final]}`` from the gamemaster's
family data. Lazy-cached at module level; call
``invalidate_cache()`` if the gamemaster is reloaded mid-run (rare).

Pure Python — imported by ``user_collection`` and safe to import on
iOS via BeeWare. No numpy/numba dependencies.

Shared between pogo-simulator and gobattlekit; see
``memory/project_shared_user_collection.md`` for the code-sharing
design. Gobattlekit's equivalent module
(``src/gobattlekit/data/evolution_lines.py``) uses a bundled
``evolution_lines.json`` + disk cache; we instead generate on demand
from the gamemaster at each Python process start. Both approaches
end up with the same dict structure.
"""

from .data import load_gamemaster

_evolution_lines_cache: "dict | None" = None
_pre_to_finals_cache: "dict | None" = None


def _build_evolution_lines() -> dict:
    """Construct the evolution-line dict from the gamemaster.

    Returns a dict keyed on the final-form species name, whose value is
    the list of species names from root evo to final, inclusive:

        {'Tinkaton': ['Tinkatink', 'Tinkatuff', 'Tinkaton'], ...}

    Families with branching evolutions (e.g. Eevee) produce one entry
    per final form, each with its own chain from the shared root.
    """
    gm = load_gamemaster()
    id_to_name = {m['speciesId']: m['speciesName'] for m in gm['pokemon']}

    # Group gamemaster entries by family id; collect parent/evolutions
    # info per member.
    families: dict = {}
    for mon in gm['pokemon']:
        fam = mon.get('family')
        if not fam:
            continue
        fam_id = fam.get('id')
        if not fam_id:
            continue
        families.setdefault(fam_id, []).append({
            'id': mon['speciesId'],
            'parent': fam.get('parent'),
            'evolutions': fam.get('evolutions', []) or [],
        })

    def build_family_lines(members: list) -> list:
        """Walk each root → leaf path in the family and return them."""
        id_map = {m['id']: m for m in members}
        roots = [m for m in members if not m.get('parent')]
        lines: list = []

        visited: set = set()

        def traverse(sid: str, path: list) -> None:
            if sid in visited:
                return
            visited.add(sid)
            node = id_map.get(sid)
            if not node:
                return
            name = id_to_name.get(sid, sid)
            new_path = path + [name]
            evos = node['evolutions']
            if not evos:
                lines.append(new_path)
            else:
                for evo_id in evos:
                    traverse(evo_id, new_path)

        for root in roots:
            traverse(root['id'], [])
        return lines

    result: dict = {}
    for fam_id, members in families.items():
        for line in build_family_lines(members):
            if line:
                result[line[-1]] = line
    return result


def load_evolution_lines() -> dict:
    """Return the ``{final_species: [chain]}`` dict, cached after first call.

    The cache persists for the lifetime of the Python process. Call
    ``invalidate_cache()`` to force a rebuild if the gamemaster
    changes mid-run.
    """
    global _evolution_lines_cache
    if _evolution_lines_cache is None:
        _evolution_lines_cache = _build_evolution_lines()
    return _evolution_lines_cache


def _load_pre_to_finals() -> dict:
    """Return a reverse index ``{member_species: [final_species, ...]}``.

    Includes every species that appears anywhere in an evolution chain
    (roots, mid-evos, and final forms). Final forms map to a single-
    element list containing themselves. Branching pre-evos like Eevee
    map to a list of every reachable final form.

    The list is deduped and order is deterministic (sorted).
    """
    global _pre_to_finals_cache
    if _pre_to_finals_cache is None:
        lines = load_evolution_lines()
        reverse: dict = {}
        for final, chain in lines.items():
            for member in chain:
                reverse.setdefault(member, set()).add(final)
        # Freeze to sorted lists for deterministic output.
        _pre_to_finals_cache = {k: sorted(v) for k, v in reverse.items()}
    return _pre_to_finals_cache


def get_final_forms(species_name: str) -> list:
    """Return the list of possible final evolutions for a species name.

    - Final forms map to ``[species_name]`` (singleton).
    - Pre-evos with a single evolution chain map to ``[final]``.
    - Branching pre-evos map to all reachable finals (sorted).
    - Species with no evolutions (e.g. Ditto) or not in any family
      map to ``[species_name]`` as a fallback.

    Examples::

        get_final_forms('Tinkatink')  # → ['Tinkaton']
        get_final_forms('Tinkaton')   # → ['Tinkaton']
        get_final_forms('Eevee')      # → ['Espeon', 'Flareon', 'Glaceon',
                                      #    'Jolteon', 'Leafeon', 'Sylveon',
                                      #    'Umbreon', 'Vaporeon']
        get_final_forms('Ditto')      # → ['Ditto']
        get_final_forms('Bunnelby')   # → ['Diggersby']
    """
    return _load_pre_to_finals().get(species_name, [species_name])


def get_final_form(species_name: str) -> str:
    """Return a single final evolution for a species name.

    Raises ``ValueError`` if the species has a branching evolution
    (multiple possible finals) — callers that might encounter branches
    should use :func:`get_final_forms` instead.

    Kept for backwards compatibility with callers that know they're
    dealing with unambiguous chains (e.g. Tinkatink, Bunnelby).
    """
    finals = get_final_forms(species_name)
    if len(finals) > 1:
        raise ValueError(
            f"{species_name!r} has branching evolutions: {finals}. "
            f"Use get_final_forms() to handle all cases.")
    return finals[0]


def invalidate_cache() -> None:
    """Clear the cached dicts. Next call rebuilds from the gamemaster."""
    global _evolution_lines_cache, _pre_to_finals_cache
    _evolution_lines_cache = None
    _pre_to_finals_cache = None
