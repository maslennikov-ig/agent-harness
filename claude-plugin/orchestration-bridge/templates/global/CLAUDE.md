<!-- HARNESS-ROUTING:BEGIN -->
@{{SHARED_AGENTS_PATH}}

- Medium/complex, staged, risky, or handoff-prone Claude work uses
  `orchestration-bridge:orchestrator-stage`.
- That skill owns Claude-specific delegation, model/effort routing, and context
  guidance.
- With Fable 5.1 as lead, act primarily as orchestrator and use Opus 5 for
  bounded execution. Match supported effort to difficulty: low for mechanical,
  medium for normal, high for complex work. The stage skill owns native
  controls; delegation alone does not guarantee lower total cost.
<!-- HARNESS-ROUTING:END -->
