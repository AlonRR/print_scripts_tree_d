import logging
import operator
from collections.abc import Sequence
from functools import reduce
from math import ceil, cos, radians, sin, sqrt
from typing import Literal, cast

import build123d as bd
from build123d import (
    Box,
    CenterOf,
    Compound,
    Cylinder,
    Face,
    Part,
    Pos,
    ShapeList,
    Vector,
    Wire,
    extrude,
)

_log = logging.getLogger(__name__)
_SQRT3 = sqrt(3)


def make_washer(outer_diameter: float, hole_diameter: float, thickness: float) -> Compound:
    """Create a flat washer (annular disc) centred at the origin.

    Args:
        outer_diameter: Overall diameter of the washer in mm.
        hole_diameter: Diameter of the central hole in mm. Must be less than outer_diameter.
        thickness: Thickness of the washer along the Z axis in mm.

    Returns:
        A washer-shaped compound (outer cylinder minus inner cylinder).

    Raises:
        ValueError: If hole_diameter >= outer_diameter.
    """
    if hole_diameter >= outer_diameter:
        raise ValueError(
            f"hole_diameter ({hole_diameter}) must be less than outer_diameter ({outer_diameter})."
        )
    body = Cylinder(outer_diameter / 2, thickness)
    hole = Cylinder(hole_diameter / 2, thickness)
    return body - hole


def make_hexagonal_mesh(
    length: float,
    width: float,
    thickness: float,
    hex_radius: float,
    spacing: float,
    fillet_radius: float = 0.0,
    outer_border: float = 0.0,
) -> Compound:
    """Create a rectangular panel with a honeycomb pattern of hexagonal cutouts.

    Args:
        length: Panel dimension along the X axis in mm.
        width: Panel dimension along the Y axis in mm.
        thickness: Panel thickness along the Z axis in mm.
        hex_radius: circumradius (centre to vertex) of each hexagonal cutout in mm.
        spacing: Minimum gap between adjacent hexagon edges in mm.
        fillet_radius: If > 0, fillet top-face hex edges at this radius in mm.
        outer_border: If > 0, add a solid border of this width around the panel perimeter in mm.
    Returns:
        A compound representing the panel with hex cutouts subtracted.
    """
    base = Box(length, width, thickness)

    # Tiling step derived so the gap between any two adjacent hex edges equals spacing.
    S = hex_radius + spacing / _SQRT3
    dx, dy = 1.5 * S, S * _SQRT3

    # both=True extrudes symmetrically from z=0, matching the box which is also
    # centred at the origin. Without this, cuts only reach the top half of the
    # panel and leave a solid slab on the bottom.
    hex_template = extrude(bd.RegularPolygon(hex_radius, 6), thickness / 2, both=True)

    # Enough columns/rows to cover the panel; partial hexes at the boundary are
    # clipped automatically by the boolean subtraction.
    nx, ny = ceil(length / dx) + 1, ceil(width / dy) + 1
    total = (2 * nx + 1) * (2 * ny + 1)
    _log.info("Unioning %d hex cutters...", total)

    # Union all cutters into one shape, then subtract once — faster than
    # subtracting each hex from an increasingly complex result in a loop.
    cutters = reduce(
        operator.add,
        (
            Pos(col * dx, row * dy + (dy / 2 if col % 2 else 0)) * hex_template
            # Odd columns are offset by half a row step to form the honeycomb stagger.
            for col in range(-nx, nx + 1)
            for row in range(-ny, ny + 1)
        ),
    )

    if outer_border > 0:
        # Clip cutters to the inner region so hexes don't cut into the border.
        # Must happen before subtraction — unioning after would fill in the holes.
        _log.info("Clipping cutters to inner region...")
        inner = Box(length - 2 * outer_border, width - 2 * outer_border, thickness)
        cutters = cutters & inner

    _log.info("Subtracting cutters from base...")
    result = base - cutters

    if fillet_radius > 0:
        # Only fillet the top face — filleting all edges fails on the short, irregular
        # edges where partial hexagons are clipped at the panel boundary.
        # Edges shorter than 2 * fillet_radius are also skipped as they cannot
        # geometrically accommodate the requested radius.
        _log.info("Filleting top edges...")
        top_edges = ShapeList(
            e
            for e in max(result.faces(), key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z).edges()
            if e.length >= 2 * fillet_radius
        )
        result = result.fillet(fillet_radius, top_edges)

    return cast(Compound, result)


def make_table(
    table_top: Part | Compound,
    columns: list[Part | Compound],
    column_positions: list[tuple[float, float]],
) -> Compound:
    """Create a table by combining a tabletop and columns.

    Args:
        table_top:
            A Part representing the tabletop, centered at the origin.
        columns:
            A list of Parts representing the columns, each centered at the origin.
        column_positions:
            A list of (x, y) tuples in the range 0–100, where (0,0) places the
            column's outer corner flush with the tabletop corner and (100,100) does
            the same on the opposite corner. Columns never extend beyond the tabletop.
    Returns:
        A compound with the tabletop's bottom face at z=0 and columns extending upward.
    """
    top_bb = table_top.bounding_box().size
    # Shift the tabletop up so its bottom face sits at z=0.
    table = cast(Compound, Pos(0, 0, top_bb.Z / 2) * table_top)
    # Cache (x, y, z) extents by object id to avoid recomputing for identical columns.
    _bb_cache: dict[int, tuple[float, float, float]] = {}
    for column, (px, py) in zip(columns, column_positions):
        if id(column) not in _bb_cache:
            s = column.bounding_box().size
            _bb_cache[id(column)] = (s.X, s.Y, s.Z)
        col_x, col_y, col_z = _bb_cache[id(column)]
        if col_x >= top_bb.X or col_y >= top_bb.Y:
            raise ValueError(
                f"Column bounding box ({col_x:.1f} x {col_y:.1f}) must be smaller "
                f"than the tabletop ({top_bb.X:.1f} x {top_bb.Y:.1f})."
            )
        # Inset the usable range by each column's half-width so the edge, not
        # its centre, reaches the tabletop boundary at 0% and 100%.
        x = (px / 100 - 0.5) * (top_bb.X - col_x)
        y = (py / 100 - 0.5) * (top_bb.Y - col_y)
        # Column bottom sits on the tabletop top face; columns extend upward.
        table = cast(Compound, table + Pos(x, y, top_bb.Z + col_z / 2) * column)

    return table


def _scale_to_fit(part: Part, target_x: float, target_y: float) -> Part:
    """Uniformly scale *part* so its XY extents fit within target_x × target_y."""
    bb = part.bounding_box().size
    factor = min(target_x / bb.X, target_y / bb.Y)
    return part.scale(factor)


def _gusset(pts: list[tuple[float, float, float]], thickness: float) -> Compound:
    """Right-triangle prism from three 3-D points, extruded by thickness/2 both ways."""
    wire = Wire.make_polygon([Vector(*p) for p in pts], close=True)
    return cast(Compound, extrude(Face(wire), thickness / 2, both=True))


def make_column(
    body: Part,
    height: float,
    foot: Part,
    diameter: float | tuple[float, float] | None,
    gusset_size: float = 0.0,
    gusset_thickness: float = 0.0,
    gusset_position_z: Literal["top", "bottom"] = "top",
    gusset_orientation_xy: Sequence[float] = (0, 90, 180, 270),
) -> Compound:
    """Create a column by combining a shaped body section with a foot shape.

    Args:
        body:
            A Part representing the main section of the column, centered at the origin.
        height:
            The total height of the column along the Z axis in mm.
        foot:
            A Part representing the foot of the column, centered at the origin.
        diameter:
            If given, each part is scaled uniformly so its XY extent fits within this
            diameter (float → square, tuple → rectangle). Nothing is cut away.
        gusset_size:
            If > 0, right-triangle gussets of this arm length are added at the angles
            and position specified by gusset_orientation_xy and gusset_position_z.
        gusset_thickness:
            Thickness of each gusset in mm. Used when gusset_size > 0.
        gusset_position_z:
            "top" (default) places gussets at the top of the column; "bottom" places
            them at the bottom. Used when gusset_size > 0.
        gusset_orientation_xy:
            A list or tuple of four angles in degrees, specifying the XY rotation of
            each gusset around the leg. Used when gusset_size > 0. 
            Also used to determine number of gussets. 
    Returns:
        A compound representing the column.
    """
    if diameter is not None:
        if isinstance(diameter, tuple):
            tx, ty = diameter
        else:
            tx, ty = diameter, diameter
        body = _scale_to_fit(body, tx, ty)
        foot = _scale_to_fit(foot, tx, ty)

    foot_height = foot.bounding_box().size.Z
    body_height = body.bounding_box().size.Z

    # Foot at the bottom of the total height; body sits directly above it.
    foot_z = -height / 2 + foot_height / 2
    body_z = -height / 2 + foot_height + body_height / 2

    column = cast(Compound, Pos(0, 0, body_z) * body + Pos(0, 0, foot_z) * foot)

    # Cache XY extents before clipping — the Z-clip doesn't change XY.
    pre_clip_bb = column.bounding_box().size
    hw, hd = pre_clip_bb.X / 2, pre_clip_bb.Y / 2

    # Clip to the intended total height — the body may be taller than the gap.
    # & can return ShapeList in some build123d versions; reduce back to a single Compound.
    clipped = column & Box(10_000, 10_000, height)
    column = cast(Compound, reduce(operator.add, clipped) if isinstance(clipped, ShapeList) else clipped)

    if gusset_size > 0:
        if gusset_thickness <= 0:
            _log.warning("gusset_size > 0 but gusset_thickness is 0 — no gussets added.")
        else:
            gz = height / 2 if gusset_position_z == "top" else -height / 2
            # Vertical arm goes toward the body: down from top, up from bottom.
            gv = -gusset_size if gusset_position_z == "top" else gusset_size

            _log.info("Adding %d gussets at %s...", len(gusset_orientation_xy), gusset_position_z)
            gusset_shapes = []
            for angle_deg in gusset_orientation_xy:
                angle_rad = radians(angle_deg)
                cos_a, sin_a = cos(angle_rad), sin(angle_rad)
                cx, cy = cos_a * hw, sin_a * hd
                dx, dy = cos_a * gusset_size, sin_a * gusset_size
                pts = [(cx, cy, gz), (cx + dx, cy + dy, gz), (cx, cy, gz + gv)]
                gusset_shapes.append(_gusset(pts, gusset_thickness))
            if gusset_shapes:
                column = cast(Compound, column + reduce(operator.add, gusset_shapes))

    return column
