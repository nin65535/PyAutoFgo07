"""Offline R26 experiment; scores are diagnostics, not production confidence."""

import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

from PIL import Image, ImageChops, ImageStat


def match(image: Image.Image, reference: Image.Image, position: int, search_top: int = 600) -> dict:
    """Search RGB MAE at quarter resolution, with no labels as input."""
    left = (76, 461, 846, 1231, 1616)[position]
    best = {"score": float("inf")}
    for step in range(13, 20):
        scale = step / 10
        size = tuple(round(value * scale / 4) for value in reference.size)
        template = reference.resize(size, Image.Resampling.LANCZOS)
        for y in range(search_top // 4, (850 - size[1] * 4) // 4 + 1):
            for x in range(left // 4, (left + 300 - size[0] * 4) // 4 + 1):
                patch = image.crop((x, y, x + size[0], y + size[1]))
                score = sum(ImageStat.Stat(ImageChops.difference(patch, template)).mean) / 3
                if score < best["score"]:
                    best = {
                        "score": score,
                        "scale": scale,
                        "gameRect": [x * 4, y * 4, size[0] * 4, size[1] * 4],
                    }
    best["score"] = round(best["score"], 4)
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument(
        "--references", type=Path, default=Path("card-data/references/manifest.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--search-top", type=int, default=600)
    args = parser.parse_args()
    manifest = json.loads(args.references.read_text(encoding="utf-8"))
    names = {character["id"]: character["name"] for character in manifest["characters"]}
    references = []
    for entry in manifest["references"]:
        if entry["reviewed"] is True:
            path = args.references.parent / entry["imagePath"]
            with Image.open(path) as opened:
                references.append(
                    (entry, opened.convert("RGB"), hashlib.sha256(path.read_bytes()).hexdigest())
                )
    report = {
        "method": "RGB MAE, quarter resolution, scale 1.3..1.9 step 0.1, 4px translation",
        "searchTop": args.search_top,
        "referenceManifestSha256": hashlib.sha256(args.references.read_bytes()).hexdigest(),
        "references": [{"id": entry["id"], "sha256": digest} for entry, _, digest in references],
        "cases": [],
    }
    for path in args.images:
        started = perf_counter()
        with Image.open(path) as opened:
            original = opened.convert("RGB")
        if original.size == (1962, 1114):
            original = original.crop((0, 34, 1920, 1114))
        elif original.size != (1920, 1080):
            raise ValueError(f"unsupported image size: {original.size}")
        image = original.resize((480, 270), Image.Resampling.LANCZOS)
        case = {
            "imagePath": path.as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "cards": [],
        }
        for position in range(5):
            candidates = sorted(
                [
                    {
                        "referenceId": entry["id"],
                        "characterName": names[entry["characterId"]],
                        **match(image, ref, position, args.search_top),
                    }
                    for entry, ref, _ in references
                ],
                key=lambda item: item["score"],
            )
            best_by_name = {}
            for candidate in candidates:
                best_by_name.setdefault(candidate["characterName"], candidate)
            names = list(best_by_name.values())
            margin = round(names[1]["score"] - names[0]["score"], 4) if len(names) > 1 else None
            case["cards"].append(
                {"position": position, "candidates": candidates, "differentCharacterMargin": margin}
            )
        case["elapsedSeconds"] = round(perf_counter() - started, 3)
        report["cases"].append(case)
        print(
            path.name,
            [
                (
                    card["candidates"][0]["referenceId"],
                    card["candidates"][0]["score"],
                    card["differentCharacterMargin"],
                )
                for card in case["cards"]
            ],
            flush=True,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
