---
name: "image-vision sweep r2 evidence checkpoint"
type: "task"
tags: [image-vision, sweep, evidence, bad-params, vlm-cost, task_id:image-vision-sweep-20260703-r2]
agent: "codex-image-vision-sweep-20260703-r2"
created: "2026-07-03T07:52:25.029499+00:00"
---

证据节点：已读开发文档/README.md、模块开发文档、modules/image-vision/README.md；用 routes/capabilities/db_schema/code_explore/code_node/code_impact 查证。现状 image-vision 仅注册 describe(file_id)，router 先调用 VLM，失败后才返回少量元数据，未输出结构化本地事实/成本策略。run_uploaded_file_capability 已通过 file_reader.check_file_access 做 owner/share 权限与路径边界，但 require_positive_file_id 对负数/非整数抛 ValueError。现状探针确认：call_capability file_id=-1 和 file_id='abc' 均 500；POST /api/image-vision/describe file_id=-1 也是 500，file_id='abc' 是统一 422。
