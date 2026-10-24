"""End-to-end pins for .githooks/pre-commit (DEVELOPER_NOTES gate and friends).

Runs the WORKING-TREE hook, scripts and notes inside a throwaway local
clone (the clone is brought to the working tree's state and committed
--no-verify as a baseline), so each scenario is a real `git commit`.

Pre-fix values, from the 2026-10-24 adversarial reviews of b1f054e and
f88e230: the hook read the working tree, so an unstaged over-cap edit
blocked unrelated commits and a staged dangling citation passed once the
working copy was fixed; `--diff-filter=ACM` made deletion-only commits
exit 0 before the check; a missing interpreter was reported as notes
drift; worktrees (no .venv) blocked every commit under a non-direnv PATH;
verify_dev_counts.py spawned bare `python`; step 1 grepped the working
tree; a bad TMPDIR aborted the hook in mktemp; a checker crash read as
drift.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
STRIPPED_ENV = {'HOME': os.environ.get('HOME', '/tmp'),
                'TMPDIR': os.environ.get('TMPDIR', '/tmp'),
                'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'}
IDENT = ['-c', 'user.name=hook test', '-c', 'user.email=hook@test.invalid']


def _git(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(['git', *IDENT, '-C', str(cwd), *args], text=True,
                          capture_output=True, env=env)


def _run(cwd: Path, *args: str) -> list[str]:
    return subprocess.run(['git', '-C', str(cwd), *args], text=True,
                          capture_output=True, check=True).stdout.split('\n')


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    c = tmp_path / 'clone'
    subprocess.run(['git', 'clone', '-q', '--local', str(REPO_ROOT), str(c)], check=True)
    # Bring the clone to the working tree's state (tracked changes + untracked).
    changed = [f for f in _run(REPO_ROOT, 'diff', '--name-only', 'HEAD') if f]
    untracked = [f for f in _run(REPO_ROOT, 'ls-files', '-o', '--exclude-standard') if f]
    for rel in changed + untracked:
        src, dst = REPO_ROOT / rel, c / rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
        elif dst.exists():
            dst.unlink()
    _git(c, 'add', '-A')  # throwaway clone: the broad add is the point here
    _git(c, 'commit', '-q', '--no-verify', '--allow-empty', '-m', 'baseline')
    _git(c, 'config', 'core.hooksPath', '.githooks')
    (c / '.venv').symlink_to(REPO_ROOT / '.venv')
    return c


def _commit(cwd: Path, msg: str, env: dict | None = None, *extra: str) -> subprocess.CompletedProcess:
    return _git(cwd, 'commit', '-q', '--allow-empty', '-m', msg, *extra, env=env)


def _append(p: Path, text: str) -> None:
    p.write_text(p.read_text() + text)


def test_staged_dangling_citation_is_blocked(clone):
    (clone / 'docs' / 'zz.md').write_text('see DEVELOPER_NOTES "No such thing"\n')
    _git(clone, 'add', 'docs/zz.md')
    r = _commit(clone, 'a')
    assert r.returncode == 1 and 'content being committed' in r.stderr


def test_unstaged_overcap_notes_do_not_block_unrelated_commit(clone):
    _append(clone / 'DEVELOPER_NOTES.md', 'x' * 400)  # over cap, NOT staged
    _append(clone / 'README.md', 'x\n')
    _git(clone, 'add', 'README.md')
    assert _commit(clone, 'b').returncode == 0


def test_deletion_only_commit_still_runs_the_gate(clone):
    # The notes name this file, so deleting it alone must be blocked.
    _git(clone, 'rm', '-q', 'tests/test_pvpoke_sandbox.py')
    r = _commit(clone, 'c')
    assert r.returncode == 1 and 'DEVELOPER_NOTES drift' in r.stderr


def test_stripped_path_uses_the_venv_then_reports_missing_interpreter(clone):
    assert _commit(clone, 'd', STRIPPED_ENV).returncode == 0
    (clone / '.venv').unlink()
    r = _commit(clone, 'e', STRIPPED_ENV)
    assert r.returncode == 1 and 'no project interpreter' in r.stderr
    assert 'drift' not in r.stderr


def test_worktree_finds_the_main_checkouts_venv(clone, tmp_path):
    wt = tmp_path / 'wt'
    assert _git(clone, 'worktree', 'add', '-q', str(wt), '-b', 'wtb').returncode == 0
    assert _commit(wt, 'w', STRIPPED_ENV).returncode == 0


def test_bad_tmpdir_does_not_block(clone):
    env = {**STRIPPED_ENV, 'TMPDIR': '/nonexistent/dir'}
    assert _commit(clone, 't', env).returncode == 0


def test_checker_crash_is_reported_as_a_crash(clone):
    checker = clone / 'scripts' / 'verify_dev_notes.py'
    checker.write_text('import nonexistent_module_zz\n' + checker.read_text())
    r = _commit(clone, 'x')
    assert r.returncode == 1 and 'crashed' in r.stderr
    assert 'Commit blocked by DEVELOPER_NOTES drift' not in r.stderr


def test_step1_reads_the_index_not_the_working_tree(clone):
    toml = next(f for f in _run(clone, 'ls-files', 'thresholds') if f.endswith('.toml'))
    p = clone / toml
    _append(p, '\nauthored_by = "ai"\n')
    _git(clone, 'add', toml)
    _git(clone, 'checkout', '--', toml) if False else None
    # Restore the WORKING COPY only; the index still holds the bad line.
    subprocess.run(['git', '-C', str(clone), 'show', f'HEAD:{toml}'], check=True,
                   stdout=p.open('w'))
    r = _commit(clone, 's1')
    assert r.returncode == 1 and 'AI-drafted prose' in r.stderr


@pytest.mark.slow  # pytest collection of the whole suite (~3 s)
def test_step2_runs_under_stripped_path_and_reads_index_sentinels(clone):
    # Staging a tests/ file triggers step 2; the sibling script must find
    # its own interpreter (pre-fix: "derivation failed ... 'python'").
    # NOTE: test_count itself is machine-dependent (tests parametrize over
    # local userdata/ artifacts), so a clean clone may legitimately report
    # drift; the pin here is "no interpreter error", not rc == 0.
    _append(clone / 'tests' / 'conftest.py', '# hook test\n')
    _git(clone, 'add', 'tests/conftest.py')
    r = _commit(clone, 's2', STRIPPED_ENV)
    assert 'derivation failed' not in r.stderr and "'python'" not in r.stderr, r.stderr
    # Sentinel VALUES come from the index: stage a bogus value, restore the
    # working copy, and the block must quote the staged value.
    import re
    notes = clone / 'DEVELOPER_NOTES.md'
    good = notes.read_text()
    bogus = re.sub(r'(<!-- sync:test_count -->)\d+', r'\g<1>1', good, count=1)
    assert bogus != good
    notes.write_text(bogus)
    _git(clone, 'add', 'DEVELOPER_NOTES.md')
    notes.write_text(good)
    r = _commit(clone, 's2b', STRIPPED_ENV)
    assert r.returncode == 1 and 'sentinel 1 !=' in r.stderr, r.stderr


@pytest.mark.slow
def test_staged_heading_rename_without_citers_is_blocked_but_unstaged_is_not(clone):
    notes = clone / 'DEVELOPER_NOTES.md'
    renamed = notes.read_text().replace('## Article lifecycle\n', '## Article lifecycle (renamed)\n')
    assert renamed != notes.read_text()
    notes.write_text(renamed)
    _append(clone / 'README.md', 'y\n')
    _git(clone, 'add', 'README.md')
    assert _commit(clone, 'f').returncode == 0  # index clean, tree broken
    _git(clone, 'add', 'DEVELOPER_NOTES.md')
    assert _commit(clone, 'h').returncode == 1
