"""Shared ship-surface enumeration (DRY review 2026-08-05 entry 3a).

Both ship gates (verify_article_links, verify_no_unicode_dashes) must
gate exactly what publish_website.sh rsyncs. Their private copies of
the enumeration only picked up index.html at the site root, so
cups.html and support.html shipped with ZERO checks. The enumeration
now lives in ship_surfaces.find_ship_surfaces; this pins the root-glob
fix and that both gates actually route through the shared module.

The routing half used to be pinned as import TEXT plus one exact-substring
absence pin. A 2026-08-09 fragility probe re-spelled the forbidden private
enumeration as ``sub.rglob("index*.html")`` (double quotes) and the pin
stayed green. Both halves are now (a) object identity -- swap the shared
function, both gates must return the swapped value -- and (b) a tolerant
AST scan with its own self-test and a positive control on the module that
is SUPPOSED to own the glob.
"""
import ast
import importlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import ship_surfaces  # noqa: E402
from ship_surfaces import find_ship_surfaces  # noqa: E402

_SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
_GATES = ('verify_article_links', 'verify_no_unicode_dashes')

# NOT start-anchored: a leading path component (``*/index*.html``,
# ``**/index*.html``, ``./index*.html``) is the same enumeration and slipped
# past the anchored version (2026-08-09 adversarial review).
_PAGE_GLOB = re.compile(r'index[^/]*\.html\Z')


def _static_str(node):
    """The literal text of ``node``, or None if it isn't statically known.

    Folds the shapes an author reaches for without thinking: implicit
    concatenation (free -- the parser does it), an f-string with no
    interpolation (``ast.JoinedStr``, NOT ``ast.Constant``), and ``'a' +
    'b'``. An interpolated chunk becomes ``\\x00`` so a genuinely dynamic
    glob can never accidentally match a literal pattern.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        return ''.join(v.value if isinstance(v, ast.Constant) else '\x00'
                       for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _static_str(node.left), _static_str(node.right)
        return None if left is None or right is None else left + right
    return None


def _open_coded_page_globs(source):
    """Constant ``glob``/``rglob`` args that enumerate ``index*.html`` pages.

    AST-based, so quote style, interior whitespace, implicit string
    concatenation, an inert ``f`` prefix and ``+`` joins all fold away
    before the match.
    """
    hits = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')
        if name not in ('glob', 'rglob'):
            continue
        for arg in node.args:
            text = _static_str(arg)
            if text is not None and _PAGE_GLOB.search(text):
                hits.append(text)
    return hits


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('<html></html>')


def test_root_pages_are_gated(tmp_path):
    site = tmp_path / 'website'
    for rel in ('index.html', 'cups.html', 'support.html',
                'guides/index.html', 'guides/iv-flavor-guide/index.html',
                'azumarill-great-league/index.html',
                'azumarill-great-league/index_m1_a_b.html',
                'azumarill-great-league/scores.json.gz'):
        _touch(site / rel)
    got = {str(p.relative_to(site)) for p in find_ship_surfaces(site)}
    assert 'cups.html' in got          # the previously-ungated root pages
    assert 'support.html' in got
    assert 'index.html' in got
    assert 'guides/iv-flavor-guide/index.html' in got
    assert 'azumarill-great-league/index_m1_a_b.html' in got
    assert 'azumarill-great-league/scores.json.gz' not in got


def test_both_gates_call_the_shared_enumerator(monkeypatch):
    """Object identity, not import text: swap the shared function and both
    gates' wrappers must hand back the swapped value. Survives an isort, an
    added import name, or an alias; fails the moment a gate stops routing."""
    sentinel = [Path('sentinel.html')]
    monkeypatch.setattr(ship_surfaces, 'find_ship_surfaces', lambda root: sentinel)
    for name in _GATES:
        mod = importlib.import_module(name)
        assert mod._find_ship_surfaces() == sentinel, name


def test_no_gate_re_open_codes_the_page_enumeration():
    """Absence half, tolerantly: neither gate may glob for index pages
    itself, in any spelling."""
    for name in _GATES:
        hits = _open_coded_page_globs((_SCRIPTS / f'{name}.py').read_text())
        assert not hits, (name, hits)


def test_the_page_glob_scanner_actually_catches_a_respelling():
    """Guard the guard, and the positive control in one: the scan must fire
    on every spelling of the retired private enumeration (the double-quoted
    one slipped past the old substring pin on 2026-08-09), and it must still
    find the glob in the module that is SUPPOSED to own it -- otherwise
    'no gate open-codes it' would also pass in a world where nobody
    enumerates ship surfaces at all."""
    for snippet in ("sub.rglob('index*.html')",
                    'sub.rglob("index*.html")',
                    "sub.glob( 'index*.html' )",
                    "sub.rglob('index' '*.html')",
                    "sub.glob('index_m*.html')",
                    # ...and the escapes an adversarial pass found on
                    # 2026-08-09: a leading path component, an inert `f`
                    # prefix, a `+` join.
                    "sub.glob('*/index*.html')",
                    "sub.rglob('**/index*.html')",
                    "sub.glob('./index*.html')",
                    "sub.glob(f'index*.html')",
                    "sub.glob('index' + '*.html')",
                    "list(sub.rglob('index*.html'))"):
        assert _open_coded_page_globs(snippet), snippet
    assert not _open_coded_page_globs("d.glob('*.html')\nd.glob('scores.json.gz')")
    # A genuinely dynamic glob is not a literal respelling.
    assert not _open_coded_page_globs("d.glob(f'{name}.html')")
    owner = _open_coded_page_globs((_SCRIPTS / 'ship_surfaces.py').read_text())
    assert owner, 'ship_surfaces no longer enumerates index pages'
