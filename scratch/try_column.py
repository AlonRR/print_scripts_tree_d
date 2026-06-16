# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F403

reload_pkg()

# %% [Column — built from explicit body + foot Parts]
# make_column takes build123d Parts (body, foot), not a params dataclass, so
# build those here; ColumnParams supplies the scalar settings.
cp = params.ColumnParams(
    height=100.0,
    diameter=30.0,
    gusset_size=8.0,
    gusset_thickness=3.0,
    gusset_position_z="top",
)
col_r = cp.diameter / 2
body = Cylinder(col_r, cp.height)
foot = Cone(bottom_radius=col_r * 0.67, top_radius=col_r, height=cp.diameter)

column = shapes.make_column(
    body=body,
    height=cp.height,
    foot=foot,
    diameter=cp.diameter,
    gusset_size=cp.gusset_size,
    gusset_thickness=cp.gusset_thickness,
    gusset_position_z=cp.gusset_position_z,
    gusset_orientation_xy=cp.gusset_orientation_xy,
)
reset_show()
show(column)

# %% [Export]
save_stl(column, models / "column.stl")
