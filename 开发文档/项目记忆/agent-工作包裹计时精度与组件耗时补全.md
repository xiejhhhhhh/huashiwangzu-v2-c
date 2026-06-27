---
name: "Agent 工作包裹计时精度与组件耗时补全"
type: task
tags: ["agent", "前端", "计时", "组件耗时", "秒级", "修复"]
created: 2026-06-27
agent: zcode
---

修复两点：

1. 工作包裹初始显示 "0ms" → 改为秒级格式化，"0秒" 起步，每秒自增
   - WorkTraceGroup.formatDuration: ms<1000 不再显示 ms，统一用秒
   - 实时计时器从 200ms 改为 1000ms 间隔

2. 每个思考/工具组件结束时都显示执行耗时
   - applyThinkingEvent: 记录每段思考开始时间 (_lastThinkingStart)，新事件到达时关闭上一张卡并计算耗时
   - applyToolResultEvent: 新增 durationMs 参数，从 SSE/timeline 传入
   - processStreamResponse: tool_result 分支传递 evt.duration_ms
   - expandTimeline: 恢复时传递 e.duration_ms
   - closeLastThinking(): 辅助函数，finishWorkGroup/flushStreamingAsMessage/stopGeneration 均调用
   - 思考卡显示 "思维过程 · 1.3秒"，工具卡显示 "工具记录 · 234ms"
