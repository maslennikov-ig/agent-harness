/*
 * SPDX-License-Identifier: Apache-2.0
 * Adapted from block/buzz at commit 1ff98fa. See docs/vendored-from-buzz.md.
 */

import { execFileSync } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const MAX_LINES = 1000;
const rules = [
  {
    root: "web/src",
    extensions: new Set([".ts", ".tsx", ".css"]),
    maxLines: MAX_LINES,
  },
];

function git(args, options = {}) {
  return execFileSync("git", args, {
    cwd: repoRoot,
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
    ...options,
  });
}

function countLines(content) {
  return content.length === 0 ? 0 : content.split(/\r?\n/).length;
}

function baseRef() {
  if (process.env.CHECK_FILE_SIZES_BASE) {
    return process.env.CHECK_FILE_SIZES_BASE;
  }
  if (process.env.GITHUB_ACTIONS === "true") {
    try {
      git(["cat-file", "-e", "HEAD^1^{commit}"]);
      return "HEAD^1";
    } catch {
      return "HEAD";
    }
  }
  return "HEAD";
}

function parseChanges(output) {
  const fields = output.split("\0");
  const changes = [];
  for (let index = 0; index < fields.length - 1; ) {
    const status = fields[index++];
    if (status.startsWith("R") || status.startsWith("C")) {
      changes.push({ status: status[0], oldPath: fields[index++], path: fields[index++] });
    } else {
      changes.push({ status: status[0], path: fields[index++] });
    }
  }
  return changes;
}

function changedFiles(reference) {
  const changes = parseChanges(
    git(["diff", "--name-status", "-z", "-M", reference, "--", "web"]),
  );
  const tracked = new Set(changes.map((change) => change.path));
  for (const file of git(["ls-files", "--others", "--exclude-standard", "-z", "--", "web"])
    .split("\0")
    .filter(Boolean)) {
    if (!tracked.has(file)) {
      changes.push({ status: "A", path: file });
    }
  }
  return changes;
}

function ruleFor(file) {
  return rules.find((rule) => file.startsWith(`${rule.root}/`));
}

const reference = baseRef();
git(["cat-file", "-e", `${reference}^{commit}`]);
const violations = [];

for (const change of changedFiles(reference)) {
  if (change.status === "D") continue;
  const rule = ruleFor(change.path);
  if (!rule || !rule.extensions.has(path.extname(change.path))) continue;

  const candidateLines = countLines(await fs.readFile(path.join(repoRoot, change.path), "utf8"));
  const basePath = change.oldPath ?? change.path;
  const baseContent =
    change.status === "A"
      ? null
      : git(["show", `${reference}:${basePath}`], { encoding: null }).toString("utf8");
  const baseLines = baseContent == null ? null : countLines(baseContent);
  const limit = baseLines == null || baseLines <= rule.maxLines ? rule.maxLines : baseLines;
  if (candidateLines > limit) {
    violations.push({ file: change.path, baseLines, candidateLines, limit });
  }
}

if (violations.length > 0) {
  console.error(`Console file size ratchet failed (base ${reference}):`);
  for (const violation of violations) {
    console.error(
      `- ${violation.file}: ${violation.baseLines ?? "new"} -> ${violation.candidateLines} lines (allowed ${violation.limit})`,
    );
  }
  console.error("Keep new files at or below the limit; files already over it may not grow.");
  process.exitCode = 1;
}
