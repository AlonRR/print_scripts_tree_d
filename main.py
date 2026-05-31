import logging
from pathlib import Path

from build123d import Cone, Cylinder

from print_scripts_tree_d.export import save_stl
from print_scripts_tree_d.params import ColumnParams, HexPanelParams, TableParams
from print_scripts_tree_d.shapes import make_column, make_hexagonal_mesh, make_table


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    models = Path("models")
    models.mkdir(exist_ok=True)

    p = TableParams(
        top=HexPanelParams(
            length=200, width=200, thickness=2.5, hex_radius=10, spacing=2.5, outer_border=4
        ),
        column=ColumnParams(height=100, diameter=30),
    )

    column = make_column(
        body=Cylinder(20, 100),
        height=p.column.height,
        foot=Cone(bottom_radius=0.5, top_radius=30, height=10),
        diameter=p.column.diameter,
    )
    table_top = make_hexagonal_mesh(
        length=p.top.length,
        width=p.top.width,
        thickness=p.top.thickness,
        hex_radius=p.top.hex_radius,
        spacing=p.top.spacing,
        outer_border=p.top.outer_border,
    )
    table = make_table(
        table_top=table_top,
        columns=[column] * len(p.column_positions),
        column_positions=p.column_positions,
    )

    save_stl(table, models / "table.stl")


if __name__ == "__main__":
    main()
