---
name: new-shape
description: Scaffold a new parametric shape in print_scripts_tree_d end-to-end — module, params dataclass, re-export, main.py wiring, a pytest case, and a scratch try-script. Use when the user asks to add a new make_* shape, a new shape family, or "a new part" to this build123d library.
---

# Add a new shape to print_scripts_tree_d

This library is a parametric 3D-printing shape library built on build123d. A
"shape" is a pure function `make_<name>(...) -> Compound` plus its params
dataclass, re-export, main.py call, test, and scratch script. Follow the steps
below in order; do not skip the test or the export validation — `save_stl` is
the real pass/fail gate.

Read the repo-root `CLAUDE.md` first if you have not this session — it holds the
authoritative build123d API rules, fillet rules, and warning conventions that
this skill summarizes. When they disagree, CLAUDE.md wins.

## Step 0 — Pin down the geometry before writing code

Confirm with the user (or state your assumption) before building:
- The primary axis is **Z** (height); the shape is **centred at the origin**.
  (Only `make_table` deviates, by design.)
- Units are **millimetres**, always.
- FDM target: prefer support-free geometry — flat bottoms, ≤45° overhangs, no
  thin unsupported bridges. Flag any overhang the design forces.
- Which inputs are *hard* constraints (raise `ValueError`) vs. *soft* ones that
  clamp (emit `_log.warning`). See Step 2 and Step 3.

## Step 1 — New module: `shapes/<name>.py`

Create `print_scripts_tree_d/shapes/<name>.py`. It must be **self-contained**:
import only from `build123d` (and stdlib) — never from a sibling shape module.

Boilerplate every shape module needs:
```python
import logging
from typing import cast

from build123d import Compound, ShapeList  # + the primitives you use

_log = logging.getLogger(__name__)


def _as_compound(result: object) -> Compound:
    if isinstance(result, ShapeList):
        return Compound(children=list(result))
    return cast(Compound, result)
```
`_as_compound` is **deliberately duplicated per module** (CLAUDE.md mandates a
local copy) — do not try to share it from another module.

Use the **direct/algebra API only** — never `with BuildPart():`. Common moves:
| Goal | Pattern |
|---|---|
| Solids | `Box(l,w,h)`, `Cylinder(r,h)`, `Cone(r1,r2,h)` |
| Rounded vertical corners | `bd.RectangleRounded(w,h,r)` then `extrude(face, h/2, both=True)` |
| Regular polygon | `bd.RegularPolygon(r, sides)` then `extrude(face, depth, both=True)` |
| Move | `Pos(x,y,z) * shape` |
| Union of many | `reduce(operator.add, parts)` — **guard `if parts:`** (raises on empty) |
| Subtract / intersect | `a - b`, `a & b` |

`both=True` centres the extrude at z=0, matching `Box`.

## Step 2 — Validate inputs early (raise) vs. clamp (warn)

Right after the signature, raise `ValueError` for params that **cannot** make
valid geometry — with a message naming the param and the value:
```python
if outer_diameter <= 0:
    raise ValueError(f"outer_diameter must be > 0, got {outer_diameter}")
if hole_diameter >= outer_diameter:
    raise ValueError(
        f"hole_diameter ({hole_diameter}) must be < outer_diameter "
        f"({outer_diameter})"
    )
```

For params that are *valid* but get silently capped or skipped (a fillet radius
bigger than the wall, a slot longer than the body), compute the effective value
and **warn on mismatch** — never silently clamp:
```python
eff_r = min(requested_r, max_rim_r)
if requested_r > max_rim_r:
    _log.warning(
        "top_fillet_radius %.3g exceeds wall limit; clamped to %.3g.",
        requested_r, eff_r,
    )
```
Rules: warn don't raise; name the param, the given value, and the clamp; use
`%.3g`; warn **once** at the clamp site (not inside an edge loop); and **do not
warn when the request is in range** — check against the real defaults so sane
calls stay silent.

## Step 3 — Fillets (the #1 source of non-watertight bugs)

- Bake **vertical-corner rounding into the profile** (`RectangleRounded` +
  extrude). Do not post-hoc `fillet()` vertical edges if rim fillets also apply
  — OCC cannot blend a corner fillet and a rim fillet sharing a vertex.
- Rim fillets: skip arc edges (`e.geom_type.name != "LINE"`), skip edges too
  short for the radius (`e.length < 2 * r`), and cap the radius to the wall.
- **Never stage fillets at a shared vertex.** Apply simultaneously in one
  `fillet()` call, or rework so they don't meet.
- Skip the `fillet()` call entirely on an empty edge list (it raises).
- Edge/face selection idioms:
  ```python
  top = max(shell.faces(), key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z)
  straight = [e for e in face.edges() if e.geom_type.name == "LINE"]
  # WRONG: e.geom_type == "LINE"  (enum != str, always False)
  ```

Return type is **always `Compound`**. Seed with `Compound(children=[shape])`
before `fillet()` so it returns a Compound, and wrap boolean results in
`_as_compound(...)`.

## Step 4 — Params dataclass in `params.py`

Add a `@dataclass` with a one-line class docstring and a `#:` Sphinx doc-comment
**above** every field (not inline `# …`). All numeric defaults in mm. Composite
params nest via `field(default_factory=SubParams)`.
```python
@dataclass
class WidgetParams:
    """One-line description of what this shape is."""

    #: Outer dimension along X in mm.
    length: float = 100.0
    #: Composite sub-params use field(default_factory=…).
    pin: PinParams = field(default_factory=PinParams)
```
Keep the dataclass field defaults **in sync** with the function's keyword
defaults — a diverged default produces different geometry depending on call
path (this has bitten the repo before).

## Step 5 — Re-export

In `shapes/__init__.py`, import `make_<name>` and add it to `__all__`.

## Step 6 — Wire into `main.py`

Add a build+export call so `uv run python main.py` exercises it:
```python
from print_scripts_tree_d.export import save_stl
save_stl(make_widget(...), models / "widget.stl")  # validates watertight+volume
```

## Step 7 — Test in `tests/test_shapes.py`

Add at least one coarse invariant test and one invalid-params test:
```python
def test_make_widget_volume() -> None:
    w = make_widget(length=100, ...)
    assert w.volume < bounding_solid_volume          # cutouts removed material
    assert w.bounding_box().size.Z == pytest.approx(expected_height, abs=0.2)

def test_make_widget_invalid_raises() -> None:
    with pytest.raises(ValueError):
        make_widget(length=0, ...)
```
For anything whose watertightness is non-trivial (threads, swept profiles,
fillets that meet), add a test that runs it through `save_stl(shape, tmp_path /
"x.stl")` — that is the only check that catches mesh holes.

## Step 8 — Scratch try-script

Copy `scratch/template.py` to `scratch/try_<name>.py`, replace `SHAPENAME`, and
use `from _dev import *` for shared imports/helpers. `preview(make, params,
**overrides)` builds from a params dataclass (dropping fields the function does
not accept), shows via `ocp_vscode`, and returns the shape. Run cells with
Shift+Enter in VS Code Interactive; `%autoreload 2` hot-reloads the package.

## Step 9 — Verify the whole chain

```
uv run ruff check .
uv run mypy print_scripts_tree_d
uv run pytest tests/test_shapes.py -k <name>
uv run python main.py            # confirms the export validates watertight
```
build123d is slow (seconds per shape) — that is expected, not a hang.

If `save_stl` raises `AssertionError`, see the **watertight-debug** skill —
holes are almost always a fillet failure; negative volume is an operand-order
or normals problem.
