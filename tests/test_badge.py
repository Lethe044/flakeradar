from flakeradar.badge import badge_for_flaky_count, color_for_count, generate_badge_svg


def test_badge_is_valid_svg_markup():
    svg = badge_for_flaky_count(3)
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "flaky tests" in svg
    assert ">3<" in svg


def test_color_green_when_zero():
    assert color_for_count(0) == "#4c1"


def test_color_yellow_for_small_counts():
    assert color_for_count(1) == "#dfb317"
    assert color_for_count(3) == "#dfb317"


def test_color_red_for_larger_counts():
    assert color_for_count(4) == "#e05d44"
    assert color_for_count(50) == "#e05d44"


def test_custom_label_is_used():
    svg = badge_for_flaky_count(2, label="broken tests")
    assert "broken tests" in svg
    assert "flaky tests" not in svg


def test_html_special_characters_are_escaped():
    svg = generate_badge_svg("a & b", "<1>", "#4c1")
    assert "&amp;" in svg
    assert "<1>" not in svg
