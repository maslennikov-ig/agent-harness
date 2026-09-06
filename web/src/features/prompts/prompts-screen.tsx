import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Copy, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import { requestJson } from "@/shared/api/client";
import { useAppearance } from "@/shared/theme/appearance-provider";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Input } from "@/shared/ui/input";
import { RawInspector } from "@/shared/ui/raw-inspector";
import { Select } from "@/shared/ui/select";

interface PromptProfile {
  id: string;
  label: string;
  description: string;
  default: boolean;
}

interface PromptCard {
  id: string;
  title: string;
  category: string;
  library_visibility: "manual" | "system";
  description: string;
  source: string;
  tags: string[];
  usage_count: number;
  launcher_text: string;
  full_text: string;
  launcher_chars: number;
  full_chars: number;
  recommended_mode: "launcher" | "portable";
  profile?: {
    label?: string;
  };
  situations?: {
    tier?: string;
    use?: string[];
    instead?: string[];
    beads?: string;
  };
}

interface RecentCopy {
  ts: number;
  prompt_id: string;
  mode: "launcher" | "full";
  runtime: string;
  profile?: string;
}

interface PromptsPayload {
  runtime: "codex" | "claude";
  source: string;
  manifest_path: string;
  active_profile?: PromptProfile;
  profiles: PromptProfile[];
  prompts: PromptCard[];
  recent_copies: RecentCopy[];
  composition: unknown;
  fragments: unknown;
  error?: string;
}

type RuntimeProfiles = Record<"codex" | "claude", string>;

const PROFILE_STORE_KEY = "orch-prompts.runtime-profiles";

function loadStoredProfiles(): RuntimeProfiles {
  try {
    const parsed = JSON.parse(
      localStorage.getItem(PROFILE_STORE_KEY) || "{}",
    ) as Partial<RuntimeProfiles>;
    return {
      codex: typeof parsed.codex === "string" ? parsed.codex : "",
      claude: typeof parsed.claude === "string" ? parsed.claude : "",
    };
  } catch {
    return { codex: "", claude: "" };
  }
}

function migrateProfile(runtime: "codex" | "claude", profile: string) {
  if (!profile) return { migratedFrom: "", profile: "" };
  const supported =
    runtime === "codex" ? ["gpt-6-astra"] : ["fable-5.1", "opus-5"];
  if (supported.includes(profile)) {
    return { migratedFrom: "", profile };
  }
  return { migratedFrom: profile, profile: supported[0] };
}

function initialRuntimeProfiles(): RuntimeProfiles {
  const stored = loadStoredProfiles();
  return {
    codex: migrateProfile("codex", stored.codex).profile,
    claude: migrateProfile("claude", stored.claude).profile,
  };
}

function storeProfiles(profiles: RuntimeProfiles) {
  try {
    localStorage.setItem(PROFILE_STORE_KEY, JSON.stringify(profiles));
  } catch {
    // Storage is optional; the selected profiles remain active for this session.
  }
}

export function PromptsScreen() {
  const screen = screenById("prompts");
  const { runtime } = useAppearance();
  const [runtimeProfiles, setRuntimeProfiles] = useState<RuntimeProfiles>(
    initialRuntimeProfiles,
  );
  const profile = runtimeProfiles[runtime];
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [showSystem, setShowSystem] = useState(false);
  const [usage, setUsage] = useState<Record<string, number>>({});
  const [copied, setCopied] = useState("");
  const data = useQuery({
    queryKey: ["prompts", runtime, profile],
    queryFn: () => {
      const params = new URLSearchParams({ runtime });
      if (profile) params.set("profile", profile);
      return requestJson<PromptsPayload>(`/api/prompts?${params}`);
    },
  });

  useEffect(() => {
    const stored = loadStoredProfiles();
    for (const target of ["codex", "claude"] as const) {
      const migration = migrateProfile(target, stored[target]);
      if (!migration.migratedFrom) continue;
      storeProfiles(runtimeProfiles);
      toast.info(
        `Сохранённый профиль ${migration.migratedFrom} заменён на ${migration.profile}`,
      );
    }
  }, [runtimeProfiles]);

  useEffect(() => {
    if (!data.data) return;
    const fallback =
      data.data.active_profile?.id ||
      data.data.profiles.find((item) => item.default)?.id ||
      "";
    const resolved = data.data.profiles.some((item) => item.id === profile)
      ? profile
      : fallback;
    if (resolved && resolved !== profile) {
      setRuntimeProfiles((current) => {
        const next = { ...current, [runtime]: resolved };
        storeProfiles(next);
        return next;
      });
    }
  }, [data.data, profile, runtime]);

  const libraryPrompts = useMemo(
    () =>
      (data.data?.prompts ?? []).filter(
        (item) => item.library_visibility === "manual" || showSystem,
      ),
    [data.data?.prompts, showSystem],
  );
  const categories = useMemo(
    () => [...new Set(libraryPrompts.map((item) => item.category))].sort(),
    [libraryPrompts],
  );
  const prompts = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return libraryPrompts.filter((item) => {
      const categoryOk = category === "all" || item.category === category;
      const searchable =
        `${item.title} ${item.description} ${item.tags.join(" ")} ${(item.situations?.use ?? []).join(" ")} ${(item.situations?.instead ?? []).join(" ")}`.toLowerCase();
      return categoryOk && (!needle || searchable.includes(needle));
    });
  }, [category, libraryPrompts, query]);

  const copyPrompt = async (prompt: PromptCard, mode: "launcher" | "full") => {
    const text = mode === "full" ? prompt.full_text : prompt.launcher_text;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      toast.error("Не удалось скопировать");
      return;
    }
    // The usage counter is best-effort: a failed POST must not lose the copy
    // the user just made, so it is reported quietly and the flow continues.
    fetch("/api/prompts/usage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: prompt.id, mode, runtime, profile }),
    }).catch(() => {
      toast.warning("Счётчик использований не обновился");
    });
    setUsage((current) => ({
      ...current,
      [prompt.id]: (current[prompt.id] ?? prompt.usage_count) + 1,
    }));
    setCopied(`${prompt.id}:${mode}`);
    toast.success(`Скопировано: ${prompt.title}`);
  };

  return (
    <ScreenFrame
      actions={
        <Button
          onClick={() => data.refetch()}
          size="sm"
          type="button"
          variant="outline"
        >
          <RefreshCw aria-hidden="true" /> Обновить
        </Button>
      }
      marker={{ kind: "native", id: screen.id }}
      screen={screen}
    >
      <div className="space-y-4">
        <div className="grid gap-3 rounded-xl bg-surface-low p-3 md:grid-cols-[minmax(12rem,1fr)_minmax(10rem,0.5fr)_minmax(10rem,0.5fr)]">
          <label
            className="block text-xs text-muted-foreground"
            htmlFor="prompts-search"
          >
            Поиск
            <span className="relative mt-1 block">
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                className="rounded-lg pl-9 text-sm"
                id="prompts-search"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Название, тег или ситуация"
                value={query}
              />
            </span>
          </label>
          <label
            className="block text-xs text-muted-foreground"
            htmlFor="prompts-category"
          >
            Категория
            <Select
              className="rounded-lg text-sm"
              containerClassName="mt-1"
              id="prompts-category"
              onChange={(event) => setCategory(event.target.value)}
              value={category}
            >
              <option value="all">Все</option>
              {categories.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
          </label>
          <label
            className="block text-xs text-muted-foreground"
            htmlFor="prompts-profile"
          >
            Профиль промпта
            <Select
              className="rounded-lg text-sm"
              containerClassName="mt-1"
              disabled={(data.data?.profiles.length ?? 0) < 2}
              id="prompts-profile"
              onChange={(event) => {
                const selected = event.target.value;
                setRuntimeProfiles((current) => {
                  const next = { ...current, [runtime]: selected };
                  storeProfiles(next);
                  return next;
                });
              }}
              value={profile}
            >
              {(data.data?.profiles ?? []).map((item) => (
                <option key={item.id} title={item.description} value={item.id}>
                  {item.label}
                </option>
              ))}
            </Select>
          </label>
        </div>

        <p className="max-w-3xl text-sm text-muted-foreground">
          {data.data?.active_profile?.description} Профиль меняет текст промпта.
          Модель и глубина размышлений выбираются в Codex или Claude Code.
        </p>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/70 bg-card/50 px-4 py-3">
          <p className="max-w-3xl text-sm text-muted-foreground">
            Здесь только промпты, которые добавляют задаче новый контекст.
            Системные роли harness подключает автоматически.
          </p>
          <Button
            aria-pressed={showSystem}
            onClick={() => setShowSystem((current) => !current)}
            size="sm"
            type="button"
            variant="outline"
          >
            {showSystem ? "Скрыть системные" : "Показать системные"}
          </Button>
        </div>

        {data.data ? (
          <div className="space-y-3">
            <div className="grid min-w-0 content-start items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
              {data.data.error ? (
                <p
                  className="rounded-xl border border-destructive p-5 text-destructive"
                  role="alert"
                >
                  {data.data.error}
                </p>
              ) : null}
              {!data.data.error
                ? prompts.map((prompt) => (
                    <Card
                      className="flex min-w-0 flex-col bg-card/80"
                      key={prompt.id}
                    >
                      <CardHeader className="space-y-1.5 p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <CardTitle className="text-base">
                            {prompt.title}
                          </CardTitle>
                          <Badge variant="secondary">{prompt.category}</Badge>
                          {prompt.library_visibility === "system" ? (
                            <Badge variant="outline">Системный</Badge>
                          ) : null}
                          {prompt.situations?.tier ? (
                            <Badge variant="outline">
                              {prompt.situations.tier}
                            </Badge>
                          ) : null}
                        </div>
                        <p className="line-clamp-2 text-sm text-muted-foreground">
                          {prompt.description}
                        </p>
                      </CardHeader>
                      <CardContent className="flex flex-1 flex-col gap-3 p-4 pt-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Button
                            onClick={() => copyPrompt(prompt, "launcher")}
                            size="sm"
                            type="button"
                            variant={
                              prompt.recommended_mode === "launcher"
                                ? "default"
                                : "outline"
                            }
                          >
                            <Copy aria-hidden="true" />{" "}
                            {copied === `${prompt.id}:launcher`
                              ? "Скопировано"
                              : "Короткий"}
                          </Button>
                          <Button
                            onClick={() => copyPrompt(prompt, "full")}
                            size="sm"
                            type="button"
                            variant={
                              prompt.recommended_mode === "portable"
                                ? "default"
                                : "outline"
                            }
                          >
                            <Copy aria-hidden="true" />{" "}
                            {copied === `${prompt.id}:full`
                              ? "Скопировано"
                              : "Переносимый"}
                          </Button>
                        </div>
                        <details className="group mt-auto">
                          <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-md text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
                            <ChevronDown
                              aria-hidden="true"
                              className="size-3.5 transition-transform group-open:rotate-180"
                            />
                            <span className="group-open:hidden">
                              Когда применять и текст
                            </span>
                            <span className="hidden group-open:inline">
                              Свернуть
                            </span>
                            <span className="ml-auto shrink-0 font-mono text-xs font-normal">
                              {usage[prompt.id] ?? prompt.usage_count} uses
                            </span>
                          </summary>
                          <div className="mt-3 space-y-3">
                            {prompt.situations?.use?.length ? (
                              <ul className="list-disc space-y-1 pl-5 text-sm">
                                {prompt.situations.use.map((item) => (
                                  <li key={item}>{item}</li>
                                ))}
                              </ul>
                            ) : null}
                            {prompt.situations?.instead?.length ? (
                              <p className="text-sm text-muted-foreground">
                                Вместо этого:{" "}
                                {prompt.situations.instead.join(" · ")}
                              </p>
                            ) : null}
                            {prompt.situations?.beads ? (
                              <p className="font-mono text-xs">
                                Beads: {prompt.situations.beads}
                              </p>
                            ) : null}
                            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-low p-3 text-xs">
                              {prompt.launcher_text}
                            </pre>
                            <p className="break-words font-mono text-xs text-muted-foreground">
                              native {prompt.launcher_chars} · portable{" "}
                              {prompt.full_chars} · {prompt.source}
                              {prompt.profile?.label
                                ? ` · ${prompt.profile.label}`
                                : ""}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {prompt.tags.join(" · ")}
                            </p>
                          </div>
                        </details>
                      </CardContent>
                    </Card>
                  ))
                : null}
              {!data.data.error && !prompts.length ? (
                <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
                  No prompts found.
                </p>
              ) : null}
            </div>
            <RawInspector
              data={{
                source: data.data.source,
                manifest_path: data.data.manifest_path,
                active_profile: data.data.active_profile,
                profiles: data.data.profiles,
                composition: data.data.composition,
                fragments: data.data.fragments,
              }}
            />
          </div>
        ) : data.error ? (
          <p className="rounded-xl border border-destructive p-5 text-destructive">
            {data.error.message}
          </p>
        ) : (
          <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
            Загружаем промпты…
          </p>
        )}
      </div>
    </ScreenFrame>
  );
}
