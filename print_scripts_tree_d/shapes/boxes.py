import logging
from typing import cast

import build123d as bd
from build123d import CenterOf, Compound, ShapeList, extrude

_log = logging.getLogger(__name__)


def _as_compound(result: object) -> Compound:
    if isinstance(result, ShapeList):
        return Compound(children=list(result))
    return cast(Compound, result)


def make_rounded_box(
    length: float,
    width: float,
    height: float,
    wall_thickness: float,
    corner_radius: float,
    top_fillet_radius: float = 0.0,
    bottom_fillet_radius: float = 0.0,
) -> Compound:
    """Rectangular hollow tube with rounded edges.

    A solid outer box with a full-height rectangular through-cavity (no floor,
    no ceiling). Corner rounding is baked into the extruded profile (not a
    post-hoc fillet), so rim fillets on the top and bottom faces work cleanly.

    Args:
        length:
            Outer dimension along X in mm.
        width:
            Outer dimension along Y in mm.
        height:
            Height along Z in mm.
        wall_thickness:
            Thickness of each wall in mm.
        corner_radius:
            Radius of the outer vertical corner arcs in mm.
        top_fillet_radius:
            Fillet radius on the top rim edges (inner + outer).
            Clamped to wall_thickness / 2 * 0.95.
        bottom_fillet_radius:
            Fillet radius on the bottom rim edges (inner + outer).
            Same constraint.
    Returns:
        Hollow box compound centred at the origin.
    """
    # Outer profile with rounded corners; inner profile offset inward by
    # wall_thickness. Inner corner radius shrinks by wall_thickness to keep
    # a uniform wall at the corners.
    # RectangleRounded requires radius < min(w, h) / 2, so clamp both radii.
    inner_l = length - 2 * wall_thickness
    inner_w = width - 2 * wall_thickness
    if inner_l <= 0 or inner_w <= 0:
        raise ValueError(
            f"wall_thickness {wall_thickness} leaves no interior "
            f"({inner_l:.1f} x {inner_w:.1f} mm)."
        )
    max_corner_r = min(length, width) / 2 * 0.99
    if corner_radius > max_corner_r:
        _log.warning(
            "corner_radius %.3g exceeds half the smallest side; "
            "clamped to %.3g.",
            corner_radius,
            max_corner_r,
        )
    eff_corner_r = min(corner_radius, max_corner_r)
    inner_corner_r = min(
        max(0.1, corner_radius - wall_thickness),
        min(inner_l, inner_w) / 2 * 0.99,
    )
    outer_face = bd.RectangleRounded(length, width, eff_corner_r)
    inner_face = bd.RectangleRounded(inner_l, inner_w, inner_corner_r)

    # both=True centres the extrusion at z=0 (matches Box default).
    outer = extrude(outer_face, height / 2, both=True)
    inner = extrude(inner_face, height / 2 + 1, both=True)
    shell = _as_compound(outer - inner)

    # Rim fillets: straight edges on the top and bottom annular faces.
    # Arc edges from the rounded profile corners are skipped (geom_type != LINE).
    max_rim_r = wall_thickness / 2 * 0.95
    for requested_r, label, z_sel in (
        (top_fillet_radius, "top", max),
        (bottom_fillet_radius, "bottom", min),
    ):
        eff_r = min(requested_r, max_rim_r)
        if eff_r <= 0:
            continue
        if requested_r > max_rim_r:
            _log.warning(
                "%s_fillet_radius %.3g exceeds wall limit; clamped to %.3g.",
                label,
                requested_r,
                max_rim_r,
            )
        faces = shell.faces()
        rim_face = z_sel(
            faces, key=lambda f: f.center(CenterOf.BOUNDING_BOX).Z
        )
        rim_edges = ShapeList(
            e for e in rim_face.edges()
            if e.geom_type.name == "LINE" and e.length >= 2 * eff_r
        )
        if rim_edges:
            _log.info("Filleting %s rim r=%.3f...", label, eff_r)
            shell = shell.fillet(eff_r, rim_edges)

    return shell
