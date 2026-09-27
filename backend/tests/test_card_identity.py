import json
import math
import shutil
from pathlib import Path

import pytest
from PIL import Image

from autofgo.card_identity import (
    CardIdentityRecognizer,
    CardReference,
    IdentityCandidate,
    IdentityPolicy,
    decide_identity,
    load_references,
)

FIXTURES = Path(__file__).parent / "fixtures" / "card_identity"


def candidate(name, score, reference_id=1):
    return IdentityCandidate(reference_id, name, 1, score, 1.3, (0, 0, 40, 40))


@pytest.mark.parametrize(
    ("scores", "status", "reason", "name"),
    [
        ([], "unknown", "no_references", None),
        ([candidate("a", 41), candidate("b", 80)], "unknown", "low_similarity", None),
        ([candidate("a", 41), candidate("b", 41)], "unknown", "low_similarity", None),
        ([candidate("a", 40), candidate("b", 50)], "recognized", "matched", "a"),
        ([candidate("a", 29.8), candidate("b", 39.8)], "recognized", "matched", "a"),
        ([candidate("a", 20), candidate("b", 29.99)], "ambiguous", "close_candidates", None),
        ([candidate("a", 0), candidate("b", 0)], "ambiguous", "close_candidates", None),
        ([candidate("a", 5)], "ambiguous", "no_competing_character", None),
        ([candidate("a", 5), candidate("a", 6), candidate("b", 30)], "recognized", "matched", "a"),
    ],
)
def test_decision_boundaries(scores, status, reason, name):
    result = decide_identity(0, tuple(scores))
    assert (result.status, result.reason, result.character_name) == (status, reason, name)
    assert len(result.candidates) == len(scores)


@pytest.mark.parametrize("score", [math.nan, math.inf, -1, 256])
def test_rejects_invalid_scores(score):
    with pytest.raises(ValueError):
        decide_identity(0, (candidate("a", score),))


@pytest.mark.parametrize("kwargs", [{"max_mae": math.nan}, {"max_mae": -1}, {"min_margin": 0}])
def test_rejects_invalid_policy(kwargs):
    with pytest.raises(ValueError):
        IdentityPolicy(**kwargs)


def test_fixed_85_card_decision_regression():
    cases = json.loads((FIXTURES / "decisions.json").read_text(encoding="utf-8"))
    recognized = unknown = 0
    for case in cases:
        for card in case["cards"]:
            candidates = tuple(
                IdentityCandidate(
                    c["referenceId"],
                    c["characterName"],
                    1,
                    c["score"],
                    c["scale"],
                    tuple(c["gameRect"]),
                )
                for c in card["candidates"]
            )
            result = decide_identity(card["position"], candidates)
            assert result.character_name == card["expectedName"], (case["id"], card["position"])
            recognized += result.status == "recognized"
            unknown += result.status == "unknown"
    assert (recognized, unknown) == (65, 20)


def test_load_fixed_references():
    references = load_references(FIXTURES / "manifest.json")
    assert len(references) == 3
    assert all(r.image.mode == "RGB" for r in references)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("imagePath", "../outside.png"),
        ("imagePath", "C:/outside.png"),
        ("imagePath", "https://host/a.png"),
        ("imageSize", [1, 1]),
        ("reviewed", "true"),
        ("imageSize", [True, 100]),
    ],
)
def test_rejects_invalid_reference(tmp_path, key, value):
    data = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    data["references"][0][key] = value
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_references(path)


def test_matcher_rejects_identical_images_with_different_names():
    refs = tuple(
        CardReference(index, name, 1, Image.new("RGB", (16, 16)), (16, 16))
        for index, name in enumerate(("a", "b"), 1)
    )
    results = CardIdentityRecognizer(refs).recognize(Image.new("RGB", (1920, 1080)))
    assert len(results) == 5
    assert all(
        r.status == "ambiguous" and r.character_name is None and r.margin == 0 for r in results
    )


def test_signed_difference_and_frame_offset():
    refs = tuple(
        CardReference(index, name, 1, Image.new("RGB", (16, 16), color), (16, 16))
        for index, (name, color) in enumerate((("black", "black"), ("white", "white")), 1)
    )
    recognizer = CardIdentityRecognizer(refs)
    screenshot = Image.new("RGB", (1962, 1114), "white")
    screenshot.paste(Image.new("RGB", (1920, 1080)), (0, 34))
    results = recognizer.recognize(screenshot)
    assert all(r.character_name == "black" and r.score == 0 and r.margin == 255 for r in results)


def test_no_references_and_unknown_layout():
    recognizer = CardIdentityRecognizer(())
    assert all(
        r.reason == "no_references" for r in recognizer.recognize(Image.new("RGB", (1920, 1080)))
    )
    with pytest.raises(ValueError, match="layout"):
        recognizer.recognize(Image.new("RGB", (100, 100)))


def test_vectorized_search_matches_exhaustive_pillow():
    from backend.experiments.r26_match import match

    reference = load_references(FIXTURES / "manifest.json")[0]
    # Fixed pixels generated in memory: tests never modify image fixtures.
    screenshot = Image.new("RGB", (1920, 1080), (128, 128, 128))
    screenshot.paste(reference.image.resize((168, 160), Image.Resampling.LANCZOS), (100, 580))
    reduced = screenshot.resize((480, 270), Image.Resampling.LANCZOS)
    expected = match(reduced, reference.image, 0, search_top=560)
    result = CardIdentityRecognizer((reference,)).recognize(screenshot)[0].candidates[0]
    assert result.score == expected["score"]
    assert result.scale == expected["scale"]
    assert result.game_rect == tuple(expected["gameRect"])


def test_unreviewed_images_are_not_loaded(tmp_path):
    data = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    for entry in data["references"]:
        entry["reviewed"] = False
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_references(path) == ()


def test_duplicate_ids_and_png_dimensions(tmp_path):
    shutil.copytree(FIXTURES / "images", tmp_path / "images")
    data = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    path = tmp_path / "manifest.json"
    data["references"].append(data["references"][0])
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_references(path)
    data["references"].pop()
    data["references"][0]["imagePath"] = data["references"][1]["imagePath"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="imagePath"):
        load_references(path)


@pytest.mark.parametrize("version", [True, "2", 1, 3, None])
def test_rejects_unknown_or_coerced_schema_version(tmp_path, version):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schemaVersion": version, "references": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        load_references(path)


def test_resized_reference_metadata_and_alpha(tmp_path):
    data = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    data["references"] = data["references"][:1]
    entry = data["references"][0]
    entry["imageSize"] = [32, 32]
    entry["transform"] = {"resize": [32, 32], "resample": "LANCZOS"}
    (tmp_path / "images").mkdir()
    target = tmp_path / entry["imagePath"]
    Image.new("RGBA", (32, 32), (1, 2, 3, 0)).save(target)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    ref = load_references(manifest)[0]
    assert ref.crop_size == (105, 100)
    assert ref.image.getpixel((0, 0)) == (255, 255, 255)
    Image.new("RGB", (32, 32)).save(target, format="JPEG")
    with pytest.raises(ValueError, match="PNG"):
        load_references(manifest)


def test_invalid_source_crop(tmp_path):
    data = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    data["references"][0]["source"]["crop"] = [1900, 0, 105, 100]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="crop"):
        load_references(path)
