"""Pins for scripts/replay_render_diff.py's pure helpers (no render).

The harness is the byte-diff gate every behavior-preserving render change
must pass, so a silent regression in its normalization would let a real
page change through (too much normalized) or fail every check (too
little). These tests pin the helpers on synthetic strings only; the
render path itself is exercised by running the harness.
"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    'replay_render_diff', REPO_ROOT / 'scripts' / 'replay_render_diff.py')
rrd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rrd)


def _toggle(cid):
    # Same markup deep_dive_rendering.cover_toggle_html emits.
    return (f'<input type="checkbox" class="cover-toggle" id="{cid}">'
            f'<span class="cover-rest">, x</span>'
            f'<label class="cover-more" for="{cid}">').encode()


def test_cover_toggle_markup_matches_the_id_regex():
    """Positive control: the real emitter's markup is what the regex
    targets. If cover_toggle_html's attribute shape changes, mode B would
    silently stop canonicalizing; this fails instead."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / 'scripts'))
    sys.path.insert(0, str(REPO_ROOT / 'src'))
    import deep_dive_rendering
    html = deep_dive_rendering.cover_toggle_html('h', ', t', 1, 'fdet7')
    out, n = rrd.canonicalize_ids(html.encode())
    assert n == 1
    assert b'id="fdet1"' in out and b'for="fdet1"' in out
    assert b'fdet7' not in out


def test_vintage_rendered_at_is_normalized():
    a = b'engine_hash = "abc"\nrendered_at     = "2026-09-25T13:01:02"\n'
    b = b'engine_hash = "abc"\nrendered_at     = "2026-09-26T08:00:59"\n'
    assert a != b
    assert rrd.normalize(a) == rrd.normalize(b)
    assert b'<RENDERED_AT>' in rrd.normalize(a)
    # Other vintage fields are NOT normalized: an engine-hash change must
    # still differ.
    c = a.replace(b'"abc"', b'"abd"')
    assert rrd.normalize(a) != rrd.normalize(c)


def test_path_placeholders_longest_first():
    root = '/scratch/run1/tinkaton_great'
    data = f'src="{root}/website/x.js" other="/scratch/run1"'.encode()
    out = rrd.normalize(data, [('/scratch/run1', '<A>'),
                               (root, '<RENDER_ROOT>')])
    assert out == b'src="<RENDER_ROOT>/website/x.js" other="<A>"'


def test_normalize_leaves_ordinary_bytes_alone():
    data = b'<div id="fdet3">rendered_at 2026-09-25</div>'
    assert rrd.normalize(data) == data


def test_canonicalize_ids_renumbers_in_document_order_per_prefix():
    base = _toggle('fdet1') + _toggle('cm2') + _toggle('fdet3')
    shifted = _toggle('fdet41') + _toggle('cm17') + _toggle('fdet42')
    cb, nb = rrd.canonicalize_ids(base)
    cs, ns = rrd.canonicalize_ids(shifted)
    assert cb == cs
    assert nb == ns == 3
    assert b'id="fdet1"' in cb and b'id="fdet2"' in cb and b'id="cm1"' in cb


def test_canonicalize_ids_handles_escaped_quotes_and_all_prefixes():
    data = (b'id=\\"sb9\\" for=\\"sb9\\" id="flip5" for="flip5" '
            b'id="cm8" id="fdet2"')
    out, n = rrd.canonicalize_ids(data)
    assert n == 4
    assert out == (b'id=\\"sb1\\" for=\\"sb1\\" id="flip1" for="flip1" '
                   b'id="cm1" id="fdet1"')


def test_canonicalize_ids_keeps_a_duplicate_id_visible():
    # A real bug (two toggles sharing one id) must still differ from a
    # correct page after canonicalization.
    good = _toggle('fdet1') + _toggle('fdet2')
    dup = _toggle('fdet5') + _toggle('fdet5')
    assert rrd.canonicalize_ids(good)[0] != rrd.canonicalize_ids(dup)[0]


def test_canonicalize_ids_ignores_other_ids_and_content_changes():
    a = b'<div id="flipper3"></div><div id="dd-cm2x"></div>' + _toggle('cm4')
    out, n = rrd.canonicalize_ids(a)
    assert n == 1
    assert b'id="flipper3"' in out and b'id="dd-cm2x"' in out
    # A content change next to renumbered ids still differs.
    b = a.replace(b'flipper3', b'flipper4').replace(b'cm4', b'cm9')
    assert rrd.canonicalize_ids(a)[0] != rrd.canonicalize_ids(b)[0]


def test_first_diff_offset():
    assert rrd.first_diff_offset(b'abc', b'abc') is None
    assert rrd.first_diff_offset(b'abc', b'abd') == 2
    assert rrd.first_diff_offset(b'ab', b'abc') == 2
    big = b'x' * 200_000
    assert rrd.first_diff_offset(big + b'a', big + b'b') == 200_000
    assert rrd.first_diff_offset(big, big[:-1] + b'y') == 199_999


def test_diff_excerpt_is_capped_and_rebased():
    a = b'\n'.join(b'line %d' % i for i in range(1000))
    b = a.replace(b'line 700', b'LINE 700')
    ex = rrd.diff_excerpt(a, b)
    assert 0 < len(ex) <= rrd.DIFF_EXCERPT_LINES
    assert '-line 700' in ex and '+LINE 700' in ex
    hunk = [ln for ln in ex if ln.startswith('@@')][0]
    assert '-698' in hunk  # 1-based line 701 minus 3 context lines
    long_a = b'a' * 5000
    long_b = b'b' * 5000
    ex2 = rrd.diff_excerpt(long_a, long_b)
    assert all(len(ln) < rrd.DIFF_LINE_CLIP + 40 for ln in ex2)


def test_blob_label():
    assert rrd.blob_label(
        'userdata/replay/20260920_180117_Tinkaton_great.replay.pkl.gz'
    ) == 'tinkaton_great'
    assert rrd.blob_label(
        '20260921_191707_Cramorant_ultra.replay.pkl.gz') == 'cramorant_ultra'
    assert rrd.blob_label(
        '20260901_000000_Sableye_shadow_great.replay.pkl.gz'
    ) == 'sableye_shadow_great'


def test_out_dir_inside_repo_is_refused(tmp_path):
    import pytest
    with pytest.raises(SystemExit) as e:
        rrd._check_out_dir(REPO_ROOT / 'userdata' / 'render_diff_probe')
    assert e.value.code == 2
    assert not (REPO_ROOT / 'userdata' / 'render_diff_probe').exists()
    # Outside the repo is fine, and marks the dir as owned.
    out = rrd._check_out_dir(tmp_path / 'o')
    assert (out / rrd.MARKER).exists()
    # A foreign non-empty dir is refused.
    (tmp_path / 'foreign').mkdir()
    (tmp_path / 'foreign' / 'f').write_text('x')
    with pytest.raises(SystemExit):
        rrd._check_out_dir(tmp_path / 'foreign')
