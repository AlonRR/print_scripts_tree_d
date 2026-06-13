import math

import pytest
from build123d import Box, Cylinder

from print_scripts_tree_d.shapes import (
    make_column,
    make_hexagonal_mesh,
    make_magnet_ring_panel,
    make_table,
    make_washer,
)

# --- make_washer ---


def test_make_washer_volume() -> None:
    outer, hole, thickness = 20.0, 10.0, 5.0
    washer = make_washer(outer, hole, thickness)
    expected = math.pi * thickness * ((outer / 2) ** 2 - (hole / 2) ** 2)
    assert abs(washer.volume - expected) < 1.0  # within 1 mm³


def test_make_washer_invalid_raises() -> None:
    with pytest.raises(ValueError):
        make_washer(outer_diameter=10.0, hole_diameter=10.0, thickness=2.0)
    with pytest.raises(ValueError):
        make_washer(outer_diameter=10.0, hole_diameter=15.0, thickness=2.0)


# --- make_hexagonal_mesh ---


def test_make_hexagonal_mesh_has_cutouts() -> None:
    panel = make_hexagonal_mesh(
        length=30, width=30, thickness=3, hex_radius=2, spacing=1
    )
    solid_volume = 30 * 30 * 3
    assert panel.volume < solid_volume


def test_make_hexagonal_mesh_with_border() -> None:
    # Border should add material back along the perimeter, so volume with
    # border > without.
    without = make_hexagonal_mesh(
        length=30, width=30, thickness=3, hex_radius=2, spacing=1
    )
    with_border = make_hexagonal_mesh(
        length=30,
        width=30,
        thickness=3,
        hex_radius=2,
        spacing=1,
        outer_border=3,
    )
    assert with_border.volume > without.volume


# --- make_magnet_ring_panel ---


def test_make_magnet_ring_panel_has_bore_and_pockets() -> None:
    panel = make_magnet_ring_panel(
        outer_diameter=60,
        thickness=4,
        bore_diameter=12,
        magnet_diameter=6,
        magnet_thickness=3,
        number_of_magnets=6,
    )
    solid_volume = math.pi * (60 / 2) ** 2 * 4
    assert panel.volume < solid_volume
    assert panel.bounding_box().size.X <= 61


def test_make_magnet_ring_panel_invalid_count_raises() -> None:
    with pytest.raises(ValueError):
        make_magnet_ring_panel(
            outer_diameter=60,
            thickness=4,
            bore_diameter=12,
            magnet_diameter=6,
            magnet_thickness=3,
            number_of_magnets=0,
        )


# --- make_table ---


def test_make_table_bottom_at_z0() -> None:
    top = Box(40, 40, 4)
    col = Cylinder(3, 20)
    table = make_table(top, [col], [(50, 50)])
    bb = table.bounding_box()
    assert abs(bb.min.Z) < 0.1


def test_make_table_column_too_large_raises() -> None:
    top = Box(10, 10, 2)
    col = Cylinder(6, 20)  # diameter 12 > tabletop 10
    with pytest.raises(ValueError):
        make_table(top, [col], [(50, 50)])


# --- make_column ---


def test_make_column_height() -> None:
    body = Cylinder(5, 30)
    foot = Cylinder(8, 10)
    col = make_column(body=body, height=40, foot=foot, diameter=None)
    bb_z = col.bounding_box().size.Z
    assert abs(bb_z - 40) < 0.5


def test_make_column_gusset_warning(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    body = Cylinder(5, 30)
    foot = Cylinder(8, 10)
    with caplog.at_level(logging.WARNING):
        make_column(
            body=body,
            height=40,
            foot=foot,
            diameter=None,
            gusset_size=5,
            gusset_thickness=0,
        )
    assert any("gusset" in r.message.lower() for r in caplog.records)
