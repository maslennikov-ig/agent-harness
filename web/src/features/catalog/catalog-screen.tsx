import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import { OverviewState } from "@/features/overview/overview-state";
import { RefreshOverviewButton } from "@/features/overview/refresh-overview-button";
import { useAppearance } from "@/shared/theme/appearance-provider";
import { Badge } from "@/shared/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

export function CatalogScreen() {
  const screen = screenById("catalog");
  const { runtime } = useAppearance();
  return (
    <ScreenFrame
      screen={screen}
      actions={<RefreshOverviewButton />}
      marker={{ kind: "native", id: screen.id }}
    >
      <OverviewState>
        {(data) => {
          const rows =
            runtime === "claude"
              ? [
                  ["Enabled plugins", data.catalog_claude.enabled_plugins],
                  ["Disabled plugins", data.catalog_claude.disabled_plugins],
                  ["Skill packs", data.catalog_claude.skill_packs],
                  ["Plugin skills", data.catalog_claude.plugin_skills],
                  ["Agents total", data.catalog_claude.agents],
                  ["User agents", data.catalog_claude.user_agents],
                  ["Project agents", data.catalog_claude.project_agents],
                  ["Plugin agents", data.catalog_claude.plugin_agents],
                  ["aitmpl candidates", data.catalog_claude.aitmpl_candidates],
                  [
                    "aitmpl matches",
                    data.catalog_claude.aitmpl_matching_agents,
                  ],
                  [
                    "Orchestration bridge",
                    data.catalog_claude.orchestration_bridge
                      ? "enabled"
                      : "missing",
                  ],
                ]
              : [
                  ["Generated", data.catalog.generated_at || "unknown"],
                  ["Staged sources", data.catalog.staged_sources],
                  ["Staged skills", data.catalog.staged_skills],
                  ["Staged agents", data.catalog.staged_agents],
                  ["Installed skills", data.catalog.installed_skills],
                  ["Custom agents", data.catalog.custom_agents],
                ];
          const catalogErrors =
            runtime === "claude" ? [] : (data.catalog.errors ?? []);
          return (
            <>
              <Badge className="mb-4">
                {runtime === "claude" ? "Claude assets" : "Codex catalog"}
              </Badge>
              {runtime !== "claude" && (
                <Card className="mb-4 border-border/70 bg-card/80">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Homes
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1 font-mono text-xs text-foreground">
                    <p>
                      <span className="text-muted-foreground">assets: </span>
                      {data.catalog.home}
                    </p>
                    <p>
                      <span className="text-muted-foreground">session: </span>
                      {data.catalog.runtime_home}
                    </p>
                    <p>
                      <span className="text-muted-foreground">runner: </span>
                      {data.catalog.runner}
                    </p>
                  </CardContent>
                </Card>
              )}
              {catalogErrors.length > 0 && (
                <Card className="mb-4 border-destructive/60 bg-destructive/5">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-destructive">
                      Catalog unavailable
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1 font-mono text-xs text-foreground">
                    {catalogErrors.map((message) => (
                      <p key={message}>{message}</p>
                    ))}
                  </CardContent>
                </Card>
              )}
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {rows.map(([label, value]) => (
                  <Card key={label} className="border-border/70 bg-card/80">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium text-muted-foreground">
                        {label}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="font-mono text-2xl font-semibold text-foreground">
                        {value}
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </>
          );
        }}
      </OverviewState>
    </ScreenFrame>
  );
}
