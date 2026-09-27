"""Shared schema, allocation, and durable storage for card references."""

import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from PIL import Image

_write_lock = threading.Lock()


def _positive(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


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


def filename(name: str, appearance_id: int, sample_number: int) -> str:
    if (
        not name
        or name != name.strip()
        or name.endswith(".")
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
    ):
        raise ValueError("character name cannot be used as a Windows filename")
    _positive(appearance_id, "appearanceId")
    _positive(sample_number, "sampleNumber")
    return f"{name}-{appearance_id}-{sample_number:02d}.png"


def empty_manifest() -> dict:
    return {
        "schemaVersion": 2,
        "nextCharacterId": 1,
        "nextReferenceId": 1,
        "characters": [],
        "references": [],
    }


def read_manifest(path: Path, *, missing_ok: bool = False) -> dict:
    if missing_ok and not path.exists():
        return empty_manifest()
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(data, path.parent)
    return data


def validate_manifest(data: object, root: Path) -> None:
    if (
        not isinstance(data, dict)
        or type(data.get("schemaVersion")) is not int
        or data["schemaVersion"] != 2
    ):
        raise ValueError("unsupported reference manifest")
    characters, references = data.get("characters"), data.get("references")
    if not isinstance(characters, list) or not isinstance(references, list):
        raise ValueError("invalid reference manifest collections")
    next_character = _positive(data.get("nextCharacterId"), "nextCharacterId")
    next_reference = _positive(data.get("nextReferenceId"), "nextReferenceId")
    names: set[str] = set()
    character_ids: set[int] = set()
    appearance_ids: dict[int, set[int]] = {}
    for character in characters:
        if not isinstance(character, dict):
            raise ValueError("character must be an object")
        cid = _positive(character.get("id"), "characterId")
        name = _text(character, "name")
        if cid in character_ids or name in names or cid >= next_character:
            raise ValueError("duplicate or unallocated character")
        character_ids.add(cid)
        names.add(name)
        next_appearance = _positive(character.get("nextAppearanceId"), "nextAppearanceId")
        appearances = character.get("appearances")
        next_samples = character.get("nextSampleNumbers")
        if not isinstance(appearances, list):
            raise ValueError("appearances must be a list")
        if not isinstance(next_samples, dict):
            raise ValueError("nextSampleNumbers must be an object")
        ids = set()
        for appearance in appearances:
            aid = _positive(appearance, "appearanceId")
            if aid in ids or aid >= next_appearance:
                raise ValueError("duplicate or unallocated appearance")
            _positive(next_samples.get(str(aid)), "nextSampleNumber")
            ids.add(aid)
        if set(next_samples) != {str(aid) for aid in ids}:
            raise ValueError("nextSampleNumbers do not match appearances")
        appearance_ids[cid] = ids
    ids: set[int] = set()
    paths: set[str] = set()
    samples: set[tuple[int, int, int]] = set()
    for entry in references:
        if not isinstance(entry, dict):
            raise ValueError("reference must be an object")
        rid = _positive(entry.get("id"), "reference id")
        cid = _positive(entry.get("characterId"), "characterId")
        aid = _positive(entry.get("appearanceId"), "appearanceId")
        sample = _positive(entry.get("sampleNumber"), "sampleNumber")
        if rid in ids or rid >= next_reference or aid not in appearance_ids.get(cid, set()):
            raise ValueError("duplicate reference id or unknown character/appearance")
        ids.add(rid)
        key = (cid, aid, sample)
        if key in samples:
            raise ValueError("duplicate sample number")
        samples.add(key)
        name = next(c["name"] for c in characters if c["id"] == cid)
        character = next(c for c in characters if c["id"] == cid)
        if sample >= character["nextSampleNumbers"][str(aid)]:
            raise ValueError("unallocated sample number")
        relative = _text(entry, "imagePath")
        parts = PurePosixPath(relative)
        if (
            parts.is_absolute()
            or parts.parts != ("images", filename(name, aid, sample))
            or relative in paths
        ):
            raise ValueError("invalid or duplicate imagePath")
        paths.add(relative)
        if not (root / relative).resolve().is_relative_to(root.resolve()):
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
        if type(entry.get("reviewed")) is not bool:
            raise ValueError("reviewed must be a boolean")


def allocate(data: dict, name: str, appearance_id: int | None) -> tuple[int, int, int, int, str]:
    """Reserve IDs in a manifest copy; callers persist it with the new PNG."""
    filename(name, 1, 1)
    character = next((c for c in data["characters"] if c["name"] == name), None)
    if character is None:
        if appearance_id is not None:
            raise ValueError("new character requires a new appearance")
        character = {
            "id": data["nextCharacterId"],
            "name": name,
            "nextAppearanceId": 1,
            "appearances": [],
            "nextSampleNumbers": {},
        }
        data["nextCharacterId"] += 1
        data["characters"].append(character)
    if appearance_id is None:
        appearance_id = character["nextAppearanceId"]
        character["nextAppearanceId"] += 1
        character["appearances"].append(appearance_id)
        character["nextSampleNumbers"][str(appearance_id)] = 1
    elif appearance_id not in character["appearances"]:
        raise ValueError("unknown appearanceId")
    sample = character["nextSampleNumbers"][str(appearance_id)]
    character["nextSampleNumbers"][str(appearance_id)] += 1
    rid = data["nextReferenceId"]
    data["nextReferenceId"] += 1
    return (
        rid,
        character["id"],
        appearance_id,
        sample,
        f"images/{filename(name, appearance_id, sample)}",
    )


@contextmanager
def reference_write_lock(path: Path):
    """Serialize reference updates across threads and sampler/CLI processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / ".manifest.lock"
    with _write_lock, lock_path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def register_reference(
    path: Path,
    name: str,
    appearance_id: int | None,
    image: Image.Image,
    source: dict,
) -> tuple[dict, Path]:
    """Allocate and save one reference against the latest manifest."""
    with reference_write_lock(path):
        data = read_manifest(path, missing_ok=True)
        rid, cid, aid, sample, image_path = allocate(data, name, appearance_id)
        entry = {
            "id": rid,
            "characterId": cid,
            "appearanceId": aid,
            "sampleNumber": sample,
            "imagePath": image_path,
            "imageSize": list(image.size),
            "source": source,
            "reviewed": True,
        }
        target = _save_reference(path, data, entry, image)
        return entry, target


def _save_reference(path: Path, data: dict, entry: dict, image: Image.Image) -> Path:
    """Publish within the write lock; roll back owned image on failure."""
    if image.size != tuple(entry["imageSize"]):
        raise ValueError("PNG dimensions differ from manifest")
    data["references"].append(entry)
    validate_manifest(data, path.parent)
    target = path.parent / entry["imagePath"]
    if target.exists():
        raise ValueError(f"reference image already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".manifest-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Exclusive creation avoids replacing an existing image.
        created = False
        try:
            with target.open("xb") as stream:
                created = True
                image.save(stream, format="PNG")
            os.replace(temp_name, path)
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target
