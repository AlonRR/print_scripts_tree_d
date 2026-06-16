# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F403

reload_pkg()

# %% [Rounded box — hollow tube with rounded corners and rims]
box = preview(
    shapes.make_rounded_box,
    params.RoundedBoxParams(
        length=90.0,
        width=15.0,
        height=6.0,
        wall_thickness=4.0,
        corner_radius=2.5,
        top_fillet_radius=5.0,
        bottom_fillet_radius=1.0,
    ),
)

# %% [Export]
save_stl(box, models / "rounded_box.stl")
