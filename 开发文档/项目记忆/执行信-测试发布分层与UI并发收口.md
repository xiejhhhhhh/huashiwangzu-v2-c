# 执行信：测试发布分层与 UI 并发收口

收件人：Codex / 独立执行会话
任务类型：测试工程化 / 发布效率
建议 agent 标识：`codex-test-release-layering-r1`
优先级：中高
边界：只收 pytest / Playwright 配置和测试副作用；不要改 release gate 核心实现。

---

## 0. 任务一句话

把测试从“能跑但分层不清、UI 串行、全量收集不稳”收口成 quick/module/preflight/full 四层，并修复 UI 并发和测试产物污染问题。

---

## 1. 必读材料

请先读：

1. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/AGENTS.md`
2. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/README.md`
3. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/dev_toolkit/README.md`
4. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/产品化闭环桌面体验与测试发布效率总审计报告.md`

注意：数据库反向链路执行线可能正在改 `dev_toolkit/release_gate.py`、`smoke.py`、`module_sandbox_matrix.py`，本任务不要抢这些文件。

---

## 2. 修改边界

### 允许修改

```text
pytest.ini
backend/pytest.ini
frontend/playwright.config.js
frontend/tests/
frontend/package.json      # 仅限必要 test script 调整
dev_toolkit/README.md      # 仅文档说明，不改 release_gate 实现
开发文档/项目记忆/
```

### 禁止修改

```text
dev_toolkit/release_gate.py
dev_toolkit/smoke.py
dev_toolkit/module_sandbox_matrix.py
backend/app/
modules/agent/
modules/knowledge/
```

如发现必须修改禁止范围才能完成，停止并写剩余风险，不要越界。

---

## 3. 背景证据

产品化总审计发现：

- `release_gate(full, skip_ui=true, sandbox_jobs=4, sandbox_frontend_jobs=2)` 约 69 秒完成，后端 + sandbox 已较快。
- `release_gate(preflight, skip_ui=true)` 约 1.8 秒。
- Playwright 配置仍 `workers: 1`，主 spec 有 serial。
- pytest 配置只注册 marker，缺 testpaths/addopts 和默认层级选择。
- `pytest --collect-only` 曾在 `modules/codemap/tests/test_feedback_capabilities.py` 触发 SQLAlchemy 表重复定义错误。
- UI 测试产物曾写到邮箱/收件箱或项目记忆，容易污染长期工作区。

---

## 4. 目标测试分层

请按这个口径落文档和最小配置：

| 层级 | 目标耗时 | 内容 | 结论口径 |
|---|---:|---|---|
| quick check | 30-60 秒 | 受影响文件 lint/单测、preflight gate | 只判断当前是否可继续开发 |
| module check | 1-3 分钟 | 当前模块 sandbox、相关 pytest、模块前端 build | 判断模块任务是否可合入 |
| preflight release gate | 3-5 分钟 | backend smoke、队列 delta、sandbox matrix、dirty 摘要 | 可给 PASS_WITH_DEBT，必须列债 |
| full regression | 可更久 | 完整 release gate + UI；可并发、可解释 | 只有这里能给 clean release |

---

## 5. 后端 pytest 收口

目标：

1. 统一 root `pytest.ini` 和 `backend/pytest.ini` 的口径，避免重复/漂移。
2. 明确 markers：quick、integration、live、slow、ui、sandbox 等按现有习惯命名。
3. 修复 `pytest --collect-only` 当前收集错误。
4. 不要为了收集通过而跳过真实测试问题。
5. 不要全量改测试逻辑；只修收集层面的明显错误和配置分层。

验收：

```text
backend/.venv/bin/python -m pytest --collect-only
backend/.venv/bin/python -m pytest -m quick   # 如 marker 可落地
```

如果 quick marker 暂不能完整落地，至少文档说明当前可执行的 quick 命令。

---

## 6. Playwright / UI 并发收口

目标：

1. 默认支持外部常驻前端服务：`PLAYWRIGHT_EXTERNAL_SERVER=1`。
2. 拆分 Playwright project 或 spec，让不互相依赖的 UI 测试可并发。
3. 保留必须 serial 的少量场景，并解释原因。
4. 避免测试产物写入邮箱/收件箱/项目记忆等长期目录。
5. 截图、trace、报告写到测试 artifacts/logs 目录，并确保可清理。
6. 不使用硬 sleep；必须等待时用条件等待。

验收：

```text
cd frontend && npm run build
cd frontend && PLAYWRIGHT_EXTERNAL_SERVER=1 npm run test:browser
```

如果完整 UI 因当前并行脏代码失败，至少拆出一个局部 project 命令证明并发和 artifacts 目录正确，并如实报告失败输出。

---

## 7. 发布门禁文档口径

本任务不改 release gate 代码，但要在 `dev_toolkit/README.md` 或相关文档里说明：

- quick check 怎么跑；
- module check 怎么跑；
- preflight release gate 怎么跑；
- full regression 怎么跑；
- `PASS_WITH_DEBT` 不是 clean pass；
- dirty worktree 下只能说 release safe with debt，不能说 clean release。

---

## 8. 不做事项

本任务不要做：

1. 不改 `dev_toolkit/release_gate.py`。
2. 不改 `dev_toolkit/smoke.py`。
3. 不改 `dev_toolkit/module_sandbox_matrix.py`。
4. 不改产品后端 API。
5. 不碰 Agent workflow。
6. 不通过删除测试来加速。
7. 不把失败标记成 skip 来制造绿。
8. 不清理真实用户数据。

---

## 9. 验收红线

以下直接判不通过：

- 为了速度删除关键测试。
- 默认跳过失败测试但不说明。
- UI 测试继续污染 `开发文档/项目记忆/` 或邮箱收件箱。
- Playwright 使用大量硬等待。
- TypeScript 用 `any/as any/@ts-ignore` 绕过。
- 改动越界到 release gate 核心或业务模块。

---

## 10. 交付物

请交付：

1. 修改文件清单。
2. 测试分层说明。
3. pytest collect 修复说明。
4. Playwright 并发/外部服务/artifacts 说明。
5. 验证命令与真实结果。
6. 失败项和剩余风险。
7. `memory_write(agent="codex-test-release-layering-r1")`。
8. `mcp_feedback(agent="codex-test-release-layering-r1")`。

---

## 11. 一句话目标

让强机器跑测试的时间花在有效验证上，而不是重复启动、串行等待、全量收集错误和测试产物污染上。
