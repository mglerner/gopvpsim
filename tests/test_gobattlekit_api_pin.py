"""Public-API pin for the ../gobattlekit consumer.

The sibling app pulls spreads out of this repo read-only:
``../gobattlekit/tools/threshold_export/export_thresholds.py`` imports NINE
names across five ``gopvpsim`` modules, and nothing on this side pinned any
of them.  Roughly 30 ``refactor(...)`` commits land here per month; a rename
breaks the export silently, discovered only when someone next runs it.
2026-08-09 test-suite review, policy-fit finding on the consumer contract.

Pinned deliberately at the level of NAMES + PARAMETER NAMES/KINDS, not
behavior: the export tool calls these by keyword, so what breaks it is a
rename or a positional->keyword-only move, and behavior is already covered by
tests/test_breakpoints.py, tests/test_thresholds.py and friends.  Defaults'
VALUES are not pinned -- only whether a parameter has one -- so tuning a
default is not a false alarm, while removing it (which makes the argument
required for a caller that omits it) is.

Nothing here reads or writes anything under ../gobattlekit; the last test
only parses that file, and skips when the sibling checkout is absent.
"""
import ast
import importlib
import inspect
from pathlib import Path

import pytest

# module path -> name -> ((param name, kind, has-default), ...)
# Regenerate with inspect.signature if a change here is intentional.
PINNED = {
    ('gopvpsim.breakpoints', 'breakpoints'): (
        ('move', 'POSITIONAL_OR_KEYWORD', False),
        ('attacker_types', 'POSITIONAL_OR_KEYWORD', False),
        ('defender_def', 'POSITIONAL_OR_KEYWORD', False),
        ('defender_types', 'POSITIONAL_OR_KEYWORD', False),
        ('atk_min', 'POSITIONAL_OR_KEYWORD', False),
        ('atk_max', 'POSITIONAL_OR_KEYWORD', False),
        # Added 2026-09-02 for the Mega Bonus. KEYWORD_ONLY with a default,
        # so the export tool's 6 positional args cannot collide with it and
        # omitting it reproduces the pre-mega behavior exactly. No
        # ../gobattlekit change was required.
        ('mega_level', 'KEYWORD_ONLY', True),
    ),
    ('gopvpsim.breakpoints', 'bulkpoints'): (
        ('move', 'POSITIONAL_OR_KEYWORD', False),
        ('attacker_atk', 'POSITIONAL_OR_KEYWORD', False),
        ('attacker_types', 'POSITIONAL_OR_KEYWORD', False),
        ('defender_types', 'POSITIONAL_OR_KEYWORD', False),
        ('def_min', 'POSITIONAL_OR_KEYWORD', False),
        ('def_max', 'POSITIONAL_OR_KEYWORD', False),
        ('mega_level', 'KEYWORD_ONLY', True),   # see breakpoints() above
    ),
    ('gopvpsim.data', 'load_gamemaster'): (),
    ('gopvpsim.data', 'parse_types'): (
        ('mon', 'POSITIONAL_OR_KEYWORD', False),
    ),
    ('gopvpsim.moves', 'get_moves'): (),
    ('gopvpsim.pokemon', 'iv_rank'): (
        ('species_name', 'POSITIONAL_OR_KEYWORD', False),
        ('league', 'KEYWORD_ONLY', True),
        ('max_level', 'KEYWORD_ONLY', True),
        ('shadow', 'KEYWORD_ONLY', True),
    ),
    ('gopvpsim.thresholds', 'IvListSpread'): (
        ('name', 'POSITIONAL_OR_KEYWORD', False),
        ('ivs', 'POSITIONAL_OR_KEYWORD', False),
        ('description', 'POSITIONAL_OR_KEYWORD', True),
        ('source', 'POSITIONAL_OR_KEYWORD', True),
        ('deprecated', 'POSITIONAL_OR_KEYWORD', True),
    ),
    ('gopvpsim.thresholds', 'StatCutoffSpread'): (
        ('name', 'POSITIONAL_OR_KEYWORD', False),
        ('attack', 'POSITIONAL_OR_KEYWORD', True),
        ('defense', 'POSITIONAL_OR_KEYWORD', True),
        ('stamina', 'POSITIONAL_OR_KEYWORD', True),
        ('description', 'POSITIONAL_OR_KEYWORD', True),
        ('source', 'POSITIONAL_OR_KEYWORD', True),
        ('deprecated', 'POSITIONAL_OR_KEYWORD', True),
    ),
    ('gopvpsim.thresholds', 'load_file'): (
        ('path', 'POSITIONAL_OR_KEYWORD', False),
        ('species', 'KEYWORD_ONLY', True),
        ('league', 'KEYWORD_ONLY', True),
    ),
}

SIBLING_EXPORT = (Path(__file__).resolve().parents[2] / 'gobattlekit' /
                  'tools' / 'threshold_export' / 'export_thresholds.py')


def _observed(module_path, name):
    obj = getattr(importlib.import_module(module_path), name)
    return tuple((p.name, p.kind.name,
                  p.default is not inspect.Parameter.empty)
                 for p in inspect.signature(obj).parameters.values())


@pytest.mark.parametrize('key', sorted(PINNED), ids=lambda k: f'{k[0]}.{k[1]}')
def test_consumer_facing_signature_is_unchanged(key):
    module_path, name = key
    mod = importlib.import_module(module_path)
    assert hasattr(mod, name), (
        f'{module_path}.{name} no longer exists. '
        f'../gobattlekit/tools/threshold_export/export_thresholds.py imports '
        f'it by name; renaming it breaks the export with an ImportError that '
        f'nothing in this repo would have caught.')
    assert _observed(module_path, name) == PINNED[key], (
        f'{module_path}.{name} changed shape. If the change is intentional, '
        f'update export_thresholds.py in ../gobattlekit FIRST, then re-pin '
        f'here.')


def test_pin_covers_nine_names_across_five_modules():
    """Anti-vacuity floor: an empty or truncated PINNED table would make every
    parametrized case above pass by not existing."""
    assert len(PINNED) == 9
    assert len({m for m, _ in PINNED}) == 5


def test_thresholds_declares_its_public_surface():
    """``__all__`` is the marker that says which of load_toml /
    load_legacy_json / load_file an outside caller is meant to use."""
    import gopvpsim.thresholds as th
    assert hasattr(th, '__all__'), (
        'src/gopvpsim/thresholds.py lost its __all__; it has an external '
        'consumer and three similarly-named loaders.')
    assert {'IvListSpread', 'StatCutoffSpread', 'load_file'} <= set(th.__all__)
    missing = [n for n in th.__all__ if not hasattr(th, n)]
    assert not missing, f'__all__ names nonexistent attributes: {missing}'
    private = [n for n in th.__all__ if n.startswith('_')]
    assert not private, f'__all__ should not export private names: {private}'


@pytest.mark.skipif(not SIBLING_EXPORT.exists(),
                    reason='../gobattlekit checkout not present')
def test_pin_still_matches_what_the_consumer_actually_imports():
    """Stale-pin guard: derive the imported names from the consumer's own
    source rather than trusting this file's hand-copied list.

    Read-only. If gobattlekit starts importing a tenth name, this fails and
    the pin above gets extended -- which is the whole point, since the
    failure mode being defended against is a rename nobody notices.
    """
    tree = ast.parse(SIBLING_EXPORT.read_text(), filename=str(SIBLING_EXPORT))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module \
                and node.module.split('.')[0] == 'gopvpsim':
            for alias in node.names:
                imported.add((node.module, alias.name))
    imported.discard(('gopvpsim', 'gopvpsim'))
    assert imported, 'found no gopvpsim imports in the consumer -- did the ' \
                     'file move? Update SIBLING_EXPORT.'
    unpinned = sorted(imported - set(PINNED))
    assert not unpinned, (
        f'../gobattlekit imports gopvpsim name(s) this pin does not cover: '
        f'{unpinned}. Add them to PINNED.')
