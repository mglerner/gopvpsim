"""The one place the turn-model caveat is worded.

REWRITTEN 2026-09-09, when PvPoke merged its new-mechanics work to master.
Before that neither ``--mechanics`` setting was defensible and both needed a
caveat. That interim is over:

* ``new`` is the default everywhere -- ``simulate()`` itself, the product CLIs,
  and the oracle harness. It is the ruleset the live game runs, and it is now
  cross-checked: 237 of 243 oracle cells match PvPoke master exactly.
* ``legacy`` models the pre-2026-09-02 turn system, which the game no longer
  runs AND which PvPoke master no longer implements. It is not a supported
  choice; it survives only so the port-fidelity history stays runnable.

So there is exactly one caveat left, and it is narrow rather than sweeping.

DELETE THIS MODULE and its two call sites when the 6 cells below are resolved
-- either by fixing them or by promoting them to documented xfails with an
agreed reason. It exists to disclose a specific open divergence, not to be
permanent furniture.

Kept in scripts/ deliberately: gopvpsim/battle.py is a sweep-cache engine-hash
file, so putting a string constant there would bump the engine hash and stale
every cached column for a docs change.
"""

_NEW = (
    "mechanics=new matches PvPoke master on 237 of 243 oracle cells. The 6 "
    "that differ are ALL Aegislash vs Azumarill under form change, and all 6 "
    "agree on the WINNER -- they differ in score (50-142 points) because our "
    "Aegislash banks 100 energy in Shield form and throws on T44 where PvPoke "
    "commits on T30. Which is correct is UNRESOLVED: farming in Shield and "
    "bursting in Blade is the species' actual gimmick, and PvPoke's rating is "
    "damage-weighted, so it penalises farming even in a fight we win. Read "
    "Aegislash form-change numbers with that open question in mind. See "
    "docs/validations/2026-09-09_oracle_new_vs_master_raw.txt."
)

_LEGACY = (
    "mechanics=legacy models the PRE-2026-09-02 turn system. The live game "
    "does not run it and PvPoke master no longer implements it, so this "
    "setting compares a dead model against nothing. It is retained only to "
    "keep the port-fidelity history runnable. Do not publish from it."
)


def mechanics_caveat(mechanics):
    """Return the caveat string for a turn model, or None if there is none."""
    if mechanics == 'new':
        return _NEW
    if mechanics == 'legacy':
        return _LEGACY
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
