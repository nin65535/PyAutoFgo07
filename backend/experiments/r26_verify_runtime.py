"""Compare production matching with saved exhaustive PIL scores and time it."""

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from time import perf_counter

from PIL import Image
from r26_match import match

from autofgo.card_identity import CardIdentityRecognizer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = Path("card-data/evaluation/manifest.json")
    evaluation = json.loads(manifest_path.read_text(encoding="utf-8"))
    review = json.loads(
        Path("documents/verification/r26-appearance-review.json").read_text(encoding="utf-8")
    )
    registered = {
        case["id"]: {card["position"]: card["registered"] for card in case["cards"]}
        for case in review["cases"]
    }
    baseline = json.loads(
        Path("documents/verification/r26-expanded-scores.json").read_text(encoding="utf-8")
    )
    expected = {Path(case["imagePath"]).resolve(): case for case in baseline["cases"]}
    references_path = Path("card-data/references/manifest.json")
    assert (
        hashlib.sha256(references_path.read_bytes()).hexdigest()
        == baseline["referenceManifestSha256"]
    )
    for reference in baseline["references"]:
        path = references_path.parent / "images" / (reference["id"] + ".png")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == reference["sha256"]
    started = perf_counter()
    recognizer = CardIdentityRecognizer.from_manifest(references_path)
    output = {
        "prepareSeconds": perf_counter() - started,
        "policy": {"maxMae": 40, "minMargin": 10},
        "cases": [],
    }
    counts = Counter()
    for case_index, case in enumerate(evaluation["cases"]):
        path = (manifest_path.parent / case["imagePath"]).resolve()
        old = expected[path]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == old["sha256"]
        with Image.open(path) as opened:
            image = opened.copy()
        started = perf_counter()
        results = recognizer.recognize(image)
        elapsed = perf_counter() - started
        cards = []
        for result, previous in zip(results, old["cards"], strict=True):
            known = registered[case["id"]][result.position]
            assert result.status == ("recognized" if known else "unknown")
            assert result.character_name == (
                case["cards"][result.position]["characterName"] if known else None
            )
            counts[result.status] += 1
            candidates = []
            for current, saved in zip(result.candidates, previous["candidates"], strict=True):
                assert current.reference_id == saved["referenceId"]
                assert abs(current.score - saved["score"]) < 0.0001
                assert current.scale == saved["scale"]
                assert list(current.game_rect) == saved["gameRect"]
                candidates.append(
                    {
                        "referenceId": current.reference_id,
                        "characterName": current.character_name,
                        "score": current.score,
                        "scale": current.scale,
                        "gameRect": current.game_rect,
                    }
                )
            cards.append(
                {
                    "position": result.position,
                    "status": result.status,
                    "reason": result.reason,
                    "characterName": result.character_name,
                    "differentCharacterMargin": result.margin,
                    "candidates": candidates,
                }
            )
        output["cases"].append(
            {
                "id": case["id"],
                "imagePath": path.relative_to(Path.cwd()).as_posix(),
                "sha256": old["sha256"],
                "elapsedSeconds": elapsed,
                "baselineElapsedSeconds": old["elapsedSeconds"],
                "cards": cards,
            }
        )
        if case_index in (0, len(evaluation["cases"]) - 1):
            game = image.convert("RGB").crop((0, 34, 1920, 1114))
            reduced = game.resize((480, 270), Image.Resampling.LANCZOS)
            from autofgo.card_identity import load_references

            references = load_references(references_path)
            started = perf_counter()
            for position in range(5):
                for reference in references:
                    match(reduced, reference.image, position, search_top=560)
            output["cases"][-1]["sameProcessPillowSeconds"] = perf_counter() - started
        print(case["id"], round(elapsed, 4), [r.status for r in results], flush=True)
    output["medianSeconds"] = statistics.median(c["elapsedSeconds"] for c in output["cases"])
    output["baselineMedianSeconds"] = statistics.median(
        c["baselineElapsedSeconds"] for c in output["cases"]
    )
    output["candidateScoresAndLocationsMatch"] = True
    output["runtimeCounts"] = dict(counts)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("median", output["medianSeconds"], "baseline", output["baselineMedianSeconds"])


if __name__ == "__main__":
    main()
