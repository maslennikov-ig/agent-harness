# Graphify Legacy Migration And Semantic Modes

Read this reference only when a focused query reports pre-#1504 node IDs, a
tightened `.graphifyignore` requires a forced rebuild, or semantic/non-code
sources are in scope.

## Legacy Node-ID Migration

Graphify 0.9 uses full repo-relative node IDs. For a pre-#1504 warning:

1. Inspect `git status`, `git worktree list`, and active ownership/process state.
   Do not rebuild in an actively owned or unsafe worktree.
2. Back up ignored `graphify-out` outside the repo, for example under
   `$HOME/.local/state/graphify-pre-1504-<date>/<repo>/graphify-out`.
3. Rebuild locally without authorizing an external backend:

   ```bash
   graphify update . --force
   graphify cluster-only . --no-viz --no-label --timing
   ```

4. Rerun `graphify check-update .`, the focused query, and `graphify affected`
   for a known node. The warning must disappear.

Use `--timing` only for migration diagnostics. If semantic sources cannot be
reproduced locally or the warning remains, keep the backup and stop with the
exact blocker. Do not substitute a code-only graph or run semantic extraction
without authorization.

When `.graphifyignore` was tightened against sources already present, use the
same backed-up forced rebuild rather than deleting the graph or trusting an
incremental update. Then run 2-3 focused smoke checks:

```bash
graphify query "What are the main architecture subsystems in this project?" --graph graphify-out/graph.json --budget 2000
graphify query "Where are the main entrypoints and configuration files?" --graph graphify-out/graph.json --budget 2000
graphify explain "README.md" --graph graphify-out/graph.json
```

Prefer exact node IDs from `GRAPH_REPORT.md` when broad natural-language
queries are noisy.

## What The Default Graph Omits

`graphify update` re-extracts code. From documents it takes the file name and
headings; the prose between them is never read, and queries match node names
rather than content, so a phrase inside a document is unreachable through the
graph. A code graph therefore cannot establish that a phrase occurs inside
a document.

The graph answers code-structure questions. What a document says is found by
reading and grepping it.

## Semantic Modes

- `code/local graph`: local CLI graph/report without an external model backend
- `full semantic`: docs/research/PDF or other semantic extraction through an available, authorized backend/session workflow
- `blocked/deferred semantic`: semantic extraction needs missing support, credentials, hosted calls, or authorization

Do not run `graphify extract` with `openai`, `anthropic`, `gemini`, `claude`, or
similar backends unless the user explicitly authorizes those calls for the
current task and credentials are already configured. Never print secrets.

When blocked, keep the local graph and report:

```text
Graphify is installed and the local graph/report are available, but full semantic extraction is blocked or deferred because no authorized session-backed or backend mode is available.
```
