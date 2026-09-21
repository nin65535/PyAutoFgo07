import {
  CommandParseError,
  parseScenarioCommand,
  type CommandLocation,
} from "../commands/parser";
import type { ScenarioCommand } from "../commands/types";

export type ScenarioSummary = {
  id: string;
  displayName: string;
  modifiedAt: string;
};

export type ScenarioValidationError = {
  location: CommandLocation | "scenario";
  message: string;
};

export type ValidatedScenario = {
  schemaVersion: 1;
  members: string[];
  commandSources: string[][];
  commands: ScenarioCommand[][];
};

export type ScenarioValidation =
  | { valid: true; scenario: ValidatedScenario }
  | { valid: false; errors: ScenarioValidationError[] };

const ROOT_KEYS = ["schemaVersion", "members", "commands"];

export function validateScenario(value: unknown): ScenarioValidation {
  if (!isRecord(value))
    return invalid("ルートはオブジェクトである必要があります");
  const unknownKeys = Object.keys(value).filter(
    (key) => !ROOT_KEYS.includes(key),
  );
  if (unknownKeys.length > 0)
    return invalid(`未定義の項目があります: ${unknownKeys.join(", ")}`);
  if (value.schemaVersion !== 1)
    return invalid("schemaVersionは1である必要があります");
  if (
    !Array.isArray(value.members) ||
    value.members.length < 1 ||
    value.members.length > 6
  )
    return invalid("membersは1件以上6件以下の配列である必要があります");
  if (
    value.members.some(
      (member) =>
        typeof member !== "string" || member.length < 1 || member.length > 100,
    )
  )
    return invalid("各メンバー名は1文字以上100文字以下である必要があります");
  if (
    !Array.isArray(value.commands) ||
    value.commands.length < 1 ||
    value.commands.length > 5
  )
    return invalid(
      "commandsは1グループ以上5グループ以下の配列である必要があります",
    );

  const errors: ScenarioValidationError[] = [];
  const parsedGroups: ScenarioCommand[][] = [];
  const sourceGroups: string[][] = [];
  value.commands.forEach((group, groupIndex) => {
    if (!Array.isArray(group) || group.length < 1 || group.length > 20) {
      errors.push({
        location: "scenario",
        message: `グループ${groupIndex + 1}は1命令以上20命令以下である必要があります`,
      });
      return;
    }
    const parsed: ScenarioCommand[] = [];
    const sources: string[] = [];
    group.forEach((source, commandIndex) => {
      const location = { groupIndex, commandIndex };
      if (
        typeof source !== "string" ||
        source.length < 1 ||
        source.length > 100
      ) {
        errors.push({
          location,
          message: "命令は1文字以上100文字以下の文字列である必要があります",
        });
        return;
      }
      sources.push(source);
      try {
        parsed.push(parseScenarioCommand(source, location));
      } catch (error) {
        errors.push({
          location,
          message:
            error instanceof CommandParseError
              ? error.message
              : "命令を検証できませんでした",
        });
      }
    });
    sourceGroups.push(sources);
    parsedGroups.push(parsed);
  });
  if (errors.length > 0) return { valid: false, errors };
  return {
    valid: true,
    scenario: {
      schemaVersion: 1,
      members: value.members as string[],
      commandSources: sourceGroups,
      commands: parsedGroups,
    },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalid(message: string): ScenarioValidation {
  return { valid: false, errors: [{ location: "scenario", message }] };
}
