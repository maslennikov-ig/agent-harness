---
name: test-driven-development
description: Use when test-first development is requested or a focused regression reproducer would unblock uncertain implementation.
---

# Focused Test-Driven Development

Test-first is an optional development technique. Default to implementing the
requested change and running the smallest meaningful acceptance at the end.
Behavior changes, task size, and risk labels do not automatically require a
red-green cycle. Preserve explicit task requirements and preflights needed
before destructive or irreversible actions.

When a defect or uncertain contract would otherwise cause speculative edits,
a small failing test can shorten the work. Exercise the real behavior, confirm
the failure is relevant, implement the fix, and use the same focused target.
If an existing test covers it, reuse that test. Add coverage only where it can
catch a meaningful regression; avoid tests mirroring implementation details.

The focused red-green loop is a development instrument. It does not trigger an affected package, broad suite, reviewer, or closeout after each correction.
Workers run it only when assigned or needed to unblock their implementation.
Final acceptance remains root-owned under the active task contract.

Keep useful working code. Do not delete or recreate it to demonstrate that a
test was written first. Tests written after implementation are valid evidence
when they exercise the required behavior and meaningful failure cases.
