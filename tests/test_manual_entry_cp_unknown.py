"""A manual collection entry has no CP, and the page must not invent one.

The manual-entry form in the dive's collection panel (scripts/deep_dive.py,
the ``collection-manual`` block) has fields for species, Atk/Def/HP IVs,
level and the shadow flag -- and NO CP field. ``readManualForm()`` therefore
stores ``cp: 0``.

Pre-fix value (2026-09-22): the collection table printed that straight
through as ``<b>CP 0</b>``, and the "Yours" hover as ``CP0``. "CP 0" is not
"unknown" -- it reads as a real current CP of zero, which is both impossible
in game and the worst possible sort key.

Fix: one ``cpText()`` helper that prints ``--`` for any non-positive or
non-finite cp, used at every site that prints ``mon.cp``. The which-build
owner list already had this rule inline (``!(mon.cp > 0)``, 2026-09-17); this
is that rule at the remaining print sites.

Chose the print-side fix over adding a CP input to the form: it is the
smaller change, it also covers a malformed CSV row (cp 0 from a bad export is
equally unknown), and it needs no per-record provenance flag.
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tests'))

from test_win_boundary import strip_js  # noqa: E402

JS_PATH = REPO / 'scripts' / 'deep_dive_engine.js'

# A "CP" LABEL immediately followed by a raw ``<x>.mon.cp``: i.e. a print of
# the current CP to the reader. Tolerant on the receiver name and on spacing.
#
# Run against the RAW source, not strip_js output, and that is deliberate.
# strip_js blanks string literals -- which is exactly the ``'CP '`` label that
# separates a PRINT of the CP from the legitimate remaining raw use, the
# numeric ``data-sort="' + rc.mon.cp + '"`` sort key that must stay a number.
# Stripped, the two are indistinguishable. The structural half of the policy
# is covered by the strip_js-based scans below.
_CP_LABEL_PRINT = re.compile(r"CP\s*'\s*\+\s*\w+\.mon\.cp\b")


def _code():
    """The JS with comments, strings and regex literals blanked out.

    Required here: the docstring-ish comments in the engine and this very
    fix's own comment both contain the words being scanned for, and the
    `'CP '` literals are strings. A raw-text regex would match those and
    report a false positive.
    """
    return strip_js(JS_PATH.read_text())


def test_no_site_prints_a_raw_mon_cp_after_a_cp_label():
    """The absence pin.

    Pre-fix there were five such sites: the single-mon "Yours" hover, the
    multi-mon CP list, both anchor-bullet ``title`` builders, and the
    collection table's Current CP cell.
    """
    raw = JS_PATH.read_text()
    offenders = []
    for m in _CP_LABEL_PRINT.finditer(raw):
        line = raw[:m.start()].count('\n') + 1
        offenders.append((line, m.group(0).strip()))
    assert not offenders, (
        f'{len(offenders)} site(s) print a raw mon.cp after a "CP" label '
        f'instead of going through cpText(): {offenders}. A manual entry has '
        f'cp 0 and would print "CP 0".')


def test_the_numeric_sort_key_still_uses_the_raw_cp():
    """The deliberate remaining raw use, pinned so the fix is not over-applied.

    The Current CP column sorts on ``data-sort``, which must stay a NUMBER --
    an unknown-CP row sorting as 0 groups the unknowns together, which is the
    wanted behaviour. Only the visible cell gets the placeholder.
    """
    raw = JS_PATH.read_text()
    assert re.search(r"data-sort=\"'\s*\+\s*rc\.mon\.cp", raw), (
        'the Current CP sort key no longer uses the raw numeric cp')


def test_the_cp_label_scanner_matches_the_pre_fix_source():
    """Positive control for the absence pin above.

    An absence assertion is worthless if its regex quietly stops matching.
    Feeds it the literal pre-fix expressions.
    """
    pre_fix = [
        "h += '<td data-sort=\"' + rc.mon.cp + '\"><b>CP ' + rc.mon.cp + '</b></td>';",
        "lines.push('  <b>CP ' + rcL.mon.cp + '</b>' +",
        "return 'CP' + h.mon.cp + ' ' + h.mon.atk_iv;",
    ]
    for src in pre_fix:
        assert _CP_LABEL_PRINT.search(src), (
            f'the scanner no longer matches the pre-fix source it exists to '
            f'catch: {src}')
    # And it must NOT fire on the corrected form -- which still carries a raw
    # rc.mon.cp in its data-sort attribute, the case that makes this scanner
    # label-anchored rather than a bare "raw mon.cp" search.
    post_fix = ("h += '<td data-sort=\"' + rc.mon.cp + '\"><b>CP ' "
                "+ cpText(rc.mon.cp) + '</b></td>';")
    assert not _CP_LABEL_PRINT.search(post_fix)


def test_cptext_exists_and_every_cp_print_routes_through_it():
    """The positive half: the helper is defined and actually used.

    Floor set BELOW today's count (5 call sites) so this cannot pass because
    the scan silently found nothing.
    """
    code = _code()
    assert re.search(r'function\s+cpText\s*\(', code), (
        'cpText() is gone; the CP-unknown rule has no single home')
    calls = len(re.findall(r'\bcpText\s*\(\s*\w+\.mon\.cp\s*\)', code))
    assert calls >= 4, (
        f'only {calls} cpText(mon.cp) call sites found; there were 5 when '
        f'this was written')


def test_the_which_build_owner_list_still_skips_an_unknown_cp():
    """The pre-existing instance of the same rule (2026-09-17).

    It guards with ``!(mon.cp > 0)`` rather than cpText because it OMITS the
    CP entirely rather than printing a placeholder. Pinned so a future
    "unify these" pass has to notice the two behaviours are different on
    purpose.
    """
    code = _code()
    assert re.search(r'!\s*\(\s*mon\.cp\s*>\s*0\s*\)', code), (
        'the which-build owner list no longer guards against cp 0')


@pytest.mark.parametrize('cp,expected', [
    (0, '--'), (-5, '--'), (None, '--'), (float('nan'), '--'),
    (float('inf'), '--'), (1500, '1500'), (10, '10'),
])
def test_cptext_semantics_under_node(cp, expected):
    """Run the shipped helper itself, so the contract is executed not read."""
    import json
    import shutil
    import subprocess
    if shutil.which('node') is None:
        pytest.skip('node not installed')
    src = JS_PATH.read_text()
    start = src.index('function cpText(')
    end = src.index('\n}', start) + 2
    if cp is None:
        arg = 'null'
    elif cp != cp:
        arg = 'NaN'
    elif cp == float('inf'):
        arg = 'Infinity'
    else:
        arg = json.dumps(cp)
    out = subprocess.run(
        ['node', '-e', src[start:end] + f'\nconsole.log(cpText({arg}));'],
        capture_output=True, text=True, check=True)
    assert out.stdout.strip() == expected


@pytest.mark.render
def test_the_rendered_dive_page_ships_the_cp_unknown_rule(small_dive_html):
    """The rendered pin: the fix has to reach the artifact, not just the file.

    scripts/deep_dive_engine.js is inlined into the page by deep_dive.py, and
    an emitter that stopped including this part of the engine would leave the
    source tests above green while shipping the old behaviour.
    """
    assert 'function cpText(' in small_dive_html, (
        'the shipped dive page does not contain cpText(); the CP-unknown '
        'rule never reaches the reader')
    assert 'cpText(rc.mon.cp)' in small_dive_html
    # The pre-fix markup must be gone from the shipped page.
    assert "<b>CP ' + rc.mon.cp + '</b>" not in small_dive_html


@pytest.mark.render
def test_the_manual_form_still_has_no_cp_field(small_dive_html):
    """Why cpText exists at all -- and the trigger to revisit it.

    If a CP input is ever added to the manual form, readManualForm() should
    read it and this whole placeholder path becomes reachable only for a
    malformed CSV row. This test going red is that signal, not a failure.
    """
    for field in ('manual-atk', 'manual-def', 'manual-hp', 'manual-level',
                  'manual-shadow', 'manual-species'):
        assert f'id="{field}"' in small_dive_html, field
    assert 'id="manual-cp"' not in small_dive_html, (
        'the manual form grew a CP field; readManualForm() should now read '
        'it instead of hardcoding cp: 0 (see tests/test_manual_entry_cp_'
        'unknown.py)')
