import logging
from typing import cast

from build123d import (
    Compound,
    Cylinder,
    Helix,
    Plane,
    Polygon,
    Pos,
    ShapeList,
    sweep,
)

_log = logging.getLogger(__name__)


def _as_compound(result: object) -> Compound:
    if isinstance(result, ShapeList):
        return Compound(children=list(result))
    return cast(Compound, result)


def make_washer(
    outer_diameter: float, hole_diameter: float, thickness: float
) -> Compound:
    """Create a flat washer (annular disc) centred at the origin.

    Args:
        outer_diameter:
            Overall diameter of the washer in mm.
        hole_diameter:
            Diameter of the central hole in mm. Must be less than outer_diameter.
        thickness:
            Thickness of the washer along the Z axis in mm.
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


def make_magnet(outer_diameter: float, thickness: float) -> Compound:
    """Create a cylindrical magnet centred at the origin.

    Args:
        outer_diameter:
            Diameter of the magnet in mm.
        thickness:
            Thickness of the magnet along the Z axis in mm.
    Returns:
        A cylindrical magnet-shaped compound.
    """
    return Cylinder(outer_diameter / 2, thickness)


def make_screw_part(
    outer_diameter: float,
    thickness: float,
    thread_pitch: float = 0.0,
    bore_diameter: float = 0.0,
) -> Compound:
    """Create a screw-shaped part centred at the origin.

    A plain cylinder, or — when ``thread_pitch > 0`` — a cylinder with a
    single-start external helical thread. With ``bore_diameter > 0`` a central
    through-bore makes it a hollow screw (threaded tube).

    Args:
        outer_diameter:
            Outer (crest) diameter of the screw in mm.
        thickness:
            Length of the screw along the Z axis in mm.
        thread_pitch:
            Axial distance between thread crests in mm. 0 makes a smooth
            cylinder.
        bore_diameter:
            Diameter of an optional central through-bore in mm. 0 leaves the
            screw solid; must be < outer_diameter.
    Returns:
        A screw-shaped compound centred at the origin (Z is the axis).
    """
    if outer_diameter <= 0:
        raise ValueError(f"outer_diameter must be > 0, got {outer_diameter}")
    if thickness <= 0:
        raise ValueError(f"thickness must be > 0, got {thickness}")
    if thread_pitch < 0:
        raise ValueError(f"thread_pitch must be >= 0, got {thread_pitch}")
    if bore_diameter < 0:
        raise ValueError(f"bore_diameter must be >= 0, got {bore_diameter}")
    if bore_diameter >= outer_diameter:
        raise ValueError(
            f"bore_diameter ({bore_diameter}) must be < outer_diameter "
            f"({outer_diameter})"
        )

    outer_r = outer_diameter / 2.0
    if thread_pitch == 0:
        screw = _as_compound(Cylinder(outer_r, thickness))
        root_r = outer_r
    else:
        # Thread depth/width follow the pitch but are capped to the screw
        # radius so a coarse pitch (comparable to the diameter) cannot blow the
        # crest past outer_diameter or self-intersect.
        unclamped_depth = 0.6 * thread_pitch
        depth = min(unclamped_depth, 0.35 * outer_r)
        half_w = min(0.45 * thread_pitch, 0.45 * outer_r)
        if depth < unclamped_depth:
            _log.warning(
                "thread_pitch %.3g is coarse for diameter %.3g; thread depth "
                "clamped to %.3g.",
                thread_pitch, outer_diameter, depth,
            )
        # Core at the root (minor) radius with a helical triangular ridge swept
        # up to the crest. The profile sits in the plane perpendicular to the
        # helix tangent at its start (radial +X, axial along the other axis);
        # its base dips slightly into the core for a clean union.
        root_r = outer_r - depth
        helix = Helix(pitch=thread_pitch, height=thickness, radius=root_r)
        profile = Plane(
            origin=helix @ 0.0, z_dir=helix % 0.0, x_dir=(1, 0, 0)
        ) * Polygon(
            (-0.1, -half_w), (-0.1, half_w), (depth, 0.0), align=None
        )
        # Helix runs z = 0..thickness; shift the ridge to the centred core.
        thread = Pos(0, 0, -thickness / 2) * sweep(profile, path=helix)
        core = Cylinder(root_r + 0.05, thickness)
        # The swept ridge overruns the ends; trim flush to thickness with a
        # generous-radius cylinder so only the axial overrun is cut, not the
        # crest.
        screw = _as_compound(
            (core + thread) & Cylinder(outer_r + 1.0, thickness)
        )

    if bore_diameter > 0:
        bore_r = bore_diameter / 2.0
        if bore_r >= root_r:
            _log.warning(
                "bore_diameter %.3g reaches past the thread root (%.3g); the "
                "core wall is gone, leaving only the thread ridges.",
                bore_diameter, 2 * root_r,
            )
        screw = _as_compound(screw - Cylinder(bore_r, thickness + 2))

    return screw
