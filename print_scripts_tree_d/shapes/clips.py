import logging
import operator
from collections.abc import Callable
from functools import reduce
from math import atan2, cos, degrees, pi, sin
from typing import cast

from build123d import (
    Axis,
    Box,
    Compound,
    Cylinder,
    Face,
    Line,
    Pos,
    Rot,
    ShapeList,
    ThreePointArc,
    Vector,
    Wire,
    revolve,
)

_log = logging.getLogger(__name__)


def _as_compound(result: object) -> Compound:
    if isinstance(result, ShapeList):
        return Compound(children=list(result))
    return cast(Compound, result)


def _fillet_circle(
    body: Compound,
    circ: float,
    radius: float,
    z_ok: Callable[[float], bool],
) -> Compound:
    """Fillet the complete-circle edge(s) of *body* whose circumference
    matches *circ* and whose centre Z satisfies *z_ok*.

    A no-op when *radius* is non-positive or no matching edge survives
    (e.g. the circle was already segmented by slot cuts). Edges shorter
    than 2 * radius are skipped so OCC can fit the fillet.
    """
    if radius <= 0:
        return body
    edges = [
        e
        for e in body.edges()
        if e.geom_type.name == "CIRCLE"
        and z_ok(e.center().Z)
        and e.length >= 2 * radius
        and abs(e.length - circ) < 1.0
    ]
    return _as_compound(body.fillet(radius, edges)) if edges else body


def _snap_tab(
    outer_r: float,
    tab_protrusion: float,
    tab_length: float,
    tab_width: float,
    tip_z: float,
) -> Compound:
    """Snap tab with a rounded cam face, revolved to follow the bore.

    The radial–Z profile (a convex cam arc plus a flat lock ledge) is
    revolved about Z through the angular width that spans tab_width of arc
    at the protrusion radius, and returned centred on the +X axis for the
    caller to rotate into place.  Because it is revolved, the protruding
    cam surface is concentric with the bore, so the bore presses on it with
    uniform pressure across the whole tab instead of pinching a single
    tangent line.  The cam arc rises from flush with the OD at the
    insertion tip to full protrusion at the base; its radius is chosen so
    the base corner is the arc's outermost point, capping the protrusion at
    exactly tab_protrusion.  The flat base face is perpendicular to Z and
    locks the clip.
    """
    # r_inner sinks 0.5 mm into the wall so the tab properly overlaps the
    # cylinder body, avoiding a tangent (non-manifold) union.
    r_inner = outer_r - 0.5
    r2 = outer_r + tab_protrusion
    base_z = tip_z - tab_length

    def _p(u: float, v: float) -> Vector:
        """Map radial distance u, height v into the XZ half-plane."""
        return Vector(u, 0.0, v)

    # Cam arc through tip -> base corner. Centre the circle so the base
    # corner is its outermost point; the arc then stays within r2, capping
    # protrusion at tab_protrusion. A 3-point arc keeps it in the XZ plane.
    a = r2 - r_inner
    radius = (a * a + tab_length * tab_length) / (2 * a)
    centre_u = r2 - radius
    mid_ang = atan2(tip_z - base_z, r_inner - centre_u) / 2.0
    cam_mid = _p(
        centre_u + radius * cos(mid_ang), base_z + radius * sin(mid_ang)
    )
    cam_profile = (
        ThreePointArc(_p(r_inner, tip_z), cam_mid, _p(r2, base_z))
        + Line(_p(r2, base_z), _p(r_inner, base_z))
        + Line(_p(r_inner, base_z), _p(r_inner, tip_z))
    )
    # tab_width is the arc length at the protrusion radius r2.
    sweep = degrees(tab_width / r2)
    cam_wedge = Rot(0, 0, -sweep / 2) * revolve(
        Face(cast(Wire, cam_profile)), Axis.Z, revolution_arc=sweep
    )
    return _as_compound(cam_wedge)


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
    lead_in_fillet: float = 0.8,
    include_flange: bool = True,
    flat_bottom: bool = False,
    flat_fillet_r: float = 0.0,
    flat_inner_margin: float = 0.3,
    bore_floor_fillet_r: float = 0.0,
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
            Circumferential arc-width of each tab at the protrusion
            radius in mm.
        slot_width:
            Width of each slot cut that frees a spring finger in mm.
        clearance:
            Per-side radial clearance for bore fit in mm.
        lead_in_fillet:
            Fillet radius on the leading (insertion-tip) outer rim in mm,
            rounding the edge that first enters the bore so the clip noses
            in instead of catching; 0 = no fillet. Clamped to 0.9x the
            wall thickness.
        flat_bottom:
            When True, cut material beyond outer_r in the +X
            direction.  After Rot(0, 90, 0) the +X face maps to world −Z,
            so this makes the flange flush with the clip body on the
            print-down side, eliminating the downward overhang.  The
            tab/slot pattern is rotated half a spacing so a tab gap (not a
            tab) faces this flat cut, leaving every snap tab intact.
        flat_fillet_r:
            Fillet radius on the inner bore arc exposed on the
            flat cut face.  Ignored when flat_bottom is False or 0.
        flat_inner_margin:
            Depth of the flat cut measured inward from the body outer
            wall (mm); the cut plane sits at outer_r - flat_inner_margin.
            A positive value bites into the wall toward the bore, so the
            inner bore arc is exposed and fillet-able on the flat face; a
            negative value keeps the cut outside the wall.
        bore_floor_fillet_r:
            Fillet radius on the concave corner where the bore wall meets
            the flange cap that floors the blind hole (mm); 0 = no fillet.
            Only applies when include_flange is True.
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

    if tab_count <= 0:
        raise ValueError(f"tab_count must be >= 1, got {tab_count}")

    tip_z = body_depth / 2
    outer_r = od / 2
    inner_r = id_ / 2
    # Leave at least 2 mm of cylinder wall as the spring-finger root.
    eff_tab_length = min(tab_length, body_depth - 2.0)
    if tab_length > body_depth - 2.0:
        _log.warning(
            "tab_length %.3g leaves < 2 mm finger root; clamped to %.3g.",
            tab_length,
            body_depth - 2.0,
        )
    if flat_bottom and flat_fillet_r > wall_thickness:
        _log.warning(
            "flat_fillet_r %.3g exceeds wall_thickness %.3g; bore-top "
            "edge may be skipped.",
            flat_fillet_r,
            wall_thickness,
        )
    slot_length = min(eff_tab_length + 5.0, body_depth - 0.5)
    tab_spacing = 360.0 / tab_count
    # When printing flat, rotate the whole tab/slot pattern by half a spacing
    # so a tab gap (not a tab) faces the +X flat cut, keeping every snap tab
    # intact instead of shaving one off.
    tab_phase = tab_spacing / 2 if flat_bottom else 0.0

    # Each tab is an angular wedge of arc-width tab_width at the protrusion
    # radius; with one slot per gap, a tab plus its slot must fit in one
    # angular slice or the slot cuts into the tab (and adjacent tabs merge).
    tab_r = outer_r + tab_protrusion
    max_tab_width = 2 * pi * tab_r / tab_count - slot_width
    if max_tab_width <= 0:
        raise ValueError(
            f"slot_width {slot_width} leaves no room for {tab_count} tabs "
            f"around the {2 * tab_r:.1f} mm protrusion circle."
        )
    eff_tab_width = min(tab_width, max_tab_width)
    if tab_width > max_tab_width:
        _log.warning(
            "tab_width %.3g exceeds the per-tab arc; clamped to %.3g so "
            "tabs and slots do not overlap.",
            tab_width,
            max_tab_width,
        )

    _log.info(
        "Building clip body OD=%.1f ID=%.1f depth=%.1f...",
        od,
        id_,
        body_depth,
    )

    # Hollow cylinder body centred at Z = 0.
    body: Compound = Compound(children=[Cylinder(outer_r, body_depth)])
    body = _as_compound(body - Cylinder(inner_r, body_depth + 1))

    # Lead-in fillet on the leading (insertion-tip) outer rim, applied now
    # while it is still a complete circle, so the nose eases into the bore.
    if lead_in_fillet > 0:
        eff_lead_in = min(lead_in_fillet, 0.9 * wall_thickness)
        if lead_in_fillet > eff_lead_in:
            _log.warning(
                "lead_in_fillet %.3g exceeds wall limit; clamped to %.3g.",
                lead_in_fillet,
                eff_lead_in,
            )
        body = _fillet_circle(
            body, 2 * pi * outer_r, eff_lead_in, lambda z: z > 0
        )

    # Round the inner bore-top edge now, while it is still a complete
    # circle.  The slot cuts below segment it into arcs that OCC cannot
    # re-fillet; after Rot(0, 90, 0) this edge faces the print-down side.
    if flat_bottom and flat_fillet_r > 0:
        body = _fillet_circle(
            body, 2 * pi * inner_r, flat_fillet_r, lambda z: z > 0
        )

    # Longitudinal slot cuts between adjacent tabs free the spring fingers.
    # Single-sided radial slots (one per gap); a full-diameter box would
    # also cut the gap 180° away, which lands on a tab for odd tab_count.
    slot_z = tip_z - slot_length / 2
    _log.info("Cutting %d spring-finger slots...", tab_count)
    slots = reduce(
        operator.add,
        (
            Rot(0, 0, i * tab_spacing + tab_spacing / 2 + tab_phase)
            * Pos(od / 4, 0, slot_z)
            * Box(od / 2 + 2, slot_width, slot_length)
            for i in range(tab_count)
        ),
    )
    body = _as_compound(body - slots)

    # Snap tabs on the freed spring fingers near the insertion tip. All tabs
    # are identical, so revolve one wedge and rotate a copy into each slot.
    _log.info("Adding %d snap tabs...", tab_count)
    base_tab = _snap_tab(
        outer_r=outer_r,
        tab_protrusion=tab_protrusion,
        tab_length=eff_tab_length,
        tab_width=eff_tab_width,
        tip_z=tip_z,
    )
    tabs = reduce(
        operator.add,
        (
            Rot(0, 0, i * tab_spacing + tab_phase) * base_tab
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

        # Round the concave corner where the bore wall meets the flange cap
        # that floors the blind hole. Cap the radius to the floor radius and
        # to the unslotted root ring, so the fillet stays on a complete
        # circle below the spring-finger slots.
        if bore_floor_fillet_r > 0:
            floor_z = -body_depth / 2
            root_h = body_depth - slot_length
            eff_floor_r = min(bore_floor_fillet_r, 0.9 * inner_r, 0.9 * root_h)
            if bore_floor_fillet_r > eff_floor_r:
                _log.warning(
                    "bore_floor_fillet_r %.3g exceeds bore/root limit; "
                    "clamped to %.3g.",
                    bore_floor_fillet_r,
                    eff_floor_r,
                )
            body = _fillet_circle(
                body,
                2 * pi * inner_r,
                eff_floor_r,
                lambda z: abs(z - floor_z) < 0.5,
            )
    result = body

    if flat_bottom:
        cut_x = outer_r - flat_inner_margin
        large = flange_r * 2 + 4
        # Box spans the whole clip in Z (and beyond) so the cut face stays
        # flat regardless of flange_thickness.
        flat_cut = Pos(cut_x + large / 2, 0, 0) * Box(large, large, 10_000)
        result = _as_compound(result - flat_cut)

    return result


def make_magnet_attachment_clip(
    bore_diameter: float,
    magnet_diameter: float,
    magnet_thickness: float,
    number_of_magnets: int,
    wall_thickness: float,
) -> Compound:
    """Make a flat clip that attaches cylindrical bores with cylindrical magnets.

    The clip body is a hollow prism whose shape is determined by the number
    of magnets and their dimensions. The magnet(s) are held in an array at the
    base of the clip, with the magnet axis aligned with the clip's attachment
    axis. The magnets are held in place by a flange that extends outward from
    the outer wall of the clip, and a small gap in the flange allows the
    magnets to be pressed in and held by friction. A small hole is left for
    easy removal.

    Args:
        bore_diameter: Diameter of the circular bore in mm.
        magnet_diameter: Diameter of the cylindrical magnets in mm.
        magnet_thickness: Thickness of the cylindrical magnets in mm.
        number_of_magnets: Number of magnets to hold in the clip.
        wall_thickness: Thickness of the clip walls in mm.
    Returns:
        A compound representing the magnet attachment clip.

    """

    # Calculate the shape of the clip body based on the number of magnets and their dimensions
    magnet_radius = magnet_diameter / 2
    clip_length = magnet_diameter * number_of_magnets + wall_thickness * 2
    clip_width = magnet_diameter + wall_thickness * 2
    clip_height = magnet_thickness + wall_thickness * 2
    # Create the hollow prism body of the clip
    outer_box = Box(clip_length, clip_width, clip_height)
    inner_box = Box(
        clip_length - 2 * wall_thickness,
        clip_width - 2 * wall_thickness,
        clip_height - 2 * wall_thickness,
    )
    clip_body = outer_box - inner_box
    # Create the flange to hold the magnets in place
    flange_length = magnet_diameter * number_of_magnets + wall_thickness
    flange_width = wall_thickness
    flange_height = magnet_thickness + wall_thickness
    flange = Box(flange_length, flange_width, flange_height)
    flange = Pos(wall_thickness, (clip_width - flange_width) / 2, wall_thickness) * flange
    clip_body += flange
    # Create the hole for magnet removal
    hole_radius = magnet_radius / 2
    hole = Cylinder(hole_radius, flange_height)
    hole = Pos(wall_thickness + magnet_radius, clip_width / 2, wall_thickness) * hole
    clip_body = _as_compound(clip_body - hole)

    return _as_compound(clip_body)
