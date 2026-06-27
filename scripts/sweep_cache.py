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
from pathlib import Path

import numpy as np

from cache_base import write_planes, read_planes

# Manual escape hatch: bump on any battle-behavior change that the
# engine source hash somehow misses (it shouldn't — see _ENGINE_FILES).
# v2 (2026-06-12): S7 cleanup touched dive worker/orchestration code in
# scripts/ (outside the engine hash); bump per the standing rule.
# v3 (2026-06-12): energy-lead axis added to _sweep_worker plumbing
# (focal starting energy threaded through worker init); bump per the
# same rule.
# v5 (2026-06-27): columns moved from a single-array .npy (score only) to
# a multi-plane .npz ({score: float64, energy: uint8}). Energy is now
# always captured + stored so --compare-energy re-dives serve warm instead
# of force-disabling the cache. Old .npy columns are orphaned (GC cleans).
# v6 (2026-06-27): the engine-source hash moved OUT of the focal key into a
# PER-COLUMN engine stamp (stored in the .json sidecar). An engine change no
# longer orphans the whole focal dir; columns self-heal in place (cold), and
# scripts/migrate_cache.py can selectively BLESS the columns a localized fix
# provably doesn't touch (e.g. bug #1's shadow-XOR predicate) so the re-dive
# is warm. gamemaster stays in the focal key, so a blessed column is
# guaranteed same-gamemaster (the predicate models only the engine delta).
CACHE_VERSION = 6
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
        # scripts/deep_dive_signature.py is not in the gopvpsim package but
        # DOES affect sweep scores: it picks which IVs share a representative
        # sim, so a dedup-logic change can change a column. Hash it too.
        _sig = Path(__file__).parent / 'deep_dive_signature.py'
        if _sig.exists():
            h.update(_sig.read_bytes())
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
                     iv_floor, shield_scenarios, bait_mode,
                     energy_lead=0, focal_max_level=None):
    """Focal-side key dict shared by every column of one sweep.

    ``energy_lead`` is the focal's starting energy in RAW energy points
    (already converted from the mode string's fast-move multiples and
    capped by the sweep), so two movesets whose 'e1' resolves to the
    same raw energy correctly share nothing here — the moveset is
    keyed separately anyway via ``fast``/``charged``.

    ``focal_max_level`` is the focal's max power-up level when the
    best-buddy/L51 toggle raised it (``None`` = league default). It changes
    the focal's per-IV levels and therefore every column's per-IV scores, so
    an L50 and an L51 sweep of the same species/moveset MUST NOT share columns.
    (Opponent column keys carry ``opp_level`` separately, so an over-leveled
    opponent already keys distinctly with no change here.)
    """
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
        'energy_lead': energy_lead,
        'focal_max_level': focal_max_level,
        # NB: the engine hash is intentionally NOT here (v6) — it is a
        # per-column stamp in the .json sidecar so an engine change doesn't
        # orphan the dir. gamemaster stays, so all columns in a focal dir
        # share one gamemaster vintage.
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
        return self.dir / f'{_key_hash(col_fields)}.npz'

    @staticmethod
    def read_stamp(json_path):
        """Read the per-column engine stamp from its .json sidecar, or None.

        The sidecar holds ``{'engine': <hash>, 'col': <col_fields>}`` (v6).
        Returns the stored engine hash so a stale-engine column can be
        rejected (or, via migrate_cache, blessed) without touching the .npz.
        """
        try:
            return json.loads(Path(json_path).read_text()).get('engine')
        except Exception:
            return None

    def get_column(self, col_fields, n_ivs, n_scenarios):
        """Return the column's planes as ``{'score': ndarray, 'energy':
        ndarray}``, or None on a miss.

        A hit requires the per-column engine stamp to equal the current
        engine hash (a stale-engine column is a miss — checked from the small
        sidecar before the big .npz is loaded), and both planes present at
        shape ``(n_ivs, n_scenarios)``. Corrupt/partial writes self-heal as a
        miss (re-simmed and overwritten).
        """
        try:
            p = self._col_path(col_fields)
            # Cheap stale-engine rejection first: skip loading the .npz if the
            # sidecar stamp doesn't match the current engine.
            if self.read_stamp(p.with_suffix('.json')) != engine_hash():
                self.misses += 1
                return None
            planes = read_planes(p)
            if (planes is not None
                    and 'score' in planes and 'energy' in planes
                    and planes['score'].shape == (n_ivs, n_scenarios)
                    and planes['energy'].shape == (n_ivs, n_scenarios)):
                self.hits += 1
                return planes
        except Exception as e:
            # A corrupt stored file self-heals as a miss (re-simmed and
            # overwritten), but silently it looks like "cache stopped
            # working" — leave a trace.
            import logging
            logging.getLogger('deep_dive').debug(
                f'sweep cache: failed to load column ({e}); treating as miss')
        self.misses += 1
        return None

    def put_column(self, col_fields, planes):
        """Persist a column from a ``{plane_name: ndarray}`` dict. ``score``
        is stored float64, ``energy`` uint8 (0..100, asserted). The .json
        sidecar records the current engine hash as the column's stamp (v6)."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            meta_p = self.dir / 'meta.json'
            if not meta_p.exists():
                meta_p.write_text(json.dumps(self._focal_fields, indent=1,
                                             sort_keys=True))
            score = np.asarray(planes['score'], dtype=np.float64)
            energy = np.asarray(planes['energy'])
            # Energy is a bounded battle output (0..100). Fail loud rather than
            # silently wrapping if a future change ever produces out-of-range
            # energy — uint8 would corrupt the "banks N charged moves" line.
            assert energy.min() >= 0 and energy.max() <= 100, (
                f'energy out of [0,100]: min={energy.min()} max={energy.max()}')
            p = self._col_path(col_fields)
            write_planes(p, {'score': score,
                             'energy': energy.astype(np.uint8)})
            p.with_suffix('.json').write_text(json.dumps(
                {'engine': engine_hash(), 'col': col_fields},
                indent=1, sort_keys=True))
        except Exception:
            pass  # cache is best-effort
