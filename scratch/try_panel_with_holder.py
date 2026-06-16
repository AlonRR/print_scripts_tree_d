# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

# ruff: noqa

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F401, F403

reload_pkg()


# %% [Threaded holder for the panel]
# Single watertight solid: smooth shank bottom, externally threaded top.
# Thread profile set from the measured screw: major 13.2, minor 11.48
# (-> depth 0.86), pitch 1.24, crest flat 0.76, root flat 0.4 — a near-square
# trapezoidal thread. depth/crest/root override the V-angle.
holder = shapes.make_threaded_rod(
    outer_diameter=13.2,      # major (crest) diameter
    thickness=16.4,
    smooth_length=8.2,
    thread_pitch=1.27,        # crest-to-crest
    bore_diameter=8,
    thread_depth=0.8,
    thread_crest_width=0.3,   # flat at the crest
    # thread_root_width=0.3,    # flat at the root
    lead_in_length=1.5,       # chamfered start at the threaded tip
    runout_length=2.0,        # thread fades out into the shank
    thread_angle=45,          # V-angle of the thread
)
show(holder)

# %% [Magnet panel WITH the holder fused in — one watertight solid]
# make_magnet_ring_panel now mounts a pre-built holder on the bore axis (like
# make_table takes its columns), adds a curved cove where the smooth shank meets
# the top face (holder_base_fillet_radius), and extends the magnet-release slots
# up into the holder (release_cut_into_holder) so magnets can still be pushed
# out from above. This replaces the old imported screw_attachmentobj.obj.
panel = preview(
    shapes.make_magnet_ring_panel,
    params.MagnetRingPanelParams(
        outer_diameter=24,
        thickness=4,
        bore_diameter=3,
        bore_top_diameter=8,
        magnet_diameter=6,
        magnet_thickness=2.5,
        number_of_magnets=3,
        ring_margin=3,
        wall_concavity=0.4,
        bore_fillet_radius=0.6,
        outer_fillet_radius=0.7,
        pocket_fillet_radius=0.3,
        clearance=0,
        top_slot_length=4.0,
        top_slot_width=2.0,
        holder_base_fillet_radius=2.5,  # curved cove up the smooth shank
        release_cut_into_holder=5.0,    # magnet-release slots cut 3 mm into it
    ),
    holder=holder,  # passed through preview() straight to the function
)
bb = panel.bounding_box()
print("panel + holder: height %.1f mm, solids %d" % (bb.size.Z, len(panel.solids())))


# %% [PROOF watertight — single closed, positive-volume solid]
save_stl(panel, models / "magnet_panel_with_holder.stl")
print("panel + holder exported watertight OK, volume %.1f mm^3" % panel.volume)
