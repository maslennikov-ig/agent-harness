/*
 * SPDX-License-Identifier: Apache-2.0
 * Adapted from block/buzz at commit 1ff98fa. See docs/vendored-from-buzz.md.
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const TEXT_ARBITRARY_RE = /\btext-\[\d+(?:\.\d+)?(?:px|rem|em)\]/g;
const FONT_SIZE_PX_RE = /(?<!-)\bfont-size:\s*\d+(?:\.\d+)?px/g;
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const sourceRoot = path.resolve(scriptDir, "../web/src");
const extensions = new Set([".ts", ".tsx", ".css"]);

async function walkFiles(directory) {
  const entries = await fs.readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const fullPath = path.join(directory, entry.name);
      return entry.isDirectory() ? walkFiles(fullPath) : [fullPath];
    }),
  );
  return nested.flat();
}

const violations = [];
for (const filePath of await walkFiles(sourceRoot)) {
  if (!extensions.has(path.extname(filePath))) continue;
  const relativePath = path.relative(sourceRoot, filePath).split(path.sep).join("/");
  const lines = (await fs.readFile(filePath, "utf8")).split(/\r?\n/);
  lines.forEach((line, index) => {
    const matches = [
      ...(line.match(TEXT_ARBITRARY_RE) ?? []),
      ...(line.match(FONT_SIZE_PX_RE) ?? []),
    ];
    for (const match of matches) {
      violations.push({ relativePath, lineNumber: index + 1, match });
    }
  });
}

if (violations.length > 0) {
  console.error("Console px-text check failed:");
  for (const violation of violations) {
    console.error(
      `- ${violation.relativePath}:${violation.lineNumber}: ${violation.match}`,
    );
  }
  console.error(
    "Use named rem-based text tokens so browser zoom keeps readable text on one scale.",
  );
  process.exit(1);
}
