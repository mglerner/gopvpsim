"""One knob block for every iv_sweep call site (D9).

DRY review 2026-08-05 entry 12 / June review D9: the same eight-line
pass-through was hand-typed at five ``iv_sweep`` call sites in
``deep_dive.main`` (Phase 2, the extra composite modes, the reference sweep,
the base-form census, the best-buddy pass). Adding a knob meant editing five
argument lists, and a miss is silent -- commit 06bedca is the worked example.

The load-bearing property is that ``SweepConfig`` stays a faithful shadow of
``iv_sweep``'s signature: the tests below introspect ``iv_sweep`` rather than
re-typing its parameter names, so renaming/retyping a sweep kwarg fails HERE
instead of at dive time.
"""
import argparse
import inspect

from tests.conftest import load_deep_dive

deep_dive = load_deep_dive()

SweepConfig = deep_dive.SweepConfig

# The knobs SweepConfig owns. Anything a call site varies per call
# (opp_iv_mode, capture_energy, capture_metrics, focal_max_level,
# opp_max_level) stays OUT of it on purpose.
FIELDS = ('iv_floor', 'log_path', 'verbose', 'threshold_registry',
          'reserve_cpus', 'signature_dedup', 'use_sweep_cache', 'mechanics')


def _args(**overrides):
    ns = argparse.Namespace(
        iv_floor=(1, 2, 3), verbose=True, reserve_cpus=4,
        no_signature_dedup=False, no_sweep_cache=False, mechanics='legacy',
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def test_every_field_is_a_real_iv_sweep_kwarg():
    params = inspect.signature(deep_dive.iv_sweep).parameters
    for name in FIELDS:
        assert name in params, f'{name} is not an iv_sweep parameter'


def test_defaults_mirror_iv_sweep_defaults():
    """An omitted field must pass through as though it were never passed."""
    params = inspect.signature(deep_dive.iv_sweep).parameters
    defaults = SweepConfig().as_kwargs()
    for name in FIELDS:
        assert defaults[name] == params[name].default, name


def test_as_kwargs_is_exactly_the_field_set():
    assert set(SweepConfig().as_kwargs()) == set(FIELDS)


def test_from_args_inverts_the_negated_flags():
    on = SweepConfig.from_args(_args(no_signature_dedup=False,
                                     no_sweep_cache=False))
    assert on.signature_dedup is True and on.use_sweep_cache is True
    off = SweepConfig.from_args(_args(no_signature_dedup=True,
                                      no_sweep_cache=True))
    assert off.signature_dedup is False and off.use_sweep_cache is False


def test_from_args_carries_the_rest_verbatim():
    reg = object()
    cfg = SweepConfig.from_args(_args(mechanics='new'),
                                log_path='/tmp/run.log',
                                threshold_registry=reg)
    kw = cfg.as_kwargs()
    assert kw['iv_floor'] == (1, 2, 3)
    assert kw['log_path'] == '/tmp/run.log'
    assert kw['verbose'] is True
    assert kw['reserve_cpus'] == 4
    assert kw['mechanics'] == 'new'
    # Identity, not a copy: the registry is a live object the sweep resolves
    # variant IVs through (dataclasses.asdict would have deep-copied it).
    assert kw['threshold_registry'] is reg


def test_as_kwargs_call_is_accepted_by_iv_sweep():
    """Bind the splat against the real signature -- catches an arity/name
    drift without running a sweep."""
    kw = SweepConfig.from_args(_args()).as_kwargs()
    inspect.signature(deep_dive.iv_sweep).bind(
        'Azumarill', 'BUBBLE', ['ICE_BEAM'], 'great', False,
        ['Medicham'], [('COUNTER', ['PSYCHIC'])], [(1, 1)],
        opp_iv_mode='pvpoke', capture_energy=True, **kw)
