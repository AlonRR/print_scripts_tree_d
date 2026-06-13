import logging
import operator
from functools import reduce
from math import atan2, ceil, cos, degrees, pi, radians, sin, sqrt
from typing import cast

import build123d as bd
from build123d import (
    Box,
    CenterOf,
    Compound,
    Cone,
    Cylinder,
    ShapeList,
    extrude,
)

_log = logging.getLogger(__name__)
_SQRT3 = sqrt(3)


def _as_compound(result: object) -> Compound:
    if isinstance(result, ShapeList):
        return Compound(children=list(result))
    return cast(Compound, result)


def _fillet_retry(
    shape: Compound, radius: float, edges: ShapeList
) -> tuple[Compound, float]:
    """Fillet ``edges`` of ``shape``, shrinking the radius on OCC failure.

    Tight geometry can make OCC refuse an otherwise reasonable fillet; rather
    than fail the whole build, retry with a progressively smaller radius.
    Returns the filleted shape (or ``shape`` unchanged if even a tiny radius
    fails) and the radius actually applied (0.0 if skipped).
    """
    applied = radius
    while edges and applied > 1e-3:
        try:
            return _as_compound(shape.fillet(applied, edges)), applied
        except Exception:
            applied *= 0.6
    return shape, 0.0


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
            Circumradius (centre to vertex) of each hexagonal cutout in mm.
        spacing:
            Minimum gap between adjacent hexagon edges in mm.
        fillet_radius:
            If > 0, fillet top-face hex edges at this radius in mm.
        outer_border:
            If > 0, add a solid border of this width around the panel perimeter in mm.
    Returns:
        A compound representing the panel with hex cutouts subtracted.
    """
    if hex_radius <= 0:
        raise ValueError(f"hex_radius must be > 0, got {hex_radius}")
    if spacing < 0:
        raise ValueError(f"spacing must be >= 0, got {spacing}")
    if outer_border > 0 and (
        2 * outer_border >= length or 2 * outer_border >= width
    ):
        _log.warning(
            "outer_border %.3g leaves no inner region for hex cutouts.",
            outer_border,
        )
    if fillet_radius > thickness:
        _log.warning(
            "fillet_radius %.3g exceeds panel thickness %.3g; top edges "
            "may be skipped.",
            fillet_radius,
            thickness,
        )

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

    # Pre-filter to hex centres whose bounding circle overlaps the clip
    # region (inner area when outer_border > 0, full panel otherwise).
    # Hexes entirely outside never cut anything and only bloat the cutter
    # compound fed to every subsequent OCC boolean op.
    inner_hx = length / 2 - outer_border + hex_radius
    inner_hy = width / 2 - outer_border + hex_radius
    # Offset the grid by -S in x so the panel centre falls on a junction point
    # (where three hexagons meet) rather than on a hex centre.
    # Derivation: without offset, three hexes at (0,0), (dx, ±dy/2) share a
    # vertex at (S, 0). Subtracting S from every x position moves that vertex
    # to the origin.
    positions = []
    for col in range(-nx, nx + 1):
        for row in range(-ny, ny + 1):
            # Odd columns offset by half a row to form the honeycomb stagger.
            x = col * dx - S
            y = row * dy + (dy / 2 if col % 2 else 0)
            if abs(x) < inner_hx and abs(y) < inner_hy:
                positions.append((x, y))
    _log.info("Unioning %d hex cutters...", len(positions))
    if not positions:
        return _as_compound(base)

    # Union all cutters into one shape, then subtract once — faster than
    # subtracting each hex from an increasingly complex result in a loop.
    cutters = _as_compound(
        reduce(
            operator.add,
            (bd.Pos(x, y) * hex_template for x, y in positions),
        )
    )

    if outer_border > 0:
        # Clip cutters to the inner region so hexes don't cut into the border.
        # Must happen before subtraction — unioning after would fill in the holes.
        _log.info("Clipping cutters to inner region...")
        inner = Box(
            length - 2 * outer_border, width - 2 * outer_border, thickness
        )
        cutters = _as_compound(cutters & inner)

    _log.info("Subtracting cutters from base...")
    result = _as_compound(base - cutters)

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
        if top_edges:
            result = _as_compound(result.fillet(fillet_radius, top_edges))

    return result


def make_magnet_ring_panel(
    outer_diameter: float,
    thickness: float,
    bore_diameter: float,
    magnet_diameter: float,
    magnet_thickness: float,
    number_of_magnets: int,
    clearance: float = 0.2,
    ring_margin: float = 0.5,
    wall_concavity: float = 0.0,
    bore_top_diameter: float = 0.0,
    bore_fillet_radius: float = 0.0,
    outer_fillet_radius: float = 0.0,
    pocket_fillet_radius: float = 0.3,
    top_slot_length: float = 2.0,
    top_slot_width: float = 1.0,
) -> Compound:
    """Create a flat rounded-corner regular-prism panel with magnet pockets.

    The outline is a regular polygon with one rounded corner per magnet:
    each magnet pocket sits inside a corner and the corners are joined by
    walls, so the panel reads as a prism with rounded corners rather than a
    scalloped flower of circular lobes. With ``wall_concavity > 0`` the walls
    between corners curve inward, pinching the panel to a waist between the
    bulging corners.

    Args:
        outer_diameter:
            Overall outer span of the panel in mm (the polygon corners
            reach this diameter when it is large enough for the magnets).
        thickness:
            Panel thickness along the Z axis in mm.
        bore_diameter:
            Diameter of the central bore hole in mm.
        magnet_diameter:
            Diameter of each cylindrical magnet in mm.
        magnet_thickness:
            Thickness of each cylindrical magnet in mm.
        number_of_magnets:
            Number of magnet pockets arranged evenly around the bore.
        clearance:
            Radial clearance per side for each magnet pocket in mm.
        ring_margin:
            Extra radial margin between the bore, magnet ring, and outer
            edge in mm.
        wall_concavity:
            Fraction in [0, 1) by which the walls between corners curve
            inward. 0 leaves straight walls; larger values carve a deeper
            concave waist (only applied when there are >= 3 magnets).
        bore_top_diameter:
            Diameter of the bore at the top face in mm, making the bore a
            cone (``bore_diameter`` is the bottom). 0 keeps a straight
            cylindrical bore.
        bore_fillet_radius:
            If > 0, round the bore mouth where it meets the bottom face by
            this radius in mm, so the rim is not a sharp edge.
        outer_fillet_radius:
            If > 0, round the outer top and bottom perimeter by this radius
            in mm, so the outside edge is not sharp. Capped at the material
            between each face and the magnet slot, (thickness -
            magnet_thickness) / 2, since the slots breach the corner walls.
        pocket_fillet_radius:
            Small edge-break radius in mm where the magnet slot's walls meet
            its flat floor and ceiling. Kept small so the floor and ceiling
            stay flat and parallel for the flat-faced cylindrical magnet; 0
            leaves a sharp internal edge.
        top_slot_length:
            Radial length in mm of a small obround slit cut into the top face
            above each magnet, centred at the magnet's inner edge (closest to
            the bore) and aligned with the slot. Breaks through into the
            magnet cavity. 0 (or 0 width) adds no slit.
        top_slot_width:
            Tangential width in mm of that obround top slit.
    Returns:
        A compound representing the panel.
    """
    if outer_diameter <= 0:
        raise ValueError(f"outer_diameter must be > 0, got {outer_diameter}")
    if thickness <= 0:
        raise ValueError(f"thickness must be > 0, got {thickness}")
    if bore_diameter <= 0:
        raise ValueError(f"bore_diameter must be > 0, got {bore_diameter}")
    if magnet_diameter <= 0:
        raise ValueError(f"magnet_diameter must be > 0, got {magnet_diameter}")
    if magnet_thickness <= 0:
        raise ValueError(
            f"magnet_thickness must be > 0, got {magnet_thickness}"
        )
    if number_of_magnets < 1:
        raise ValueError(
            f"number_of_magnets must be >= 1, got {number_of_magnets}"
        )
    if clearance < 0:
        raise ValueError(f"clearance must be >= 0, got {clearance}")
    if ring_margin < 0:
        raise ValueError(f"ring_margin must be >= 0, got {ring_margin}")
    if not 0 <= wall_concavity < 1:
        raise ValueError(
            f"wall_concavity must be in [0, 1), got {wall_concavity}"
        )
    if bore_top_diameter < 0:
        raise ValueError(
            f"bore_top_diameter must be >= 0, got {bore_top_diameter}"
        )
    if bore_fillet_radius < 0:
        raise ValueError(
            f"bore_fillet_radius must be >= 0, got {bore_fillet_radius}"
        )
    if outer_fillet_radius < 0:
        raise ValueError(
            f"outer_fillet_radius must be >= 0, got {outer_fillet_radius}"
        )
    if pocket_fillet_radius < 0:
        raise ValueError(
            f"pocket_fillet_radius must be >= 0, got {pocket_fillet_radius}"
        )
    if top_slot_length < 0:
        raise ValueError(f"top_slot_length must be >= 0, got {top_slot_length}")
    if top_slot_width < 0:
        raise ValueError(f"top_slot_width must be >= 0, got {top_slot_width}")

    bore_radius = bore_diameter / 2
    magnet_radius = magnet_diameter / 2
    pocket_radius = magnet_radius + clearance / 2

    if magnet_thickness > thickness:
        _log.warning(
            "magnet_thickness %.3g exceeds panel thickness %.3g; pockets will "
            "pass through the panel.",
            magnet_thickness,
            thickness,
        )

    # Rounded-corner regular prism. Each magnet lives in a rounded corner; the
    # corner radius is kept tight to the pocket (just one wall thickness wider)
    # so the corners read as fillets, not bulging lobes. Straight walls join
    # adjacent corners, giving the polygon-with-rounded-corners outline.
    n = number_of_magnets
    corner_radius = pocket_radius + ring_margin

    # Smallest ring radius (magnet/corner ring) that still leaves a wall around
    # the bore and keeps adjacent corners separated by a straight wall (their
    # corner circles must not merge, which would round the outline into a blob).
    min_ring = bore_radius + corner_radius + ring_margin
    if n > 1:
        min_ring = max(min_ring, corner_radius / sin(pi / n))

    # Honour outer_diameter by pushing the corners out to the rim when it is
    # large enough; otherwise expand to the minimum and warn.
    target_ring = outer_diameter / 2 - corner_radius
    if target_ring >= min_ring:
        ring_radius = target_ring
    else:
        ring_radius = min_ring
        _log.warning(
            "outer_diameter %.3g is too small for the requested magnet "
            "layout; panel will be expanded to %.3g.",
            outer_diameter,
            2 * (ring_radius + corner_radius),
        )

    pocket_ring_radius = ring_radius

    # Build the body as one smooth closed outline: a convex corner arc per
    # magnet joined by wall arcs, each tangent to its two neighbouring corner
    # circles. With wall_concavity > 0 the wall arcs curve inward to a waist;
    # at 0 they are straight. Every arc meets its neighbour tangentially, so
    # the perimeter is smooth (G1) — no crease forms between wall and corner as
    # concavity increases (the reason a bite-out-of-straight-walls approach
    # leaves a kink). Corner centres sit on the magnet ring.
    centers = [
        (
            ring_radius * cos(radians(i * 360 / n)),
            ring_radius * sin(radians(i * 360 / n)),
        )
        for i in range(n)
    ]

    if n >= 3:
        thetas = [radians(i * 360 / n) for i in range(n)]
        biss = [radians((i + 0.5) * 360 / n) for i in range(n)]
        half_chord = ring_radius * sin(pi / n)
        m_radius = ring_radius * cos(pi / n)
        depth = wall_concavity * 0.9 * half_chord
        if depth > 0:
            # Keep a wall of material between the waist and the bore. Use the
            # widest bore radius (the cone's top) so the waist clears the whole
            # bore, not just its narrow end.
            widest_bore = max(
                bore_radius,
                bore_top_diameter / 2 if bore_top_diameter > 0 else 0.0,
            )
            min_waist = widest_bore + ring_margin
            max_depth = m_radius + corner_radius - min_waist
            if depth > max_depth:
                _log.warning(
                    "wall_concavity %.3g would pinch the waist into the "
                    "bore; depth clamped from %.3g to %.3g mm.",
                    wall_concavity,
                    depth,
                    max(max_depth, 0.0),
                )
                depth = max(max_depth, 0.0)

        # Centre radius of each concave wall arc, tangent to its two corners.
        ce_radius = (
            m_radius + (half_chord**2 - depth**2) / (2 * depth)
            if depth > 0
            else 0.0
        )

        def _tan_dir(i: int, e: int) -> tuple[float, float]:
            # Unit direction from corner i toward wall arc e's centre (the
            # outward bisector when the wall is straight).
            if depth <= 0:
                return cos(biss[e]), sin(biss[e])
            dx = ce_radius * cos(biss[e]) - centers[i][0]
            dy = ce_radius * sin(biss[e]) - centers[i][1]
            length = sqrt(dx * dx + dy * dy)
            return dx / length, dy / length

        def _tan_point(i: int, e: int) -> tuple[float, float]:
            ux, uy = _tan_dir(i, e)
            return (
                centers[i][0] + corner_radius * ux,
                centers[i][1] + corner_radius * uy,
            )

        outline = []
        for i in range(n):
            start = _tan_point(i, (i - 1) % n)
            end = _tan_point(i, i)
            # The outward radial tip always lies on the convex corner arc, so
            # it is a robust arc mid-point (a bisector of the two tangent
            # directions goes antiparallel at high concavity and flips).
            tip = (
                centers[i][0] + corner_radius * cos(thetas[i]),
                centers[i][1] + corner_radius * sin(thetas[i]),
            )
            outline.append(
                bd.ThreePointArc(
                    bd.Vector(*start), bd.Vector(*tip), bd.Vector(*end)
                )
            )
            wall_end = _tan_point((i + 1) % n, i)
            if depth <= 0:
                outline.append(bd.Line(bd.Vector(*end), bd.Vector(*wall_end)))
            else:
                wr = m_radius + corner_radius - depth
                waist = (wr * cos(biss[i]), wr * sin(biss[i]))
                outline.append(
                    bd.ThreePointArc(
                        bd.Vector(*end),
                        bd.Vector(*waist),
                        bd.Vector(*wall_end),
                    )
                )
        body = _as_compound(
            extrude(bd.make_face(bd.Wire(outline)), thickness / 2, both=True)
        )
    else:
        # Too few magnets for a polygon: a central disc with rounded corner
        # bumps, plus a connecting wall for two magnets.
        parts = [Cylinder(bore_radius + corner_radius, thickness)]
        corner_solid = Cylinder(corner_radius, thickness)
        for x, y in centers:
            parts.append(bd.Pos(x, y, 0) * corner_solid)
        if n == 2:
            x0, y0 = centers[0]
            x1, y1 = centers[1]
            edge_length = sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
            if edge_length > 0:
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                edge_deg = degrees(atan2(y1 - y0, x1 - x0))
                wall = extrude(
                    bd.Rectangle(edge_length, 2 * corner_radius),
                    thickness / 2,
                    both=True,
                )
                parts.append(bd.Pos(mx, my, 0) * bd.Rot(0, 0, edge_deg) * wall)
        body = _as_compound(reduce(operator.add, parts))

    # A different top diameter makes the bore a cone; otherwise a cylinder.
    bore_top_radius = (
        bore_top_diameter / 2 if bore_top_diameter > 0 else bore_radius
    )
    if abs(bore_top_radius - bore_radius) < 1e-9:
        bore = Cylinder(bore_radius, thickness)
    else:
        bore = Cone(bore_radius, bore_top_radius, thickness)

    slit_length = max(
        magnet_thickness,
        corner_radius + magnet_radius + ring_margin,
    )
    slit_width = 2 * pocket_radius
    # Small edge break where the slot walls meet the floor and ceiling. The
    # magnets are flat-faced cylinders with only a tiny corner round, so keep
    # this small — the floor and ceiling must stay flat and parallel, not
    # heavily filleted.
    edge_fillet = min(
        pocket_fillet_radius,
        0.45 * magnet_thickness,
        0.45 * pocket_radius,
    )
    if pocket_fillet_radius > edge_fillet:
        _log.warning(
            "pocket_fillet_radius %.3g exceeds the slot limits; clamped to "
            "%.3g.",
            pocket_fillet_radius,
            edge_fillet,
        )
    # Slit reaches the outer surface of the rounded corner and runs inward,
    # so the magnet slides in from the corner face. The slot is a stadium
    # (obround): straight side walls and a half-circle inner end that matches
    # the curvature of the disc magnet, so the disc's edge nests against it.
    pocket_center_radius = pocket_ring_radius + corner_radius - slit_length / 2
    # The disc/half-circle centre, in the slot's local frame (slot runs along
    # +X, local origin maps to pocket_center_radius). The disc rests here.
    x_cap = -slit_length / 2 + magnet_radius
    # Run the mouth a little past the corner surface so the slot opens cleanly.
    mouth_x = slit_length / 2 + 0.5
    channel = bd.Pos((x_cap + mouth_x) / 2, 0, 0) * Box(
        mouth_x - x_cap, slit_width, magnet_thickness
    )
    cap = bd.Pos(x_cap, 0, 0) * Cylinder(pocket_radius, magnet_thickness)
    template = _as_compound(channel + cap)
    # Break the inside edge where the side and half-circle walls meet the flat
    # floor and ceiling: fillet the top and bottom perimeter in one pass.
    if edge_fillet > 0:
        seam_faces = template.faces()
        seam = ShapeList(
            e
            for f in (
                max(
                    seam_faces, key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z
                ),
                min(
                    seam_faces, key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z
                ),
            )
            for e in f.outer_wire().edges()
        )
        template, _ = _fillet_retry(template, edge_fillet, seam)

    # Optional small obround slit in the top face above each magnet, centred
    # at the magnet's inner edge (closest to the bore, local x = -slit_length/2)
    # and aligned with the slot. It breaks down into the magnet cavity from the
    # top while leaving the bottom of the panel solid.
    vent_template = None
    if top_slot_length > 0 and top_slot_width > 0:
        vent_bottom = magnet_thickness / 2 - 0.5  # just inside the cavity
        vent_h = thickness / 2 + 0.5 - vent_bottom
        if vent_h > 0:
            vent_len = max(top_slot_length, top_slot_width)
            vent_template = bd.Pos(
                -slit_length / 2 + top_slot_length / 2, 0, vent_bottom
            ) * extrude(bd.SlotOverall(vent_len, top_slot_width), vent_h)

    angle_step = 360 / number_of_magnets
    pockets = []
    vents = []
    for index in range(number_of_magnets):
        angle_deg = index * angle_step
        angle = radians(angle_deg)
        placement = bd.Pos(
            pocket_center_radius * cos(angle),
            pocket_center_radius * sin(angle),
            0,
        ) * bd.Rot(0, 0, angle_deg)
        pockets.append(placement * template)
        if vent_template is not None:
            vents.append(placement * vent_template)

    cutters = [bore, *pockets, *vents]
    result = _as_compound(body - _as_compound(reduce(operator.add, cutters)))

    if outer_fillet_radius > 0:
        # Round the outer top/bottom perimeter. The vertical corners are baked
        # into the profile, so each perimeter is one smooth closed loop and
        # fillets in a single pass. The radius is limited by the material
        # between the face and the magnet slot opening (the slots breach the
        # corner walls); a larger ball rolls into a slot and OCC fails.
        slot_gap = (thickness - magnet_thickness) / 2
        eff_r = min(
            outer_fillet_radius,
            0.95 * max(slot_gap, 0.0),
            0.49 * thickness,
        )
        if outer_fillet_radius > eff_r:
            _log.warning(
                "outer_fillet_radius %.3g exceeds the rim limit "
                "(thickness - magnet_thickness)/2; clamped to %.3g.",
                outer_fillet_radius,
                eff_r,
            )
        if eff_r > 0:
            faces = result.faces()
            top_face = max(
                faces, key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z
            )
            bot_face = min(
                faces, key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z
            )
            rim = ShapeList(
                list(top_face.outer_wire().edges())
                + list(bot_face.outer_wire().edges())
            )
            # Deeper concavity tightens the perimeter and lowers the largest
            # radius OCC will accept, so fall back to a smaller radius rather
            # than failing the whole build.
            result, applied = _fillet_retry(result, eff_r, rim)
            if 0 < applied < eff_r:
                _log.warning(
                    "outer_fillet_radius %.3g not buildable here; reduced to "
                    "%.3g.",
                    outer_fillet_radius,
                    applied,
                )
            elif rim and applied == 0.0:
                _log.warning(
                    "outer_fillet_radius %.3g could not be applied; skipped.",
                    outer_fillet_radius,
                )

    if bore_fillet_radius > 0:
        # Round the bore mouth where the cone/cylinder meets the bottom face.
        # Only the bore rim is a full circle centred on the Z axis; corner and
        # concave-wall arcs are centred off-axis, so filter by arc centre to
        # avoid touching the outline.
        eff_r = min(
            bore_fillet_radius,
            0.45 * thickness,
            0.45 * bore_radius,
        )
        if bore_fillet_radius > eff_r:
            _log.warning(
                "bore_fillet_radius %.3g exceeds bore/thickness limits; "
                "clamped to %.3g.",
                bore_fillet_radius,
                eff_r,
            )
        faces = result.faces()
        bot_face = min(faces, key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z)
        rim_edges = ShapeList(
            e
            for e in bot_face.edges()
            if e.geom_type.name == "CIRCLE"
            and e.arc_center.X**2 + e.arc_center.Y**2 < 1e-6
        )
        result, applied = _fillet_retry(result, eff_r, rim_edges)
        if 0 < applied < eff_r:
            _log.warning(
                "bore_fillet_radius %.3g not buildable here; reduced to %.3g.",
                bore_fillet_radius,
                applied,
            )
        elif rim_edges and applied == 0.0:
            _log.warning(
                "bore_fillet_radius %.3g could not be applied; skipped.",
                bore_fillet_radius,
            )

    return result
