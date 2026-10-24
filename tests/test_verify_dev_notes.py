"""Gate tests for scripts/verify_dev_notes.py (DEVELOPER_NOTES size + pointers).

Synthetic repos under tmp_path exercise each check in isolation; the last
test runs the checker against THIS repo and asserts it finds a non-trivial
number of citations (an empty scan passing is the silent failure mode).
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / 'scripts' / 'verify_dev_notes.py'

spec = importlib.util.spec_from_file_location('verify_dev_notes', SCRIPT)
vdn = importlib.util.module_from_spec(spec)
sys.modules['verify_dev_notes'] = vdn
spec.loader.exec_module(vdn)

_vdc_spec = importlib.util.spec_from_file_location(
    'verify_dev_counts', REPO_ROOT / 'scripts' / 'verify_dev_counts.py')
_vdc = importlib.util.module_from_spec(_vdc_spec)
_vdc_spec.loader.exec_module(_vdc)
KEYS = sorted(_vdc.ALL_KEYS)

SENTINELS = ''.join(f'<!-- sync:{k} -->{i}<!-- /sync -->\n' for i, k in enumerate(KEYS, 1))

GOOD_NOTES = f"""# Developer Notes

## PvPoke bugs found

**3. A numbered item** body.

## Engine constant sourcing (float32)

### League facts: `pokemon.LEAGUES`

{SENTINELS}
See CLAUDE.md "Ship-mode narrative policy" and TODO "Reproducibility" and
CHANGELOG "2026-01-01 -- an archived entry". Pin: `tests/test_thing.py::test_ok`.
"""

GOOD_FILES = {
    'CLAUDE.md': '## Ship-mode narrative policy\n',
    'TODO.md': '## Reproducibility\n',
    'CHANGELOG.md': '## 2026-01-01 -- an archived entry\n\nbody mentions "not a heading".\n',
    'tests/test_thing.py': 'def test_ok():\n    pass\n',
    'tests/test_cite.py': ('# See DEVELOPER_NOTES "Engine constant\n'
                           '# sourcing" and DEVELOPER_NOTES "League facts: pokemon.LEAGUES"\n'
                           '# and DEVELOPER_NOTES "3. A numbered item".\n'),
}


def make_repo(tmp_path: Path, notes: str = GOOD_NOTES, **extra: str) -> Path:
    files = {**GOOD_FILES, **extra}
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    (tmp_path / 'DEVELOPER_NOTES.md').write_text(notes)
    (tmp_path / 'scripts').mkdir(exist_ok=True)
    shutil.copy(REPO_ROOT / 'scripts' / 'verify_dev_counts.py', tmp_path / 'scripts')
    return tmp_path


def test_happy_path(tmp_path):
    fails, warns = vdn.run_checks(make_repo(tmp_path))
    assert fails == [] and warns == []


def test_size_cap_fails(tmp_path):
    pad = 'x' * (vdn.CHAR_CAP + 1 - len(GOOD_NOTES))
    fails, _ = vdn.run_checks(make_repo(tmp_path, GOOD_NOTES + pad))
    assert len(fails) == 1 and fails[0].startswith('size:')
    assert 'CHANGELOG' in fails[0]


def test_size_at_cap_passes(tmp_path):
    pad = 'x' * (vdn.CHAR_CAP - len(GOOD_NOTES))
    fails, _ = vdn.run_checks(make_repo(tmp_path, GOOD_NOTES + pad))
    assert fails == []


def test_dangling_inbound_citation_fails_in_ordinary_file(tmp_path):
    repo = make_repo(tmp_path, **{
        'docs/x.md': 'see DEVELOPER_NOTES "Section that was renamed"\n'})
    fails, warns = vdn.run_checks(repo)
    assert len(fails) == 1 and 'docs/x.md:1' in fails[0]
    assert 'section that was renamed' in fails[0]
    assert warns == []


def test_dangling_inbound_citation_only_warns_in_engine_hash_file(tmp_path):
    repo = make_repo(tmp_path, **{
        'src/gopvpsim/battle.py': '# DEVELOPER_NOTES "Section that was renamed"\n'})
    fails, warns = vdn.run_checks(repo)
    assert fails == []
    assert len(warns) == 1 and 'engine-hash' in warns[0]


def test_dangling_inbound_citation_only_warns_in_point_in_time_doc(tmp_path):
    repo = make_repo(tmp_path, **{
        'docs/validations/2026-01-01_x.md': 'DEVELOPER_NOTES "gone"\n'})
    fails, warns = vdn.run_checks(repo)
    assert fails == [] and len(warns) == 1 and 'point-in-time' in warns[0]


def test_citation_is_case_insensitive_and_strips_comment_prefixes(tmp_path):
    repo = make_repo(tmp_path, **{
        'scripts/x.js': '// see DEVELOPER_NOTES "engine CONSTANT\n// sourcing"\n'})
    fails, _ = vdn.run_checks(repo)
    assert fails == []


def test_outbound_missing_test_name_fails(tmp_path):
    notes = GOOD_NOTES.replace('test_ok', 'test_vanished')
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'defines no `test_vanished`' in fails[0]


def test_outbound_missing_path_fails_but_userdata_warns(tmp_path):
    notes = GOOD_NOTES + '`tests/no_such_file.py` and `userdata/replay/x.log`\n'
    fails, warns = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'tests/no_such_file.py' in fails[0]
    assert len(warns) == 1 and 'userdata/replay/x.log' in warns[0]


def test_outbound_doc_citations(tmp_path):
    notes = GOOD_NOTES.replace('"Ship-mode narrative policy"', '"No such policy"')
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'CLAUDE.md "no such policy"' in fails[0]

    # CHANGELOG citations must hit a HEADING, not body text.
    notes = GOOD_NOTES.replace('"2026-01-01 -- an archived entry"', '"not a heading"')
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'CHANGELOG' in fails[0] and 'headings' in fails[0]


def test_sentinel_duplicate_and_leak_fail(tmp_path):
    k = KEYS[0]
    notes = GOOD_NOTES + f'<!-- sync:{k} -->99<!-- /sync -->\n'
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert [f for f in fails if f'sync:{k} appears 2x' in f]

    repo = make_repo(tmp_path)
    (repo / 'CHANGELOG.md').write_text(
        GOOD_FILES['CHANGELOG.md'] + f'<!-- sync:{k} -->1<!-- /sync -->\n')
    fails, _ = vdn.run_checks(repo)
    assert [f for f in fails if f'sync:{k} leaked' in f]


def test_missing_sentinel_fails(tmp_path):
    k = KEYS[0]
    notes = GOOD_NOTES.replace(f'<!-- sync:{k} -->', '')
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert [f for f in fails if f'sync:{k} appears 0x' in f]


def test_real_repo_passes_and_scan_is_non_trivial():
    fails, _warns = vdn.run_checks(REPO_ROOT)
    assert fails == [], '\n'.join(fails)

    notes = (REPO_ROOT / 'DEVELOPER_NOTES.md').read_text()
    anchors = vdn._anchors(notes)
    resolved = 0
    for p in vdn._iter_repo_files(REPO_ROOT):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if rel in ('DEVELOPER_NOTES.md', 'CHANGELOG.md') or rel in vdn.SELF_FILES:
            continue
        try:
            text = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for m in vdn._CITE_RE.finditer(text):
            if m.group(1) == 'DEVELOPER_NOTES' and vdn._resolves(m.group(2), anchors):
                resolved += 1
    # 2026-10-24: 60+ resolving citations; floor set well below.
    assert resolved >= 20, resolved
    assert len(notes) <= vdn.CHAR_CAP
