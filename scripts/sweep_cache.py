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
                scenarios, bait mode, CACHE_VERSION
  column side - opponent species, shadow, resolved IVs, level, moveset
  per-column stamp (.json sidecar) - engine source hash (v6) AND
                sim-relevant gamemaster hash (v7)

The gamemaster hash makes data drift safe WITHOUT orphaning the cache:
opponent IVs and movesets are resolved BEFORE the key is built, so a
rankings refresh that changes resolution produces a different column key
(miss), while move-stat/base-stat changes change the per-column gamemaster
stamp (v7) — a stale-stamp column misses, and migrate_cache can bless the
columns a balance patch provably doesn't touch.

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
# v7 (2026-06-29): the gamemaster hash ALSO moved out of the focal key into a
# PER-COLUMN stamp (mirroring v6's engine move), AND was NARROWED to the only
# sim-relevant subset gm['pokemon'] + gm['moves'] (CPM/type-chart/STAB/shadow
# mults are all hardcoded in the engine, not read from the gamemaster — see
# gamemaster_hash). Two wins: (a) non-sim churn (timestamp/cups/formats/
# rankingScenarios/pokemonTags/...) no longer invalidates the cache at all;
# (b) a real balance patch that touches only a few species/moves no longer
# orphans the whole cache — migrate_cache.py's --from-gamemaster predicate
# blesses the columns whose focal+opponent species and moves are unchanged
# (e.g. "add a new species" touches nothing existing). A v7 focal dir can hold
# columns of mixed engine AND gamemaster vintages, each self-identifying by
# its sidecar stamp; gc_cache.py keeps v7 dirs (no per-dir vintage).
CACHE_VERSION = 7
CACHE_DIR = Path.home() / '.cache' / 'gopvpsim' / 'sweep'

# Compact on-disk dtype per column plane. score is the float64 PvPoke score;
# energy/shields are tiny bounded ints; won is a flag; hp/max_hp fit u16.
# Hits reconstruct exact values (all are integer-valued except score, which
# stays float64), so warm == cold bit-for-bit.
_PLANE_DTYPES = {
    'score': np.float64,
    'energy': np.uint8,
    'won': np.bool_,
    'hp': np.uint16,
    'max_hp': np.uint16,
    'shields': np.uint8,
}

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


def gamemaster_subset(gm):
    """The ONLY gamemaster fields the battle engine reads: pokemon + moves.

    Everything else that affects a score — CPM table, shadow atk/def
    multipliers, the type-effectiveness chart, STAB/BONUS/SUPER_EFFECTIVE —
    is HARDCODED in gopvpsim (pokemon.py, moves.py), not read from the
    gamemaster. A repo-wide grep (2026-06-29) confirms zero reads of
    settings/cups/formats/rankingScenarios/pokemonTags/shadowPokemon. So a
    score depends on the gamemaster ONLY through these two keys; hashing them
    (and nothing else) is the tightest sim-relevant identity. Callers that
    diff two gamemaster vintages (migrate_cache) use the SAME subset.
    """
    return {'pokemon': gm['pokemon'], 'moves': gm['moves']}


def gamemaster_hash():
    """Hash of the SIM-RELEVANT gamemaster subset (memoized per process).

    v7: narrowed from the whole-file md5 to md5(pokemon + moves) — see
    ``gamemaster_subset``. load_gamemaster() always round-trips through the
    cached gamemaster.json (fresh fetches are written before use), so the
    file content matches the data every sweep actually ran on. Parsing the
    file (vs the old raw-bytes md5) is what drops non-sim churn from the key.
    """
    global _GAMEMASTER_HASH
    if _GAMEMASTER_HASH is None:
        from gopvpsim.data import CACHE_DIR as DATA_CACHE_DIR
        p = DATA_CACHE_DIR / 'gamemaster.json'
        if p.exists():
            gm = json.loads(p.read_text())
            blob = json.dumps(gamemaster_subset(gm), sort_keys=True,
                              separators=(',', ':'))
            _GAMEMASTER_HASH = hashlib.md5(blob.encode()).hexdigest()[:12]
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
        # NB: NEITHER the engine hash (v6) NOR the gamemaster hash (v7) is
        # here — both are per-column stamps in the .json sidecar, so an engine
        # change or a gamemaster change doesn't orphan the focal dir. A v7
        # focal dir can therefore hold columns of mixed engine/gamemaster
        # vintages, each self-identifying by its sidecar stamp.
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

        The sidecar holds ``{'engine': <hash>, 'gamemaster': <hash>,
        'col': <col_fields>}`` (v7; v6 had no 'gamemaster'). Returns the
        stored engine hash so a stale-engine column can be rejected (or, via
        migrate_cache, blessed) without touching the .npz.
        """
        try:
            return json.loads(Path(json_path).read_text()).get('engine')
        except Exception:
            return None

    @staticmethod
    def read_gm_stamp(json_path):
        """Read the per-column gamemaster stamp from its .json sidecar (v7),
        or None if absent (v6 columns carry no gamemaster stamp)."""
        try:
            return json.loads(Path(json_path).read_text()).get('gamemaster')
        except Exception:
            return None

    def get_column(self, col_fields, n_ivs, n_scenarios,
                   required_planes=('score', 'energy')):
        """Return the column's planes as ``{name: ndarray}``, or None on a miss.

        A hit requires the per-column engine stamp AND gamemaster stamp to
        equal the current hashes (a stale-engine OR stale-gamemaster column is
        a miss — checked from the small sidecar before the big .npz is
        loaded), and every plane in ``required_planes`` present at shape
        ``(n_ivs, n_scenarios)``. The ML path requests the metric planes
        (won/hp/max_hp/shields) too; a column written with only score+energy
        misses for it. Corrupt/partial writes self-heal as a miss (re-simmed
        and overwritten).
        """
        try:
            p = self._col_path(col_fields)
            sidecar = p.with_suffix('.json')
            # Cheap stale-stamp rejection first: skip loading the .npz if the
            # sidecar engine OR gamemaster stamp doesn't match the current run.
            # (v6 columns carry no gamemaster stamp -> read_gm_stamp returns
            # None != current hash -> correctly a miss until re-simmed/blessed.)
            if (self.read_stamp(sidecar) != engine_hash()
                    or self.read_gm_stamp(sidecar) != gamemaster_hash()):
                self.misses += 1
                return None
            planes = read_planes(p)
            if (planes is not None
                    and all(name in planes
                            and planes[name].shape == (n_ivs, n_scenarios)
                            for name in required_planes)):
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
        """Persist a column from a ``{plane_name: ndarray}`` dict, each cast to
        its compact dtype (see ``_PLANE_DTYPES``). ``energy`` is asserted in
        [0,100] so a future out-of-range value fails loud instead of wrapping
        into uint8. The .json sidecar records the current engine AND
        sim-relevant gamemaster hashes as the column's stamps (v6 + v7)."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            meta_p = self.dir / 'meta.json'
            if not meta_p.exists():
                meta_p.write_text(json.dumps(self._focal_fields, indent=1,
                                             sort_keys=True))
            if 'energy' in planes:
                e = np.asarray(planes['energy'])
                assert e.min() >= 0 and e.max() <= 100, (
                    f'energy out of [0,100]: min={e.min()} max={e.max()}')
            out = {name: np.asarray(arr, dtype=_PLANE_DTYPES.get(name, np.float64))
                   for name, arr in planes.items()}
            p = self._col_path(col_fields)
            write_planes(p, out)
            p.with_suffix('.json').write_text(json.dumps(
                {'engine': engine_hash(), 'gamemaster': gamemaster_hash(),
                 'col': col_fields},
                indent=1, sort_keys=True))
        except Exception:
            pass  # cache is best-effort
