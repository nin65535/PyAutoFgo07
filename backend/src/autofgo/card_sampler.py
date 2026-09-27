"""Independent status screenshot sampler for card reference images."""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps

from autofgo.card_references import register_reference


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
    _, target = register_reference(
        manifest_path, args.character_name, args.appearance_id, cropped, source
    )
    return target


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
            part.add_argument("--character-name", required=True)
            part.add_argument("--appearance-id", type=int)
            part.add_argument("--source-id", required=True)
            part.add_argument("--source-url")
            part.add_argument("--confirmed", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(sample(args))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
