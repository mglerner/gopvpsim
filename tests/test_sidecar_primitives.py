"""Shared cache-sidecar primitives (DRY review 2026-08-05 entry 3e).

The sidecar's field set was serialized in four places (put_column,
SlayerCache.save, migrate_cache._bless, _bless_slayer). The migrate
rewrites re-serialized a HARDCODED field list, so any field a future
put_column adds would be silently dropped by the next warm migration
-- on the artifact whose only recovery is a multi-hour cold re-dive.
The primitives now live in sweep_cache (read_sidecar / write_sidecar /
bless_sidecar); bless is read-modify-write, which is the property
under test here.

The "nobody hand-rolls it anymore" half used to be an exact dict-literal
substring asserted absent, plus two import-text pins. A 2026-08-09
fragility probe re-introduced the forbidden serialization as
``{'engine': engine,  'gamemaster': gamemaster}`` (two spaces) and the pin
stayed green; the routing pins could not fail on a refactor either. Both
are now structural: an AST scan over migrate_cache's dict literals (with
its own self-test and a positive control on the bless call site), and
runtime spies proving the two writers really call the shared primitive.
"""
import ast
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import sweep_cache  # noqa: E402
import slayer_cache  # noqa: E402

_SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def _hand_rolled_stamp_dicts(source):
    """Dict literals that re-serialize the sidecar's stamp fields by hand.

    A mapping carrying BOTH stamp keys is the shape write_sidecar /
    bless_sidecar exist to own. AST-based, so interior spacing, quote
    style, key order and line wrapping cannot re-spell it past the scan --
    and both mapping syntaxes count: the ``{...}`` literal and the
    ``dict(engine=..., gamemaster=...)`` call form, which escaped the
    literal-only version (2026-08-09 adversarial review).
    """
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            keys = {k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        elif (isinstance(node, ast.Call)
                and getattr(node.func, 'id', None) == 'dict'):
            keys = {kw.arg for kw in node.keywords if kw.arg}
        else:
            continue
        if {'engine', 'gamemaster'} <= keys:
            hits.append((node.lineno, sorted(keys)))
    return hits


def _calls_named(source, name):
    """Line numbers of every call to ``name`` (bare or attribute)."""
    return [n.lineno for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.Call)
            and (getattr(n.func, 'attr', None) or getattr(n.func, 'id', None)) == name]


def test_write_read_roundtrip(tmp_path):
    sc = tmp_path / 'col.json'
    fields = {'engine': 'e1', 'gamemaster': 'g1', 'col': {'species': 'Azumarill'}}
    sweep_cache.write_sidecar(sc, fields)
    assert sweep_cache.read_sidecar(sc) == fields
    # Anti-vacuity for the negative below: the sidecar really landed here,
    # so "no .tmp droppings" is not just "nothing was written at all".
    assert sc.exists() and json.loads(sc.read_text()) == fields
    assert not list(tmp_path.glob('*.tmp'))  # atomic write left no droppings


def test_bless_preserves_future_fields(tmp_path):
    # THE property: a field bless doesn't know about must survive the
    # migration verbatim.
    sc = tmp_path / 'col.json'
    sweep_cache.write_sidecar(sc, {
        'engine': 'old', 'gamemaster': 'g1',
        'col': {'species': 'Azumarill'},
        'a_future_field': {'added': 'by a later put_column'}})
    assert sweep_cache.bless_sidecar(sc, engine='new')
    d = sweep_cache.read_sidecar(sc)
    assert d['engine'] == 'new'
    assert d['gamemaster'] == 'g1'                    # untouched stamp kept
    assert d['a_future_field'] == {'added': 'by a later put_column'}
    assert d['col'] == {'species': 'Azumarill'}


def test_bless_refuses_unreadable_sidecar(tmp_path):
    missing = tmp_path / 'nope.json'
    assert not sweep_cache.bless_sidecar(missing, engine='new')
    assert not missing.exists()  # must not fabricate a sidecar
    corrupt = tmp_path / 'corrupt.json'
    corrupt.write_text('{not json')
    assert not sweep_cache.bless_sidecar(corrupt, engine='new')
    assert corrupt.read_text() == '{not json'  # left alone


def test_read_sidecar_failure_is_none(tmp_path):
    assert sweep_cache.read_sidecar(tmp_path / 'absent.json') is None


def test_slayer_read_stamp_routes_through_shared_reader(tmp_path):
    sc = tmp_path / 's.json'
    sweep_cache.write_sidecar(sc, {'engine': 'e', 'gamemaster': 'g',
                                   'scenario': {'species': 'Medicham'}})
    assert slayer_cache.read_stamp(sc) == ('e', 'g', {'species': 'Medicham'})
    assert slayer_cache.read_stamp(tmp_path / 'absent.json') == (None,) * 3


def test_migrate_cache_does_not_re_serialize_the_stamp_by_hand():
    src = (_SCRIPTS / 'migrate_cache.py').read_text()
    assert not _hand_rolled_stamp_dicts(src)
    # Positive control: the canonical replacement must still be CALLED.
    # Without this, "no hand-rolled dict" is also true of a migrate_cache
    # that stopped touching sidecars altogether.
    assert _calls_named(src, 'bless_sidecar'), 'migrate_cache stopped blessing'


def test_the_hand_rolled_scanner_actually_catches_a_respelling():
    """Guard the guard. The first spelling is what the old substring pin
    caught; the rest are what a 2026-08-09 probe slipped past it."""
    for snippet in ("d = {'engine': engine, 'gamemaster': gamemaster}",
                    "d = {'engine': engine,  'gamemaster': gamemaster}",
                    'd = {"engine": engine, "gamemaster": gamemaster}',
                    "d = {'gamemaster': gamemaster, 'engine': engine}",
                    "d = {\n    'engine': engine,\n    'gamemaster': gm,\n}",
                    # ...and the call form, which escaped the
                    # literal-only scan (2026-08-09 adversarial review).
                    "d = dict(engine=engine, gamemaster=gamemaster)",
                    "d = dict(\n    gamemaster=gm,\n    engine=e,\n)"):
        assert _hand_rolled_stamp_dicts(snippet), snippet
    # ...and stays quiet on the shapes that are allowed to exist.
    assert not _hand_rolled_stamp_dicts("d = {'engine': engine}")
    assert not _hand_rolled_stamp_dicts("d = dict(engine=engine)")
    assert not _hand_rolled_stamp_dicts(
        "bless_sidecar(p, engine=engine, gamemaster=gamemaster)")


def test_slayer_save_routes_through_the_shared_writer(tmp_path, monkeypatch):
    """Object identity, not import text: swap write_sidecar and the slayer
    cache's save must be the thing that called it."""
    seen = []
    monkeypatch.setattr(sweep_cache, 'write_sidecar',
                        lambda p, fields: seen.append((Path(p).name, fields)))
    monkeypatch.setattr(slayer_cache, 'CACHE_DIR', tmp_path)
    c = slayer_cache.SlayerCache(cache_key='k', disk=True,
                                 scenario={'species': 'Medicham'})
    c.put(0, 0, (500.0, 500.0))
    c.save()
    assert len(seen) == 1, seen
    name, fields = seen[0]
    assert name == 'k.json'
    assert fields['scenario'] == {'species': 'Medicham'}
    assert set(fields) >= {'engine', 'gamemaster', 'scenario'}


def test_put_column_routes_through_the_shared_writer(tmp_path, monkeypatch):
    import numpy as np
    seen = []
    real = sweep_cache.write_sidecar

    def spy(p, fields):
        seen.append((Path(p).name, fields))
        return real(p, fields)

    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(sweep_cache, 'write_sidecar', spy)
    focal = sweep_cache.focal_key_fields(
        species='Azumarill', league='great', shadow=False, fast_id='BUBBLE',
        charged_ids=['ICE_BEAM'], iv_floor=(14, 14, 14),
        shield_scenarios=[(0, 0)], bait_mode='bait')
    col = sweep_cache.column_key_fields(
        opp_species='Medicham', opp_shadow=False, opp_ivs=(7, 15, 14),
        opp_level=49.0, opp_fast_id='COUNTER', opp_charged_ids=['PSYCHIC'])
    sweep_cache.SweepCache(focal).put_column(
        col, {'score': np.zeros((8, 1)), 'energy': np.zeros((8, 1))})
    assert len(seen) == 1, seen
    # Monotone set, not an equality (matches the slayer sibling above): the
    # sidecar schema is versioned and has grown before (v6 engine stamp, v7
    # gamemaster stamp), so a legitimate v8 field must not be a repair
    # commit (2026-08-09 adversarial review).
    assert set(seen[0][1]) >= {'engine', 'gamemaster', 'col'}
