---
name: "前端 UI E2E fixture 拆分与 gate 登录态加固"
type: "task"
tags: [ui-e2e, playwright, frontend-tests, release-gate, test-fixtures]
agent: "codex"
created: "2026-07-05T07:15:30.521917+00:00"
---

# 改了什么

- 将 `frontend/tests/ui-e2e.spec.mjs` 从 1007 行拆到 526 行，新增 `frontend/tests/ui-e2e/` helper：`auth.mjs`、`desktop.mjs`、`files.mjs`、`samples.mjs`、`report.mjs`、`state.mjs`。
- token refresh / request retry 集中到 `auth.mjs`；上传、回收站清理、文件状态轮询集中到 `files.mjs`；报告生成支持 `UI_E2E_REPORT_PATH` 覆盖。
- `content-artifact-desktop.spec.mjs` 改为复用共享 auth retry，避免 release gate 前置流程后 storageState 过期导致 401。
- `ui-e2e` 中需要 API 写入的场景会 refresh admin token 并同步回 page localStorage，避免登录刷新后页面 token 失效。

# 验证了什么

- `node --check` 覆盖修改后的 spec/helper 文件，通过。
- 禁止项扫描 `any/@ts-ignore/@ts-expect-error/waitForTimeout/sleep(` 为空。
- `npm --prefix frontend run build` 通过。
- `PLAYWRIGHT_EXTERNAL_SERVER=1 npm --prefix frontend run test:browser -- --reporter=line`：47 passed。
- `backend/.venv/bin/python dev_toolkit/release_gate.py`：PASS_WITH_DEBT；UI coverage PASS，passed=47，skipped=0；Test data pollution active=0/recycled=0/knowledge=0/content=0。

# 是否还有残留风险

- Release gate 仍有历史 debt：Queue failed=5、deleted-source obsolete failures=4、Sandbox matrix chunk warnings=19；无 BLOCKER。
- 工作区里有另外任务留下的两个未跟踪项目记忆文件，本次提交未包含。

# 关联 commit

- `84fc90e8 test: split UI e2e fixtures`
