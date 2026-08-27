"""build_joint_iv_page: the MIRROR MATCH note is MEASURED, not asserted.

Guard commit 8ebb642 (2026-08-24) replaced the mirror seat-antisymmetry
ASSERTION with a measurement: ``build_data`` now counts diagonal
even-shield wins and off-diagonal both-seat wins over each true-mirror
grid and picks the MIRROR MATCH wording from those counters.

Pre-guard behaviour (373bae8), recorded here as the pre-fix value: a
single diagonal even-shield win made the builder die with

    SystemExit: ABORT: <label> scenario 1-1: 1 mirror cell(s) won from
    BOTH seats -- seat bookkeeping bug; the MIRROR MATCH note would be
    false.

so the two asymmetry tests below fail against 373bae8 by aborting.

The zero-asymmetry branch is a BYTE pin: the shipped Lickilicky /
Wigglytuff / Corviknight / Quagsire-Shadow mirror pages carry the
round-1 (2026-08-20) wording verbatim, and the guard commit's whole
acceptance argument is that those pages rebuild unchanged. ``_ROUND1``
below is transcribed from 373bae8's source, i.e. from the shipped
wording, not from the post-guard code.

These call ``build_data`` -- the smallest real unit that contains both
the counting and the wording choice -- on tiny synthetic ``won`` arrays,
with the disk/gamemaster-backed helpers around it stubbed out.
"""
import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
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


# Byte pin, transcribed from 373bae8 scripts/build_joint_iv_page.py
# (the wording the shipped round-1 mirror pages carry).
_ROUND1 = (
    'MIRROR MATCH. Reading rules: (1) identical builds -- the '
    'diagonal, and any two spreads with byte-identical stats -- '
    'fight to an exact 500 tie at even shields, which this page '
    'counts as a LOSS for both seats (the standing tie '
    'convention); with a shield advantage the diagonal is a '
    'real, asymmetric fight, not a coin flip. (2) Cell (i, j) '
    'and cell (j, i) are one fight read from the two seats; '
    'this build verified no cell is a win from both seats. '
    '(3) Exact charge-priority ties (equal attack values) '
    'resolve charged-move ORDER by seat -- player 0 first, the '
    'engine\'s documented PROP-1 rule; on this data that '
    'ordering produced only ties, never a seat-dependent win.')

_MIRROR_TOML = '''
[pair]
league = "great"
focal = "Lickilicky"
focal_shadow = false
focal_slug = "lickilicky"
opponent = "Lickilicky"
opponent_shadow = false
opponent_slug = "lickilicky"
opponent_fast = "LICK"
opponent_charged = ["BODY_SLAM", "SHADOW_BALL"]
data_dir = "userdata/joint_iv/mirror"
injected_moves = []

[[grids]]
label = "bssb_bait"
focal_fast = "LICK"
focal_charged = ["BODY_SLAM", "SHADOW_BALL"]
bait = true
'''

_LABEL = 'bssb_bait'


def _fake_spec(data_dir):
    return {
        'data_dir': str(data_dir),
        'focal': 'Lickilicky',
        'opponent': 'Lickilicky',
        'focal_display': 'Lickilicky',
        'opp_display': 'Lickilicky',
        'labels': [_LABEL],
        'files': {_LABEL: 'grid.npz'},
        'pretty': {_LABEL: 'Lick / Body Slam + Shadow Ball, baiting'},
        'collection_species': ['Lickilicky'],
        'analyzed_species': ['Lickilicky'],
        'threshold_species': ['Lickilicky'],
        'grid_species': ['Lickilicky', 'Lickilicky'],
        'opp_moveset': 'Lickilicky Lick / Body Slam + Shadow Ball',
        'out_name': 'mirror.html',
    }


def _fake_iv_table(species, shadow=False):
    return {
        'species': species,
        'ivs': [[0, 0, 0], [1, 1, 1]],
        'level': [40.0, 40.0],
        'cp': [1500, 1500],
        'atk': [1.0, 1.0],
        'def': [1.0, 1.0],
        'hp': [100, 100],
    }


def _mirror_note(monkeypatch, tmp_path, won):
    """Run build_data over one synthetic grid; return notes[0]."""
    _page._configure(load_pair(tmp_path / 'pair.toml'))
    assert _page._is_true_mirror(_page.CFG), 'fixture must be a true mirror'

    monkeypatch.setitem(sys.modules, 'sweep_cache', types.SimpleNamespace(
        gamemaster_hash=lambda: 'gm-test'))
    monkeypatch.setattr(_page, 'load_manifest', lambda d: {'total_sims': 0})
    monkeypatch.setattr(_page, 'dataset_spec',
                        lambda manifest, data_dir=None: _fake_spec(data_dir))
    monkeypatch.setattr(_page, 'iv_table', _fake_iv_table)
    monkeypatch.setattr(_page, 'load_grid', lambda data_dir, label, spec: (
        won, {'won_packed': np.packbits(won, axis=None, bitorder='big')}))
    monkeypatch.setattr(_page, 'check_axis_order',
                        lambda z, focal_tbl, opp_tbl, label: None)
    monkeypatch.setattr(_page, 'load_meta_wins',
                        lambda *a, **k: None)
    monkeypatch.setattr(_page, 'load_json', lambda p: None)
    monkeypatch.setattr(_page, 'move_legality', lambda spec, grids_meta: {})
    monkeypatch.setattr(_page, 'default_moveset_label',
                        lambda spec, grids_meta: (None, None))
    monkeypatch.setattr(_page, 'build_collection', lambda spec: {})

    data, _missing, _spec_out = _page.build_data(
        tmp_path, allow_missing=True, won_labels=set(), won_scenarios=(),
        breakpoints_path=tmp_path / 'breakpoints.json',
        reco_path=tmp_path / 'reco.json')
    notes = data['meta']['notes']
    assert notes and notes[0].startswith('MIRROR MATCH'), notes[:1]
    return notes[0]


@pytest.fixture
def mirror_dir(tmp_path):
    (tmp_path / 'pair.toml').write_text(_MIRROR_TOML)
    return tmp_path


def test_diagonal_even_shield_win_selects_measured_wording(
        monkeypatch, mirror_dir):
    """One diagonal 1-1 win -> the asymmetric note, counted 1 of 6.

    Pre-fix (373bae8) this was a hard SystemExit ABORT ('1 mirror
    cell(s) won from BOTH seats'), so no note existed at all.
    """
    won = np.zeros((2, 2, 9), dtype=bool)
    won[0, 0, 4] = True          # diagonal cell, scenario 1-1 (even)
    note = _mirror_note(monkeypatch, mirror_dir, won)

    assert note.startswith(
        'MIRROR MATCH -- read this before trusting any cell.')
    # 1 diagonal even-shield win out of 3 even scenarios x 2 diagonal cells.
    assert "even shields the row seat's line wins 1 of 6 " \
           'identical-build fights on this page' in note
    assert note != _ROUND1
    assert 'verified no cell is a win from both seats' not in note


def test_off_diagonal_both_seat_win_selects_measured_wording(
        monkeypatch, mirror_dir):
    """The both-seat counter alone also flips the wording.

    Cell (0, 1) won at 0-1 shields and its seat swap (1, 0) at 1-0 is the
    same fight recorded as a win twice. Pre-fix (373bae8) that aborted;
    post-guard it is measured, with zero on the diagonal counter.
    """
    won = np.zeros((2, 2, 9), dtype=bool)
    won[0, 1, 1] = True          # scenario 0-1
    won[1, 0, 3] = True          # scenario 1-0, the seat swap
    note = _mirror_note(monkeypatch, mirror_dir, won)

    assert note.startswith(
        'MIRROR MATCH -- read this before trusting any cell.')
    assert "even shields the row seat's line wins 0 of 6 " \
           'identical-build fights on this page' in note


def test_all_zero_grid_reproduces_round1_wording_byte_identically(
        monkeypatch, mirror_dir):
    """The shipped round-1 mirror pages pin this string byte-for-byte."""
    won = np.zeros((2, 2, 9), dtype=bool)
    assert _mirror_note(monkeypatch, mirror_dir, won) == _ROUND1


def test_odd_shield_diagonal_win_is_not_counted_as_even(
        monkeypatch, mirror_dir):
    """Only scenarios 0-0 / 1-1 / 2-2 feed the diagonal counter.

    Positive control for the [0, 4, 8] selector: a diagonal win at 0-1
    shields is a real asymmetric fight, not evidence about identical
    builds, so it must leave the round-1 wording in place.
    """
    won = np.zeros((2, 2, 9), dtype=bool)
    won[0, 0, 1] = True          # diagonal cell, scenario 0-1 (odd)
    assert _mirror_note(monkeypatch, mirror_dir, won) == _ROUND1


def test_diagonal_seat_swap_pair_is_not_a_both_seat_win(
        monkeypatch, mirror_dir):
    """Diagonal cells are excluded from the both-seat counter.

    A diagonal cell won at 0-1 AND at its seat swap 1-0 is the same
    identical-build matchup fought under the two asymmetric shield
    starts -- two genuinely different fights, not a seat bookkeeping
    contradiction.  The ``np.fill_diagonal`` exclusion inside the
    counter is what keeps this input on the round-1 wording; deleting
    it flips the note to the asymmetric branch (adversarial-review
    mutation M5, 2026-08-27).
    """
    won = np.zeros((2, 2, 9), dtype=bool)
    won[0, 0, 1] = True          # diagonal cell, scenario 0-1
    won[0, 0, 3] = True          # diagonal cell, scenario 1-0 (seat swap)
    assert _mirror_note(monkeypatch, mirror_dir, won) == _ROUND1
