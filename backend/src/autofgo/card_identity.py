"""Local card-name recognition with explicit unknown and ambiguous outcomes."""

import json
import math
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

import numpy as np
from PIL import Image, ImageOps

from autofgo.card_colors import SLOT_LEFTS, _game_viewport
from autofgo.screen_operations import ScreenRegion


@dataclass(frozen=True, slots=True)
class IdentityPolicy:
    max_mae: float = 40.0
    min_margin: float = 10.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_mae) or not 0 <= self.max_mae <= 255:
            raise ValueError("max_mae must be finite and in 0..255")
        if not math.isfinite(self.min_margin) or not 0 < self.min_margin <= 255:
            raise ValueError("min_margin must be finite and in (0, 255]")


DEFAULT_POLICY = IdentityPolicy()


@dataclass(frozen=True, slots=True)
class IdentityCandidate:
    reference_id: str
    character_name: str
    appearance_id: str
    score: float
    scale: float
    game_rect: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class CardIdentity:
    position: int
    status: Literal["recognized", "unknown", "ambiguous"]
    reason: str
    character_name: str | None
    score: float | None
    margin: float | None
    candidates: tuple[IdentityCandidate, ...]
    # Diagnostic distances, not a calibrated probability of correctness.


def decide_identity(
    position: int,
    candidates: tuple[IdentityCandidate, ...],
    policy: IdentityPolicy = DEFAULT_POLICY,
) -> CardIdentity:
    if type(position) is not int or position not in range(5):
        raise ValueError("card position must be 0..4")
    if any(
        not c.character_name.strip() or not math.isfinite(c.score) or not 0 <= c.score <= 255
        for c in candidates
    ):
        raise ValueError("invalid identity candidate")
    ordered = tuple(sorted(candidates, key=lambda c: c.score))
    if not ordered:
        return CardIdentity(position, "unknown", "no_references", None, None, None, ())
    best = ordered[0]
    other = next((c for c in ordered if c.character_name != best.character_name), None)
    margin = None if other is None else round(other.score - best.score, 4)
    if best.score > policy.max_mae:
        status, reason, name = "unknown", "low_similarity", None
    elif margin is None:
        status, reason, name = "ambiguous", "no_competing_character", None
    elif margin < policy.min_margin:
        status, reason, name = "ambiguous", "close_candidates", None
    else:
        status, reason, name = "recognized", "matched", best.character_name
    return CardIdentity(position, status, reason, name, best.score, margin, ordered)


@dataclass(frozen=True, slots=True)
class CardReference:
    id: str
    character_name: str
    appearance_id: str
    image: Image.Image
    crop_size: tuple[int, int]


def _text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a nonempty string")
    return value


def _integers(value: object, length: int, key: str) -> tuple[int, ...]:
    if (
        not isinstance(value, list)
        or len(value) != length
        or any(type(v) is not int for v in value)
    ):
        raise ValueError(f"{key} must contain {length} integers")
    return tuple(value)


def load_references(manifest: Path) -> tuple[CardReference, ...]:
    """Validate metadata first; only reviewed local PNGs become candidates."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or type(data.get("schemaVersion")) is not int
        or data["schemaVersion"] != 1
        or not isinstance(data.get("references"), list)
    ):
        raise ValueError("unsupported reference manifest")
    root = manifest.parent.resolve()
    references = []
    ids = set()
    for entry in data["references"]:
        if not isinstance(entry, dict):
            raise ValueError("reference must be an object")
        reference_id = _text(entry, "id")
        if reference_id in ids:
            raise ValueError("duplicate reference id")
        ids.add(reference_id)
        name, appearance = _text(entry, "characterName"), _text(entry, "appearanceId")
        if type(entry.get("reviewed")) is not bool:
            raise ValueError("reviewed must be a boolean")
        relative = _text(entry, "imagePath")
        parts = PurePosixPath(relative)
        if (
            parts.is_absolute()
            or ".." in parts.parts
            or "\\" in relative
            or ":" in relative
            or parts.suffix.lower() != ".png"
        ):
            raise ValueError("imagePath must be a relative PNG without traversal")
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("imagePath escapes reference directory")
        width, height = _integers(entry.get("imageSize"), 2, "imageSize")
        source = entry.get("source")
        if not isinstance(source, dict) or source.get("kind") != "statusScreenshot":
            raise ValueError("source must be a status screenshot")
        _text(source, "sourceId")
        sw, sh = _integers(source.get("sourceSize"), 2, "sourceSize")
        x, y, cw, ch = _integers(source.get("crop"), 4, "crop")
        if min(width, height, sw, sh, cw, ch) <= 0 or min(x, y) < 0 or x + cw > sw or y + ch > sh:
            raise ValueError("invalid reference dimensions or crop")
        transform = entry.get("transform")
        if transform is None:
            if (width, height) != (cw, ch):
                raise ValueError("imageSize differs from crop without resize metadata")
        elif (
            not isinstance(transform, dict)
            or transform.get("resample") != "LANCZOS"
            or _integers(transform.get("resize"), 2, "resize") != (width, height)
        ):
            raise ValueError("unsupported reference transform")
        if not entry["reviewed"]:
            continue
        # Scale assumptions have only been evaluated on these status layouts.
        if (sw, sh) not in {(1962, 1114), (1920, 1080)}:
            raise ValueError("unsupported reference source layout")
        with Image.open(path) as opened:
            if opened.format != "PNG":
                raise ValueError("reference file must contain PNG data")
            oriented = ImageOps.exif_transpose(opened)
            if oriented.size != (width, height):
                raise ValueError("PNG dimensions differ from manifest")
            rgba = oriented.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            image = background.convert("RGB")
        references.append(CardReference(reference_id, name, appearance, image, (cw, ch)))
    return tuple(references)


class CardIdentityRecognizer:
    """Cache references once and exhaustively compare the original search grid."""

    def __init__(
        self,
        references: tuple[CardReference, ...],
        policy: IdentityPolicy = DEFAULT_POLICY,
    ) -> None:
        self.policy = policy
        prepared = []
        for reference in references:
            templates = []
            for step in range(13, 20):
                scale = step / 10
                width, height = (round(v * scale / 4) for v in reference.crop_size)
                if not (1 <= width <= 75 and 1 <= height <= 72):
                    continue
                resized = reference.image.resize((width, height), Image.Resampling.LANCZOS)
                array = np.asarray(resized, dtype=np.int16).transpose(2, 0, 1)
                array.setflags(write=False)
                templates.append((scale, width, height, array))
            if not templates:
                raise ValueError(f"reference does not fit search area: {reference.id}")
            prepared.append((reference, tuple(templates)))
        self._prepared = tuple(prepared)

    @classmethod
    def from_manifest(
        cls, path: Path, policy: IdentityPolicy = DEFAULT_POLICY
    ) -> "CardIdentityRecognizer":
        return cls(load_references(path), policy)

    def recognize(
        self, screenshot: Image.Image, viewport: ScreenRegion | None = None
    ) -> tuple[CardIdentity, ...]:
        game = _game_viewport(screenshot, viewport)
        image = screenshot.convert("RGB").crop((game.left, game.top, game.right, game.bottom))
        pixels = np.asarray(image.resize((480, 270), Image.Resampling.LANCZOS), dtype=np.int16)
        results = []
        for position, left in enumerate(SLOT_LEFTS):
            x0, y0 = left // 4, 560 // 4
            roi = pixels[y0 : 850 // 4, x0 : (left + 300) // 4]
            candidates = []
            for reference, templates in self._prepared:
                best_score = float("inf")
                best_scale = 0.0
                best_rect = (0, 0, 0, 0)
                for scale, width, height, template in templates:
                    windows = np.lib.stride_tricks.sliding_window_view(
                        roi, (height, width), axis=(0, 1)
                    )
                    # Bound temporary memory; int16 prevents uint8 subtraction wraparound.
                    for row in range(0, windows.shape[0], 8):
                        difference = np.subtract(windows[row : row + 8], template)
                        np.abs(difference, out=difference)
                        sums = difference.sum(axis=(2, 3, 4), dtype=np.int64)
                        index = int(sums.argmin())
                        dy, dx = divmod(index, sums.shape[1])
                        score = int(sums[dy, dx]) / (width * height * 3)
                        if score < best_score:
                            best_score = score
                            best_scale = scale
                            best_rect = ((x0 + dx) * 4, (y0 + row + dy) * 4, width * 4, height * 4)
                candidates.append(
                    IdentityCandidate(
                        reference.id,
                        reference.character_name,
                        reference.appearance_id,
                        round(best_score, 4),
                        best_scale,
                        best_rect,
                    )
                )
            results.append(decide_identity(position, tuple(candidates), self.policy))
        return tuple(results)
