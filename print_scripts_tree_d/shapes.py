import logging
import operator
from functools import reduce
from math import ceil, sqrt
from typing import cast

import build123d as bd
from build123d import Box, Compound, Cylinder, Part, Pos, ShapeList, extrude

_log = logging.getLogger(__name__)
_SQRT3 = sqrt(3)


def make_box(length: float, width: float, height: float) -> Part:
    """Create a rectangular box centred at the origin.

    Args:
        length: Dimension along the X axis in mm.
        width: Dimension along the Y axis in mm.
        height: Dimension along the Z axis in mm.

    Returns:
        A solid rectangular box.
    """
    return Box(length, width, height)


def make_cylinder(radius: float, height: float) -> Part:
    """Create a cylinder centred at the origin with its axis along Z.

    Args:
        radius: Radius of the cylinder in mm.
        height: Height of the cylinder along the Z axis in mm.

    Returns:
        A solid cylinder.
    """
    return Cylinder(radius, height)


def make_washer(outer_diameter: float, hole_diameter: float, thickness: float) -> Compound:
    """Create a flat washer (annular disc) centred at the origin.

    Args:
        outer_diameter: Overall diameter of the washer in mm.
        hole_diameter: Diameter of the central hole in mm. Must be less than outer_diameter.
        thickness: Thickness of the washer along the Z axis in mm.

    Returns:
        A washer-shaped compound (outer cylinder minus inner cylinder).

    Raises:
        ValueError: Raised by build123d if hole_diameter >= outer_diameter.
    """
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
            for e in max(result.faces(), key=lambda f: f.center.Z).edges()
            if e.length >= 2 * fillet_radius
        )
        result = result.fillet(fillet_radius, top_edges)

    return cast(Compound, result)


def make_table(
    table_top: Part | Compound,
    legs: list[Part | Compound],
    leg_positions: list[tuple[float, float]],
    leg_height: float,
) -> Compound:
    """Create a table by combining a tabletop and legs.

    Args:
        table_top:
            A Part representing the tabletop, centered at the origin.
        legs:
            A list of Parts representing the legs, each centered at the origin.
        leg_positions:
            A list of (x, y) tuples in the range 0–100, where (0,0) is the
            bottom-left corner of the tabletop and (100,100) is the top-right.
        leg_height:
            The height of the legs along the Z axis in mm.
    Returns:
        A compound representing the assembled table.
    """
    bb = table_top.bounding_box().size
    table = cast(Compound, table_top)
    for leg, (px, py) in zip(legs, leg_positions):
        # Convert 0-100 percentage to absolute mm coordinates centred at origin.
        x = (px / 100 - 0.5) * bb.X
        y = (py / 100 - 0.5) * bb.Y
        table = cast(Compound, table + Pos(x, y, -leg_height / 2) * leg)

    return table


def _scale_to_fit(part: Part, target_x: float, target_y: float) -> Part:
    """Uniformly scale *part* so its XY extents fit within target_x × target_y."""
    bb = part.bounding_box().size
    factor = min(target_x / bb.X, target_y / bb.Y)
    return part.scale(factor)


def make_leg(
    leg_body: Part,
    leg_height: float,
    leg_foot: Part,
    leg_diameter: float | tuple[float, float] | None,
) -> Compound:
    """Create a leg by combining a shaped leg section with a foot shape.

    Args:
        leg_body:
            A Part representing the main section of the leg, centered at the origin.
        leg_height:
            The height of the leg along the Z axis in mm.
        leg_foot:
            A Part representing the foot of the leg, centered at the origin.
        leg_diameter:
            If given, each part is scaled uniformly so its XY extent fits within this
            diameter (float → square, tuple → rectangle). Nothing is cut away.
    Returns:
        A compound representing the leg.
    """
    if isinstance(leg_diameter, float):
        leg_body = _scale_to_fit(leg_body, leg_diameter, leg_diameter)
        leg_foot = _scale_to_fit(leg_foot, leg_diameter, leg_diameter)
    elif isinstance(leg_diameter, tuple):
        leg_body = _scale_to_fit(leg_body, leg_diameter[0], leg_diameter[1])
        leg_foot = _scale_to_fit(leg_foot, leg_diameter[0], leg_diameter[1])

    foot_height = leg_foot.bounding_box().size.Z

    # Foot sits at the bottom of the total height; body fills the space above it.
    foot_z = -leg_height / 2 + foot_height / 2
    body_z = foot_height / 2  # body bottom aligns with foot top

    return cast(Compound, Pos(0, 0, body_z) * leg_body + Pos(0, 0, foot_z) * leg_foot)
