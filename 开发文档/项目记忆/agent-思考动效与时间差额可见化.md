---
name: "Agent 思考动效与时间差额可见化"
type: task
tags: ["agent", "前端", "后端", "计时", "动效", "响应等待", "schedule_overhead", "华世王镞-v2"]
created: 2026-06-27
agent: zcode
---

1. 思维过程卡片增加转圈动效：运行态且内容不足 20 字符时标题栏显示旋转 spinner，展开后显示"思考中…"；内容到齐后 spinner 消失，结束后显示耗时

2. 时间差额可见化——"响应等待"条目：
   - 后端：最终持久化前，汇总所有 thinking+tool_result 的 duration_ms，与 work_duration_ms 做差；差额 >500ms 则往 timeline 头部插入 schedule_overhead 条目
   - 前端实时：finishWorkGroup 同样计算差额，>500ms 则追加到工作组 items
   - 前端恢复：expandTimeline 处理 schedule_overhead 条目，WorkTraceGroup 渲染为灰色小行「响应等待 · 8秒」

3. 所有 timeline entry（thinking/tool_call/tool_result/text/work_summary）都带 started_at 绝对时间戳，用于后端精确计算每段耗时
