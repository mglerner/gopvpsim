#!/usr/bin/env python
"""Audit every PvPoke-oracle matchup in tests/test_battle.py against the
Node harness (scripts/pvpoke_trace.js).

Strategy: the test suite passing already proves our sim == each recorded
fixture, and the xfail cases are exactly the documented sim != PvPoke
divergences. So we don't re-type PvPoke's score matrices here (that would
just re-introduce the typo risk we're auditing for). Instead we run BOTH
our sim and the harness for all 9 shield combos of every oracle matchup
and compare score / winner / chargedLog directly:

  * non-divergence cell, sim == harness  -> fixture validated transitively
  * non-divergence cell, sim != harness  -> NEW divergence, must flag
  * divergence cell,     sim != harness  -> documented divergence intact
  * divergence cell,     sim == harness  -> divergence vanished, flag to un-xfail

Usage:
    python scripts/audit_oracle_harness.py [--pvpoke-root PATH]

Exit 0 if every cell is either an exact match or a still-present documented
divergence; nonzero otherwise.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tests'))
DEFAULT_PVPOKE_ROOT = Path.home() / 'coding' / 'MGLPoGo' / 'pvpoke'
HARNESS = REPO / 'scripts' / 'pvpoke_trace.js'

from test_battle import _make_battle_pokemon, _extract_battle_log  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp  # noqa: E402


def P(species, fast, charged, ivs, hid, shadow=False, level=None):
    """One side of a matchup. `species` is our display name; `hid` is the
    PvPoke speciesId for the harness. `level` pins an explicit level on
    BOTH engines — needed when our at_best_level (max 51, best buddy)
    and PvPoke's UI default disagree (e.g. UL Aegislash: PvPoke default
    is level 50; level 51 Shield yields a level-39 Blade instead of 38
    and every downstream damage/DP decision shifts)."""
    return dict(species=species, fast=fast, charged=list(charged),
                ivs=ivs, hid=hid, shadow=shadow, level=level)


# Every oracle matchup with a hand-typed PvPoke score/log in test_battle.py.
# xfail_cells: (s1, s2) combos pinned as documented divergences (Aegislash
# bug #3 cascade). Everything else must match the harness exactly.
MATCHUPS = [
    dict(label='medicham_vs_azumarill',
         p1=P('Medicham', 'PSYCHO_CUT', ['DYNAMIC_PUNCH', 'PSYCHIC'], (5, 15, 15), 'medicham'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], (8, 15, 15), 'azumarill')),
    dict(label='azumarill_vs_forretress_sand_rock',
         p1=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], (4, 15, 13), 'azumarill'),
         p2=P('Forretress', 'VOLT_SWITCH', ['SAND_TOMB', 'ROCK_TOMB'], (5, 15, 13), 'forretress')),
    dict(label='azumarill_vs_forretress_rt_only',
         p1=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'HYDRO_PUMP'], (4, 15, 13), 'azumarill'),
         p2=P('Forretress', 'VOLT_SWITCH', ['ROCK_TOMB'], (5, 15, 13), 'forretress')),
    dict(label='beedrill_vs_medicham_fell_stinger',
         p1=P('Beedrill', 'POISON_JAB', ['FELL_STINGER', 'X_SCISSOR'], (4, 15, 15), 'beedrill'),
         p2=P('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], (7, 15, 14), 'medicham')),
    dict(label='corviknight_vs_medicham_air_cutter',
         p1=P('Corviknight', 'AIR_SLASH', ['AIR_CUTTER', 'PAYBACK'], (4, 12, 14), 'corviknight'),
         p2=P('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], (7, 15, 14), 'medicham')),
    dict(label='mienfoo_vs_medicham_high_jump_kick',
         p1=P('Mienfoo', 'LOW_KICK', ['HIGH_JUMP_KICK', 'LOW_SWEEP'], (13, 15, 15), 'mienfoo'),
         p2=P('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], (7, 15, 14), 'medicham')),
    dict(label='corviknight_vs_azumarill_air_cutter_buff',
         p1=P('Corviknight', 'AIR_SLASH', ['AIR_CUTTER', 'PAYBACK'], (4, 12, 14), 'corviknight'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill')),
    dict(label='shadow_swampert_vs_registeel',
         p1=P('Swampert', 'MUD_SHOT', ['HYDRO_CANNON', 'EARTHQUAKE'], (15, 15, 15), 'swampert_shadow', shadow=True),
         p2=P('Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST'], (15, 15, 15), 'registeel')),
    dict(label='corviknight_mirror_both_buff',
         p1=P('Corviknight', 'AIR_SLASH', ['AIR_CUTTER'], (4, 12, 14), 'corviknight'),
         p2=P('Corviknight', 'AIR_SLASH', ['AIR_CUTTER'], (4, 12, 14), 'corviknight')),
    # Morpeko cells 1v1/1v2/2v1/2v2 differ on chargedLog only (score+winner
    # match). PvPoke bug #8: its Battle.js:1536 form-toggle guard makes
    # Morpeko stick in Hangry after the first charged move instead of
    # toggling back. OUR two-way toggle is correct (verified in-game
    # 2026-06-06). See DEVELOPER_NOTES "PvPoke bugs found" #8.
    dict(label='morpeko_vs_azumarill_form_change',
         p1=P('Morpeko (Full Belly)', 'THUNDER_SHOCK', ['AURA_WHEEL_ELECTRIC', 'PSYCHIC_FANGS'], (5, 14, 15), 'morpeko_full_belly'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill'),
         xfail_cells={(1, 1), (1, 2), (2, 1), (2, 2)}),
    dict(label='aegislash_vs_azumarill_form_change',
         p1=P('Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT', ['SHADOW_BALL', 'GYRO_BALL'], (4, 14, 15), 'aegislash_shield'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill'),
         xfail_cells={(0, 1), (0, 2), (1, 1), (1, 2), (2, 1), (2, 2)}),
    dict(label='mimikyu_vs_azumarill_form_change',
         p1=P('Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'], (5, 13, 15), 'mimikyu'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill')),
    # Opponent-side disguise (2026-06-24): every prior Mimikyu oracle row
    # had Mimikyu as player-0 (focal); now that PvPoke ranks Mimikyu in
    # GL+UL it is a real OPPONENT, so the dive carries Mimikyu rows where
    # the disguise mechanics run on the player-1 side. Mirror of
    # mimikyu_vs_azumarill_form_change with the sides swapped; same IVs /
    # default moveset.
    dict(label='azumarill_vs_mimikyu_form_change',
         p1=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill'),
         p2=P('Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'], (5, 13, 15), 'mimikyu')),
    # --- Form-change depth (2026-06-12, pre-publish gap fill: each form
    # species previously had exactly ONE oracle opponent, all Azumarill,
    # and Blade-as-focal / opponent-side form change had no 9-cell
    # coverage at all). IVs are PvPoke defaultIVs / already-audited
    # spreads; movesets via get_default_moveset or already-audited
    # variants. Data vintage verified clone==cache for all species+moves
    # 2026-06-12. ---
    # Blade-as-focal: exercises the Blade->Shield reversion-on-shielding
    # path in battle (the 07c6388 clamp fix only tested the level math).
    # Reversion itself verified identical to PvPoke (both swap stats AND
    # the fast move per Pokemon.js changeForm:2386-2394). xfails, traced
    # 2026-06-12: (1,2) is PvPoke bug #3 (its Aegislash throws Gyro Ball
    # where ours throws strictly-better Shadow Ball); (1,1) is the
    # near-KO plan-choice cluster — PvPoke banks 100 energy in safe
    # Shield form then double-Shadow-Balls (T44/T45) and WINS the cell;
    # ours throws at 50, re-Blades into paper form early, dies to chip.
    # PvPoke's plan is better in this cell, but the cluster is closed
    # as not-fixing (matching inverts the 6:1 cluster ratio — see
    # DEVELOPER_NOTES 'Near-KO DP plan choice').
    dict(label='aegislash_blade_vs_azumarill_form_change',
         p1=P('Aegislash (Blade)', 'PSYCHO_CUT', ['SHADOW_BALL', 'GYRO_BALL'], (4, 14, 15), 'aegislash_blade'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill'),
         xfail_cells={(1, 1), (1, 2)}),
    # Opponent-side form change: expands the single 0v0 cell (the "773"
    # oracle pin in test_dive_worker_form_change) to the full grid —
    # every GL dive carries Aegislash opponent rows in all 9 scenarios.
    # xfails, traced 2026-06-12: ALL six are PvPoke bug #3 seen from the
    # opponent side — every diverging log line is its Aegislash throwing
    # Gyro Ball where ours throws Shadow Ball. (2,1)/(2,2) are winner
    # flips: PvPoke's Aegislash burns Azu's shields on the weaker move
    # and LOSES a fight ours wins — the documented 'GB availability
    # actively hurts Aegislash' effect, not a new divergence. Azumarill's
    # own move choices agree in every cell (no bug-#2 manifestation).
    dict(label='azumarill_vs_aegislash_shield_form_change',
         p1=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill'),
         p2=P('Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT', ['SHADOW_BALL', 'GYRO_BALL'], (4, 14, 15), 'aegislash_shield'),
         xfail_cells={(1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)}),
    # Disguise vs fast-move pressure (Azumarill's Bubble is slow; Counter
    # chips the disguise differently and CMP differs).
    dict(label='mimikyu_vs_medicham_form_change',
         p1=P('Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'], (5, 13, 15), 'mimikyu'),
         p2=P('Medicham', 'COUNTER', ['DYNAMIC_PUNCH', 'ICE_PUNCH'], (7, 15, 14), 'medicham')),
    # Hangry where the Aura Wheel type flip matters: vs ground/steel the
    # Electric wheel is double-resisted but the Dark wheel is merely
    # steel-resisted, so Full Belly->Hangry changes effectiveness class.
    # xfails, traced 2026-06-12: all four are PvPoke bug #8 (Hangry
    # stickiness — its Battle.js:1536 guard leaves Morpeko stuck in
    # Hangry; our two-way toggle is in-game-verified 2026-06-06).
    # (2,0)/(2,1) are log-only (form label on the final move); (1,2)/
    # (2,2) cascade into score differences (same winner) because
    # G-Fisk's DP sees a different Aura Wheel threat from a stuck-
    # Hangry Morpeko and times Earthquake differently.
    dict(label='morpeko_vs_stunfisk_galarian_form_change',
         p1=P('Morpeko (Full Belly)', 'THUNDER_SHOCK', ['AURA_WHEEL_ELECTRIC', 'PSYCHIC_FANGS'], (5, 14, 15), 'morpeko_full_belly'),
         p2=P('Stunfisk (Galarian)', 'MUD_SHOT', ['ROCK_SLIDE', 'EARTHQUAKE'], (5, 15, 13), 'stunfisk_galarian'),
         xfail_cells={(1, 2), (2, 0), (2, 1), (2, 2)}),
    # UL Aegislash (2026-06-12): Aegislash opponent rows are live on the
    # published Tinkaton UL dive via ul_top60.txt, and UL
    # uses a different Blade-level formula (x0.75 vs GL's x0.5+1) — zero
    # UL form-change oracle cells existed. Movesets/IVs are PvPoke UL
    # defaults; vintage clone==cache verified (Tinkaton moves included).
    # Levels pinned to 50 on both sides (the PvPoke UI defaults the
    # dive opponent rows resolve to); our at_best_level would pick 51
    # (best buddy), which yields a level-39 Blade instead of 38 — a
    # different Pokemon, not a divergence.
    # xfails, traced 2026-06-12: every cell agrees on winner; (1,0)/
    # (1,1) are bug #3 (PvPoke's Aegislash burns Tinkaton's shield with
    # Gyro Ball and never lands a real charged hit — ours lands a
    # Shadow Ball, hence the ~280-pt margin gap); the small-margin
    # cells are Tinkaton-side shield-bait/plan-timing choices (e.g.
    # PvPoke's Tinkaton throws a third Bulldoze into the shield at
    # (0,1); ours holds) — the near-KO/plan-choice family. (0,0) is
    # exact.
    dict(label='tinkaton_vs_aegislash_shield_form_change', league='ultra',
         p1=P('Tinkaton', 'FAIRY_WIND', ['GIGATON_HAMMER', 'BULLDOZE'], (12, 15, 15), 'tinkaton', level=50),
         p2=P('Aegislash (Shield)', 'AEGISLASH_CHARGE_PSYCHO_CUT', ['SHADOW_BALL', 'GYRO_BALL'], (15, 15, 15), 'aegislash_shield', level=50),
         xfail_cells={(0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)}),
    # buffTarget='both' (Obstruct) fixture, added 2026-06-11 with the E1 fix.
    dict(label='obstagoon_obstruct_vs_azumarill',
         p1=P('Obstagoon', 'COUNTER', ['OBSTRUCT', 'NIGHT_SLASH'], (5, 15, 12), 'obstagoon'),
         p2=P('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13), 'azumarill')),
    # --- Ultra League (2026-06-11, review finding T6: the hand-typed UL
    # fixtures previously had no audit coverage at all) ---
    # Defender-bestCM selfDefenseDebuffing shield-gate fixture. The [1,2]
    # cell matched PvPoke exactly once the 2026-06-11 bait-wait fix
    # landed (the hold wrongly excluded self-debuffing cms[1]).
    dict(label='moltres_galarian_vs_florges', league='ultra',
         p1=P('Moltres (Galarian)', 'SUCKER_PUNCH', ['FLY', 'BRAVE_BIRD'], (4, 11, 11), 'moltres_galarian'),
         p2=P('Florges', 'FAIRY_WIND', ['CHILLING_WATER', 'DISARMING_VOICE'], (4, 13, 15), 'florges')),
    # MG near-KO plan-choice cluster (intentional divergence, DEVELOPER_
    # NOTES 'Near-KO DP plan choice'): our DP nukes with Brave Bird where
    # PvPoke serial-Flys. xfail_cells filled from the audited grid.
    # Audited grid 2026-06-11: (0,x) cells are the documented score-margin
    # divergences (our MG retains ~29pp more HP, jellicent family d1=-146;
    # near-KO plan choice, see DEVELOPER_NOTES). The (2,x) LOG-ONLY cells
    # pinned earlier the same day vanished with the bait-wait fix (the
    # hold wrongly excluded self-debuffing cms[1]).
    dict(label='jellicent_vs_moltres_galarian', league='ultra',
         p1=P('Jellicent', 'HEX', ['SURF', 'SHADOW_BALL'], (6, 14, 15), 'jellicent'),
         p2=P('Moltres (Galarian)', 'SUCKER_PUNCH', ['FLY', 'BRAVE_BIRD'], (1, 15, 15), 'moltres_galarian'),
         xfail_cells={(0, 0), (0, 1), (0, 2)}),
    dict(label='corviknight_vs_moltres_galarian', league='ultra',
         p1=P('Corviknight', 'SAND_ATTACK', ['AIR_CUTTER', 'PAYBACK'], (0, 15, 15), 'corviknight'),
         p2=P('Moltres (Galarian)', 'SUCKER_PUNCH', ['FLY', 'BRAVE_BIRD'], (1, 15, 15), 'moltres_galarian'),
         xfail_cells={(0, 0), (0, 1), (0, 2)}),
    # (1,2) is the documented WINNER FLIP (PvPoke's Fly plan correctly
    # wins the close fight; ours loses by 1 HP).
    dict(label='lapras_vs_moltres_galarian', league='ultra',
         p1=P('Lapras', 'PSYWAVE', ['SPARKLING_ARIA', 'ICE_BEAM'], (0, 15, 15), 'lapras'),
         p2=P('Moltres (Galarian)', 'SUCKER_PUNCH', ['FLY', 'BRAVE_BIRD'], (1, 15, 15), 'moltres_galarian'),
         xfail_cells={(1, 2)}),
]

LEAGUE_CP = {'great': '1500', 'ultra': '2500'}


def norm_log(entries):
    """Harness chargedLog tags shadow forms ' (Shadow)'; our _extract_battle_log
    drops it. Strip it so the two are comparable. Form suffixes (Blade,
    Busted, Hangry, Full Belly) are kept by both sides."""
    return [e.replace(' (Shadow)', '') for e in entries]


def run_sim(m, s1, s2):
    league = m.get('league', 'great')
    a = _make_battle_pokemon(m['p1']['species'], m['p1']['fast'], m['p1']['charged'],
                             league, s1, *m['p1']['ivs'], shadow=m['p1']['shadow'],
                             max_level=m['p1'].get('level') or 51.0)
    d = _make_battle_pokemon(m['p2']['species'], m['p2']['fast'], m['p2']['charged'],
                             league, s2, *m['p2']['ivs'], shadow=m['p2']['shadow'],
                             max_level=m['p2'].get('level') or 51.0)
    r = simulate(a, d, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp, log=True)
    return (round(r.pvpoke_score(0)), round(r.pvpoke_score(1)),
            r.winner, _extract_battle_log(r))


def run_harness(m, s1, s2, root):
    cp = LEAGUE_CP[m.get('league', 'great')]
    cmd = ['node', str(HARNESS), '--pvpoke-root', str(root), '--cp', cp,
           '--p1', m['p1']['hid'], '--p1-fast', m['p1']['fast'],
           '--p1-charged', ','.join(m['p1']['charged']),
           '--p1-ivs', '{}/{}/{}'.format(*m['p1']['ivs']), '--p1-shields', str(s1),
           '--p2', m['p2']['hid'], '--p2-fast', m['p2']['fast'],
           '--p2-charged', ','.join(m['p2']['charged']),
           '--p2-ivs', '{}/{}/{}'.format(*m['p2']['ivs']), '--p2-shields', str(s2)]
    for side in ('p1', 'p2'):
        if m[side].get('level'):
            cmd += [f'--{side}-level', str(m[side]['level'])]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f'harness rc={proc.returncode}: {proc.stderr.strip()}')
    d = json.loads(proc.stdout)
    return (round(d['score'][0]), round(d['score'][1]),
            d['winner'], norm_log(d['chargedLog']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pvpoke-root', type=Path, default=DEFAULT_PVPOKE_ROOT)
    ap.add_argument('--only', metavar='SUBSTR',
                    help='audit only matchups whose label contains SUBSTR '
                         '(triage helper; the full run is the gate)')
    args = ap.parse_args()
    if not args.pvpoke_root.exists():
        sys.stderr.write(f'PvPoke root not found: {args.pvpoke_root}\n')
        return 2
    matchups = [m for m in MATCHUPS
                if not args.only or args.only in m['label']]
    if not matchups:
        sys.stderr.write(f'--only {args.only!r} matched no labels\n')
        return 2

    new_divergences = []   # sim != harness on a cell NOT marked xfail
    vanished = []          # sim == harness on a cell marked xfail
    confirmed_div = []     # sim != harness on an xfail cell (expected)
    n_cells = 0

    for m in matchups:
        xfail = m.get('xfail_cells', set())
        print(f'\n{m["label"]}')
        for s1 in (0, 1, 2):
            for s2 in (0, 1, 2):
                n_cells += 1
                ss0, ss1, sw, slog = run_sim(m, s1, s2)
                hs0, hs1, hw, hlog = run_harness(m, s1, s2, args.pvpoke_root)
                score_ok = (ss0 == hs0 and ss1 == hs1)
                win_ok = (sw == hw)
                log_ok = (slog == hlog)
                match = score_ok and win_ok and log_ok
                cell = (s1, s2)
                is_xfail = cell in xfail
                if match:
                    tag = 'OK'
                    if is_xfail:
                        tag = 'VANISHED'
                        vanished.append((m['label'], cell))
                else:
                    if is_xfail:
                        tag = 'div(known)'
                        confirmed_div.append((m['label'], cell))
                    else:
                        tag = 'MISMATCH'
                        new_divergences.append(
                            (m['label'], cell,
                             f'sim s0/s1={ss0}/{ss1} win={sw}; '
                             f'harness s0/s1={hs0}/{hs1} win={hw}; '
                             f'log_ok={log_ok}'))
                flag = '' if (match or is_xfail) else '   <<<'
                print(f'  [{s1}v{s2}] {tag:11s} '
                      f'sim({ss0}/{ss1},w{sw})  pvpoke({hs0}/{hs1},w{hw})  '
                      f'log_ok={log_ok}{flag}')

    print('\n' + '=' * 70)
    print(f'cells checked: {n_cells}')
    print(f'confirmed documented divergences: {len(confirmed_div)}')
    for lbl, cell in confirmed_div:
        print(f'    {lbl} {cell}')
    if vanished:
        print(f'\nDIVERGENCES THAT VANISHED (consider un-xfail): {len(vanished)}')
        for lbl, cell in vanished:
            print(f'    {lbl} {cell}')
    if new_divergences:
        print(f'\nNEW / UNDOCUMENTED MISMATCHES: {len(new_divergences)}')
        for lbl, cell, detail in new_divergences:
            print(f'    {lbl} {cell}: {detail}')
    if not new_divergences and not vanished:
        print('\nAll oracle cells match the harness or are still-present '
              'documented divergences.')
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
