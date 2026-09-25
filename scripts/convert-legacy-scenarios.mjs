import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const LEGACY_KEYS = ["members", "commands"];

export function convertLegacyScenario(value, sourceName = "legacy scenario") {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${sourceName}: root must be an object`);
  }
  const keys = Object.keys(value);
  const unexpected = keys.filter((key) => !LEGACY_KEYS.includes(key));
  const missing = LEGACY_KEYS.filter((key) => !keys.includes(key));
  if (unexpected.length > 0 || missing.length > 0) {
    throw new Error(
      `${sourceName}: expected only members and commands ` +
        `(missing: ${missing.join(", ") || "none"}; unexpected: ${unexpected.join(", ") || "none"})`,
    );
  }
  if (!Array.isArray(value.members) || !Array.isArray(value.commands)) {
    throw new Error(`${sourceName}: members and commands must be arrays`);
  }

  return { schemaVersion: 1, members: value.members, commands: value.commands };
}

export async function convertDirectory(inputDirectory, outputDirectory) {
  const entries = await readdir(inputDirectory, { withFileTypes: true });
  const files = entries
    .filter((entry) => entry.isFile() && path.extname(entry.name) === ".json")
    .sort((left, right) => left.name.localeCompare(right.name, "ja"));

  await mkdir(outputDirectory, { recursive: true });
  let commandCount = 0;
  for (const file of files) {
    const source = JSON.parse(
      await readFile(path.join(inputDirectory, file.name), "utf8"),
    );
    const converted = convertLegacyScenario(source, file.name);
    commandCount += converted.commands.reduce(
      (count, group) => count + (Array.isArray(group) ? group.length : 0),
      0,
    );
    await writeFile(
      path.join(outputDirectory, file.name),
      `${JSON.stringify(converted, null, 2)}\n`,
      "utf8",
    );
  }
  return { fileCount: files.length, commandCount };
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : undefined;
if (invokedPath === fileURLToPath(import.meta.url)) {
  const [, , inputDirectory, outputDirectory] = process.argv;
  if (!inputDirectory || !outputDirectory) {
    console.error(
      "Usage: node scripts/convert-legacy-scenarios.mjs <legacy-directory> <output-directory>",
    );
    process.exitCode = 2;
  } else {
    try {
      const result = await convertDirectory(inputDirectory, outputDirectory);
      console.log(
        `Converted ${result.fileCount} files and ${result.commandCount} commands.`,
      );
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error));
      process.exitCode = 1;
    }
  }
}
