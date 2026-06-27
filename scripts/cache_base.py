"""Shared foundation for gopvpsim's disk caches.

This module owns the pieces the per-opponent sweep cache, the ML envelope
cache, and the slayer cache would otherwise each re-implement: atomic
multi-plane column storage, and (added in later phases) the per-entry
engine stamp + predicate invalidation and the version-aware GC.

The goal (Michael 2026-06-27): a feature added here — an energy plane,
a new invalidation predicate, a GC policy — lands for every cache at once,
so cache work is never re-done per consumer. See
``docs/design/2026-06-27_cache_rework_design.md``.

A "column" is a small set of NAMED PLANES (e.g. ``{'score': float64,
'energy': uint8}``) sharing one shape ``(n_ivs, n_scenarios)``, persisted
as a single ``.npz``. Storing planes by name (rather than a bare array)
lets one consumer keep just ``score`` while another keeps the full metric
set, with no format fork.
"""
import os
from pathlib import Path

import numpy as np


def write_planes(path, planes):
    """Atomically write a dict of named ndarrays to ``path`` as ``.npz``.

    Atomic (tmp + ``os.replace``) so a crash or a concurrent reader never
    sees a truncated archive. Best-effort: any I/O failure is swallowed by
    the caller's try/except (caches degrade to a miss / no-store).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    # np.savez appends '.npz' to a *name* but not to a file handle, so write
    # through an explicit handle to keep the path we os.replace from.
    with open(tmp, 'wb') as f:
        np.savez(f, **planes)
    os.replace(tmp, path)


def read_planes(path):
    """Load a ``.npz`` written by ``write_planes`` into a plain dict of
    ndarrays, or return ``None`` if the file is absent/corrupt.

    Returns a materialized dict (not the lazy ``NpzFile``) so the file
    handle is closed before we return — important on a long-lived cache.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        with np.load(path) as npz:
            return {k: npz[k] for k in npz.files}
    except Exception:
        return None
