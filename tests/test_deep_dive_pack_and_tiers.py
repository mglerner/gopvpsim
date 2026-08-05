"""Regression tests for two DRY drop-ins in ``scripts/deep_dive.py``
(DRY review 2026-08-05 entry 12, sub-items D14 and js-py-score-pack
first half):

* ``_pack_u16`` -- one encoder for the score grid and the energy grid.
  Pinned against hand-computed little-endian bytes plus the run-to-run
  determinism (``mtime=0``) the replay-vs-original diffing depends on.
* ``_recompute_tier_assignments`` -- the inline clone that used to sit
  in ``_generate_narrative_for_moveset`` now routes through the helper.
  Pinned against the frozen pre-fix inline implementation.
"""
import base64
import gzip
import importlib.util
import random
import re
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"
_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)


def _unpack(blob):
    """Inverse of _pack_u16: base64 -> gunzip -> list of uint16."""
    raw = gzip.decompress(base64.b64decode(blob))
    return list(struct.unpack(f'<{len(raw) // 2}H', raw))


# --------------------------------------------------------------------
# _pack_u16
# --------------------------------------------------------------------

def test_pack_u16_hand_computed_bytes():
    # 0 -> 00 00, 1 -> 01 00, 258 -> 02 01, 65535 -> ff ff (little-endian)
    blob = deep_dive._pack_u16([0, 1, 258, 65535])
    raw = gzip.decompress(base64.b64decode(blob))
    assert raw == b'\x00\x00\x01\x00\x02\x01\xff\xff'


def test_pack_u16_round_trip():
    values = [0, 7, 500, 1234, 65535, 42]
    assert _unpack(deep_dive._pack_u16(values)) == values


def test_pack_u16_clamps_and_truncates():
    # Below range clamps to 0, above range clamps to 65535, floats go
    # through int() (truncation toward zero), which is what the pre-DRY
    # inline encoders did.
    packed = deep_dive._pack_u16([-1, -65535, 65536, 70000, 3.9, 500.2])
    assert _unpack(packed) == [0, 0, 65535, 65535, 3, 500]


def test_pack_u16_empty():
    assert _unpack(deep_dive._pack_u16([])) == []


def test_pack_u16_is_deterministic():
    """mtime=0 keeps the gzip header timestamp out of the HTML.

    Without it, byte-identical data produced different HTML run-to-run
    (arc S4, caught by replay-vs-original diffing).
    """
    values = [1, 2, 3, 4, 5]
    first = deep_dive._pack_u16(values)
    second = deep_dive._pack_u16(values)
    assert first == second
    # Bytes 4..8 of the gzip header are MTIME; assert they are zeroed
    # rather than trusting the equality above (two calls in the same
    # second would pass that even with a live timestamp).
    header = base64.b64decode(first)
    assert header[4:8] == b'\x00\x00\x00\x00'


def test_only_one_u16_encoder_left_in_deep_dive():
    """DRY tripwire: the score grid and the energy grid share one encoder."""
    src = DEEP_DIVE_PATH.read_text()
    packs = re.findall(r"struct\.pack\(f?'<\{[^']*\}H'", src)
    assert len(packs) == 1, f"expected one u16 encoder, found {len(packs)}"


# --------------------------------------------------------------------
# _recompute_tier_assignments (D14)
# --------------------------------------------------------------------

def _frozen_inline_assignments(data_obj, plot_tiers):
    """The pre-D14 inline clone from _generate_narrative_for_moveset,
    frozen here as the oracle for the drop-in."""
    _n = data_obj['nIvs']
    _iv_tiers = [-1] * _n
    _iv_all_tiers = [[] for _ in range(_n)]
    for _ti, _t in enumerate(plot_tiers):
        _ac = _t.get('attack', 0) or 0
        _dc = _t.get('defense', 0) or 0
        _hc = _t.get('stamina', 0) or 0
        for _iv in range(_n):
            meets = True
            if _ac > 0 and data_obj['ivAtk'][_iv] < _ac:
                meets = False
            if _dc > 0 and data_obj['ivDef'][_iv] < _dc:
                meets = False
            if _hc > 0 and data_obj['ivHp'][_iv] < _hc:
                meets = False
            if meets:
                _iv_all_tiers[_iv].append(_ti)
                if _iv_tiers[_iv] < 0:
                    _iv_tiers[_iv] = _ti
    return _iv_tiers, _iv_all_tiers


def _tiny_data_obj():
    return {
        'nIvs': 4,
        'ivAtk': [0, 15, 10, 15],
        'ivDef': [0, 15, 12, 5],
        'ivHp': [0, 15, 14, 15],
    }


def test_recompute_tier_assignments_hand_computed():
    data_obj = _tiny_data_obj()
    plot_tiers = [
        {'name': 'Tight', 'attack': 14, 'defense': 14, 'stamina': 14},
        {'name': 'Atk only', 'attack': 10},
        {'name': 'General'},
    ]
    deep_dive._recompute_tier_assignments(data_obj, plot_tiers)
    # iv0 (0/0/0): only the no-cutoff tier. iv1 (15/15/15): all three.
    # iv2 (10/12/14): fails Tight on defense, meets Atk only. iv3
    # (15/5/15): fails Tight on defense, meets Atk only.
    assert data_obj['ivAllTiers'] == [[2], [0, 1, 2], [1, 2], [1, 2]]
    assert data_obj['ivTiers'] == [2, 0, 1, 1]


def test_recompute_matches_frozen_inline_clone():
    rng = random.Random(20260805)
    for _ in range(25):
        n = rng.randint(1, 40)
        data_obj = {
            'nIvs': n,
            'ivAtk': [rng.randint(0, 15) for _ in range(n)],
            'ivDef': [rng.randint(0, 15) for _ in range(n)],
            'ivHp': [rng.randint(0, 15) for _ in range(n)],
        }
        plot_tiers = []
        for _t in range(rng.randint(0, 4)):
            plot_tiers.append({
                'attack': rng.choice([0, None, 8, 12, 15]),
                'defense': rng.choice([0, None, 8, 13]),
                'stamina': rng.choice([0, None, 10, 15]),
            })
        want_tiers, want_all = _frozen_inline_assignments(data_obj, plot_tiers)
        deep_dive._recompute_tier_assignments(data_obj, plot_tiers)
        assert data_obj['ivTiers'] == want_tiers
        assert data_obj['ivAllTiers'] == want_all


def test_narrative_no_longer_carries_an_inline_clone():
    """DRY tripwire for D14: one tier-assignment loop, in the helper."""
    src = DEEP_DIVE_PATH.read_text()
    assert src.count("_iv_all_tiers[") == 0
    assert src.count("iv_all_tiers[iv].append(ti)") == 1
