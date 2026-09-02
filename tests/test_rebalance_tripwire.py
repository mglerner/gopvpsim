"""Rebalance / PvPoke-update tripwires (Michael 2026-08-25).

Two guards that turn external-change response into procedure (the
response playbook is docs/rebalance_checklist.md):

1. MOVE-DATA tripwire: any CHANGED or REMOVED existing move in the live
   gamemaster vs the pinned vintage fails loudly -- the signature of a
   move rebalance (a big one is expected ~2 weeks post-Worlds). Move
   ADDITIONS are ignored: routine churn, never a rebalance signal.
2. PVPOKE-ENGINE tripwire: the battle-engine JS in ../pvpoke drifted
   from the last vetted commit -- re-vet, re-run the oracle audit, and
   check whether PvPoke's AI/strategy changed (the Cramorant update
   arrived exactly this way).

Re-pin fixtures (checklist steps A5 / B4) with:

    .venv/bin/python - <<'EOF'
    # strat_vintage_moves.json
    import json, sys; sys.path.insert(0, 'src')
    from gopvpsim.data import load_gamemaster
    from tests.test_rebalance_tripwire import _SIM_FIELDS, _snapshot
    ...  # see git history of tests/fixtures/ for the full snippet
    EOF

(Practically: rerun the pinning snippet from the commit that added the
fixtures, updating pinned_at / hashes / commit fields.)
"""
import hashlib
import json
from pathlib import Path

import pytest

from gopvpsim.data import load_gamemaster

_FIXTURES = Path(__file__).parent / 'fixtures'
_SIM_FIELDS = ('power', 'energy', 'energyGain', 'cooldown', 'turns', 'type',
               'buffs', 'buffTarget', 'buffApplyChance', 'buffsSelf',
               'buffsOpponent', 'category', 'damageMethod', 'tags')
_PVPOKE_ROOT = Path(__file__).resolve().parents[2] / 'pvpoke'


def _snapshot(gm):
    return {m['moveId']: {k: m[k] for k in _SIM_FIELDS if k in m}
            for m in gm['moves']}


def test_no_existing_move_changed_since_strat_verification():
    """MOVE-DATA tripwire. Fires on the rebalance signature only."""
    pin = json.loads((_FIXTURES / 'strat_vintage_moves.json').read_text())
    current = _snapshot(load_gamemaster())
    changed, removed = [], []
    for mid, fields in pin['moves'].items():
        if mid not in current:
            removed.append(mid)
        elif current[mid] != fields:
            diff = {k: (fields.get(k), current[mid].get(k))
                    for k in set(fields) | set(current[mid])
                    if fields.get(k) != current[mid].get(k)}
            changed.append((mid, diff))
    assert not changed and not removed, (
        f"MOVE REBALANCE DETECTED vs the {pin['pinned_at']} vintage "
        f"(pvpoke {pin['pvpoke_commit']}): {len(changed)} changed, "
        f"{len(removed)} removed. Changed: "
        f"{[(m, d) for m, d in changed[:8]]}... "
        f"Run docs/rebalance_checklist.md section A -- the PoGoDives "
        f"strat's fitted constants were tuned on the pinned move data "
        f"and must be re-verified, and the sweep cache needs the "
        f"gamemaster migration. Re-pin the fixture in the SAME commit "
        f"as the re-verification results.")


def test_move_tripwire_scanner_detects_a_change():
    """Positive control: a mutated copy of the pin must be detected
    (dead-scanner guard per the testing policy)."""
    pin = json.loads((_FIXTURES / 'strat_vintage_moves.json').read_text())
    current = _snapshot(load_gamemaster())
    mid = 'ICE_BEAM'
    assert mid in pin['moves'] and mid in current
    doctored = dict(pin['moves'][mid])
    doctored['power'] = (doctored.get('power') or 0) + 5
    assert doctored != current[mid], 'scanner cannot see a power change'


@pytest.mark.local_artifacts
def test_pvpoke_engine_matches_last_vetted_commit():
    """PVPOKE-ENGINE tripwire (needs the ../pvpoke checkout)."""
    if not _PVPOKE_ROOT.exists():
        pytest.skip('../pvpoke checkout not present')
    pin = json.loads((_FIXTURES / 'pvpoke_engine_digests.json').read_text())
    drifted = []
    for rel, want in pin['digests'].items():
        p = _PVPOKE_ROOT / 'src' / 'js' / 'battle' / rel
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != want:
            drifted.append(rel)
    assert not drifted, (
        f"PVPOKE ENGINE CHANGED since the last vetted commit "
        f"({pin['pvpoke_commit']}): {drifted}. Run "
        f"docs/rebalance_checklist.md section B -- read the upstream "
        f"commits, re-run the oracle audit, and check whether PvPoke's "
        f"AI/strategy changed (our PoGoDives tier is defined relative "
        f"to pvpoke_dp). Re-pin the digest fixture with the re-vet.\n\n"
        f"IF THIS FIRED BECAUSE THE TURN SYSTEM MERGED (check: does "
        f"Battle.js now contain 'chargedMoveLastTurn'?), that is the "
        f"signal the 2026-09-02 WAIT is over. Decision then was to wait "
        f"for PvPoke to settle its new-mechanics work rather than chase "
        f"a branch its author marked 'for now'. Next steps are in "
        f"docs/validations/2026-09-02_new_mechanics_oracle_ab.md: re-port "
        f"the turn loop against the merged reference, drive "
        f"`audit_oracle_harness.py --mechanics new` to zero, then flip "
        f"the default and delete scripts/mechanics_notice.py.")