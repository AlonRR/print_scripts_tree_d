from print_scripts_tree_d.shapes import make_box, make_cylinder


def test_make_box() -> None:
    shape = make_box(10, 20, 30)
    assert shape is not None
    assert shape.volume > 0


def test_make_cylinder() -> None:
    shape = make_cylinder(5, 15)
    assert shape is not None
    assert shape.volume > 0
