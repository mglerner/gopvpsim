"""build_joint_iv_page._configure: config plumbing pins.

Cheap pins on the page builder's pair-config resolution -- the byte-level
rebuild acceptance ran in-session (2026-08-19); these keep the config
contract from silently drifting afterward.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / 'scripts'
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_ROOT / 'src'))

from joint_iv_config import load_pair  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    'build_joint_iv_page', _SCRIPTS / 'build_joint_iv_page.py')
_page = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_page)


_BASE = '''
[pair]
league = "great"
focal = "Wigglytuff"
focal_shadow = false
focal_slug = "wigglytuff"
opponent = "Lickilicky"
opponent_shadow = false
opponent_slug = "lickilicky"
opponent_fast = "ROLLOUT"
opponent_charged = ["BODY_SLAM", "SHADOW_BALL"]
data_dir = "userdata/joint_iv/x"
injected_moves = []

[[grids]]
label = "iwsw_bait"
focal_fast = "CHARM"
focal_charged = ["ICY_WIND", "SWIFT"]
bait = true

[[grids]]
label = "iwsw_nobait"
focal_fast = "CHARM"
focal_charged = ["ICY_WIND", "SWIFT"]
bait = false
'''


def _cfg(tmp_path, body=_BASE):
    p = tmp_path / 'pair.toml'
    p.write_text(body)
    return load_pair(p)


def test_configure_defaults(tmp_path):
    _page._configure(_cfg(tmp_path))
    assert _page.LEAGUE == 'great' and _page.LEAGUE_LABEL == 'Great'
    assert _page.MAX_LEVEL == 50.0
    assert _page.PRIMARY_ARM == 'iwsw'
    assert _page.LABEL_ORDER == ['iwsw_bait', 'iwsw_nobait']
    assert _page.PUBLISH_SLUG_NAME == 'wigglytuff-lickilicky-robustness.html'
    assert _page.PRETTY_FALLBACK['iwsw_bait'] == \
        'Charm / Icy Wind + Swift, baiting'
    assert _page.DENIAL_FILENAME == 'denial.json'
    assert _page.ARCHIVE_NOTE_TEXT is None
    assert _page.METAWINS_FALLBACK_DIR is None


def test_injected_moves_require_static_note(tmp_path):
    body = _BASE.replace('injected_moves = []',
                         'injected_moves = ["ICY_WIND"]')
    with pytest.raises(SystemExit, match='injected_note'):
        _page._configure(_cfg(tmp_path, body))
    # and WITH the note it configures fine
    body += '\n[page]\ninjected_note = "MOVE LEGALITY: test note."\n'
    _page._configure(_cfg(tmp_path, body))
    assert _page.INJECTED_NOTE == 'MOVE LEGALITY: test note.'


def test_thievul_configs_reproduce_shipped_page_knobs():
    _page._configure(load_pair(_ROOT / 'pairs' / 'thievul_lickitung.toml'))
    assert _page.PUBLISH_SLUG_NAME == 'thievul-lickitung-robustness.html'
    assert _page.ARCHIVE_NOTE_TEXT.startswith('Archived 2026-08-17:')
    assert _page.PRIMARY_ARM == 'iwpr'
    assert _page.LABEL_ORDER == ['iwpr_bait', 'iwpr_nobait', 'nsiw_bait',
                                 'nsiw_nobait']
    _page._configure(load_pair(_ROOT / 'pairs' / 'thievul_lickilicky.toml'))
    assert _page.DENIAL_FILENAME == 'licki_denial.json'
    assert _page.METAWINS_FALLBACK_DIR == _ROOT / 'userdata' / 'thievul_licki'
    assert _page.OCCASION == 'the Thievul Community Day'
