---
name: watertight-debug
description: Diagnose and fix non-watertight / negative-volume geometry in print_scripts_tree_d, and apply the in-process watertight check + pitch-nudge retry pattern. Use when save_stl raises AssertionError ("mesh has holes" / "negative volume"), when a thread/swept/filleted shape fails to export, or when building geometry that must be guaranteed watertight before returning.
---

# Debug non-watertight geometry in print_scripts_tree_d

`save_stl` is the print-ready gate: it exports the STL, reloads it with trimesh,
and asserts `mesh.is_watertight` and `mesh.volume > 0`. A shape that raises here
is not printable. This skill covers the two failure modes and the in-process
guard that prevents them.

## The two AssertionErrors

### "mesh has holes — not print-ready" → almost always a fillet failure

Check, in this order:
1. **Fillet on an arc edge.** OCC cannot re-fillet an already-curved edge. Keep
   only straight edges: `[e for e in face.edges() if e.geom_type.name == "LINE"]`.
   (`geom_type` is an enum — `e.geom_type == "LINE"` is always False.)
2. **Edge too short for the radius.** Skip edges with `e.length < 2 * r`.
3. **Radius exceeds the wall cross-section.** Cap it to what fits.
4. **Two fillet passes meeting at a shared vertex.** OCC produces a non-manifold
   blend. Apply such fillets simultaneously in one `fillet()` call, or rework the
   geometry so the edges don't share a vertex. When top and bottom rims use
   *different* radii, run separate passes; same radius can share one pass.
5. **Corner-rounding + rim fillet sharing a vertex.** Bake vertical-corner
   rounding into the profile (`RectangleRounded` + extrude) instead of a post-hoc
   `fillet()` on vertical edges.
6. **A cone/cylinder cutting across a helical thread.** Lead-in and run-out cones
   tessellate non-watertight at *specific* pitches even when the boolean
   "succeeds." This one is not fixable by edge selection — use the pitch-nudge
   pattern below.

### "negative volume / inverted normals"

The shape was fully subtracted away, or a boolean ran in the wrong order.
- Verify operand order: `body - cutter`, not `cutter - body`.
- Verify the primitives actually overlap (a cutter that misses leaves the body
  unchanged or, combined with a later op, inverts).
- Check a count/clip didn't remove every element, leaving an empty or negative
  solid.

## The in-process watertight check

To reject a bad mesh **before** returning (so the caller can retry instead of
crashing in `save_stl`), tessellate in-process and test with trimesh. This
mirrors `save_stl`'s gate without writing a file. Canonical implementation
(already in `shapes/primitives.py` as `_mesh_is_watertight`):
```python
def _mesh_is_watertight(shape: Compound) -> bool:
    import numpy as np
    import trimesh

    verts, tris = shape.tessellate(0.001)
    mesh = trimesh.Trimesh(
        vertices=np.array([(v.X, v.Y, v.Z) for v in verts]),
        faces=np.array(tris),
    )
    return bool(mesh.is_watertight)
```
Notes:
- Lazy-import numpy/trimesh inside the function (they are heavy and only needed
  on this path).
- `tessellate(0.001)` is a fine tolerance — it is a check, not the export mesh.
  It is **not byte-identical** to `save_stl`'s mesh (which comes from
  `export_stl` at build123d's default deflection). They agree in practice for
  the thread cases here, but if you tighten one gate, re-validate the other.
- Prefer reusing the existing `_mesh_is_watertight` over re-implementing it.

## The pitch-nudge retry pattern

OCC's helical sweep + boolean degenerates at certain turn counts
(`thickness / pitch`): the result tessellates with holes or splits into multiple
solids. Dodge it by nudging the pitch a few percent — shifting the turn count off
the degenerate value — and rebuilding until the result is a single watertight
solid. Pattern (see `make_threaded_rod`):
```python
for factor in (1.0, 1.008, 0.992, 1.017, 0.984, 1.027, 1.04, 0.96):
    pitch = requested_pitch * factor
    try:
        shape = build_geometry(pitch)              # the whole pipeline
        good = len(shape.solids()) == 1 and _mesh_is_watertight(shape)
    except Exception:
        good = False
    if not good:
        continue
    if factor != 1.0:
        _log.warning(
            "thread_pitch %.3g hit an OCC degeneracy at this length; nudged "
            "to %.4g to keep it watertight.", requested_pitch, pitch,
        )
    return shape
raise ValueError(f"could not build a watertight result for pitch {requested_pitch} ...")
```
Cautions when using or extending this pattern:
- It **changes the user's spec** — a nudged thread won't mate with a part cut at
  the exact requested pitch. Always `_log.warning` the effective value, and
  prefer to return/expose it if a caller needs to script a mating part.
- Each iteration is a full rebuild (seconds). If `build_geometry` itself wraps
  another nudge loop (e.g. `make_threaded_rod` calling `make_screw_part`), the
  cost compounds (up to 8×6 builds) — keep the inner pipeline cheap, and
  reject early on `solids() != 1` before paying for tapers/bores.
- Only run the (expensive) `_mesh_is_watertight` gate on the paths that need it;
  a pure single-solid count is enough when no taper/cone crosses the thread.

## Construction tricks that keep booleans watertight

- **Avoid coincident faces.** Two solids sharing an exact cylindrical/planar
  face fuse non-watertight. Offset one by a hair (e.g. a collar at
  `outer_r + 1e-3`, or extend an intersection solid `1.0` mm past each body
  face) so no faces coincide.
- **Add a ridge onto a minor-diameter core, then clip flat**, rather than
  subtracting a groove — the groove approach leaves non-watertight slivers at
  the end faces on long/fine-pitch threads.
- **Drill the full bore last**, after lead-in/run-out, so the bore cuts through
  the final shape instead of leaving inner-edge artefacts at cone boundaries.
- A **revolved quarter-round ring** is more robust than an OCC edge `fillet()`
  for a cove at a union seam (the edge fillet there tends to collapse to a tiny
  radius).

## Verify

```
uv run pytest tests/test_shapes.py -k <name>     # include a save_stl(...) case
uv run python main.py                            # exports + validates every model
```
A shape whose watertightness is non-obvious (threads, swept profiles, fillets
that meet) **must** have a test that runs it through `save_stl(shape, tmp_path /
"x.stl")` — a volume-only assertion will pass on a holey mesh and hide the bug.
