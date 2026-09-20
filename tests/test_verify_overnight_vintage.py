"""Build-vintage stamp: deep_dive writes it, verify_overnight reads it.

A dive's SCORES come frozen out of its replay blob, but the render reads the
LIVE gamemaster and the LIVE rankings every time
(``deep_dive_brief.build_opp_meta_ranks`` -> ``data.get_rankings_for``). A
24h-TTL refetch part-way through a multi-day bake therefore changes opponent
ranks -- and with them the VERDICTS a page prints -- between one page and the
next, with no sim change at all. It happened on 2026-09-12.

Pre-fix value: nothing recorded the vintage anywhere -- not on the page, not
beside it, not in the replay blob -- so a mid-bake roll was UNDETECTABLE after
the fact. ``vintage_errors`` did not exist and a mixed bake passed the morning
gate green; the only protection was remembering to launch through
``overnight_redive.sh``, whose TTL keeper prevents the roll in the first place.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import verify_overnight as vo  # noqa: E402


def _stamp(d, engine, gamemaster, name='x'):
    sub = d / name
    sub.mkdir(parents=True, exist_ok=True)
    (sub / vo.VINTAGE_FILE).write_text(
        f'engine_hash     = "{engine}"\n'
        f'gamemaster_hash = "{gamemaster}"\n'
        'rankings_file   = "great.json"\n'
        'rankings_mtime  = 1758000000\n')
    return sub


def test_one_vintage_everywhere_is_clean(tmp_path):
    dirs = [_stamp(tmp_path, 'eeee11112222', 'gggg11112222', f'dive{i}')
            for i in range(4)]
    assert vo.vintage_errors(dirs) == []


def test_a_mid_bake_gamemaster_roll_is_red_and_names_the_minority(tmp_path):
    """The 2026-09-12 shape: most pages on one vintage, a tail on another."""
    dirs = [_stamp(tmp_path, 'eeee11112222', 'gggg11112222', f'dive{i}')
            for i in range(5)]
    dirs.append(_stamp(tmp_path, 'eeee11112222', 'hhhh33334444', 'late'))
    errs = vo.vintage_errors(dirs)
    assert len(errs) == 1, errs                 # pre-fix: no such check
    assert errs[0].startswith('MIXED gamemaster_hash')
    assert 'hhhh33334444 x1' in errs[0]
    assert 'late' in errs[0]
    # the engine was consistent, so it must NOT also be reported
    assert 'MIXED engine_hash' not in errs[0]


def test_a_mixed_engine_is_red_too(tmp_path):
    dirs = [_stamp(tmp_path, 'eeee11112222', 'gggg11112222', 'a'),
            _stamp(tmp_path, 'ffff55556666', 'gggg11112222', 'b')]
    errs = vo.vintage_errors(dirs)
    assert len(errs) == 1
    assert errs[0].startswith('MIXED engine_hash')
    assert 'eeee11112222' in errs[0] and 'ffff55556666' in errs[0]


def test_both_axes_mixed_gives_two_lines(tmp_path):
    dirs = [_stamp(tmp_path, 'eeee11112222', 'gggg11112222', 'a'),
            _stamp(tmp_path, 'ffff55556666', 'hhhh33334444', 'b')]
    assert len(vo.vintage_errors(dirs)) == 2


def test_an_unstamped_dir_is_reported_not_silently_consistent(tmp_path):
    """"No evidence" and "evidence of one vintage" are different answers."""
    dirs = [_stamp(tmp_path, 'eeee11112222', 'gggg11112222', 'a')]
    bare = tmp_path / 'nostamp'
    bare.mkdir()
    dirs.append(bare)
    errs = vo.vintage_errors(dirs)
    assert len(errs) == 1
    assert 'no vintage.toml in 1 fresh dive dirs' in errs[0]
    assert 'nostamp' in errs[0]


def test_an_unreadable_stamp_is_reported(tmp_path):
    d = tmp_path / 'broken'
    d.mkdir()
    (d / vo.VINTAGE_FILE).write_text('this is not = valid = toml [[[\n')
    errs = vo.vintage_errors([d])
    assert len(errs) == 1 and 'no vintage.toml' in errs[0]


def test_the_stamp_is_not_published():
    """It is build metadata, like meta.toml, and must not reach the site."""
    sh = (REPO_ROOT / 'scripts' / 'publish_website.sh').read_text()
    line = next(ln for ln in sh.splitlines()
                if ln.startswith('RSYNC_EXCLUDES='))
    assert "--exclude='vintage.toml'" in line
    assert "--exclude='meta.toml'" in line      # positive control


def test_the_stamp_is_not_a_meta_toml_key():
    """It deliberately lives in its OWN file.

    ``meta.toml`` is the site index's AUTHORED channel: build_website_index
    requires title/description/landing there and treats any dir that has one
    as curated. Dive dirs carry none and are titled from their slug, so
    folding a build stamp into meta.toml would either drop every dive off
    the index (missing required keys) or change how all 136 render on it.
    """
    import build_website_index as bwi
    src = (REPO_ROOT / 'scripts' / 'build_website_index.py').read_text()
    assert 'vintage.toml' not in src
    assert "for k in ('title', 'description', 'landing')" in src  # the schema
    assert callable(bwi.load_entries)


def test_build_website_index_ignores_a_dive_dir_carrying_a_stamp(tmp_path):
    """A stamped dive still loads, and is still NOT curated."""
    import build_website_index as bwi
    d = tmp_path / 'tinkaton-great-league'
    d.mkdir()
    (d / 'index.html').write_text('<title>Tinkaton - Great League IV Dive</title>')
    (d / vo.VINTAGE_FILE).write_text('engine_hash = "eeee11112222"\n')
    entries = bwi.load_entries(tmp_path)
    assert len(entries) == 1, entries
    assert entries[0]['curated'] is False
    assert entries[0]['landing'] == 'index.html'


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_a_real_render_writes_the_stamp(tmp_path):
    """The render tail actually emits it, with values that resolve.

    Blob-backed rather than mocked: the point of the stamp is that it records
    what THIS process read, so a test that does not run the render tail would
    not be testing the thing.
    """
    import tomllib
    from tests.conftest import load_deep_dive
    import sweep_cache
    blobs = sorted((REPO_ROOT / 'userdata' / 'replay').glob('*.replay.pkl.gz'),
                   key=lambda p: p.stat().st_size)
    if not blobs:
        pytest.skip('no replay blobs on this machine')
    dd = load_deep_dive()
    state = dd.load_replay_state(str(blobs[0]))
    state['html_path'] = str(tmp_path / 'index.html')
    state['card_path'] = None
    dd.render_dive_html(state)
    stamp = tmp_path / vo.VINTAGE_FILE
    assert stamp.exists(), 'the render tail wrote no vintage stamp'
    with open(stamp, 'rb') as fh:
        got = tomllib.load(fh)
    assert got['engine_hash'] == sweep_cache.engine_hash()
    assert got['gamemaster_hash'] == sweep_cache.gamemaster_hash()
    assert got['rankings_file'].endswith('.json')
    assert isinstance(got['rankings_mtime'], int)
    assert got['rendered_at']
    # and the check reads its own writer's output
    assert vo.vintage_errors([tmp_path]) == []
