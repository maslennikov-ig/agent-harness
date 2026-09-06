# Verification

Implement the outcome first. `inner_loop` has no mandatory tests,
review, build, screenshots, or acceptance artifacts. A focused diagnostic is
optional when it resolves uncertainty blocking the next edit. Test-first is
available when useful or explicitly requested, not a default risk lane.

At final acceptance, root selects the smallest set proving changed behavior.
Batch related writer returns and corrections before that set; a worker return,
commit, review comment, or skill invocation does not start another acceptance.
Workers return their changes and any existing evidence. Reviewers inspect it.
Reuse passing results with matching inputs; expand only for a new failure,
changed dependency, or unresolved risk. Full configured suite is epic/release acceptance only.

## UI and UX

UI edits do not automatically need a browser. Prefer existing tests or code
inspection when sufficient. Use a focused browser check only for a layout, interaction, accessibility, or integration risk those cannot resolve.
Use representative cases; language/theme/viewport combinations are not a matrix.
A screenshot may help inspect a visual result; an archived UX proof package
is not routine acceptance. Create such a package
only for an explicit user/delivery requirement or a named risk that cheaper
evidence cannot establish. Do not regenerate UX proof for unrelated changes when its declared inputs still
match. Preserve exact-SHA or client-proof requirements where required; change
their provenance contract separately, never restamp old evidence as new proof.

## Expensive final runs

Within the final set, put cheap manifest, packaging, and configuration checks
before dependent builds, browser runs, or proof capture. Collect independent
failures together, fix the batch, and rerun failed/affected checks. Repeat the
full release set only if its contract requires it or shared inputs invalidate
the earlier results. A successful focused repair is not itself release proof.
Avoid competing heavy tests/builds during a shared-machine acceptance run;
other workers can finish edits or documentation. Do not terminate other owners.
Before replacing a quiet worker, check its status and artifact once; message
delay alone is not evidence that work stopped.

For release caching, immutable builds, or a failed operational attempt, read
`acceptance-evidence.md`. This does not create a new gate or manifest.

Auth/tenancy, billing, secrets, personal/production data, irreversible migration,
safety/regulatory behavior, and high-blast-radius release require one targeted independent model review
at final task or release acceptance. The reviewer did not own implementation. If unavailable, record
`independent-review-required`; the change is not release-ready.
This narrow exception is not a routine verifier step. Human review
blocks release for real-money behavior, irreversible production-data changes,
and safety/regulatory behavior. Implementation may finish while release waits.
