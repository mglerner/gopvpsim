#!/usr/bin/env python
"""Build (and locally verify) replayable pvpoke.com battle/sandbox links.

Purpose
-------
Our engine can play lines PvPoke's AI never would (the PoGoDives strategy
sheet, energy-advantage what-ifs, hand-authored "what if I bait here"
questions).  A reader can only *check* such a claim if they can replay it
on pvpoke.com.  PvPoke's Sandbox mode exists for exactly that: the URL
carries an explicit action script, and the simulator replays it instead
of running its AI.

This module turns a ``gopvpsim.battle.simulate()`` result into that URL,
and verifies the URL by decoding it the way pvpoke.com's own routing and
``Interface.js`` would and running PvPoke's real ``Battle.js`` on the
result.

Nothing here is Cramorant- or showcase-specific except
``AUTO_FIRED_PREFIXES`` (see its comment).

Typical use -- verify THROUGH THE URL, not through the spec
------------------------------------------------------------
    from pvpoke_sandbox_lib import (PokeSpec, timeline_to_actions,
                                    sandbox_url, verify_url)

    r = simulate(p0, p1, charged_policy_0=..., log=True)   # log=True REQUIRED
    acts, auto = timeline_to_actions(r, p0, p1)
    url = sandbox_url(cp, spec0, spec1, (s0, s1), acts)

    got = verify_url(url)                    # <- the pre-publish gate
    assert got['score'][0] == r.pvpoke_score(0)
    assert got['hp'] == r.hp_remaining and got['shields'] == r.shields_remaining

:func:`verify_url` takes the URL **string** and re-derives everything
from it -- routing, the dropdown-index decode, the pinned spread, the
action script.  That is deliberate: the move segment is the only
nontrivial encoding in the link, and a spec-based check (see
:func:`run_pvpoke`) cannot exercise it at all.  Use ``run_pvpoke`` only
for a spec-level baseline (e.g. "what does PvPoke's AI do here"), never
as the publication gate.

SANDBOX SEMANTICS (Battle.js @ pvpoke 78c64048a)
------------------------------------------------
In sandbox mode PvPoke runs **no AI for either Pokemon**
(``Battle.getTurnAction``: the ``ActionLogic.decideAction`` call is
skipped entirely when ``sandbox``).  Each turn, a Pokemon whose cooldown
is 0 either matches a listed action for that turn or throws a fast move.
Consequences:

* You must encode **every** charged move by **both** sides, not just the
  turns where you deviate from PvPoke's plan.  (An empty action list
  makes both sides fast-move for the whole fight -- it is NOT the AI
  baseline.)
* Shielding is not decided by the AI either: the ``shielded`` digit on
  the *attacker's* action says whether the DEFENDER shielded it.
* Auto-fired moves are NOT actions.  Cramorant's Gulp Missile is injected
  by Battle.js itself, so drop it from the action list --
  :func:`timeline_to_actions` does that for you and returns it separately.
* Guaranteed buffs (``buffApplyChance == 1``, e.g. Skull Bash, Gulp
  Missile) still apply in sandbox -- the apply test short-circuits on
  ``move.buffApplyChance == 1``.  The ``buffs`` digit only matters for
  moves with a *partial* apply chance, where it is the ONLY thing that
  makes the buff land (``buffChanceModifier = -1`` and the deterministic
  buff meter is disabled in sandbox, Battle.js:1462).  Our timeline does
  not log buff procs, so :func:`timeline_to_actions` REFUSES a moveset
  containing a partial-chance charged move rather than emit a link that
  may silently diverge.
* ``wait`` (type 2) suppresses that Pokemon's fast move for one turn.
  **Its turn number is the turn the fast move would be INITIATED, not the
  turn it would land** -- unlike charged actions, whose turn is the
  resolution turn.  A wait on a turn where the Pokemon is mid-cooldown is
  a no-op.  Banking energy needs no waits (you bank by throwing fast
  moves); waits are only for genuinely idling.

URL GRAMMAR
-----------
Both link forms are positional paths, produced by PvPoke's
``Interface.generateSingleBattleLinkString`` and routed by
``src/.htaccess`` rules 42-48::

    /battle/[sandbox/]{cp}/{p1}/{p2}/{shields}/{m1}/{m2}[/{hp}/{energy}]/{actions}/

``{cp}``        ``1500`` | ``2500`` | ``10000``.  A ``{cp}-{levelCap}``
                form (e.g. ``1500-40``) works on **plain battle links
                only**: the two sandbox rewrite rules use ``(\\d+)`` for
                that segment while the plain rules use ``([\\d-]+)``, so a
                sandbox link with a level cap matches no rule and 404s.
                That is an upstream PvPoke bug (its own sandbox share
                button is equally broken at a non-default cap); this
                module therefore refuses ``level_cap`` on sandbox links
                rather than emitting a dead one.
``{p1} {p2}``   see INITIAL-STATE KNOBS below.
``{shields}``   two digits, p1 then p2, e.g. ``21``.
``{m1} {m2}``   ``fast-charged1-charged2`` as **dropdown option indices**,
                not move ids.  Fast index = position in the move pool.
                Charged index = position in the pool **+1** (option 0 is
                "None"), so a single-charged-move set must still emit a
                trailing ``-0`` or the parser leaves slot 1 holding
                whatever was auto-selected.  Pools = the species'
                gamemaster ``fastMoves`` / ``chargedMoves`` (+ ``RETURN``
                when shadow-eligible **and the entry actually has a
                ``level25CP`` field** that is ``<= cp`` -- in JS
                ``undefined <= 1500`` is false, and seven entries have no
                such field -- + ``FRUSTRATION`` for a ``_shadow`` entry),
                **sorted by moveId**.  See :func:`move_pools`.
                A third charged slot indexes a *different* pool
                (``extraChargedMovePool``) and is unreachable at this
                vintage (``hasThirdChargedMove()`` returns false), so
                ``charged`` is limited to 1 or 2 moves.
``{hp}``        OPTIONAL pair ``p1hp-p2hp`` -- starting HP.
``{energy}``    OPTIONAL pair ``p1e-p2e`` -- **starting energy**.  These
                two segments are emitted together, both or neither, and
                sit between the movesets and the action string.  This is
                the hook for energy-advantage scenarios.  ``setStartHp``
                clamps to max HP and treats 0 as "full", so passing a
                large sentinel for the side you do not want to change is
                fine (``start_hp='full'`` does that for you).
``{actions}``   sandbox only; ``-``-joined ``turn.TAVSBC`` tokens, or the
                literal ``0`` for none.  See :class:`Action`.

INITIAL-STATE KNOBS (the ``{p1}``/``{p2}`` segment)
---------------------------------------------------
``speciesId`` alone means "whatever the *visitor's* Settings -> Default
IV's produces" (shipped default ``gamemaster`` = "Typical IV's", but
``maximize`` and ``scale`` are one click away and change the fight).
**Pin the spread for anything you publish.**  ``Interface.js`` only reads
the numeric block when it has at least 8 elements, so emit all nine::

    {speciesId}-{level}-{atkIV}-{defIV}-{hpIV}-{atkBuff+4}-{defBuff+4}-{baitShields}-{optimizeMoveTiming}

* ``level``   half-levels allowed (``40.5``).
* ``*IV``     0..15.
* ``*Buff+4`` starting stat stages, offset by 4 so the URL has no minus
  signs (4 = neutral, 5 = +1, 3 = -1).  PvPoke clamps to -4..4; a stage
  outside that range would also emit an empty dash element and shift the
  whole block, so this module rejects it.
* ``baitShields``  0 = never bait, 1 = selective (PvPoke default),
  2 = always.  Ignored in sandbox mode (no AI).
* ``optimizeMoveTiming`` 1 = on (default), 0 = off.  Also AI-only.

Independent suffix tokens, matched anywhere in the dash list:

* ``-shadow`` / ``-purified`` -- shadow type.  (Species ids ending in
  ``_shadow`` already carry it.)
* ``-d-{ms}`` -- ``startCooldown`` in ms (PvPoke only emits ``-d-1000``);
  models entering a matchup mid-fast-move.

NOT round-trippable: ``generateURLPokeStr`` emits ``-p`` for a forced
CMP-priority flag but the parser has no ``p`` case.

Note that the parser does NOT enforce the league CP cap on a pinned
spread (PvPoke only ``console.error``s), so this module warns instead.

Coupling to watch
-----------------
:func:`timeline_to_actions` parses ``BattleResult.timeline``, which is a
*human-readable display log* with no stability contract -- a wording
change silently yields zero actions.  Two guards: the parse asserts it
found at least one action whenever the timeline contains ``" uses "``,
and the pre-publish gate is :func:`verify_url`, which would catch a
truncated action list as a score mismatch.  If ``BattleResult`` ever
grows a structured per-event list (actor index, turn, move id, shielded),
switch to it -- that would also make mirror matchups transcribable, which
the string log fundamentally is not (see :func:`timeline_to_actions`).

Gamemaster provenance
---------------------
Move indices and the verifier must be computed against the SAME
gamemaster blob.  This module therefore reads
``{pvpoke_root}/src/data/gamemaster.json`` for both, rather than
accepting a caller-supplied dict (``gopvpsim.data.load_gamemaster`` is a
TTL-cached network fetch and can skew).  Pass ``gamemaster=`` explicitly
only if you have a reason, and it will be checked against the
``pvpoke_root`` blob.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

__all__ = [
    'PokeSpec', 'Action', 'timeline_to_actions', 'action_str',
    'move_pools', 'move_index_str', 'poke_url_segment',
    'sandbox_url', 'plain_battle_url', 'verify_url', 'run_pvpoke',
    'load_gamemaster', 'DEFAULT_PVPOKE_ROOT',
]

DEFAULT_PVPOKE_ROOT = Path(__file__).resolve().parents[1].parent / 'pvpoke'
_HERE = Path(__file__).resolve().parent
SPEC_DRIVER = _HERE / 'pvpoke_sandbox_driver.js'  # spec -> Battle.js
URL_DRIVER = _HERE / 'pvpoke_url_run.js'      # URL string -> Battle.js
HOST = 'https://pvpoke.com'

SHADOW_TYPES = ('normal', 'shadow', 'purified')


@lru_cache(maxsize=4)
def load_gamemaster(pvpoke_root=None):
    """The gamemaster blob the verifier will also use (see module docs)."""
    root = Path(pvpoke_root or DEFAULT_PVPOKE_ROOT)
    return json.loads((root / 'src' / 'data' / 'gamemaster.json').read_text())


def _resolve_gamemaster(gamemaster, pvpoke_root):
    canonical = load_gamemaster(str(pvpoke_root or DEFAULT_PVPOKE_ROOT))
    if gamemaster is None:
        return canonical
    if (gamemaster.get('pokemon') != canonical.get('pokemon')
            or gamemaster.get('moves') != canonical.get('moves')):
        raise ValueError(
            'supplied gamemaster disagrees with '
            f'{pvpoke_root or DEFAULT_PVPOKE_ROOT}/src/data/gamemaster.json; '
            'indices computed against one blob cannot be verified against '
            'the other')
    return canonical


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------

@dataclass
class PokeSpec:
    """One side of a battle, in PvPoke's vocabulary.

    ``species_id`` is PvPoke's speciesId (``'cramorant'``,
    ``'lapras_shadow'``); ``fast``/``charged`` are gamemaster moveIds.
    Leaving ``level``/``ivs`` as ``None`` means "whatever the visitor's
    Default IV's setting produces" -- fine for exploration, **not** for
    anything you publish (see INITIAL-STATE KNOBS).

    ``start_hp='full'`` emits a sentinel that PvPoke clamps to max HP,
    which is how you leave one side alone while giving the other an HP or
    energy lead (the URL segment pair is all-or-nothing).
    """
    species_id: str
    fast: str
    charged: list[str]
    ivs: "tuple[int, int, int] | None" = None      # (atk, def, hp)
    level: "float | None" = None
    shadow_type: str = 'normal'                    # normal | shadow | purified
    start_buffs: "tuple[int, int]" = (0, 0)        # (atk, def) stages, -4..4
    bait_shields: int = 1           # 0 none / 1 selective / 2 always
    optimize_move_timing: bool = True
    start_hp: "int | str | None" = None            # int, or 'full'
    start_energy: "int | None" = None
    start_cooldown: "int | None" = None            # ms, e.g. 1000

    def __post_init__(self):
        if len(self.charged) not in (1, 2):
            raise ValueError(
                f'{self.species_id}: charged must hold 1 or 2 moves, got '
                f'{self.charged!r}. A third slot indexes extraChargedMovePool, '
                'which Pokemon.hasThirdChargedMove() disables at this vintage, '
                'so it silently decodes back to two moves.')
        if self.shadow_type not in SHADOW_TYPES:
            raise ValueError(f'shadow_type must be one of {SHADOW_TYPES}')
        for i, stage in enumerate(self.start_buffs):
            if not (-4 <= int(stage) <= 4):
                raise ValueError(
                    f'{self.species_id}: start_buffs[{i}]={stage} is outside '
                    "PvPoke's -4..4 clamp (PokeSelect.js:1407); the URL would "
                    'be silently dropped or split wrong')
        if self.bait_shields not in (0, 1, 2):
            raise ValueError('bait_shields must be 0, 1 or 2')
        if self.start_energy is not None and not (0 <= self.start_energy <= 100):
            raise ValueError('start_energy must be 0..100')
        if (self.ivs is not None) != (self.level is not None):
            raise ValueError('pin ivs and level together, or neither: the '
                             'parser reads the whole numeric block or none of it')
        if self.ivs is not None and not all(0 <= v <= 15 for v in self.ivs):
            raise ValueError('IVs must be 0..15')

    def pinned(self) -> bool:
        """True when the numeric level/IV block has to be emitted."""
        return (self.ivs is not None
                or tuple(self.start_buffs) != (0, 0)
                or self.bait_shields != 1
                or not self.optimize_move_timing)

    def hp_segment_value(self, max_hp=None):
        if self.start_hp == 'full':
            return 9999          # setStartHp clamps to stats.hp
        return self.start_hp


@dataclass
class Action:
    """One forced sandbox action.

    Serialises to ``turn.TAVSBC`` where the six digits are

    ==  ==================================================================
    T   action type: 1 = charged, 2 = wait
    A   actor: the acting Pokemon's PLAYER index -- 0 = p1, 1 = p2
        (``Battle.js:774`` matches ``a.actor == poke.index``)
    V   value: index into that Pokemon's *selected* charged moves (0/1)
    S   shielded: 1 if the DEFENDER shielded this charged move
    B   buffs: 1 to force a partial-chance buff to land (guaranteed
        buffs apply regardless)
    C   charge multiplier index into [1, .95, .75, .5, .25]; 0 = full
    ==  ==================================================================

    For ``wait``, ``turn`` is the INITIATION turn of the suppressed fast
    move, not a resolution turn (see the module docstring).

    There is deliberately no ``fast`` type: ``TimelineAction.typeToInt``
    maps fast and charged to the same digit ``1``, and the parser rebuilds
    every ``1`` as a charged move, so a "fast" action would silently
    become a charged one.
    """
    turn: int
    actor: int
    value: int = 0
    shielded: bool = False
    buffs: bool = False
    charge: int = 0
    type: str = 'charged'

    def token(self) -> str:
        if self.type not in ('charged', 'wait'):
            raise ValueError("Action.type must be 'charged' or 'wait'")
        if self.actor not in (0, 1):
            raise ValueError('Action.actor must be the player index 0 or 1')
        t = 1 if self.type == 'charged' else 2
        return (f'{self.turn}.{t}{self.actor}{self.value}'
                f'{int(self.shielded)}{int(self.buffs)}{self.charge}')


def action_str(actions) -> str:
    """``-``-joined action tokens, or ``'0'`` when there are none."""
    if isinstance(actions, str):
        return actions
    return '-'.join(a.token() for a in actions) if actions else '0'


# ---------------------------------------------------------------------------
# Timeline -> actions
# ---------------------------------------------------------------------------

# gopvpsim BattleResult.timeline charged-move lines, e.g.
#   "T 15: Cramorant uses Dive → 22 dmg"
#   "T 19: Jellicent uses Surf → SHIELDED (1 dmg)"
_CHARGED_RE = re.compile(r'^T\s*(\d+): (.+?) uses (.+?) → (SHIELDED|\d+) ')

#: Charged moves Battle.js injects itself and that must NOT be encoded as
#: actions.  The Gulp Missile splice at Battle.js:1658 / :1673 is the only
#: ``turnActions.splice`` site at pvpoke 78c64048a; add here if that changes.
AUTO_FIRED_PREFIXES = ('Gulp Missile',)


_FORM_SUFFIX_RE = re.compile(r'\s*\([^()]*\)\s*$')


def _base_name(species):
    """Drop a trailing form parenthetical: 'Cramorant (Gulping)' -> 'Cramorant'.

    ``BattlePokemon.species`` is rewritten in place on a form change, so the
    object's name after a sim need not equal the name in earlier log lines.
    """
    return _FORM_SUFFIX_RE.sub('', species)


def _charged_names(bp):
    return [m.get('name', m['moveId']) for m in bp.charged_moves]


def _partial_buff_moves(bp):
    out = []
    for m in bp.charged_moves:
        if not m.get('buffs'):
            continue
        chance = float(m.get('buffApplyChance', 1) or 1)
        if 0 < chance < 1:
            out.append(m['moveId'])
    return out


def _attribute(who, n0, n1, turn):
    """Player index for a logged species name -- exact match first, then
    form-stripped match. Raises rather than guessing."""
    if who == n0 and who != n1:
        return 0
    if who == n1 and who != n0:
        return 1
    b, b0, b1 = _base_name(who), _base_name(n0), _base_name(n1)
    if b == b0 and b != b1:
        return 0
    if b == b1 and b != b0:
        return 1
    raise ValueError(
        f'turn {turn}: cannot tell which player {who!r} is ({n0!r} vs {n1!r}). '
        'Pass actors=[...] with the true player index per charged line.')


def timeline_to_actions(result, p0, p1, *, actors=None,
                        partial_buffs='refuse'):
    """Translate a ``BattleResult`` timeline into sandbox actions.

    ``result`` must come from ``simulate(..., log=True)``.  ``p0``/``p1``
    are the two ``BattlePokemon`` objects that were simulated -- passing
    the objects (rather than name prefixes and move-name lists) is what
    keeps the emitted ``value`` digit tied to the same slot order the
    ``PokeSpec`` used.

    Returns ``(actions, auto_fired)``; ``auto_fired`` is the list of
    ``(turn, move_name)`` pairs skipped because Battle.js fires them
    itself.

    Actor attribution.  The action's actor digit is the acting Pokemon's
    **player index**.  ``BattleResult.timeline`` is a display log that
    carries only species names, so this function derives the index from
    the name and then *proves* the derivation is sound:

    * it matches names exactly (falling back to a form-stripped compare,
      because ``BattlePokemon.species`` is rewritten in place on a form
      change) and refuses when a line could belong to either side -- in
      particular it refuses a mirror outright, where the old
      ``startswith`` heuristic silently tagged every action to p0;
    * it refuses on any duplicate ``(turn, actor)`` pair, which is what
      such a misattribution produces downstream.

    ``partial_buffs='assume_none'`` opts out of the refusal above for a
    moveset with a ``0 < buffApplyChance < 1`` charged move, on the
    understanding that the caller then proves equivalence with
    :func:`verify_url` -- comparing ``finalStatBuffs`` as well as
    score/HP/shields, so a proc that fired in one engine and not the
    other is observable, not merely improbable.

    Pass ``actors=[...]`` (one player index per charged line, in timeline
    order, excluding auto-fired moves) to supply the true indices from a
    caller that has them; that is the supported route for mirrors until
    ``BattleResult`` exposes a structured event list.
    """
    if not result.timeline:
        raise ValueError('empty timeline: re-run simulate() with log=True')

    n0, n1 = p0.species, p1.species
    slots = (_charged_names(p0), _charged_names(p1))

    if partial_buffs not in ('refuse', 'assume_none'):
        raise ValueError("partial_buffs must be 'refuse' or 'assume_none'")
    for bp in (p0, p1):
        bad = _partial_buff_moves(bp)
        if bad and partial_buffs == 'refuse':
            raise ValueError(
                f'{bp.species} carries partial-chance buff move(s) {bad}. '
                'In sandbox the buff lands ONLY if the action\'s buffs digit '
                'is 1, and our timeline never logs a buff proc, so an emitted '
                'link could silently diverge from this sim. Either set the '
                'buffs digit by hand, or pass partial_buffs="assume_none" AND '
                'prove it with verify_url: compare BOTH the score/HP/shields '
                'and the final stat stages (verify_url returns '
                '"finalStatBuffs"), which is what makes a missed or spurious '
                'proc observable rather than merely unlikely.')

    if actors is None and _base_name(n0) == _base_name(n1):
        raise ValueError(
            f'cannot attribute actions from the display log: both sides are '
            f'{_base_name(n0)!r} (a mirror), so every line names the same '
            'species. Pass actors=[...] with the true player index per charged '
            'line, in timeline order.')

    parsed, auto, saw_uses = [], [], False
    for line in result.timeline:
        if ' uses ' in line:
            saw_uses = True
        m = _CHARGED_RE.match(line)
        if not m:
            continue
        turn, who, move, tail = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        if move.startswith(AUTO_FIRED_PREFIXES):
            auto.append((turn, move))
            continue
        parsed.append((turn, who, move, tail == 'SHIELDED'))

    if saw_uses and not parsed and not auto:
        raise ValueError(
            'the timeline contains " uses " lines but none matched the charged-'
            'move pattern -- BattleResult.timeline\'s wording has probably '
            'changed and _CHARGED_RE needs updating (see module docstring, '
            '"Coupling to watch")')

    if actors is not None and len(actors) != len(parsed):
        raise ValueError(f'actors has {len(actors)} entries but the timeline '
                         f'has {len(parsed)} encodable charged moves')

    actions, seen = [], set()
    for i, (turn, who, move, shielded) in enumerate(parsed):
        if actors is not None:
            actor = int(actors[i])
            if actor not in (0, 1):
                raise ValueError('actors entries must be 0 or 1')
        else:
            actor = _attribute(who, n0, n1, turn)
        if move not in slots[actor]:
            raise ValueError(
                f'turn {turn}: {move!r} is not a selected charged move of '
                f'player {actor} ({slots[actor]}); it cannot be encoded')
        if (turn, actor) in seen:
            raise ValueError(
                f'two actions for player {actor} on turn {turn}: PvPoke keeps '
                'only the last match for a (turn, actor) pair, so this line '
                'cannot be replayed. Usually a sign of misattribution.')
        seen.add((turn, actor))
        actions.append(Action(turn=turn, actor=actor,
                              value=slots[actor].index(move), shielded=shielded))
    return actions, auto


# ---------------------------------------------------------------------------
# Move-select indices
# ---------------------------------------------------------------------------

def move_pools(species_id, cp, gamemaster=None, *, pvpoke_root=None):
    """Return ``(fast_pool, charged_pool)`` as moveId lists in dropdown order.

    Mirrors ``Pokemon.js`` pool construction + the ``moveId`` sort.  The
    charged dropdown puts "None" at option 0, so a charged move's URL
    index is ``charged_pool.index(id) + 1`` (see :func:`move_index_str`).

    ``RETURN`` is added only when the entry has a ``level25CP`` field that
    is ``<= cp``: ``Pokemon.js:230`` tests ``data.level25CP <= b.getCP()``
    and JS evaluates ``undefined <= 1500`` as false, so the seven
    shadow-eligible entries with no such field (krabby, kingler,
    kadabra_shadow, sharpedo_shadow, slowbro_mega, aerodactyl_mega,
    steelix_mega) must NOT get one -- a phantom RETURN shifts the index of
    every charged move sorting after it.

    ``extraChargedMoves`` (Cramorant's Gulp Missiles, mega extras) are
    deliberately excluded: they live in a separate dropdown that
    ``hasThirdChargedMove()`` disables at this vintage, and they do not
    shift the main pool's indices.
    """
    gm = _resolve_gamemaster(gamemaster, pvpoke_root)
    entry = next((p for p in gm['pokemon'] if p['speciesId'] == species_id), None)
    if entry is None:
        raise ValueError(f'unknown speciesId {species_id!r} in the gamemaster')
    known = {m['moveId'] for m in gm['moves']}
    fast = sorted(m for m in entry.get('fastMoves', []) if m in known)
    charged = list(entry.get('chargedMoves', []))
    tags = entry.get('tags') or []
    if ('shadoweligible' in tags and 'level25CP' in entry
            and entry['level25CP'] <= cp):
        charged.append('RETURN')
    if 'shadow' in tags:
        charged.append('FRUSTRATION')
    charged = sorted(m for m in charged if m in known)
    return fast or ['SPLASH'], charged or ['STRUGGLE']


def move_index_str(spec: PokeSpec, cp, gamemaster=None, *, pvpoke_root=None):
    """The ``{m1}``/``{m2}`` URL segment for ``spec``.

    Always emits two charged slots, padding a single-move set with ``0``
    ("None") exactly as PvPoke's own generator does -- the parser loops
    over whatever elements are present, so a missing slot leaves the
    auto-selected move in place.
    """
    fast, charged = move_pools(spec.species_id, cp, gamemaster,
                              pvpoke_root=pvpoke_root)
    if spec.fast not in fast:
        raise ValueError(f'{spec.fast} not in {spec.species_id} fast pool {fast}')
    parts = [str(fast.index(spec.fast))]
    for c in spec.charged:
        if c not in charged:
            raise ValueError(f'{c} not in {spec.species_id} charged pool {charged}')
        parts.append(str(charged.index(c) + 1))
    while len(parts) < 3:
        parts.append('0')
    return '-'.join(parts)


# ---------------------------------------------------------------------------
# URL assembly
# ---------------------------------------------------------------------------

def poke_url_segment(spec: PokeSpec) -> str:
    """The ``{p1}``/``{p2}`` segment, including any pinned initial state."""
    seg = spec.species_id
    if spec.pinned():
        if spec.ivs is None:
            raise ValueError(
                f'{spec.species_id}: pinning buffs/bait/timing also requires '
                'ivs and level -- the parser reads the numeric block as a unit')
        a, d, h = spec.ivs
        # PvPoke emits a JS number: 26, not 26.0 (half-levels keep the .5).
        lvl = spec.level
        lvl = int(lvl) if float(lvl) == int(lvl) else lvl
        seg += '-' + '-'.join(str(x) for x in (
            lvl, a, d, h,
            int(spec.start_buffs[0]) + 4, int(spec.start_buffs[1]) + 4,
            spec.bait_shields, int(spec.optimize_move_timing)))
    if spec.shadow_type != 'normal':
        seg += '-' + spec.shadow_type
    if spec.start_cooldown:
        seg += f'-d-{spec.start_cooldown}'
    return seg


def _warn_cp(spec, cp, pvpoke_root):
    """PvPoke does not enforce the cap on a pinned spread; we at least say so."""
    if spec.ivs is None or cp >= 10000:
        return
    try:
        import sys
        sys.path.insert(0, str(Path.home() / 'coding' / 'gopvpsim' / 'src'))
        from gopvpsim.pokemon import get_species, cp as cp_of
    except Exception:
        return
    try:
        base = get_species(spec.species_id.replace('_', ' ').title())
    except Exception:
        return
    got = cp_of(base['atk'], base['def'], base['hp'], *spec.ivs, spec.level)
    if got > cp:
        warnings.warn(f'{spec.species_id} at level {spec.level} IVs {spec.ivs} '
                      f'is CP {got}, over the {cp} cap; pvpoke only logs a '
                      'console error and will run it anyway')


def _shields_segment(shields):
    a, b = shields
    for v in (a, b):
        if v not in (0, 1, 2):
            raise ValueError(f'shields must each be 0, 1 or 2 (got {shields!r}); '
                             'the segment is two single digits')
    return f'{a}{b}'


def _battle_path(cp, p1, p2, shields, gamemaster, sandbox, actions,
                 level_cap, pvpoke_root):
    if sandbox and level_cap:
        raise ValueError(
            'a sandbox link cannot carry a level cap: the two '
            'battle/sandbox/ rewrite rules match the CP segment with '
            r'(\d+), so "%s-%s" matches no rule and the URL 404s. '
            'Upstream PvPoke bug -- use the default cap, or a plain '
            'battle link.' % (cp, level_cap))
    cp_seg = f'{cp}-{level_cap}' if level_cap else str(cp)
    path = ['battle']
    if sandbox:
        path.append('sandbox')
    for spec in (p1, p2):
        _warn_cp(spec, cp, pvpoke_root)
    path += [cp_seg, poke_url_segment(p1), poke_url_segment(p2),
             _shields_segment(shields),
             move_index_str(p1, cp, gamemaster, pvpoke_root=pvpoke_root),
             move_index_str(p2, cp, gamemaster, pvpoke_root=pvpoke_root)]
    # Optional starting HP / energy pair -- both segments or neither.
    if any(x is not None for x in (p1.start_hp, p2.start_hp,
                                   p1.start_energy, p2.start_energy)):
        if p1.start_hp is None or p2.start_hp is None:
            raise ValueError(
                'the HP/energy segments are all-or-nothing: set start_hp on '
                "BOTH specs (use start_hp='full' for the side you are not "
                'changing)')
        path.append(f'{p1.hp_segment_value()}-{p2.hp_segment_value()}')
        path.append(f'{p1.start_energy or 0}-{p2.start_energy or 0}')
    if sandbox:
        path.append(action_str(actions))
    return '/'.join(path) + '/'


def plain_battle_url(cp, p1: PokeSpec, p2: PokeSpec, shields, *,
                     gamemaster=None, level_cap=None, host=HOST,
                     pvpoke_root=None):
    """A normal (AI-driven) pvpoke.com battle link for this matchup."""
    return f'{host}/' + _battle_path(cp, p1, p2, shields, gamemaster,
                                     False, None, level_cap, pvpoke_root)


def sandbox_url(cp, p1: PokeSpec, p2: PokeSpec, shields, actions, *,
                gamemaster=None, level_cap=None, host=HOST, pvpoke_root=None):
    """A sandbox link that replays ``actions`` instead of PvPoke's AI."""
    return f'{host}/' + _battle_path(cp, p1, p2, shields, gamemaster,
                                     True, actions, level_cap, pvpoke_root)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_url(url, *, pvpoke_root=None, default_ivs='gamemaster',
               driver=URL_DRIVER):
    """**The pre-publish gate.**  Run a URL string through PvPoke's engine.

    Decodes ``url`` independently of everything above -- ``src/.htaccess``
    routing, then ``Interface.js loadGetData()``, with the dropdown option
    lists rebuilt as ``PokeSelect.js`` builds them -- and runs PvPoke's
    real ``Battle.js``.  Because it starts from the string, it exercises
    the dropdown-index encoding, the pinned-spread block and the action
    script, none of which :func:`run_pvpoke` can reach.

    ``default_ivs`` emulates the visitor's *Settings -> Default IV's*
    (``gamemaster`` = shipped default, ``maximize``, ``scale``).  Run a
    published link under all three, or pin the spread so it cannot matter.

    Returns the driver's JSON dict, including ``resolved`` -- the moveset
    PvPoke actually built from the indices, which is what makes a
    mis-indexed link obvious.  Raises on a URL that matches no rewrite
    rule (i.e. would 404).
    """
    out = subprocess.run(
        ['node', str(driver), url, '--default-ivs', default_ivs],
        capture_output=True, text=True,
        env={**os.environ,
             'PVPOKE_ROOT': str(pvpoke_root or DEFAULT_PVPOKE_ROOT)})
    if out.returncode:
        raise RuntimeError(f'url driver failed:\n{out.stderr}')
    res = json.loads(out.stdout)
    if res.get('error'):
        raise ValueError(f'{res["error"]}: {url}')
    return res


def run_pvpoke(cp, p1: PokeSpec, p2: PokeSpec, shields, *, actions=None,
               level_cap=None, pvpoke_root=None, driver=SPEC_DRIVER):
    """Run this matchup through PvPoke's ``Battle.js`` **from the spec**.

    Useful for a baseline ("what does PvPoke's AI do here?", by passing
    ``actions=None``) and for isolating an engine question from the URL
    codec.  It is NOT the publication gate -- it takes moveIds and never
    parses a URL, so it cannot see a wrong dropdown index.  Use
    :func:`verify_url`.
    """
    cmd = ['node', str(driver), '--pvpoke-root',
           str(pvpoke_root or DEFAULT_PVPOKE_ROOT), '--cp', str(cp)]
    if level_cap:
        cmd += ['--level-cap', str(level_cap)]
    for name, spec, sh in (('p1', p1, shields[0]), ('p2', p2, shields[1])):
        cmd += [f'--{name}', spec.species_id, f'--{name}-fast', spec.fast,
                f'--{name}-charged', ','.join(spec.charged),
                f'--{name}-shields', str(sh),
                f'--{name}-bait', str(spec.bait_shields)]
        if spec.ivs is not None:
            cmd += [f'--{name}-ivs', '/'.join(str(x) for x in spec.ivs)]
        if spec.level is not None:
            cmd += [f'--{name}-level', str(spec.level)]
        if spec.start_hp is not None:
            cmd += [f'--{name}-hp', str(spec.hp_segment_value())]
        if spec.start_energy is not None:
            cmd += [f'--{name}-energy', str(spec.start_energy)]
        if spec.start_cooldown is not None:
            cmd += [f'--{name}-cooldown', str(spec.start_cooldown)]
        if tuple(spec.start_buffs) != (0, 0):
            cmd += [f'--{name}-buffs', ','.join(str(x) for x in spec.start_buffs)]
        if spec.shadow_type != 'normal':
            cmd += [f'--{name}-shadow-type', spec.shadow_type]
    if actions is not None:
        cmd += ['--actions', action_str(actions)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(f'pvpoke driver failed:\n{out.stderr}')
    return json.loads(out.stdout)
