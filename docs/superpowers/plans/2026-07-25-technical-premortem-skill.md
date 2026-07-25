# Technical Premortem Skill Implementation Plan

> **Execution note:** Follow the repository verification commands and preserve
> the RED → GREEN order below.

**Goal:** Install one concise English technical-premortem skill globally for
Codex and Claude and teach the Harness private overlay/export path to preserve
Claude personal skills.

**Architecture:** The private overlay owns two byte-identical canonical
`SKILL.md` files because Codex and Claude use different global skill roots.
Public Harness code owns the generic `claude/skills` export and overlay-template
support. The skill remains risk-triggered and feeds existing orchestration
artifacts rather than adding a lifecycle stage.

**Tech stack:** Markdown skills, JSON manifests, Python stdlib, `unittest`.

---

### Task 1: Add failing contracts

**Files:**
- Create: `agent-harness-private/tests/test_technical_premortem_skill.py`
- Modify: `agent-harness-private/tests/test_skill_context_budgets.py`
- Modify: `agent-harness/tests/test_export_local.py`

1. Assert Codex/Claude canonical files exist, are byte-identical, and contain no
   Cyrillic.
2. Assert the trigger gate, low-risk skip, rerun boundary, evidence classes,
   executor-error surface, verdicts, and recovery options are present.
3. Assert both generated and template manifests include `private-claude-skills`.
4. Assert private export copies `${CLAUDE_HOME}/skills`.
5. Run the focused tests and confirm they fail for the missing implementation.

### Task 2: Create the skill and Harness support

**Files:**
- Create: `agent-harness-private/private/codex/skills/technical-premortem/SKILL.md`
- Create: `agent-harness-private/private/claude/skills/technical-premortem/SKILL.md`
- Modify: `agent-harness-private/overlay.manifest.json`
- Modify: `agent-harness/harness_core/export_local.py`
- Modify: `agent-harness/templates/private-overlay/overlay.manifest.json`
- Create: `agent-harness/templates/private-overlay/private/claude/skills/.gitkeep`

1. Scaffold the Codex skill with the official skill-creator helper.
2. Replace the scaffold with the concise English workflow.
3. Add the byte-identical Claude copy.
4. Add Claude personal skills to export sources and both manifests.
5. Run focused tests until green.

### Task 3: Update operator documentation

**Files:**
- Modify: `agent-harness/README.md`
- Modify: `agent-harness/templates/private-overlay/README.md`
- Modify: `agent-harness-private/README.md`
- Modify: `agent-harness-private/TEAMMATE_README.md`

Document the `private/claude/skills` source and `${CLAUDE_HOME}/skills` target.
Keep plugin-namespaced skills and personal global skills clearly distinct.

### Task 4: Install and evaluate

1. Copy canonical skill files through the declared overlay paths.
2. Confirm installed Codex and Claude `SKILL.md` files match the canonical bytes.
3. Run representative low-risk, migration, and retry/idempotency evaluations.
4. Confirm low-risk work skips the formal analysis and high-risk work produces
   evidence-backed blast-radius, recovery, and executor-error findings.

### Task 5: Close out

1. Run both full repository test suites, plan smoke check, JSON validation, and
   `git diff --check`.
2. Review documentation impact and graph status.
3. Update the Beads task with verification evidence and close it only when all
   acceptance criteria pass.

