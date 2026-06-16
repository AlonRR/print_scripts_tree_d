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


# %% [External thread — solid bolt with flat crest + lead-in chamfer]
# Headline case: uniform helical thread with a flat-cut crest and a tapered
# lead-in at the insertion tip. Watch the axial cross-section — every turn is
# identical (Frenet sweep) and the crest is flat, not pointed.
bolt = preview(
    shapes.make_screw_part,
    params.ScrewPartParams(
        outer_diameter=16,
        thickness=30,
        thread_pitch=2.5,
        thread_angle=60,
        lead_in_length=4,
        internal_thread=False,
        bore_diameter=12, 
    ),
)
print("bolt:    volume %.1f mm^3" % bolt.volume)


# %% [PROOF watertight — save_stl asserts a closed, positive-volume mesh]
save_stl(bolt, models / "screw_part_bolt.stl")