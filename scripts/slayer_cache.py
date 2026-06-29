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
# v4 (2026-06-27): bug #4 fix — the key now includes ``focal_max_level``.
# Pre-v4 keys omitted the focal level cap, so a Master mirror-slayer run
# at one ``--max-level`` could serve another's stale cached scores
# (the cap changes the whole cohort's per-IV levels). Bump invalidates
# the level-cap-blind entries.
# v5 (2026-06-29): MIGRATABLE schema (mirror of sweep cache v6/v7). The
# engine-source hash and the gamemaster hash were REMOVED from the filename
# key and moved to a per-file ``.json`` sidecar STAMP. Before v5 both hashes
# were baked into the opaque filename, so any engine/gamemaster change minted a
# brand-new filename and orphaned every prior entry — a 100% COLD recompute on
# every engine bump, un-migratable (no stored inputs). v5 keys the filename on
# the SCENARIO only (engine/gamemaster-independent); the sidecar carries the
# engine+gamemaster stamp plus the scenario fields, so a stale stamp is a SAFE
# MISS (re-simmed, never served) and ``migrate_cache.py`` can warm-bless the
# provably-unaffected entries instead of cold-rebaking. The v4->v5 transition
# is a one-time cold rebake (old opaque-filename entries can't be mapped to the
# new scenario-only filenames — no stored inputs), after which future bumps are
# warm.
CACHE_VERSION = 5
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
                      shield_scenarios=None, iv_floor=None, focal_max_level=None):
    """
    Build a stable cache key string identifying a slayer-iteration scenario.

    Two runs with the same key are guaranteed to produce identical sims.
    Cache key includes:

    - the shield scenario list — different scenario sets produce different
      cached score-tuple shapes, so they must not collide;
    - ``iv_floor`` — cache entries are keyed by POSITIONAL iv_meta indices,
      and the floor changes the index↔IV mapping, so floored and floorless
      runs of the same species must not share a file;
    - ``focal_max_level`` — the focal's max power-up level cap (best-buddy /
      ``--max-level``). It lifts the WHOLE mirror cohort's per-IV levels, so
      two runs at different caps produce different scores and must not share a
      file (bug #4, 2026-06-27). Mirrors the sweep cache's ``focal_max_level``
      field. ``None`` means the run used the league default;
    NB: as of v5 the engine-source hash and the gamemaster hash are NO LONGER
    part of this key — they live in the per-file ``.json`` sidecar STAMP
    (see ``SlayerCache.save``/``_load``), exactly like the sweep cache's
    per-column stamp. That makes a stale engine/gamemaster a safe MISS (the
    sidecar check rejects it) and lets ``migrate_cache.py`` warm-bless the
    provably-unaffected entries after a localized change, instead of the old
    behavior where the hashes were baked into the opaque filename and every
    bump cold-orphaned the whole cache. The key now identifies the SCENARIO
    only, so it is engine/gamemaster-independent.
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
    if shield_scenarios:
        scen_str = ','.join(f'{s0}v{s1}' for s0, s1 in shield_scenarios)
        h.update(scen_str.encode())
    if iv_floor is not None:
        h.update(f'floor={tuple(iv_floor)}'.encode())
    h.update(f'focal_max_level={focal_max_level}'.encode())
    return f'{species}_{league}_{h.hexdigest()[:12]}'


def _current_stamps():
    """(engine_hash, gamemaster_hash) at the current process state."""
    from sweep_cache import engine_hash, gamemaster_hash
    return engine_hash(), gamemaster_hash()


def read_stamp(sidecar_path):
    """Read a v5 sidecar -> (engine, gamemaster, scenario) or (None, None, None)
    on any failure. Used by migrate_cache / gc_cache to inspect a slayer file's
    vintage without unpickling the (large) .pkl."""
    try:
        d = json.loads(Path(sidecar_path).read_text())
        return d.get('engine'), d.get('gamemaster'), d.get('scenario')
    except Exception:
        return None, None, None


class SlayerCache:
    """In-memory cache with optional disk persistence.

    v5: the on-disk pair is ``{key}.pkl`` (the score dict) + ``{key}.json``
    (the engine/gamemaster STAMP and the scenario fields). A load only serves
    the pkl when the sidecar's engine AND gamemaster match the current process
    — a stale or missing stamp is a SAFE MISS (re-simmed and overwritten, never
    served). ``scenario`` is a small dict of the migration-relevant scenario
    fields (species/league/shadow/fast/charged) so ``migrate_cache`` can apply
    a predicate without unpickling."""

    def __init__(self, cache_key=None, disk=True, scenario=None):
        self.data = {}  # (focal_iv_idx, opp_iv_idx) -> tuple of scores
        self.cache_key = cache_key
        self.disk = disk
        self.scenario = scenario
        self.hits = 0
        self.misses = 0
        if disk and cache_key:
            self._load()

    def _path(self):
        return CACHE_DIR / f'{self.cache_key}.pkl'

    def _sidecar(self):
        return CACHE_DIR / f'{self.cache_key}.json'

    def _load(self):
        try:
            p = self._path()
            sc = self._sidecar()
            if not (p.exists() and sc.exists()):
                self.data = {}
                return
            eng, gm, _scen = read_stamp(sc)
            cur_eng, cur_gm = _current_stamps()
            # Stale engine/gamemaster -> safe miss (re-sim, never serve stale).
            if eng != cur_eng or gm != cur_gm:
                self.data = {}
                return
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
            eng, gm = _current_stamps()
            p = self._path()
            sc = self._sidecar()
            # Order: REMOVE old stamp -> write data -> write new stamp. The
            # sidecar must come off FIRST. Since v5 collapsed the filename to
            # the scenario only, two engine vintages share one file; if we
            # wrote the new pkl while a leftover OLD-vintage sidecar survived a
            # torn/exception-failed write, a later engine DOWNGRADE to that old
            # vintage (exactly the revert-WIP-and-rerun engine-iteration
            # workflow) would serve the new pkl's STALE scores under the old
            # stamp. Removing the stamp first means any crash leaves the pkl
            # stamp-less -> a SAFE MISS until the matching sidecar lands.
            sc.unlink(missing_ok=True)
            # Atomic write: a crash mid-pickle must not leave a truncated
            # file that the next run silently discards.
            tmp = p.with_name(p.name + '.tmp')
            with open(tmp, 'wb') as f:
                pickle.dump(self.data, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, p)
            # Sidecar stamp (engine+gamemaster+scenario), written LAST and
            # atomically via tmp+replace, so the pkl only becomes servable once
            # a current-vintage stamp is fully in place.
            sc_tmp = sc.with_name(sc.name + '.tmp')
            sc_tmp.write_text(json.dumps(
                {'engine': eng, 'gamemaster': gm, 'scenario': self.scenario},
                sort_keys=True))
            os.replace(sc_tmp, sc)
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
