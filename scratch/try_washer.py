# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *

reload_pkg()

# %% [Washer — flat annular disc]
washer = preview(
    shapes.make_washer,
    params.WasherParams(),
)

# %% [Export]
save_stl(washer, models / "washer.stl")
