---
name: "knowledge-schema-evolution节点2-schema诊断层决策"
type: "architecture"
tags: [knowledge, schema-evolution, pipeline-diagnostics, raw-fusion, 20260703]
agent: "knowledge-schema-evolution-worker"
created: "2026-07-02T16:20:30.797501+00:00"
---

完成 knowledge 链路证据收集：CodeGraph/工具台确认现有 kb_documents 仅有 parse/vector/raw/fusion 状态字段，kb_pipeline_stale 只存 stage hash；pipeline_orchestrator 已有 degraded 语义但诊断主要停留在任务 result/log 中。DB 实测显示历史 kb_raw_data/kb_page_fusions 中存在大量内容为空但状态曾可被视作完成的行，后续 raw/fusion/graph 扩展需要稳定诊断落点。决策：在 modules/knowledge 内新增 kb_pipeline_runs、kb_pipeline_stage_runs 作为全链路/阶段级持久诊断账本，并为 kb_raw_data、kb_page_fusions 补 status/error_message/duration_ms/diagnostics_json 级字段。这是结构性收益，不绑定单个 bug。
