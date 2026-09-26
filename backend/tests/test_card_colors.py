import pytest
from PIL import Image, ImageDraw

from autofgo.card_colors import SLOT_LEFTS, detect_card_colors
from autofgo.screen_operations import ScreenRegion


def test_detects_five_colors_with_vertical_motion_and_viewport():
    image = Image.new("RGB", (1962, 1114), "black")
    draw = ImageDraw.Draw(image)
    for left, color, shift in zip(
        SLOT_LEFTS, ("red", "blue", "green", "blue", "red"), (-15, 12, 0, -10, 15), strict=True
    ):
        draw.rectangle((left + 4, 34 + 650 + shift, left + 218, 34 + 760 + shift), fill=color)
        draw.rectangle((left + 35, 34 + 650 + shift, left + 189, 34 + 760 + shift), fill="black")
    cards = detect_card_colors(image)
    assert [card.color for card in cards] == ["B", "A", "Q", "A", "B"]
    assert [card.position for card in cards] == list(range(5))
    assert cards[0].region == ScreenRegion(76, 644, 230, 350)


def test_rejects_unknown_layout_and_ambiguous_color():
    with pytest.raises(ValueError, match="viewport"):
        detect_card_colors(Image.new("RGB", (100, 100)))
    with pytest.raises(ValueError, match="unclear"):
        detect_card_colors(Image.new("RGB", (1920, 1080)))
