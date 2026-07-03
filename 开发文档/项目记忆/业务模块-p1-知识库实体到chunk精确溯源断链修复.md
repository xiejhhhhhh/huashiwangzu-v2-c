---
name: "业务模块-P1-知识库实体到chunk精确溯源断链修复"
type: task
tags: ["knowledge", "entity", "chunk", "traceability", "溯源", "断链修复"]
created: 2026-07-03
agent: opencode
---

## 修改
- 文件：`modules/knowledge/backend/services/entity_service.py`
- 函数：`process_document_entities_from_fusions()`

## 修复内容
1. **KbChunkEntity 关联重建**：原有代码删除了 KbChunkEntity 记录但从不重建，本次在实体抽取后逐页查询 KbChunk，建立实体到每个源 chunk 的精确关联
2. **Evidence chunk_id 修正**：原 hardcode chunk_id=0/page=0 改为指向实际 chunk——每个(实体,页)产出一条证据，chunk_id 指向该页第一个 chunk
3. **页级溯源信息保留**：添加 entity_page 列表，LLM 抽取实体时同步记录每个实体的页号，用于后续 chunk 查找<br>4. **entity_name_to_id 映射**：实体保存时建立 name→entity_id 映射，支撑后续证据和 chunk_entity 写入

## 验证
- ruff lint 通过
- pipeline_stage_semantics 10/10 通过
- search_service_vector_normalize 4/4 通过
- 后端 health 200 OK
- git diff 确认仅改 `modules/knowledge/` 内
