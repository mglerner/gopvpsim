"""Tests for ``synthesize_mirror_tier`` in ``scripts/deep_dive_analysis.py``.

Pins two review fixes (2026-06-11):

- D6: a shadow focal's mirror is the '<species> (Shadow)' pool entry —
  with ``focal_shadow=True`` the synth must match the shadow opponent
  column and shadow-opponent anchors, not the plain entry.
- R4: the "an existing tier already names the focal species" bail used
  substring containment, so a sibling-form tier name (e.g. 'Oinkologne
  (Female) Bulk' for focal 'Oinkologne') wrongly suppressed synthesis.

All inputs are synthetic — no gamemaster, no sims.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from gopvpsim.anchors import ResolvedAnchor

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PATH = REPO_ROOT / "scripts" / "deep_dive_analysis.py"

_spec = importlib.util.spec_from_file_location("deep_dive_analysis", ANALYSIS_PATH)
analysis = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(analysis)


def _anchor(opponent, threshold=100.0, target_stat='def', strict=True):
    return ResolvedAnchor(
        name=f"auto_{opponent.lower().replace(' ', '_')}_blkp_any",
        parent="p", kind="bulkpoint",
        threshold_value=threshold, target_stat=target_stat, strict=strict,
        label="t", description=None, source=None,
        parent_display_name="P", opponent=opponent,
    )


def _synth_inputs(nIvs=4, nS=1, opponents=("Sableye", "Sableye (Shadow)")):
    """Two IVs above the def=100 threshold (win vs every opponent column
    we mark winnable), two below. Scores: the PLAIN mirror column is all
    losses (so matching it can't produce a tier); the SHADOW column is a
    clean partition (passers win, failers lose)."""
    nO = len(opponents)
    scores = np.zeros((nIvs, nS, nO))
    iv_def = [110.0, 105.0, 95.0, 90.0]   # first two pass def>100
    iv_atk = [100.0] * nIvs
    iv_hp = [140, 141, 142, 143]
    for oi, name in enumerate(opponents):
        if name.endswith('(Shadow)'):
            scores[:2, :, oi] = 700   # passers win the shadow mirror
            scores[2:, :, oi] = 300
        else:
            scores[:, :, oi] = 300    # everyone loses the plain column
    data_obj = {'ivAtk': iv_atk, 'ivDef': iv_def, 'ivHp': iv_hp}
    return dict(
        scores_flat=scores.ravel().tolist(),
        nIvs=nIvs, nS=nS, nO=nO,
        data_obj=data_obj,
        scenarios=[[1, 1]],
        opponents=list(opponents),
    )


class TestShadowFocalMirror:
    def test_shadow_focal_matches_shadow_pool_entry(self):
        kw = _synth_inputs()
        tier = analysis.synthesize_mirror_tier(
            species='Sableye',
            resolved_anchors=[_anchor('Sableye (Shadow)')],
            existing_tiers=[],
            focal_shadow=True,
            **kw,
        )
        # The shadow column is the clean partition — the tier must derive
        # from it and carry the shadow-qualified name.
        assert tier is not None
        assert tier['name'] == 'Sableye (Shadow) Mirror Bulk'
        assert tier['defense'] == pytest.approx(100.0)

    def test_shadow_focal_ignores_plain_entry_and_anchors(self):
        # Only the PLAIN entry/anchors exist: a shadow focal must bail
        # (mirror not simulated) rather than derive against the plain
        # column — that column is a different Pokemon.
        kw = _synth_inputs(opponents=("Sableye",))
        tier = analysis.synthesize_mirror_tier(
            species='Sableye',
            resolved_anchors=[_anchor('Sableye')],
            existing_tiers=[],
            focal_shadow=True,
            **kw,
        )
        assert tier is None

    def test_plain_focal_unchanged(self):
        # Non-shadow focal with a winnable plain column still synthesizes
        # against the plain entry (regression guard for the default path).
        kw = _synth_inputs(opponents=("Sableye", "Sableye (Shadow)"))
        # Make the plain column the clean partition instead.
        scores = np.asarray(kw['scores_flat']).reshape(kw['nIvs'], kw['nS'], kw['nO'])
        scores[:2, :, 0] = 700
        scores[2:, :, 0] = 300
        kw['scores_flat'] = scores.ravel().tolist()
        tier = analysis.synthesize_mirror_tier(
            species='Sableye',
            resolved_anchors=[_anchor('Sableye')],
            existing_tiers=[],
            focal_shadow=False,
            **kw,
        )
        assert tier is not None
        assert tier['name'] == 'Sableye Mirror Bulk'


class TestSiblingFormBail:
    def test_sibling_form_tier_does_not_suppress_synthesis(self):
        # R4: 'Oinkologne (Female) Bulk' must NOT bail synthesis for
        # focal 'Oinkologne' — the substring match used to.
        kw = _synth_inputs(opponents=("Oinkologne",))
        scores = np.asarray(kw['scores_flat']).reshape(kw['nIvs'], kw['nS'], kw['nO'])
        scores[:2, :, 0] = 700
        scores[2:, :, 0] = 300
        kw['scores_flat'] = scores.ravel().tolist()
        tier = analysis.synthesize_mirror_tier(
            species='Oinkologne',
            resolved_anchors=[_anchor('Oinkologne')],
            existing_tiers=[{'name': 'Oinkologne (Female) Bulk'}],
            focal_shadow=False,
            **kw,
        )
        assert tier is not None

    def test_same_form_tier_still_bails(self):
        kw = _synth_inputs(opponents=("Oinkologne",))
        tier = analysis.synthesize_mirror_tier(
            species='Oinkologne',
            resolved_anchors=[_anchor('Oinkologne')],
            existing_tiers=[{'name': 'Oinkologne Mirror Bulk'}],
            focal_shadow=False,
            **kw,
        )
        assert tier is None
