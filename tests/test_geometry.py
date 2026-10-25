from local_agent.focus.geometry import bbox_area, bbox_iou, find_focused, point_in_bbox


def test_brief_example():
    assert point_in_bbox(400, 225, (300, 200, 500, 250))


def test_inside_edge_outside():
    b = (10, 10, 20, 20)
    assert point_in_bbox(15, 15, b)
    assert point_in_bbox(10, 10, b) and point_in_bbox(20, 20, b)
    assert not point_in_bbox(21, 15, b)
    assert not point_in_bbox(15, 9, b)


def test_padding():
    b = (10, 10, 20, 20)
    assert not point_in_bbox(22, 15, b)
    assert point_in_bbox(22, 15, b, padding=2)
    assert not point_in_bbox(23, 15, b, padding=2)


def test_smallest_box_wins_on_overlap():
    boxes = [(0, 0, 100, 100), (40, 40, 60, 60)]
    assert find_focused((50, 50), boxes) == 1
    assert find_focused((10, 10), boxes) == 0


def test_none_and_miss():
    assert find_focused(None, [(0, 0, 5, 5)]) is None
    assert find_focused((50, 50), [(0, 0, 5, 5)]) is None
    assert find_focused((1, 1), []) is None


def test_iou():
    assert bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert abs(bbox_iou((0, 0, 10, 10), (5, 0, 15, 10)) - 50 / 150) < 1e-9
    assert bbox_area((5, 5, 1, 1)) == 0
