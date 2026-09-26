import pytest
from pydantic import ValidationError

from autofgo.card_selection import RecognizedCard, select_cards, validate_slots
from autofgo.commands import AttackCommand

CARDS = [
    RecognizedCard(0, "B", "A"),
    RecognizedCard(1, "A", "B"),
    RecognizedCard(2, "B", "B"),
    RecognizedCard(3, "Q", "C"),
    RecognizedCard(4, "B", "B"),
]
MEMBERS = ["A", "B", "C"]


def test_rightmost_preference_wins_and_gaps_fill_left_to_right():
    one_b = CARDS.copy()
    one_b[4] = RecognizedCard(4, "A", "B")
    choices = select_cards(["N1", "B1", "B1"], one_b, MEMBERS)
    assert [(choice.kind, choice.position, choice.matched_preference) for choice in choices] == [
        ("np", 1, None),
        ("card", 0, None),
        ("card", 2, "B1"),
    ]


def test_preference_fallback_and_leftmost_tie():
    choices = select_cards(["Q0A1", "", "B1"], CARDS, MEMBERS)
    assert [choice.position for choice in choices] == [1, 0, 2]
    assert choices[0].matched_preference == "A1"


def test_empty_slots_preserve_old_left_to_right_behavior():
    assert [choice.position for choice in select_cards(["", "", ""], CARDS, MEMBERS)] == [0, 1, 2]


@pytest.mark.parametrize("slots", [["N0", "N0", ""], ["N0B1", "", ""], ["B3", "", ""], ["", ""]])
def test_invalid_slots_are_rejected(slots):
    with pytest.raises(ValueError):
        validate_slots(slots)


def test_duplicate_front_member_is_ambiguous_only_when_requested():
    with pytest.raises(ValueError, match="duplicate"):
        select_cards(["B1", "", ""], CARDS, ["A", "B", "B"])
    assert select_cards(["", "", ""], CARDS, ["A", "B", "B"])


def test_incomplete_recognition_is_rejected():
    with pytest.raises(ValueError, match="five"):
        select_cards(["B1", "", ""], CARDS[:4], MEMBERS)


def test_attack_command_validates_typed_card_slots():
    command = AttackCommand.model_validate(
        {"type": "attack", "noblePhantasmIndexes": [], "cardSlots": ["N1", "B1", "B1"]}
    )
    assert command.card_slots == ["N1", "B1", "B1"]
    with pytest.raises(ValidationError):
        AttackCommand.model_validate(
            {"type": "attack", "noblePhantasmIndexes": [], "cardSlots": ["N1", "N1", ""]}
        )
    with pytest.raises(ValidationError):
        AttackCommand.model_validate(
            {"type": "attack", "noblePhantasmIndexes": [0], "cardSlots": ["", "", ""]}
        )
