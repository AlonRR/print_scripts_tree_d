import math
from pathlib import Path

import pytest
from build123d import Box, Cylinder

from print_scripts_tree_d.export import save_stl
from print_scripts_tree_d.shapes import (
    ThreadProfile,
    make_column,
    make_hexagonal_mesh,
    make_magnet_ring_panel,
    make_screw_part,
    make_table,
    make_threaded_rod,
    make_washer,
)

# --- make_screw_part ---


def test_make_screw_part_smooth_cylinder() -> None:
    s = make_screw_part(outer_diameter=8.0, thickness=10.0)
    expected = math.pi * (4.0**2) * 10.0
    assert abs(s.volume - expected) < 2.0


def test_make_screw_part_threaded_less_than_solid() -> None:
    solid = make_screw_part(outer_diameter=8.0, thickness=20.0)
    threaded = make_screw_part(outer_diameter=8.0, thickness=20.0, thread_pitch=2.0)
    # The thread must actually cut material — but not gut the shaft. Bounds
    # guard against the OCC failure mode where the groove silently fails and
    # the shaft is left smooth (threaded.volume == solid.volume) or empty.
    assert 0.5 * solid.volume < threaded.volume < 0.98 * solid.volume


def test_make_screw_part_threaded_robust_across_turn_counts() -> None:
    # OCC's helical sweep-subtract fails for specific turn counts
    # (thickness / pitch); make_screw_part must still cut a real thread.
    # These (thickness, pitch) pairs previously produced a smooth shaft.
    for thickness, pitch in [(10.0, 3.0), (15.0, 2.0), (20.0, 1.5)]:
        solid = make_screw_part(outer_diameter=12.0, thickness=thickness)
        threaded = make_screw_part(
            outer_diameter=12.0, thickness=thickness, thread_pitch=pitch
        )
        removed = solid.volume - threaded.volume
        assert removed > 0.02 * solid.volume, (
            f"no thread cut for thickness={thickness}, pitch={pitch}"
        )


def test_make_screw_part_hollow_less_than_solid() -> None:
    solid = make_screw_part(outer_diameter=8.0, thickness=20.0)
    hollow = make_screw_part(outer_diameter=8.0, thickness=20.0, bore_diameter=3.0)
    assert hollow.volume < solid.volume


def test_make_screw_part_internal_thread() -> None:
    nut = make_screw_part(
        outer_diameter=12.0,
        thickness=8.0,
        bore_diameter=5.0,
        thread_pitch=1.0,
        internal_thread=True,
    )
    solid_tube = math.pi * (6.0**2 - 2.5**2) * 8.0
    assert nut.volume < solid_tube  # grooves remove material


def test_make_screw_part_lead_in_less_than_no_lead_in() -> None:
    plain = make_screw_part(outer_diameter=8.0, thickness=20.0, thread_pitch=1.5)
    with_chamfer = make_screw_part(
        outer_diameter=8.0, thickness=20.0, thread_pitch=1.5, lead_in_length=3.0
    )
    assert with_chamfer.volume < plain.volume


def test_make_screw_part_thread_angle_affects_volume() -> None:
    narrow = make_screw_part(
        outer_diameter=8.0, thickness=20.0, thread_pitch=2.0, thread_angle=30.0
    )
    wide = make_screw_part(
        outer_diameter=8.0, thickness=20.0, thread_pitch=2.0, thread_angle=90.0
    )
    assert narrow.volume != wide.volume


def test_make_screw_part_invalid_raises() -> None:
    with pytest.raises(ValueError):
        make_screw_part(outer_diameter=0.0, thickness=10.0)
    with pytest.raises(ValueError):
        make_screw_part(outer_diameter=8.0, thickness=10.0, bore_diameter=8.0)
    with pytest.raises(ValueError):
        make_screw_part(outer_diameter=8.0, thickness=10.0, thread_angle=0.0)
    with pytest.raises(ValueError):
        make_screw_part(
            outer_diameter=8.0, thickness=10.0, internal_thread=True, bore_diameter=0.0
        )


# --- make_threaded_rod ---


def test_make_threaded_rod_watertight_and_partly_threaded(
    tmp_path: Path,
) -> None:
    rod = make_threaded_rod(
        outer_diameter=14.0,
        thickness=16.0,
        smooth_length=8.0,
        thread_pitch=2.0,
        bore_diameter=8.5,
    )
    # The single-solid construction must export as a closed, positive-volume
    # mesh (save_stl asserts watertight) — that is the whole point of the
    # collar-burying approach over a two-body assembly.
    save_stl(rod, tmp_path / "rod.stl")
    bb = rod.bounding_box()
    assert abs(bb.size.Z - 16.0) < 0.2
    assert 14.0 <= bb.size.X < 14.5  # ~ outer diameter (collar 1e-3 proud)
    # The threaded upper half cuts valleys, so the rod is lighter than a full-
    # diameter bored tube of the same length, but keeps most of its material.
    full_bored_tube = math.pi * (7.0**2 - 4.25**2) * 16.0
    assert 0.6 * full_bored_tube < rod.volume < full_bored_tube


def test_make_threaded_rod_tapers_watertight(tmp_path: Path) -> None:
    # A lead-in chamfer and a run-out cone both cut across the helical thread,
    # which OCC can tessellate non-watertight at some pitches; make_threaded_rod
    # must nudge the pitch to return a watertight single solid anyway.
    rod = make_threaded_rod(
        outer_diameter=13.2,
        thickness=16.4,
        smooth_length=8.2,
        thread_pitch=1.24,
        bore_diameter=8,
        thread_depth=0.8,
        thread_crest_width=0.7,
        thread_root_width=0.3,
        lead_in_length=1.5,
        runout_length=2.0,
    )
    save_stl(rod, tmp_path / "rod_taper.stl")
    assert len(rod.solids()) == 1


def test_thread_profile_matches_equivalent_args() -> None:
    # A ThreadProfile produces the same geometry as the equivalent thread_*
    # arguments — it is the conflict-proof way to pass the same spec.
    by_args = make_screw_part(
        outer_diameter=14.0,
        thickness=12.0,
        thread_pitch=2.0,
        thread_depth=1.0,
        thread_crest_width=0.9,
        thread_root_width=0.7,
    )
    by_profile = make_screw_part(
        outer_diameter=14.0,
        thickness=12.0,
        thread=ThreadProfile.trapezoidal(
            pitch=2.0, depth=1.0, crest_width=0.9, root_width=0.7
        ),
    )
    assert abs(by_args.volume - by_profile.volume) < 1.0

    v_args = make_screw_part(
        outer_diameter=12.0, thickness=12.0, thread_pitch=2.0, thread_angle=55.0
    )
    v_profile = make_screw_part(
        outer_diameter=12.0,
        thickness=12.0,
        thread=ThreadProfile.v_thread(pitch=2.0, angle=55.0),
    )
    assert abs(v_args.volume - v_profile.volume) < 1.0


def test_make_threaded_rod_invalid_raises() -> None:
    with pytest.raises(ValueError):  # smooth_length >= thickness
        make_threaded_rod(
            outer_diameter=14.0,
            thickness=16.0,
            smooth_length=16.0,
            thread_pitch=2.0,
        )
    with pytest.raises(ValueError):  # no thread
        make_threaded_rod(
            outer_diameter=14.0,
            thickness=16.0,
            smooth_length=8.0,
            thread_pitch=0.0,
        )
    with pytest.raises(ValueError):  # bore >= outer
        make_threaded_rod(
            outer_diameter=14.0,
            thickness=16.0,
            smooth_length=8.0,
            thread_pitch=2.0,
            bore_diameter=14.0,
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


def test_make_magnet_ring_panel_with_holder(tmp_path: Path) -> None:
    holder = make_threaded_rod(
        outer_diameter=14.0,
        thickness=16.4,
        smooth_length=8.2,
        thread_pitch=2.0,
        bore_diameter=8.5,
    )
    panel = make_magnet_ring_panel(
        outer_diameter=30,
        thickness=4,
        bore_diameter=3,
        bore_top_diameter=8,
        magnet_diameter=6,
        magnet_thickness=2.5,
        number_of_magnets=3,
        ring_margin=3,
        top_slot_length=4,
        top_slot_width=2,
        holder=holder,
        holder_base_fillet_radius=2.0,
        release_cut_into_holder=3.0,
    )
    # The holder fuses into one watertight solid that is taller than the panel.
    save_stl(panel, tmp_path / "panel_holder.stl")
    assert len(panel.solids()) == 1
    assert panel.bounding_box().size.Z > 4 + 12.0


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
