import json

from PIL import Image

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
        "--id",
        "test-01",
        "--character-name",
        "アーラシュ",
        "--appearance-id",
        "default",
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
    assert Image.open(manifest.parent / entry["imagePath"]).size == (30, 32)
    assert main([*register, "--confirmed"]) == 1


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
