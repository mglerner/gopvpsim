"""Verify the per-IV bitmask export variant round-trips to the full-list JSON.

The bitmask exporter (scripts/export_owned_breakdown_bundle.py) is a compact
mobile-bound alternative to the full opponent-string list: per-IV bits over the
dive's even-shield (opponent x scenario) cells plus a one-time `names` header.
This test decodes the bitmask via that header and asserts the reconstructed
per-IV drops exactly equal the full-list drops, on a real rendered dive.
"""
import base64
import importlib.util
import json
import os

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
DIVE = os.path.join(ROOT, 'userdata', 'website', 'altaria-great-league',
                    'index.html')

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


def test_bitmask_roundtrips_to_full_list():
    assert os.path.exists(DIVE), f"missing dive fixture: {DIVE}"
    _, _, full = _mod.breakdown_from_dive(DIVE)
    _, _, bm = _mod.bitmask_from_dive(DIVE)

    # same set of IVs that give up something
    assert set(bm['masks']) == set(full['drops'])
    assert bm['rank1'] == full['rank1']

    # decoded bitmask == full opponent-string list, per IV
    recon = _decode_masks(bm)
    assert recon == full['drops']


def test_bitmask_is_far_smaller_than_full_list():
    _, _, full = _mod.breakdown_from_dive(DIVE)
    _, _, bm = _mod.bitmask_from_dive(DIVE)
    full_size = len(json.dumps({'Great League': {'Altaria': full}},
                               separators=(',', ':')))
    bm_size = len(json.dumps({'Great League': {'Altaria': bm}},
                             separators=(',', ':')))
    # one species here; the full 15-species bundle is ~25.6 MB. The bitmask must
    # be far below that scale -- well under 1 MB even for this single species.
    assert bm_size < 1_000_000
    assert bm_size < full_size
