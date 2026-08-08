"""Staleness guards on scripts/patch_dive_gives_up_column.py.

That script copies a literal region of ``scripts/deep_dive_engine.js`` -- the
'Gives up vs #1' column helper -- into ALREADY-RENDERED deep-dive HTML, in
place, with no re-render. The region therefore lands on a page whose inlined
engine may be months older than the source, and anything the region calls that
is defined OUTSIDE it must already exist on that page or the patched column
throws and takes the whole collection table with it.

The region really does grow such calls: it gained ``scenLabel(si)`` (defined at
deep_dive_engine.js top level, DRY review 2026-08-05 entry 5) and then an
``isWin(score)`` call (cmp_panels.js, the WIN_RATING single-sourcing), while
the script's only skip conditions were "``_guMode`` present" and "the
placeholder strings are missing" -- neither of which can see a missing helper.

No page in userdata/website was ever exposed, though. Every rendered dive
carries ``_guMode`` and returns at the "already current" branch, which sits
ahead of the dep check, so the isWin the corpus lacks can never reach a splice.
The guard is forward-looking, and the last test below pins that ordering.

Two guards now sit in the script, and this file keeps both honest:

  * ``REGION_DEPS`` -- the manifest of out-of-region helpers, checked per
    target page before patching.
  * ``REGION_SHA256`` -- a pin on the region's source text. It is the piece
    that makes the manifest self-maintaining: edit the region and the pin
    trips, forcing a maintainer to re-derive the manifest.

The manifest-completeness test below derives the region's external calls
MECHANICALLY, so a new call added to the region fails here even if someone
re-stamps the hash without thinking.
"""
import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_win_boundary import strip_js  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / 'scripts'

# JS keywords that take a parenthesized head and would otherwise read as calls.
_KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'return', 'function',
             'typeof', 'new', 'do', 'else'}


def _patch_mod():
    spec = importlib.util.spec_from_file_location(
        'patch_dive_gives_up_column_pin',
        SCRIPTS / 'patch_dive_gives_up_column.py')
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _external_calls(region):
    """Bare ``name(`` calls in the region that the region does not define.

    Member calls (``x.foo()``) are excluded by the leading-dot check, and
    comments/strings are stripped first so prose like "list them" is not read
    as a call.
    """
    code = strip_js(region)
    called = set()
    for m in re.finditer(r'(\.?)\b([A-Za-z_$][\w$]*)\s*\(', code):
        if m.group(1) == '.':
            continue
        if m.group(2) in _KEYWORDS:
            continue
        called.add(m.group(2))
    defined = set(re.findall(r'function\s+([A-Za-z_$][\w$]*)\s*\(', code))
    return called - defined


def test_region_hash_pin_is_current():
    """The pin matches the region at HEAD, so the script is runnable.

    A failure here is BY DESIGN whenever the region changes: re-read the
    region, bring REGION_DEPS in line with the helpers it now calls from
    outside itself, and re-stamp REGION_SHA256 with the reported hash.
    """
    mod = _patch_mod()
    assert mod.REGION_HASH == mod.REGION_SHA256, (
        "the 'Gives up vs #1' region in deep_dive_engine.js changed since "
        'patch_dive_gives_up_column.py was last verified. Re-derive '
        f'REGION_DEPS, then set REGION_SHA256 = {mod.REGION_HASH!r}')


def test_region_deps_covers_every_external_call():
    """REGION_DEPS lists exactly the helpers the region calls from outside.

    Mechanical, not hand-listed: a new external call in the region fails here
    even if the hash pin was re-stamped without re-deriving the manifest.
    """
    mod = _patch_mod()
    assert _external_calls(mod.NEW_REGION) == set(mod.REGION_DEPS)


def test_region_deps_signatures_exist_in_the_shipped_js():
    """Each manifest entry names a real definition the bake inlines.

    A typo'd signature would never match any page, quietly turning the guard
    into "skip everything" (or, if inverted, into no guard at all).
    """
    mod = _patch_mod()
    src = ((SCRIPTS / 'deep_dive_engine.js').read_text()
           + (SCRIPTS / 'cmp_panels.js').read_text())
    for name, sig in mod.REGION_DEPS.items():
        assert src.count(sig) == 1, (
            f'REGION_DEPS[{name!r}] = {sig!r} must match exactly one '
            'definition across deep_dive_engine.js + cmp_panels.js')


def test_main_refuses_to_patch_when_the_pin_is_stale(monkeypatch, capsys):
    """A stale pin aborts BEFORE any file is touched, with a nonzero exit."""
    mod = _patch_mod()
    monkeypatch.setattr(mod, 'REGION_SHA256', '0' * 64)
    monkeypatch.setattr(mod, 'targets',
                        lambda argv: (_ for _ in ()).throw(
                            AssertionError('targets() must not be reached')))
    assert mod.main() == 1
    assert 'REFUSING to patch' in capsys.readouterr().err


def test_page_missing_a_dep_is_skipped_not_patched(tmp_path, monkeypatch,
                                                   capsys):
    """A page that predates a helper is reported and left byte-identical."""
    mod = _patch_mod()
    # Minimal stand-in for a rendered dive: carries every string the script
    # keys off, plus all but one of the required helper definitions.
    stale = (
        '<script>\n'
        + ''.join(f'{sig})' + ' {}\n' for name, sig in mod.REGION_DEPS.items()
                  if name != 'isWin')
        + '  // "Gives up vs #1" old body\n'
        "  var html = '';\n"
        "  header: 'Gives up vs #1',\n"
        '  escapeHtml(extras[xh].header)\n'
        '  origOpacities = traces.map(function(t) { return t.marker.opacity; });\n'
        '  renderMatchesList();\n'
        '</script>\n')
    page = tmp_path / 'index.html'
    page.write_text(stale)
    monkeypatch.setattr(mod, 'targets', lambda argv: [str(page)])
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert 'skip (page predates isWin' in out
    assert '0 upgraded' in out
    assert page.read_text() == stale


def test_gu_mode_short_circuits_before_the_dep_check(tmp_path, monkeypatch,
                                                     capsys):
    """A ``_guMode`` page is "already current", never dep-checked.

    This ordering is why the published corpus is not a patch candidate at all:
    every rendered dive carries ``_guMode``, so the isWin none of them define
    cannot reach the splice. Reversing the two branches would report the whole
    corpus as SKIPPED and misdescribe the sync path.
    """
    mod = _patch_mod()
    # Bears _guMode and NONE of the required helper definitions -- the shape
    # the dep check would reject if it were reached.
    page = tmp_path / 'index.html'
    page.write_text('<script>var _guMode = 0;\n'
                    '  // "Gives up vs #1" body\n'
                    "  var html = '';\n"
                    '</script>\n')
    monkeypatch.setattr(mod, 'targets', lambda argv: [str(page)])
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert '1 already current' in out
    assert 'skip (page predates' not in out
