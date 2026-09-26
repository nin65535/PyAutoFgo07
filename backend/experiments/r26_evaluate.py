"""Evaluate saved R26 scores without feeding labels into matching."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-mae", type=float, default=40.0)
    args = parser.parse_args()
    manifest_path = Path("card-data/evaluation/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    review = json.loads(
        Path("documents/verification/r26-appearance-review.json").read_text(encoding="utf-8")
    )
    scores = json.loads(args.scores.read_text(encoding="utf-8"))
    by_path = {Path(case["imagePath"]).resolve(): case for case in scores["cases"]}
    appearance = {case["id"]: case for case in review["cases"]}
    if len(by_path) != len(manifest["cases"]):
        raise ValueError("score set must contain every evaluation image exactly once")
    output = {"maxMae": args.max_mae, "appearanceReview": review["reviewer"], "cases": []}
    total = Counter()
    additional = Counter()
    grouped = {}
    for case in manifest["cases"]:
        path = (manifest_path.parent / case["imagePath"]).resolve()
        predicted = by_path[path]
        if hashlib.sha256(path.read_bytes()).hexdigest() != predicted["sha256"]:
            raise ValueError(f"image changed since matching: {path}")
        actual = {card["position"]: card for card in predicted["cards"]}
        reviewed = {
            card["position"]: card["registered"] for card in appearance[case["id"]]["cards"]
        }
        if set(actual) != set(range(5)) or set(reviewed) != set(range(5)):
            raise ValueError("each image requires five cards and appearance reviews")
        counts = Counter()
        cards = []
        for truth in case["cards"]:
            position = truth["position"]
            candidate = actual[position]["candidates"][0]
            accepted = candidate["score"] <= args.max_mae
            known = reviewed[position]
            correct_name = candidate["characterName"] == truth["characterName"]
            if known:
                outcome = (
                    "knownCorrect"
                    if accepted and correct_name
                    else "knownWrong"
                    if accepted
                    else "knownRejected"
                )
            else:
                outcome = "unknownAccepted" if accepted else "unknownRejected"
            counts[outcome] += 1
            counts["cards"] += 1
            if accepted and not correct_name:
                counts["acceptedWrongName"] += 1
            cards.append(
                {
                    **truth,
                    "registered": known,
                    "candidate": candidate["characterName"],
                    "score": candidate["score"],
                    "margin": actual[position]["differentCharacterMargin"],
                    "outcome": outcome,
                }
            )
        total.update(counts)
        if case["id"] not in {"battle0-img1", "battle0-img8"}:
            additional.update(counts)
        grouped.setdefault(case["captureGroup"], Counter()).update(counts)
        output["cases"].append(
            {
                "id": case["id"],
                "captureGroup": case["captureGroup"],
                "counts": dict(counts),
                "cards": cards,
            }
        )
    output.update(
        totals=dict(total),
        additional15Images=dict(additional),
        captureGroups={key: dict(value) for key, value in grouped.items()},
    )
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"totals": total, "additional15Images": additional}, ensure_ascii=False))


if __name__ == "__main__":
    main()
