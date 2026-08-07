"""
Shared fixtures for gopvpsim tests.
"""
import importlib.util
import sys
from pathlib import Path

import pytest
import gopvpsim
import gopvpsim.data as data_module

# ---------------------------------------------------------------------------
# Shared scripts/deep_dive.py loader (DRY review 2026-08-05 entry 12, T8)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
DEEP_DIVE_PATH = SCRIPTS_DIR / 'deep_dive.py'


def load_deep_dive():
    """Return THE shared ``deep_dive`` module object, loading it once.

    ``scripts/deep_dive.py`` is a script, not a package member, so tests
    load it by path.  Two properties are load-bearing and were easy to
    get wrong while every test file open-coded the load:

    * The module must be registered in ``sys.modules['deep_dive']``
      BEFORE ``exec_module`` runs.  ``iv_sweep``'s process pool pickles
      ``_sweep_worker`` / ``_sweep_worker_init`` by qualified name, so
      the name has to resolve to this object on the parent side and to
      an importable ``deep_dive`` on the child side (spawn hands the
      child the parent's ``sys.path``, which is why ``scripts/`` goes on
      it here).
    * Exactly one object may ever be bound to that name.  A second
      ``exec_module`` rebinds ``sys.modules['deep_dive']`` and breaks
      pickle's identity check for whichever test file bound first --
      i.e. worker behavior would depend on collection order.

    Get-or-create preserves both.  Safe to call at test-module import
    time and from inside a test; every call returns the same object.
    """
    mod = sys.modules.get('deep_dive')
    if mod is not None:
        return mod
    for p in (REPO_ROOT / 'src', SCRIPTS_DIR):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location('deep_dive', DEEP_DIVE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules['deep_dive'] = mod      # BEFORE exec: worker pickling needs it
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        # Don't leave a half-built module registered; the next caller
        # would get it back and fail somewhere far from the real cause.
        sys.modules.pop('deep_dive', None)
        raise
    return mod


# Flags for the smallest dive that still renders EVERY conditional piece of
# page chrome. Each entry that is not just "make it small" is load-bearing for
# the DOM-id guard -- drop one and the guard silently stops covering the ids
# that block emits, so keep the reason attached (DRY review 2026-08-05 entry
# 12, js-py-dom-id-registry):
#
#   --top-movesets 2   -> >1 moveset, so the 'moveset-sel' dropdown renders
#   --opp-ivs both     -> >1 opponent-IV mode, so 'oppiv-sel' renders
#   --energy-lead on   -> >1 energy value, so 'energy-sel' renders
#   (--bait both, the default) -> both bait modes, so 'bait-sel' renders
#   (best-buddy auto on Great) -> the sidenav's 'dd-bb-toggle' renders
#   (shield scenarios) -> --html implies --interactive, which expands 1,1 to
#                         all nine, so 'scenario-sel' renders
#
# The rest keep it cheap and side-effect free: 8 IVs x 2 opponents, no slayer
# iteration, and -- important while the engine is under edit -- NO sweep-cache
# writes, no replay blob, no log file under userdata/ (CLAUDE.md "use
# --no-sweep-cache while changing the engine": a WIP-engine run with the cache
# on overwrites trusted columns in place).
SMALL_DIVE_ARGS = [
    'Bastiodon', '--league', 'great',
    '--opponents', '2', '--species-iv-floor', '14,14,14',
    '--top-movesets', '2', '--opp-ivs', 'both', '--energy-lead', 'on',
    '--no-thresholds', '--no-mirror-slayer',
    '--no-cache', '--no-sweep-cache', '--no-replay-dump',
    '--quiet', '--log-file', '/dev/null',
]


@pytest.fixture(scope='session')
def small_dive_html(tmp_path_factory):
    """Render ONE tiny but REAL deep-dive page; return its HTML text.

    Runs ``deep_dive.main()`` in-process (~10-15s, once per session) via
    the shared loader above -- the loader's ``sys.modules['deep_dive']``
    registration is what lets the sweep's spawn-mode workers resolve
    their pickled entry points from inside pytest.

    Session-scoped and shared: tests that need "what the shipped page
    actually contains" (DOM ids, the emitted score decoder) must not each
    pay for a render. Returns text, not a path, so no test can mutate
    what the next one reads.
    """
    dd = load_deep_dive()
    out = tmp_path_factory.mktemp('small_dive') / 'small_dive.html'
    old_argv = sys.argv
    sys.argv = ['deep_dive.py'] + SMALL_DIVE_ARGS + ['--html', str(out)]
    try:
        dd.main()
    finally:
        sys.argv = old_argv
    return out.read_text()


@pytest.fixture(autouse=True, scope='session')
def _pin_data_cache_ttl():
    """Pin the gamemaster/rankings disk cache for the whole test run.

    A pytest invocation must never REFRESH the on-disk cache: the refresh
    swaps opponent data under everything else sharing the cache — including
    an in-flight overnight dive chain (the documented reproducibility
    hazard). With CACHE_TTL pinned to infinity an existing cache file is
    used as-is regardless of age; a genuinely cold cache still fetches once.
    """
    orig = data_module.CACHE_TTL
    data_module.CACHE_TTL = float('inf')
    yield
    data_module.CACHE_TTL = orig

# ---------------------------------------------------------------------------
# Fake species used in unit tests — not tied to any real gamemaster data.
# base_atk=100, base_def=100, base_sta=100 keep the math easy to check by hand.
# ---------------------------------------------------------------------------

FAKE_BASE_ATK = 100
FAKE_BASE_DEF = 100
FAKE_BASE_STA = 100

MOCK_GAMEMASTER = {
    'pokemon': [
        {
            'speciesName': 'Testmon',
            'baseStats': {
                'atk': FAKE_BASE_ATK,
                'def': FAKE_BASE_DEF,
                'hp':  FAKE_BASE_STA,   # gamemaster uses 'hp' for stamina
            },
        },
    ],
    'moves': [],
}


@pytest.fixture
def mock_gm(monkeypatch):
    """Patch load_gamemaster with fake data and clear the library caches.

    Uses the package-level ``gopvpsim.invalidate_caches()`` (DRY review
    2026-08-05 entry 11) rather than reaching into one module's private
    global: the fake gamemaster must not be visible through a stale
    index, and the real data must not stay visible through one either.
    """
    monkeypatch.setattr('gopvpsim.pokemon.load_gamemaster',
                        lambda: MOCK_GAMEMASTER)
    gopvpsim.invalidate_caches()
    yield
    gopvpsim.invalidate_caches()


@pytest.fixture(autouse=True, scope='session')
def _pin_gamemaster_cache():
    """Freeze the on-disk gamemaster/rankings cache for the whole test
    session (T1, 2026-06-12). Without this, any pytest invocation whose
    tests hit load_gamemaster/load_rankings can refresh the 24h-TTL
    cache mid-run — which silently changes opponent resolution for any
    concurrently running dive chain (the reason "no pytest while a dive
    chain runs" was a standing rule). Pinning the TTL to infinity makes
    the suite read-only on the cache: stale-but-present data is always
    served, a fetch only happens if no cache file exists at all.
    """
    import gopvpsim.data as _data
    old = _data.CACHE_TTL
    _data.CACHE_TTL = float('inf')
    yield
    _data.CACHE_TTL = old
