"""End-to-end pins for .githooks/pre-commit step 3 (DEVELOPER_NOTES gate).

Runs the WORKING-TREE hook and checker inside a throwaway local clone, so
each scenario is a real `git commit`. Pre-fix values (2026-10-24 review of
b1f054e): the hook read the working tree, so (b) blocked and (f) passed
with a broken HEAD; `--diff-filter=ACM` made (c) exit 0 before the check;
a missing interpreter was reported as notes drift (e).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_FILES = ('.githooks/pre-commit', 'scripts/verify_dev_notes.py',
              'scripts/verify_dev_counts.py', 'DEVELOPER_NOTES.md')
STRIPPED_ENV = {'HOME': os.environ.get('HOME', '/tmp'),
                'TMPDIR': os.environ.get('TMPDIR', '/tmp'),
                'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'}

pytestmark = pytest.mark.slow


def _git(clone: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(['git', '-C', str(clone), *args], text=True,
                          capture_output=True, env=env)


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    c = tmp_path / 'clone'
    subprocess.run(['git', 'clone', '-q', '--local', str(REPO_ROOT), str(c)], check=True)
    for rel in HOOK_FILES:  # the working-tree versions under test
        shutil.copy(REPO_ROOT / rel, c / rel)
    _git(c, 'add', *HOOK_FILES)
    _git(c, 'commit', '-q', '--no-verify', '-m', 'baseline')
    _git(c, 'config', 'core.hooksPath', '.githooks')
    (c / '.venv').symlink_to(REPO_ROOT / '.venv')
    return c


def _commit(clone: Path, msg: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return _git(clone, 'commit', '-q', '--allow-empty', '-m', msg, env=env)


def test_staged_dangling_citation_is_blocked(clone):
    (clone / 'docs' / 'zz.md').write_text('see DEVELOPER_NOTES "No such thing"\n')
    _git(clone, 'add', 'docs/zz.md')
    r = _commit(clone, 'a')
    assert r.returncode == 1 and 'STAGED content' in r.stderr


def test_unstaged_overcap_notes_do_not_block_unrelated_commit(clone):
    notes = clone / 'DEVELOPER_NOTES.md'
    notes.write_text(notes.read_text() + 'x' * 400)  # over cap, NOT staged
    (clone / 'README.md').write_text((clone / 'README.md').read_text() + 'x\n')
    _git(clone, 'add', 'README.md')
    assert _commit(clone, 'b').returncode == 0


def test_deletion_only_commit_still_runs_the_gate(clone):
    # The notes name this file, so deleting it alone must be blocked.
    _git(clone, 'rm', '-q', 'tests/test_pvpoke_sandbox.py')
    r = _commit(clone, 'c')
    assert r.returncode == 1 and 'DEVELOPER_NOTES drift' in r.stderr


def test_stripped_path_uses_the_venv_then_reports_missing_interpreter(clone):
    assert _commit(clone, 'd', env=STRIPPED_ENV).returncode == 0
    (clone / '.venv').unlink()
    r = _commit(clone, 'e', env=STRIPPED_ENV)
    assert r.returncode == 1 and 'no project interpreter' in r.stderr
    assert 'drift' not in r.stderr


def test_staged_heading_rename_without_citers_is_blocked_but_unstaged_is_not(clone):
    notes = clone / 'DEVELOPER_NOTES.md'
    renamed = notes.read_text().replace('## Article lifecycle\n', '## Article lifecycle (renamed)\n')
    assert renamed != notes.read_text()
    notes.write_text(renamed)
    (clone / 'README.md').write_text((clone / 'README.md').read_text() + 'y\n')
    _git(clone, 'add', 'README.md')
    assert _commit(clone, 'f').returncode == 0  # index clean, tree broken
    _git(clone, 'add', 'DEVELOPER_NOTES.md')
    assert _commit(clone, 'h').returncode == 1
