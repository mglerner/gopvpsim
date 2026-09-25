"""Parity pin for the 2026-09-25 numpy clamp in score_pack.pack_u16.

pack_u16 used to clamp with ``[max(0, min(65535, int(v))) for v in values]``
and ``struct.pack``; it now truncates, clips and casts in numpy for flat
numeric arrays and keeps that per-value path for everything else. The
packed string is embedded in every dive page, so the output must be
byte-identical. ``_reference`` is the pre-change function verbatim.
"""
import base64
import gzip
import random
import struct

import numpy as np
import pytest

from tests.conftest import load_deep_dive

load_deep_dive()                                  # puts scripts/ on sys.path
from deep_dive_lib import score_pack              # noqa: E402


def _reference(values):
    clamped = [max(0, min(65535, int(v))) for v in values]
    raw = struct.pack(f'<{len(clamped)}H', *clamped)
    gz = gzip.compress(raw, compresslevel=9, mtime=0)
    return base64.b64encode(gz).decode('ascii')


_INT_EDGES = [-2**40, -65536, -1, 0, 1, 499, 500, 501, 65534, 65535, 65536,
              2**31, 2**40]
_FLOAT_EDGES = [-1e20, -65536.0, -1.0, -0.99, -0.5, -0.0, 0.0, 0.49, 0.5,
                0.99, 1.0, 500.5, 65534.99, 65535.0, 65535.5, 65535.99,
                65536.0, 70000.7, 1e20]


def _cases():
    rng = random.Random(20260925)
    ints = [rng.randint(-100000, 100000) for _ in range(5000)] + _INT_EDGES
    floats = ([rng.uniform(-1e5, 1e5) for _ in range(5000)]
              + [rng.uniform(-2, 2) for _ in range(500)] + _FLOAT_EDGES)
    rng.shuffle(ints)
    rng.shuffle(floats)
    scores = [rng.randint(0, 1000) for _ in range(20000)]   # a score column
    yield 'python ints', ints
    yield 'python floats', floats
    yield 'mixed int/float list', ints[:300] + floats[:300]
    yield 'score column list', scores
    yield 'int64 array', np.array(ints, dtype=np.int64)
    yield 'int32 array', np.array([v for v in ints if abs(v) < 2**31],
                                  dtype=np.int32)
    yield 'uint16 array', np.array(scores, dtype=np.uint16)
    yield 'uint64 array', np.array([0, 1, 65535, 65536, 2**63 + 5],
                                   dtype=np.uint64)
    yield 'float64 array', np.array(floats)
    yield 'float32 array', np.array(floats, dtype=np.float32)
    yield 'bool list', [True, False, True]
    yield 'bool array', np.array([True, False, False])
    yield 'numpy scalars in a list', [np.int64(70000), np.float64(-3.5),
                                      np.int16(7)]
    yield 'huge python int (object dtype)', [2**70, -2**70, 5]
    yield 'empty list', []
    yield 'empty array', np.array([], dtype=np.int64)


@pytest.mark.parametrize('label,values', list(_cases()),
                         ids=[c[0] for c in _cases()])
def test_matches_reference_bytes(label, values):
    want = _reference(values)
    assert score_pack.pack_u16(values) == want, label


def test_clamp_edges_are_exercised():
    """Anti-vacuity: the edge lists really hit both clamps and the
    truncation, so the parity above is not a comparison of mid-range
    values only."""
    raw = gzip.decompress(base64.b64decode(
        score_pack.pack_u16(_INT_EDGES + _FLOAT_EDGES)))
    out = struct.unpack(f'<{len(raw) // 2}H', raw)
    assert out.count(0) >= 10 and out.count(65535) >= 8
    assert 500 in out and 65534 in out


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf')])
def test_non_finite_fails_like_reference(bad):
    for values in ([1.0, bad], np.array([1.0, bad])):
        with pytest.raises((ValueError, OverflowError)) as want:
            _reference(values)
        with pytest.raises(want.type):
            score_pack.pack_u16(values)
