# %% [Setup — run once per session]
# In VS Code: right-click → "Run Current Cell" or Shift+Enter on this cell.
# %autoreload 2

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dev import *  # noqa: F403

# %% [Magnet ring panel]
magnet_panel = preview(
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
    ),
)

# %% [Export]
save_stl(magnet_panel, models / "magnet_ring_panel.stl")

# %% [Attach OBJ holder]
import tempfile  # noqa: E402

import numpy as np  # noqa: E402
import trimesh  # noqa: E402


def cylinder_axis_xy(
    mesh: trimesh.Trimesh, lo: float = 0.2, hi: float = 0.8, n: int = 9
) -> tuple[float, float]:
    """Median least-squares circle fit over body slices — robust cylinder axis."""
    bb = mesh.bounds
    zmin, zmax = bb[0][2], bb[1][2]
    centers: list[tuple[float, float]] = []
    for f in np.linspace(lo, hi, n):
        sec = mesh.section(
            plane_origin=[0, 0, zmin + f * (zmax - zmin)],
            plane_normal=[0, 0, 1],
        )
        if sec is None:
            continue
        x, y = sec.vertices[:, 0], sec.vertices[:, 1]
        a = np.c_[2 * x, 2 * y, np.ones(len(x))]
        cx, cy, _ = np.linalg.lstsq(a, x * x + y * y, rcond=None)[0]
        centers.append((float(cx), float(cy)))
    arr = np.array(centers)
    return float(np.median(arr[:, 0])), float(np.median(arr[:, 1]))


def to_build123d(mesh: trimesh.Trimesh) -> bd.Shape:
    """Convert a trimesh mesh to a build123d shape via a temp STL."""
    tmp = Path(tempfile.gettempdir()) / "imported_mesh.stl"
    mesh.export(tmp)
    return bd.import_stl(str(tmp))


raw_holder = trimesh.load(str(models / "screw_attachmentobj.obj"), force="mesh")
axis_x, axis_y = cylinder_axis_xy(raw_holder)
nudge_xy = (0.02, -0.14)
holder = to_build123d(raw_holder)
holder_on_panel = (
    Pos(
        -axis_x + nudge_xy[0],
        -axis_y + nudge_xy[1],
        magnet_panel.bounding_box().max.Z - holder.bounding_box().min.Z,
    )
    * holder
)

reset_show()
show(
    magnet_panel,
    holder_on_panel,
    names=["magnet panel", "ptfe holder"],
    colors=["lightgray", "steelblue"],
)

# %% [Export assembly]
assembly = Compound(children=[magnet_panel, holder_on_panel])
export_stl(assembly, str(models / "magnet_panel_with_holder.stl"))
