"""Locate command cards in a status screenshot and produce reviewable crops."""

from dataclasses import dataclass
from importlib.resources import files

import numpy as np
from PIL import Image, ImageOps

GAME_SIZE = (1920, 1080)
WINDOW_SIZE = (1962, 1114)
HEADER_SIZE = (175, 44)
CARD_PITCH = 206
CARD_COUNT = 5
SIZE_PRESETS = ((100, 95), (105, 100), (110, 100), (115, 105), (120, 110))
OFFSETS = ((0, 0), (-5, -5), (0, -5), (5, -5), (-5, 0), (5, 0), (-5, 5), (0, 5), (5, 5))


@dataclass(frozen=True)
class Candidate:
    crop: tuple[int, int, int, int]
    image: Image.Image


@dataclass(frozen=True)
class CardLayout:
    source_size: tuple[int, int]
    header: tuple[int, int, int, int]
    cards: tuple[tuple[int, int, int, int], ...]


def _game_image(source: Image.Image) -> tuple[Image.Image, int]:
    image = ImageOps.exif_transpose(source).convert("RGB")
    if image.size == WINDOW_SIZE:
        return image.crop((0, 34, 1920, 1114)), 34
    if image.size == GAME_SIZE:
        return image, 0
    raise ValueError(f"unsupported status screenshot size: {image.size}")


def _find_header(image: Image.Image) -> tuple[int, int]:
    template_path = files("autofgo").joinpath("assets/card_status_header.png")
    with Image.open(template_path) as opened:
        template = np.asarray(opened.convert("RGB").resize((88, 22)), dtype=np.int16)
    scan = np.asarray(image.resize((960, 540)), dtype=np.int16)
    best = (float("inf"), 0, 0)
    # The header is on the right-hand panel; its vertical position follows scrolling.
    for y in range(75, 360):
        for x in range(365, 425):
            patch = scan[y : y + 22, x : x + 88]
            score = float(np.abs(patch - template).mean())
            if score < best[0]:
                best = (score, x, y)
    if best[0] > 22:
        raise ValueError(f"command-card heading not found (difference {best[0]:.1f})")
    return best[1] * 2, best[2] * 2


def _find_card_top(image: Image.Image, first_x: int, header_y: int) -> int:
    pixels = np.asarray(image, dtype=np.int16)
    best = (0.0, 0)
    # Card frames have a bright gold vertical edge in each of the five slots.
    for y in range(header_y + 55, min(header_y + 155, 850)):
        scores = []
        for index in range(CARD_COUNT):
            x = first_x + index * CARD_PITCH
            before = pixels[y - 5 : y, x + 1 : x + 4].mean(axis=(0, 1))
            after = pixels[y + 3 : y + 11, x + 1 : x + 4].mean(axis=(0, 1))
            scores.append(max(0.0, float(after[0] - before[0])))
        score = sum(scores) if all(value > 80 for value in scores) else 0
        if score > best[0]:
            best = (score, y)
    if best[0] < 500:
        raise ValueError("five-card row not found below heading")
    return best[1]


def detect_layout(source: Image.Image) -> CardLayout:
    """Return heading and five card frames in source-image coordinates."""
    image, source_y = _game_image(source)
    header_x, header_y = _find_header(image)
    first_x = header_x + 41
    top = _find_card_top(image, first_x, header_y)
    cards = tuple(
        (first_x + index * CARD_PITCH, top + source_y, 140, 180) for index in range(CARD_COUNT)
    )
    if cards[-1][0] + cards[-1][2] > image.width or top + 180 > image.height:
        raise ValueError("card row extends outside the screenshot")
    source_size = ImageOps.exif_transpose(source).size
    return CardLayout(source_size, (header_x, header_y + source_y, *HEADER_SIZE), cards)


def generate_candidates(
    source: Image.Image, layout: CardLayout, card_index: int, size: tuple[int, int]
) -> tuple[Candidate, ...]:
    """Make the standard crop and its eight five-pixel neighbors."""
    if size not in SIZE_PRESETS:
        raise ValueError(f"unsupported crop size: {size}")
    if not 0 <= card_index < CARD_COUNT:
        raise ValueError(f"card index out of range: {card_index}")
    image = ImageOps.exif_transpose(source).convert("RGB")
    if image.size != layout.source_size:
        raise ValueError("layout belongs to a different screenshot size")
    frame_x, frame_y, _, _ = layout.cards[card_index]
    width, height = size
    left, top = frame_x + 14, frame_y - 3
    candidates = []
    for dx, dy in OFFSETS:
        x, y = left + dx, top + dy
        if x < 0 or y < 0 or x + width > image.width or y + height > image.height:
            raise ValueError("candidate crop extends outside the screenshot")
        candidates.append(
            Candidate((x, y, width, height), image.crop((x, y, x + width, y + height)))
        )
    return tuple(candidates)
