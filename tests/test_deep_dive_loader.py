"""The shared scripts/deep_dive.py loader (DRY review 2026-08-05 entry 12, T8).

``tests.conftest.load_deep_dive`` replaced 20 open-coded loads (18
module-level preambles + 2 in-test variants; the review's "14 + 2" count
missed the line-wrapped forms).  The collapse is not cosmetic: the
preambles disagreed about the one property the dive's process pool
depends on.  ``iv_sweep`` pickles ``_sweep_worker`` / ``_sweep_worker_init``
BY QUALIFIED NAME, so

* the parent must have this exact module object registered as
  ``sys.modules['deep_dive']`` -- pickle-by-reference re-imports the name
  and compares identity, so pickling a function off an UNREGISTERED copy
  raises ``PicklingError: it's not the same object``, and
* the child (spawn) must be able to ``import deep_dive`` from the
  inherited ``sys.path``.

13 of the 20 old sites skipped the registration, so which object a test
file got -- and therefore whether worker pickling worked -- depended on
collection order.  These tests pin both halves plus a monotone guard
against a new open-coded load reappearing.

Since the entry-12 SPLIT the two pool entry points live in
``deep_dive_lib.sweep``, so pickle records THAT name and the identity
check above no longer runs against ``sys.modules['deep_dive']`` -- the
tests below assert the new name.  One-object-per-run still matters:
``deep_dive_rendering`` imports ``build_iv_categories`` back off
``deep_dive`` by name, and every test that pokes module-level state
(the opponent-variant registry, the sweep worker state) has to be
poking the same object the shims bind.
"""
import multiprocessing
import pickle
import re
import sys
from pathlib import Path

from tests.conftest import DEEP_DIVE_PATH, load_deep_dive

TESTS_DIR = Path(__file__).resolve().parent

# Matches an open-coded load of deep_dive.py under the canonical name,
# in either the one-line or the wrapped form the old preambles used.
_OPEN_CODED = re.compile(r'spec_from_file_location\(\s*["\']deep_dive["\']')


def test_loader_returns_one_shared_object():
    """Every call hands back the same object, and it IS sys.modules'."""
    dd = load_deep_dive()
    assert dd is load_deep_dive()
    assert sys.modules['deep_dive'] is dd
    assert dd.__name__ == 'deep_dive'
    assert Path(dd.__file__).resolve() == DEEP_DIVE_PATH.resolve()


def test_no_open_coded_deep_dive_loads_remain():
    """Monotone guard: a new test file must not mint its own module.

    A second exec_module rebinds sys.modules['deep_dive'] and breaks
    worker pickling for whichever file bound first -- the order-dependent
    failure T8 removed.
    """
    offenders = sorted(p.name for p in TESTS_DIR.glob('test_*.py')
                       if _OPEN_CODED.search(p.read_text()))
    assert offenders == []


def test_pool_entry_points_pickle_by_qualified_name():
    """The pool's two entry points round-trip to the SAME function object.

    Since the entry-12 split they live in ``deep_dive_lib.sweep`` and
    ``deep_dive`` re-exports them, so the qualified name pickle records is
    the LIB one -- an ordinary package import on the child side, which is
    strictly more robust than the by-path ``deep_dive`` load.  What still
    has to hold is that the re-exported object is the same object the
    qualified name resolves to; a copy would raise ``PicklingError: it's
    not the same object``.
    """
    dd = load_deep_dive()
    for fn in (dd._sweep_worker, dd._sweep_worker_init):
        assert fn.__module__ == 'deep_dive_lib.sweep'
        payload = pickle.dumps(fn)
        assert b'deep_dive_lib.sweep' in payload
        assert pickle.loads(payload) is fn


def test_spawned_worker_resolves_qualified_name():
    """A real spawn child imports the owning module and resolves the attr.

    Uses a pure parser function rather than _sweep_worker so the test
    needs no worker-init state; the mechanism under test (pickle by
    qualified name -> child-side import off the inherited sys.path) is
    identical.  ``tests/test_deep_dive_lib_workers.py`` runs the real
    ``_sweep_worker`` through a spawn pool.
    """
    dd = load_deep_dive()
    ctx = multiprocessing.get_context('spawn')
    with ctx.Pool(1) as pool:
        display, base, is_shadow, fast, charged = pool.apply(
            dd._parse_opponent_pool_line, ("Forretress (Shadow)",))
    assert (display, base, is_shadow) == ("Forretress (Shadow)",
                                          "Forretress", True)
    assert fast is None and charged is None
