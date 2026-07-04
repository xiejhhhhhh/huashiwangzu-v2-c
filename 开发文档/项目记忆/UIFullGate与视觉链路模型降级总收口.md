# UIFullGate 与视觉链路模型降级总收口

时间：2026-07-04

## 结论

本轮已把 full UI gate 从“未完整覆盖 / 失败不可归因”推进到“可运行、可复跑、失败可归因”。

最终 full release gate 结果：

```text
RELEASE GATE VERDICT: PASS_WITH_DEBT
blockers: 0
release_safe: true
deploy_allowed: true
clean_release_ready: false
ui_coverage_status: PASS, included=true, passed=45, failed=0, skipped=0
model_fallback_status: PASS, fallback_used_count=0, blocker_count=0
```

`clean_release_ready=false` 的原因不是 UI blocker，也不是视觉模型 blocker，而是仍有可跟踪 debt：dirty worktree、近 1 小时队列失败债、sandbox 前端 chunk warning。

## 本轮修复

1. `dev_toolkit/smoke.py`
   - Playwright 改为 JSON reporter 汇总，输出 passed/failed/skipped、失败测试名、截图/trace 路径。
   - smoke summary 增加 `ui` 与 `model_fallback` 结构化字段。
   - 增加 image-vision 语义视觉探针，记录主模型与 fallback 观察项。

2. `dev_toolkit/release_gate.py`
   - full gate 输出 `release_safe`、`deploy_allowed`、`clean_release_ready`。
   - 增加 `ui_coverage_status` 与 `model_fallback_status`。
   - preflight/skip-ui 明确标成 DEBT，不误判 clean release。

3. `modules/image-vision`
   - VLM 调用前压缩图片，降低 qwen3-vl context too large 风险。
   - 对 401/auth、context too large、not configured、model unavailable 做结构化分类。
   - 返回 `model_fallback`、`degraded_reasons`、`analysis_strategy.vlm_failure` 等字段。

4. `modules/media-intelligence`
   - VLM 未配置时返回结构化 `model_fallback`。
   - pipeline 将 `model_fallback` 提升到顶层结果。
   - sandbox 增加 fallback 断言。

5. 前端通知中心
   - `use-notifications.ts` 支持模型降级 action item。
   - 能展示主模型失败、fallback 使用、最终成功/失败。
   - `desktop-notification-center.spec.mjs` 增加模型降级通知 fixture 与断言。

6. UI gate 稳定性
   - `desktop-launcher-fileops.spec.mjs` 补齐桌面壳后台 mock，避免未 mock 的通知/任务/知识库接口 401 后把页面踢回登录页。
   - `content-artifact-desktop.spec.mjs` 在打开 artifact 前关闭已有窗口，并在 finally 中先关闭本测试打开的窗口再清理制品，避免后续 UI 场景被悬挂 viewer 和清理后的 404 污染。

## UI 失败归因

本轮遇到过三类 UI blocker，均已归因：

1. `content-artifact-desktop.spec.mjs` 首轮失败
   - 原因：桌面保留了上一次测试遗留的 Agent/窗口状态，目标 artifact 图标定位被干扰。
   - 处理：打开 artifact 前调用 `closeAllWindows()` 清空窗口状态。

2. `desktop-launcher-fileops.spec.mjs` 首轮失败
   - 原因：测试 token 进入桌面后，桌面后台异步请求通知/任务/知识库接口；这些接口未 mock，真实后端对测试 token 返回 401，Axios 拦截器重定向回登录页，导致 `.taskbar-start` 等不到。
   - 处理：补齐 `/api/notifications/unread-count`、`/api/tasks/worker/audit`、`/api/modules/call`、`/api/knowledge/dashboard/stats`、`/api/knowledge/governance/pending-count` 等桌面壳 mock。

3. release gate 中 `ui-e2e` 首测短暂失败
   - 表现：`1.1 Admin login - desktop loads without errors` 中 console error 数为 1。
   - 原因：前置 `content-artifact-desktop` 打开的 text-editor 窗口在 finally 清理文件后仍留在桌面，后续进入 `ui-e2e` 时 viewer 异步下载已清理文件，出现 `Download returned 404`。
   - 处理：`content-artifact-desktop` finally 中先关闭窗口，再清理发布制品。

## 模型降级策略

视觉链路现在按以下规则降级：

- mimo 401 / unauthorized / API key 类错误：归为 auth/config debt，不无限重试。
- qwen3-vl context too large / payload too large：先压缩图片，仍失败则归为 context debt 并走本地语义降级。
- 未配置或模型不可用：返回结构化 degraded/fallback 信息，业务链路不假成功，但不把“有 fallback 且最终成功”的情况判为 blocker。
- release gate 根据 `model_fallback_status` 区分 PASS / DEBT / BLOCKER。

本次最终 full gate 观察到视觉模型实际成功：

```text
source=image-vision:semantic
primary_model=vision.primary
primary_failed=false
fallback_used=false
final_success=true
status=PASS
```

因此 mimo 401 / qwen3-vl context 过大不再是当前发布 blocker；若后续真实环境再触发，会以结构化 debt 进入 smoke/release gate。

## 验证记录

```text
backend/.venv/bin/python -m pytest dev_toolkit/test_release_gate.py dev_toolkit/test_smoke_queue_gate.py
45 passed, 1 skipped

npm --prefix frontend run build
PASS，仍有既有 chunk size warning

env PLAYWRIGHT_EXTERNAL_SERVER=1 npm --prefix frontend run test:browser -- desktop-launcher-fileops.spec.mjs content-artifact-desktop.spec.mjs
3 passed

env PLAYWRIGHT_EXTERNAL_SERVER=1 npm --prefix frontend run test:browser
45 passed

backend/.venv/bin/python dev_toolkit/release_gate.py --sandbox-jobs 1 --sandbox-frontend-jobs 1
PASS_WITH_DEBT, blockers=0, deploy_allowed=true, clean_release_ready=false
```

前序同轮已验证：

```text
modules/media-intelligence/sandbox/test_module.py: PASS
modules/image-vision/sandbox/test_module.py: PASS
desktop-notification-center.spec.mjs: 3 passed
```

## 剩余 Debt

1. Dirty worktree
   - gate 记录 dirty files=116。
   - 本轮未清理或回滚其他 agent/既有改动。

2. Queue debt
   - gate 记录 failed=2、pending=0。
   - gate-run failed delta 为 0，没有新增失败任务。
   - recent failed window 有 2 个近 1 小时失败任务，按 debt 跟踪。

3. Sandbox chunk warning
   - 35 个模块 sandbox 全部 PASS。
   - 19 个模块有前端 chunk warning，属于构建体积 debt，不是 blocker。

## 发布判断

当前判断：

```text
release_safe=true
deploy_allowed=true
clean_release_ready=false
```

含义：

- 可以按 `PASS_WITH_DEBT` 发布/部署。
- 不能称为 clean release，因为 worktree 未清、队列近期失败债和 chunk warning 仍存在。
- UI/full gate 已完整覆盖且可复跑；视觉模型链路已具备结构化降级与 gate 汇总。
