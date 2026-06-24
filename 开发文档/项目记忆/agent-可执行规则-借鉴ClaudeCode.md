---
name: "Agent 可执行规则 — 借鉴 Claude Code"
type: rules
tags: ["agent", "架构", "工具系统", "技能", "快照", "规则"]
created: 2026-06-24
agent: opencode
---

# Agent 可执行规则 — 借鉴 Claude Code

本文档将从 Claude Code 调研中提取的高优先级可借鉴项，整理为项目内可执行规则。
每条规则附带"改法、边界、验证方式"。

---

## 规则 1：工具元数据优先于名字猜测

**背景**：`tool_orchestrator.py` 已实现三层解析链（显式注册→能力注册表→pattern fallback）。
但元数据注册仍需在添加新工具时手动完成。

**规则**：新增模块能力（capability）时，必须在 `register_tool_metadata()` 中声明执行语义。

### 改法（模块开发者）

```python
from engine.tool_orchestrator import register_tool_metadata, ToolMetadata

register_tool_metadata("memory__save", ToolMetadata(
    name_pattern="memory__save",
    write=True,
    requires_serial=True,
))
register_tool_metadata("knowledge__search", ToolMetadata(
    name_pattern="knowledge__search",
    read_only=True,
    concurrency_safe=True,
))
```

### 边界

- 显式声明优先于能力注册表，能力注册表优先于 pattern fallback
- 未注册工具默认走 write+serial（保守安全）
- 不需要在所有模块的 `__init__` 时注册，在 router 导入时触发即可

### 验证

- 新工具首次被调度时，日志显示 `Metadata-first: explicit match` 或 `capability registry match`
- 只读工具（如 search/list）与写工具（如 save/delete）不在同一批次并发执行
- 测试覆盖：`tool_orchestrator.py` 已有 `determine_tool_metadata` 的分支测试

---

## 规则 2：Markdown Skills 自动发现机制

**背景**：`skills_loader.py` 已实现从 `data/skills/` 和 workspace `.agent-skills/` 目录自动发现
markdown 技能文件。但项目组内仍需共识"什么时机扫描、注入到哪儿"。

### 规则

技能文件的发现和注入时机：

1. **启动时**：`find_skills()` 扫描 `data/skills/` 目录，结果缓存 60 秒
2. **每轮对话**：`assemble_context()` 调用 `find_skills()` + `match_skills()`，结果拼入 system prompt
3. **工作区技能**：如果 `CURRENT_PATH` 环境变量指向有效目录，额外扫描 `.agent-skills/` 子目录

### 边界

- 技能只在 system prompt 装配时注入，不动态变更运行时行为
- path-scoped 技能仅在 `current_path` 非空且路径匹配时才激活
- 技能 body 中的 `</skill>` 被转义为 `<\/skill>` 以防止 prompt 结构破坏
- 失败不阻塞主对话流程（non-fatal）

### 文件约定

```markdown
---
name: my-skill
description: 做什么的
allowed-tools: knowledge__search, memory__recall
paths: ["/projects/*"]
effort: 3
---

这里是技能指令，Markdown 格式。
```

### 验证

- `find_skills()` 返回的 SkillDef 列表包含 name/description/allowed_tools/paths/body
- `match_skills()` 对无 paths 的技能总是匹配，对空 current_path 跳过 path-scoped 技能
- `format_skills_for_prompt()` 输出不包含未转义的 HTML
- 测试覆盖：`test_agent_inline_tool_calls.py` 中有 skills_loader 测试

---

## 规则 3：Context Collapse 可回放、可审计

**背景**：`compressor.py` 已实现压缩前/后快照 + compaction 事件记录。
每次压缩都产生 `pre_compress` 和 `post_compress` 快照，压入的原始事件 id 记入
compaction 事件的 `folded_event_ids`。

### 规则

1. **每次压缩必须写 compaction 事件**：含 `folded_event_ids`、`summary`、`compression_ratio`
2. **每对压缩操作产生两个快照**：`pre_compress`（压缩前消息状态）+ `post_compress`（压缩后消息状态）
3. **恢复操作必须记录 restore 溯源事件**：`snapshot_restore` 事件，含 snapshot_id、类型、event 边界
4. **保留策略明确**：每 conversation 保留最近 15 个 periodic + 10 组 pre/post_compress

### 边界

- 快照数据存 JSONB（`snapshot_data` 字段），不当做消息源——消息源始终是 `agent_events` 表
- compaction 事件不删除原始事件，只标记哪些被折叠（`folded_event_ids` 列表）
- `project_to_messages()` 读取时自动跳过被折叠的事件，插入系统摘要消息
- 保留策略由 `enforce_retention()` 和 `post_turn_hooks._hook_cleanup_archive()` 双重保障

### 验证

- 压缩后事件数不变（原始不删），只投影时跳过 `folded_event_ids`
- restore 返回的消息列表与压缩前的投影一致
- `agent_events` 表可查询到 `snapshot_restore` 类型事件
- 超过保留阈值的旧快照被定期清理（后台 maintenance loop + post-turn hook）

---

## 实施基线

以下检测点在下一轮加能力前确认：

- [ ] 新加的能力（capability）是否已注册 tool metadata？
- [ ] 新加的工具是否需要放到并发只读批次？
- [ ] 新的对话后处理逻辑是否该写成 post-turn hook？
- [ ] 快照保留策略是否需要调整（EVERY_N_TURNS/MAX_PERIODIC_SNAPSHOTS）？
