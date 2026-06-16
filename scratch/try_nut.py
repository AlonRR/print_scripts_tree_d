# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

# ruff: noqa

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F401, F403

# Force fresh code on every run. %autoreload reliably misses an operation
# *reorder inside a function* (exactly the kind of edit make_screw_part got),
# which silently leaves the kernel running stale geometry. This guarantees
# the cells below build the current source.
reload_pkg()


# %% [Internal thread — nut (threaded bore, no external ridge)]
# internal_thread=True subtracts the thread valley from solid stock, then
# bores the minor diameter. The bore wall carries the helical thread; the
# outer wall stays a plain cylinder. Sized here to receive the d16 / pitch 2.5
# bolt from try_screw_part.py.
nut = preview(
    shapes.make_screw_part,
    params.ScrewPartParams(
        outer_diameter=26,
        thickness=14,
        thread_pitch=2.5,
        bore_diameter=16,
        thread_angle=60,
        internal_thread=True,
    ),
)
print("nut:     volume %.1f mm^3" % nut.volume)


# %% [PROOF watertight — save_stl asserts a closed, positive-volume mesh]
save_stl(nut, models / "screw_part_nut.stl")
print("nut exported watertight OK")
