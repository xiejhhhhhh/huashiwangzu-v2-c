---
name: "Claude Code 源码调研 — 可借鉴设计"
type: audit
tags: ["claude-code", "调研", "agent", "架构", "工具系统", "引擎"]
created: 2026-06-24
agent: opencode
---

# Claude Code 源码调研 — 可借鉴设计

调研对象：Claude Code v2.1.88 泄露源码（~1900 文件，~512K 行 TypeScript）
调研方法：codegraph_explore 源码索引 + 逐目录映射
对标模块：V2 `modules/agent/`（引擎 + 工具 + 对话 + 记忆）

## 背景

Claude Code 是 Anthropic 的终端原生 AI agent，技术栈：Bun + TypeScript（严格模式）+ React + Ink（终端 UI）+ Commander.js（CLI）+ Zod v4（schema）+ MCP SDK。

两个项目终端形态不同（CLI TUI vs. 桌面壳），但 agent 核心层（对话引擎、工具系统、记忆、任务编排）高度可比。

---

## 一、高优先级借鉴（直接可用，价值大）

### 1.1 工具并发分区（Tool Orchestration）

Claude Code 的 `services/tools/toolOrchestration.ts` 将工具执行为**可并发**和**必须串行**两类：

- **并发批**（`isConcurrencySafe && isReadOnly`): `GrepTool` + `GlobTool` + `FileReadTool` 等**同时跑**（上限 10）
- **串行批**（写操作): `FileEditTool` / `FileWriteTool` / `BashTool` 逐条执行

**对我们**：当前 Agent 工具调用逐条串行。如果知识库 `search` + `get_block` + `get_entity_dictionary` 等只读能力能并发跑，可显著减少多跳检索延迟。

**可落地位置**：`modules/agent/backend/engine/engine.py` → 增加 `_partition_tools(tool_calls)` 分区逻辑，并发 await 只读批。

### 1.2 Stop Hooks（每轮后钩子）

Claude Code 的 `query/stopHooks.ts` 在**每轮模型输出后**执行一系列轻量钩子：

- 保存安全参数（供后续 `/btw` 使用）
- 模板作业分类
- Prompt 建议（fire-and-forget）
- 记忆提取（gated）
- auto-dream 触发
- MCP 清理

**对我们**：当前 Agent 每轮对话就是单纯的对话-工具-结果循环。添加 post-turn hooks 可以在对话流中丝滑穿插"记忆沉淀""经验匹配""对话摘要"等，不阻塞主流程。

**可落地位置**：`modules/agent/backend/router.py` → chat 流结尾或 engine 内部 yield 后追加 hook 执行。

### 1.3 Token Budget with Diminishing Returns

Claude Code 的 `query/tokenBudget.ts` 实现 90% 预算继续方案，带收益递减检测：

```
如果 3 次继续后的增量 < 500 token → 停止继续
```

**对我们**：当前 `budget_allocator.py` 只是配预算-裁剪消息，没有**多轮继续的递减检测**。可以做：当模型连续产生多轮工具结果-继续时，检测每轮的净信息增量，递减到阈值就终止继续，避免 token 空转。

**可落地位置**：`modules/agent/backend/engine/budget_allocator.py` 新增 `DiminishingBudgetTracker`。

### 1.4 Event Sourcing + Replay 强化

当前 V2 Agent 已有 `agent_events` 表（event sourcing）和管理面板的 `ReplayViewer`。Claude Code 的全局事件系统有更丰富的维度：

- 每次模型调用 → 写 `transcript` 日志（含完整输入输出）
- 每次压缩 → 写 `ContextCollapseCommitEntry`
- 每次文件变更 → 写 `FileHistorySnapshotMessage`

**对我们**：在现有 event sourcing 基础上，增加**压缩事件**和**文件快照**的追溯记录，让 replay 时能看到"压缩了什么""之前的值是什么"。这几乎不增加代码量（只是多写几条 event），但能大幅提升可观测性。

**可落地位置**：`modules/agent/backend/engine/compressor.py` → 压缩时调 `record_event(db, conv_id, "compaction", {...})`。

---

## 二、中优先级借鉴（值得参考，需适配）

### 2.1 Memdir — 基于文件的轻量记忆

Claude Code 的 `memdir/memdir.ts` 核心设计：

- 一个 `MEMORY.md` 文件（最多 200 行, 25KB）
- 四种记忆类型：`user` / `feedback` / `project` / `reference`
- Prompt 中注入 `buildMemoryPrompt()` 读取 MEMORY.md 附加到 system prompt
- 跨会话持久化，通过 git 自然版本化

**对我们**：V2 有独立的 `memory` 模块（向量语义检索），能力更强但复杂度和响应成本也更高。可以借鉴"文件级记忆"作为**轻量补充**——用户/项目级别的静态记忆（如"我是谁""项目规范"）写在文件里，不走嵌入/召回，直接 prefix 注入。减少向量检索的无效召回。

**注意**：这不是替代 `memory` 模块，而是增加一个**零延迟**的确定性记忆层。

**可落地位置**：`modules/agent/backend/engine/layered_memory.py` → 新增 `read_static_memory_file(project_id) → str`，在 `assemble_context` 时拼入 system prompt。

### 2.2 Skills as Markdown（文件即技能）

Claude Code 的 `skills/loadSkillsDir.ts` 核心设计：

- 技能文件夹 `skill-name/SKILL.md`（前端元数据 + markdown 内容）
- 解析 frontmatter（`name`、`description`、`parameters`、`allowed-tools`、`context`、`agent`、`effort`、`shell`）
- 动态发现（从文件路径向上遍历找 `.claude/skills/`）
- 条件技能（`paths` 字段匹配文件操作时才激活）
- `createSkillCommand()` 处理参数替换（`${CLAUDE_SKILL_DIR}`、`${CLAUDE_SESSION_ID}`）、内联 shell 执行

**对我们**：当前 Agent 的 3 个工具是硬编码的。可以允许用户/项目在 `data/skills/` 下放 markdown 技能文件，Agent 通过 `skill_list` 自动发现。这是"用户可编程 agent"的极低门槛方式——写 markdown 就行，不需要写代码。

**可落地位置**：`modules/agent/backend/tools/` → 新增 `SkillLoader`，扫描 `data/workspaces/{user_id}/.agent-skills/*.md`。

### 2.3 Context Collapse（压缩投影）

Claude Code 的 `services/contextCollapse/`：

- 在每次 API 调用前对历史消息做**投影变换**（不是简单裁剪）
- 保留关键信息：对话摘要、决策树、已修改的文件列表
- 每次 collapse 产生一个 `ContextCollapseCommitEntry` 写入日志

**对我们**：当前 `compressor.py` 在超预算时做 hard truncate（简单裁剪中间历史），丢失了信息梯度。可以做 projection：把中间工具调用结果压缩为摘要段落，保留语义骨架。

**可落地位置**：`modules/agent/backend/engine/compressor.py` → 新增 `project_to_summary(events)` 方法。

### 2.4 工具类型体系 Tool<Input, Output, P>

Claude Code 的 `Tool.ts` 定义了完整的工具接口（~40 个方法属性）：

```typescript
type Tool<Input, Output, P> = {
  name、aliases、inputSchema(Zod)
  call(): Promise<ToolResult<Output>>
  isEnabled()、isConcurrencySafe(input)、isReadOnly(input)、isDestructive(input)
  validateInput()、checkPermissions()
  renderToolUseMessage() — TUI 渲染
}
```

**对我们**：当前 Agent 工具（`skill_list`/`skill_describe`/`skill_use`）是通用函数式调度，没有每个工具的独立生命周期。在做"更多具象工具"（直接暴露知识库检索、文件操作等）时，引入 `BaseTool` 基类能统一校验、权限、并发、渲染逻辑。

**可落地位置**：`modules/agent/backend/tools/base.py` → 新增 `Tool(ABC)` 基类。暂不着急，等工具数量到 10+ 时才需要。

---

## 三、低优先级借鉴（看看就好，暂不跟进）

### 3.1 Feature Flag Tree-shaking

Claude Code 用 Bun 的 `feature('FEATURE')` 宏实现条件编译——非活动特性在 `bun:bundle` 阶段被完全树摇掉（死代码消除）。Bun 特有，不适用于 Python/FastAPI。

**行动**：不跟进。

### 3.2 LSP 集成

Claude Code 有完整的 LSP（Language Server Protocol）集成用于诊断和代码补全（`services/lsp/`）。

**行动**：我们的桌面壳场景用编辑器 `text-editor` 模块处理，不在 agent 侧做 LSP。暂不跟进。

### 3.3 Vim Mode

Claude Code 内置完整的 Vim 模式（`vim/motions.ts`、`vim/operators.ts`、`vim/textObjects.ts`）。

**行动**：桌面壳场景不适用 CLI 的 vim 模式。不跟进。

### 3.4 GrowthBook / DataDog / OTel 遥测

Claude Code 有复杂的商业遥测管道（`services/analytics/`: GrowthBook 特性标记、DataDog 日志、1P OpenTelemetry 追踪）。

**行动**：内部企业场景不需要商业遥测。不跟进。

### 3.5 插件的 ~20 种错误类型

Claude Code 的 `PluginError` 联合类型有约 20 种变体（`PluginDisabledError`、`PluginRuntimeError`、`PluginAuthError`...）。

**行动**：对我们过度工程化。不跟进。

### 3.6 Coordinator Mode（多 Agent 协调器）

Claude Code 有完整的 coordinator 模式：一组 worker agent 并行执行子任务，coordinator 做合成。

**行动**：当前 V2 Agent 已有 `spawn_subagent` 能力，粒度已够。coordinator mode 是 CLI 特定场景（大规模重构/调研），桌面壳场景需求不强烈。暂不跟进。

---

## 四、架构对比总结

| 维度 | V2 Agent（当前） | Claude Code | 可借鉴程度 |
|------|------------------|-------------|-----------|
| 工具调度 | 逐条串行函数式 | 读写分区 + 并发批 | ⭐⭐⭐ |
| Token 预算 | 固定裁剪 | 递减检测 + 多轮继续 | ⭐⭐⭐ |
| Post-turn hooks | 无 | 完善的 stop hook 链 | ⭐⭐⭐ |
| Event sourcing | 有基础表 | 有 + 压缩/文件快照日志 | ⭐⭐⭐ |
| 记忆系统 | DB + 向量语义 | 文件级 MEMORY.md | ⭐⭐ |
| 上下文压缩 | Hard truncate | 投影 + 摘要压缩 | ⭐⭐ |
| 技能/可编程 | 3 硬编码元工具 | Markdown 技能文件 | ⭐⭐ |
| 工具类型体系 | 无 | 完整 Tool<Input,Output,P> | ⭐⭐ |
| 多 Agent 协同 | spawn_subagent 基础 | Coordinator + worker | ⭐ |
| 插件系统 | 无 | ~20 种错误类型 | ⭐ |
| LSP 集成 | 无 | 有 | ❌ |
| 遥测 | 无 | GrowthBook/DD/OTel | ❌ |
| CLI 特定 | N/A | Commands/Keyboard/Vim | ❌ |

---

## 五、建议行动项

### 立即可做（< 半天）

1. **Stop hooks 接入** — engine.py 中每轮 yield 后执行 fire-and-forget 钩子（记忆提取、经验匹配、对话摘要）。
2. **压缩事件记录** — compressor.py 压缩时写一条 `agent_events`（类型 `compaction`），含折叠数量和摘要预览。
3. **静态记忆文件** — `layered_memory.py` 新增读 `MEMORY.md`，system prompt 注入。

### 短期（1-2 天）

4. **工具并发分区** — engine.py 加 `_partition_tools()`，只读能力并发执行。
5. **Diminishing Budget Tracker** — `budget_allocator.py` 新增递减检测，token 增量 < 阈值时停止继续。

### 中期（3-5 天）

6. **Markdown 技能系统** — 新增 `tools/skill_loader.py`，扫描 `.agent-skills/*.md` 文件，Agent 自动发现。
7. **Context Projection** — `compressor.py` 新增投影压缩代替 hard truncate。

---

## 参考资料

- Claude Code 源码位置：`/Users/hekunhua/Documents/civil-engineering-cloud-claude-code-source-v2.1.88-main/`
- 研究分析：`02-claude-code-source-research/src/`
- 可运行版：`03-claude-code-runnable/src/`
- V2 Agent 模块：`modules/agent/`
