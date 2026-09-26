import type { ScenarioCommand } from "./types";

export type CommandLocation = {
  groupIndex: number;
  commandIndex: number;
};

export type CommandParseErrorCode =
  | "INVALID_FORMAT"
  | "UNKNOWN_COMMAND"
  | "INVALID_ARGUMENT_COUNT"
  | "OUT_OF_RANGE"
  | "DUPLICATE_ARGUMENT";

export class CommandParseError extends Error {
  readonly code: CommandParseErrorCode;
  readonly location: CommandLocation;

  constructor(
    code: CommandParseErrorCode,
    location: CommandLocation,
    message: string,
  ) {
    super(message);
    this.name = "CommandParseError";
    this.code = code;
    this.location = location;
  }
}

const COMMAND_PATTERN = /^([a-z_]+)\(([^()]*)\)$/;
const INTEGER_PATTERN = /^(0|[1-9][0-9]*)$/;
const KNOWN_COMMANDS = new Set(["skill", "master_skill", "attack", "swap"]);

function fail(
  code: CommandParseErrorCode,
  location: CommandLocation,
  message: string,
): never {
  throw new CommandParseError(code, location, message);
}

function parseArguments(raw: string, location: CommandLocation): number[] {
  if (raw === "") return [];

  const values = raw.split(",");
  if (values.some((value) => !INTEGER_PATTERN.test(value))) {
    fail(
      "INVALID_FORMAT",
      location,
      "引数は先頭ゼロのない非負整数で指定してください",
    );
  }
  return values.map(Number);
}

function requireArgumentCount(
  args: number[],
  allowed: readonly number[],
  location: CommandLocation,
): void {
  if (!allowed.includes(args.length)) {
    fail(
      "INVALID_ARGUMENT_COUNT",
      location,
      `引数の個数が不正です（許可: ${allowed.join(" または ")}個）`,
    );
  }
}

function requireRange(
  value: number,
  name: string,
  minimum: number,
  maximum: number,
  location: CommandLocation,
): void {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    fail(
      "OUT_OF_RANGE",
      location,
      `${name}は${minimum}以上${maximum}以下で指定してください`,
    );
  }
}

export function parseScenarioCommand(
  source: string,
  location: CommandLocation,
): ScenarioCommand {
  const match = COMMAND_PATTERN.exec(source);
  if (!match) {
    fail("INVALID_FORMAT", location, "命令が定義済みの形式に一致しません");
  }

  const [, name, rawArguments] = match;
  if (!KNOWN_COMMANDS.has(name)) {
    fail("UNKNOWN_COMMAND", location, `未対応の命令です: ${name}`);
  }
  const args =
    name === "attack" && rawArguments.startsWith("'")
      ? []
      : parseArguments(rawArguments, location);

  switch (name) {
    case "skill": {
      requireArgumentCount(args, [1, 2], location);
      requireRange(args[0], "skillIndex", 0, 8, location);
      if (args.length === 2) {
        requireRange(args[1], "targetIndex", 0, 5, location);
        return { type: "skill", skillIndex: args[0], targetIndex: args[1] };
      }
      return { type: "skill", skillIndex: args[0] };
    }
    case "master_skill": {
      requireArgumentCount(args, [1, 2], location);
      requireRange(args[0], "skillIndex", 0, 2, location);
      if (args.length === 2) {
        requireRange(args[1], "targetIndex", 0, 2, location);
        return {
          type: "master_skill",
          skillIndex: args[0],
          targetIndex: args[1],
        };
      }
      return { type: "master_skill", skillIndex: args[0] };
    }
    case "attack": {
      if (rawArguments.startsWith("'")) {
        const tokens = rawArguments.split(",");
        if (tokens.length < 1 || tokens.length > 3) {
          fail("INVALID_ARGUMENT_COUNT", location, "カード指定は3枠までです");
        }
        const slots = tokens.map((token) => {
          if (!/^'(?:N[0-2]|(?:[BAQ][0-2])*)'$/.test(token)) {
            fail("INVALID_FORMAT", location, "カード指定の形式が不正です");
          }
          return token.slice(1, -1);
        });
        while (slots.length < 3) slots.push("");
        const nps = slots.filter((slot) => slot.startsWith("N"));
        if (new Set(nps).size !== nps.length) {
          fail(
            "DUPLICATE_ARGUMENT",
            location,
            "宝具インデックスは重複指定できません",
          );
        }
        return {
          type: "attack",
          noblePhantasmIndexes: [],
          cardSlots: slots as [string, string, string],
        };
      }
      requireArgumentCount(args, [0, 1, 2, 3], location);
      args.forEach((value) =>
        requireRange(value, "noblePhantasmIndex", 0, 2, location),
      );
      if (new Set(args).size !== args.length) {
        fail(
          "DUPLICATE_ARGUMENT",
          location,
          "宝具インデックスは重複指定できません",
        );
      }
      return { type: "attack", noblePhantasmIndexes: args };
    }
    case "swap": {
      requireArgumentCount(args, [2], location);
      requireRange(args[0], "frontIndex", 0, 2, location);
      requireRange(args[1], "backIndex", 3, 5, location);
      return { type: "swap", frontIndex: args[0], backIndex: args[1] };
    }
    default:
      return fail("UNKNOWN_COMMAND", location, `未対応の命令です: ${name}`);
  }
}
