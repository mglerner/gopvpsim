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

# Bump when battle simulation logic changes.
# v2 (2026-06-10): S1 form-change plumbing — slayer workers now sim
# Aegislash/Morpeko/Mimikyu mirrors with form mechanics, so v1 scores
# for those species are stale.
# v3 (2026-06-12): S7 cleanup touched slayer_worker_init / worker
# plumbing (scripts/ is outside the engine source hash; bump is the
# standing rule for any worker-code change even when outputs are
# expected identical).
CACHE_VERSION = 3
CACHE_DIR = Path.home() / '.cache' / 'gopvpsim' / 'slayer'


def _move_hash(move_dict):
    """Stable hash of move stats relevant to battle outcomes.

    Includes the buff fields: rebalances routinely tweak only
    buffs/buffApplyChance, and those change scores just as surely as
    power/energy do.
    """
    if not move_dict:
        return 'none'
    fields = ['power', 'energy', 'energyGain', 'cooldown', 'turns', 'type',
              'buffs', 'buffTarget', 'buffApplyChance',
              'buffsSelf', 'buffsOpponent']
    parts = []
    for k in fields:
        if k in move_dict:
            parts.append(f'{k}={move_dict[k]}')
    return ','.join(parts)


def compute_cache_key(species, league, shadow, fast_move, charged_moves, base_stats,
                      shield_scenarios=None, iv_floor=None):
    """
    Build a stable cache key string identifying a slayer-iteration scenario.

    Two runs with the same key are guaranteed to produce identical sims.
    Cache key includes:

    - the shield scenario list — different scenario sets produce different
      cached score-tuple shapes, so they must not collide;
    - ``iv_floor`` — cache entries are keyed by POSITIONAL iv_meta indices,
      and the floor changes the index↔IV mapping, so floored and floorless
      runs of the same species must not share a file;
    - the engine-source hash from sweep_cache (battle.py & friends) — any
      engine edit invalidates automatically, instead of relying on a manual
      CACHE_VERSION bump (which was forgotten once already, see v2 note);
    - the gamemaster content hash — covers data the explicit move/stat
      hashes can't see (e.g. a form-change species' ALT-form stats live in
      a different gamemaster entry than the ``base_stats`` passed here).
    """
    # Local import: sweep_cache lives in the same scripts/ dir and caches
    # both hashes per-process, so this is cheap after the first call.
    from sweep_cache import engine_hash, gamemaster_hash

    h = hashlib.md5()
    h.update(f'v{CACHE_VERSION}'.encode())
    h.update(engine_hash().encode())
    h.update(gamemaster_hash().encode())
    h.update(species.encode())
    h.update(league.encode())
    h.update(b'shadow' if shadow else b'normal')
    h.update(_move_hash(fast_move).encode())
    for cm in charged_moves:
        h.update(_move_hash(cm).encode())
    h.update(json.dumps(base_stats, sort_keys=True).encode())
    if shield_scenarios:
        scen_str = ','.join(f'{s0}v{s1}' for s0, s1 in shield_scenarios)
        h.update(scen_str.encode())
    if iv_floor is not None:
        h.update(f'floor={tuple(iv_floor)}'.encode())
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
        except Exception as e:
            import logging
            logging.getLogger('deep_dive').debug(
                f'slayer cache: failed to load {self.cache_key} ({e}); '
                f'starting empty')
            self.data = {}

    def save(self):
        if not (self.disk and self.cache_key):
            return
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            p = self._path()
            # Atomic write: a crash mid-pickle must not leave a truncated
            # file that the next run silently discards.
            tmp = p.with_name(p.name + '.tmp')
            with open(tmp, 'wb') as f:
                pickle.dump(self.data, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, p)
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
