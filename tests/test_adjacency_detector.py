import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.adjacency_detector import (
    _detect_orientation_from_shelftalkers,
    get_required_legs,
    should_waive_shelftalker,
    detect_category_adjacency,
)


def _make_det(product_name, x1, y1, x2, y2):
    return {'product_name': product_name, 'bbox_xyxy': [x1, y1, x2, y2]}


def _make_st(class_name, x1, y1, x2, y2):
    return {'class_name': class_name, 'bbox': [x1, y1, x2, y2]}


ADJACENT_DETS = [
    _make_det("Pond's Face Wash", 0, 0, 100, 200),
    _make_det("Pond's Face Wash", 10, 20, 90, 180),
    _make_det("Dove Shampoo", 110, 0, 210, 200),
    _make_det("Dove Shampoo", 120, 20, 200, 180),
]


# --- Orientation detection ---

def test_vertical_orientation_hair_below_ponds():
    # Haircare (y=300-400) is below ponds (y=100-200) — no y-overlap
    # all_detected includes both brands (no prefix filter)
    dets = [
        _make_st('da_hair_care_st_bottom', 50, 300, 150, 320),
        _make_st('da_ponds_st_bottom',     50, 180, 150, 200),
        _make_st('da_ponds_st_left',       10, 100, 30, 200),
        _make_st('da_ponds_st_right',      170, 100, 190, 200),
    ]
    assert _detect_orientation_from_shelftalkers(dets) == 'vertical'


def test_vertical_orientation_hair_above_ponds():
    # Haircare (y=0-100) is above ponds (y=200-300) — no y-overlap
    dets = [
        _make_st('da_hair_care_st_bottom', 50,  80, 150, 100),
        _make_st('da_ponds_st_top',        50, 200, 150, 220),
    ]
    assert _detect_orientation_from_shelftalkers(dets) == 'vertical'


def test_horizontal_orientation_hair_right_of_ponds():
    # Haircare (y=50-150) and ponds (y=50-150) overlap in y — horizontal
    dets = [
        _make_st('da_hair_care_st_left',  200, 50, 220, 150),
        _make_st('da_ponds_st_right',     180, 50, 200, 150),
    ]
    assert _detect_orientation_from_shelftalkers(dets) == 'horizontal'


def test_horizontal_no_false_positive_from_top_bottom_labels():
    # top+bottom labels both visible but shelftalkers overlap in y (horizontal layout)
    dets = [
        _make_st('da_hair_care_st_top',  200, 50, 250, 80),
        _make_st('da_ponds_st_bottom',   50,  50, 100, 80),
    ]
    assert _detect_orientation_from_shelftalkers(dets) == 'horizontal'


def test_vertical_with_full_height_side_shelftalkers():
    # Real-world case: ponds_st_left/right span full section height (y=280-700),
    # haircare_st_bottom is at y=250-320. y-ranges overlap but centers don't.
    dets = [
        _make_st('da_hair_care_st_bottom', 50, 250, 400, 320),  # center_y=285
        _make_st('da_ponds_st_left',        0, 280,  30, 700),  # center_y=490
        _make_st('da_ponds_st_right',      610, 280, 640, 700), # center_y=490
        _make_st('da_ponds_st_bottom',      50, 650, 600, 700), # center_y=675
    ]
    assert _detect_orientation_from_shelftalkers(dets) == 'vertical'


def test_none_orientation_no_skincare():
    # Only haircare shelftalkers in all_detected — can't determine orientation
    dets = [
        _make_st('da_hair_care_st_bottom', 50, 80, 150, 100),
        _make_st('da_hair_care_st_left',   50, 100, 70, 300),
    ]
    assert _detect_orientation_from_shelftalkers(dets) is None


def test_none_orientation_empty():
    assert _detect_orientation_from_shelftalkers([]) is None


# --- Leg rules ---

def test_vertical_haircare_gets_4_legs():
    adj = detect_category_adjacency(ADJACENT_DETS)
    assert get_required_legs('HAIRCARE', adj, orientation='vertical') == 4


def test_vertical_ponds_gets_3_legs():
    adj = detect_category_adjacency(ADJACENT_DETS)
    assert get_required_legs('PONDS', adj, orientation='vertical') == 3


def test_horizontal_haircare_gets_3_legs():
    adj = detect_category_adjacency(ADJACENT_DETS)
    assert get_required_legs('HAIRCARE', adj, orientation='horizontal') == 3


def test_horizontal_ponds_gets_4_legs():
    adj = detect_category_adjacency(ADJACENT_DETS)
    assert get_required_legs('PONDS', adj, orientation='horizontal') == 4


# --- Shelftalker waiver ---

def test_vertical_ponds_gets_waiver():
    adj = detect_category_adjacency(ADJACENT_DETS)
    assert should_waive_shelftalker('PONDS', adj, orientation='vertical') is True


def test_vertical_haircare_no_waiver():
    adj = detect_category_adjacency(ADJACENT_DETS)
    assert should_waive_shelftalker('HAIRCARE', adj, orientation='vertical') is False


def test_horizontal_haircare_gets_waiver():
    adj = detect_category_adjacency(ADJACENT_DETS)
    assert should_waive_shelftalker('HAIRCARE', adj, orientation='horizontal') is True


def test_horizontal_ponds_no_waiver():
    adj = detect_category_adjacency(ADJACENT_DETS)
    assert should_waive_shelftalker('PONDS', adj, orientation='horizontal') is False


def test_no_adjacency_orientation_none_falls_back_to_horizontal_rules():
    # When no shelftalker pair detected, orientation=None → horizontal priority rules apply
    adj = detect_category_adjacency(ADJACENT_DETS)
    # HAIRCARE adjacent to PONDS, no orientation → falls back to priority rules → HAIRCARE gets 3
    assert get_required_legs('HAIRCARE', adj, orientation=None) == 3
    assert get_required_legs('PONDS', adj, orientation=None) == 4
    assert should_waive_shelftalker('HAIRCARE', adj, orientation=None) is True
    assert should_waive_shelftalker('PONDS', adj, orientation=None) is False
