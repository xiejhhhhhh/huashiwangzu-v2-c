---
name: "Agent 助手工作包裹显示与计时改造"
type: task
tags: ["agent", "前端", "后端", "SSE", "工作组", "计时", "历史恢复", "华世王镞-v2"]
created: 2026-06-27
agent: zcode
---

将 AI 助手回复过程改为工作组包裹组件渲染：

后端：
- tool_loop_runtime 在进入 run 循环时立即广播 work_start SSE，结束时广播 work_done（带 duration_ms）
- 工作耗时写入 AgentMessageMeta.usage (work_duration_ms/work_duration_sec) 和 timeline (work_summary entry)
- 历史恢复时前端从 timeline/usage 重建折叠工作组

前端：
- 新增 WorkTraceGroup.vue 组件，作为"正在工作/已工作"折叠包裹，内含思考卡片和工具卡片
- index.vue 增加 work_group 消息类型，流式处理 work_start/work_done 事件，思考/工具事件写入当前工作组 items
- 补上 replace/usage 事件处理缺口
- ThinkingCard 增加 durationMs prop，完成后标题显示耗时
- ToolCallCard 增加 durationText，tool_result 状态显示工具耗时
- expandTimeline 从历史 timeline 按 work_summary 重建折叠工作组
- 收敛旧 workSummaryText/work_summary 实现
