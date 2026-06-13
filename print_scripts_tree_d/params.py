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
class WasherParams:
    """Parameters for a flat washer (annular disc)."""

    #: Overall diameter of the washer in mm.
    outer_diameter: float = 20.0
    #: Diameter of the central hole in mm. Must be less than outer_diameter.
    hole_diameter: float = 10.0
    #: Thickness of the washer along the Z axis in mm.
    thickness: float = 5.0


@dataclass
class MagnetRingPanelParams:
    """Circular panel with a central bore and evenly spaced magnet pockets."""

    #: Overall diameter of the panel in mm.
    outer_diameter: float = 60.0
    #: Panel thickness along Z in mm.
    thickness: float = 4.0
    #: Diameter of the central bore hole in mm.
    bore_diameter: float = 12.0
    #: Diameter of each magnet pocket in mm.
    magnet_diameter: float = 6.0
    #: Pocket depth for each magnet in mm.
    magnet_thickness: float = 3.0
    #: Number of magnet pockets arranged around the bore.
    number_of_magnets: int = 6
    #: Radial clearance per side for each magnet pocket in mm.
    clearance: float = 0.2
    #: Extra radial margin between the bore, magnet ring, and outer edge in mm.
    ring_margin: float = 0.5
    #: Fraction in [0, 1) by which the walls between corners curve inward.
    wall_concavity: float = 0.35
    #: Bore diameter at the top face in mm; 0 keeps a straight cylindrical
    #: bore, otherwise the bore is a cone from bore_diameter to this.
    bore_top_diameter: float = 0.0
    #: Rounding radius for the bore mouth at the top/bottom faces in mm.
    bore_fillet_radius: float = 0.0
    #: Rounding radius for the outer top/bottom perimeter in mm. Capped at
    #: (thickness - magnet_thickness) / 2.
    outer_fillet_radius: float = 0.0
    #: Small edge-break radius in mm at the magnet slot floor/ceiling. Kept
    #: small so the slot floor and ceiling stay flat for the flat-faced magnet.
    pocket_fillet_radius: float = 0.3
    #: Radial length in mm of a small obround slit cut into the top face above each magnet.
    top_slot_length: float = 2.0
    #: Tangential width in mm of that obround top slit.
    top_slot_width: float = 1.0


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
    #: Fillet radius on the concave bore-floor corner (bore wall meets the
    #: flange cap) in mm; 0 = no fillet. Only applies when the flange is
    #: included.
    bore_floor_fillet_r: float = 1.0


@dataclass
class TableParams:
    """Table assembly: hex-panel top with columns at specified positions."""

    #: Tabletop panel parameters.
    top: HexPanelParams = field(default_factory=HexPanelParams)
    #: Column shape parameters shared by all columns.
    column: ColumnParams = field(default_factory=ColumnParams)
    #: Column placement as (x, y) percentages (0–100 per axis).
    column_positions: list[tuple[float, float]] = field(
        default_factory=lambda: [
            (0, 0),
            (100, 0),
            (0, 100),
            (100, 100),
        ]
    )
