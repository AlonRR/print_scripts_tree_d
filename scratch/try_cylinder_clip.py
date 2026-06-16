# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F403

reload_pkg()

# %% [Cylinder snap clip — mounts into a circular bore]
clip = preview(
    shapes.make_cylinder_clip,
    params.CylinderClipParams(),
)

# %% [Export]
save_stl(clip, models / "cylinder_clip.stl")
