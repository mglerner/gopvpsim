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


def _clean_env(env: dict | None) -> dict:
    # A hook exports GIT_INDEX_FILE/GIT_DIR; never let those leak into the
    # clone's git calls if this module is ever run from inside a hook.
    base = dict(env) if env is not None else dict(os.environ)
    return {k: v for k, v in base.items() if not k.startswith('GIT_')}


def _git(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(['git', *IDENT, '-C', str(cwd), *args], text=True,
                          capture_output=True, env=_clean_env(env))


def _run(cwd: Path, *args: str) -> list[str]:
    return subprocess.run(['git', '-C', str(cwd), *args], text=True, env=_clean_env(None),
                          capture_output=True, check=True).stdout.split('\n')


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    c = tmp_path / 'clone'
    # --shared: the clone borrows the real object store (176 KB .git) instead
    # of hardlinking or, across filesystems, COPYING a ~790 MB pack per test.
    subprocess.run(['git', 'clone', '-q', '--shared', str(REPO_ROOT), str(c)],
                   check=True, env=_clean_env(None))
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
    assert _git(c, 'add', '-A').returncode == 0  # throwaway clone: the broad add is the point
    assert _git(c, 'commit', '-q', '--no-verify', '--allow-empty', '-m', 'baseline').returncode == 0
    assert _git(c, 'config', 'core.hooksPath', '.githooks').returncode == 0
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
    original = checker.read_text()
    checker.write_text('import nonexistent_module_zz\n' + original)
    r = _commit(clone, 'x')
    assert r.returncode == 1 and 'crashed' in r.stderr
    assert 'Commit blocked by DEVELOPER_NOTES drift' not in r.stderr
    # A usage error exits 2 (argparse): not drift. Renaming --repo-root makes
    # the step-3 call itself the usage error (--print-scan-paths still works).
    checker.write_text(original.replace("'--repo-root'", "'--repo-rooot'"))
    r = _commit(clone, 'y')
    assert r.returncode == 1 and 'crashed (exit 2)' in r.stderr
    assert 'Commit blocked by DEVELOPER_NOTES drift' not in r.stderr
    # Same split for step 2's sibling.
    checker.write_text(original)
    sib = clone / 'scripts' / 'verify_dev_counts.py'
    sib.write_text(sib.read_text().replace('def main() -> int:', 'def main() -> int:\n    raise RuntimeError("boom")'))
    _append(clone / 'tests' / 'conftest.py', '# s2 crash\n')
    _git(clone, 'add', 'tests/conftest.py', 'scripts/verify_dev_counts.py')
    r = _commit(clone, 'z')
    assert r.returncode == 1 and 'verify_dev_counts.py could not run' in r.stderr
    assert 'dev-count drift' not in r.stderr


@pytest.mark.slow  # builds a venv (~1 s) and still runs collection attempts
def test_venv_without_pytest_is_an_environment_error_not_drift(clone, tmp_path):
    # Rounds 2-3 claimed this; the derivation failure was in fact folded into
    # the drift list and exited 3 (two round-4 reviewers reproduced it).
    bare = tmp_path / 'bare_venv'
    subprocess.run([str(REPO_ROOT / '.venv' / 'bin' / 'python'), '-m', 'venv',
                    '--without-pip', str(bare)], check=True)
    (clone / '.venv').unlink()
    (clone / '.venv').symlink_to(bare)
    _append(clone / 'tests' / 'conftest.py', '# no pytest here\n')
    _git(clone, 'add', 'tests/conftest.py')
    r = _commit(clone, 'np', STRIPPED_ENV)
    assert r.returncode == 1, r.stderr
    assert 'could not run' in r.stderr and 'derivation failed' in r.stderr
    assert 'dev-count drift' not in r.stderr


@pytest.mark.slow  # the deletion half triggers pytest collection (~5 s)
def test_renamed_toml_and_deleted_test_file_are_not_skipped(clone):
    # Pure rename (status R) of a TOML carrying the ai line: step 1 must see it.
    bad = clone / 'thresholds' / 'zz_ai_great.toml'
    bad.write_text('authored_by = "ai"\n')
    _git(clone, 'add', 'thresholds/zz_ai_great.toml')
    assert _git(clone, 'commit', '-q', '--no-verify', '-m', 'seed').returncode == 0
    _git(clone, 'mv', 'thresholds/zz_ai_great.toml', 'thresholds/zz_ai2_great.toml')
    r = _commit(clone, 'mv')
    assert r.returncode == 1 and 'AI-drafted prose' in r.stderr
    _git(clone, 'reset', '-q', '--hard')
    # Deletion (status D) of a test file the notes do not name: step 2 must run.
    notes = (clone / 'DEVELOPER_NOTES.md').read_text()
    victim = next(f for f in _run(clone, 'ls-files', 'tests')
                  if f.startswith('tests/test_') and f.endswith('.py') and Path(f).name not in notes)
    _git(clone, 'rm', '-q', victim)
    r = _commit(clone, 'del')
    assert 'dev-count' in r.stderr, (victim, r.stderr)  # drift or could-not-run: step 2 ran
    _git(clone, 'reset', '-q', '--hard')
    # Rename OUT of tests/ (round 5): with rename detection the diff listed
    # only the destination, so the count change never triggered step 2.
    _git(clone, 'mv', victim, 'docs/zz_moved_out.py')
    r = _commit(clone, 'mv-out')
    assert 'dev-count' in r.stderr, (victim, r.stderr)


@pytest.mark.slow  # pytest collection of the whole suite (~5 s)
def test_broken_test_module_is_an_environment_error_not_drift(clone):
    # Round 5: pytest exits 2 with "N tests collected, 1 error"; the partial N
    # was accepted and reported as drift (or matched and passed).
    (clone / 'tests' / 'test_zz_broken.py').write_text('def (:\n')
    _git(clone, 'add', 'tests/test_zz_broken.py')
    r = _commit(clone, 'broken')
    assert r.returncode == 1 and 'could not run' in r.stderr, r.stderr
    assert 'exited 2' in r.stderr and 'dev-count drift' not in r.stderr, r.stderr


def test_symlinked_ship_toml_is_rejected(clone):
    # `git show :path` on a symlink prints the TARGET PATH, so the ai line in
    # the target was invisible to step 1 (round 5, typechange/symlink lens).
    (clone / 'zz_target.toml').write_text('authored_by = "ai"\n')
    link = clone / 'thresholds' / 'zz_link_great.toml'
    link.symlink_to('../zz_target.toml')
    _git(clone, 'add', 'thresholds/zz_link_great.toml')
    r = _commit(clone, 'ln')
    assert r.returncode == 1 and 'symlinked ship-tracked' in r.stderr, r.stderr
    # Typechange (T): a tracked TOML replaced by a symlink is also caught.
    _git(clone, 'reset', '-q', '--hard')
    toml = next(f for f in _run(clone, 'ls-files', 'thresholds') if f.endswith('.toml'))
    (clone / toml).unlink()
    (clone / toml).symlink_to('../zz_target.toml')
    _git(clone, 'add', toml)
    r = _commit(clone, 'ty')
    assert r.returncode == 1 and 'symlinked ship-tracked' in r.stderr, r.stderr


def test_step1_reads_the_index_not_the_working_tree(clone):
    toml = next(f for f in _run(clone, 'ls-files', 'thresholds') if f.endswith('.toml'))
    p = clone / toml
    _append(p, '\nauthored_by = "ai"\n')
    _git(clone, 'add', toml)
    # Restore the WORKING COPY only; the index still holds the bad line.
    p.write_text(_git(clone, 'show', f'HEAD:{toml}').stdout)
    r = _commit(clone, 's1')
    assert r.returncode == 1 and 'AI-drafted prose' in r.stderr


def test_step1_large_toml_with_ai_line_at_top_is_still_caught(clone):
    # `grep -q` on a pipe under pipefail took SIGPIPE above ~450 KB and the
    # file passed silently (round-3 review); grep must read the whole blob.
    big = clone / 'thresholds' / 'zz_big_great.toml'
    big.write_text('authored_by = "ai"\n' + ('# padding line of no consequence\n' * 40000))
    assert big.stat().st_size > 1_000_000
    _git(clone, 'add', 'thresholds/zz_big_great.toml')
    r = _commit(clone, 'big')
    assert r.returncode == 1 and 'AI-drafted prose' in r.stderr


@pytest.mark.slow  # pytest collection of the whole suite (~5 s)
def test_step2_runs_under_stripped_path_and_reads_index_sentinels(clone):
    # Staging a tests/ file triggers step 2; the sibling script must find
    # its own interpreter (pre-fix: "derivation failed ... 'python'").
    # NOTE: test_count is checkout-dependent: modules skip themselves at
    # import without a sibling ../pvpoke clone (15 tests), node (5) or a
    # rendered userdata/ article (5), so a clean clone legitimately reports drift;
    # the pin here is "no interpreter error", not rc == 0.
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
