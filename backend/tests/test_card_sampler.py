import json
import multiprocessing
import os
from pathlib import Path

import pytest
from PIL import Image

from autofgo.card_references import (
    _save_reference,
    allocate,
    read_manifest,
    reference_write_lock,
    register_reference,
)
from autofgo.card_sampler import main


def _source(name: str) -> dict:
    return {
        "kind": "statusScreenshot",
        "sourceId": name,
        "sourceSize": [2, 2],
        "crop": [0, 0, 2, 2],
    }


def _register_in_process(path: Path, ready, done) -> None:
    ready.set()
    register_reference(path, "Alice", None, Image.new("RGB", (2, 2)), _source("Alice"))
    done.set()


def test_preview_and_register(tmp_path):
    source = tmp_path / "status.png"
    Image.new("RGB", (100, 80), (20, 40, 60)).save(source)
    preview = tmp_path / "preview.png"
    common = ["--input", str(source), "--crop", "10,12,30,32"]
    assert main(["preview", *common, "--output", str(preview)]) == 0
    assert Image.open(preview).size == (30, 32)

    manifest = tmp_path / "references" / "manifest.json"
    register = [
        "register",
        *common,
        "--manifest",
        str(manifest),
        "--character-name",
        "アーラシュ",
        "--source-id",
        "status-01",
    ]
    assert main(register) == 1
    assert not manifest.exists()
    assert main([*register, "--confirmed"]) == 0
    entry = json.loads(manifest.read_text(encoding="utf-8"))["references"][0]
    assert entry["source"]["crop"] == [10, 12, 30, 32]
    assert entry["imageSize"] == [30, 32]
    assert entry["reviewed"] is True
    assert (entry["id"], entry["characterId"], entry["appearanceId"], entry["sampleNumber"]) == (
        1,
        1,
        1,
        1,
    )
    assert entry["imagePath"] == "images/アーラシュ-1-01.png"
    assert Image.open(manifest.parent / entry["imagePath"]).size == (30, 32)
    assert main([*register, "--appearance-id", "1", "--confirmed"]) == 0
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert [entry["sampleNumber"] for entry in data["references"]] == [1, 2]
    assert data["nextReferenceId"] == 3


def test_rejects_out_of_bounds_crop(tmp_path):
    source = tmp_path / "status.png"
    Image.new("RGB", (20, 20)).save(source)
    assert (
        main(
            [
                "preview",
                "--input",
                str(source),
                "--crop",
                "19,0,2,2",
                "--output",
                str(tmp_path / "preview.png"),
            ]
        )
        == 1
    )


def test_allocated_numbers_survive_deleted_entries(tmp_path):
    data = read_manifest(tmp_path / "manifest.json", missing_ok=True)
    assert allocate(data, "アーラシュ", None)[:4] == (1, 1, 1, 1)
    entry = {
        "id": 1,
        "characterId": 1,
        "appearanceId": 1,
        "sampleNumber": 1,
    }
    data["references"].append(entry)
    data["references"].clear()
    assert allocate(data, "アーラシュ", 1)[:4] == (2, 1, 1, 2)
    assert allocate(data, "アーラシュ", None)[:4] == (3, 1, 2, 1)
    assert allocate(data, "ダイダロス", None)[:4] == (4, 2, 1, 1)


def test_process_writer_waits_for_manifest_lock_and_keeps_both_references(tmp_path):
    path = tmp_path / "references" / "manifest.json"
    context = multiprocessing.get_context("spawn")
    ready, done = context.Event(), context.Event()
    process = context.Process(target=_register_in_process, args=(path, ready, done))
    try:
        with reference_write_lock(path):
            process.start()
            assert ready.wait(10)
            assert not done.wait(0.3)
            assert not path.exists()
    finally:
        if process.pid is not None:
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join()
    assert process.exitcode == 0
    register_reference(path, "Bob", None, Image.new("RGB", (2, 2)), _source("Bob"))
    data = read_manifest(path)
    assert [entry["id"] for entry in data["references"]] == [1, 2]
    assert [character["name"] for character in data["characters"]] == ["Alice", "Bob"]
    assert sorted(p.name for p in (path.parent / "images").iterdir()) == [
        "Alice-1-01.png",
        "Bob-1-01.png",
    ]


def test_failed_exclusive_creation_does_not_delete_other_writers_image(tmp_path, monkeypatch):
    path = tmp_path / "references" / "manifest.json"
    data = read_manifest(path, missing_ok=True)
    rid, cid, aid, sample, image_path = allocate(data, "Alice", None)
    entry = {
        "id": rid,
        "characterId": cid,
        "appearanceId": aid,
        "sampleNumber": sample,
        "imagePath": image_path,
        "imageSize": [2, 2],
        "source": _source("Alice"),
        "reviewed": True,
    }
    target = path.parent / image_path
    original_open = Path.open

    def competing_open(self, mode="r", *args, **kwargs):
        if self == target and mode == "xb":
            target.write_bytes(b"other writer")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", competing_open)
    with pytest.raises(FileExistsError):
        _save_reference(path, data, entry, Image.new("RGB", (2, 2)))
    assert target.read_bytes() == b"other writer"
    assert not path.exists()


def test_own_image_is_removed_when_manifest_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "references" / "manifest.json"

    def fail_replace(_source_path, _target_path):
        raise OSError("replacement failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        register_reference(path, "Alice", None, Image.new("RGB", (2, 2)), _source("Alice"))
    assert not (path.parent / "images" / "Alice-1-01.png").exists()
    assert not path.exists()
