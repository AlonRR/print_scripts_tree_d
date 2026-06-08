from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class HexPanelParams:
    """Rectangular panel with a honeycomb hex cutout pattern."""

    #: Panel dimension along X in mm.
    length: float = 200.0
    #: Panel dimension along Y in mm.
    width: float = 200.0
    #: Panel thickness along Z in mm.
    thickness: float = 2.5
    #: Circumradius (centre to vertex) of each hex cutout in mm.
    hex_radius: float = 10.0
    #: Minimum gap between adjacent hex edges in mm.
    spacing: float = 2.5
    #: Fillet radius on top-face hex edges; 0 = no fillet.
    fillet_radius: float = 0.0
    #: Solid border width around the panel perimeter in mm.
    outer_border: float = 4.0


@dataclass
class ColumnParams:
    """Structural column with optional gusset supports."""

    #: Column height along Z in mm.
    height: float = 100.0
    #: Shaft diameter in mm.
    diameter: float = 30.0
    #: Gusset arm length in mm; 0 = no gussets.
    gusset_size: float = 0.0
    #: Gusset plate thickness in mm.
    gusset_thickness: float = 0.0
    #: Gusset placement along Z: "top" or "bottom".
    gusset_position_z: Literal["top", "bottom"] = "top"
    #: Gusset angles around the Z axis in degrees.
    gusset_orientation_xy: Sequence[float] = field(
        default_factory=lambda: (0, 90, 180, 270)
    )


@dataclass
class RoundedBoxParams:
    """Rectangular hollow tube with rounded outer corner edges."""

    #: Outer dimension along X in mm.
    length: float = 100.0
    #: Outer dimension along Y in mm.
    width: float = 10.0
    #: Height along Z in mm.
    height: float = 5.0
    #: Thickness of each wall in mm.
    wall_thickness: float = 3.0
    #: Fillet radius on the outer vertical corner edges in mm.
    corner_radius: float = 5.0
    #: Fillet radius on the top rim edges (inner + outer) in mm.
    top_fillet_radius: float = 10.0
    #: Fillet radius on the bottom rim edges (inner + outer) in mm.
    bottom_fillet_radius: float = 10.0


@dataclass
class CylinderClipParams:
    """Hollow cylindrical snap clip for mounting into a circular bore."""

    #: Diameter of the circular bore in mm.
    bore_diameter: float = 11.0
    #: Insertion depth into the bore in mm.
    body_depth: float = 10.0
    #: Clip wall thickness in mm.
    wall_thickness: float = 1.2
    #: Flange radius extension beyond bore radius in mm.
    flange_overlap: float = 3.0
    #: Flange disc thickness in mm.
    flange_thickness: float = 2.5
    #: Number of snap tabs (and matching slot cuts).
    tab_count: int = 4
    #: Radial protrusion of each tab beyond the bore wall in mm.
    tab_protrusion: float = 0.8
    #: Axial height of each tab wedge in mm.
    tab_length: float = 4.0
    #: Circumferential width of each tab prism in mm.
    tab_width: float = 5.0
    #: Width of each slot cut freeing a spring finger in mm.
    slot_width: float = 1.2
    #: Per-side radial clearance for bore fit in mm.
    clearance: float = 0.2
    #: Cut the +X face flush with the clip body so the flange does not
    #: protrude past the print surface when printed flat.
    flat_bottom: bool = True
    #: Fillet radius on the inner bore arc at the flat cut face in mm;
    #: 0 = no fillet.
    flat_fillet_r: float = 0.5
    #: How far past the inner bore wall the flat cut extends (mm),
    #: exposing the bore arc so it can be filleted.
    flat_inner_margin: float = 0.3


@dataclass
class TableParams:
    """Table assembly: hex-panel top with columns at specified positions."""

    top: HexPanelParams = field(default_factory=HexPanelParams)
    column: ColumnParams = field(default_factory=ColumnParams)
    column_positions: list[tuple[float, float]] = field(
        default_factory=lambda: [
            (0, 0),
            (100, 0),
            (0, 100),
            (100, 100),
        ]
    )
