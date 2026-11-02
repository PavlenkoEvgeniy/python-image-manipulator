"""Tests for window positioning helpers."""

from image_manipulator.positioning import centered_origin, choose_monitor

# Two side-by-side 1920x1080 monitors, like a laptop screen + external.
MONITORS = [(0, 0, 1920, 1080), (1920, 0, 1920, 1080)]


def test_centers_window_on_screen():
    assert centered_origin((1920, 1080), (800, 650)) == (560, 215)


def test_window_equal_to_container_starts_at_origin():
    assert centered_origin((800, 650), (800, 650)) == (0, 0)


def test_window_larger_than_container_gives_negative_origin():
    assert centered_origin((100, 100), (200, 300)) == (-50, -100)


def test_odd_difference_rounds_down():
    assert centered_origin((101, 101), (50, 50)) == (25, 25)


def test_pointer_on_left_monitor_picks_left_monitor():
    assert choose_monitor(MONITORS, (960, 540)) == (0, 0, 1920, 1080)


def test_pointer_on_right_monitor_picks_right_monitor():
    assert choose_monitor(MONITORS, (3000, 100)) == (1920, 0, 1920, 1080)


def test_pointer_outside_all_monitors_gives_none():
    assert choose_monitor(MONITORS, (5000, 100)) is None


def test_pointer_above_all_monitors_gives_none():
    assert choose_monitor(MONITORS, (960, -10)) is None
