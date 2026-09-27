"""
Shared fixtures for gopvpsim tests.
"""
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
import gopvpsim
import gopvpsim.data as data_module


# ---------------------------------------------------------------------------
# @pytest.mark.node -- the ONE "skip if node is missing" rule
# ---------------------------------------------------------------------------
# Tests that run shipped JS under node carry this marker instead of each
# re-implementing the check (there were ~30 open-coded skipifs and imperative
# skips before 2026-09-27). The skip stays per test, as the 2026-08-09 review
# decided; scripts/verify_tests.py is what makes a node-less SHIP machine loud.

def pytest_configure(config):
    config.addinivalue_line(
        'markers', 'node: runs JS under node; skips (reason "node not '
                   'installed") when node is not on PATH')


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    # tryfirst: skip before fixture setup, so a module fixture that shells
    # out to node is never entered on a node-less machine.
    if item.get_closest_marker('node') and shutil.which('node') is None:
        pytest.skip('node not installed')

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


def load_script(name):
    """Return ``scripts/<name>.py`` as module ``name``, loaded at most once.

    Get-or-create by name, registered in ``sys.modules`` before exec, so every
    test module asking for e.g. ``sweep_cache`` shares one object. Four cache
    test modules carried this body verbatim (as ``sys.modules.get(n) or
    _load(n)``) until 2026-09-27. Callers put ``scripts/`` on ``sys.path``
    themselves when the script imports its siblings.
    """
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(
        name, SCRIPTS_DIR / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Replay-blob lookup (was open-coded in five test modules until 2026-09-27)
# ---------------------------------------------------------------------------

def replay_dirs():
    """Where replay blobs may live: this clone, then a sibling checkout.

    A working clone of this repo shares the machine's blob store with the
    main checkout rather than duplicating 9 GB of pickles.
    """
    return [REPO_ROOT / 'userdata' / 'replay',
            REPO_ROOT.parent / 'gopvpsim' / 'userdata' / 'replay']


def find_blob(name):
    """Path to replay blob ``name``, or None when it is not on this machine."""
    for d in replay_dirs():
        p = d / name
        if p.exists():
            return p
    return None


def require_blob(name):
    """Path to replay blob ``name``; skips the test when it is absent."""
    p = find_blob(name)
    if p is None:
        pytest.skip(f"{name} is not on this machine")
    return p


# ``deep_dive_which_build.prepare`` at its defaults (pvpoke, l50), once per
# blob per session. prepare() is the expensive step (13.8 s on the Shadow
# Sableye blob, 7.5 s on Melmetal, against 1-2 s for load_blob), and the
# which-build tests asked for the SAME three blobs (Sableye shadow/plain,
# Melmetal GL) from module fixtures, parametrized tests and three separate
# modules -- about 17 prepare() calls where 3 do (those three modules' full
# run: 242 s -> 99 s, 2026-09-27). Memory is not new: the module-level
# ``_facts_for`` cache in test_which_build_section.py already held exactly
# these three (state, facts) pairs for the rest of the session; this memo
# replaces it and lets the module fixtures share it instead of holding their
# own copies. Consumers must treat the result as read-only (a probe on
# 2026-09-27 found all three fact sets pickle-identical at the end of a full
# run of their consumers).
_PREPARED = {}


def prepared_blob(name):
    """``(state, all_facts, path_str)`` for replay blob ``name``, memoised."""
    if name not in _PREPARED:
        path = str(require_blob(name))
        for p in (REPO_ROOT / 'src', SCRIPTS_DIR):
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
        import deep_dive_brief as B
        import deep_dive_which_build as W
        state = B.load_blob(path)
        _PREPARED[name] = (state, W.prepare(state, path), path)
    return _PREPARED[name]


# ---------------------------------------------------------------------------
# strip_js -- the tests' shared JS scrubber. Moved here from
# test_win_boundary.py on 2026-09-27 (a dozen modules imported it from that
# test module); its self-test, test_strip_js_detects_only_real_code, stays
# there.
# ---------------------------------------------------------------------------

# Characters after which a `/` starts a regex literal rather than a division.
_RE_PRECEDERS = set('(,=:[!&|?{};+-*%~^<>\n')


def strip_js(text):
    """Blank out JS comments, string literals and regex literals.

    Removed regions are replaced by spaces so line numbers and columns are
    preserved for reporting. Handles ``//`` line comments, ``/* */`` block
    comments, ``'``/``"``/`` ` `` strings with backslash escapes, and regex
    literals (disambiguated from division by the previous significant char).
    """
    out = list(text)
    i, n = 0, len(text)
    prev_sig = '\n'   # last significant (non-space) code character

    def blank(a, b):
        for k in range(a, b):
            if out[k] != '\n':
                out[k] = ' '

    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if c in '\'"`':
            j = i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2
                    continue
                if text[j] == c:
                    j += 1
                    break
                j += 1
            blank(i, j)
            prev_sig = 'x'   # a string is a value, like an identifier
            i = j
            continue
        if c == '/' and prev_sig in _RE_PRECEDERS:
            j, in_class = i + 1, False
            while j < n:
                ch = text[j]
                if ch == '\\':
                    j += 2
                    continue
                if ch == '\n':
                    break            # not a regex after all; bail
                if ch == '[':
                    in_class = True
                elif ch == ']':
                    in_class = False
                elif ch == '/' and not in_class:
                    j += 1
                    break
                j += 1
            blank(i, j)
            prev_sig = 'x'
            i = j
            continue
        if not c.isspace():
            prev_sig = c
        i += 1
    return ''.join(out)


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
#   --policy both      -> both strategy tiers, so 'policy-sel' renders
#                         (Marill is a non-case species, so the
#                         pogodives tier is byte-identical pvpoke sims --
#                         cheap, and it exercises the fallback invariant
#                         through a real render)
#   (best-buddy auto on Great) -> the sidenav's 'dd-bb-toggle' renders
#   Marill (not Bastiodon) -> best buddy is ACTIVE (its 14/14/14 IVs are
#                         under 1500 CP at L50, so they climb to L51), so
#                         the L51 <template>s render
#                         and the DOM-id / tooltip / opp-anchor / clusters
#                         guards see both halves of every host pair. Until
#                         2026-09-25 this was Bastiodon, a best-buddy NO-OP
#                         species; no-op dives stopped rendering the L51
#                         pass then (tests/test_bb_noop_single_pass.py), so
#                         a no-op fixture would leave those guards vacuous.
#   (shield scenarios) -> --html implies --interactive, which expands 1,1 to
#                         all nine, so 'scenario-sel' renders
#
# The rest keep it cheap and side-effect free: 8 IVs x 2 opponents, no slayer
# iteration, and -- important while the engine is under edit -- NO sweep-cache
# writes, no replay blob, no log file under userdata/ (CLAUDE.md "use
# --no-sweep-cache while changing the engine": a WIP-engine run with the cache
# on overwrites trusted columns in place).
SMALL_DIVE_ARGS = [
    'Marill', '--league', 'great',
    '--opponents', '2', '--species-iv-floor', '14,14,14',
    '--top-movesets', '2', '--opp-ivs', 'both', '--energy-lead', 'on',
    '--policy', 'both',
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


@pytest.fixture
def allow_legacy_mechanics(monkeypatch):
    """Opt in to simulate(mechanics='legacy'), which raises by default.

    For tests that compare the retired legacy clock against the live one on
    purpose; anything else should just use 'new'.
    """
    monkeypatch.setenv('GOPVPSIM_ALLOW_LEGACY_MECHANICS', '1')


@pytest.fixture(autouse=True, scope='session')
def _pin_data_cache_ttl():
    """Pin the gamemaster/rankings disk cache for the whole test run.

    A pytest invocation must never REFRESH the on-disk cache: the refresh
    swaps opponent data under everything else sharing the cache — including
    an in-flight overnight dive chain (the documented reproducibility
    hazard). With CACHE_TTL pinned to infinity an existing cache file is
    used as-is regardless of age; a genuinely cold cache still fetches once.

    Longer form of the same rationale (T1, 2026-06-12): without this, any
    pytest invocation whose tests hit load_gamemaster/load_rankings can
    refresh the 24h-TTL cache mid-run — which silently changes opponent
    resolution for any concurrently running dive chain (the reason "no
    pytest while a dive chain runs" was a standing rule). Pinning the TTL
    to infinity makes the suite read-only on the cache: stale-but-present
    data is always served, a fetch only happens if no cache file exists at
    all.

    (A byte-equivalent duplicate of this fixture, `_pin_gamemaster_cache`,
    lived below until the 2026-08-09 test-suite review: both were
    session-scoped autouse and both set CACHE_TTL = inf, so the second one
    saved the value the first had already pinned and its restore was a
    provable no-op. Merged into this one.)
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
