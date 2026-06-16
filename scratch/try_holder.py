# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

# ruff: noqa

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F401, F403

reload_pkg()


# %% [Threaded holder — smooth shank bottom, externally threaded top]
# Single watertight solid that replaces the imported screw_attachmentobj.obj.
# make_threaded_rod generates a full-length external thread and buries its lower
# turns under a full-diameter collar, so the bottom smooth_length mm is a plain
# shank and the rest is threaded — all one solid (no two-body assembly).
#
# Defaults match the measured OBJ envelope (OD 14, height 16.4, bore 8.5).
# Set thread_pitch / thread_angle from the mating screw; bore_diameter=0 = solid.
holder = preview(
    shapes.make_threaded_rod,
    params.ThreadedRodParams(
        outer_diameter=14.0,
        thickness=16.4,
        smooth_length=8.2,
        thread_pitch=2.0,
        bore_diameter=8.5,
        thread_angle=60.0,
    ),
)
bb = holder.bounding_box()
print("holder: height %.1f mm, OD %.1f mm" % (bb.size.Z, bb.size.X))


# %% [PROOF watertight — single closed, positive-volume mesh]
save_stl(holder, models / "threaded_holder.stl")
print("holder exported watertight OK, volume %.1f mm^3" % holder.volume)
