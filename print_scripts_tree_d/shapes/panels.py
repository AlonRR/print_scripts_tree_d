import logging
import operator
from functools import reduce
from math import ceil, sqrt
from typing import cast

import build123d as bd
from build123d import Box, CenterOf, Compound, ShapeList, extrude

_log = logging.getLogger(__name__)
_SQRT3 = sqrt(3)


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
        length:
            Panel dimension along the X axis in mm.
        width:
            Panel dimension along the Y axis in mm.
        thickness:
            Panel thickness along the Z axis in mm.
        hex_radius:
            circumradius (centre to vertex) of each hexagonal cutout in mm.
        spacing:
            Minimum gap between adjacent hexagon edges in mm.
        fillet_radius:
            If > 0, fillet top-face hex edges at this radius in mm.
        outer_border:
            If > 0, add a solid border of this width around the panel perimeter in mm.
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
    hex_template = extrude(
        bd.RegularPolygon(hex_radius, 6), thickness / 2, both=True
    )

    # Enough columns/rows to cover the panel; partial hexes at the boundary are
    # clipped automatically by the boolean subtraction.
    nx, ny = ceil(length / dx) + 1, ceil(width / dy) + 1
    total = (2 * nx + 1) * (2 * ny + 1)
    _log.info("Unioning %d hex cutters...", total)

    # Union all cutters into one shape, then subtract once — faster than
    # subtracting each hex from an increasingly complex result in a loop.
    #
    # Offset the grid by -S in x so the panel centre falls on a junction point
    # (where three hexagons meet) rather than on a hex centre.
    # Derivation: without offset, three hexes at (0,0), (dx, ±dy/2) share a
    # vertex at (S, 0). Subtracting S from every x position moves that vertex
    # to the origin.
    cutters = reduce(
        operator.add,
        (
            # Odd columns offset by half a row to form the honeycomb stagger.
            bd.Pos(col * dx - S, row * dy + (dy / 2 if col % 2 else 0))
            * hex_template
            for col in range(-nx, nx + 1)
            for row in range(-ny, ny + 1)
        ),
    )

    if outer_border > 0:
        # Clip cutters to the inner region so hexes don't cut into the border.
        # Must happen before subtraction — unioning after would fill in the holes.
        _log.info("Clipping cutters to inner region...")
        inner = Box(
            length - 2 * outer_border, width - 2 * outer_border, thickness
        )
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
            for e in max(
                result.faces(), key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z
            ).edges()
            if e.geom_type.name == "LINE" and e.length >= 2 * fillet_radius
        )
        result = result.fillet(fillet_radius, top_edges)

    return cast(Compound, result)
