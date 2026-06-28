---
name: "Agent 最终总结阶段 XML 清洗修复"
type: task
tags: ["agent", "runtime", "final-summary", "xml-cleaning", "empty-message"]
created: 2026-06-28
agent: zcode
---

修复了前一个提交（空消息拦截）引发的副作用：`persist_assistant` 清洗后空内容拦截生效，但 `_generate_final_summary` 产生的回复全是 `<invoke>` XML 标记，没有实际文本，被拦截后前端完全不显示回复。

根因：`_generate_final_summary` 直接将 raw token 追加到 `full`，未经过 `parse_inline_tool_calls` 清洗。模型在工具轮次耗尽后的"总结"阶段仍输出 XML 式工具调用（而非自然语言总结）。

修法：`_generate_final_summary` 流式循环结束后，对整个 `full` 内容调用 `parse_inline_tool_calls` 清洗 XML。若有变化则替换 `full`。这样 `persist_assistant` 收到的是清洗过的内容，非 XML 文本得以保留。纯 XML 的情况则仍被 `persist_assistant` 空检查拦截。

验证：`ruff check` 全绿，`pytest test_stream_emitter_guardrails.py` 3 passed。提交 `cb1622b`，后端已重启。
