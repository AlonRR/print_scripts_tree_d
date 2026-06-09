from build123d import Compound, Cylinder


def make_washer(outer_diameter: float, hole_diameter: float, thickness: float) -> Compound:
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
