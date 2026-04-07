"""
Cache for mirror slayer iteration sims.

The slayer iteration tests focal IVs against many opponent IVs of the same species.
Same focal-vs-opponent pair gives the same scores (deterministic sim), so we cache
them. Cache is in-memory for the current run plus optionally persisted to disk
across runs.

Cache key: (focal_iv_idx, opp_iv_idx) -> tuple of n_scenarios ints (scores).
File key: species, league, moveset, shadow flag, plus a hash of move stats and
species stats (so cache invalidates when move data or species data changes).
"""
import hashlib
import json
import os
import pickle
from pathlib import Path

CACHE_VERSION = 1  # bump when battle simulation logic changes
CACHE_DIR = Path.home() / '.cache' / 'gopvpsim' / 'slayer'


def _move_hash(move_dict):
    """Stable hash of move stats relevant to damage calc."""
    if not move_dict:
        return 'none'
    fields = ['power', 'energy', 'energyGain', 'cooldown', 'turns', 'type']
    parts = []
    for k in fields:
        if k in move_dict:
            parts.append(f'{k}={move_dict[k]}')
    return ','.join(parts)


def compute_cache_key(species, league, shadow, fast_move, charged_moves, base_stats):
    """
    Build a stable cache key string identifying a slayer-iteration scenario.

    Two runs with the same key are guaranteed to produce identical sims.
    """
    h = hashlib.md5()
    h.update(f'v{CACHE_VERSION}'.encode())
    h.update(species.encode())
    h.update(league.encode())
    h.update(b'shadow' if shadow else b'normal')
    h.update(_move_hash(fast_move).encode())
    for cm in charged_moves:
        h.update(_move_hash(cm).encode())
    h.update(json.dumps(base_stats, sort_keys=True).encode())
    return f'{species}_{league}_{h.hexdigest()[:12]}'


class SlayerCache:
    """In-memory cache with optional disk persistence."""

    def __init__(self, cache_key=None, disk=True):
        self.data = {}  # (focal_iv_idx, opp_iv_idx) -> tuple of scores
        self.cache_key = cache_key
        self.disk = disk
        self.hits = 0
        self.misses = 0
        if disk and cache_key:
            self._load()

    def _path(self):
        return CACHE_DIR / f'{self.cache_key}.pkl'

    def _load(self):
        try:
            p = self._path()
            if p.exists():
                with open(p, 'rb') as f:
                    self.data = pickle.load(f)
        except Exception:
            self.data = {}

    def save(self):
        if not (self.disk and self.cache_key):
            return
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            p = self._path()
            with open(p, 'wb') as f:
                pickle.dump(self.data, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            pass  # cache is best-effort

    def get(self, focal_iv_idx, opp_iv_idx):
        key = (focal_iv_idx, opp_iv_idx)
        if key in self.data:
            self.hits += 1
            return self.data[key]
        self.misses += 1
        return None

    def put(self, focal_iv_idx, opp_iv_idx, scores):
        self.data[(focal_iv_idx, opp_iv_idx)] = tuple(scores)

    def stats(self):
        total = self.hits + self.misses
        rate = self.hits / total if total else 0
        return f'cache: {self.hits} hits, {self.misses} misses ({rate:.1%} hit rate, {len(self.data)} entries)'
