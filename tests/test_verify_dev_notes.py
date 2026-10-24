"""Gate tests for scripts/verify_dev_notes.py (DEVELOPER_NOTES size + pointers).

Synthetic repos under tmp_path exercise each check in isolation; the last
tests run the checker against THIS repo and assert it finds a non-trivial
number of citations (an empty scan passing is the silent failure mode).
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

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

**4. A wrapped numbered item that
runs onto a second line.** body.

## Engine constant sourcing (float32)

### League facts: `pokemon.LEAGUES`

```
# not a heading: inside a code fence
```

{SENTINELS}
See CLAUDE.md "Ship-mode narrative policy" and TODO "Reproducibility" and
CHANGELOG "2026-01-01 -- an archived entry". Pin: `tests/test_thing.py::test_ok`,
`tests/test_thing.py:12-14`, `tests/test_thing.py::TestK::test_m`,
`tests/test_thing.py::test_ok[case-1]`, `tests/test_thing.py::LIMIT`,
`tests/test_thing.py::ANN`, `tests/test_thing.py::test_async`,
`scripts/tool.py
--flag x`, `docs/notes.md::not_a_python_member`, `tests/test_thing.py::test_
ok`.
Own section: DEVELOPER_NOTES "PvPoke bugs found". CLAUDE.md "a human override
always wins" is a body phrase, not a heading.
"""

TEST_THING = '''LIMIT = 3
ANN: int = 4

def test_ok():
    pass

async def test_async():
    pass

class TestK:
    def test_m(self):
        pass

class Other:
    def test_elsewhere(self):
        pass

"""
    def test_in_docstring(): removed
"""
FLAG == 3
'''

GOOD_FILES = {
    'CLAUDE.md': '## Ship-mode narrative policy\n\nBody phrase: a human override always wins.\n',
    'TODO.md': '## Reproducibility\n',
    'CHANGELOG.md': '## 2026-01-01 -- an archived entry\n\nbody mentions "not a heading".\n',
    'scripts/tool.py': 'pass\n',
    'docs/notes.md': 'x\n',
    'tests/test_thing.py': TEST_THING,
    'tests/test_cite.py': ('# See DEVELOPER_NOTES "Engine constant\n'
                           '# sourcing" and DEVELOPER_NOTES "League facts: pokemon.LEAGUES"\n'
                           '# and DEVELOPER_NOTES "3. A numbered item".\n'
                           "P = REPO_ROOT / 'DEVELOPER_NOTES.md'  # a string literal, not a cite\n"),
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


def test_citation_quote_styles_all_checked(tmp_path):
    forms = {
        'docs/a.md': "DEVELOPER_NOTES 'Section gone'\n",
        'docs/b.md': 'DEVELOPER_NOTES “Section gone”\n',
        'docs/c.md': 'DEVELOPER_NOTES.md section "Section gone"\n',
        'docs/d.md': 'DEVELOPER_NOTES\'s "Section gone"\n',
        'docs/e.md': 'see `DEVELOPER_NOTES.md` "Section gone"\n',
        'scripts/f.py': '# see DEVELOPER_NOTES\n# "Section gone"\n',
        'docs/g.md': 'DEVELOPER_NOTES, "Section gone"\n',
    }
    for rel, text in forms.items():
        fails, _ = vdn.run_checks(make_repo(tmp_path, **{rel: text}))
        assert len(fails) == 1 and rel in fails[0], (rel, fails)
        (tmp_path / rel).unlink()
    # ...and each resolves when the name is right.
    good = {rel: t.replace('Section gone', 'PvPoke bugs found') for rel, t in forms.items()}
    fails, _ = vdn.run_checks(make_repo(tmp_path, **good))
    assert fails == []


def test_string_literals_and_prefixed_names_are_not_citations(tmp_path):
    repo = make_repo(tmp_path, **{
        'scripts/lit.py': ('P = ROOT / "DEVELOPER_NOTES.md"\nQ = "other"\n'
                           "R = ROOT / 'DEVELOPER_NOTES.md'\n"
                           'MY_DEVELOPER_NOTES "Gone"\n'
                           'docs/DEVELOPER_NOTES "Gone"\n')})
    fails, _ = vdn.run_checks(repo)
    assert fails == []


def test_apostrophe_in_single_quoted_name_does_not_truncate(tmp_path):
    # Would otherwise resolve "A numbered item" by accident; now skipped.
    repo = make_repo(tmp_path, **{
        'docs/x.md': "DEVELOPER_NOTES 'A numbered item's renamed bit'\n"})
    fails, _ = vdn.run_checks(repo)
    assert fails == []
    assert not vdn._CITE_RE.search("DEVELOPER_NOTES 'A numbered item's renamed bit'")


def test_wrapped_bold_item_is_an_anchor_but_fenced_hash_is_not(tmp_path):
    repo = make_repo(tmp_path, **{
        'docs/x.md': 'DEVELOPER_NOTES "4. A wrapped numbered item that runs onto a second line."\n'})
    fails, _ = vdn.run_checks(repo)
    assert fails == []
    repo = make_repo(tmp_path, **{
        'docs/y.md': 'DEVELOPER_NOTES "not a heading: inside a code fence"\n'})
    fails, _ = vdn.run_checks(repo)
    assert len(fails) == 1 and 'docs/y.md' in fails[0]


def test_unclosed_bold_item_does_not_swallow_next_paragraph():
    anchors = vdn._anchors('## H\n\n**2. Item unclosed body\n\nPara two has **bold** words.\n')
    assert not any('para two' in a for a in anchors)
    assert vdn._anchors('**1. Real item.** x **bold** y **9. ** z **w**') == ['1. real item.']


def test_tilde_fences_and_issue_numbers_are_not_headings():
    assert vdn._anchors('~~~\n# fake heading\n~~~\n#378 wrapped issue ref\n## Real\n') == ['real']


def test_match_is_on_word_boundaries(tmp_path):
    for bad in ('ugs fou', 'gs found', '###'):
        repo = make_repo(tmp_path, **{'docs/x.md': f'DEVELOPER_NOTES "{bad}"\n'})
        fails, _ = vdn.run_checks(repo)
        assert len(fails) == 1, bad
    repo = make_repo(tmp_path, **{'docs/x.md': 'DEVELOPER_NOTES "bugs found"\n'})
    fails, _ = vdn.run_checks(repo)
    assert fails == []


def test_outbound_missing_test_name_fails(tmp_path):
    notes = GOOD_NOTES.replace('::test_ok`', '::test_vanished`')
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'defines no `test_vanished`' in fails[0]

    notes = GOOD_NOTES.replace('::TestK::test_m`', '::TestK::test_gone`')
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'defines no `TestK::test_gone`' in fails[0]

    notes = GOOD_NOTES.replace('::LIMIT`', '::NOPE`')
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'defines no `NOPE`' in fails[0]


def test_member_check_uses_ast_scoping(tmp_path):
    for bad in ('::TestK::test_elsewhere', '::test_in_docstring', '::FLAG', '::test_ok::nested'):
        notes = GOOD_NOTES + f'`tests/test_thing.py{bad}`\n'
        fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
        assert len(fails) == 1 and 'defines no' in fails[0], (bad, fails)
    repo = make_repo(tmp_path)
    (repo / 'tests' / 'test_thing.py').write_text('def broken(:\n')
    fails, _ = vdn.run_checks(repo)
    assert fails and all('does not parse' in f for f in fails)


def test_outbound_missing_path_fails_but_userdata_warns(tmp_path):
    notes = GOOD_NOTES + '`tests/no_such_file.py` and `userdata/replay/x.log`\n'
    fails, warns = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'tests/no_such_file.py' in fails[0]
    assert len(warns) == 1 and 'userdata/replay/x.log' in warns[0]

    notes = GOOD_NOTES + '`scripts/no_such_tool.py --flag x` and `tests/nope.py:12`\n'
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 2


def test_outbound_doc_citations(tmp_path):
    notes = GOOD_NOTES.replace('"Ship-mode narrative policy"', '"No such policy"')
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'CLAUDE.md "no such policy"' in fails[0]

    # CLAUDE.md/TODO citations may hit body text...
    notes = GOOD_NOTES.replace('"a human override\nalways wins"', '"a robot override\nalways wins"')
    assert notes != GOOD_NOTES
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'CLAUDE.md "a robot override always wins"' in fails[0]

    # ...but CHANGELOG citations must hit a HEADING.
    notes = GOOD_NOTES.replace('"2026-01-01 -- an archived entry"', '"not a heading"')
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'CHANGELOG' in fails[0] and 'headings' in fails[0]


def test_own_section_citation_in_notes_is_checked(tmp_path):
    notes = GOOD_NOTES.replace('Own section: DEVELOPER_NOTES "PvPoke bugs found"',
                               'Own section: DEVELOPER_NOTES "Section gone"')
    assert notes != GOOD_NOTES
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'its own section' in fails[0]


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


def test_unloadable_or_empty_sibling_fails_rather_than_disabling_sentinel_check(tmp_path):
    notes = GOOD_NOTES.replace('<!-- sync:', '<!-- nosync:')  # every sentinel gone
    repo = make_repo(tmp_path, notes)
    sibling = repo / 'scripts' / 'verify_dev_counts.py'
    sibling.unlink()
    fails, _ = vdn.run_checks(repo)
    assert len(fails) == 1 and 'sentinels:' in fails[0] and 'missing' in fails[0]

    sibling.write_text('raise RuntimeError("boom")\n')
    fails, _ = vdn.run_checks(repo)
    assert len(fails) == 1 and 'could not load ALL_KEYS' in fails[0]

    sibling.write_text('ALL_KEYS = set()\n')
    fails, _ = vdn.run_checks(repo)
    assert len(fails) == 1 and 'empty' in fails[0]


def test_non_ascii_warns_and_bad_utf8_fails(tmp_path):
    repo = make_repo(tmp_path, GOOD_NOTES + 'arrow → here\n')
    fails, warns = vdn.run_checks(repo)
    assert fails == [] and len(warns) == 1 and 'non-ASCII' in warns[0]
    (repo / 'DEVELOPER_NOTES.md').write_bytes(GOOD_NOTES.encode() + b'\x92\n')
    fails, _ = vdn.run_checks(repo)
    assert len(fails) == 1 and 'UTF-8' in fails[0]


def test_hook_exports_the_checkers_scan_paths():
    hook = (REPO_ROOT / '.githooks' / 'pre-commit').read_text()
    assert '--print-scan-paths' in hook
    r = subprocess.run([sys.executable, str(SCRIPT), '--print-scan-paths'],
                       capture_output=True, text=True, check=True)
    assert r.stdout.split() == [*vdn.SCAN_FILES, *vdn.SCAN_DIRS, vdn.NOTES, vdn.CHANGELOG]


def test_exit_codes_distinguish_drift_from_crash(tmp_path):
    repo = make_repo(tmp_path, GOOD_NOTES + 'x' * vdn.CHAR_CAP)
    r = subprocess.run([sys.executable, str(SCRIPT), '--quiet', '--repo-root', str(repo)],
                       capture_output=True, text=True)
    assert r.returncode == vdn.DRIFT_EXIT == 3 and r.stdout == '' and 'size:' in r.stderr
    r = subprocess.run([sys.executable, str(SCRIPT), '--bogus-flag'], capture_output=True, text=True)
    assert r.returncode == 2  # argparse; must never collide with DRIFT_EXIT
    r = subprocess.run([sys.executable, str(SCRIPT), '--repo-root', str(make_repo(tmp_path))],
                       capture_output=True, text=True)
    assert r.returncode == 0 and 'resolve' in r.stdout


def test_real_repo_passes_and_scan_is_non_trivial():
    fails, warns = vdn.run_checks(REPO_ROOT)
    assert fails == [], '\n'.join(fails)
    # Every backticked repo path in the notes fits a checked form (pins the
    # `::`/`_` line-wrap rejoin and the glob/placeholder suppressions).
    assert not [w for w in warns if 'fits no checked form' in w], warns

    notes = (REPO_ROOT / 'DEVELOPER_NOTES.md').read_text()
    anchors = vdn._anchors(notes)
    resolved, files = 0, set()
    for p in vdn._iter_repo_files(REPO_ROOT):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if rel in vdn.SELF_FILES:
            continue
        text = vdn._read(p)
        for m in vdn._CITE_RE.finditer(text):
            if m.group(1) == 'DEVELOPER_NOTES' and vdn._resolves(vdn._cite_quote(m), anchors):
                resolved += 1
                files.add(rel)
    # 2026-10-24: 53 resolving citations across 32 files; floors well below.
    assert resolved >= 20, resolved
    assert len(files) >= 10, sorted(files)
    assert len(notes) <= vdn.CHAR_CAP


# --- round-3 pins -----------------------------------------------------------

def test_wrapped_backticked_test_ref_is_checked(tmp_path):
    notes = GOOD_NOTES + '`tests/test_thing.py::\ntest_ok` and `tests/test_thing.py::\ntest_gone`\n'
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'test_gone' in fails[0], fails
    notes = GOOD_NOTES + '`tests/test_thing.py::test_ok[case]::extra`\n'
    fails, warns = vdn.run_checks(make_repo(tmp_path, notes))
    assert fails == [] and len(warns) == 1 and 'fits no checked form' in warns[0]


def test_unparseable_path_like_token_warns(tmp_path):
    notes = (GOOD_NOTES + '`tests/test_thing.py::1bad` `docs/validations/` `articles/*.toml` '
             '`userdata/<slug>.log` `userdata/x.{sh,log}`\n')
    fails, warns = vdn.run_checks(make_repo(tmp_path, notes))
    assert fails == []
    assert len(warns) == 1 and 'fits no checked form' in warns[0] and '1bad' in warns[0]


def test_citation_pairs_across_at_most_one_newline(tmp_path):
    repo = make_repo(tmp_path, **{
        'docs/x.md': 'end of a paragraph about DEVELOPER_NOTES\n\n\n"Unrelated quote three paras later"\n',
        'scripts/y.js': '// DEVELOPER_NOTES\n// "Section gone"\n',
        'docs/z.md': 'see `DEVELOPER_NOTES.md` \u00a7"Section gone"\n'})
    fails, _ = vdn.run_checks(repo)
    assert len(fails) == 2 and all('Section gone'.lower() in f for f in fails), fails


def test_single_quote_needs_whitespace_before_it(tmp_path):
    repo = make_repo(tmp_path, **{'docs/x.md': "DEVELOPER_NOTES.md'Gone section'\n"})
    fails, _ = vdn.run_checks(repo)
    assert fails == []


def test_right_word_boundary(tmp_path):
    repo = make_repo(tmp_path, **{'docs/x.md': 'DEVELOPER_NOTES "bugs fou"\n'})
    fails, _ = vdn.run_checks(repo)
    assert len(fails) == 1


def test_fences_long_indented_and_mixed_markers():
    text = ('````md\n```\n# leaked\n```\n````\n'
            '  ```python\n# leaked2\n```\n'
            '~~~\n# leaked3\n```\n~~~\n'
            '```\n```python\n# leaked4: an info string cannot close a fence\n```\n'
            '## Real\n')
    assert vdn._anchors(text) == ['real']


def test_markdown_heading_after_mention_is_not_a_citation(tmp_path):
    repo = make_repo(tmp_path, **{'docs/x.md': '# see DEVELOPER_NOTES\n## "Section gone"\n'})
    fails, _ = vdn.run_checks(repo)
    assert fails == []


def test_stray_backtick_does_not_hide_later_refs(tmp_path):
    notes = GOOD_NOTES + 'a stray ` here\n\n`tests/test_thing.py::test_gone`\n'
    fails, _ = vdn.run_checks(make_repo(tmp_path, notes))
    assert len(fails) == 1 and 'test_gone' in fails[0]


def test_attribute_and_subscript_assignments_bind_nothing(tmp_path):
    src = 'obj = object()\nobj.attr = 1\na = [0]\na[0] = 1\nd = {}\nd[k] = 1\n'
    for bad in ('attr', 'k'):
        repo = make_repo(tmp_path, GOOD_NOTES + f'`tests/test_bind.py::{bad}`\n',
                         **{'tests/test_bind.py': src})
        fails, _ = vdn.run_checks(repo)
        assert len(fails) == 1 and f'defines no `{bad}`' in fails[0], (bad, fails)
    repo = make_repo(tmp_path, GOOD_NOTES + '`tests/test_bind.py::obj` `tests/test_bind.py::a`\n',
                     **{'tests/test_bind.py': src})
    fails, _ = vdn.run_checks(repo)
    assert fails == []


def test_drift_exit_is_shared_with_the_sibling_and_the_hook():
    hook = (REPO_ROOT / '.githooks' / 'pre-commit').read_text()
    assert vdn.DRIFT_EXIT == _vdc.DRIFT_EXIT == 3
    assert hook.count(f'$rc -eq {vdn.DRIFT_EXIT} ]]') == 2  # steps 3 and 2


def test_member_check_scoping_and_blocks(tmp_path):
    src = ('import typing\nif typing.TYPE_CHECKING:\n    def under_if(): pass\n'
           'else:\n    IN_ELSE = 1\n'
           'try:\n    A, B = 1, 2\nexcept ImportError:\n    FALLBACK = 1\nfinally:\n    FIN = 2\n'
           'with open(__file__):\n    def under_with(): pass\n'
           'class K:\n    def meth(self): pass\n')
    repo = make_repo(tmp_path, GOOD_NOTES + '`tests/test_blocks.py::under_if` `tests/test_blocks.py::B` '
                     '`tests/test_blocks.py::IN_ELSE` `tests/test_blocks.py::FALLBACK` '
                     '`tests/test_blocks.py::FIN` `tests/test_blocks.py::under_with` '
                     '`tests/test_blocks.py::K::meth`\n', **{'tests/test_blocks.py': src})
    fails, _ = vdn.run_checks(repo)
    assert fails == []
    # A method named without its class must NOT resolve at module level.
    repo = make_repo(tmp_path, GOOD_NOTES + '`tests/test_blocks.py::meth`\n', **{'tests/test_blocks.py': src})
    fails, _ = vdn.run_checks(repo)
    assert len(fails) == 1 and 'defines no `meth`' in fails[0]


def test_gitignore_is_scanned(tmp_path):
    repo = make_repo(tmp_path, **{'.gitignore': '# see DEVELOPER_NOTES "Section gone"\n'})
    fails, _ = vdn.run_checks(repo)
    assert len(fails) == 1 and '.gitignore:1' in fails[0]


def test_real_repo_outbound_floors():
    notes = (REPO_ROOT / 'DEVELOPER_NOTES.md').read_text()
    paths = [tok for _, tok in vdn._path_tokens(notes) if vdn._PATH_RE.match(tok)]
    members = [tok for tok in paths if '::' in tok]
    doc_cites = [m for m in vdn._CITE_RE.finditer(notes) if m.group(1) != 'DEVELOPER_NOTES']
    # 2026-10-24: 69 paths, 7 member refs, 5 doc citations; floors well below.
    assert len(paths) >= 30, len(paths)
    assert len(members) >= 4, members
    assert len(doc_cites) >= 3, len(doc_cites)
