#!/usr/bin/env python
"""Worlds 2026 outcome-plane storage: npz planes + a stamped manifest.

Plan: docs/worlds_prep_plan.md ("Guardrails (as code)"). Planes live in
``worlds/planes/*.npz`` -- NEVER the sweep disk cache -- with ONE
manifest (``worlds/planes/manifest.json``, tracked in git as the
provenance record; the npz blobs are gitignored). Stamps are
manifest-GLOBAL, a deliberate divergence from the sweep cache's
per-column design: the sweep cache is 42GB, multi-consumer and must
hold mixed vintages; Worlds planes are small, single-consumer and
season-scoped, and the plan declares a hash mismatch = full re-bake by
design. One global stamp with REFUSE-on-mismatch cannot serve a
mixed-vintage plane.

Write guards (hard failures, not conventions):

* only ``.npz`` / ``.json`` under the planes dir, path-contained -- and
  ``*_great.toml`` is named explicitly because that glob is the iOS
  threshold-bundler's collision surface (topn_cup_filter_plan.md);
* ``mechanics`` must be the literal ``'legacy'`` (Worlds is confirmed
  old-system; an accidental ``'new'`` bake would otherwise be invisible);
* the gamemaster stamp must be real (sweep_cache.gamemaster_hash()
  degrades to the literal ``'no-gamemaster'`` on a missing cache file --
  never stamp fake provenance);
* scores must fit the uint16 [0, 1000] pvpoke range (the plane stores
  the RAW score; the won-plane is the win/loss authority and margin is
  derived at read time via the ``margin`` helper, which widens before
  subtracting -- a signed "margin" plane in uint16, or a bare
  ``score - 500`` on the raw array, wraps every loss).

The won plane is ``np.packbits`` with explicit ``bitorder='big'`` and
the shape stored both in the manifest and INSIDE the npz (packbits pads
to whole bytes; ``unpackbits(count=...)`` + the stored shape round-trip
exactly, and a Tier-1 shape happens to be divisible by 8, so an
inferred shape would fail only silently).

``worlds_code_hash()`` closes the gap sweep_cache's CACHE_VERSION bumps
exist for: the plane-producing code lives in ``scripts/``, OUTSIDE the
engine source hash, so it gets its own source stamp; a producer edit
refuses to extend an existing manifest exactly like an engine edit.
"""
import fnmatch
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
PLANES_DIR = REPO / 'worlds' / 'planes'
META_TOML = REPO / 'worlds' / 'meta.toml'

sys.path.insert(0, str(REPO / 'scripts'))

from cache_base import write_planes as _write_npz, read_planes as _read_npz
from sweep_cache import engine_hash, gamemaster_hash, write_sidecar

MANIFEST_SCHEMA = 1
# Manual escape hatch for semantic changes the source hash can't see
# (e.g. a reinterpretation of an existing array).
WORLDS_PLANE_VERSION = 1
MECHANICS = 'legacy'

# The plane-producing sources. A byte change in any of these stamps new
# manifests differently and REFUSES to extend old ones (see module
# docstring). Explicit tuple so a rename fails loud in the tests.
# Boundary (2026-08-10 review): deep_dive_lib/sweep.py is IN -- it builds
# every simmed BattlePokemon (BattleSide/make_battle_pokemon/
# group_ivs_by_stat_profile) yet sits outside the engine hash;
# worlds_tier0.py is OUT -- it never runs in the plane path (a render-time
# consumer; its vintage gets stamped with the rendered products, session
# 4), so a tier0 edit must not cold a 1,860-plane bake.
_WORLDS_SOURCE_FILES = (
    REPO / 'scripts' / 'worlds_planes.py',
    REPO / 'scripts' / 'worlds_bake.py',
    REPO / 'scripts' / 'deep_dive_lib' / 'robustness.py',
    REPO / 'scripts' / 'deep_dive_lib' / 'sweep.py',
)


def worlds_code_hash():
    """md5 over the plane-producing sources, in the tuple's fixed order."""
    h = hashlib.md5()
    for p in _WORLDS_SOURCE_FILES:
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def entry_sim_digest(entry):
    """Digest of the SIM-RELEVANT fields of one meta entry -- the only
    meta.toml content a plane depends on. Usage percentages, badges,
    prose reasons and the `generated` stamp are deliberately excluded:
    hashing the whole file (the original design) turned every prose
    edit or Dracoviz usage re-poll into a full 465-pair cold re-bake,
    the same over-broad-stamp mistake the sweep cache's v7 gamemaster
    narrowing fixed (2026-08-10 review, HIGH)."""
    blob = json.dumps([entry['species_id'], entry['species'],
                       bool(entry['shadow']), entry['fast_move_id'],
                       list(entry['charged_move_ids'])])
    return hashlib.md5(blob.encode()).hexdigest()[:12]


def meta_sim_digests(entries):
    return {e['species_id']: entry_sim_digest(e) for e in entries}


def meta_delta(manifest, entries):
    """(changed, removed, added) species_ids between the manifest's
    recorded meta and the current entries -- computed from the actual
    sim-relevant delta, migrate_cache-style. A purely-ADDED delta is
    extendable (bake exactly the new pairs); changed/removed entries
    invalidate planes and must refuse."""
    old = (manifest or {}).get('meta_entries', {})
    new = meta_sim_digests(entries)
    changed = sorted(s for s in old if s in new and new[s] != old[s])
    removed = sorted(s for s in old if s not in new)
    added = sorted(s for s in new if s not in old)
    return changed, removed, added


def out_path(name, planes_dir=PLANES_DIR):
    """The ONLY path constructor for plane artifacts. Hard-fails on the
    known hazards instead of trusting callers (see module docstring)."""
    planes_dir = Path(planes_dir)
    p = planes_dir / name
    if fnmatch.fnmatch(p.name, '*_great.toml'):
        raise ValueError(
            f'{name!r} matches *_great.toml -- the iOS threshold bundler '
            f'globs that pattern (docs/topn_cup_filter_plan.md); a Worlds '
            f'artifact must never collide with it')
    if p.suffix not in ('.npz', '.json'):
        raise ValueError(f'{name!r}: only .npz/.json belong under planes/')
    resolved = p.resolve()
    if planes_dir.resolve() not in resolved.parents:
        raise ValueError(f'{name!r} escapes the planes dir ({resolved})')
    return p


def pack_won(won):
    """bool array -> (packed uint8, shape) with pinned bitorder."""
    won = np.asarray(won)
    assert won.dtype == np.bool_, won.dtype
    return np.packbits(won, axis=None, bitorder='big'), won.shape


def unpack_won(packed, shape):
    """Exact inverse of pack_won; returns bool dtype (uint8 '~' is a
    footgun: ~1 == 254).

    The byte-count check is OURS: numpy 2.4's ``unpackbits(count=n)``
    silently fabricates zero bits when ``n`` exceeds the stored bits
    (measured 2026-08-10), so a wrong shape would otherwise read as
    all-losses padding instead of failing."""
    n = int(np.prod(shape))
    if packed.size != (n + 7) // 8:
        raise ValueError(f'packed size {packed.size} bytes does not match '
                         f'shape {tuple(shape)} ({n} bits)')
    return (np.unpackbits(packed, count=n, bitorder='big')
            .reshape(shape).astype(bool))


def content_md5(planes):
    """Order-independent content hash over a dict of named arrays."""
    h = hashlib.md5()
    for name in sorted(planes):
        arr = np.ascontiguousarray(planes[name])
        h.update(f'{name}|{arr.dtype.str}|{arr.shape}|'.encode())
        h.update(arr.tobytes())
    return h.hexdigest()


def plane_arrays(won, score, focal_ivs, focal_levels, opp_ivs, opp_levels,
                 scenarios, top512_mask, atkband_mask):
    """Assemble + validate the npz dict for one (pair, direction, bait).

    ``won`` is the authority for win/loss (packed); ``score`` is the raw
    focal pvpoke_score in [0, 1000] (signed margin comes from the
    ``margin`` helper at read time, never bare uint16 subtraction). Shapes: won/score (n_spreads, n_cohort, n_scenarios).
    """
    won = np.asarray(won)
    score = np.asarray(score, dtype=np.uint16)
    if score.shape != won.shape:
        raise ValueError(f'shape mismatch: won {won.shape} score {score.shape}')
    if score.size and int(score.max()) > 1000:
        raise ValueError(f'score out of pvpoke range: max {int(score.max())}')
    packed, shape = pack_won(won)
    arrs = {
        'won_packed': packed,
        'won_shape': np.asarray(shape, dtype=np.int64),
        'score': score,
        'focal_ivs': np.asarray(focal_ivs, dtype=np.int64),
        'focal_levels': np.asarray(focal_levels, dtype=np.float64),
        'opp_ivs': np.asarray(opp_ivs, dtype=np.int64),
        'opp_levels': np.asarray(opp_levels, dtype=np.float64),
        'scenarios': np.asarray(scenarios, dtype=np.int64),
        'top512_mask': np.asarray(top512_mask, dtype=bool),
        'atkband_mask': np.asarray(atkband_mask, dtype=bool),
    }
    n = shape[1] if len(shape) == 3 else 0
    for key in ('opp_ivs', 'opp_levels', 'top512_mask', 'atkband_mask'):
        if len(arrs[key]) != n:
            raise ValueError(f'{key} length {len(arrs[key])} != cohort {n}')
    return arrs


def write_plane(name, arrs, planes_dir=PLANES_DIR):
    """Atomic npz write through the guarded path constructor."""
    _write_npz(out_path(name, planes_dir), arrs)


def read_plane(name, planes_dir=PLANES_DIR):
    """Load a plane; returns the dict with ``won`` unpacked to bool
    (authority), plus every stored array. None when absent/corrupt."""
    raw = _read_npz(out_path(name, planes_dir))
    if raw is None:
        return None
    raw['won'] = unpack_won(raw['won_packed'], tuple(raw['won_shape']))
    return raw


def margin(score):
    """Signed win margin (score - 500) from the uint16 raw-score plane.

    THE read recipe: ``plane['score'] - 500`` on the raw uint16 array
    wraps every loss to ~65k (2026-08-10 review) -- widen first. Never
    re-derive win/loss from this; ``won`` is the authority."""
    return np.asarray(score).astype(np.int32) - 500


def fresh_stamps():
    """The global manifest stamps for a NEW bake. Hard-fails rather than
    stamping fake provenance."""
    gm = gamemaster_hash()
    if gm == 'no-gamemaster':
        raise SystemExit('ABORT: no cached gamemaster.json -- refusing to '
                         'stamp a manifest with fake provenance')
    return {
        'schema': MANIFEST_SCHEMA,
        'plane_version': WORLDS_PLANE_VERSION,
        'mechanics': MECHANICS,
        'engine': engine_hash(),
        'gamemaster': gm,
        'worlds_code': worlds_code_hash(),
    }


# Meta changes are NOT a stamp: they are diffed per-entry (meta_delta) so
# an additive meta row extends the manifest instead of refusing.
STAMP_KEYS = ('plane_version', 'mechanics', 'engine', 'gamemaster',
              'worlds_code')


def stamp_mismatches(manifest):
    """[(key, manifest_value, current_value), ...] -- empty = extendable."""
    cur = fresh_stamps()
    return [(k, manifest.get(k), cur[k])
            for k in STAMP_KEYS if manifest.get(k) != cur[k]]


def manifest_path(planes_dir=PLANES_DIR):
    return out_path('manifest.json', planes_dir)


def load_manifest(planes_dir=PLANES_DIR):
    p = manifest_path(planes_dir)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def save_manifest(manifest, planes_dir=PLANES_DIR):
    """Atomic manifest write (sweep_cache.write_sidecar: tmp+replace).
    Ordering contract with write_plane: npz FIRST, manifest entry
    SECOND -- the manifest is the index of record, so the safe crash
    residue is an orphan npz (overwritten next run), never an entry
    pointing at a missing file."""
    Path(planes_dir).mkdir(parents=True, exist_ok=True)
    write_sidecar(manifest_path(planes_dir), manifest)


def pair_key(focal_id, opp_id, bait):
    return f'{focal_id}|{opp_id}|{"bait" if bait else "nobait"}'


def plane_filename(focal_id, opp_id, bait):
    return f'{focal_id}__vs__{opp_id}__{"bait" if bait else "nobait"}.npz'


def expected_tier1_keys(meta_entries):
    """The full Tier-1 key set from the meta: every ordered direction of
    every unordered pair, x both bait modes (C(31,2)=465 pairs -> 1860
    keys). Derived from the same meta the driver bakes from, so a
    coverage check may compare with == (testing-policy exception)."""
    ids = [e['species_id'] for e in meta_entries]
    if len(set(ids)) != len(ids):
        raise ValueError('meta species_id values are not unique')
    keys = set()
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            for focal, opp in ((a, b), (b, a)):
                for bait in (True, False):
                    keys.add(pair_key(focal, opp, bait))
    return keys


def is_baked(manifest, key, planes_dir=PLANES_DIR):
    """Idempotent-skip predicate: manifest entry present AND its npz
    exists (a crash between npz and manifest, or a manual rm, must
    re-bake, not skip)."""
    entry = (manifest or {}).get('entries', {}).get(key)
    if entry is None:
        return False
    return out_path(entry['file'], planes_dir).exists()
