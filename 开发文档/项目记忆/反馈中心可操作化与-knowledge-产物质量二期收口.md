---
name: "反馈中心可操作化与 Knowledge 产物质量二期收口"
type: "task"
tags: [desktop, knowledge, feedback-center, export, source-unavailable]
agent: "codex-feedback-knowledge-product-r2"
created: "2026-07-04T08:09:09.113359+00:00"
---

# 改了什么
- 反馈中心新增显式 ActionItem 契约，聚合通知、任务队列、Agent workflow、Knowledge source unavailable/失败文档/治理待处理等来源。
- 任务栏通知面板支持 ActionItem 主动作与次动作，可打开 Agent/Knowledge 并传 payload；通知类动作继续走已读，非通知类忽略采用本地 session dismiss，避免伪造后端已处理。
- Knowledge 前端消费 payload，可定位文档或治理视图；导出按钮增加不可用原因提示；source unavailable 提供重新上传指导与带确认的删除无效记录动作；补齐可检索/深度分析/图谱无实体/失败树点等用户语义。
- Knowledge 导出后端收紧 format，只支持 markdown/html/json；Capability 非法格式返回清晰失败；导出源改为优先 page_fusion、无 fusion 时 fallback chunks，避免 chunk 与 page_fusion 重复；返回 metadata，HTML 转义用户内容。
- Knowledge sandbox 增加导出契约测试，README 更新导出、状态与 source unavailable 策略。

# 验证了什么
- mcp lint: modules/knowledge/backend/router.py、modules/knowledge/backend/services/export_service.py 均通过。
- pytest: backend/.venv/bin/python -m pytest modules/knowledge/sandbox/test_module.py，14 passed。
- frontend npm run build 通过，仅 chunk size warnings。
- modules/knowledge/sandbox npm run build 通过，仅既有 Rollup PURE/chunk warnings。
- git diff --check 通过。
- 目标 TS/Vue 范围 any/as any/@ts-ignore/@ts-expect-error 扫描 0 命中。
- 活栈探针覆盖 /api/health、/api/notifications、/api/tasks/worker/audit、/api/knowledge/dashboard/stats、documents、knowledge:get_pending_count、agent:list_workflows、knowledge:get_ingest_status、knowledge:export markdown/html/json/bad_format、HTTP export bad_format/markdown。
- 复现样本 document_id=40 导出不再重复 hello smoke，metadata export_source=page_fusion、block_count=1。

# 残留风险
- 未做浏览器截图验收。
- source unavailable 的删除入口是带确认的真实软删除，未清理历史 163 条 source unavailable 债务。
- 本次未提交、未暂存。

# 关联 commit
- 无。
