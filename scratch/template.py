# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F403

# %% [Shape]
shape = preview(
    shapes.make_SHAPENAME,
    params.SHAPENAMEParams(),
    # override individual params here:
    # outer_diameter=30,
)

# %% [Export]
save_stl(shape, models / "SHAPENAME.stl")
