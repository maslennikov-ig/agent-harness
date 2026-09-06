# Manual Agent Prompt Template

Use this template when the orchestrator prepares a prompt and the user launches the agent manually.
Keep the core contract compact. Add task, repository, artifact, delivery, and
completion details only when the active task or repository actually uses them.

## Core structure

```md
<one-line outcome title>

## Goal
<1 short paragraph with the exact expected outcome>

## Boundaries
- <only material in-scope, out-of-scope, or settled constraints>

## Write Zone
- <exact file/path set>
- Do not touch unrelated files.
- You are not alone in the codebase; do not revert others' work.

## Verification
- `<assigned focused command, or none during work; root final acceptance>`
- If a command is blocked by the environment, report that with the result.

## Stop
Return when the stated outcome and assigned verification are complete. If
blocked, name the blocker and the smallest decision or external change needed
to continue.
```

## Conditional additions

Add only the fields that change how this task must run:

- Task ID or Stage ID when durable tracking or stage binding exists.
- Workspace, repository, base commit, worktree, and contract-file context when
  the agent cannot discover them safely from its launch location.
- Artifact path and required conclusions when the task returns a durable
  artifact instead of an ordinary final response.
- Branch, commit, push, or PR requirements when the repository contract or the
  current task explicitly selects that delivery path.
- Business-critical requirements that are not already inherited from the
  repository or active skills.

## Completion transport (when configured)

When the active repository and stage use the completion inbox, append the
configured Task ID, Stage ID, and artifact path, then require this event after
the artifact is ready:

`python3 scripts/orchestration/report_child_completion.py --task <task_id> --stage <stage_id> --artifact <artifact_path> --status <returned|blocked> --commit <commit_hash_or_n/a> --verify <passed|failed|blocked> --clean <yes|no>`

If event reporting is blocked, include that fact in both the artifact and the
short final response. Without a configured completion inbox, omit this section
and return the result normally.
