import { useEffect, useState } from "react";
import ReactMarkdown, { type UrlTransform } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import type { ThemedToken } from "shiki/types";
import { useAppearance } from "@/shared/theme/appearance-provider";

type HighlighterModule = typeof import("@/shared/ui/highlighter");

let highlighterModule: Promise<HighlighterModule> | null = null;
let highlighterPromise: ReturnType<
  HighlighterModule["createHighlighter"]
> | null = null;

/**
 * Shiki is loaded on the first fenced code block, not with the bundle: most
 * screens never render one, and the engine plus its grammars are the single
 * largest dependency in the console.
 */
async function loadHighlighter() {
  highlighterModule ??= import("@/shared/ui/highlighter");
  const module = await highlighterModule;
  highlighterPromise ??= module.createHighlighter();
  return { highlighter: await highlighterPromise, module };
}

export const safeUrlTransform: UrlTransform = (url) => {
  const trimmed = url.trim();
  if (
    trimmed.startsWith("#") ||
    trimmed.startsWith("./") ||
    trimmed.startsWith("../") ||
    (trimmed.startsWith("/") && !trimmed.startsWith("//"))
  )
    return trimmed;
  try {
    const parsed = new URL(trimmed);
    return ["http:", "https:", "mailto:"].includes(parsed.protocol)
      ? trimmed
      : "";
  } catch {
    return "";
  }
};

function tokenStyle(token: ThemedToken) {
  const fontStyle = token.fontStyle ?? 0;
  return {
    color: token.color,
    fontStyle: fontStyle & 1 ? "italic" : undefined,
    fontWeight: fontStyle & 2 ? 700 : undefined,
    textDecoration: fontStyle & 4 ? "underline" : undefined,
  } as const;
}

function HighlightedCode({
  code,
  language,
}: {
  code: string;
  language: string;
}) {
  const { theme } = useAppearance();
  const [lines, setLines] = useState<ThemedToken[][] | null>(null);

  useEffect(() => {
    let active = true;
    // Until shiki arrives the block renders as plain text, so an unsupported
    // language or a failed chunk load degrades to unhighlighted code.
    loadHighlighter()
      .then(({ highlighter, module }) => {
        if (!active) return;
        const result = highlighter.codeToTokens(code, {
          lang: module.normalizeLanguage(language),
          theme: theme === "dark" ? "github-dark" : "github-light",
        });
        setLines(result.tokens);
      })
      .catch(() => {
        if (active) setLines(null);
      });
    return () => {
      active = false;
    };
  }, [code, language, theme]);

  return (
    <code className="block min-w-max p-4 font-mono text-sm leading-6">
      {lines
        ? lines.map((line) => (
            <span
              className="block min-h-6"
              key={`${line[0]?.offset ?? "empty"}:${line.map((token) => token.content).join("")}`}
            >
              {line.map((token) => (
                <span key={token.offset} style={tokenStyle(token)}>
                  {token.content}
                </span>
              ))}
            </span>
          ))
        : code}
    </code>
  );
}

export function MarkdownContent({ source }: { source: string }) {
  return (
    <div
      className="min-w-0 text-sm leading-6 text-foreground [&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4 [&_blockquote]:border-l-2 [&_blockquote]:border-primary/50 [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground [&_code]:rounded [&_code]:bg-code-bg [&_code]:px-1.5 [&_code]:py-0.5 [&_li]:my-1 [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:my-2 [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-border-soft [&_pre]:bg-code-bg [&_table]:my-3 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-border-soft [&_td]:p-2 [&_th]:border [&_th]:border-border-soft [&_th]:bg-surface-low [&_th]:p-2 [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-6"
      data-testid="timeline-markdown"
    >
      <ReactMarkdown
        components={{
          a: ({ children, href }) => (
            <a href={href || undefined} rel="noreferrer" target="_blank">
              {children}
            </a>
          ),
          code: ({ children, className }) => {
            const language = /language-([\w-]+)/.exec(className ?? "")?.[1];
            const code = String(children).replace(/\n$/, "");
            return language ? (
              <HighlightedCode code={code} language={language} />
            ) : (
              <code className={className}>{children}</code>
            );
          },
        }}
        remarkPlugins={[remarkGfm, remarkBreaks]}
        urlTransform={safeUrlTransform}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
