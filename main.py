import logging
from pathlib import Path

from build123d import Cone, export_stl

import print_scripts_tree_d.shapes as shapes


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    models = Path("models")
    models.mkdir(exist_ok=True)

    table_leg_body = shapes.make_cylinder(20, 100)
    table_leg_foot = Cone(bottom_radius=0.5, top_radius=30, height=10)
    table_leg = shapes.make_leg(
        leg_body=table_leg_body,
        leg_height=100,
        leg_foot=table_leg_foot,
        leg_diameter=30,
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
        legs=[table_leg] * 4,
        leg_height=100,
        leg_positions=[(0, 0), (100, 0), (0, 100), (100, 100)],
    )
    export_stl(table, str(models / "table.stl"))


if __name__ == "__main__":
    main()
