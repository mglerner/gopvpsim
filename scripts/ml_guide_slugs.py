"""Single source for the ML IV-guide slug formulas.

The producer (iv_envelope_analysis.py) writes
``userdata/dives/{json_slug}_iv_envelope*.json`` and its per-guide log
under the same slug; the renderer publishes to
``userdata/website/articles/{article_slug}-ml-iv-guide``. Five scripts
once re-derived one or both formulas by hand (producer, driver, two
watch views, renderer) and two gates checked the producer's output
under a re-derived name -- a formula drift would have made the
completeness gate look for files nobody writes. Both formulas live
HERE now (a tiny module so the log watchers never import the heavy
producer); DRY review 2026-08-05 entry 3d.
"""


def json_slug(species: str) -> str:
    """'Dialga (Origin)' -> 'dialga_origin' (JSON + per-guide-log slug)."""
    return species.lower().replace(' ', '_').replace('(', '').replace(')', '')


def article_slug(species: str) -> str:
    """'Dialga (Origin)' -> 'dialga-origin' (published article dir slug)."""
    return species.lower().replace(' ', '-').replace('(', '').replace(')', '')
