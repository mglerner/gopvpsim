"""``sweep_cache._ENGINE_FILES`` must cover everything the engine imports.

``engine_hash()`` stamps every cached sweep column.  An edit to a hashed
module changes the stamp, so the column re-sims; an edit to an UNHASHED
module the engine reads does not, so the cache keeps serving scores computed
under the old code -- silently, with no error and no self-heal.  The list is
a hand-maintained literal tuple (scripts/sweep_cache.py:112-113), and until
now nothing checked it against what ``gopvpsim.battle`` actually pulls in.
2026-08-09 test-suite review, policy-fit finding F5.

This test derives the closure by AST-walking intra-package imports rather
than by importing and diffing ``sys.modules``, so it also sees edges that a
runtime probe would miss: ``battle.py`` reaches ``formchange`` only through
function-level ``from .formchange import ...`` statements (battle.py:2041,
2093, 2126), which never execute for a battle without a form-change species.

DEVELOPER_NOTES.md:384-388 already states the design rule this enforces
("the same constants in an unhashed module would let the sweep cache serve
columns computed under the old values").  The point of the test is that new
edges get caught: the two current exceptions are named and reasoned about
below, and anything else fails.
"""
import ast
import os
import sys
from pathlib import Path

import gopvpsim

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import sweep_cache  # noqa: E402

PKG_DIR = Path(gopvpsim.__file__).resolve().parent
ROOT_MODULE = 'battle'

# Modules that are in the closure but deliberately NOT engine-hashed.
# Each entry needs a reason, and the reason has to survive being read by
# someone deciding whether to add a sixth.
ALLOWLIST = {
    '__init__.py':
        "package init: its content is the invalidate_caches/_CACHE_GLOBALS "
        "cache utility, not sim math. Nothing it defines feeds a damage, "
        "stat or timing calculation.",
    'data.py':
        "KNOWN HOLE, not an endorsement. data.parse_types (data.py:207-215) "
        "IS damage-affecting -- it produces the type lists that reach "
        "type_effectiveness() and stab() on every calc_damage call -- so an "
        "edit to it can change a score while engine_hash() stands still. "
        "The fix is to relocate parse_types into an already-hashed module "
        "(pokemon.py or moves.py) per the rule DEVELOPER_NOTES.md:384-388 "
        "already states for the league table; it is QUEUED FOR THE NEXT "
        "ENGINE-HASH BUMP WINDOW rather than done here, because adding "
        "data.py to _ENGINE_FILES costs a full cold re-dive. Empirically "
        "low risk: parse_types' body has changed exactly once in 1165 "
        "commits (the commit that created it). See the 2026-08-09 "
        "test-suite review, finding F5.",
}


def _intra_package_imports(path):
    """Every ``gopvpsim`` sibling module `path` imports, at ANY nesting depth.

    Covers ``from . import x`` / ``from .x import y`` (relative) and
    ``import gopvpsim.x`` / ``from gopvpsim.x import y`` (absolute), whether
    written at module scope or inside a function body.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.module:          # from .x import y
                found.add(node.module.split('.')[0])
            elif node.level and node.module is None:  # from . import x, y
                found.update(a.name.split('.')[0] for a in node.names)
            elif node.module and node.module.split('.')[0] == 'gopvpsim':
                parts = node.module.split('.')
                if len(parts) > 1:
                    found.add(parts[1])
        elif isinstance(node, ast.Import):
            for a in node.names:
                parts = a.name.split('.')
                if parts[0] == 'gopvpsim' and len(parts) > 1:
                    found.add(parts[1])
    return found


def _walk(root=ROOT_MODULE):
    """Transitive intra-package closure of `root`: ``(file_names, unresolved)``.

    Seeded with ``__init__.py`` as well as `root`, because importing any
    submodule executes the package init -- so whatever IT imports is in the
    engine's runtime closure too, and a walk that only pasted ``__init__.py``
    onto the result as a string would miss a module reachable solely through
    it.

    A name that resolves to a SUBPACKAGE (``gopvpsim/x/__init__.py``) is
    reported as ``'x/__init__.py'`` and NOT descended into: its relative
    imports resolve against a different base, which this flat walker does not
    model.  That under-approximation is safe rather than silent, because
    ``_ENGINE_FILES`` is a flat tuple of top-level module names and can never
    contain a subpackage -- so the entry lands in ``unaccounted`` and fails
    ``test_every_engine_import_is_hashed_or_explicitly_allowlisted`` until a
    human writes down what to do about it.  Do not "fix" that by descending;
    fix it by deciding whether the subpackage belongs in the engine at all.

    Names that resolve to neither are returned in `unresolved` rather than
    dropped -- see ``test_every_intra_package_import_resolves``.
    """
    seen, subpkgs, unresolved = set(), set(), set()
    stack = [root, '__init__']
    while stack:
        name = stack.pop()
        if name in seen or name in subpkgs:
            continue
        module = PKG_DIR / f'{name}.py'
        package = PKG_DIR / name / '__init__.py'
        if module.exists():
            seen.add(name)
            stack.extend(_intra_package_imports(module) - seen)
        elif package.exists():
            subpkgs.add(name)          # surfaced, deliberately not descended
        else:
            unresolved.add(name)
    files = {f'{n}.py' for n in seen} | {f'{n}/__init__.py' for n in subpkgs}
    return files, unresolved


def _closure(root=ROOT_MODULE):
    """The file-name half of :func:`_walk`."""
    return _walk(root)[0]


def test_the_walker_finds_the_edges_a_runtime_probe_would_miss():
    """Guard the guard: the closure walk must be non-trivial and must see
    both module-scope and function-level relative imports."""
    direct = _intra_package_imports(PKG_DIR / 'battle.py')
    assert 'moves' in direct and 'data' in direct and 'pokemon' in direct, direct
    # formchange is imported ONLY inside function bodies (battle.py:2041,
    # 2093, 2126). If the walk ever stops descending into functions, this
    # is what says so -- otherwise the whole test quietly narrows.
    assert 'formchange' in direct, (
        'the AST walk no longer sees battle.py\'s function-level '
        f'"from .formchange import ..." edges; found only {sorted(direct)}')


def test_closure_is_the_expected_set():
    """Anti-vacuity floor: a walker that returned {} would pass the coverage
    assertion below trivially, so pin the shape of what it found."""
    closure = _closure()
    assert closure >= {'battle.py', 'moves.py', 'pokemon.py', 'data.py',
                       '_dp_jit.py', 'formchange.py', '__init__.py'}, closure
    assert len(closure) >= 7


def test_every_intra_package_import_resolves():
    """No import may vanish from the walk unexplained.

    The walker used to ``continue`` past any name with no ``<name>.py`` beside
    it, which silently dropped whole subtrees (a subpackage resolved to
    nothing and was never reported).  Anything the walk cannot place is now
    surfaced here instead of shrinking the closure behind everyone's back."""
    _files, unresolved = _walk()
    assert not unresolved, (
        'the engine has intra-package import(s) this walk cannot resolve to a '
        f'module or subpackage: {sorted(unresolved)}. Either it is a NAME '
        're-exported from gopvpsim/__init__.py (in which case teach the walker '
        'to map it to the module that defines it) or the closure is now '
        'under-counting and the coverage assertion below has gone soft.')


def test_every_engine_import_is_hashed_or_explicitly_allowlisted():
    """THE assertion. A new intra-package import from the engine must either
    join ``_ENGINE_FILES`` or earn a named entry in ``ALLOWLIST`` above."""
    closure = _closure()
    hashed = set(sweep_cache._ENGINE_FILES)
    unaccounted = sorted(closure - hashed - set(ALLOWLIST))
    assert not unaccounted, (
        'gopvpsim.battle now (transitively) imports module(s) that are '
        f'neither in sweep_cache._ENGINE_FILES nor allowlisted: {unaccounted}.\n'
        'A cached sweep column is stamped with engine_hash(), so an edit to '
        'an unhashed module the engine reads is served WARM under the old '
        'scores. Either add the file to _ENGINE_FILES (costs one cold '
        're-dive) or add it to ALLOWLIST in this test with a reason that '
        'says why it cannot change a score.')


def test_allowlist_entries_are_all_still_in_the_closure():
    """Stale-allowlist guard (the pattern at
    tests/test_gamemaster_lookup_sites.py:365-375). An allowlist entry whose
    module no longer reaches the engine is an exemption nobody is checking --
    and if parse_types is ever relocated, this is what says "delete the
    data.py entry"."""
    closure = _closure()
    stale = sorted(set(ALLOWLIST) - closure)
    assert not stale, (
        f'ALLOWLIST names module(s) the engine no longer imports: {stale}. '
        'Delete the entry -- and if this is data.py, the parse_types '
        'relocation landed, so update DEVELOPER_NOTES too.')


def test_allowlisted_files_are_not_also_hashed():
    """The two lists must not overlap, or an allowlist entry silently stops
    meaning anything."""
    both = sorted(set(ALLOWLIST) & set(sweep_cache._ENGINE_FILES))
    assert not both, f'allowlisted AND hashed (drop the allowlist entry): {both}'


def test_every_hashed_file_exists():
    """_ENGINE_FILES is a literal tuple of names; a rename would make
    engine_hash() raise at dive time rather than here."""
    missing = [n for n in sweep_cache._ENGINE_FILES
               if not (PKG_DIR / n).exists()]
    assert not missing, f'_ENGINE_FILES names nonexistent module(s): {missing}'
