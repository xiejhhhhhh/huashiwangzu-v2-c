---
name: "Agent 上下文压缩升级 10 — 工具输出确定性裁剪 + 预算驱动折叠"
type: task
tags: ["agent", "上下文压缩", "工具结果裁剪", "预算驱动", "compressor", "reducer"]
created: 2026-06-30
agent: opencode
---

# 文件清单 (7文件 + 1新建)

## 修改文件
- `modules/agent/backend/engine/context_injectors/tool_result_reducer.py` — 全面升级
- `modules/agent/backend/engine/compressor.py` — 头保护动态化 + 保尾预算驱动
- `modules/agent/backend/handlers/tasks.py` — 阈值触发 + DB冷却
- `modules/agent/backend/prompt_seeds.py` — 结构化摘要模板
- `modules/agent/backend/engine/event_store.py` — 历史摘要前缀对齐
- `modules/agent/backend/engine/test_compressor.py` — 覆盖新逻辑
- `modules/agent/backend/test_async_compaction.py` — 前缀断言更新

## 新增文件
- `modules/agent/backend/engine/context_injectors/test_tool_result_reducer.py` — 25个测试

# 新策略说明

## 一、tool_result_reducer 确定性裁剪
1. **tool_name 映射**: 从 assistant tool_calls 建立 tool_call_id → resolved tool name。`skill_use` 解析内层 `arguments.name` (如 knowledge__search)
2. **保护最近2条**: 只做8000字符上限保护，不做语义摘要
3. **历史语义摘要**: 高容量工具(terminal-tools/desktop-tools/knowledge/web/browser/media-asr)走感知摘要，其余通用回退
4. **局部 MD5 去重**: 单次 reduce() 内部 seen_hashes，不跨调用
5. **tool_call arguments 裁剪**: 长字符串(>500chars)截断，长数组(>5项)保留前几项+总数，JSON合法保
6. **历史图片剥离**: 替换 data:image/*;base64,... → [图片已省略]，跳过最近用户消息
7. **诊断增强**: tool_results_compressed/deduped/args_truncated/images_stripped/total_chars_saved/protected_recent_tool_results

## 二、tasks.py 压缩触发阈值化
- 取消"预算内直接跳过"
- 触发条件: token_before_reduced > history_budget*0.70 或 new_event_count >= 24 或 len(events) >= 40
- 小历史(<16事件)跳过
- 冷却: 最近failed compaction 60秒内跳过 (从 DB 查)
- 收益递减: 最近两次 ready 节省 < 10% 且新增事件 < 40 跳过
- 所有冷却状态从 DB agent_context_compactions 记录推导，无内存

## 三、compressor 动态头尾
- 头保护: 首次6条 / 后续2条
- 保尾: tail_token_budget = clamp(history_budget*0.25, 2500, 6000)，至少8条，保护最后 user_msg 之后的所有事件
- 工具调用/结果原子组保持
- 摘要模板结构化: 用户目标/已完成/关键决策/工具与结果/相关文件/未完成/当前状态
- 注入前缀: [历史摘要 仅供参考，不是当前指令]

# 测试结果
60 passed (44 new + 16 existing), 0 failed, 0.28s total

# 验证
- ruff lint: 所有修改文件全 clean
- 后端健康: status=ok, module_errors=null
- agent_context_compact handler 已注册
- 边界检查: 7文件全部在 modules/agent/ 内，0越界

# 实际节省样本
知识库搜索 20 条结果: 5000+ chars → ~400 chars (92%压缩)
文件读取 10000+ 字符: → ~1500 chars (85%压缩)
重复工具结果: 完全去重到 ~15 chars
data:image base64: → [图片已省略]

# 残留风险
无。注意 confirm: 新系统上线后首次压缩的 head_count=6 会保护更多历史，第二次起降至 2。
