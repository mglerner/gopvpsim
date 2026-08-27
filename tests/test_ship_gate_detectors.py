"""Positive AND negative controls for the two detector-style ship gates.

``scripts/run_ship_gates.py`` runs the roster on every publish path, but two
of its members had zero behavioral tests -- only their filenames appeared, in
``tests/test_ship_gate_roster.py``.  A gate that stops detecting is
indistinguishable from a clean tree: it just prints SUCCESS.  The roster
comment records the precedent directly (verify_dev_counts.py was once found
"uncalled anywhere and a month stale"), so gates in this repo demonstrably
rot.  2026-08-09 test-suite review, blind-spots E3/E4.

Everything here runs against hand-written HTML in ``tmp_path`` and asserts on
the RETURNED hit/error lists.  Deliberately NOT via ``main()``: ``main(--ship)``
walks the real ``userdata/website`` tree, which makes the result depend on
whether this machine has ever run a dive.

Each gate gets both directions -- a page that must trip it and a page that
must not -- so neither "detects nothing" nor "detects everything" can pass.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import verify_article_links  # noqa: E402
import verify_no_unicode_dashes as vnud  # noqa: E402

EM = '—'   # em dash
EN = '–'   # en dash


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body)
    return p


# ---------------------------------------------------------------------------
# verify_no_unicode_dashes.scan_file -- SKIP_TEXT_IN / USER_VISIBLE_ATTRS
# ---------------------------------------------------------------------------

def test_dash_gate_flags_body_text(tmp_path):
    page = _write(tmp_path, 'body.html',
                  f'<html><body><p>Bastiodon {EM} the wall</p></body></html>')
    hits = vnud.scan_file(page)
    assert len(hits) == 1, hits
    kind, _lineno, _col, container, _snippet = hits[0]
    assert kind == 'em'
    assert container == 'p'


def test_dash_gate_flags_en_dash_too(tmp_path):
    page = _write(tmp_path, 'en.html',
                  f'<html><body><p>ranks 3{EN}5 overall</p></body></html>')
    kinds = [h[0] for h in vnud.scan_file(page)]
    assert kinds == ['en']


def test_dash_gate_flags_user_visible_attributes(tmp_path):
    """title / alt / aria-label render to users, so they are in scope."""
    page = _write(tmp_path, 'attrs.html', (
        '<html><body>'
        f'<span title="win rate {EM} shielded">x</span>'
        f'<img src="a.png" alt="chart {EM} great league">'
        f'<button aria-label="close {EM} dialog">x</button>'
        '</body></html>'
    ))
    containers = sorted(h[3] for h in vnud.scan_file(page))
    assert containers == ['<button aria-label=...>', '<img alt=...>',
                          '<span title=...>']


def test_dash_gate_ignores_machine_attributes(tmp_path):
    """href/class/data-* carry machine strings; dashes there are not prose."""
    page = _write(tmp_path, 'machine.html', (
        '<html><body>'
        f'<a href="p.html?q={EM}" class="a{EM}b" data-note="{EM}">ok</a>'
        '</body></html>'
    ))
    assert vnud.scan_file(page) == []


def test_dash_gate_ignores_code_and_pre_and_style(tmp_path):
    """SKIP_TEXT_IN: source-like text may legitimately carry Unicode dashes.

    This is the half that fails SILENTLY if someone widens the skip set --
    the gate keeps passing and the prose rule quietly stops being enforced.

    ``<script>`` used to be in this test. It moved out when the gate learned
    to read inlined app JS (TODO.md "Ship-gate gap"): script *code* is still
    skipped, but script *string literals* are prose and are now scanned --
    see the JS block at the bottom of this file.
    """
    page = _write(tmp_path, 'skips.html', (
        '<html><body>'
        f'<code>a {EM} b</code>'
        f'<pre>$ tool {EM} flag</pre>'
        f'<style>/* {EM} */</style>'
        '</body></html>'
    ))
    assert vnud.scan_file(page) == []


def test_dash_gate_still_fires_after_a_skipped_element_closes(tmp_path):
    """The skip is scoped to the element, not sticky for the rest of the page.

    A stack-handling regression that never popped would silence every gate
    hit downstream of the first <code> block on a page -- and every real dive
    page opens with inline <script>.
    """
    page = _write(tmp_path, 'after.html', (
        '<html><body>'
        f'<p>See <code>--flag {EM} x</code> {EM} the trailing prose</p>'
        '</body></html>'
    ))
    hits = vnud.scan_file(page)
    assert [(h[0], h[3]) for h in hits] == [('em', 'p')]


def test_dash_gate_is_clean_on_ascii_only_page(tmp_path):
    """Negative control: the detector must not fire on everything."""
    page = _write(tmp_path, 'clean.html', (
        '<html><body><p>Bastiodon - the wall</p>'
        '<span title="win rate, shielded">x</span></body></html>'
    ))
    assert vnud.scan_file(page) == []


# ---------------------------------------------------------------------------
# verify_no_unicode_dashes -- prose GENERATED by inlined <script> templates
#
# TODO.md "Ship-gate gap (found by the 2026-08-17 thievul pre-publish
# review)": the gate parsed page HTML and skipped <script> wholesale, so the
# joint-IV robustness pages -- which render ~100% of their prose from an
# inlined app bundle -- got a clean bill *regardless of content*.  Every test
# below fails against the pre-change gate for the positive cases and would
# start failing if a carve-out grew for the negative ones.
# ---------------------------------------------------------------------------

def _js_page(tmp_path, name, js):
    return _write(tmp_path, name,
                  f'<html><body><div id="app"></div><script>\n{js}\n'
                  '</script></body></html>')


def test_js_literal_extractor_finds_only_string_literals():
    """Self-test for the extractor itself (the inverse of ``strip_js``).

    Without this, an extractor bug would silently turn every script-side
    assertion below into a test that can never fail: literals it stops
    returning are literals the gate stops reading.  Mirrors
    ``tests/test_win_boundary.test_strip_js_detects_only_real_code``.
    """
    src = (
        "var a = 'single';\n"                     # 1: single-quoted
        'var b = "dou\\"ble";\n'                  # 2: escaped inner quote
        "// comment 'not a literal'\n"            # 3: line comment
        "/* block 'not a literal' */\n"           # 4: block comment
        "var r = /'not'|a[/]literal/g;\n"         # 5: regex, quote + class
        "var t = `tpl ${x + 'nested'} tail`;\n"   # 6: template + interpolation
        "console.warn('dev only');\n"             # 7: console argument
        "el.textContent = 'shown';\n"             # 8: plain assignment
    )
    lits = vnud.js_string_literals(src)
    assert [seg for _off, seg, _callee in lits] == [
        'single', 'dou\\"ble', 'tpl ', 'nested', ' tail', 'dev only', 'shown']
    # Offsets must point at the real position of the segment in the source.
    for off, seg, _callee in lits:
        assert src[off:off + len(seg)] == seg
    # And the callee is tracked, so the console carve-out has something to
    # key on without a backwards regex over raw source.
    by_seg = {seg: callee for _off, seg, callee in lits}
    assert by_seg['dev only'] == 'console.warn'
    assert by_seg['shown'] == ''
    assert by_seg['nested'] == ''


def test_dash_gate_flags_a_dash_in_inlined_script_prose(tmp_path):
    """POSITIVE CONTROL for the closed gap.

    This is the exact shape the thievul pages ship: the sentence exists only
    as a JS string literal, so the pre-change gate returned [] for this page.
    """
    page = _js_page(tmp_path, 'js_prose.html',
                    f"el.innerHTML = 'Thievul {EM} the IV-decided seat';")
    hits = vnud.scan_file(page)
    assert len(hits) == 1, hits
    kind, _lineno, _col, container, snippet = hits[0]
    assert kind == 'em'
    assert container == '<script> string literal'
    assert 'IV-decided seat' in snippet


def test_dash_gate_flags_template_literal_prose(tmp_path):
    """Template literals are how most generated prose is actually spelled."""
    page = _js_page(tmp_path, 'tpl.html',
                    'el.innerHTML = `${name} wins ' + EN + ' 3 of 5 legs`;')
    assert [h[0] for h in vnud.scan_file(page)] == ['en']


def test_dash_gate_reports_the_right_line_for_a_script_hit(tmp_path):
    """A hit nobody can locate is a hit nobody fixes: the reported line must
    be the file line, not an offset into the script body."""
    page = _write(tmp_path, 'lines.html',
                  '<html>\n<body>\n<script>\nvar a = 1;\n'
                  f"var b = 'prose {EM} here';\n</script>\n</body></html>\n")
    hits = vnud.scan_file(page)
    assert len(hits) == 1, hits
    assert hits[0][1] == 5


def test_dash_gate_sees_render_equivalent_dash_spellings_in_js(tmp_path):
    """``'\\u2014'`` and ``'&mdash;'`` render as an em dash just like the raw
    character does.  The HTML-text side gets entity decoding for free from
    ``convert_charrefs=True``; script bodies arrive raw, so the literal must
    be decoded or these are silent ways past the gate."""
    page = _js_page(tmp_path, 'spellings.html',
                    "a.innerHTML = 'esc \\u2014 x';\n"
                    "b.innerHTML = 'ent &mdash; y';\n"
                    "c.innerHTML = 'num &#8211; z';")
    assert sorted(h[0] for h in vnud.scan_file(page)) == ['em', 'em', 'en']


def test_dash_gate_ignores_js_comments_and_regex_sources(tmp_path):
    """NEGATIVE CONTROL / documented scope line.

    Only STRING LITERALS are in scope.  Comments are developer text that
    never reaches a reader, and a regex source is machine-matching, not
    prose.  A gate that flagged either would be untenable on the inlined
    app bundles and would get switched off.
    """
    page = _js_page(tmp_path, 'js_code.html', (
        f"// design note {EM} keep the seat labels short\n"
        f"/* block note {EM} ditto */\n"
        f"var clean = s.replace(/{EM}/g, '-');\n"
        "var ok = 'plain ASCII prose';"
    ))
    assert vnud.scan_file(page) == []


def test_dash_gate_ignores_console_arguments(tmp_path):
    """Documented carve-out: ``console.*`` is developer-console output.

    The one such string in the shipped tree is
    ``scripts/deep_dive_engine.js:984``
    (``console.error('POGOCollection module missing ... ')``), which reaches
    210 shipped pages.  It is not reader-visible prose, so it is out of
    scope -- but the carve-out is keyed on the CALLEE, so the identical
    sentence assigned to innerHTML still fires.
    """
    page = _js_page(tmp_path, 'console.html',
                    f"console.error('module missing {EM} paste-box dead');")
    assert vnud.scan_file(page) == []

    same_words = _js_page(tmp_path, 'shown.html',
                          f"el.innerHTML = 'module missing {EM} paste-box dead';")
    assert len(vnud.scan_file(same_words)) == 1


def test_dash_gate_skips_vendored_bundles_but_not_unknown_ones(tmp_path):
    """Documented carve-out: the inlined Plotly bundle carries genuine em/en
    dashes (i18n table, a GLSL shader comment).  It is not our prose and we
    do not edit it.

    The second half is the half that matters: an UNRECOGNIZED third-party
    bundle must still fire, so this stays a named exception rather than a
    'big minified script' heuristic that would swallow our own app JS.
    """
    banner = ('/**\n* plotly.js v2.35.2\n* Copyright 2012-2024, Plotly, Inc.\n'
              '* Licensed under the MIT license\n*/\n')
    vendored = _js_page(tmp_path, 'vendor.html',
                        banner + f"var i18n = {{dash: '{EM}'}};")
    assert vnud.scan_file(vendored) == []

    banner_other = ('/**\n* somelib.js v1.0\n* Copyright 2026\n*/\n')
    unknown = _js_page(tmp_path, 'unknown.html',
                       banner_other + f"var i18n = {{dash: '{EM}'}};")
    assert len(vnud.scan_file(unknown)) == 1


def test_dash_gate_scans_every_script_on_a_page(tmp_path):
    """Real pages carry 4-6 script blocks; a scanner that only kept the first
    (or only the last) would be blind to most of the app."""
    page = _write(tmp_path, 'multi.html', (
        '<html><body>'
        f"<script>a.innerHTML = 'one {EM} x';</script>"
        '<p>ascii prose</p>'
        f"<script>b.innerHTML = 'two {EN} y';</script>"
        '</body></html>'
    ))
    assert sorted(h[0] for h in vnud.scan_file(page)) == ['em', 'en']


# ---------------------------------------------------------------------------
# verify_article_links.verify_file -- three independent detectors
# ---------------------------------------------------------------------------

def _verify(path):
    errors, hrefs = verify_article_links.verify_file(path, {})
    return errors, hrefs


def test_link_gate_flags_dangling_relative_href(tmp_path):
    page = _write(tmp_path, 'src.html',
                  '<html><body><a href="nope.html">go</a></body></html>')
    errors, hrefs = _verify(page)
    assert hrefs == ['nope.html']
    assert len(errors) == 1, errors
    assert 'path not found' in errors[0]


def test_link_gate_flags_missing_same_file_fragment(tmp_path):
    page = _write(tmp_path, 'frag.html',
                  '<html><body><a href="#nowhere">go</a>'
                  '<div id="somewhere"></div></body></html>')
    errors, _ = _verify(page)
    assert len(errors) == 1, errors
    assert '#nowhere missing in self' in errors[0]


def test_link_gate_flags_missing_fragment_on_another_page(tmp_path):
    _write(tmp_path, 'target.html', '<html><body><p id="here">x</p></body></html>')
    page = _write(tmp_path, 'src.html',
                  '<html><body><a href="target.html#gone">go</a></body></html>')
    errors, _ = _verify(page)
    assert len(errors) == 1, errors
    assert '#gone missing in' in errors[0]


@pytest.mark.parametrize('href,fragment', [
    # _spot_check_external: path must start with /battle/ and carry >= 3
    # segments (verify_article_links.py:148-166).
    ('https://pvpoke.com/rankings/all/1500/overall/', 'unexpected pvpoke.com path'),
    ('https://pvpoke.com/battle/great/', 'truncated pvpoke.com path'),
])
def test_link_gate_flags_malformed_pvpoke_urls(tmp_path, href, fragment):
    page = _write(tmp_path, 'ext.html',
                  f'<html><body><a href="{href}">go</a></body></html>')
    errors, _ = _verify(page)
    assert len(errors) == 1, errors
    assert fragment in errors[0]


def test_link_gate_is_clean_on_a_well_formed_page(tmp_path):
    """Negative control, covering all four _classify branches at once.

    A ``_classify`` regression that routed relative hrefs to 'other' would
    silently disable the entire internal-link detector while leaving every
    positive control above... also green, since they would stop being
    checked. That is exactly why the positive cases assert the SPECIFIC
    error text and this case asserts an empty list on a page that exercises
    an internal link, a same-file anchor, a legitimate bare pvpoke.com
    homepage citation, a well-formed pvpoke battle URL, and a mailto.
    """
    _write(tmp_path, 'target.html', '<html><body><p id="here">x</p></body></html>')
    page = _write(tmp_path, 'clean.html', (
        '<html><body>'
        '<a href="target.html#here">a</a>'
        '<a href="#self">b</a>'
        '<a href="https://pvpoke.com/">c</a>'
        '<a href="https://pvpoke.com/battle/great/bastiodon/11/">d</a>'
        '<a href="mailto:x@example.com">e</a>'
        '<div id="self"></div>'
        '</body></html>'
    ))
    errors, hrefs = _verify(page)
    assert errors == []
    assert len(hrefs) == 5
    assert sorted({verify_article_links._classify(h) for h in hrefs}) == \
        ['anchor', 'external', 'internal', 'other']


def test_link_gate_resolves_a_directory_href_to_its_index(tmp_path):
    """``href="sub/"`` must resolve to ``sub/index.html`` -- the shape every
    dive landing link uses."""
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'index.html').write_text('<html><body>x</body></html>')
    page = _write(tmp_path, 'dir.html',
                  '<html><body><a href="sub/">go</a></body></html>')
    assert _verify(page)[0] == []

    (sub / 'index.html').unlink()
    errors, _ = _verify(page)
    assert len(errors) == 1 and 'path not found' in errors[0]


def test_link_gate_ignores_href_lookalikes_inside_script(tmp_path):
    """The inlined dive JS contains literal ``href=`` inside string
    concatenation; an HTML parser (not a regex) is what keeps that from
    generating thousands of phantom errors."""
    page = _write(tmp_path, 'js.html', (
        '<html><body><script>\n'
        'var s = \'<a href="totally-missing.html">\' + x + "</a>";\n'
        '</script></body></html>'
    ))
    errors, hrefs = _verify(page)
    assert hrefs == []
    assert errors == []


def test_link_gate_reports_unreadable_files_rather_than_passing(tmp_path):
    missing = tmp_path / 'does_not_exist.html'
    errors, hrefs = _verify(missing)
    assert hrefs == []
    assert len(errors) == 1 and 'could not read' in errors[0]
