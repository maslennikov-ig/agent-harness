# Docs and Graphify

The decision itself is owned by the kernel; this reference covers only mechanics.
Codex has no `docs-context` skill, so the resolver contract lives here. Run one
`orch-prompts docs-resolve --cwd <repo> --package <name> --topic '<API keywords>'`
per package/topic before relying on that behavior. It accepts only exact or
same-major.minor newer-patch `@neuledge/context` L1; missing, stale, cross-track,
floating, or insufficient L1 reports Context7/first-party fallback.
Persist whatever that fallback returns with `orch-prompts docs-persist`, so a
later task and a post-compaction resume hit L1 instead of the network.
The wrapper is authoritative in every repository for Codex and Claude. Diagnose
the shared route with `orch-prompts docs-diagnose --json`; `context` and
Context7 expose tools (`get_docs` and `query-docs` are their primary lookups),
so empty MCP resources/templates do not prove them unavailable. Direct MCP tool
injection is optional because the wrapper owns the workflow. Open a fresh task
after skill changes; restart the relevant host only after an actual MCP server
configuration change, not from config-file mtime or missing direct tools alone.

Local examples establish repository convention, not authoritative claims about
how an external framework, API, platform, browser, or tool is guaranteed to
behave.

When the local graph has `graphify-out/GRAPH_REPORT.md`, Graphify is an optional
orientation aid. Read it and use focused `graphify query`, `path`, or `explain`
when it helps with unfamiliar architecture, relationships, or impact. The
graph answers code-structure questions. It carries document file names and
headings but not document text, and it matches node names rather than content,
so information inside docs, ADRs, runbooks, and research notes is found by
reading and grepping them, never by querying the graph.
Never paste full graph JSON into prompts. Read-only audits query only. Refresh
after durable relevant changes at an accepted relevant integration/release boundary
when ownership is safe; otherwise record the bounded reason. External
semantic/model extraction and Graphify git hooks need explicit authorization.

For product UI, follow the global managed Lazyweb workflow and use Impeccable
for craft/implementation. Stitch is explicit-only. Designed HTML-to-PDF also
uses PDF rendering checks. Design routing does not authorize delegation.

Record the exact docs source and `graph-reviewed` result at closeout, including
`blocked` with the bounded reason when refresh is unsafe.
