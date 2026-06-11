"""
Per-opponent-column disk cache for IV sweep sims.

A sweep's result decomposes into independent per-opponent score columns
(``per_opp[(si, oi)]``), so the cache is keyed PER OPPONENT COLUMN
rather than per whole sweep (Michael's 2026-06-10 design decision, arc
S4). Pool edits become incremental: adding a mon to a 60-opponent pool
sims 1 column, removing/reordering opponents is all-hits, and an
unchanged dive command re-run is all-columns-hit.

Key structure:
  focal side  - species, league, shadow, moveset, iv_floor, shield
                scenarios, bait mode, gamemaster content hash, engine
                source hash, CACHE_VERSION
  column side - opponent species, shadow, resolved IVs, level, moveset

The gamemaster hash makes rankings/data drift safe: opponent IVs and
movesets are resolved BEFORE the key is built, so a rankings refresh
that changes resolution produces a different column key (miss), while
move-stat/base-stat changes invalidate via the gamemaster hash.

Columns store raw float64 per-IV scores in canonical iv_meta order,
shape (n_ivs, n_scenarios) — ~300KB per column at 4096 IVs x 9
scenarios — so replayed analysis is bit-identical to a fresh sim.
S3's signature dedup is upstream and invisible here (columns hold
post-fan-out scores).

Layout on disk:
  ~/.cache/gopvpsim/sweep/<species>_<league>_<focalhash12>/
      meta.json            human-readable focal-key fields
      <colhash16>.npy      one score column
      <colhash16>.json     human-readable column-key fields
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np

# Manual escape hatch: bump on any battle-behavior change that the
# engine source hash somehow misses (it shouldn't — see _ENGINE_FILES).
CACHE_VERSION = 1
CACHE_DIR = Path.home() / '.cache' / 'gopvpsim' / 'sweep'

# Engine sources whose content participates in the focal key. Any edit
# (even a comment) invalidates the cache — spurious invalidation is the
# safe direction, and it removes the "forgot to bump the version"
# failure mode for behavior changes.
_ENGINE_FILES = ('battle.py', '_dp_jit.py', 'moves.py', 'formchange.py',
                 'pokemon.py')

_ENGINE_HASH = None
_GAMEMASTER_HASH = None


def engine_hash():
    """Hash of the battle-engine source files (memoized per process)."""
    global _ENGINE_HASH
    if _ENGINE_HASH is None:
        import gopvpsim
        pkg = Path(gopvpsim.__file__).parent
        h = hashlib.md5()
        for name in _ENGINE_FILES:
            h.update((pkg / name).read_bytes())
        _ENGINE_HASH = h.hexdigest()[:12]
    return _ENGINE_HASH


def gamemaster_hash():
    """Hash of the cached gamemaster.json content (memoized per process).

    load_gamemaster() always round-trips through this file (fresh fetches
    are written before use), so the file content matches the data every
    sweep actually ran on.
    """
    global _GAMEMASTER_HASH
    if _GAMEMASTER_HASH is None:
        from gopvpsim.data import CACHE_DIR as DATA_CACHE_DIR
        p = DATA_CACHE_DIR / 'gamemaster.json'
        if p.exists():
            _GAMEMASTER_HASH = hashlib.md5(p.read_bytes()).hexdigest()[:12]
        else:
            _GAMEMASTER_HASH = 'no-gamemaster'
    return _GAMEMASTER_HASH


def _key_hash(fields, n=16):
    """Stable hash of a JSON-serializable key dict."""
    blob = json.dumps(fields, sort_keys=True, separators=(',', ':'))
    return hashlib.md5(blob.encode()).hexdigest()[:n]


def focal_key_fields(species, league, shadow, fast_id, charged_ids,
                     iv_floor, shield_scenarios, bait_mode):
    """Focal-side key dict shared by every column of one sweep."""
    return {
        'v': CACHE_VERSION,
        'species': species,
        'league': league,
        'shadow': bool(shadow),
        'fast': fast_id,
        'charged': list(charged_ids),
        'iv_floor': list(iv_floor) if iv_floor else None,
        'scenarios': [[s0, s1] for s0, s1 in shield_scenarios],
        'bait': bait_mode,
        'engine': engine_hash(),
        'gamemaster': gamemaster_hash(),
    }


def column_key_fields(opp_species, opp_shadow, opp_ivs, opp_level,
                      opp_fast_id, opp_charged_ids):
    """Column-side key dict for one resolved opponent."""
    return {
        'species': opp_species,
        'shadow': bool(opp_shadow),
        'ivs': list(opp_ivs),
        'level': opp_level,
        'fast': opp_fast_id,
        'charged': list(opp_charged_ids),
    }


class SweepCache:
    """Disk cache of per-opponent sweep score columns. Best-effort:
    any I/O failure degrades to a miss / silent no-store."""

    def __init__(self, focal_fields):
        species_slug = focal_fields['species'].replace(' ', '_').replace('(', '').replace(')', '')
        self.dir = (Path(CACHE_DIR) /
                    f"{species_slug}_{focal_fields['league']}_{_key_hash(focal_fields, 12)}")
        self._focal_fields = focal_fields
        self.hits = 0
        self.misses = 0

    def _col_path(self, col_fields):
        return self.dir / f'{_key_hash(col_fields)}.npy'

    def get_column(self, col_fields, n_ivs, n_scenarios):
        """Return the (n_ivs, n_scenarios) float64 column, or None."""
        try:
            p = self._col_path(col_fields)
            if p.exists():
                arr = np.load(p)
                if arr.shape == (n_ivs, n_scenarios):
                    self.hits += 1
                    return arr
        except Exception as e:
            # A corrupt stored file self-heals as a miss (re-simmed and
            # overwritten), but silently it looks like "cache stopped
            # working" — leave a trace.
            import logging
            logging.getLogger('deep_dive').debug(
                f'sweep cache: failed to load column ({e}); treating as miss')
        self.misses += 1
        return None

    def put_column(self, col_fields, arr):
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            meta_p = self.dir / 'meta.json'
            if not meta_p.exists():
                meta_p.write_text(json.dumps(self._focal_fields, indent=1,
                                             sort_keys=True))
            p = self._col_path(col_fields)
            # Atomic write: a crash (or a concurrent dive of the same
            # focal) mid-np.save must not leave a truncated column.
            # File-handle form so np.save can't append a second '.npy'.
            tmp = p.with_name(p.name + '.tmp')
            with open(tmp, 'wb') as f:
                np.save(f, np.asarray(arr, dtype=np.float64))
            os.replace(tmp, p)
            p.with_suffix('.json').write_text(
                json.dumps(col_fields, indent=1, sort_keys=True))
        except Exception:
            pass  # cache is best-effort
