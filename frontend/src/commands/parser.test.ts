import { describe, expect, it } from "vitest";
import {
  CommandParseError,
  parseScenarioCommand,
  type CommandParseErrorCode,
} from "./parser";

const location = { groupIndex: 1, commandIndex: 2 };

describe("parseScenarioCommand", () => {
  it.each([
    ["skill(0)", { type: "skill", skillIndex: 0 }],
    ["skill(8,5)", { type: "skill", skillIndex: 8, targetIndex: 5 }],
    ["master_skill(2)", { type: "master_skill", skillIndex: 2 }],
    [
      "master_skill(0,2)",
      { type: "master_skill", skillIndex: 0, targetIndex: 2 },
    ],
    ["attack()", { type: "attack", noblePhantasmIndexes: [] }],
    ["attack(2,0,1)", { type: "attack", noblePhantasmIndexes: [2, 0, 1] }],
    ["swap(2,3)", { type: "swap", frontIndex: 2, backIndex: 3 }],
  ])("parses %s", (source, expected) => {
    expect(parseScenarioCommand(source, location)).toEqual(expected);
  });

  it.each<[string, CommandParseErrorCode]>([
    ["heal(0)", "UNKNOWN_COMMAND"],
    ["Skill(0)", "INVALID_FORMAT"],
    ["skill (0)", "INVALID_FORMAT"],
    [" skill(0)", "INVALID_FORMAT"],
    ["skill(0)junk", "INVALID_FORMAT"],
    ["skill(01)", "INVALID_FORMAT"],
    ["skill(-1)", "INVALID_FORMAT"],
    ["skill(1.0)", "INVALID_FORMAT"],
    ["skill(1+1)", "INVALID_FORMAT"],
    ["skill(0,)", "INVALID_FORMAT"],
    ["skill()", "INVALID_ARGUMENT_COUNT"],
    ["skill(9)", "OUT_OF_RANGE"],
    ["master_skill(0,3)", "OUT_OF_RANGE"],
    ["attack(0,1,2,0)", "INVALID_ARGUMENT_COUNT"],
    ["attack(0,0)", "DUPLICATE_ARGUMENT"],
    ["swap(3,4)", "OUT_OF_RANGE"],
    ["swap(0,2)", "OUT_OF_RANGE"],
    ["swap(0)", "INVALID_ARGUMENT_COUNT"],
  ])("rejects %s as %s", (source, code) => {
    expect(() => parseScenarioCommand(source, location)).toThrowError(
      expect.objectContaining({ code, location }),
    );
  });

  it("returns an error carrying the JSON command location and reason", () => {
    try {
      parseScenarioCommand("attack(2,2)", location);
      throw new Error("expected parsing to fail");
    } catch (error) {
      expect(error).toBeInstanceOf(CommandParseError);
      expect(error).toMatchObject({
        code: "DUPLICATE_ARGUMENT",
        location,
      });
      expect((error as Error).message).not.toBe("");
    }
  });
});
