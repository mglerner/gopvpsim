"""The one place the turn-model caveat is worded.

As of 2026-09-02 there is no `--mechanics` setting that is simply correct, and
BOTH need saying out loud at the point of use.

The product CLIs default to ``new`` (changed 2026-09-02, Michael): the legacy
turn system is gone from the live game, so a dive that models it describes a
game nobody can play. Modelling the current ruleset approximately beats
modelling a dead one exactly.

* ``new`` is our reading of the published spec, and it is UNVALIDATED. Measured
  2026-09-02 against PvPoke's implementation for the first time: 104 of 243
  oracle cells disagree, and the two models depart from legacy in different
  directions, so it is not a one-constant fix
  (docs/validations/2026-09-02_new_mechanics_oracle_ab.md). This is now the
  DEFAULT, which makes the caveat more important, not less.
* ``legacy`` models the pre-2026-09-02 turn system. It is no longer the
  product default, but it is NOT dead code: it is what the port-fidelity suite
  checks against PvPoke master (0/243 mismatches), and that is what proves our
  port is faithful. Keep it until PvPoke's turn-system work merges.

Project rule (CLAUDE.md): a known-wrong result must be fixed, flagged where it
appears, or not produced. Neither setting can be fixed today -- the decision
(Michael, 2026-09-02) is to WAIT for PvPoke to merge its new-mechanics work to
master, on the reasoning that if it does not match the live game its author
will notice and fix it quickly. So: flagged.

DELETE THIS MODULE, and its call sites, when the wait ends -- i.e. when
origin/twilight-trails merges to master, our turn loop is re-ported against
it, and the oracle harness runs green under ``--mechanics new``. It exists to
make an interim state visible, not to become furniture.

Kept in scripts/ deliberately: gopvpsim/battle.py is a sweep-cache engine-hash
file, so putting a string constant there would bump the engine hash and stale
every cached column for a docs change.
"""

_LEGACY = (
    "mechanics=legacy is NOT the default any more and models the "
    "PRE-2026-09-02 turn system, which the live game no longer runs. It still "
    "matches PvPoke master exactly (0/243), which is why the port-fidelity "
    "suite uses it -- but that certifies agreement with PvPoke's legacy "
    "model, NOT with the game. Do not publish spreads from this."
)

_NEW = (
    "mechanics=new is the default as of 2026-09-02 because the legacy turn "
    "system is gone from the live game -- but it is UNVALIDATED. Measured "
    "against PvPoke's new-mechanics branch (the first reference that has ever "
    "existed for it): 104 of 243 oracle cells disagree, and the two models "
    "depart from legacy in different directions, so this is not a "
    "one-constant fix. PvPoke's branch is unmerged and its author reverted "
    "the charged-attack timing rule we implement, marking it 'for now'. "
    "Numbers from this model the right ruleset approximately; they are not "
    "cross-checked against anything. See "
    "docs/validations/2026-09-02_new_mechanics_oracle_ab.md."
)


def mechanics_caveat(mechanics):
    """Return the caveat string for a turn model, or None if there is none."""
    if mechanics == 'legacy':
        return _LEGACY
    if mechanics == 'new':
        return _NEW
    return None


def warn_mechanics(mechanics, emit):
    """Emit the caveat via ``emit`` (a logger.warning or a print-like callable).

    Takes the emitter rather than choosing one: deep_dive routes through its
    structured logger (a bare print from a worker buffers badly and bypasses
    the log file), while scripts/battle.py has no logger and writes to stderr.
    """
    msg = mechanics_caveat(mechanics)
    if msg:
        emit(msg)
    return msg
