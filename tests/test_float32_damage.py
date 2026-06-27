"""Regression: damage uses the game's float32-truncated constants, not exact
1.3 / 1.2 / 1.6.

The game (and PvPoke's DamageCalculator.js) compute damage in single precision,
so BONUS / STAB / SUPER_EFFECTIVE are the float32 roundings of 1.3 / 1.2 / 1.6.
~0.009% of damage calcs land one integer higher than exact doubles would --
precisely on the breakpoint/bulkpoint boundaries that are this project's
deliverable. Matching the truncated constants makes our boundaries agree with
PvPoke and the game.

Found by the 2026-06-27 adversarial engine bug-hunt (issue #2); see
docs/reviews/2026-06-27_engine_bug_hunt.md. The boundary case below was
validated against PvPoke's live engine via scripts/pvpoke_trace.js: Tinkaton
Play Rough vs Gourgeist (Small) at 15/15/15 GL -- exact doubles give 51, the
float32 constants give 52 (PvPoke and the game agree on 52).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_battle import _make_battle_pokemon  # noqa: E402
from gopvpsim import data, moves  # noqa: E402


def test_play_rough_vs_gourgeist_small_float32_boundary():
    gf, gc = data.get_default_moveset('Gourgeist (Small)', 'great')
    tink = _make_battle_pokemon('Tinkaton', 'FAIRY_WIND', ['PLAY_ROUGH'],
                                'great', 0, 15, 15, 15)
    gour = _make_battle_pokemon('Gourgeist (Small)', gf, gc, 'great', 0, 15, 15, 15)
    _, cm = moves.get_moves()
    pr = cm['PLAY_ROUGH']
    dmg = moves.damage(pr['power'], tink.atk, gour.def_, pr['type'],
                       tink.types, gour.types)
    assert dmg == 52  # exact doubles would give 51


def test_damage_constants_are_float32_truncated():
    # The exact float32-of-(1.3 / 1.2 / 1.6) doubles PvPoke's DamageMultiplier uses.
    assert moves.BONUS == 1.2999999523162841796875
    assert moves.STAB_MULTIPLIER == 1.2000000476837158203125
    assert moves.SUPER_EFFECTIVE == 1.60000002384185791015625
