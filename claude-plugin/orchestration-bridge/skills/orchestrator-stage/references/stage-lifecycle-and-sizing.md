# Stage Lifecycle and Sizing

A stage is one cohesive risk and integration boundary, not one helper, query
variant, DTO, adapter, proof binding, docs update, graph refresh, or settled
decision.

Use the narrowest lifecycle level:

- `inner_loop`: focused iteration and one-commit cohesive changes; no stage, no
  manifest, no stage files, no durable closeout — acceptance is one handoff
  line;
- `slice_acceptance`: one cohesive product/infrastructure outcome;
- `integration`: cross-module, compatibility, migration, database, or provider
  proof;
- `release`: repository, security, evidence, and delivery gates.

Keep one active implementation stage per goal. Merge adjacent work when owner,
subsystem, risk model, test environment, rollback boundary, and acceptance
proof are shared. Split only for unresolved public ownership/contract, a hard
dependency, an independent rollback/migration boundary, distinct
security/compliance risk, or external authorization. Record the material
boundary; descriptive work-area differences are not a split reason.
Parallel isolated streams may implement that single stage concurrently and
converge through one acceptance and closeout gate.

Larger slicing does not open the whole epic. Keep only the accepted stage
active and preserve all epic criteria through the scope ledger.

Treat rising tokens, cumulative agent time, repeated verification, or review
churn as a replan signal. Do not shrink scope or weaken gates. Two consecutive
checkpoints with no new artifact, diff, command-result digest, or blocker change
end the current delegated wait.

A foundation stage names its immediate consumer, thin public facade, bounded
acceptance, and non-goals. Preserve an accepted foundation behind that facade.
