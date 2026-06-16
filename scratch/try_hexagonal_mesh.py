# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F403

reload_pkg()

# %% [Hexagonal mesh panel — honeycomb cutout pattern]
# Smaller than the 200x200 default so the preview builds quickly.
mesh = preview(
    shapes.make_hexagonal_mesh,
    params.HexPanelParams(
        length=60.0,
        width=60.0,
        thickness=2.5,
        hex_radius=6.0,
        spacing=2.0,
        outer_border=4.0,
    ),
)

# %% [Export]
save_stl(mesh, models / "hexagonal_mesh.stl")
