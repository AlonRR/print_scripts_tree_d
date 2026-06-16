"""Shared dev helpers for scratch scripts.

Usage at the top of every scratch file:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from _dev import *
"""

import importlib
import inspect
import logging
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import build123d as bd
from build123d import (
    Box,
    Compound,
    Cone,
    Cylinder,
    Part,
    Pos,
    Rot,
    ShapeList,
    export_stl,
)
from ocp_vscode import (  # type: ignore[import-untyped]
    get_defaults,
    reset_show,
    set_defaults,
    set_port,
    show,
    show_object,
)

import print_scripts_tree_d.shapes as shapes
from print_scripts_tree_d import params
from print_scripts_tree_d.export import save_stl

__all__ = [
    # build123d module + common symbols
    "bd",
    "Box",
    "Compound",
    "Cone",
    "Cylinder",
    "Part",
    "Pos",
    "Rot",
    "ShapeList",
    "export_stl",
    # ocp_vscode
    "get_defaults",
    "reset_show",
    "set_defaults",
    "set_port",
    "show",
    "show_object",
    # project
    "shapes",
    "params",
    "save_stl",
    # helpers + state
    "preview",
    "reload_pkg",
    "models",
    # stdlib commonly used in scratch files
    "Path",
    "logging",
]

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("build123d").setLevel(logging.WARNING)

models = Path(__file__).parent.parent / "models"
models.mkdir(exist_ok=True)

set_port(3939)
reset_show()


def reload_pkg(pkg: str = "print_scripts_tree_d") -> None:
    """Force-reimport every loaded submodule of *pkg*, deepest first.

    Escape hatch when %autoreload silently misses a change (e.g. after a
    reload error) — call this instead of restarting the kernel.
    """
    mods = [
        m for n, m in sys.modules.items() if n == pkg or n.startswith(pkg + ".")
    ]
    for m in sorted(mods, key=lambda m: m.__name__.count("."), reverse=True):
        importlib.reload(m)


def preview(
    make: Callable[..., Compound],
    p: Any = None,
    **overrides: Any,
) -> Compound:
    """Build a shape from a params dataclass + overrides, show, and return it.

    Dataclass fields the make_* doesn't accept are dropped; explicit
    overrides are passed straight through (so a typo'd override still raises).
    """
    sig = set(inspect.signature(make).parameters)
    kwargs = {k: v for k, v in (asdict(p) if p else {}).items() if k in sig}
    kwargs.update(overrides)
    shape = make(**kwargs)
    reset_show()
    show(shape)
    return shape
