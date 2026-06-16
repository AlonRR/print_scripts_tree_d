# print_scripts_tree_d — design principles

Parametric 3D-printable shape library using [build123d](https://github.com/gumyr/build123d).
All dimensions are in **millimetres**. All shapes are validated as watertight before export.

---

## Development commands

Tooling is managed with **uv** (Python 3.13); run everything through it:

| Task | Command |
|---|---|
| Sync dependencies | `uv sync` |
| All tests | `uv run pytest` |
| One test | `uv run pytest tests/test_shapes.py -k <name>` |
| Lint (pyflakes + import sort) | `uv run ruff check .` |
| Type-check (strict) | `uv run mypy print_scripts_tree_d` |
| Build + export every model | `uv run python main.py` |

build123d pulls in OCP/OpenCASCADE; a single shape build (and each test) can
take seconds, so the suite is slow by unit-test standards — that is expected.

---

## Project structure

```
print_scripts_tree_d/
  params.py              # @dataclass parameter objects, one per shape family
  export.py              # save_stl() — exports + validates watertight/volume
  shapes/
    __init__.py          # re-exports every public make_* function
    boxes.py             # make_rounded_box
    clips.py             # make_cylinder_clip
    panels.py            # make_hexagonal_mesh, make_magnet_ring_panel
    furniture.py         # make_column, make_table
    primitives.py        # make_washer, make_magnet, make_screw_part
main.py                  # one-shot script that builds and exports all models
sandbox.ipynb            # interactive notebook for iterating on shapes
scratch/                 # interactive dev scripts (tracked); see below
models/                  # generated output files (git-ignored)
```

---

## Adding a new shape

1. **New module** — create `shapes/<name>.py`. Do **not** import from other
   shape files; each module is self-contained and depends only on `build123d`.
2. **Params dataclass** — add a `@dataclass` to `params.py` with `#:` doc-
   comments above every field and a one-line class docstring.
3. **Re-export** — add the `make_*` function to `shapes/__init__.py` and
   `__all__`.
4. **Wire up** — call it in `main.py` (and optionally the notebook).

---

## Params pattern

```python
@dataclass
class WidgetParams:
    """One-line description of what this shape is."""

    #: Outer dimension along X in mm.
    length: float = 100.0
    #: Composite sub-params use field(default_factory=…).
    pin: PinParams = field(default_factory=PinParams)
```

- Use `#:` (Sphinx field doc) above each field — not inline `# …` comments.
- All numeric defaults are in mm.
- Composite params nest via `field(default_factory=SubParams)`.

---

## Shape function signature

```python
def make_widget(length: float, width: float, ...) -> Compound:
    """Short description.

    Args:
        length: 
            Outer dimension along X in mm.
    Returns:
        Widget compound centred at the origin.
    """
```

- Return type is always `build123d.Compound`.
- Parameters are all explicit keyword arguments — no `**kwargs`.
- Shape is **centred at the origin**; Z is the primary (height) axis.
  Exception: `make_table` places the tabletop's bottom face at z=0 by design.
- Pure function — no module-level state.
- Validate inputs early — raise `ValueError` with a clear message for
  params that cannot produce valid geometry (e.g. `tab_count < 1`, a wall
  thicker than half the box, `hole_diameter >= outer_diameter`).

---

## Warnings for clamped / ignored params

`ValueError` is for params that **cannot** produce geometry. Many params,
though, are *valid* but get silently capped or skipped — a fillet radius
larger than the wall it rounds, a `tab_length` longer than the body, an
`outer_border` that swallows the whole panel. Silent clamping hides bugs:
the user sees geometry, just not the geometry they asked for.

Whenever a user value is silently clamped or causes a step to be skipped,
emit `_log.warning(...)` at the clamp site. Compute the effective value,
compare against the request, and warn on mismatch:

```python
eff_r = min(requested_r, max_rim_r)
if requested_r > max_rim_r:
    _log.warning(
        "top_fillet_radius %.3g exceeds wall limit; clamped to %.3g.",
        requested_r, max_rim_r,
    )
```

Rules:

- Warn, don't raise — the shape still builds; this is informational.
- State the offending param name, the value given, and what it was clamped
  to (or that the step was skipped). Use `%.3g` for the numbers.
- Warn once per param at the point of clamping, not inside loops over
  edges/faces. Skip the warning when the request is within range (no noise
  on sane defaults — check against the real defaults before committing).

---

## build123d API rules

Use the **direct (algebra) API** — never the builder context (`with BuildPart():`).

### Creating geometry

| Goal | Pattern |
|---|---|
| Solid primitives | `Box(l, w, h)`, `Cylinder(r, h)`, `Cone(r1, r2, h)` |
| Rounded-corner profile | `bd.RectangleRounded(w, h, r)` then `extrude(face, h/2, both=True)` |
| Regular polygon profile | `bd.RegularPolygon(r, sides)` then `extrude(face, depth, both=True)` |
| Translation | `Pos(x, y, z) * shape` |
| Union of many shapes | `reduce(operator.add, parts)` |
| Boolean subtract/intersect | `a - b`, `a & b` |

`both=True` in `extrude` centres the solid at z = 0, matching the default
behaviour of `Box`.

`reduce(operator.add, parts)` raises `TypeError` on an empty sequence —
guard with `if parts:` before calling (collect into a list and test it).
The same applies to `fillet()` on an empty edge list: skip the call when no
edges survive filtering. Both are easy to hit when boundary clipping or a
zero count removes every element.

### Returning Compound

`Compound` must be the return type; boolean ops (`+`, `-`, `&`) can return
`ShapeList` in some build123d versions. Define a local `_as_compound` helper
that wraps `ShapeList` into `Compound(children=[...])` and `cast`s everything
else. Seed with `Compound(children=[shape])` before calling `fillet()` so it
returns `Compound` rather than the base shape type.

### Edge and face selection

```python
# Top / bottom face by Z centre
top_face = max(shell.faces(), key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z)
bot_face = min(shell.faces(), key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z)

# Straight edges only — geom_type is an enum, NOT a string
straight = [e for e in face.edges() if e.geom_type.name == "LINE"]
# WRONG: e.geom_type == "LINE"  ← always False (enum ≠ str)
```

---

## Fillet rules

OCC fillet failures are the most common source of bugs.

### 1. Bake vertical corner rounding into the profile

Use `bd.RectangleRounded` + `extrude` for shapes that need rounded vertical
corners. Do **not** rely on a post-hoc `fillet()` on vertical edges when rim
fillets will also be applied — OCC cannot blend a corner fillet and a rim
fillet that share a vertex, and produces non-watertight geometry.

### 2. Rim fillets (top / bottom edges)

- Skip arc edges (`geom_type.name != "LINE"`); they are already smooth and
  OCC cannot re-fillet them.
- Skip edges too short to geometrically fit the radius (`e.length < 2 * r`).
- Cap the radius so it fits within the wall cross-section.
- When top and bottom use **different radii**, apply in separate passes. When
  the radius is the same, a single pass covering both faces is fine.

### 3. Never stage fillets at shared vertices

Applying a fillet whose edges share a vertex with a previously filleted edge
causes OCC to produce either a `ValueError` or a non-watertight mesh. Apply
such fillets simultaneously in one call, or rework the geometry so they do
not meet at the same vertex.

---

## Formatting

`ruff` enforces a **80-character** limit, but the existing code wraps closer
to **80** — match the surrounding file.

---

## Testing and validation

Correctness is verified by:

1. **`pytest` suite** (`tests/test_shapes.py`) — builds each shape and asserts
   geometry invariants (bounding box, volume vs. a solid, that invalid params
   raise). Add a test per new `make_*`. Tests are coarse, not exhaustive.
2. `save_stl` — asserts watertight mesh and positive volume. This is the
   primary pass/fail gate; a shape that raises here is not print-ready. Tests
   and `main.py` both go through it.
3. Visual inspection via `ocp_vscode`:
   - **`sandbox.ipynb`** — good for multi-shape assembly work. The
     `preview(make, params, **overrides)` helper builds from a params dataclass
     (dropping fields the function doesn't accept), shows, and returns the shape.
   - **`scratch/try_<name>.py`** — preferred for iterating a single new shape.
     Copy `scratch/template.py`, replace `SHAPENAME`, run cells with Shift+Enter
     in VS Code Interactive. `%autoreload 2` hot-reloads `print_scripts_tree_d`
     on every cell run; a bad cell doesn't hang the kernel. `scratch/_dev.py`
     provides all shared imports and helpers via `from _dev import *`.

If `save_stl` raises an `AssertionError`:

- **Holes in mesh** — almost always a fillet failure. Check for fillets on
  arc edges (`geom_type.name != "LINE"`), edges too short for the radius, or
  two fillet passes that meet at a shared vertex (see Fillet rules).
- **Negative volume** — the shape was fully subtracted or normals are
  inverted; verify the boolean operand order and that primitives overlap
  correctly.

---

## Export

```python
from print_scripts_tree_d.export import save_stl

save_stl(shape, models / "widget.stl")      # validates watertight + volume
```

---

## Logging

```python
import logging
_log = logging.getLogger(__name__)

_log.info("Unioning %d cutters...", n)
```

Log progress at `INFO` for operations that take noticeable time (large
boolean unions, fillet passes). Callers configure the root logger; shape
modules must not call `basicConfig`.

## Git

Always ask with a clear commit message before performing a commit even in Permission bypass mode.
