/*
 * Fails when a screen hardcodes a colour or a control height instead of using
 * a registered design token.
 *
 * `shared/ui` is the only place allowed to spell out geometry and raw values,
 * because that is where the tokens are turned into components. Everywhere else
 * a `bg-[var(--surface-low)]` or an `h-10` is a second source of truth: the
 * geometry of a control drifts per screen, and a colour written by hand does
 * not follow the runtime/theme palette swap.
 *
 * Nothing is grandfathered — the tree is clean, so any hit is new.
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const sourceRoot = path.resolve(scriptDir, "../web/src");
const extensions = new Set([".ts", ".tsx", ".css"]);

/** `shared/ui` owns the primitives, so it may spell values out. */
const exemptPrefixes = ["shared/ui/", "shared/styles/"];

const rules = [
  {
    // bg-[#123456], text-[var(--x)], border-[rgb(...)], shadow-[0_0_0_rgba()]
    pattern:
      /\b[a-z-]+(?<!\bdata)(?<!\baria)-\[[^\]]*(?:var\(--|#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\()[^\]]*\]/g,
    hint: "Register the colour in the `@theme inline` block of globals.css and use the token class (bg-surface-low, text-code-fg, shadow-panel).",
  },
  {
    // min-h-[60px], w-[12px], gap-[3px] — px geometry does not scale with zoom.
    pattern: /\b[a-z-]+-\[[^\]]*\d+px[^\]]*\]/g,
    hint: "Use the spacing scale or a named token instead of a px geometry value.",
  },
  {
    // h-9 / h-10 / min-h-10 / size-9: the control height belongs to the token.
    pattern: /\b(?:min-|max-|size-)?h-(?:9|10)\b/g,
    hint: "Use the shared control height token (h-control / min-h-control) or a shared/ui component.",
  },
];

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
  const relativePath = path
    .relative(sourceRoot, filePath)
    .split(path.sep)
    .join("/");
  if (exemptPrefixes.some((prefix) => relativePath.startsWith(prefix))) continue;

  const lines = (await fs.readFile(filePath, "utf8")).split(/\r?\n/);
  lines.forEach((line, index) => {
    for (const rule of rules) {
      for (const match of line.match(rule.pattern) ?? []) {
        violations.push({
          relativePath,
          lineNumber: index + 1,
          match,
          hint: rule.hint,
        });
      }
    }
  });
}

if (violations.length > 0) {
  console.error("Console design token check failed:");
  for (const violation of violations) {
    console.error(
      `- ${violation.relativePath}:${violation.lineNumber}: ${violation.match}\n  ${violation.hint}`,
    );
  }
  process.exit(1);
}
