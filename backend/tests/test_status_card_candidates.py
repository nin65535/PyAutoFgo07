from importlib.resources import files

import pytest
from PIL import Image, ImageDraw

from autofgo.status_card_candidates import (
    OFFSETS,
    SIZE_PRESETS,
    detect_layout,
    generate_candidates,
)


def status_image(heading_y: int, *, window: bool = False) -> Image.Image:
    game = Image.new("RGB", (1920, 1080), (38, 48, 55))
    with Image.open(files("autofgo").joinpath("assets/card_status_header.png")) as header:
        game.paste(header, (775, heading_y))
    draw = ImageDraw.Draw(game)
    for index in range(5):
        x = 815 + 206 * index
        draw.rectangle((x + 1, heading_y + 87, x + 3, heading_y + 180), fill=(245, 230, 130))
        draw.rectangle((x + 4, heading_y + 87, x + 135, heading_y + 260), outline=(190, 160, 90))
    if not window:
        return game
    source = Image.new("RGB", (1962, 1114), (0, 0, 0))
    source.paste(game, (0, 34))
    return source


@pytest.mark.parametrize("heading_y", [324, 365, 430])
@pytest.mark.parametrize("window", [False, True])
def test_detects_scrolled_heading_and_five_cards(heading_y, window):
    source = status_image(heading_y, window=window)
    layout = detect_layout(source)
    offset = 34 if window else 0
    assert layout.source_size == source.size
    assert abs(layout.header[0] - 775) <= 2
    assert abs(layout.header[1] - (heading_y + offset)) <= 2
    assert len(layout.cards) == 5
    assert [card[0] for card in layout.cards] == [815 + 206 * index for index in range(5)]
    assert all(abs(card[1] - (heading_y + 87 + offset)) <= 4 for card in layout.cards)


def test_generates_nine_candidates_for_each_size():
    source = status_image(324, window=True)
    layout = detect_layout(source)
    for size in SIZE_PRESETS:
        candidates = generate_candidates(source, layout, 1, size)
        assert len(candidates) == 9
        assert [candidate.image.size for candidate in candidates] == [size] * 9
        standard = candidates[0].crop
        for candidate, (dx, dy) in zip(candidates, OFFSETS, strict=True):
            assert candidate.crop == (standard[0] + dx, standard[1] + dy, *size)
            assert candidate.image.getpixel((0, 0)) == source.getpixel(candidate.crop[:2])


def test_rejects_unrecognized_images():
    with pytest.raises(ValueError, match="unsupported status screenshot size"):
        detect_layout(Image.new("RGB", (100, 100)))
    with pytest.raises(ValueError, match="heading not found"):
        detect_layout(Image.new("RGB", (1920, 1080)))
