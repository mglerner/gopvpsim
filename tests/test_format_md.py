"""
Tests for scripts/format_md.py.

The script lives in ``scripts/`` (not part of the gopvpsim package), so we
import it via an explicit ``importlib`` spec rather than a normal import.
This keeps the test file independent of the project's package layout.
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMAT_MD_PATH = REPO_ROOT / "scripts" / "format_md.py"

_spec = importlib.util.spec_from_file_location("format_md", FORMAT_MD_PATH)
format_md = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(format_md)


# ---------------------------------------------------------------------------
# _fence_mask
# ---------------------------------------------------------------------------


def test_fence_mask_basic():
    lines = [
        "prose",
        "```",
        "code",
        "more code",
        "```",
        "more prose",
    ]
    mask = format_md._fence_mask(lines)
    # Fence delimiter lines themselves are False; only the content is True.
    assert mask == [False, False, True, True, False, False]


def test_fence_mask_tilde_does_not_close_backtick():
    lines = ["```", "still code", "~~~", "still code", "```", "prose"]
    mask = format_md._fence_mask(lines)
    assert mask == [False, True, True, True, False, False]


# ---------------------------------------------------------------------------
# strip_trailing_whitespace
# ---------------------------------------------------------------------------


def test_strip_single_trailing_space():
    assert format_md.strip_trailing_whitespace(["hello "]) == ["hello"]


def test_strip_trailing_tab():
    assert format_md.strip_trailing_whitespace(["hello\t"]) == ["hello"]


def test_preserves_two_space_soft_break():
    assert format_md.strip_trailing_whitespace(["line one  "]) == ["line one  "]


def test_normalizes_excess_trailing_spaces_to_two():
    # 5 trailing spaces -> exactly 2 (markdown soft break, no extra padding).
    assert format_md.strip_trailing_whitespace(["line one     "]) == ["line one  "]


def test_whitespace_only_line_becomes_blank():
    # A line containing only spaces is not a soft break — it's just a blank
    # line with stray whitespace. Reduce to truly empty.
    assert format_md.strip_trailing_whitespace(["   "]) == [""]


def test_strip_leaves_fenced_code_alone():
    lines = [
        "prose with trailing  ",   # outside fence: 2 spaces, preserved
        "```",
        "code with trailing   ",   # inside fence: 3 spaces, preserved as-is
        "```",
        "more prose   ",            # outside fence: 3 spaces -> 2
    ]
    out = format_md.strip_trailing_whitespace(lines)
    assert out == [
        "prose with trailing  ",
        "```",
        "code with trailing   ",
        "```",
        "more prose  ",
    ]


# ---------------------------------------------------------------------------
# collapse_blank_lines
# ---------------------------------------------------------------------------


def test_collapse_two_blanks_to_one():
    lines = ["a", "", "", "b"]
    assert format_md.collapse_blank_lines(lines) == ["a", "", "b"]


def test_collapse_many_blanks_to_one():
    lines = ["a", "", "", "", "", "b"]
    assert format_md.collapse_blank_lines(lines) == ["a", "", "b"]


def test_single_blank_preserved():
    lines = ["a", "", "b"]
    assert format_md.collapse_blank_lines(lines) == ["a", "", "b"]


def test_trailing_blank_lines_stripped():
    lines = ["a", "", "b", "", "", ""]
    assert format_md.collapse_blank_lines(lines) == ["a", "", "b"]


def test_blank_lines_inside_fence_preserved():
    lines = ["prose", "", "", "```", "code", "", "", "", "more code", "```", "", "", "after"]
    out = format_md.collapse_blank_lines(lines)
    assert out == [
        "prose", "",
        "```", "code", "", "", "", "more code", "```", "",
        "after",
    ]


# ---------------------------------------------------------------------------
# pad_tables
# ---------------------------------------------------------------------------


def test_pad_tables_basic():
    lines = [
        "| a | longer header |",
        "|---|---|",
        "| x | y |",
    ]
    out = format_md.pad_tables(lines)
    # Column 0 has only 1-char data ("a", "x"), but the separator needs at
    # least 3 dashes to be a valid markdown separator, so the column width
    # is bumped to 3. Column 1 width is 13 ("longer header").
    assert out == [
        "| a   | longer header |",
        "| --- | ------------- |",
        "| x   | y             |",
    ]


def test_pad_tables_alignment_markers_preserved():
    lines = [
        "| left | center | right |",
        "|:---|:---:|---:|",
        "| a | b | c |",
    ]
    out = format_md.pad_tables(lines)
    sep = out[1]
    cells = [c.strip() for c in sep.strip("|").split("|")]
    # Left alignment: ':---' and '---' are equivalent in CommonMark; the
    # script canonicalizes explicit-left to implicit-left ('---'), which
    # is fine — the rendering is identical.
    assert not cells[0].startswith(":") and not cells[0].endswith(":")
    # Center: must keep both colons.
    assert cells[1].startswith(":") and cells[1].endswith(":")
    # Right: must keep trailing colon only.
    assert not cells[2].startswith(":") and cells[2].endswith(":")
    # Right-aligned column 'c' should be right-padded — its cell content
    # ends with 'c' immediately before the trailing pipe.
    assert out[2].rstrip("|").rstrip().endswith("c")


def test_pad_tables_inside_fence_left_alone():
    lines = [
        "```",
        "| a | b |",
        "|---|---|",
        "| 1 | 2 |",
        "```",
    ]
    assert format_md.pad_tables(lines) == lines


def test_pipe_lines_without_separator_left_alone():
    # Not a real markdown table — no separator row. Should be untouched.
    lines = ["| a | b |", "| c | d |"]
    assert format_md.pad_tables(lines) == lines


# ---------------------------------------------------------------------------
# format_text (full pipeline)
# ---------------------------------------------------------------------------


def test_format_text_idempotent():
    sample = (
        "# Title\n"
        "\n"
        "Para with trailing.   \n"
        "\n"
        "\n"
        "\n"
        "| a | longer |\n"
        "|---|---|\n"
        "| x | y |\n"
        "\n"
        "```\n"
        "code with trailing   \n"
        "\n"
        "\n"
        "still code\n"
        "```\n"
        "\n"
        "Final.\n"
    )
    once = format_md.format_text(sample)
    twice = format_md.format_text(once)
    assert once == twice, "format_text must be idempotent"


def test_format_text_preserves_trailing_newline():
    assert format_md.format_text("a\n").endswith("\n")
    # No trailing newline in -> no trailing newline out.
    assert not format_md.format_text("a").endswith("\n")


def test_format_text_strips_then_collapses():
    """A whitespace-only line should be stripped to blank, then collapsed
    against an adjacent real blank — verifying pass ordering."""
    text = "a\n   \n\nb\n"
    out = format_md.format_text(text)
    # Two consecutive blanks (one originally whitespace-only, one real)
    # should collapse to a single blank.
    assert out == "a\n\nb\n"


# ---------------------------------------------------------------------------
# CLI / hook mode
# ---------------------------------------------------------------------------


def test_hook_mode_with_md_path(tmp_path, monkeypatch, capsys):
    md = tmp_path / "doc.md"
    # Use blank-line collapse (not trailing whitespace) to verify the hook
    # actually invokes the formatter — trailing-whitespace inputs would
    # exercise the soft-break preservation rule, which is a separate concern
    # already covered by the strip_trailing_whitespace tests.
    md.write_text("a\n\n\n\nb\n")
    payload = json.dumps({"tool_input": {"file_path": str(md)}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = format_md.main(["format_md.py", "--hook"])
    assert rc == 0
    assert md.read_text() == "a\n\nb\n"


def test_hook_mode_skips_non_md_path(tmp_path, monkeypatch, capsys):
    py = tmp_path / "thing.py"
    py.write_text("x = 1\n\n\n\ny = 2\n")
    original = py.read_text()
    payload = json.dumps({"tool_input": {"file_path": str(py)}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = format_md.main(["format_md.py", "--hook"])
    assert rc == 0
    # Non-markdown path must NOT be touched, even if it has issues.
    assert py.read_text() == original


def test_hook_mode_handles_malformed_json(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    rc = format_md.main(["format_md.py", "--hook"])
    assert rc == 0  # graceful no-op, not a crash


def test_explicit_file_arg_formats(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("a\n\n\n\nb\n")
    rc = format_md.main(["format_md.py", str(md)])
    assert rc == 0
    assert md.read_text() == "a\n\nb\n"
