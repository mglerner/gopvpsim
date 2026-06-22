# gopvpsim - Pokemon GO PvP battle simulator

A pure-Python Pokemon GO PvP battle simulator focused on breakpoint and
bulkpoint analysis. It powers a set of CLI tools and a static website of
interactive IV / moveset "deep dives" that show which IV spreads cross which
damage thresholds against the meta.

## Built on PvPoke

This project is built on [PvPoke](https://pvpoke.com)
([source](https://github.com/pvpoke/pvpoke)), created by Empoleon_Dynamite and
released under the MIT license. The battle simulator in `src/gopvpsim/battle.py`
is a Python port of PvPoke's open-source battle logic, and all game data (the
gamemaster, move stats, the type chart, and the meta rankings) is fetched from
PvPoke. Scores are cross-checked against PvPoke's own simulate-mode engine.
**This project would not exist without PvPoke.** Please support and credit it.

Divergences from PvPoke are tracked deliberately in `DEVELOPER_NOTES.md` (some
are PvPoke bugs we have reported; others are intentional choices documented
there and in `CLAUDE.md`).

## Built with Claude

This codebase makes heavy use of [Claude](https://www.anthropic.com/claude)
(Anthropic's Claude Code). A large share of the code, tests, documentation, and
analysis tooling was written collaboratively with Claude. Commits authored with
Claude carry a `Co-Authored-By` trailer.

## Layout

- `src/gopvpsim/` - the core library (pure Python): `data.py` (game-data fetch
  + cache), `pokemon.py` (stats / CP / IVs), `moves.py` (damage + type chart),
  `battle.py` (the simulation loop), `breakpoints.py` (threshold analysis).
- `scripts/` - CLI tools and the deep-dive / article / website renderers
  (these may use numba etc. for speed).
- `thresholds/`, `articles/`, `guides/` - data + narrative sources that render
  into the public site.
- `tests/` - battle-correctness tests verified against PvPoke ground truth.

## Setup

Requires Python 3.13+. The environment is `uv`-managed:

```
uv venv
uv pip install -e ".[dev,perf]"
direnv allow
```

See `CLAUDE.md` ("Running Python") for how `python` resolves in different
shells, and the docstrings / `docs/` for the analysis vocabulary
(`docs/concepts.md`) and file formats.

## License

This project is released under the MIT license (see `LICENSE`), Copyright (c)
2026 Michael G. Lerner. PvPoke, on which this project is built, is independently
MIT-licensed and Copyright its own authors (Empoleon_Dynamite); see
[its repository](https://github.com/pvpoke/pvpoke) for details.
