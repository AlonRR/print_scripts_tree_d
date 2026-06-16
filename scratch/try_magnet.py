# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F403

reload_pkg()

# %% [Magnet — plain cylinder (no params dataclass; pass args directly)]
magnet = preview(
    shapes.make_magnet,
    outer_diameter=6.0,
    thickness=3.0,
)

# %% [Export]
save_stl(magnet, models / "magnet.stl")
