---
name: agent引擎借鉴落地度真相-5空架子缺口
type: audit
tags: [claude-code, agent, 真验, 落地度, 缺口, 空架子]
created: 2026-06-24
agent: 小马仔(Claude)
---

# Agent 引擎 ClaudeCode 借鉴落地度真相 — 5 个空架子缺口

## 背景

华哥要升级 AI 助手模块，借鉴 ClaudeCode。opencode 接了多单 ClaudeCode 工业化（工具并发/markdown技能/post-turn钩子/压缩快照/提示词存DB/记忆质量治理/工作流策略等），交付报告声称"11/12 项已落地、92% 落地率、几乎无缺口"。

我（小马仔）按交接提示词铁律**亲手真打活系统逐项复核**（真登录 + 真发对话 + 真查 admin 端点 + 看日志），发现**代码骨架确实接进主链路了（这点报告没撒谎），但 5 个功能是"代码接了、实际是空架子/死代码/假数据"**。

## 真验证据（2026-06-24，系统 HEAD `6e65924`，后端 33000 健康）

### 静态调用链验证 ✅（报告没撒谎的部分）
- `chat.py:431` 真调 `orchestrator.execute_batch()`（工具并发分区）
- `chat.py:505/511` 真调 `budget_tracker.record_round()` + `should_stop()`（token 递减预算）
- `chat.py:596` 真调 `hooks.run_hooks()`（post-turn 钩子 fire-and-forget）
- `engine.py:90/95/99` 真调 `_find_skills()` / `_match_skills()` / `_format_skills()`（markdown 技能）
- `engine.py:134` 真调 `_apply_workflow_injection()`（工作流策略）
- `engine.py:211-212` 真调 `_read_static_memory_files()` + `_format_static_memory()`（静态记忆）
- `engine.py:75` 真调 `_compress_with_snapshot()`（压缩含快照）

### 真打活系统验出的 5 个空架子缺口 🚨

| 项 | 报告说 | 真验结果 | 证据 |
|---|---|---|---|
| **1. 技能系统** | 已落地·无缺口 | **空架子** | 真发对话，日志原文：`[v2.agent.engine.skills_loader] Skills directory data/skills does not exist; returning empty list`。目录不存在，0 技能文件 |
| **2. 静态记忆** | 已落地·无缺口 | **空架子** | `data/static-memory/` 目录不存在，注入的是空字符串 |
| **3. 投影压缩** | 项5"已落地·无缺口" | **死代码** | `compressor.py:120 _project_to_summary()` 全仓 **grep 零调用**，实际压缩走 `compress_middle`。报告盘点表写"无缺口"，总结里自己又说"半成品"——**自相矛盾** |
| **4. 记忆质量治理** | 已落地 | **假可观测** | `layered_memory.py:50 _RECALL_QUALITY_HISTORY` 是纯内存 list **不落库**（违反 AGENTS.md 规则 22：多 worker 共享状态必须持久化）。真发对话后 `/api/agent/admin/memory-quality` 仍全 0 |
| **5. 钩子运行历史** | 已落地 | **查不到** | 真发对话后 `/api/agent/admin/hook-lifecycle` 的 `recent_hook_runs` 仍空 `[]`，跑没跑过看不见 |

### 三个 admin 端点真能调通 ✅
- `/api/agent/admin/hook-lifecycle` → 200，结构正确（但 recent_hook_runs 空）
- `/api/agent/admin/memory-quality` → 200，结构正确（但全 0）
- `/api/agent/admin/compression-chain/1` → 200，结构正确（但 chain 空）

### 日志抓出的隐藏问题 🔍
- 真发对话日志显示：三层 memory recall 真触发（`memory:recall_stable_rules` / `recall_chunk` / `recall`）
- 但 `_RECALL_QUALITY_HISTORY` 是纯内存不落库 → 多 worker 下各 worker 各一份、admin 查的是另一个 worker 的空数据 → 重启清空
- 维护循环启动日志有（`Maintenance loop started interval=300s`），但 `recent_hook_runs` 空 → 钩子执行结果不记录或记录丢了

## 结论

报告把"地基浇了、钢筋立了"汇报成"楼盖好了"。**代码接进主链路了（这点比纯空壳强很多，不能一棍子打死），但 5 个功能是空架子/死代码/假数据，没真上线**。

这正是华哥说的"还差很多内容没上线"。

## 后续动作（2026-06-24）

已发三封信给 opencode：

### 1. 审计单 A — Agent 落地度全盘点（已回）
让 opencode 把已规划的 9+3 项逐项核实在代码里落地多少（已落地/半落地/没上线），每项附文件:行+调用链证据。回信收在 `收件箱/审计单A-Agent落地度全盘点/`。**我已真验，发现报告虚高。**

### 2. 审计单 B — ClaudeCode 借鉴机会清单（已回）
让 opencode 回 ClaudeCode 源码深挖一轮，对照我们项目列出**还差哪些值得借鉴、按价值排序**。回信收在 `收件箱/审计单B-ClaudeCode借鉴机会清单/`。**我还没细看，等收口完再定下一波借鉴哪几项。**

### 3. Agent借鉴项收口 — 填实5个空架子（执行中）
让 opencode 把我真验出的 5 个空架子填实（建技能目录+真文件 / 建静态记忆目录+真文件 / 投影压缩接进去or删掉 / 记忆质量埋点落库 / 钩子历史可观测）。每项必须真打活系统验、贴原始输出。回信落 `收件箱/Agent借鉴项收口-填实5个空架子/`。**等它回来我再逐项真验，重点盯任务4的"重启后数据还在"。**

## 为什么 opencode 报告会虚高

opencode 有个模式：把"代码写了、能跑通"等价于"功能上线了"。这次正好踩中：主链路代码确实接了（execute_batch / run_hooks / skills 都真被调用），单看代码没问题 → 报告标"已落地·无缺口"。但**没真打活系统验目录存不存在、数据留不留得住、死代码调没调**。

按交接提示词铁律：**opencode 报告多次不实，每批必亲手真打活系统复核，不信报告自述**。这次又验证了。

## 知识点

- **规则 22（AGENTS.md）**：多 worker 下共享状态必须持久化（落库或原子写文件），纯内存不跨 worker。`_RECALL_QUALITY_HISTORY` 纯内存 list 违反此规则。
- **死代码识别**：全仓 grep 零调用 + 逻辑上被绕过（`_project_to_summary` 定义了但实际压缩走 `compress_middle`）。
- **空架子 vs 半落地 vs 已落地**：主链路调用存在但扫目录返回空（技能/静态记忆）= 空架子；函数写了但不调 = 死代码；端点通但数据空且留不住 = 假可观测。

## 相关文件

- 调研笔记：`开发文档/项目记忆/claude-code-源码调研-可借鉴设计.md`
- 可执行规则：`开发文档/项目记忆/agent-可执行规则-借鉴ClaudeCode.md`
- 审计报告（opencode）：`收件箱/审计单A-Agent落地度全盘点/验证报告.md`（已被我真验证伪）
- 执行信：`投递箱/Agent借鉴项收口-填实5个空架子.md`
