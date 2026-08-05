"""ML-guide slug single-sourcing (DRY review 2026-08-05 entry 3d).

Five scripts once re-derived the producer's slug formulas by hand; a
drift would have made the completeness gates look for files nobody
writes. Both formulas live in ml_guide_slugs; this pins the formulas
and that every consumer routes through the module.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from ml_guide_slugs import article_slug, json_slug  # noqa: E402

_SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def test_formulas():
    assert json_slug('Dialga (Origin)') == 'dialga_origin'
    assert article_slug('Dialga (Origin)') == 'dialga-origin'
    assert json_slug('Zygarde (Complete Forme)') == 'zygarde_complete_forme'
    assert article_slug('Reshiram (Shadow)') == 'reshiram-shadow'


def test_consumers_route_through_the_module():
    for script in ('run_iv_guides.py', 'iv_envelope_analysis.py',
                   'chain_status.py', 'iv_guides_status.py',
                   'render_iv_envelope_article.py'):
        text = (_SCRIPTS / script).read_text()
        assert 'ml_guide_slugs' in text, script
        # No consumer may still hand-roll the formula (either variant).
        hand_rolled = re.compile(
            r"\.lower\(\)\.replace\(' ', '[-_]'\)\s*"
            r"(?:\n\s*)?\.replace\('\('")
        assert not hand_rolled.search(text), script


def test_run_iv_guides_reexports_for_verify_overnight():
    # verify_overnight reads rig.json_slug; the re-export must survive.
    import run_iv_guides as rig
    assert rig.json_slug is json_slug
    assert rig.article_slug is article_slug
