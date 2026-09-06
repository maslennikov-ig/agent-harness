# Vendored from block/buzz

The Orchestration Console reuses a narrow set of frontend guard patterns from
[block/buzz](https://github.com/block/buzz) under Apache-2.0. The pinned source
is commit `1ff98fa`. This repository is not a fork of buzz.

| Local file | Upstream file(s) | Local modifications |
|---|---|---|
| `biome.json` | `biome.json`, `desktop/biome.json` | Flattened the desktop `extends` chain into one root configuration; retained the upstream schema and rules. |
| `scripts/check-file-sizes.mjs` | `desktop/scripts/check-file-sizes.mjs`, `scripts/check-file-sizes-core.mjs` | Combined the runner and core into one standalone script, limited rules to `web/src`, and used the current checkout as the local comparison base. |
| `scripts/check-px-text.mjs` | `desktop/scripts/check-px-text.mjs`, `scripts/check-px-text-core.mjs` | Combined the runner and core, limited scanning to `web/src`, and removed buzz-domain overrides. |
| `web/src/features/workspace/lib/formatTimelineMessages.ts`, `web/src/features/workspace/lib/formatTimelineMessages.test.mjs` | `desktop/src/features/messages/lib/formatTimelineMessages.ts`, `formatTimelineMessages.test.mjs` | Replaced Nostr/channel entities with the console's shared coordination envelope; retained the tested projection pattern for stable grouping, day boundaries, unread placement, and deterministic incremental merge. |
| `web/src/features/workspace/lib/useAnchoredScroll.ts`, `web/src/features/workspace/lib/useAnchoredScroll.test.mjs` | `desktop/src/features/messages/ui/useAnchoredScroll.ts` and its four adjacent `*.test.mjs` files | Reduced the channel/search/split-panel hook to the console's virtua boundary. Consolidated the upstream test matrix into focused anchor capture/restore, physical-bottom, and stable-key prepend tests; virtua owns dynamic measurement and the `shift` compensation. |
| `web/src/shared/ui/VirtualizedList.tsx` | `desktop/src/shared/ui/VirtualizedList.tsx` | Replaced the upstream TanStack virtualizer facade with a thin `virtua` `VList` facade selected by this epic; retained stable keys, variable-height rows, external scroll state, and a caller-owned renderer. |
| `web/src/shared/ui/UnreadPill.tsx` | `desktop/src/shared/ui/UnreadPill.tsx` | Reduced to the Workspace's one downward new-event affordance and localized the count label. |
| `web/src/shared/ui/TimelineSkeleton.tsx` | `desktop/src/features/messages/ui/TimelineSkeleton.tsx` | Removed channel-local cache and reaction/action shapes; retained a deterministic four-row timeline loading silhouette against the console tokens. |

Every vendored or adapted source and test that supports comments keeps an SPDX
Apache-2.0 notice. Comment-free configuration formats such as `biome.json` are
tracked by this table instead. Any later edit to one of these files must update
this table.
