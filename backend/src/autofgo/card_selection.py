"""Deterministic allocation of a recognized hand to three attack slots."""

import re
from dataclasses import dataclass

SLOT_PATTERN = re.compile(r"(?:N[0-2]|(?:[BAQ][0-2])*)\Z")


@dataclass(frozen=True, slots=True)
class RecognizedCard:
    position: int
    color: str
    character_name: str


@dataclass(frozen=True, slots=True)
class CardChoice:
    kind: str
    position: int
    matched_preference: str | None = None


def validate_slots(slots: list[str]) -> None:
    if len(slots) != 3 or any(not SLOT_PATTERN.fullmatch(slot) for slot in slots):
        raise ValueError("attack slots must be three NP tokens or card preference strings")
    nps = [slot for slot in slots if slot.startswith("N")]
    if len(nps) != len(set(nps)):
        raise ValueError("noble phantasm indexes cannot be repeated")


def select_cards(
    slots: list[str], cards: list[RecognizedCard], front_members: list[str]
) -> tuple[CardChoice, CardChoice, CardChoice]:
    """Reserve preferred cards right to left, then fill gaps from the left."""
    validate_slots(slots)
    if len(cards) != 5 or sorted(card.position for card in cards) != list(range(5)):
        raise ValueError("exactly five distinct card positions are required")
    if len(front_members) != 3:
        raise ValueError("exactly three front members are required")
    if any(card.color not in {"B", "A", "Q"} or not card.character_name for card in cards):
        raise ValueError("all card colors and names must be recognized")
    if any(not name for name in front_members):
        raise ValueError("front member names are required")
    cards_by_position = sorted(cards, key=lambda card: card.position)
    chosen: list[CardChoice | None] = [None, None, None]
    used: set[int] = set()
    for index in range(2, -1, -1):
        slot = slots[index]
        if slot.startswith("N"):
            chosen[index] = CardChoice("np", int(slot[1]))
            continue
        for offset in range(0, len(slot), 2):
            preference = slot[offset : offset + 2]
            color, member_index = preference[0], int(preference[1])
            name = front_members[member_index]
            if front_members.count(name) > 1:
                raise ValueError(f"duplicate front member cannot be identified: {name}")
            match = next(
                (
                    card
                    for card in cards_by_position
                    if card.position not in used
                    and card.color == color
                    and card.character_name == name
                ),
                None,
            )
            if match is not None:
                chosen[index] = CardChoice("card", match.position, preference)
                used.add(match.position)
                break
    for index, choice in enumerate(chosen):
        if choice is None:
            match = next(card for card in cards_by_position if card.position not in used)
            chosen[index] = CardChoice("card", match.position)
            used.add(match.position)
    assert all(choice is not None for choice in chosen)
    return tuple(chosen)  # type: ignore[return-value]
