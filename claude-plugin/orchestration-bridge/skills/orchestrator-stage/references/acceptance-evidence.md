# Release evidence and operational retries

Repo-local closeout is the sole acceptance executor; consumers share evidence.
Reuse matching receipts, not freshness-only reruns. A cache hit needs complete
declared inputs and a fingerprint of step, lockfiles, tools, environment, and
dependencies; otherwise ineligible. Required steps stay intact; collect
independent failures; only dependants block.

`verification-manifest/v2` reuse defaults off; enable after completeness review.
Automatically use matching v2 evidence at final closeout where complete declared
inputs and repo policy permit; otherwise execute. `--reuse` stays; `--must-run`
bypasses cache; shadow reports would-hit but executes; kill switch forces
execution. V1 never hits. Never enable reuse globally or invent repo manifests.
If reuse rarely hits, inspect declared inputs and miss reasons before changing
the cache; a different commit is not by itself proof that all inputs changed.

Use one immutable candidate build per stable source identity. Documentation
outside declared build inputs does not invalidate it. Evidence identities:
`inner_loop`, `slice_acceptance`, `integration`, `release`. Preserve exact-SHA
contracts and immutable receipts; optimize their implementation separately.

Never repeat a failed operational attempt without new evidence or a named code,
config, or state mutation. One corrected retry is a recommendation, then replan,
not a hard stop. Prefer a local simulated cycle for protocol/receipt validation
before a separately authorized live attempt; local evidence is not live proof.
