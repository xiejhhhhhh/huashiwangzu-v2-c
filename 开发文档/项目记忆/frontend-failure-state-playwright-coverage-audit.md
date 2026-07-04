---
name: "frontend failure-state Playwright coverage audit"
type: "task"
tags: [frontend, playwright, audit, load-state, notifications, readonly]
agent: "codex-subagent-5"
created: "2026-07-04T13:24:55.161207+00:00"
---

Read-only audit for frontend/tests failure-state coverage. Findings: frontend/tests has no hard waits (`waitForTimeout`, `sleep`, test-level setTimeout patterns absent); existing specs cover notification happy grouping/read/focus and file paste partial-failure copy. Coverage gaps remain for shared `ApiErrorInfo` normalization, `LoadState` error/stale transition, notification-center load issue copy/retry, and primary jump actions for Agent/Knowledge action items. No source/test files edited; Playwright not run because this was a coverage audit.
