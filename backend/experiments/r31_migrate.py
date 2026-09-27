"""One-time v1 reference migration; keep the explicit mapping for auditability."""

import json
from pathlib import Path

from autofgo.card_references import validate_manifest


def migrate(path: Path) -> dict[str, int]:
    old = json.loads(path.read_text(encoding="utf-8"))
    if old.get("schemaVersion") != 1:
        raise ValueError("expected a version 1 manifest")
    names = list(dict.fromkeys(entry["characterName"] for entry in old["references"]))
    characters = []
    appearance_maps = {}
    for cid, name in enumerate(names, 1):
        appearances = list(
            dict.fromkeys(
                e["appearanceId"] for e in old["references"] if e["characterName"] == name
            )
        )
        appearance_maps[name] = {label: index for index, label in enumerate(appearances, 1)}
        characters.append(
            {
                "id": cid,
                "name": name,
                "nextAppearanceId": len(appearances) + 1,
                "appearances": list(range(1, len(appearances) + 1)),
                "nextSampleNumbers": {
                    str(index): sum(
                        e["characterName"] == name and e["appearanceId"] == label
                        for e in old["references"]
                    )
                    + 1
                    for index, label in enumerate(appearances, 1)
                },
            }
        )
    mapping = {}
    references = []
    moves = []
    for rid, old_entry in enumerate(old["references"], 1):
        entry = old_entry.copy()
        name = entry.pop("characterName")
        old_id = entry["id"]
        mapping[old_id] = rid
        cid = names.index(name) + 1
        aid = appearance_maps[name][entry["appearanceId"]]
        sample = (
            sum(1 for e in references if e["characterId"] == cid and e["appearanceId"] == aid) + 1
        )
        entry.update(
            id=rid,
            characterId=cid,
            appearanceId=aid,
            sampleNumber=sample,
            imagePath=f"images/{name}-{aid}-{sample:02d}.png",
        )
        moves.append((path.parent / old_entry["imagePath"], path.parent / entry["imagePath"]))
        references.append(entry)
    data = {
        "schemaVersion": 2,
        "nextCharacterId": len(names) + 1,
        "nextReferenceId": len(references) + 1,
        "characters": characters,
        "references": references,
    }
    validate_manifest(data, path.parent)
    for source, target in moves:
        if not source.is_file() or target.exists():
            raise ValueError(f"cannot move {source} to {target}")
    for source, target in moves:
        source.rename(target)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return mapping


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    print(migrate(root / "card-data/references/manifest.json"))
