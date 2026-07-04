# 执行信：Release Gate 二期能力漂移与文档矩阵门禁

## 目标

把 release gate 从“健康/资产/队列”升级到“发布契约门禁”：capability drift、README 验收矩阵、component_key 空窗口、bundle warning 都进入 PASS/DEBT/BLOCKER。

## 前置

如果当前 Test data pollution 仍是 BLOCKER，先不要执行本信，先执行“测试污染回归清零与门禁稳态”。

## 边界

允许：

```text
dev_toolkit/release_gate.py
dev_toolkit/release_response.py
dev_toolkit/module_sandbox_matrix.py
dev_toolkit/test_release_gate.py
dev_toolkit/test_release_response.py
dev_toolkit/test_module_sandbox_matrix.py
开发文档/项目记忆/
```

禁止：

```text
backend/app/
frontend/src/
modules/
```

## 必做

1. capability live registry vs manifest/source drift 进入 gate。
2. README 验收矩阵缺失进入 DEBT；新变更模块缺失可 BLOCKER。
3. normal app 空 component_key / background-service component_key 规则进入 gate。
4. frontend sandbox chunk warning 进入 DEBT。
5. 输出 compact summary：verdict、blockers、debts、clean_release_ready、deploy_allowed。

## 验收

```bash
backend/.venv/bin/ruff check dev_toolkit/release_gate.py dev_toolkit/release_response.py dev_toolkit/module_sandbox_matrix.py
backend/.venv/bin/python -m pytest dev_toolkit/test_release_gate.py dev_toolkit/test_release_response.py
```

活栈：

```text
release_gate(skip_ui=true, mode=preflight)
```

## 交付

写：

```text
开发文档/项目记忆/ReleaseGate二期能力漂移与文档矩阵门禁收口.md
```

调用：

```text
finish_task(...)
memory_write(agent="codex-release-gate-contract-r1")
mcp_feedback(agent="codex-release-gate-contract-r1")
```

## 提示词

请读取并执行：‘/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/执行信-ReleaseGate二期能力漂移与文档矩阵门禁.md’
