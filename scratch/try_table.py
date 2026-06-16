# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F403

reload_pkg()

# %% [Table — hex-panel top on columns; assembled from Parts]
# make_table takes a built top Part and a list of column Parts. A smaller hex
# top than the 200x200 default keeps the preview quick.
tp = params.TableParams(
    top=params.HexPanelParams(
        length=80.0,
        width=80.0,
        thickness=3.0,
        hex_radius=8.0,
        spacing=3.0,
        outer_border=5.0,
    ),
)

col_r = tp.column.diameter / 2
col_body = Cylinder(col_r, tp.column.height)
col_foot = Cone(
    bottom_radius=col_r * 0.67, top_radius=col_r, height=tp.column.diameter
)
column = shapes.make_column(
    body=col_body,
    height=tp.column.height,
    foot=col_foot,
    diameter=tp.column.diameter,
)

table_top = shapes.make_hexagonal_mesh(
    length=tp.top.length,
    width=tp.top.width,
    thickness=tp.top.thickness,
    hex_radius=tp.top.hex_radius,
    spacing=tp.top.spacing,
    outer_border=tp.top.outer_border,
)

table = shapes.make_table(
    table_top=table_top,
    columns=[column.rotate(angle=180, axis=bd.Axis.X)],
    column_positions=tp.column_positions,
)
reset_show()
show(table)

# %% [Export]
save_stl(table, models / "table.stl")
