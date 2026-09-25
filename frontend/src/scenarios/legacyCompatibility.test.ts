import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { validateScenario } from "./scenario";

const scenarioDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../scenarios",
);

describe("converted legacy scenario compatibility", () => {
  it("validates all 20 converted files and parses all 310 commands", async () => {
    const files = (await readdir(scenarioDirectory))
      .filter((name) => name.endsWith(".json"))
      .sort();
    const typeCounts: Record<string, number> = {};
    let commandCount = 0;

    expect(files).toHaveLength(20);
    for (const file of files) {
      const content: unknown = JSON.parse(
        await readFile(path.join(scenarioDirectory, file), "utf8"),
      );
      const result = validateScenario(content);
      if (!result.valid) {
        throw new Error(`${file}: ${JSON.stringify(result.errors)}`);
      }
      for (const command of result.scenario.commands.flat()) {
        commandCount += 1;
        typeCounts[command.type] = (typeCounts[command.type] ?? 0) + 1;
      }
    }

    expect(commandCount).toBe(310);
    expect(typeCounts).toEqual({
      attack: 42,
      master_skill: 16,
      skill: 235,
      swap: 17,
    });
  });
});
