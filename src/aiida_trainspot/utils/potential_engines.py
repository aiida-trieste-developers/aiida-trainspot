"""Registry of potential "engines" usable by MD exploration.

The data lives in `potential_engines.json` (one block per engine: which
`training_engine`s can produce it, which LAMMPS pair_style it maps to, and how to
build its `pair_coeff`/`potential_style_options`). Adding a new engine should only
require adding a block there -- this module is just a handful of generic functions
that read it, plus the tiny bit of Python needed to turn a structure into pair_coeff
tokens.

A `pair_coeff` field that's missing/null means no custom pair_coeff is needed at all:
aiida-lammps' own default (`pair_coeff * * <file> <species>`, driven by
`read_from_file` in its own `lammps_potentials.json`) is used instead.
"""

import json

from pathlib import Path

from aiida_lammps.data.potential import LammpsPotentialData
from ase.data import atomic_numbers

with open(Path(__file__).parent / "potential_engines.json", encoding="utf8") as _handle:
    _data = json.load(_handle)

# Keys starting with "_" (e.g. "_doc") are documentation, not engines
ENGINES = {tag: engine for tag, engine in _data.items() if not tag.startswith("_")}

# Extra pair_coeff options appended for the DFT-D2 dispersion correction used by the
# vdw_d2 protocol, shared by every engine that supports being combined with it.
VDW_D2_PAIR_COEFF_OPTIONS = "momb 20.0 0.75 20.0"

# The handful of ways a structure gets turned into the tokens following "* *
# [base_pair_style]" in a pair_coeff line.
_PAIR_COEFF_TOKENS = {
    "filename_symbols": lambda structure, filename: [filename, *structure.get_symbols_set()],
    "symbols": lambda structure, filename: sorted(structure.get_symbols_set()),
    "atomic_numbers": lambda structure, filename: [
        str(atomic_numbers[symbol]) for symbol in sorted(structure.get_symbols_set())
    ],
}


def match_engine(pair_style: str) -> tuple:
    """Find the (tag, engine) whose tag is contained in `pair_style` (substring match, so
    e.g. "allegro3232" still matches the "allegro" entry). Returns `(None, None)` if
    `pair_style` doesn't match any known engine.
    """
    for tag, engine in ENGINES.items():
        if tag in pair_style:
            return tag, engine
    return None, None


def filename(pair_style: str) -> str:
    """The filename aiida-lammps will write/expect for the given `pair_style`."""
    return LammpsPotentialData.default_potential_info.get(pair_style, {}).get("filename", "potential.dat")


def pair_coeff(engine: dict, structure, hybrid: bool, filename: str):
    """Build the `pair_coeff` string for `structure`, or `None` if this engine doesn't need one."""
    kind = engine.get("pair_coeff")
    if kind is None:
        return None
    tokens = _PAIR_COEFF_TOKENS[kind](structure, filename)
    if hybrid:
        # `pair_coeff` only takes the sub-style's bare name, not its own args (unlike the
        # `pair_style hybrid/overlay` line itself, which needs `base_pair_style` in full --
        # e.g. mace's is "mace no_domain_decomposition", but `pair_coeff * * mace ...`).
        sub_style_name = engine["base_pair_style"].split()[0]
        prefix = f"* * {sub_style_name} "
    else:
        prefix = "* * "
    return prefix + " ".join(tokens)


def style_options(engine: dict, filename: str, hybrid: bool):
    """`potential_style_options` for this engine, or `None` if it doesn't need any."""
    template = engine.get("style_options")
    plain = template.format(filename=filename) if template else None
    if not hybrid:
        return plain
    sub_style = f"{engine['base_pair_style']} {plain}" if plain else engine["base_pair_style"]
    return f"{sub_style} {VDW_D2_PAIR_COEFF_OPTIONS}"


def default_pair_style_for_training_engine(training_engine: str):
    """The `base_pair_style` of the first-registered engine compatible with `training_engine`."""
    for engine in ENGINES.values():
        if training_engine in engine["training_engine"]:
            return engine["base_pair_style"]
    return None


def is_pair_style_compatible(pair_style: str, training_engine: str) -> bool:
    """Whether `pair_style` is a format `training_engine` can produce."""
    _, engine = match_engine(pair_style)
    return engine is not None and training_engine in engine["training_engine"]
