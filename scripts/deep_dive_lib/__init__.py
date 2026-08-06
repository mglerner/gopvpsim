"""Modules extracted from ``scripts/deep_dive.py``.

The DRY review 2026-08-05 entry 12 split (TODO.md "Split scripts/deep_dive.py",
review section H) moves the self-contained blocks out of the ~8k-line
orchestrator. ``deep_dive.py`` keeps a thin re-export shim for every moved
public name, so every existing importer -- the patch/analysis scripts, the
replay path, the tests -- keeps working unchanged.

Import order (no cycles): ``opponents`` -> ``sweep`` -> ``render``;
``categories`` is independent of all three.

Nothing is imported here on purpose: ``deep_dive_lib.sweep`` must be
importable on its own in a spawn-mode worker child (section G, invariant 22),
and an eager package import would drag the render/analysis chain into every
worker process.
"""
