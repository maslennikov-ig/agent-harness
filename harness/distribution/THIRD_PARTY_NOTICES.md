# Third-party notices

The harness-owned source in this distribution is MIT licensed; see the root
`LICENSE`. Dependencies retain their own licenses. Installing a dependency
does not relicense it under the harness license.

## Superpowers

Source: [obra/superpowers](https://github.com/obra/superpowers), v6.3.0,
commit `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`.
Copyright (c) 2025 Jesse Vincent. MIT license is preserved at
`vendor/superpowers/LICENSE` beside the redistributed code.

The bundled skills are modified by the harness's canonical
`harness/private/private/superpowers/bounded-tdd.patch`. Exact patch provenance
is in `vendor/superpowers/PROVENANCE.json`. Hooks, upstream plugin marketplaces,
runtime state and Git history are not included. The installer does not fetch
or automatically update this dependency.

## VoltAgent Codex subagents

Some files under `harness/private/private/codex/agents/` are adapted from
[VoltAgent/awesome-codex-subagents](https://github.com/VoltAgent/awesome-codex-subagents).
Their source comments and `QUALITY_PACK.md` retain the adaptation attribution.
The MIT license is reproduced in `licenses/voltagent-codex-subagents-MIT.txt`.
License evidence was retrieved at upstream commit
`ad1150a764457c301609217ab0ef0efa1cac307a`; this is the license evidence revision,
not a claim that every adapted role came from that revision.

## Block Buzz

Selected console frontend utilities are adapted from
[block/buzz](https://github.com/block/buzz), source commit `1ff98fa`, under
Apache-2.0. See `licenses/buzz-Apache-2.0.txt` and the file mapping in
`docs/vendored-from-buzz.md` at the distribution root. Existing per-file
copyright, license and modification notices are preserved.

## Package dependencies

Node and Python dependencies are resolved from the shipped `package-lock.json`
and `uv.lock`. Their licenses remain with the installed packages, including
font licenses supplied by the font packages. This source distribution does not
include `node_modules`, a Python virtual environment or a prebuilt frontend.
