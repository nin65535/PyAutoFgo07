import { describe, expect, it } from "vitest";
import { validateScenario } from "./scenario";

describe("validateScenario", () => {
  it("parses every command in a valid scenario", () => {
    const result = validateScenario({
      schemaVersion: 1,
      members: ["A"],
      commands: [["skill(5,2)", "attack(0,1)"]],
    });
    expect(result.valid).toBe(true);
    if (result.valid)
      expect(result.scenario.commands[0][0]).toEqual({
        type: "skill",
        skillIndex: 5,
        targetIndex: 2,
      });
  });

  it("rejects unknown root properties", () => {
    const result = validateScenario({
      schemaVersion: 1,
      members: ["A"],
      commands: [["attack()"]],
      extra: true,
    });
    expect(result).toMatchObject({
      valid: false,
      errors: [{ location: "scenario" }],
    });
  });

  it("collects command errors with zero-based locations", () => {
    const result = validateScenario({
      schemaVersion: 1,
      members: ["A"],
      commands: [["skill(9)"], ["swap(0,2)"]],
    });
    expect(result).toMatchObject({
      valid: false,
      errors: [
        { location: { groupIndex: 0, commandIndex: 0 } },
        { location: { groupIndex: 1, commandIndex: 0 } },
      ],
    });
  });
});
