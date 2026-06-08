import logging
import operator
from functools import reduce
from math import cos, pi, radians, sin
from typing import cast

from build123d import (
    Box,
    Compound,
    Cylinder,
    Face,
    Pos,
    Rot,
    ShapeList,
    Vector,
    Wire,
    extrude,
)

_log = logging.getLogger(__name__)


def _as_compound(result: object) -> Compound:
    if isinstance(result, ShapeList):
        return Compound(children=list(result))
    return cast(Compound, result)


def _snap_tab(
    outer_r: float,
    tab_protrusion: float,
    tab_length: float,
    tab_width: float,
    tip_z: float,
    angle_deg: float,
) -> Compound:
    """Right-triangle snap-tab prism on the outer surface of a cylinder.

    The triangle lies in the radial–Z plane at angle_deg, extruded
    circumferentially by tab_width / 2 in both directions.

    The cam face slopes from flush with the cylinder OD at the insertion
    tip to full protrusion at the base, guiding the bore entrance over the
    tab.  The flat base face is perpendicular to Z and locks the clip.
    """
    θ = radians(angle_deg)
    c, s = cos(θ), sin(θ)
    # r_inner sinks 0.5 mm into the wall so the prism properly overlaps
    # the cylinder body, avoiding a tangent (non-manifold) union.
    r_inner = outer_r - 0.5
    r2 = outer_r + tab_protrusion
    pts = [
        (r_inner * c, r_inner * s, tip_z),  # tip
        (r_inner * c, r_inner * s, tip_z - tab_length),  # base (lock)
        (r2 * c, r2 * s, tip_z - tab_length),  # base — protrusion
    ]
    wire = Wire.make_polygon([Vector(*p) for p in pts], close=True)
    return cast(Compound, extrude(Face(wire), tab_width / 2, both=True))


def make_cylinder_clip(
    bore_diameter: float,
    body_depth: float = 25.0,
    wall_thickness: float = 3.0,
    flange_overlap: float = 6.0,
    flange_thickness: float = 4.0,
    tab_count: int = 4,
    tab_protrusion: float = 2.0,
    tab_length: float = 10.0,
    tab_width: float = 15.0,
    slot_width: float = 2.5,
    clearance: float = 0.3,
    include_flange: bool = True,
    flat_bottom: bool = False,
    flat_fillet_r: float = 0.0,
    flat_inner_margin: float = 0.3,
) -> Compound:
    """Hollow cylindrical snap clip that mounts into a circular bore.

    The body slides into a bore_diameter circular hole; the flange stops at
    the bore face.  Spring fingers freed by longitudinal slot cuts carry
    wedge-shaped snap tabs near the insertion tip.  As the clip is pushed
    in, the bore entrance cams over each tab and snaps behind the lock face.

    Insertion direction is +Z.  The body is centred at Z = 0; the flange
    extends from Z = −(body_depth / 2) downward by flange_thickness.

    Args:
        bore_diameter:
            Diameter of the circular bore in mm.
        body_depth:
            Insertion depth into the bore in mm.
        wall_thickness:
            Clip tube wall thickness in mm.
        flange_overlap:
            Flange radius extension beyond bore radius in mm.
        flange_thickness:
            Flange disc thickness in mm.
        tab_count:
            Number of snap tabs (and slot cuts), evenly spaced.
        tab_protrusion:
            Radial protrusion of each tab beyond bore wall in mm.
        tab_length:
            Axial height of each tab wedge in mm.
        tab_width:
            Circumferential width of each tab prism in mm.
        slot_width:
            Width of each slot cut that frees a spring finger in mm.
        clearance:
            Per-side radial clearance for bore fit in mm.
        flat_bottom:
            When True, cut material beyond outer_r in the +X
            direction.  After Rot(0, 90, 0) the +X face maps to world −Z,
            so this makes the flange flush with the clip body on the
            print-down side, eliminating the downward overhang.
        flat_fillet_r:
            Fillet radius on the inner bore arc exposed on the
            flat cut face.  Ignored when flat_bottom is False or 0.
        flat_inner_margin:
            How far past the inner bore wall to place the
            flat cut (mm), so the inner bore arc is visible and fillet-able
            on the flat face.
    Returns:
        Clip compound with insertion along +Z, body centred at the origin.
    """
    od = bore_diameter - 2 * clearance
    id_ = od - 2 * wall_thickness

    if id_ <= 0:
        raise ValueError(
            f"wall_thickness {wall_thickness} too large for "
            f"{od:.1f} mm clip body OD."
        )

    tip_z = body_depth / 2
    outer_r = od / 2
    # Leave at least 2 mm of cylinder wall as the spring-finger root.
    eff_tab_length = min(tab_length, body_depth - 2.0)
    slot_length = min(eff_tab_length + 5.0, body_depth - 0.5)
    tab_spacing = 360.0 / tab_count

    _log.info(
        "Building clip body OD=%.1f ID=%.1f depth=%.1f...",
        od,
        id_,
        body_depth,
    )

    # Hollow cylinder body centred at Z = 0.
    body: Compound = Compound(children=[Cylinder(outer_r, body_depth)])
    body = _as_compound(body - Cylinder(id_ / 2, body_depth + 1))

    # Longitudinal slot cuts between adjacent tabs free the spring fingers.
    slot_z = tip_z - slot_length / 2
    _log.info("Cutting %d spring-finger slots...", tab_count)
    slots = reduce(
        operator.add,
        (
            Rot(0, 0, i * tab_spacing + tab_spacing / 2)
            * Pos(0, 0, slot_z)
            * Box(od + 4, slot_width, slot_length)
            for i in range(tab_count)
        ),
    )
    body = _as_compound(body - slots)

    # Snap tabs on the freed spring fingers near the insertion tip.
    _log.info("Adding %d snap tabs...", tab_count)
    tabs = reduce(
        operator.add,
        (
            _snap_tab(
                outer_r=outer_r,
                tab_protrusion=tab_protrusion,
                tab_length=eff_tab_length,
                tab_width=tab_width,
                tip_z=tip_z,
                angle_deg=i * tab_spacing,
            )
            for i in range(tab_count)
        ),
    )
    body = _as_compound(body + tabs)

    flange_r = outer_r
    if include_flange:
        flange_r = bore_diameter / 2 + flange_overlap
        flange_z = -(body_depth + flange_thickness) / 2
        flange_disc = Pos(0, 0, flange_z) * Cylinder(flange_r, flange_thickness)
        body = _as_compound(body + flange_disc)
    result = body

    if flat_bottom:
        inner_r = id_ / 2
        cut_x = inner_r - flat_inner_margin
        large = flange_r * 2 + 4
        depth = body_depth + flange_thickness + 4
        if flat_fillet_r > 0:
            # Fillet the inner bore top edge before the flat cut while it
            # is still a clean full circle.  After Rot(0, 90, 0) this edge
            # maps to the bottom of the clip, improving print quality.
            bore_top = [
                e
                for e in result.edges()
                if e.geom_type.name == "CIRCLE"
                and e.center().Z > 0
                and e.length >= 2 * flat_fillet_r
                and abs(e.length - 2 * pi * inner_r) < 1.0
            ]
            if bore_top:
                result = _as_compound(result.fillet(flat_fillet_r, bore_top))
        flat_cut = Pos(cut_x + large / 2, 0, 0) * Box(large, large, depth)
        result = _as_compound(result - flat_cut)

    return result
