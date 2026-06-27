---
name: "知识库 Prompt 模板数据库化验收复核"
type: task
tags: ["knowledge", "prompt", "framework", "verification"]
created: 2026-06-26
agent: codex
---

复核了“框架任务-知识库Prompt模板数据库化与只读入口”。已确认 backend/app/services/prompt_service.py 新增 get_template_by_name/render_template/render_template_sync，backend/app/routers/prompt.py 暴露 GET /api/prompts/templates/by-name/{name} 且 viewer 可读；backend/app/seed.py 中已写入 knowledge 分类和 4 条模板；modules/knowledge/backend/services/profile_service.py、entity_service.py、fusion_service.py 均改为通过 load_prompt(db, KEY) 读取模板，三段长中文 system prompt 已从 service 代码移除。实测：GET /api/prompts/templates/by-name/knowledge_profile_system 返回 200；framework_prompt_templates 中 knowledge_* 共 4 行，category=knowledge 计数为 4；backend/tests/test_prompt_read.py 单测 10/10 通过；全量 pytest 结果为 437 passed, 1 failed，失败项是既有的 tests/test_file_system_create_list_detail.py::test_create_folder_and_list，与本次 prompt 改动无关。
