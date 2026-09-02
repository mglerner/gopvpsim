"""The one place the turn-model caveat is worded.

As of 2026-09-02 there is no `--mechanics` setting that is simply correct, and
BOTH need saying out loud at the point of use:

* ``legacy`` is the default everywhere, and it models the pre-2026-09-02 turn
  system. Michael reported that system is gone from the live game as of
  2026-09-02. So the default path now describes a ruleset the game no longer
  runs -- and it says so nowhere, which is the more dangerous of the two
  because nobody has to opt into it.
* ``new`` is our reading of the published spec. It has now been measured
  against PvPoke's implementation for the first time and disagrees on 104 of
  243 oracle cells; the two models depart from legacy in different directions
  (docs/validations/2026-09-02_new_mechanics_oracle_ab.md).

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
    "mechanics=legacy models the PRE-2026-09-02 turn system, which the live "
    "game no longer runs (reported 2026-09-02). It still matches PvPoke "
    "master, so the oracle stays green -- that certifies agreement with "
    "PvPoke's legacy model, NOT with the game. Do not publish spreads from "
    "this without saying so."
)

_NEW = (
    "mechanics=new is UNVALIDATED. Measured 2026-09-02 against PvPoke's "
    "new-mechanics branch (the first reference that has ever existed for it): "
    "104 of 243 oracle cells disagree, and the two models depart from legacy "
    "in different directions, so this is not a one-constant fix. PvPoke's own "
    "branch is unmerged and its author reverted the charged-attack timing "
    "rule we implement, marking it 'for now'. See "
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
