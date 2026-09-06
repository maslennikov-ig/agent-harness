# Stage Lifecycle and Sizing

A stage is one cohesive risk and integration boundary, not one helper, query
variant, DTO, adapter, proof binding, docs update, graph refresh, settled
decision, test, commit, or review finding.

Use the narrowest level:

- `inner_loop`: focused iteration and one-commit cohesive changes; no stage, no
  manifest, no stage files, no durable closeout — acceptance is one handoff
  line;
- `slice_acceptance`: one cohesive product/infrastructure outcome;
- `integration`: cross-module, compatibility, migration, database, or provider
  proof;
- `release`: repository, security, evidence, and delivery gates.

Keep one active implementation stage per Beads goal. Merge adjacent work when
owner, subsystem, risk model, test environment, rollback boundary, and
acceptance proof are shared. Split only for unresolved public
ownership/contract, a hard dependency, independent rollback/migration,
distinct security/compliance risk, or external authorization. Record that
material boundary; file, time, token, complexity, and work-area counts are not
split reasons.
Parallel isolated streams may implement that single stage concurrently and
converge through one acceptance and closeout gate.

Larger slicing does not open the epic. The accepted stage remains the only
active implementation boundary and the scope ledger preserves all criteria.

Cost, repeated verification, and review churn trigger a more efficient replan,
never scope shrinkage or weaker gates. Two checkpoints with no new artifact,
diff, result digest, or blocker change end the delegated wait.

A foundation stage names its immediate consumer, thin public facade, bounded
acceptance, and non-goals. Preserve an accepted foundation behind its facade.
