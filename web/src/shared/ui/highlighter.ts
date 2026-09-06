import { createBundledHighlighter } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";

/**
 * Shiki's core and its regex engine live in this module alone so that
 * `markdown.tsx` can reach them through a dynamic import. Nothing here is
 * loaded until a fenced code block with a language is actually rendered.
 */
const languageLoaders = {
  bash: () => import("@shikijs/langs/bash"),
  css: () => import("@shikijs/langs/css"),
  diff: () => import("@shikijs/langs/diff"),
  html: () => import("@shikijs/langs/html"),
  javascript: () => import("@shikijs/langs/javascript"),
  json: () => import("@shikijs/langs/json"),
  markdown: () => import("@shikijs/langs/markdown"),
  python: () => import("@shikijs/langs/python"),
  tsx: () => import("@shikijs/langs/tsx"),
  typescript: () => import("@shikijs/langs/typescript"),
};

const themeLoaders = {
  "github-dark": () => import("@shikijs/themes/github-dark"),
  "github-light": () => import("@shikijs/themes/github-light"),
};

export type SupportedLanguage = keyof typeof languageLoaders;

const supportedLanguages = new Set<string>(Object.keys(languageLoaders));

/** Unknown languages fall back to plain text rather than failing the render. */
export function normalizeLanguage(
  language: string,
): SupportedLanguage | "text" {
  return supportedLanguages.has(language)
    ? (language as SupportedLanguage)
    : "text";
}

const createConsoleHighlighter = createBundledHighlighter({
  engine: () => createJavaScriptRegexEngine(),
  langs: languageLoaders,
  themes: themeLoaders,
});

export function createHighlighter() {
  return createConsoleHighlighter({
    langs: Object.keys(languageLoaders) as SupportedLanguage[],
    themes: ["github-dark", "github-light"],
  });
}
