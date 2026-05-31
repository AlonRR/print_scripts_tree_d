from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class HexPanelParams:
    length: float = 200.0
    width: float = 200.0
    thickness: float = 2.5
    hex_radius: float = 10.0
    spacing: float = 2.5
    fillet_radius: float = 0.0
    outer_border: float = 4.0


@dataclass
class ColumnParams:
    height: float = 100.0
    diameter: float = 30.0
    gusset_size: float = 0.0
    gusset_thickness: float = 0.0
    gusset_position_z: str = "top"
    gusset_orientation_xy: Sequence[float] = field(default_factory=lambda: (0, 90, 180, 270))


@dataclass
class TableParams:
    top: HexPanelParams = field(default_factory=HexPanelParams)
    column: ColumnParams = field(default_factory=ColumnParams)
    column_positions: list[tuple[float, float]] = field(
        default_factory=lambda: [(0, 0), (100, 0), (0, 100), (100, 100)]
    )
