"""Disk cache of won-set results for the ML IV-envelope analysis.

iv_envelope_analysis.py sims a focal at a handful of specific IV spreads across
a 2x2 best-buddy level grid -- far less work than a full deep_dive 4096-IV
sweep, and NOT in the sweep cache's per-opponent-column layout. So this is a
SEPARATE cache namespace (~/.cache/gopvpsim/iv_envelope/), deliberately never
the deep_dive sweep cache: writing our handful of spreads into a sweep column
would leave it partly populated, and a later deep_dive would read the
shape-valid-but-mostly-empty column as a corrupt hit. We DO reuse the sweep
cache's engine/gamemaster hashing and its best-effort + atomic-write design --
reuse where it's safe (logic), isolation where it must be (data).

Granularity: one entry per won_set() call = (focal IV spread, my_level,
opp_level), within a file pinned to (species, shadow, moveset, shields,
opponent pool, engine hash, gamemaster hash). One JSON file per species run, so
the driver's per-species subprocesses never contend (each owns its own file)
and re-running a finished species is all-hits.
"""
import json
import os
from pathlib import Path

from sweep_cache import engine_hash, gamemaster_hash, _key_hash

# Manual escape hatch: bump on a won_set-semantics change the engine /
# gamemaster hashes don't capture (e.g. the opponent IV assumption or the
# win condition itself).
CACHE_VERSION = 1
CACHE_DIR = Path.home() / '.cache' / 'gopvpsim' / 'iv_envelope'


def pool_fingerprint(opponents):
    """Stable hash of the resolved opponent pool. A won_set depends on each
    opponent's identity + moveset; opponent IVs are always 15/15/15 and their
    level is keyed per-won_set, so neither belongs here."""
    return _key_hash([[o['display'], o['base'], bool(o['shadow']),
                       o['fast'], list(o['charged'])] for o in opponents], 16)


def sig_fields(base_species, shadow, fast_id, charged_ids, shields, opponents):
    """Everything that makes a cached won_set valid; hashed into the filename
    so an engine edit, gamemaster refresh, moveset change, shield-set change,
    or pool change all produce a fresh file (the stale one is orphaned, safe to
    delete -- like the sweep cache, there is no auto-purge)."""
    return {
        'v': CACHE_VERSION,
        'species': base_species,
        'shadow': bool(shadow),
        'fast': fast_id,
        'charged': list(charged_ids),
        'shields': [[a, b] for a, b in shields],
        'pool': pool_fingerprint(opponents),
        'engine': engine_hash(),
        'gamemaster': gamemaster_hash(),
    }


class WonSetCache:
    """Per-species disk cache of won_set results. Best-effort: any I/O error
    degrades to a miss / no-store. ``enabled=False`` -> always-miss, no writes."""

    def __init__(self, species_slug, variant, sig, enabled=True):
        self.enabled = enabled
        self.hits = self.misses = 0
        self._dirty = False
        self.data = {}
        self.path = (CACHE_DIR /
                     f"{species_slug}__{variant}__{_key_hash(sig, 12)}.json")
        if enabled:
            try:
                self.data = json.loads(self.path.read_text())
            except Exception:
                self.data = {}

    @staticmethod
    def _k(ivs, my_lvl, opp_lvl):
        return f"{ivs[0]},{ivs[1]},{ivs[2]}|{my_lvl}|{opp_lvl}"

    def get(self, ivs, my_lvl, opp_lvl):
        """Reconstruct the won set, or None on miss."""
        if not self.enabled:
            return None
        v = self.data.get(self._k(ivs, my_lvl, opp_lvl))
        if v is None:
            self.misses += 1
            return None
        self.hits += 1
        return {(disp, (shf, sho)) for disp, shf, sho in v}

    def put(self, ivs, my_lvl, opp_lvl, won):
        if not self.enabled:
            return
        self.data[self._k(ivs, my_lvl, opp_lvl)] = sorted(
            [disp, shf, sho] for (disp, (shf, sho)) in won)
        self._dirty = True

    def flush(self):
        if not self.enabled or not self._dirty:
            return
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + '.tmp')
            tmp.write_text(json.dumps(self.data, separators=(',', ':')))
            os.replace(tmp, self.path)
            self._dirty = False
        except Exception:
            pass  # cache is best-effort
