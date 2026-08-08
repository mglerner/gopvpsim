"""Pure-Python Pokemon Go PvP battle simulation library.

Beyond the submodules, this package exposes one process-wide utility:
``invalidate_caches()``, which drops every gamemaster/rankings-derived
lazy cache in the library at once, plus ``register_cache_invalidator()``
for out-of-package caches to join it.
"""

__all__ = ['invalidate_caches', 'register_cache_invalidator']


def _none():
    """Factory for caches whose 'not built yet' sentinel is None."""
    return None


# Every gamemaster/rankings-derived module cache in the library, as
# (module name, global name, factory producing the unbuilt value).
#
# These are ASSIGNED from here rather than cleared by a per-module
# invalidator on purpose: pokemon.py / moves.py are engine-hash files
# (editing one forces a cold re-dive; see CLAUDE.md), and setting a
# module global from outside is exactly equivalent to the `global`
# assignment the module's own builder does.
#
# Keep this table in sync when a new lazy gamemaster cache is added --
# tests/test_invalidate_caches.py fails loudly if a name here no longer
# exists, and invalidate_caches() itself raises rather than silently
# no-opping on a typo or a rename.
_CACHE_GLOBALS = (
    ('gopvpsim.pokemon',         '_pokemon_index',         _none),
    ('gopvpsim.pokemon',         '_gm_entry_index',        _none),
    ('gopvpsim.pokemon',         '_gm_id_index',           _none),
    ('gopvpsim.moves',           '_fast_moves',            _none),
    ('gopvpsim.moves',           '_charged_moves',         _none),
    ('gopvpsim.data',            '_species_id_index',      _none),
    ('gopvpsim.data',            '_rankings_index',        dict),
    ('gopvpsim.evolution_lines', '_evolution_lines_cache', _none),
    ('gopvpsim.evolution_lines', '_pre_to_finals_cache',   _none),
)

# functools-cached helpers over the same data (cleared via cache_clear()
# rather than by assignment), as (module name, attribute name).
_CACHE_CLEARS = (
    ('gopvpsim.display', '_female_sibling_bases'),
)

# Gamemaster-derived caches that live OUTSIDE the package -- today,
# scripts/auto_gen_narrative.py's move-display-name index. They cannot be
# table rows: the tables above are resolved with importlib, and the library
# must not import scripts/ (it is not a package, it is not installed, and
# nothing in the library may depend on the dive tooling). So instead of the
# library reaching out, the out-of-package module reaches IN and registers
# its own reset -- the seam runs one way, which keeps the dependency arrow
# pointing the same direction it already does.
#
# Populated by register_cache_invalidator(); intentionally a plain list so an
# unregistered caller simply never participates.
_EXTRA_INVALIDATORS: list = []


def register_cache_invalidator(fn):
    """Register ``fn`` to be called by ``invalidate_caches()``.

    For gamemaster/rankings-derived caches that live outside this package
    (scripts/, downstream tooling) and therefore cannot appear in the
    ``_CACHE_GLOBALS`` / ``_CACHE_CLEARS`` tables, which resolve names via
    importlib and only reach installed modules.

    ``fn`` takes no arguments and drops the caller's caches; it is invoked
    AFTER the library's own caches are dropped, so a hook that re-derives
    from library state sees the fresh state. Registration is idempotent
    (re-registering the same callable is a no-op), so it is safe to call
    from a lazy code path that runs more than once. Returns ``fn``, so it
    also works as a decorator.

    Register from the point where the cache is first built rather than at
    module import, so a module that is importable without this package stays
    that way.
    """
    if fn not in _EXTRA_INVALIDATORS:
        _EXTRA_INVALIDATORS.append(fn)
    return fn


def invalidate_caches() -> None:
    """Drop every gamemaster/rankings-derived cache in the library.

    Call this after the on-disk gamemaster or rankings cache is
    refreshed mid-process, or in a test that swaps ``load_gamemaster``
    for a fixture. Without it the modules keep independently-built
    indices and can end up disagreeing about the same species with no
    error raised.

    Rebuilding is lazy: each cache is only re-derived the next time
    something asks for it.

    Anything registered via ``register_cache_invalidator()`` runs last --
    that is how out-of-package caches (scripts/auto_gen_narrative.py's
    move-display index) join in without the library importing them.

    Raises AttributeError if a cache named in ``_CACHE_GLOBALS`` /
    ``_CACHE_CLEARS`` no longer exists, so a rename can't turn this
    into a silent no-op.
    """
    import importlib

    for mod_name, attr, factory in _CACHE_GLOBALS:
        mod = importlib.import_module(mod_name)
        if not hasattr(mod, attr):
            raise AttributeError(
                f"{mod_name}.{attr} no longer exists; update "
                f"gopvpsim.__init__._CACHE_GLOBALS")
        setattr(mod, attr, factory())

    for mod_name, attr in _CACHE_CLEARS:
        mod = importlib.import_module(mod_name)
        if not hasattr(mod, attr):
            raise AttributeError(
                f"{mod_name}.{attr} no longer exists; update "
                f"gopvpsim.__init__._CACHE_CLEARS")
        getattr(mod, attr).cache_clear()

    for fn in _EXTRA_INVALIDATORS:
        fn()
