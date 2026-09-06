import { CheckCircle2, CircleAlert } from "lucide-react";
import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import { OverviewState } from "@/features/overview/overview-state";
import { RefreshOverviewButton } from "@/features/overview/refresh-overview-button";
import { Badge } from "@/shared/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

export function EnvironmentScreen() {
  const screen = screenById("environment");
  return (
    <ScreenFrame
      screen={screen}
      actions={<RefreshOverviewButton />}
      marker={{ kind: "native", id: screen.id }}
    >
      <OverviewState>
        {(data) => {
          const rows = [
            ["Codex Home", data.paths.codex_home, data.health.online],
            ["Workspace", data.paths.workspace, data.health.online],
            ["Local skill files", String(data.skills.count), true],
            ["Agents", String(data.agents.count), true],
            ["Beads", data.beads.summary, data.beads.bd_present],
            ["Embedded Dolt", `${data.beads.embedded_dolt_repos} repos`, true],
            [
              "Standalone Dolt",
              data.beads.dolt_present ? "installed" : "not installed",
              data.beads.dolt_present,
            ],
            ...data.tools.map(
              (tool) =>
                [
                  tool.label,
                  tool.detail || (tool.present ? "ok" : "not found"),
                  tool.ok,
                ] as const,
            ),
          ] as const;
          return (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {rows.map(([label, value, ok]) => (
                <Card key={label} className="border-border/70 bg-card/80">
                  <CardHeader className="flex-row items-start justify-between gap-4 pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      {label}
                    </CardTitle>
                    <Badge variant={ok ? "secondary" : "destructive"}>
                      {ok ? (
                        <CheckCircle2 aria-hidden="true" />
                      ) : (
                        <CircleAlert aria-hidden="true" />
                      )}
                      {ok ? "ok" : "check"}
                    </Badge>
                  </CardHeader>
                  <CardContent>
                    <p className="break-words font-mono text-sm leading-6 text-foreground">
                      {value}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          );
        }}
      </OverviewState>
    </ScreenFrame>
  );
}
