# print_scripts_tree_d

Parametric 3D-printable shape library in Python using [build123d](https://github.com/gumyr/build123d) / OpenCASCADE.
All dimensions are in millimetres. All exported shapes are validated as watertight before saving.

## Shapes

| Function | Module | Description |
|---|---|---|
| `make_rounded_box` | `boxes.py` | Hollow rectangular tube with rounded corner edges and rim fillets |
| `make_cylinder_clip` | `clips.py` | Hollow snap-fit cylinder clip for mounting into a circular bore |
| `make_hexagonal_mesh` | `panels.py` | Rectangular panel with a honeycomb hex cutout pattern |
| `make_magnet_ring_panel` | `panels.py` | Rounded-corner prism with central cone bore, magnet pockets, and concave walls |
| `make_column` | `furniture.py` | Structural column with optional gusset supports |
| `make_table` | `furniture.py` | Hex-panel tabletop assembled with columns at specified positions |
| `make_washer` | `primitives.py` | Flat annular disc (washer) |
| `make_magnet` | `primitives.py` | Cylindrical magnet placeholder |
| `make_screw_part` | `primitives.py` | Threaded rod or nut with configurable pitch, angle, bore, and lead-in |

## Quick start

```bash
uv sync                    # install dependencies
uv run python main.py      # build and export all demo models to models/
uv run pytest              # run the test suite
```

## Interactive iteration

Open `sandbox.ipynb` in VS Code (with the OCP Viewer extension on port 3939) for
multi-shape assembly work, or copy `scratch/template.py` for single-shape iteration
with `%autoreload 2` hot-reload and VS Code Interactive (`# %%` cells).

## Development

See [CLAUDE.md](CLAUDE.md) for architecture, conventions, and build123d API rules.
