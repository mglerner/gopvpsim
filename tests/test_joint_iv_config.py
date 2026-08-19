"""joint_iv_config loader: schema validation + shipped-name reproduction.

The thievul pair configs are the kit's S1 acceptance anchors: their
grid_filename() outputs must equal the npz names the retired
thievul_licki_bake.py wrote, or the byte-identical rebuild target is
unreachable before any pipeline step even runs.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / 'scripts'))

from joint_iv_config import load_pair  # noqa: E402

PAIRS = _ROOT / 'pairs'


def test_thievul_lickilicky_reproduces_shipped_names():
    cfg = load_pair(PAIRS / 'thievul_lickilicky.toml')
    assert [g.label for g in cfg.grids] == [
        'iwpr_bait', 'nsiw_bait', 'iwpr_nobait', 'nsiw_nobait']
    assert cfg.grid_filename('iwpr_bait') == \
        'thievul_iwpr_bait__vs__lickilicky.npz'
    assert cfg.data_dir == _ROOT / 'userdata' / 'thievul_lickilicky'
    assert cfg.injected_moves == ('ICY_WIND',)
    assert cfg.opp_charged == ('BODY_SLAM', 'SHADOW_BALL')
    assert not cfg.focal_shadow and not cfg.opp_shadow


def test_thievul_lickitung_reproduces_shipped_names():
    cfg = load_pair(PAIRS / 'thievul_lickitung.toml')
    # 3 grids only -- the original lickitung bake never ran nsiw_nobait.
    assert [g.label for g in cfg.grids] == [
        'iwpr_bait', 'iwpr_nobait', 'nsiw_bait']
    assert cfg.grid_filename('nsiw_bait') == \
        'thievul_nsiw_bait__vs__lickitung.npz'
    assert cfg.data_dir == _ROOT / 'userdata' / 'thievul_licki'


def _write(tmp_path, body):
    p = tmp_path / 'pair.toml'
    p.write_text(body)
    return p


_VALID = '''
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
label = "m_bait"
focal_fast = "CHARM"
focal_charged = ["ICY_WIND", "SWIFT"]
bait = true
'''


def test_unknown_pair_key_rejected(tmp_path):
    bad = _VALID.replace('injected_moves = []',
                         'injected_moves = []\ninjected_mvoes = []')
    with pytest.raises(ValueError, match='unknown keys'):
        load_pair(_write(tmp_path, bad))


def test_missing_required_key_rejected(tmp_path):
    bad = _VALID.replace('opponent_fast = "ROLLOUT"\n', '')
    with pytest.raises(ValueError, match='missing keys'):
        load_pair(_write(tmp_path, bad))


def test_duplicate_grid_labels_rejected(tmp_path):
    bad = _VALID + '''
[[grids]]
label = "m_bait"
focal_fast = "CHARM"
focal_charged = ["ICY_WIND", "SWIFT"]
bait = false
'''
    with pytest.raises(ValueError, match='duplicate grid labels'):
        load_pair(_write(tmp_path, bad))


def test_step_sections_carried_verbatim(tmp_path):
    cfg = load_pair(_write(tmp_path, _VALID + '''
[assemble]
primary_grid = "m_bait"
'''))
    assert cfg.section('assemble') == {'primary_grid': 'm_bait'}
    assert cfg.section('denial') == {}
