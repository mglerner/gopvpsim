"""Verify the per-IV bitmask export variant round-trips to the full-list JSON.

The bitmask exporter (scripts/export_owned_breakdown_bundle.py) is a compact
mobile-bound alternative to the full opponent-string list: per-IV bits over the
dive's even-shield (opponent x scenario) cells plus a one-time `names` header.
This test decodes the bitmask via that header and asserts the reconstructed
per-IV drops exactly equal the full-list drops, on a real rendered dive.

The dive is a machine-local artifact, so both tests are ``local_artifacts``
and skip when it is absent (the repo convention for blob/artifact-backed
tests). Like the replay-blob tests, they look in this clone first and then in
a sibling ``gopvpsim`` checkout -- a working clone shares the machine's
rendered dives rather than duplicating them.
"""
import base64
import importlib.util
import json
import os

import pytest

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
DIVE_REL = os.path.join('userdata', 'website', 'altaria-great-league',
                        'index.html')
DIVE_DIRS = [ROOT, os.path.join(os.path.dirname(ROOT), 'gopvpsim')]


def require_dive():
    for d in DIVE_DIRS:
        p = os.path.join(d, DIVE_REL)
        if os.path.exists(p):
            return p
    pytest.skip(f"no rendered dive at {DIVE_REL} on this machine")


_spec = importlib.util.spec_from_file_location(
    'export_owned_breakdown_bundle',
    os.path.join(ROOT, 'scripts', 'export_owned_breakdown_bundle.py'))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _decode_masks(entry):
    """Reconstruct {iv: sorted(opp strings)} from a bitmask entry's header."""
    names = entry['names']
    nCells = len(names)
    out = {}
    for iv, b64 in entry['masks'].items():
        bits = base64.b64decode(b64)
        assert len(bits) == (nCells + 7) // 8
        out[iv] = sorted(names[c] for c in range(nCells)
                         if bits[c // 8] >> (c % 8) & 1)
    return out


@pytest.mark.local_artifacts
def test_bitmask_roundtrips_to_full_list():
    dive = require_dive()
    _, _, full = _mod.breakdown_from_dive(dive)
    _, _, bm = _mod.bitmask_from_dive(dive)

    # Oracle parity is only parity if there is something to compare.
    assert full['drops'], "positive control: this dive gives something up"

    # same set of IVs that give up something
    assert set(bm['masks']) == set(full['drops'])
    assert bm['rank1'] == full['rank1']

    # decoded bitmask == full opponent-string list, per IV
    recon = _decode_masks(bm)
    assert recon == full['drops']


@pytest.mark.local_artifacts
def test_bitmask_is_far_smaller_than_full_list():
    dive = require_dive()
    _, _, full = _mod.breakdown_from_dive(dive)
    _, _, bm = _mod.bitmask_from_dive(dive)
    full_size = len(json.dumps({'Great League': {'Altaria': full}},
                               separators=(',', ':')))
    bm_size = len(json.dumps({'Great League': {'Altaria': bm}},
                             separators=(',', ':')))
    # one species here; the full 15-species bundle is ~25.6 MB. The bitmask must
    # be far below that scale -- well under 1 MB even for this single species.
    assert bm_size < 1_000_000
    assert bm_size < full_size
