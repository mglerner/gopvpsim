"""Tests for ``gopvpsim.evolution_lines``.

Integration tests: depend on the live PvPoke gamemaster. Mark as
``integration`` so a hermetic unit-test run can skip them.
"""
import pytest

from gopvpsim.evolution_lines import (
    get_final_forms,
    load_evolution_lines,
    get_final_form,
    invalidate_cache,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Ensure each test sees a freshly-built evolution map. The module
    caches at process scope, so a single bad fixture or a previous
    test's mutation could otherwise contaminate downstream runs."""
    invalidate_cache()
    yield
    invalidate_cache()


# ===========================================================================
# Straightforward chains (unbranching) — sanity baseline
# ===========================================================================

@pytest.mark.integration
@pytest.mark.parametrize("pre,final", [
    ("Tinkatink", "Tinkaton"),
    ("Tinkatuff", "Tinkaton"),
    ("Tinkaton", "Tinkaton"),     # final → self
    ("Bunnelby", "Diggersby"),
])
def test_unambiguous_chain(pre, final):
    assert get_final_forms(pre) == [final]


# ===========================================================================
# Branching evolutions — Eevee + Lechonk (after the sibling-form fix)
# ===========================================================================

@pytest.mark.integration
def test_eevee_branches_to_eight_finals():
    """Eevee has 8 reachable final forms; sanity-check the count and
    that the list is sorted."""
    finals = get_final_forms("Eevee")
    assert len(finals) == 8
    assert finals == sorted(finals)


@pytest.mark.integration
def test_lechonk_has_both_oinkologne_forms():
    """Regression guard for the 2026-05-17 sibling-form fix
    (commit 1b59c83). PvPoke's gamemaster lists Lechonk's
    `evolutions` field as ['oinkologne', 'oinkologne'] — both
    entries point at the bare Male form's speciesId. So
    Oinkologne (Female) only reaches the matcher via the
    sibling-form pass in _build_evolution_lines: it has
    parent='lechonk' in its own entry but isn't listed as an
    evolution target on Lechonk.

    If this test breaks, paste-box detection on the Female
    Oinkologne dive silently breaks too — every Lechonk in a
    Poke Genie CSV would fail to be considered a potential
    Oinkologne (Female).
    """
    finals = get_final_forms("Lechonk")
    assert "Oinkologne" in finals
    assert "Oinkologne (Female)" in finals
    # Sorted invariant.
    assert finals == sorted(finals)


@pytest.mark.integration
def test_oinkologne_female_final_form_self_lookup():
    """The Female form should be its own final-form key too — the
    forward walk produces this via the `oinkologne_female` speciesId
    (it appears in the gamemaster with parent='lechonk' but no
    outgoing evolutions). Belt-and-suspenders against the sibling-
    form fix accidentally only populating reverse-walk, not forward."""
    assert get_final_forms("Oinkologne (Female)") == ["Oinkologne (Female)"]
    assert get_final_forms("Oinkologne") == ["Oinkologne"]


# ===========================================================================
# get_final_form (singular) — error on branching
# ===========================================================================

@pytest.mark.integration
def test_get_final_form_singular_on_unambiguous():
    assert get_final_form("Tinkatink") == "Tinkaton"


@pytest.mark.integration
def test_get_final_form_raises_on_branching():
    """get_final_form (singular) is for callers that KNOW the chain
    is unambiguous. Lechonk is now branching (Male + Female), so
    callers that pass Lechonk should get the ValueError nudge to
    switch to get_final_forms."""
    with pytest.raises(ValueError, match="branching"):
        get_final_form("Lechonk")


# ===========================================================================
# Finals shared across roots — Burmy → Mothim (cross-repo CP13)
# ===========================================================================

@pytest.mark.integration
@pytest.mark.parametrize("burmy,wormadam", [
    ("Burmy (Plant)", "Wormadam (Plant)"),
    ("Burmy (Sandy)", "Wormadam (Sandy)"),
    ("Burmy (Trash)", "Wormadam (Trash)"),
])
def test_burmy_reaches_own_wormadam_and_shared_mothim(burmy, wormadam):
    """Regression guard for the 2026-06-12 shared-final fix (gobattlekit
    review CP13). The family-wide visited set used to keep only the
    first root's chain to the shared Mothim final, so Burmy (Sandy) /
    (Trash) rows were invisible to Mothim targets. Every cloak must
    reach both its own Wormadam and the shared Mothim."""
    finals = get_final_forms(burmy)
    assert wormadam in finals
    assert "Mothim" in finals
    assert finals == sorted(finals)


@pytest.mark.integration
def test_mothim_chain_merges_all_burmy_roots():
    """The Mothim entry merges pre-evo members from every root path,
    with the final staying last (mirrors gobattlekit 2256a80)."""
    chain = load_evolution_lines()["Mothim"]
    assert chain[-1] == "Mothim"
    assert {"Burmy (Plant)", "Burmy (Sandy)", "Burmy (Trash)"} <= set(chain[:-1])
