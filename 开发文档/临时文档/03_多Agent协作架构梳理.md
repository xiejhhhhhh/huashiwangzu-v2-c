# 多 Agent 开发协作架构

## 当前 Agent 清单

```
┌─────────────────────────────────────────────────────────────────────┐
│  华哥（决策者）                                                       │
│  不写代码，只做调度和拍板                                              │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  Claude Code     │   │  Codex CLI      │   │  OpenCode       │
│  (opus-4.8)     │   │  (codex-cli)    │   │  (headless)     │
│                 │   │                 │   │                 │
│  角色：策划+高端  │   │  角色：中端执行   │   │  角色：低端打手   │
│  费用：最贵      │   │  费用：中等      │   │  费用：最低      │
│  能力：全能      │   │  能力：全能      │   │  能力：全能      │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         │                     │                     │
         │  直接操作            │  直接操作            │  被派发
         ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        项目代码库                                     │
│  /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2                     │
│                                                                     │
│  共享入口：                                                          │
│  ├── .mcp.json          → project_toolkit MCP（三者共用）             │
│  ├── .codex/config.toml → Codex 专用配置                             │
│  ├── .opencode/agents/  → OpenCode 子代理定义（执行者/探索者等）       │
│  └── .claude/           → Claude Code 专用配置                       │
└─────────────────────────────────────────────────────────────────────┘
```

## 调度链路

```
                    ┌─────────────────────────────┐
                    │  Claude Code（你/4.8）         │
                    │  策划 + 审计 + 高端实现        │
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┼────────────────────┐
              │                │                    │
              ▼                ▼                    ▼
   ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
   │ 直接子代理(Agent) │  │  投递箱派发    │  │  Codex CLI 直调   │
   │ sonnet/haiku     │  │  → OpenCode   │  │  codex run ...   │
   │ 便宜+并行        │  │  → 任意Agent  │  │                  │
   └──────────────────┘  └──────┬───────┘  └──────────────────┘
                                │
                    ┌───────────┼───────────┐
                    ▼                       ▼
         ┌──────────────────┐   ┌──────────────────┐
         │  OpenCode 网关    │   │  邮箱/投递箱/     │
         │  端口 55891       │   │  .md 信件        │
         │  headless 模式    │   │                  │
         └────────┬─────────┘   └──────────────────┘
                  │
                  ▼
         ┌──────────────────┐
         │  OpenCode 子代理  │
         │  executor/explorer│
         │  用 deepseek 模型 │
         └──────────────────┘
```

## 资源层

```
┌─────────────────────────────────────────────────────────────────────┐
│  模型资源                                                            │
├─────────────────┬───────────────────┬───────────────────────────────┤
│  Claude 直连     │  Codex 本地网关    │  云端中转                      │
│  (opus-4.8)     │  (50936 端口)     │                               │
│                 │  gpt-5.5 能力     │  jayce.sky1818.com            │
│  用途：          │                   │  gpt-5.5 (视觉/生图)          │
│  - 你自己       │  用途：            │                               │
│  - 子代理       │  - 知识库分析      │  opencode.ai/zen/go           │
│                 │  - OpenCode 执行   │  deepseek-v4-flash (Agent)    │
├─────────────────┴───────────────────┴───────────────────────────────┤
│  本地模型                                                            │
│  30000: bge-m3 (deprecated)                                         │
│  30001: bge-reranker                                                │
│  30002: qwen3-vl (视觉)                                             │
│  30003: gemma-4 (文本 fallback)                                     │
│  30004: qwen3-embedding-8b (主力嵌入)                                │
└─────────────────────────────────────────────────────────────────────┘
```

## MCP 工具台调用关系

```
┌─────────────────────────────────────────────────────────────────────┐
│  project_toolkit MCP (dev_toolkit/server.py)                        │
│  ~100 个工具，三个 Agent 共用同一实例                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─ 核心运维（高频）────────────────────────────────────────────┐   │
│  │ sql / probe / call_capability / run_test / lint             │   │
│  │ tail_log / restart_backend / finish_task / plan_task        │   │
│  │ diagnose / worktree_guard / bug_logs / docs_audit           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ 代码编辑（中频）──────────────────────────────────────────┐    │
│  │ apply_patch / quick_fix_preview / quick_fix_patch           │    │
│  │ batch_quick_fix_apply / edit_recipe_*                       │    │
│  │ code_explore / code_node / code_impact                      │    │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ Agent 调度（仅策划 Agent 用）─────────────────────────────┐    │
│  │ mailbox_write_letter / opencode_dispatch_letter             │    │
│  │ opencode_sdk_job_submit / _status / _list / _notifications  │    │
│  │ opencode_pty_start / _read / _write / _stop                 │    │
│  │ agent_board_claim / _heartbeat / _complete / _block          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ 记忆/画像（低频）────────────────────────────────────────┐     │
│  │ memory_write / memory_search / memory_recent               │     │
│  │ user_profile_get / _suggest / _update                      │     │
│  │ mcp_feedback / mcp_feedback_summary                        │     │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ 知识库管线（专项）───────────────────────────────────────┐     │
│  │ knowledge_pipeline_snapshot / knowledge_source_gap_snapshot │     │
│  │ knowledge_source_manifest_scan / _summary / _audit / _enqueue│   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ 发布/治理（低频）───────────────────────────────────────┐      │
│  │ release_gate / module_sandbox_matrix / capability_contract_diff│  │
│  │ git_sync_plan / git_sync_workflow                           │    │
│  │ docs_sync / docs_snapshot / workspace_audit                 │    │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ 自检/遥测（极低频）──────────────────────────────────────┐    │
│  │ tool_usage_stats / mcp_self_check / dev_toolkit_architecture_audit│
│  │ agent_activity_report / agent_runtime_snapshot              │    │
│  │ tool_job_submit / _status / _notifications                  │    │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## 当前问题

### 1. 三个 Agent 共用 100 个工具，token 浪费

Claude Code 每次初始化要吃掉约 100 个工具定义的 token（每个工具 ~200 token = ~20K token 开销）。
执行 Agent（OpenCode）根本不需要 `mailbox_write_letter`（那是策划 Agent 写的），
策划 Agent 也不需要 `opencode_gateway_start`（那是自动拉起的）。

### 2. OpenCode 调度链路太长

```
Claude 调 MCP → opencode_gateway_start → opencode_sdk_job_dispatch_letter
→ 等 → opencode_sdk_job_status 轮询 → opencode_sdk_job_notifications 收结果
```
6 个工具调用才能完成一次"派任务→等完成→收结果"。

### 3. 投递箱积压 60+ 封信

旧信没清理，新 Agent 读邮箱时容易被噪音污染。

### 4. 没有统一进度看板

投递了 5 个并行任务后，华哥要一个个问"完了没有"，没有汇聚视图。

## 优化方案建议

### A. 工具分层（按角色裁剪）

```
strategy_tools  (~35 个) ← Claude Code 用（策划+高端实现+调度）
executor_tools  (~25 个) ← OpenCode/Codex 用（执行+自检）
```

不是两套 MCP 进程，而是同一个 server.py 里加一个 `TOOL_PROFILE` 环境变量：

```json
// .mcp.json (Claude Code)
{ "env": { "TOOL_PROFILE": "strategy" } }

// .codex/config.toml (Codex)
env = { TOOL_PROFILE = "executor" }
```

server.py 启动时按 profile 过滤 tool_definitions() 返回的列表。

### B. 投递+等待 合并为一个工具

把 6 步链路合成一个 `dispatch_and_wait`：

```
dispatch_and_wait(letter, timeout=1800)
→ 自动启动 gateway
→ 派发信件
→ 后台轮询
→ 完成后返回结果摘要
```

### C. 并行派发 + 汇聚

```
dispatch_batch(letters=["任务A.md", "任务B.md", "任务C.md"])
→ 同时派 3 个 OpenCode session
→ 返回 {job_ids, 预计完成时间}

check_batch(job_ids)
→ 返回每个任务状态 + 已完成的结果摘要
```

### D. 投递箱自动归档

`finish_task` 成功后自动把对应投递信移到归档箱，而不是手动操作。

### E. 进度看板（agent_board 复用）

agent_board 的设计本身是对的（claim/heartbeat/complete/block），只是没人在用。
如果 OpenCode 执行时自动 heartbeat（每 5 分钟），策划 Agent 用 `agent_board_snapshot` 就能一眼看所有并行任务状态。
