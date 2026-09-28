"""The MIRROR POPULATION: the focal's own species as extra opponent columns.

TODO.md "NEXT BAKE: mirror population as opponent columns" is the decision
record (Michael, 2026-09-22). "The mirrors I will meet" are:

(1) PvPoke's rank-ordered IV list for the focal, top :data:`N_RANK`
    (``gopvpsim.pokemon.iv_rank``: stat product descending, IV sum as the
    tiebreak -- PvPoke's own ordering, so the list is bulk-first by
    construction), for the focal's form and, when the pool carries it, the
    other shadow form too;
(2) the page's OWN builds -- each named build's most-winning member under
    every live Build-criteria preset, plus SP1 (stat-product rank 1 on the
    arm's grid) -- because that is what readers build once the page exists.

Each member is an opponent with EXPLICIT IVs at its best level under the
league cap, with the pool's moveset for that form (the same moveset the
pool's own mirror column uses). The opp-IV modes do not apply -- the IVs are
the point -- so each arm is swept once per BAIT mode and nothing else.

Vocabulary (per document):

- Arm: one moveset of the blob (``state['moveset_data'][arm]``).
- Member: one (form, IV spread) in the population. Deduplicated: a spread
  that is both rank-list #1 and SP1 is ONE member with two source tags.
- Source tag: 'pvpoke_rank' (the rank list), 'build:<role>' (a build's
  most-winning member; role is primary / fork / rank1), 'sp1'.
- SP1: the arm grid's stat-product rank 1 (``deep_dive_builds.build_ctx``'s
  ``sp_rank``), which is the rank list's #1 unless the dive floors its IVs.
- CMP (charge-move priority): decided by the PRE-shadow attack
  (``battle.BattlePokemon.cmp_atk``), so every member carries ``raw_atk``.

Schema (``state['mirror_population']``, version :data:`SCHEMA_VERSION`)::

    {'version': 1, 'n_rank': 20, 'level': 'l50', 'render_mode': 'pvpoke',
     'bait_modes': {'bait': 'pvpoke', 'nobait': 'pvpoke:nobait'},
     'engine_hash': str, 'gamemaster_hash': str,
     'members': [{'name', 'species', 'shadow', 'ivs': (a, d, s), 'level',
                  'cp', 'atk', 'def_', 'hp', 'raw_atk', 'rank',
                  'fast', 'charged'}, ...],
     'arms': [{'members': [member index, ...],        # this arm's columns
               'tags': [[source tag, ...], ...],      # parallel to members
               'builds': {preset: {role: member index}},
               'sp1': member index, 'rank1': member index,
               'scores': {'bait': int16 (n_iv, n_sc, M),
                          'nobait': int16 (n_iv, n_sc, M)}}, ...]}

``scores[b][i, si, j]`` is the focal spread ``i`` (the arm's grid, in the
same order as ``moveset_data[arm]['meta']``) against member
``arms[arm]['members'][j]`` in shield scenario ``si``, from the FOCAL's seat
(row = the focal under pvpoke_dp with that bait mode, column = the opponent
AI, which always baits). There is no antisymmetry: (i vs j) and (j vs i) are
two different fights.

Only the league cap ('l50') is swept. A best-buddy (L51) page keeps the
cohort paragraph (see ``deep_dive_builds.population_facts``).
"""
import time

import numpy as np

from gopvpsim.pokemon import Pokemon, iv_rank

from deep_dive_logging import get_logger

logger = get_logger()

SCHEMA_VERSION = 1
N_RANK = 20
LEVEL = 'l50'
# The builds are computed exactly as the page computes them: the page's
# section reads mode 'pvpoke' (deep_dive_which_build.prepare's default).
RENDER_MODE = 'pvpoke'
# brief.compute_brief quotes the blob's basename in its provenance fields;
# the blob does not exist yet when the population is chosen. Nothing the
# builds read depends on it.
PRE_RENDER_BLOB = 'pre-render-mirror-population'


def form_name(species, shadow):
    return species + (' (Shadow)' if shadow else '')


def pool_forms(state):
    """``[(shadow, pool name or None, (fast, charged))]``, focal form first.

    The focal's form always; the other shadow form only when the pool
    carries it under its plain name. The moveset is the pool entry's (the
    one the pool's own mirror column is simmed with); a focal form missing
    from the pool falls back to PvPoke's default moveset for it.
    """
    species, shadow = state['species'], bool(state['shadow'])
    names = state['opponent_names']
    movesets = state.get('opp_movesets') or []
    out = []
    for sh in (shadow, not shadow):
        nm = form_name(species, sh)
        if nm in names and len(movesets) == len(names):
            fast, charged = movesets[names.index(nm)]
            out.append((sh, nm, (fast, list(charged))))
        elif sh == shadow:
            from gopvpsim.data import get_default_moveset
            try:
                fast, charged = get_default_moveset(
                    species, league=state['league'], shadow=sh,
                    cup=state.get('cup'))
            except (KeyError, ValueError) as e:
                logger.warning(f"  Mirror population: no moveset for "
                               f"{nm} ({e}); skipped")
                return []
            out.append((sh, None, (fast, list(charged))))
    return out


def arm_build_members(state, arm):
    """The page's own build members for one arm, as grid indices.

    ``{'sp1': idx, 'builds': {preset: {role: idx}}}``; ``builds`` is empty
    when the arm's brief fails a guard (the page then has no builds for it
    either). Computed with the page's own call, ``compute_builds`` at the
    section's mode and the league cap.
    """
    import deep_dive_brief as brief
    import deep_dive_builds as builds
    ctx = builds.build_ctx(state, arm, mode=RENDER_MODE, level=LEVEL)
    sp1 = int(np.argmin(ctx['sp_rank']))
    try:
        facts = brief.compute_brief(state, arm, PRE_RENDER_BLOB,
                                    mode=RENDER_MODE, level=LEVEL)
        res = builds.compute_builds(state, arm, mode=RENDER_MODE,
                                    level=LEVEL, facts=facts)
    except brief.GuardError as e:
        logger.warning(f"  Mirror population: moveset {arm + 1} has no "
                       f"builds ({type(e).__name__}: {e}); rank list and "
                       f"SP1 only")
        return {'sp1': sp1, 'builds': {}}
    out = {}
    for key, block in res['presets'].items():
        out[key] = {b['role']: int(b['most_winning_member']['idx'])
                    for b in block['builds']}
    return {'sp1': sp1, 'builds': out}


def _member(species, shadow, ivs, league, name, moveset, rank):
    a, d, s = (int(v) for v in ivs)
    p = Pokemon.at_best_level(species, a, d, s, league=league, shadow=shadow)
    return {'name': name or form_name(species, shadow),
            'species': species, 'shadow': bool(shadow), 'ivs': (a, d, s),
            'level': float(p.level), 'cp': int(p.cp),
            'atk': float(p.atk), 'def_': float(p.def_), 'hp': int(p.hp),
            'raw_atk': float(p.raw_atk), 'rank': rank,
            'fast': moveset[0], 'charged': list(moveset[1])}


def select_population(state, arm_builds, n_rank=N_RANK):
    """The member table and each arm's columns. No simulation.

    ``arm_builds`` is one :func:`arm_build_members` result per arm (None for
    an arm to skip). Returns the schema dict WITHOUT ``scores``.
    """
    species, league = state['species'], state['league']
    forms = pool_forms(state)
    if not forms:
        return None
    focal_shadow = bool(state['shadow'])
    focal_moveset = forms[0][2]
    focal_name = forms[0][1]
    members, index = [], {}
    ranks = {}

    def add(shadow, ivs, name, moveset):
        key = (bool(shadow), tuple(int(v) for v in ivs))
        if key not in index:
            if shadow not in ranks:
                ranks[shadow] = {(e['atk_iv'], e['def_iv'], e['sta_iv']):
                                 e['rank'] for e in
                                 iv_rank(species, league=league,
                                         shadow=shadow)}
            index[key] = len(members)
            members.append(_member(species, shadow, key[1], league, name,
                                   moveset, ranks[shadow].get(key[1])))
        return index[key]

    rank_cols = []
    for sh, nm, ms in forms:
        top = iv_rank(species, league=league, shadow=sh)[:n_rank]
        rank_cols.append([add(sh, (e['atk_iv'], e['def_iv'], e['sta_iv']),
                              nm, ms) for e in top])
    arms = []
    for arm, ab in enumerate(arm_builds):
        if ab is None:
            arms.append(None)
            continue
        meta = np.asarray(state['moveset_data'][arm]['meta'], dtype=float)
        tags = {}

        def tag(mi, t):
            tags.setdefault(mi, [])
            if t not in tags[mi]:
                tags[mi].append(t)
        for col in rank_cols:
            for mi in col:
                tag(mi, 'pvpoke_rank')
        sp1 = add(focal_shadow, meta[ab['sp1'], :3], focal_name,
                  focal_moveset)
        tag(sp1, 'sp1')
        blds = {}
        for key, roles in ab['builds'].items():
            blds[key] = {}
            for role, idx in roles.items():
                mi = add(focal_shadow, meta[idx, :3], focal_name,
                         focal_moveset)
                tag(mi, f'build:{role}')
                blds[key][role] = mi
        cols = sorted(tags)
        arms.append({'members': cols, 'tags': [tags[m] for m in cols],
                     'builds': blds, 'sp1': sp1,
                     'rank1': rank_cols[0][0]})
    pop = {'version': SCHEMA_VERSION, 'n_rank': int(n_rank), 'level': LEVEL,
           'render_mode': RENDER_MODE, 'members': members, 'arms': arms}
    check_guards(pop)
    return pop


class PopulationGuardError(ValueError):
    """The population is missing a member it must carry."""


def check_guards(pop):
    """Every swept arm's columns carry SP1 and the focal form's rank-list #1.

    The two anchors every sentence the page prints is read against: SP1 is
    what a reader builds by default, and the rank list's #1 is PvPoke's
    headline spread. A population missing either is not the population the
    decision record specifies, so this raises rather than degrading.
    """
    for arm, a in enumerate(pop['arms']):
        if a is None:
            continue
        cols = a['members']
        for what in ('sp1', 'rank1'):
            if a.get(what) not in cols:
                raise PopulationGuardError(
                    f"mirror population arm {arm}: {what} is not a column")
        r1 = pop['members'][a['rank1']]
        if r1['rank'] != 1 or 'pvpoke_rank' not in a['tags'][
                cols.index(a['rank1'])]:
            raise PopulationGuardError(
                f"mirror population arm {arm}: rank-list #1 is not tagged")
        if 'sp1' not in a['tags'][cols.index(a['sp1'])]:
            raise PopulationGuardError(
                f"mirror population arm {arm}: SP1 is not tagged")
        for key, roles in a['builds'].items():
            for role, mi in roles.items():
                if mi not in cols:
                    raise PopulationGuardError(
                        f"mirror population arm {arm}: build {key}/{role} "
                        f"is not a column")


def bake(state, movesets, bait_modes, sweep_fn, sweep_kwargs,
         n_rank=N_RANK):
    """Choose the population and sweep every arm against it.

    ``movesets`` is ``[(fast, charged)]`` parallel to ``moveset_data``;
    ``bait_modes`` maps a bait tag ('bait' / 'nobait') to the composite mode
    string ``sweep_fn`` (``iv_sweep``) is called with. Returns the schema
    dict, or None when the focal form has no moveset to sim.
    """
    import sweep_cache
    t0 = time.time()
    arm_builds = [arm_build_members(state, arm)
                  for arm in range(len(state['moveset_data']))]
    pop = select_population(state, arm_builds, n_rank=n_rank)
    if pop is None:
        return None
    t_sel = time.time() - t0
    n_sc = len(state['shield_scenarios'])
    members = pop['members']
    n_cols = 0
    for arm, a in enumerate(pop['arms']):
        if a is None:
            continue
        cols = [members[m] for m in a['members']]
        n_iv = len(state['moveset_data'][arm]['meta'])
        fast, charged = movesets[arm]
        a['scores'] = {}
        for tag, mode in bait_modes.items():
            _res, _n, cs, _meta, _en = sweep_fn(
                state['species'], fast, charged, state['league'],
                state['shadow'],
                [c['name'] for c in cols],
                [(c['fast'], c['charged']) for c in cols],
                state['shield_scenarios'],
                opp_iv_mode=mode,
                opp_ivs=[c['ivs'] for c in cols],
                **sweep_kwargs)
            a['scores'][tag] = np.asarray(cs, dtype=np.int16).reshape(
                n_iv, n_sc, len(cols))
            n_cols += len(cols)
    pop['bait_modes'] = dict(bait_modes)
    pop['engine_hash'] = sweep_cache.engine_hash()
    pop['gamemaster_hash'] = sweep_cache.gamemaster_hash()
    n_arm = sum(1 for a in pop['arms'] if a is not None)
    logger.info(f"  Mirror population: {len(members)} members, "
                f"{n_cols} column-sweeps over {n_arm} moveset(s) in "
                f"{time.time() - t0:.1f}s (selection {t_sel:.1f}s)")
    return pop
