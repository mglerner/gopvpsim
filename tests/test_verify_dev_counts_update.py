"""``scripts/verify_dev_counts.py --update`` (derivable sentinels only).

The ``test_count`` sentinel in DEVELOPER_NOTES.md is a serialization
point: every work lane that adds a test has to bump the same line, so
parallel lanes race and churn the same commit.  ``--update`` makes the
bump an explicit, opt-in, once-per-batch operation.

What these tests pin:

  - ``--update`` rewrites only DERIVABLE keys, in place, printing
    ``old -> new``, and leaves the rest of the file byte-identical.
  - the rewritten line still round-trips through ``_parse_sentinels``
    (i.e. the sentinel format is unchanged, so ``build_guides``'s
    identical regex keeps working).
  - the no-change case writes nothing at all.
  - WITHOUT ``--update`` the exact-match gate is untouched: drift still
    exits 1 and the file is never written.

Every test drives a temp copy via ``monkeypatch.setattr(mod,
'DEV_NOTES_PATH', ...)`` -- the real DEVELOPER_NOTES.md is never read
or written here, and the (slow, subprocess-pytest) derivations are
monkeypatched out.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / 'scripts' / 'verify_dev_counts.py'


def _load_module():
    spec = importlib.util.spec_from_file_location(
        'verify_dev_counts_under_test', SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load_module()


NOTES_TEMPLATE = """# Developer notes (fixture)

Some prose that must survive untouched.

As of today, <!-- sync:test_count -->{test_count}<!-- /sync --> tests collected.
Verified against PvPoke for <!-- sync:pvpoke_matchups_verified -->23<!-- /sync -->
matchups (<!-- sync:pvpoke_cells_verified -->207<!-- /sync --> cells:
<!-- sync:pvpoke_cells_exact -->172<!-- /sync --> exact).

- **Type effectiveness**: All <!-- sync:type_chart_cells_verified -->{type_cells}<!-- /sync --> matchups match

<!-- sync:pvpoke_bugs_documented -->5<!-- /sync --> bugs documented below.

Trailing prose, also untouched.
"""


def _write_notes(tmp_path, *, test_count=1733, type_cells=324):
    path = tmp_path / 'DEVELOPER_NOTES.md'
    path.write_text(NOTES_TEMPLATE.format(
        test_count=test_count, type_cells=type_cells))
    return path


def _run(mod, monkeypatch, notes_path, argv, *,
         live_test_count=1733, live_type_cells=324):
    monkeypatch.setattr(mod, 'DEV_NOTES_PATH', notes_path)
    monkeypatch.setattr(mod, '_derive_test_count', lambda: live_test_count)
    monkeypatch.setattr(mod, '_derive_type_chart_cells',
                        lambda: live_type_cells)
    monkeypatch.setattr(sys, 'argv', ['verify_dev_counts.py', *argv])
    return mod.main()


def test_update_rewrites_drifted_test_count(mod, tmp_path, monkeypatch, capsys):
    notes = _write_notes(tmp_path, test_count=1733)
    before = notes.read_text()

    rc = _run(mod, monkeypatch, notes, ['--update'], live_test_count=1740)
    out = capsys.readouterr().out

    assert rc == 0
    assert '1733 -> 1740' in out
    after = notes.read_text()
    assert '<!-- sync:test_count -->1740<!-- /sync -->' in after
    # Nothing else in the file moved: the ONLY textual difference is the
    # one sentinel value.
    assert after == before.replace(
        '<!-- sync:test_count -->1733<!-- /sync -->',
        '<!-- sync:test_count -->1740<!-- /sync -->')


def test_update_rewrites_type_chart_cells_too(mod, tmp_path, monkeypatch,
                                              capsys):
    notes = _write_notes(tmp_path, type_cells=324)

    rc = _run(mod, monkeypatch, notes, ['--update'], live_type_cells=306)
    out = capsys.readouterr().out

    assert rc == 0
    assert 'type_chart_cells_verified: 324 -> 306' in out
    assert ('<!-- sync:type_chart_cells_verified -->306<!-- /sync -->'
            in notes.read_text())


def test_updated_sentinel_round_trips_through_parser(mod, tmp_path,
                                                     monkeypatch, capsys):
    notes = _write_notes(tmp_path, test_count=1733)
    _run(mod, monkeypatch, notes, ['--update'], live_test_count=1740)
    capsys.readouterr()

    # The format the rewrite emits must be the format the readers expect
    # (_parse_sentinels here; build_guides._load_verification_counts uses
    # an identical regex).
    parsed = mod._parse_sentinels(notes.read_text())
    assert parsed['test_count'] == 1740
    # ... and a second --update is then a clean no-op.
    rc = _run(mod, monkeypatch, notes, ['--update'], live_test_count=1740)
    assert rc == 0
    assert '->' not in capsys.readouterr().out


def test_update_no_change_leaves_file_untouched(mod, tmp_path, monkeypatch,
                                                capsys):
    notes = _write_notes(tmp_path, test_count=1733, type_cells=324)
    before = notes.read_bytes()
    mtime_before = notes.stat().st_mtime_ns

    rc = _run(mod, monkeypatch, notes, ['--update'],
              live_test_count=1733, live_type_cells=324)
    out = capsys.readouterr().out

    assert rc == 0
    assert notes.read_bytes() == before
    # Not merely equal content -- the file is not rewritten at all.
    assert notes.stat().st_mtime_ns == mtime_before
    assert '->' not in out
    assert 'test_count: 1733 (matches live)' in out


def test_without_update_drift_is_still_a_gate(mod, tmp_path, monkeypatch,
                                              capsys):
    notes = _write_notes(tmp_path, test_count=1733)
    before = notes.read_bytes()

    rc = _run(mod, monkeypatch, notes, [], live_test_count=1740)
    err = capsys.readouterr().err

    assert rc == 1
    assert 'test_count: sentinel 1733 != live 1740' in err
    assert notes.read_bytes() == before


def test_without_update_quiet_agreement_is_silent(mod, tmp_path, monkeypatch,
                                                  capsys):
    notes = _write_notes(tmp_path)
    rc = _run(mod, monkeypatch, notes, ['--quiet'])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == ''
    assert captured.err == ''


def test_update_never_touches_non_derivable_keys(mod, tmp_path, monkeypatch,
                                                 capsys):
    # An implausible non-derivable sentinel is a problem --update cannot
    # fix: it must still fail, and the bad value must stay put.
    notes = _write_notes(tmp_path)
    notes.write_text(notes.read_text().replace(
        '<!-- sync:pvpoke_bugs_documented -->5<!-- /sync -->',
        '<!-- sync:pvpoke_bugs_documented -->0<!-- /sync -->'))

    rc = _run(mod, monkeypatch, notes, ['--update'], live_test_count=1740)
    captured = capsys.readouterr()

    assert rc == 1
    assert ('pvpoke_bugs_documented: implausible sentinel value 0'
            in captured.err)
    text = notes.read_text()
    assert '<!-- sync:pvpoke_bugs_documented -->0<!-- /sync -->' in text
    # The derivable key next to it was still fixed.
    assert '<!-- sync:test_count -->1740<!-- /sync -->' in text


def test_update_missing_derivable_sentinel_still_fails(mod, tmp_path,
                                                       monkeypatch, capsys):
    notes = _write_notes(tmp_path)
    notes.write_text(notes.read_text().replace(
        '<!-- sync:test_count -->1733<!-- /sync -->', '(count removed)'))

    rc = _run(mod, monkeypatch, notes, ['--update'], live_test_count=1740)
    err = capsys.readouterr().err

    # --update rewrites sentinels; it does not invent missing ones.
    assert rc == 1
    assert 'missing sentinel: sync:test_count' in err
    assert '1740' not in notes.read_text()


def test_rewrite_sentinel_preserves_padding_and_other_keys(mod):
    text = ('a <!-- sync:test_count -->  12  <!-- /sync --> b '
            '<!-- sync:pvpoke_cells_verified -->207<!-- /sync --> c')
    new, n = mod._rewrite_sentinel(text, 'test_count', 99)
    assert n == 1
    assert new == ('a <!-- sync:test_count -->  99  <!-- /sync --> b '
                   '<!-- sync:pvpoke_cells_verified -->207<!-- /sync --> c')


def test_rewrite_sentinel_will_not_cross_a_missing_closing_marker(mod):
    # A hand-edit that drops a closing <!-- /sync --> must NOT let the
    # rewrite run on to the next key's marker and swallow the prose (and
    # the following sentinel) in between.
    text = ('<!-- sync:test_count -->1733\n'
            'some important prose here\n'
            '<!-- sync:pvpoke_cells_verified -->207<!-- /sync -->\n')
    new, n = mod._rewrite_sentinel(text, 'test_count', 1766)
    assert n == 0
    assert new == text


def test_update_reports_a_malformed_sentinel_instead_of_eating_prose(
        mod, tmp_path, monkeypatch, capsys):
    notes = _write_notes(tmp_path)
    notes.write_text(notes.read_text().replace(
        '<!-- sync:test_count -->1733<!-- /sync -->',
        '<!-- sync:test_count -->1733'))
    before = notes.read_text()

    rc = _run(mod, monkeypatch, notes, ['--update'], live_test_count=1766)
    err = capsys.readouterr().err

    assert rc == 1
    assert 'could not rewrite sentinel' in err
    # Nothing between the orphaned opener and the next key was touched.
    assert notes.read_text() == before


def test_rewrite_sentinel_does_not_double_whitespace_only_padding(mod):
    text = 'x <!-- sync:test_count -->   <!-- /sync --> y'
    new, n = mod._rewrite_sentinel(text, 'test_count', 99)
    assert n == 1
    assert new == 'x <!-- sync:test_count -->   99<!-- /sync --> y'
    assert mod._parse_sentinels(new)['test_count'] == 99


def test_rewrite_sentinel_updates_every_occurrence(mod):
    text = ('<!-- sync:test_count -->12<!-- /sync --> ... '
            'and again <!-- sync:test_count -->12<!-- /sync -->')
    new, n = mod._rewrite_sentinel(text, 'test_count', 99)
    assert n == 2
    assert '12' not in new
    assert new.count('<!-- sync:test_count -->99<!-- /sync -->') == 2
