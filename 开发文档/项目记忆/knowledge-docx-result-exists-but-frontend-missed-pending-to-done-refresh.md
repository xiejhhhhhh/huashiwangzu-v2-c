---
name: "knowledge docx result exists but frontend missed pending-to-done refresh"
type: gotcha
tags: ["knowledge", "frontend", "docx", "pipeline", "progress", "ui"]
created: 2026-06-26
agent: codex
---

User uploaded a docx and thought no analysis content was produced. DB/API showed the docx was ingested as `document_id=1`, `kb_pipeline` completed, and fusions/profile/chunks existed. The frontend issue was that document opening only started polling for `running`, not `pending`, and `pollTick` loaded results only on `wasRunning -> done`, missing `pending -> done` and already-done-but-empty-result states. Fixed `modules/knowledge/frontend/index.vue` so handshake/open polling includes pending, and result loading happens whenever current progress is done and fusions/profile are not loaded. Rendered browser validation confirmed the Word node opens to `1 页 · 分析完成` with overview content.
