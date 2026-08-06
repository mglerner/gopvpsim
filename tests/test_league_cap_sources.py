"""League CP caps: one canonical dict, no script-local copies.

``pokemon.LEAGUE_CAPS`` is the canonical mapping (it stays in pokemon.py on
purpose -- moving it would edit an engine-hash file for a cosmetic win).
``scripts/build_opponent_pool.py`` used to carry its own ``_CP_BY_LEAGUE``
literal, which is the same unforced-copy shape that let the shadow-defense
multiplier rot unnoticed for months. This pins the import.

The JS-side fallback literal is pinned separately in
``tests/test_js_shadow_constants.py``.
"""
import importlib.util
import re
from pathlib import Path

from gopvpsim.pokemon import LEAGUE_CAPS

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / 'scripts' / 'build_opponent_pool.py'


def _load():
    spec = importlib.util.spec_from_file_location('build_opponent_pool_pin', SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_opponent_pool_uses_canonical_caps():
    mod = _load()
    assert mod.LEAGUE_CAPS is LEAGUE_CAPS


def test_build_opponent_pool_has_no_local_cap_dict():
    src = SRC.read_text()
    assert '_CP_BY_LEAGUE' not in src, (
        'build_opponent_pool.py re-declares the league CP caps; import '
        'LEAGUE_CAPS from gopvpsim.pokemon instead')
    # No other inline ``{'great': 1500, ...}``-shaped literal either.
    assert not re.search(r"\{\s*'great'\s*:\s*1500", src)


def test_canonical_caps_values():
    """Guard the values themselves so an import-only refactor can't drift.

    'little' joined the table with the league descriptor (DRY review
    2026-08-05 entry 13 / L6); the per-league facts are pinned in
    tests/test_league_descriptor.py.
    """
    assert LEAGUE_CAPS == {'little': 500, 'great': 1500,
                           'ultra': 2500, 'master': 10000}
