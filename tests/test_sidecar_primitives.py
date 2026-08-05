"""Shared cache-sidecar primitives (DRY review 2026-08-05 entry 3e).

The sidecar's field set was serialized in four places (put_column,
SlayerCache.save, migrate_cache._bless, _bless_slayer). The migrate
rewrites re-serialized a HARDCODED field list, so any field a future
put_column adds would be silently dropped by the next warm migration
-- on the artifact whose only recovery is a multi-hour cold re-dive.
The primitives now live in sweep_cache (read_sidecar / write_sidecar /
bless_sidecar); bless is read-modify-write, which is the property
under test here.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import sweep_cache  # noqa: E402
import slayer_cache  # noqa: E402


def test_write_read_roundtrip(tmp_path):
    sc = tmp_path / 'col.json'
    fields = {'engine': 'e1', 'gamemaster': 'g1', 'col': {'species': 'Azumarill'}}
    sweep_cache.write_sidecar(sc, fields)
    assert sweep_cache.read_sidecar(sc) == fields
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


def test_no_hand_rolled_sidecar_serialization_left():
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    # migrate_cache must not re-serialize sidecar field lists by hand.
    text = (scripts / 'migrate_cache.py').read_text()
    assert "'engine': engine, 'gamemaster': gamemaster" not in text
    assert 'bless_sidecar' in text
    # slayer save + sweep put_column route through write_sidecar.
    assert 'write_sidecar' in (scripts / 'slayer_cache.py').read_text()
    assert 'write_sidecar(sidecar' in (scripts / 'sweep_cache.py').read_text()
