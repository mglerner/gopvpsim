"""Dive->article slug resolution (docs/article_schema.md link contract).

The slug's durable home is `[<Species>.article] slug` in
`thresholds/<species>.toml`.  Before 2026-08-27 only main()'s thresholds
AUTO-DISCOVER path read it, so a `--no-thresholds` dive (Cramorant) lost the
link on any plain CLI rebake and the link had to be re-injected by hand into
the replay state before every re-render.  These tests pin the resolver and
the two paths that now use it.
"""
import sys
from pathlib import Path

import pytest

from tests.conftest import load_deep_dive

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

deep_dive = load_deep_dive()

THRESHOLDS = REPO_ROOT / "thresholds"


def test_cramorant_article_slug_has_a_durable_home():
    """thresholds/cramorant.toml carries the strategy-article slug."""
    assert (THRESHOLDS / "cramorant.toml").exists()
    assert (deep_dive.article_slug_from_thresholds("Cramorant")
            == "cramorant-pogodives-strategy")


def test_thievul_precedent_still_resolves():
    """The precedent file the Cramorant registration was modeled on."""
    assert (deep_dive.article_slug_from_thresholds("Thievul")
            == "thievul-cd-2026-08")


def test_absent_file_or_table_resolves_empty():
    # No thresholds file at all.
    assert deep_dive.article_slug_from_thresholds("Nosuchmon") == ""
    # Real thresholds file, no [article] table (positive control: if
    # azumarill.toml ever gains one, this test should be re-pointed, not
    # deleted -- the empty case must stay covered).
    assert (THRESHOLDS / "azumarill.toml").exists()
    assert deep_dive.article_slug_from_thresholds("Azumarill") == ""


def test_shadow_focal_uses_the_shadow_file_and_key(tmp_path):
    """A shadow focal must not inherit the base species' article slug."""
    (tmp_path / "sableye.toml").write_text(
        '[Sableye.article]\nslug = "base-article"\n')
    (tmp_path / "sableye_shadow.toml").write_text(
        '["Sableye (Shadow)".article]\nslug = "shadow-article"\n')
    resolve = deep_dive.article_slug_from_thresholds
    assert resolve("Sableye", thresholds_dir=tmp_path) == "base-article"
    assert resolve("Sableye", shadow=True,
                   thresholds_dir=tmp_path) == "shadow-article"
    # Wrong-key file: a shadow file keyed on the bare species name yields
    # nothing rather than silently inheriting.
    (tmp_path / "furret_shadow.toml").write_text(
        '[Furret.article]\nslug = "wrong-key"\n')
    assert resolve("Furret", shadow=True, thresholds_dir=tmp_path) == ""


def _minimal_state(**over):
    """Smallest state dict render_dive_html accepts (single-file branch)."""
    state = {
        "species": "Cramorant",
        "league": "great",
        "shadow": False,
        "article_slug": "",
        "split_movesets": False,
        "moveset_data": [{"name": "m1"}],
        "reference_idx": 0,
        "html_path": "",
        "thresholds": None,
        "opponent_label": "",
        "shield_scenarios": [],
        "opponent_names": [],
        "opp_iv_modes": [],
        "standalone": True,
        "slayer_iter_result": None,
        "cli_args_str": "",
        "has_toml_tiers": False,
        "threshold_registry": None,
        "species_narrative": {},
        "shared_plotly_dir": None,
    }
    state.update(over)
    return state


def _capture_render(monkeypatch, state):
    seen = {}

    def _fake_generate(*a, **kw):
        seen.update(kw)

    monkeypatch.setattr(deep_dive, "generate_interactive_html", _fake_generate)
    monkeypatch.setattr(deep_dive, "_remove_stale_split_siblings",
                        lambda *a, **kw: None)
    deep_dive.render_dive_html(state)
    return seen


def test_render_dive_html_fills_an_empty_slug_from_thresholds(
        monkeypatch, tmp_path):
    """Replay/rebake fallback: no hand-injected state['article_slug'] needed.

    Pre-fix value: '' (the blob's baked-in empty slug went straight through
    to the renderer, so the re-rendered page had no article link).
    """
    state = _minimal_state(html_path=str(tmp_path / "index.html"))
    seen = _capture_render(monkeypatch, state)
    assert seen["article_slug"] == "cramorant-pogodives-strategy"


def test_render_dive_html_keeps_an_explicit_slug(monkeypatch, tmp_path):
    state = _minimal_state(html_path=str(tmp_path / "index.html"),
                           article_slug="explicitly-set")
    seen = _capture_render(monkeypatch, state)
    assert seen["article_slug"] == "explicitly-set"


def test_no_thresholds_path_reads_the_article_slug():
    """main()'s --no-thresholds branch must resolve the slug.

    The branch is inline in main() (not callable), so this pins the call
    site: the opt-out branch routes through the resolver rather than
    leaving _article_slug = ''.
    """
    src = (REPO_ROOT / "scripts" / "deep_dive.py").read_text()
    head, _, tail = src.partition("elif args.no_thresholds:")
    assert tail, "the --no-thresholds branch was renamed"
    branch = tail.partition("\n    else:")[0]
    assert "article_slug_from_thresholds(args.species, args.shadow)" in branch


@pytest.mark.local_artifacts
def test_published_cramorant_dive_carries_the_link():
    """Rendered-artifact check: the shipped page emits the relative link."""
    page = (REPO_ROOT / "userdata" / "website" / "cramorant-great-league"
            / "index.html")
    if not page.exists():
        pytest.skip("no locally built Cramorant dive")
    assert "../articles/cramorant-pogodives-strategy/" in page.read_text()
