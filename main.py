import logging
from pathlib import Path
from typing import cast

import build123d as bd
from build123d import Compound, Cone, Cylinder, Pos, Rot, ShapeList

from print_scripts_tree_d.export import save_stl
from print_scripts_tree_d.params import (
    CylinderClipParams,
    RoundedBoxParams,
    TableParams,
)
from print_scripts_tree_d.shapes import (
    make_column,
    make_cylinder_clip,
    make_hexagonal_mesh,
    make_rounded_box,
    make_table,
)


def _as_compound(result: object) -> Compound:
    if isinstance(result, ShapeList):
        return Compound(children=list(result))
    return cast(Compound, result)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    models = Path("models")
    models.mkdir(exist_ok=True)

    # Rounded box
    bp = RoundedBoxParams()
    box = make_rounded_box(
        length=bp.length,
        width=bp.width,
        height=bp.height,
        wall_thickness=bp.wall_thickness,
        corner_radius=bp.corner_radius,
        top_fillet_radius=0.8,
        bottom_fillet_radius=0.5,
    )
    save_stl(box, models / "rounded_box.stl")

    # Table with hex-panel top and columns
    tp = TableParams()
    col_r = tp.column.diameter / 2
    col_body = Cylinder(col_r, tp.column.height)
    col_foot = Cone(
        bottom_radius=col_r * 0.67,
        top_radius=col_r,
        height=tp.column.diameter,
    )
    column = make_column(
        body=col_body,
        height=tp.column.height,
        foot=col_foot,
        diameter=tp.column.diameter,
        gusset_size=tp.column.gusset_size,
        gusset_thickness=tp.column.gusset_thickness,
        gusset_position_z=tp.column.gusset_position_z,
        gusset_orientation_xy=tp.column.gusset_orientation_xy,
    )
    hp = tp.top
    table_top = make_hexagonal_mesh(
        length=hp.length,
        width=hp.width,
        thickness=hp.thickness,
        hex_radius=hp.hex_radius,
        spacing=hp.spacing,
        outer_border=hp.outer_border,
    )
    table = make_table(
        table_top=table_top,
        columns=[column.rotate(angle=180, axis=bd.Axis.X)],
        column_positions=tp.column_positions,
    )
    save_stl(table, models / "table.stl")

    # Box with cylinder snap clip
    cp = CylinderClipParams()
    bp_clip = RoundedBoxParams(
        length=90.0,
        width=15.0,
        height=6.0,
        wall_thickness=4.0,
        corner_radius=2.5,
        top_fillet_radius=5.0,
        bottom_fillet_radius=1.0,
    )
    clip_box = make_rounded_box(
        length=bp_clip.length,
        width=bp_clip.width,
        height=bp_clip.height,
        wall_thickness=bp_clip.wall_thickness,
        corner_radius=bp_clip.corner_radius,
        top_fillet_radius=bp_clip.top_fillet_radius,
        bottom_fillet_radius=bp_clip.bottom_fillet_radius,
    )
    clip = make_cylinder_clip(
        bore_diameter=cp.bore_diameter,
        body_depth=cp.body_depth,
        wall_thickness=cp.wall_thickness,
        flange_overlap=cp.flange_overlap,
        flange_thickness=cp.flange_thickness,
        tab_count=cp.tab_count,
        tab_protrusion=cp.tab_protrusion,
        tab_length=cp.tab_length,
        tab_width=cp.tab_width,
        slot_width=cp.slot_width,
        clearance=cp.clearance,
        flat_bottom=cp.flat_bottom,
        flat_fillet_r=cp.flat_fillet_r,
        flat_inner_margin=cp.flat_inner_margin,
    )
    tx = bp_clip.length / 2 + cp.body_depth / 2
    clip_rotated = Rot(0, 90, 0) * clip
    flat_bottom_z = clip_rotated.bounding_box().min.Z
    z_offset = -flat_bottom_z - bp_clip.height / 2
    clip_at_end = Pos(tx, 0, z_offset) * clip_rotated
    assembly = _as_compound(clip_box + clip_at_end)
    assembly = _as_compound(Pos(0, 0, bp_clip.height / 2) * assembly)
    save_stl(assembly, models / "box_with_clip.stl")


if __name__ == "__main__":
    main()
