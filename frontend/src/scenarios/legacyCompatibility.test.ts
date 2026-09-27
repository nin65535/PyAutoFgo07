import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { validateScenario } from "./scenario";

const scenarioDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../scenarios",
);

const convertedFiles = [
  "10 ev++.json",
  "10 アズライール.json",
  "10 ギルガメッシュ.json",
  "10 グランマリー2.json",
  "10 ステラマリー.json",
  "10 ソロモン.json",
  "10 ノア.json",
  "10 ヘラクレス.json",
  "20 ひき逃げ.json",
  "20 めりゅ子.json",
  "20 モルガン.json",
  "20 首吊り.json",
  "20 青王.json",
  "30 カジノ3.json",
  "30 ハンティング.json",
  "30 禁断の頁.json",
  "30 月光.json",
  "30 常夏即売会場.json",
  "30 精霊根.json",
  "30 聖剣2連.json",
];

describe("converted legacy scenario compatibility", () => {
  it("validates all 20 converted files and parses all 310 commands", async () => {
    const typeCounts: Record<string, number> = {};
    let commandCount = 0;

    expect(convertedFiles).toHaveLength(20);
    for (const file of convertedFiles) {
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
