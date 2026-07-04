# 调研信：AI Agent 能力上限与成熟工作台对标

收件人：Codex / 独立调研会话
任务类型：调研，不改代码
建议 agent 标识：`codex-agent-capability-audit`
优先级：中高
边界：**只读调研；禁止修改源码、禁止清理数据、禁止提交代码**

---

## 0. 任务一句话

请从“华世王镞 V2 的 Agent 最终能不能成为真正的工作中枢”出发，对标成熟 AI 工作台和 Agent 产品，调研当前 Agent 能力上限、短板、架构缺口，并给出下一轮能力升级路线图。

这不是普通 bug 审计，也不是 UI 审计。重点是判断：

> 当前 Agent 离 OpenCode / Claude Code / Cursor / Devin / OpenHands / Dify / LangGraph 这类成熟工作台或 Agent 架构，还差哪些关键能力？

---

## 1. 必读项目材料

请先读：

1. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/AGENTS.md`
2. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/README.md`
3. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/01_框架开发文档/README.md`
4. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/02_底层开发文档/README.md`
5. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/03_模块开发文档/README.md`
6. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/agent/README.md`
7. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/memory/README.md`
8. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/knowledge/README.md`
9. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/dev_toolkit/README.md`

也请读取当前正在并行执行/调研的任务信，避免提出互相打架的执行建议：

1. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/执行信-后端无感Agent工作流中枢完整落地.md`
2. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/执行信-数据库反向链路主链路闭环修复.md`
3. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/调研信-产品化闭环桌面体验与测试发布效率总审计.md`

这三条已有独立会话在跑。你的调研不要改代码，不要抢它们的实现范围。

---

## 2. 可参考外部项目资料

本机已有参考资料目录：

```text
/Users/hekunhua/Documents/Agent/reference_sources
```

请优先读取这个目录中已经下载的项目/文档。

如果资料不够，可以自行下载新的开源项目或公开文档。下载时使用代理：

```text
127.0.0.1:4780
```

建议重点参考：

- OpenCode / Claude Code 类 CLI coding agent
- Cursor / Windsurf 类 IDE agent
- Devin / OpenHands 类自主软件工程 agent
- Dify / LangGraph / AutoGen / CrewAI 类工作流与多 Agent 编排
- Open WebUI / AnythingLLM 类本地 AI 工作台
- VS Code extension host / task system / problem matcher 的工具与任务模型

注意：

- 只学习架构、交互、能力组织方式。
- 不搬运代码。
- 报告要列出参考来源和借鉴点。
- 如果下载外部项目，不要写入本项目源码目录。

---

## 3. 调研边界

### 3.1 允许做

- 读取项目源码、文档、测试。
- 只读查看数据库结构和少量样本。
- 调用项目工具台 MCP。
- 调用活系统接口做只读验证。
- 阅读 `/Users/hekunhua/Documents/Agent/reference_sources`。
- 必要时下载外部公开资料。
- 写调研报告到 `开发文档/项目记忆/`。
- 用 `memory_write(agent="codex-agent-capability-audit")` 留项目记忆。
- 用 `mcp_feedback(agent="codex-agent-capability-audit")` 反馈工具台体验。

### 3.2 禁止做

- 禁止修改源码。
- 禁止修改数据库数据。
- 禁止清理文件。
- 禁止提交代码。
- 禁止执行 destructive 命令。
- 禁止直接实现你提出的升级方案。
- 禁止和正在执行的 Agent workflow 任务抢同一批文件。

---

## 4. 核心问题

请围绕以下问题调研：

1. 当前 Agent 是“聊天助手”、“工具调用器”，还是已经接近“工作中枢”？
2. 它是否具备任务规划能力？
3. 它是否能拆解任务、跟踪子任务、恢复中断任务？
4. 它是否能管理多工具、多模块、多轮上下文？
5. 它是否能判断自己卡住、失败、需要用户确认？
6. 它是否有长期记忆、项目记忆、经验复用能力？
7. 它是否能根据任务选择模型、预算、上下文压缩策略？
8. 它是否能安全地执行命令、读写文件、发布产物？
9. 它是否支持多 Agent 协作或子 Agent 派发？
10. 它是否有可审计的工作痕迹和用户可理解的进度反馈？
11. 它和知识库、文件、桌面、任务中心之间是否形成闭环？
12. 它最值得下一轮升级的 5 个能力是什么？

---

## 5. 能力维度评分模型

请按以下维度给当前 Agent 打分，满分 10 分，并说明证据：

| 维度 | 说明 |
|---|---|
| 任务理解 | 能否把用户需求转成清晰目标和约束 |
| 规划拆解 | 能否拆成步骤、依赖、风险、验收 |
| 工具使用 | 能否稳定选择工具、处理工具失败 |
| 上下文管理 | 能否管理文件、历史、摘要、长上下文 |
| 记忆复用 | 能否复用项目记忆、用户偏好、经验库 |
| 工作流持久化 | 能否跨请求/重启/多 worker 恢复任务 |
| 审批与安全 | 能否识别敏感操作并请求确认 |
| 多 Agent 协作 | 能否派发、追踪、合并子任务 |
| 产物生成 | 能否把工作结果落成文档、文件、任务、报告 |
| 自我纠错 | 能否发现失败、回滚、重试、降级 |
| 用户无感知 | 后台工作时用户是否只看到必要状态 |
| 可观测性 | 管理员能否追踪成本、错误、耗时、瓶颈 |

---

## 6. 对标成熟系统

请至少对标 5 类系统，每类选 1-3 个代表：

### 6.1 Coding Agent

例如：OpenCode、Claude Code、Aider、Cursor Agent、Windsurf。

重点看：

- repo 理解方式
- 文件编辑策略
- diff/patch 安全性
- 测试闭环
- 用户确认点
- 长任务体验

### 6.2 自主软件工程 Agent

例如：Devin、OpenHands、SWE-agent。

重点看：

- 任务规划
- sandbox / workspace
- 浏览器与终端协同
- 失败恢复
- 多步执行轨迹

### 6.3 Workflow / 多 Agent 框架

例如：LangGraph、AutoGen、CrewAI、Dify workflow。

重点看：

- 状态图
- checkpoint
- 人工审批
- 节点重试
- 多 Agent 通信
- 可视化执行流

### 6.4 本地 AI 工作台 / 知识库产品

例如：Open WebUI、AnythingLLM、Dify knowledge。

重点看：

- 知识库接入
- 文件引用
- 多模型配置
- 用户配置与权限
- 对普通用户的体验包装

### 6.5 IDE / 桌面任务系统

例如：VS Code tasks/problem matcher、JetBrains AI、Obsidian 插件生态。

重点看：

- 命令注册
- 任务输出
- 问题定位
- 插件能力边界
- 用户可追踪的状态模型

---

## 7. 当前项目重点观察区域

建议重点读取/分析：

```text
modules/agent/
modules/agent/backend/engine/
modules/agent/backend/runtime/
modules/agent/backend/services/
modules/agent/backend/handlers/
modules/agent/frontend/
modules/memory/
modules/knowledge/
modules/codemap/
modules/terminal-tools/
modules/desktop-tools/
backend/app/services/task_queue_audit_service.py
backend/app/routers/tasks.py
dev_toolkit/
```

但注意：只读，不改。

重点找：

- tool loop 如何运行
- action policy 如何审批
- checkpoint 是否可恢复
- memory 如何接入 Agent
- knowledge 如何被 Agent 调用
- terminal-tools / desktop-tools 的边界
- dev_toolkit 是否可被 Agent 当作工程工具使用
- 前端是否能表达 Agent 的工作过程

---

## 8. 推荐 MCP / 命令流程

请优先使用项目工具台 MCP：

```text
brief()
plan_task(description="AI Agent 能力上限与成熟工作台对标", task_type="investigation", module_key="agent")
worktree_guard(module_key="agent")
memory_search("Agent 工作流 工具调用 上下文 记忆 多 Agent")
code_explore("agent tool loop runtime checkpoint approval memory context")
code_explore("agent frontend work trace timeline approval")
code_explore("terminal tools desktop tools workspace publish")
capabilities(module="agent")
capabilities(module="memory")
capabilities(module="knowledge")
capabilities(module="terminal-tools")
routes(filter="agent")
routes(filter="tasks")
db_schema(table="agent")
probe(method="GET", path="/api/health")
```

如 MCP 临时不可用，可以用本地只读命令替代，但报告里说明。

---

## 9. 报告输出路径

请把最终报告写到：

```text
/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/AI-Agent能力上限与成熟工作台对标调研报告.md
```

---

## 10. 报告格式要求

报告必须包含：

```markdown
# AI Agent 能力上限与成熟工作台对标调研报告

## 1. 结论摘要
- 当前 Agent 定位判断
- 当前综合成熟度评分 x/10
- 最短板的 5 个能力
- 最值得下一轮升级的 5 个能力

## 2. 调研范围与证据
- 读取的项目文档
- 读取的代码区域
- 使用的 MCP 工具/命令
- 对标的外部项目/资料

## 3. 当前 Agent 能力地图
- 任务理解
- 规划拆解
- 工具使用
- 上下文管理
- 记忆复用
- 工作流持久化
- 审批与安全
- 多 Agent 协作
- 产物生成
- 自我纠错
- 用户无感知
- 可观测性

## 4. 评分表

## 5. 对标成熟系统差距
- Coding Agent
- 自主软件工程 Agent
- Workflow / 多 Agent 框架
- 本地 AI 工作台 / 知识库产品
- IDE / 桌面任务系统

## 6. 当前已有优势

## 7. 当前关键短板

## 8. 下一轮能力升级路线图
- 第 1 阶段：低冲突快补
- 第 2 阶段：Agent 中枢增强
- 第 3 阶段：多 Agent / 自主工作台

## 9. 后续执行信建议
至少 3 封：标题、目标、边界、禁止范围、验收方式、和当前并行任务的冲突关系。

## 10. 不建议现在做的事

## 11. 剩余风险
```

---

## 11. 后续执行信建议方向

请至少给出 3 封后续执行信建议，优先考虑这些方向：

1. Agent 工具调用可靠性与失败恢复专项。
2. Agent 上下文与记忆复用专项。
3. 多 Agent 派发、跟踪、合并专项。
4. Agent 用户无感工作痕迹与进度反馈专项。
5. Agent 产物发布与桌面/文件闭环专项。

每封都要明确是否依赖当前正在执行的“后端无感 Agent 工作流中枢”任务完成。

---

## 12. 与当前并行任务的关系

当前已有 3 个并行会话：

1. Agent 工作流中枢完整落地：偏 `modules/agent/` 实现。
2. 数据库反向链路主链路闭环：偏 backend/frontend/dev_toolkit 主链路。
3. 产品化闭环、桌面体验与测试发布效率总审计：偏产品化全局调研。

你的任务是能力上限专项调研。

要求：

- 不和第 1 个抢实现。
- 不和第 2 个抢 release gate / task queue 实现。
- 不重复第 3 个的产品化总审计，聚焦 Agent 能力本身。
- 报告中明确哪些建议必须等第 1 个任务完成后再做。

---

## 13. 验收标准

合格标准：

1. 报告能回答“Agent 离成熟工作台还差什么”。
2. 每项短板有项目内证据或外部对标依据。
3. 能区分“现在就能补的小能力”和“需要架构升级的大能力”。
4. 给出可执行的三阶段路线图。
5. 后续执行信建议边界清楚，不会和当前 3 个会话直接冲突。
6. 没有修改源码、没有清理数据、没有提交代码。

---

## 14. 收工要求

完成后请：

1. 写入报告到指定路径。
2. 用 `memory_write(agent="codex-agent-capability-audit")` 留一条项目记忆。
3. 用 `mcp_feedback(agent="codex-agent-capability-audit")` 反馈工具台体验。
4. 最后回复报告路径和一句话结论即可。

---

## 15. 一句话提醒

这次不是问“Agent 还有哪些 bug”，而是问“Agent 要成为真正的工作中枢，还差哪些能力层级”。
