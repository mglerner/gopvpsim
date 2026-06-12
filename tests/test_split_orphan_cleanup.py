"""_remove_stale_split_siblings: stale split-file orphan cleanup.

A re-dive whose moveset enumeration changed writes differently-named
``index_m*.html`` files; old ones must be deleted or downstream
consumers (article freshness gate, compare_loadouts) see mixed data
vintages. This killed the 2026-06-11 overnight chain.
"""
import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'


def _load_deep_dive():
    if 'deep_dive' in sys.modules:
        return sys.modules['deep_dive']
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        'deep_dive', _SCRIPTS / 'deep_dive.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['deep_dive'] = mod
    spec.loader.exec_module(mod)
    return mod


def test_stale_siblings_removed_fresh_kept(tmp_path):
    dd = _load_deep_dive()
    base = tmp_path / 'index.html'
    base.write_text('landing')
    fresh = tmp_path / 'index_m1_tackle_body_slam.html'
    fresh.write_text('fresh split')
    stale = tmp_path / 'index_m1_mud_slap_trailblaze.html'
    stale.write_text('old split, different enumeration')
    stale2 = tmp_path / 'index_m4_tackle_dig.html'
    stale2.write_text('old split, index beyond fresh set')

    dd._remove_stale_split_siblings(str(base), [str(fresh)])

    assert base.exists()
    assert fresh.exists()
    assert not stale.exists()
    assert not stale2.exists()


def test_single_file_rerun_clears_all_splits(tmp_path):
    # A re-dive that now produces only the landing file (e.g. one
    # surviving moveset) must clear every old split sibling — the
    # Ninetales case from the 2026-06-11 chain.
    dd = _load_deep_dive()
    base = tmp_path / 'index.html'
    base.write_text('landing')
    stale = tmp_path / 'index_m1_ember_weather_ball.html'
    stale.write_text('old split')

    dd._remove_stale_split_siblings(str(base), [])

    assert base.exists()
    assert not stale.exists()


def test_unrelated_files_untouched(tmp_path):
    dd = _load_deep_dive()
    base = tmp_path / 'index.html'
    base.write_text('landing')
    other_stem = tmp_path / 'report_m1_foo.html'
    other_stem.write_text('different stem')
    non_split = tmp_path / 'index_extra.html'
    non_split.write_text('no _m<digit> pattern')

    dd._remove_stale_split_siblings(str(base), [])

    assert other_stem.exists()
    assert non_split.exists()
