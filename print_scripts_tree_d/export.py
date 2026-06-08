import logging
from pathlib import Path

import trimesh
from build123d import Compound, export_stl

_log = logging.getLogger(__name__)


def save_stl(shape: Compound, path: Path | str, validate: bool = True) -> None:
    """Export *shape* to an STL file and optionally verify it is print-ready.

    Args:
        shape: The build123d Compound to export.
        path: Destination file path. Parent directories must exist.
        validate: If True, load the exported mesh with trimesh and assert that
                  it is watertight and has positive volume.

    Raises:
        AssertionError: If validation is enabled and the mesh fails either check.
    """
    path = Path(path)
    export_stl(shape, str(path))
    _log.info("Exported %s", path)

    if not validate:
        return

    loaded = trimesh.load(str(path))
    if isinstance(loaded, trimesh.Scene):
        mesh = trimesh.util.concatenate(loaded.dump())
    else:
        mesh = loaded
    assert mesh.is_watertight, f"{path.name}: mesh has holes — not print-ready"
    assert mesh.volume > 0, f"{path.name}: mesh has inverted normals (negative volume)"
    _log.info("%s validated — watertight, volume=%.1f mm³", path.name, mesh.volume)
