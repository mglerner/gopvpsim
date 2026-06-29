#!/usr/bin/env python
"""Selective sweep-cache invalidation after a localized engine OR gamemaster
change.

The sweep cache stamps each column with the engine hash AND (v7) the
sim-relevant gamemaster hash that produced it (in the .json sidecar). After a
localized change, most columns are provably unaffected and only a
characterizable subset changed. This tool BLESSES the unaffected columns
(rewrites their stamp to the current value, so a re-dive serves them warm) and
DELETES the affected ones (so they re-sim cold), instead of cold-rebaking the
whole cache.

Two migration modes:

  ENGINE  (--from-engine <oldhash> [--predicate ...]): a localized engine fix.
          A PROVEN predicate (not guessed) marks the affected columns.

  GAMEMASTER (--from-gamemaster <stamp> --old-gamemaster-file <path>): a
          gamemaster data change. Unlike the engine predicates, the affected
          set is COMPUTED from the actual old-vs-current pokemon/moves delta —
          no per-change predicate to hand-prove. A column is affected iff a
          gamemaster entry the battle READS for it changed or was removed.

Engine predicates (PROVEN, not guessed):

  shadow_xor  — bug #1 (the fire_now CMP gate using cmp_atk instead of
                shadow-boosted atk). A matchup's score changes ONLY when
                exactly one side is shadow. both-non-shadow: cmp_atk == atk
                on both sides, so the gate boolean is unchanged. both-shadow:
                dividing both atks by 1.2 preserves the `>` inequality, so
                the gate boolean is unchanged. Hence affected = (focal.shadow
                XOR opp.shadow). Proof pinned by tests/test_migrate_cache.py
                and the engine test tests/test_fire_now_cmp_shadow.py.

  self_debuff_either_side — bandaid[910] (the [910] defer gate using the
                defender's MAX-DAMAGE move instead of its bestChargedMove;
                --from-engine acdb94e0df72). The fix's behavioral delta is
                reachable ONLY when the ACTING pokemon's selected first charged
                move is self-debuffing, which requires it to own a
                self-debuffing charged move. A column simulates both
                orientations, so affected = (focal OR opponent owns a
                self-debuffing CM); a column is provably unchanged iff NEITHER
                does (BOTH-SIDED — an opponent-side self-debuff holder changes a
                non-self-debuff focal's column). Proof + completeness pinned by
                tests/test_migrate_cache.py and the engine A/B regression in
                tests/test_bandaid910_bestcm.py.

Preconditions enforced here:
  - ENGINE mode: only columns whose engine stamp == --from-engine are touched
    (scopes the predicate to the exact characterized delta), AND only columns
    whose per-column gamemaster stamp == the current gamemaster (so the
    from->to delta is engine-only — the predicate models nothing about
    gamemaster). v7: the gamemaster lives in the per-COLUMN sidecar, not the
    focal-dir meta, so a single dir can hold mixed vintages.
  - GAMEMASTER mode: only columns whose gamemaster stamp == --from-gamemaster
    are touched, AND only columns whose engine stamp == the current engine (so
    the from->to delta is gamemaster-only).

Default is --dry-run (report only). Pass --apply to write.

Usage:
  python scripts/migrate_cache.py --list-stamps
  python scripts/migrate_cache.py --from-engine <oldhash> [--predicate shadow_xor]
  python scripts/migrate_cache.py --from-engine <oldhash> --apply
  python scripts/migrate_cache.py --from-gamemaster <stamp> \
      --old-gamemaster-file <path-to-old-gamemaster.json> [--apply]
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep_cache  # noqa: E402


_SELF_DEBUFF_CM_IDS = None


def _self_debuff_charged_ids():
    """The set of charged moveIds flagged selfDebuffing by the ENGINE
    (moves.get_moves(), which sets the derived flag at moves.py:199).

    Memoized. MUST come from the engine path, not raw gamemaster move dicts —
    the raw dicts lack the computed ``selfDebuffing`` flag, and reading it off
    them silently yields all-False (the 2026-06-28 feasibility harness hit this
    exact trap and produced a false "gate never reached" reading)."""
    global _SELF_DEBUFF_CM_IDS
    if _SELF_DEBUFF_CM_IDS is None:
        from gopvpsim.moves import get_moves
        _, charged = get_moves()
        _SELF_DEBUFF_CM_IDS = {mid for mid, m in charged.items()
                               if m.get('selfDebuffing')}
    return _SELF_DEBUFF_CM_IDS


def _self_debuff_either_side(f, c):
    """bandaid[910] engine fix (pinned --from-engine acdb94e0df72).

    A column's score changes under the fix ONLY when, in some orientation, the
    ACTING pokemon's selected first charged move is self-debuffing — which
    requires that pokemon to OWN a self-debuffing charged move. A column
    simulates both orientations, so it is provably unchanged iff NEITHER side
    owns a self-debuffing charged move (BOTH-SIDED). Affected = the complement.

    The triage's earlier focal-only complement was UNSOUND: an opponent-side
    self-debuff holder changes a non-self-debuff focal's column (Lickitung
    focal vs Pangoro 92->284). Hence both sides.

    FAIL-SAFE: if either side's moveset is missing/unresolvable, return True
    (AFFECTED, re-sim) — never bless a column we can't prove unchanged."""
    if not f or not c:
        return True
    fch = f.get('charged')
    cch = c.get('charged')
    if not fch or not cch:
        return True
    sd = _self_debuff_charged_ids()
    return bool(set(fch) & sd) or bool(set(cch) & sd)


# affected(focal_fields, col_fields) -> True if the engine change changed
# this column's scores (must be re-simmed); False if provably unchanged.
PREDICATES = {
    'shadow_xor': lambda f, c: bool(f.get('shadow')) != bool(c.get('shadow')),
    'self_debuff_either_side': _self_debuff_either_side,
}


def _narrow_hash(gm):
    """Narrowed sim-relevant gamemaster hash of a parsed blob (matches
    sweep_cache.gamemaster_hash's value)."""
    blob = json.dumps(sweep_cache.gamemaster_subset(gm), sort_keys=True,
                      separators=(',', ':'))
    return hashlib.md5(blob.encode()).hexdigest()[:12]


def _name_index(gm):
    """speciesName -> [speciesId, ...] (a display name can map to several
    forms, e.g. Lanturn/Cradily/Golisopod)."""
    idx = {}
    for p in gm['pokemon']:
        idx.setdefault(p['speciesName'], []).append(p['speciesId'])
    return idx


def _id_map(gm, key, idkey):
    return {x[idkey]: x for x in gm[key]}


def build_gamemaster_delta(old_gm, new_gm):
    """Return (affected_fn, info) for the old->new gamemaster delta.

    ``affected_fn(focal_fields, col_fields)`` is True iff a gamemaster entry
    the battle READS for this column changed-or-was-removed. Computed from the
    actual data, not a hand-proven predicate. Soundness rests on:

      - Only gm['pokemon'] and gm['moves'] affect a score (everything else —
        CPM/type-chart/STAB/shadow mults — is hardcoded; see
        sweep_cache.gamemaster_subset). So touched = the pokemon/moves entries
        that differ.
      - touched is REMOVED-or-CHANGED only (not ADDED): a column baked at the
        old gm can only reference ids that existed THEN, so an added id touches
        nothing existing. (This also makes a purely-additive delta — e.g. "a
        new species was added" — a trivial bless-all.)
      - A column reads the BASE pokemon entry for its species (shadow stats =
        base x hardcoded mult, NOT the redundant gm '_shadow' entry), PLUS any
        form-change alternative-form entry read at battle time
        (formchange.py), PLUS the move entries both sides use.
      - If a column's stored display name can't be resolved to any id in either
        gm, we can't prove it unaffected -> AFFECTED (re-sim).
    """
    old_pk = _id_map(old_gm, 'pokemon', 'speciesId')
    new_pk = _id_map(new_gm, 'pokemon', 'speciesId')
    old_mv = _id_map(old_gm, 'moves', 'moveId')
    new_mv = _id_map(new_gm, 'moves', 'moveId')
    old_names = _name_index(old_gm)
    new_names = _name_index(new_gm)

    def _dump(x):
        return json.dumps(x, sort_keys=True) if x is not None else None

    touched_species = {sid for sid in old_pk
                       if _dump(old_pk[sid]) != _dump(new_pk.get(sid))}
    touched_moves = {mid for mid in old_mv
                     if _dump(old_mv[mid]) != _dump(new_mv.get(mid))}

    def _form_expand(ids):
        """Transitively add formChange.alternativeFormId targets (read at
        battle time), using both gms so a form relationship present in either
        vintage is honored."""
        out, stack = set(), list(ids)
        while stack:
            sid = stack.pop()
            if sid in out:
                continue
            out.add(sid)
            for pk in (old_pk, new_pk):
                e = pk.get(sid)
                if not e:
                    continue
                fc = e.get('formChange') or {}
                alt = fc.get('alternativeFormId')
                if alt and alt not in out:
                    stack.append(alt)
        return out

    def resolved_ids(name, shadow):
        cands = set(old_names.get(name, [])) | set(new_names.get(name, []))
        # Shadow combat stats come from the BASE entry; strip the suffix so a
        # base-entry change is caught even if the redundant '_shadow' copy
        # wasn't regenerated.
        cands = {c[:-7] if c.endswith('_shadow') else c for c in cands}
        if not cands:
            return None  # unresolvable -> caller treats as AFFECTED
        return _form_expand(cands)

    def affected(focal_fields, col_fields):
        if not touched_species and not touched_moves:
            return False  # purely-additive (or no-op) delta: nothing existing
        rf = resolved_ids(focal_fields.get('species'),
                          focal_fields.get('shadow'))
        ro = resolved_ids(col_fields.get('species'),
                          col_fields.get('shadow'))
        if rf is None or ro is None:
            return True
        if (rf | ro) & touched_species:
            return True
        used = {focal_fields.get('fast'), col_fields.get('fast')}
        used |= set(focal_fields.get('charged') or [])
        used |= set(col_fields.get('charged') or [])
        return bool(used & touched_moves)

    info = {
        'touched_species': sorted(touched_species),
        'touched_moves': sorted(touched_moves),
        'added_species': sorted(set(new_pk) - set(old_pk)),
        'added_moves': sorted(set(new_mv) - set(old_mv)),
    }
    return affected, info


def _iter_columns(cache_dir):
    """Yield (focal_dir, meta_fields, json_path, engine_stamp, gm_stamp,
    col_fields) for every stored column under ``cache_dir``. v7: the engine
    AND gamemaster stamps both live in the per-column sidecar."""
    cache_dir = Path(cache_dir)
    if not cache_dir.exists():
        return
    for focal_dir in sorted(cache_dir.iterdir()):
        if not focal_dir.is_dir():
            continue
        meta_p = focal_dir / 'meta.json'
        try:
            meta = json.loads(meta_p.read_text())
        except Exception:
            continue
        for jp in sorted(focal_dir.glob('*.json')):
            if jp.name == 'meta.json':
                continue
            try:
                side = json.loads(jp.read_text())
            except Exception:
                continue
            yield (focal_dir, meta, jp, side.get('engine'),
                   side.get('gamemaster'), side.get('col'))


def list_stamps(cache_dir):
    eng = Counter()
    gm = Counter()
    for _fd, _meta, _jp, e_stamp, gm_stamp, _col in _iter_columns(cache_dir):
        eng[e_stamp] += 1
        gm[gm_stamp] += 1
    cur_e = sweep_cache.engine_hash()
    cur_gm = sweep_cache.gamemaster_hash()
    print(f"current engine hash:     {cur_e}")
    print(f"current gamemaster hash: {cur_gm}")
    for label, counts, cur in (('engine', eng, cur_e),
                               ('gamemaster', gm, cur_gm)):
        print(f"\n{label} stamps:")
        if not counts:
            print("  (none)")
        for stamp, n in counts.most_common():
            tag = '  <- current' if stamp == cur else ''
            print(f"  {n:>8}  {stamp}{tag}")


def _bless(jp, col, engine, gamemaster):
    """Rewrite only the tiny sidecar stamp; the .npz (provably-valid scores) is
    left untouched. Atomic via tmp + replace."""
    tmp = jp.with_name(jp.name + '.tmp')
    tmp.write_text(json.dumps(
        {'engine': engine, 'gamemaster': gamemaster, 'col': col},
        indent=1, sort_keys=True))
    os.replace(tmp, jp)


def migrate_engine(cache_dir, from_engine, predicate_name, apply):
    affected = PREDICATES[predicate_name]
    to_engine = sweep_cache.engine_hash()
    cur_gm = sweep_cache.gamemaster_hash()
    if from_engine == to_engine:
        print(f"--from-engine {from_engine} equals the current engine; "
              "nothing to migrate.")
        return
    blessed = deleted = skipped_gm = skipped_other = 0
    for _fd, _meta, jp, e_stamp, gm_stamp, col in _iter_columns(cache_dir):
        # v7: the delta must be engine-only, so the column's gamemaster stamp
        # must already be current (per-column, not per-dir).
        if gm_stamp != cur_gm:
            skipped_gm += 1
            continue
        if e_stamp != from_engine:
            skipped_other += 1
            continue
        npz = jp.with_suffix('.npz')
        if affected(_meta, col):
            deleted += 1
            if apply:
                for p in (npz, jp):
                    try:
                        p.unlink()
                    except OSError:
                        pass
        else:
            blessed += 1
            if apply:
                _bless(jp, col, to_engine, gm_stamp)
    mode = 'APPLIED' if apply else 'DRY-RUN (use --apply to write)'
    print(f"ENGINE  predicate={predicate_name}  from={from_engine}  "
          f"to={to_engine}")
    print(f"  blessed (unaffected, served warm): {blessed}")
    print(f"  deleted (affected, will re-sim):   {deleted}")
    print(f"  skipped (other engine vintage):    {skipped_other}")
    print(f"  skipped (other gamemaster):        {skipped_gm}")
    print(f"  {mode}")


def migrate_gamemaster(cache_dir, from_gamemaster, old_gm_file, apply):
    to_gamemaster = sweep_cache.gamemaster_hash()
    cur_engine = sweep_cache.engine_hash()
    if from_gamemaster == to_gamemaster:
        print(f"--from-gamemaster {from_gamemaster} equals the current "
              "gamemaster; nothing to migrate.")
        return
    old_gm = json.loads(Path(old_gm_file).read_text())
    from gopvpsim.data import load_gamemaster
    new_gm = load_gamemaster()
    # Guard: the supplied old blob must be the one named by --from-gamemaster.
    actual = _narrow_hash(old_gm)
    if actual != from_gamemaster:
        print(f"ERROR: --old-gamemaster-file narrows to {actual}, not "
              f"--from-gamemaster {from_gamemaster}. Refusing to migrate.")
        sys.exit(2)
    # Guard: the current gamemaster on disk must match what we're migrating TO.
    cur_actual = _narrow_hash(new_gm)
    if cur_actual != to_gamemaster:
        print(f"ERROR: current gamemaster narrows to {cur_actual} but "
              f"gamemaster_hash() reports {to_gamemaster}. Refusing.")
        sys.exit(2)

    affected, delta = build_gamemaster_delta(old_gm, new_gm)
    print(f"GAMEMASTER  from={from_gamemaster}  to={to_gamemaster}")
    print(f"  delta: {len(delta['touched_species'])} species changed/removed, "
          f"{len(delta['touched_moves'])} moves changed/removed, "
          f"{len(delta['added_species'])} species added, "
          f"{len(delta['added_moves'])} moves added")
    if delta['touched_species']:
        print(f"  changed/removed species: {delta['touched_species'][:40]}")
    if delta['touched_moves']:
        print(f"  changed/removed moves:   {delta['touched_moves'][:40]}")

    blessed = deleted = skipped_engine = skipped_other = unresolved = 0
    for _fd, meta, jp, e_stamp, gm_stamp, col in _iter_columns(cache_dir):
        if e_stamp != cur_engine:
            skipped_engine += 1
            continue
        if gm_stamp != from_gamemaster:
            skipped_other += 1
            continue
        npz = jp.with_suffix('.npz')
        if affected(meta, col):
            deleted += 1
            if apply:
                for p in (npz, jp):
                    try:
                        p.unlink()
                    except OSError:
                        pass
        else:
            blessed += 1
            if apply:
                _bless(jp, col, e_stamp, to_gamemaster)
    mode = 'APPLIED' if apply else 'DRY-RUN (use --apply to write)'
    print(f"  blessed (unaffected, served warm): {blessed}")
    print(f"  deleted (affected, will re-sim):   {deleted}")
    print(f"  skipped (other engine vintage):    {skipped_engine}")
    print(f"  skipped (other gamemaster vintage):{skipped_other}")
    print(f"  {mode}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--list-stamps', action='store_true',
                    help='report the distinct engine/gamemaster stamps and exit')
    ap.add_argument('--from-engine',
                    help='engine-mode: migrate columns stamped with this '
                         'engine hash (the pre-fix hash; see --list-stamps)')
    ap.add_argument('--predicate', default='shadow_xor',
                    choices=sorted(PREDICATES),
                    help='engine-mode: which proven invalidation predicate to '
                         'apply (default: %(default)s)')
    ap.add_argument('--from-gamemaster',
                    help='gamemaster-mode: migrate columns stamped with this '
                         'gamemaster hash (see --list-stamps)')
    ap.add_argument('--old-gamemaster-file',
                    help='gamemaster-mode: path to the OLD gamemaster.json '
                         '(supplies the delta; must narrow to --from-gamemaster)')
    ap.add_argument('--apply', action='store_true',
                    help='actually write changes (default: dry-run)')
    ap.add_argument('--cache-dir', default=None,
                    help='override the sweep cache dir (for tests)')
    a = ap.parse_args()
    cache_dir = a.cache_dir or sweep_cache.CACHE_DIR

    if a.list_stamps:
        list_stamps(cache_dir)
        return
    if a.from_gamemaster:
        if not a.old_gamemaster_file:
            ap.error('--from-gamemaster requires --old-gamemaster-file')
        migrate_gamemaster(cache_dir, a.from_gamemaster,
                           a.old_gamemaster_file, a.apply)
        return
    if not a.from_engine:
        ap.error('one of --list-stamps / --from-engine / --from-gamemaster '
                 'is required')
    migrate_engine(cache_dir, a.from_engine, a.predicate, a.apply)


if __name__ == '__main__':
    main()
