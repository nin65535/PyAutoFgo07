"""Independent status screenshot sampler for card reference images."""

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

from PIL import Image, ImageOps


def rectangle(value: str) -> tuple[int, int, int, int]:
    try:
        parts = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("crop must be left,top,width,height") from exc
    if len(parts) != 4 or parts[0] < 0 or parts[1] < 0 or parts[2] <= 0 or parts[3] <= 0:
        raise argparse.ArgumentTypeError(
            "crop must be nonnegative left/top and positive width/height"
        )
    return parts


def _safe_image_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "\\" in value
        or ".." in path.parts
        or path.parts[:1] != ("images",)
        or path.suffix.lower() != ".png"
    ):
        raise ValueError("imagePath must be a PNG below images/ without parent traversal")


def _manifest(path: Path) -> dict:
    if not path.exists():
        return {"schemaVersion": 1, "references": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1 or not isinstance(data.get("references"), list):
        raise ValueError("unsupported reference manifest")
    for entry in data["references"]:
        _safe_image_path(entry["imagePath"])
    return data


def sample(args: argparse.Namespace) -> Path:
    if not args.input.is_file():
        raise ValueError(f"input image not found: {args.input}")
    with Image.open(args.input) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    left, top, width, height = args.crop
    if left + width > image.width or top + height > image.height:
        raise ValueError(f"crop {args.crop} exceeds source size {image.size}")
    cropped = image.crop((left, top, left + width, top + height))
    if args.command == "preview":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(args.output, format="PNG")
        return args.output

    manifest_path = args.manifest
    data = _manifest(manifest_path)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.id):
        raise ValueError("id must contain lowercase ASCII letters, digits, or hyphens")
    if any(entry["id"] == args.id for entry in data["references"]):
        raise ValueError(f"reference id already exists: {args.id}")
    image_path = f"images/{args.id}.png"
    _safe_image_path(image_path)
    target = manifest_path.parent / image_path
    if target.exists():
        raise ValueError(f"reference image already exists: {target}")
    if not args.confirmed:
        raise ValueError("inspect a preview first, then pass --confirmed to register")
    source = {
        "kind": "statusScreenshot",
        "sourceId": args.source_id,
        "sourceSize": list(image.size),
        "crop": list(args.crop),
    }
    if args.source_url:
        source["sourceUrl"] = args.source_url
    entry = {
        "id": args.id,
        "characterName": args.character_name,
        "appearanceId": args.appearance_id,
        "imagePath": image_path,
        "imageSize": list(cropped.size),
        "source": source,
        "reviewed": True,
    }
    data["references"].append(entry)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_png_bytes(cropped))
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        target.unlink()
        raise
    return target


def _png_bytes(image: Image.Image) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "register"):
        part = sub.add_parser(command)
        part.add_argument("--input", type=Path, required=True)
        part.add_argument("--crop", type=rectangle, required=True, help="left,top,width,height")
        if command == "preview":
            part.add_argument("--output", type=Path, required=True)
        else:
            part.add_argument(
                "--manifest", type=Path, default=Path("card-data/references/manifest.json")
            )
            part.add_argument("--id", required=True)
            part.add_argument("--character-name", required=True)
            part.add_argument("--appearance-id", required=True)
            part.add_argument("--source-id", required=True)
            part.add_argument("--source-url")
            part.add_argument("--confirmed", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(sample(args))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
