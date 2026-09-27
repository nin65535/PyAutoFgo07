import json

from PIL import Image

from autofgo.card_references import allocate, read_manifest
from autofgo.card_sampler import main


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
