import logging
from pathlib import Path

from build123d import Cone, Cylinder, export_stl

import print_scripts_tree_d.shapes as shapes


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    models = Path("models")
    models.mkdir(exist_ok=True)

    col_body = Cylinder(20, 100)
    col_foot = Cone(bottom_radius=0.5, top_radius=30, height=10)
    column = shapes.make_column(
        body=col_body,
        height=100,
        foot=col_foot,
        diameter=30,
    )
    table_top = shapes.make_hexagonal_mesh(
        length=200,
        width=200,
        thickness=2.5,
        hex_radius=10,
        spacing=2.5,
        outer_border=4,
    )
    table = shapes.make_table(
        table_top=table_top,
        columns=[column] * 4,
        column_positions=[(0, 0), (100, 0), (0, 100), (100, 100)],
    )
    export_stl(table, str(models / "table.stl"))


if __name__ == "__main__":
    main()
