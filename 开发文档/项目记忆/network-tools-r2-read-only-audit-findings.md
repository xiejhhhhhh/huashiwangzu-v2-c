---
name: "network tools r2 read-only audit findings"
type: "task"
tags: [network-tools, audit, r2, web-tools, browser-tools, github-search, agent, ssrf, timeout]
agent: "codex-flow-audit-network-tools-r2"
created: "2026-07-03T09:34:30.170084+00:00"
---

Agent codex-flow-audit-network-tools-r2 completed a read-only audit of outbound network/tool chains on branch codex/sweep-quality-r2. Scope covered web-tools, browser-tools, github-search, and Agent skill/tool dispatch. No code was changed and no commit was made.

Evidence used: brief, plan_task(task_type=investigation), worktree_guard, routes, capabilities, code_explore/code_node/code_impact, tail_log, probe, call_capability, finish_task. Live probes: web-tools:fetch http://127.0.0.1:33000/api/health returned 422 URL targets a private/internal address; browser-tools:open same localhost URL returned 422; /api/github-search/health returned 200. backend tail_log was empty.

Findings queue: no confirmed P0. P1: browser-tools accepts unbounded user timeout values in open/click/type/wait_for/download and Agent chat is SSE timeout-exempt, so skill_use can hold an Agent turn far longer than the normal 60s HTTP middleware; fix inside modules/browser-tools plus Agent network-tool execution guard. P1: browser-tools direct download uses httpx get(content) and only checks size after full body is read, so large/streaming responses can consume memory before the 50MB limit is enforced; fix with streamed read and early abort. P1/P2: Agent tool loop and ToolOrchestrator intentionally turn tool exceptions into normal tool_result {error:...}; for network tools this can become model-level swallowing/retry drift unless hard failure classes are mapped to stop/retry/degrade policy. P2: web-tools runtime is hardened (trust_env=False, no default proxy, SSRF redirect recheck, binary/size limits, fake failure converted to 422), but modules/web-tools/README.md still says default proxy http://127.0.0.1:4780, conflicting with code and sandbox. P2: github-search has no module README even though it depends on gh CLI auth, runtime cache, file-backed rate limit, and 15s CLI timeout.

Suggested repair task boundaries: browser-tools-only task for timeout bounds and streaming download; agent-only task for network tool failure policy and per-tool timeout budget under SSE; docs-only or module-owner cleanup for web-tools README and github-search README. Shared url_safety should remain a separate framework task only if new SSRF cases are found; current localhost probes passed fail-closed.
