"""Locate the five command-card slots and classify their background colors."""

from dataclasses import dataclass

from PIL import Image

from autofgo.screen_operations import ScreenRegion

GAME_SIZE = (1920, 1080)
SLOT_LEFTS = (76, 461, 846, 1231, 1616)
SLOT_TOP = 610
SLOT_WIDTH = 230
SLOT_HEIGHT = 350


@dataclass(frozen=True, slots=True)
class CardColor:
    position: int
    region: ScreenRegion
    color: str
    counts: dict[str, int]


def _game_viewport(image: Image.Image, viewport: ScreenRegion | None) -> ScreenRegion:
    if viewport is not None:
        if (
            viewport.left < 0
            or viewport.top < 0
            or not ScreenRegion(0, 0, *image.size).contains_region(viewport)
        ):
            raise ValueError("game viewport exceeds image bounds")
        return viewport
    if image.size == GAME_SIZE:
        return ScreenRegion(0, 0, *GAME_SIZE)
    if image.size == (1962, 1114):
        return ScreenRegion(0, 34, *GAME_SIZE)
    raise ValueError("unknown screenshot layout; provide the game viewport")


def _scale_region(region: ScreenRegion, viewport: ScreenRegion) -> ScreenRegion:
    return ScreenRegion(
        viewport.left + round(region.left * viewport.width / GAME_SIZE[0]),
        viewport.top + round(region.top * viewport.height / GAME_SIZE[1]),
        max(1, round(region.width * viewport.width / GAME_SIZE[0])),
        max(1, round(region.height * viewport.height / GAME_SIZE[1])),
    )


def detect_card_colors(
    image: Image.Image, viewport: ScreenRegion | None = None
) -> tuple[CardColor, ...]:
    """Return left-to-right card colors in screenshot pixel coordinates.

    An unsupported layout or unclear color raises ValueError, so callers cannot
    mistake an unrecognized screen for a valid five-card hand.
    """
    game = _game_viewport(image, viewport)
    hsv = image.convert("RGB").convert("HSV")
    cards = []
    for position, left in enumerate(SLOT_LEFTS):
        slot = _scale_region(ScreenRegion(left, SLOT_TOP, SLOT_WIDTH, SLOT_HEIGHT), game)
        # The narrow side strips stay clear of portraits, lettering and effect icons.
        side_regions = [
            _scale_region(ScreenRegion(left + offset, 650, 28, 110), game) for offset in (4, 190)
        ]
        counts, sampled = _count_colors(hsv, side_regions)
        color = _dominant_color(counts, sampled)
        if color is None:
            # Card portraits can cover the side strips. The color-specific word
            # effect is drawn in front of the portrait near the card bottom.
            effect = _scale_region(ScreenRegion(left + 20, 780, 190, 120), game)
            effect_counts, effect_sampled = _count_colors(hsv, [effect])
            color = _dominant_color(effect_counts, effect_sampled)
            if color is not None:
                counts = effect_counts
        if color is None:
            raise ValueError(f"card {position} color is unclear: {counts}")
        cards.append(CardColor(position, slot, color, counts))
    return tuple(cards)


def _count_colors(hsv: Image.Image, regions: list[ScreenRegion]) -> tuple[dict[str, int], int]:
    counts = {"B": 0, "A": 0, "Q": 0}
    sampled = 0
    for region in regions:
        for y in range(region.top, region.bottom):
            for x in range(region.left, region.right):
                hue, saturation, value = hsv.getpixel((x, y))
                sampled += 1
                if saturation < 100 or value < 65:
                    continue
                if hue <= 18 or hue >= 245:
                    counts["B"] += 1
                elif 135 <= hue <= 185:
                    counts["A"] += 1
                elif 48 <= hue <= 110:
                    counts["Q"] += 1
    return counts, sampled


def _dominant_color(counts: dict[str, int], sampled: int) -> str | None:
    color = max(counts, key=counts.__getitem__)
    total = sum(counts.values())
    if counts[color] < sampled * 0.08 or counts[color] < total * 0.6:
        return None
    return color
