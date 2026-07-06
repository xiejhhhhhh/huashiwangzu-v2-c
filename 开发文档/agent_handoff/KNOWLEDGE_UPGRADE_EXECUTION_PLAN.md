# Knowledge Upgrade Execution Plan

> 临时执行方案。用于本轮“企业级知识库架构升级 + 企业微盘继续导入”施工前对齐；实现完成后，应把长期规则沉淀到 `modules/knowledge/README.md` 或相关稳定文档，并删除本文件。

## 1. 目标

在不替换 PostgreSQL、pgvector、现有 `kb_*` 表和现有 pipeline 的前提下，吸收“多层哈希、证据链、断点重跑、图片近似分组”的工程思想，升级知识库底座。

本轮不追求提前建立固定标签体系。当前阶段优先保证：

1. 企业微盘资料能大量导入。
2. 每个分析节点都有沉淀产物。
3. 每个节点可审计、可断点、可重跑。
4. GPT/VLM 分析精度优先，token 成本和本机性能消耗可接受。
5. 标签、文档类型、实体类型、关系类型允许模型先自由返回，形成“混沌原始标签池”。
6. 样本足够后，再做标签聚类、归一、合并、治理和正式知识图谱收敛。
7. 图片/海报不把二进制写入数据库，只保留文本、版式、视觉结构、指纹、相似关系和证据链。

## 2. 架构原则

### 2.1 不换底层

继续使用当前架构：

- 框架文件存储保存原始物理文件。
- `kb_documents` 保存知识库文档引用。
- `kb_raw_data` 保存 raw text / OCR / vision 三轮采集。
- `kb_page_fusions` 保存页级融合结果。
- `kb_document_profiles` 保存文档画像。
- `kb_entity_dictionary` / `kb_graph_nodes` / `kb_graph_edges` 保存实体和图谱。
- `kb_evidence` 保存证据。
- `kb_pipeline_runs` / `kb_pipeline_stage_runs` 保存 pipeline 运行诊断。
- pgvector 继续承载向量检索。

不引入 Neo4j、Elasticsearch、FAISS 或自研“三进制哈希图引擎”。如果未来数据规模证明需要，再单独评估。

### 2.2 混沌标签先保存，后治理

当前阶段不要把标签、文档类型、实体类型做成固定枚举。原因：

- 企业微盘样本尚未充分展开，提前设计标签体系容易把后续资料框死。
- 历史资料类型复杂，模型自由输出能先暴露真实业务分布。
- 后续可以基于真实样本做聚类、同义词合并、黑名单、标签树和标准本体。

落地方式：

- 模型返回的 `doc_type`、`business_tags`、`usage_tags`、`content_boundaries`、实体类型、关系类型全部原样保存。
- 原始标签先作为弱检索信号和后续治理输入，不作为强过滤依据。
- 暂不因为标签混乱阻塞企业微盘入库。

### 2.3 精度优先

当前核心是一次性把企业历史资料分析准确，后续大规模 token 调用会明显减少。

因此：

- 不为了省 token 跳过关键 VLM/LLM 分析。
- 相似图片初期也可以完整跑 VLM，同时记录相似关系，作为后续复用依据。
- 自动复用代表图 VLM 结果必须保守启用，避免污染知识库。
- 所有 fallback、degraded、failed 都要落库，后续可补跑。

## 3. 总体升级路线

分三层推进：

### 第一层：分析账本

目标：每个 stage 的输入、输出、模型、提示词、版本、状态、耗时、错误、依赖都可追溯。

新增统一表，而不是为每个 stage 新建一套账本表：

```text
kb_analysis_artifacts
```

业务结果仍写入现有表；账本表只记录“这次分析是如何产生的”。

### 第二层：证据链增强

目标：每个标签、实体、关系、结论、视觉结构都能追溯到文档、页、块、raw 轮次、融合页和模型诊断。

优先增强 `kb_evidence`，必要时新增关系证据表：

```text
kb_relation_evidence
```

### 第三层：重跑规划器

目标：未来改 prompt、模型、schema、OCR/VLM 预处理、词典、实体治理时，系统自动判断最小重跑范围。

在现有 `pipeline_orchestrator` / `stale_tracker` 基础上升级：

- 不再用时间戳作为非源文件 stage hash。
- 改成稳定的 `input_hash + output_hash + prompt_hash + schema_version + model_profile`。
- 支持 document/page/block 粒度重跑。

## 4. 新增和增强的数据结构

### 4.1 `kb_analysis_artifacts`

用途：统一分析产物账本，覆盖 raw、fusion、profile、entity、relations、embedding、image_similarity 等 stage。

建议字段：

```text
id
owner_id
document_id
file_id
task_id
pipeline_run_id
stage
unit_type              -- document/page/block/raw_round/entity/relation/image_asset
unit_key               -- page:1 / page:1:round:vision / block:xxx / relation:xxx
source_artifact_ids    -- JSON array
input_hash
output_hash
prompt_hash
model_profile
model_used
schema_version
preprocess_version
status                 -- pending/running/done/degraded/failed/skipped/stale
reason
diagnostics_json
metrics_json
token_input
token_output
duration_ms
started_at
completed_at
created_at
updated_at
```

关键规则：

- `input_hash` 基于上游真实产物内容生成。
- `output_hash` 基于当前 stage 关键输出生成，排除时间戳、耗时等非业务字段。
- `prompt_hash` 基于 prompt 完整文本生成。
- `schema_version` 由代码常量或配置提供。
- `source_artifact_ids` 记录依赖链，便于追溯和重跑。

### 4.2 增强 `kb_raw_data`

当前已有：

- `document_id`
- `file_id`
- `page`
- `round`
- `source_type`
- `content`
- `model_used`
- `confidence`
- `metadata_json`
- `content_hash`
- `status`
- `error_message`
- `duration_ms`

建议增强：

```text
input_hash
prompt_hash
schema_version
preprocess_version
artifact_id
source_image_hash
```

说明：

- raw text、OCR、vision 每轮都要能独立重跑。
- 对图片/扫描页，`metadata_json` 继续保存 OCR words、图像压缩信息、尺寸、VLM 预处理信息。
- 不存图片二进制。

### 4.3 增强 `kb_page_fusions`

当前已有融合正文、摘要、标题、结构化 JSON、标签、冲突、证据、diagnostics。

建议增强：

```text
input_hash
output_hash
prompt_hash
schema_version
artifact_id
source_raw_ids
```

说明：

- 页级融合是后续 profile/entity/vector 的核心输入。
- 如果 raw 未变、prompt 未变、schema 未变，则 fusion 可直接复用。
- 如果 fusion output_hash 未变，下游可跳过。

### 4.4 增强 `kb_document_profiles`

当前已有 `labels_json`，适合保存混沌标签。

建议增强：

```text
input_hash
output_hash
prompt_hash
schema_version
artifact_id
model_used
diagnostics_json
raw_doc_type
```

说明：

- `doc_type` / `labels_json` 先保存模型原始输出。
- 不急着映射为标准标签。
- 后续治理阶段再从 `labels_json` 和 `raw_doc_type` 生成标准标签。

### 4.5 增强 `kb_evidence`

当前证据字段粒度还不够。建议增加：

```text
raw_data_id
page_fusion_id
artifact_id
source_round          -- text/ocr/vision/fusion/profile/entity/relation
claim_type            -- tag/entity/relation/conclusion/visual_layout/doc_type
bbox_json
offset_json
source_hash
prompt_hash
model_used
diagnostics_json
```

说明：

- 图片/海报证据用 `bbox_json` 保存坐标和区域。
- 文本证据用 `offset_json` 保存字符范围或 block 定位。
- 自动继承的相似图片分析要标记来源，不能冒充原图自分析结果。

### 4.6 新增 `kb_image_assets`

用途：图片、海报、扫描页、PPT 页面截图等视觉资产的指纹和相似分组。

建议字段：

```text
id
owner_id
document_id
file_id
page
block_id
raw_data_id
asset_type              -- poster/screenshot/product/scan/page_render/unknown
visual_box_json
width
height
file_md5
ahash
dhash
phash
ocr_text_hash
clip_embedding          -- optional pgvector, 可后置实现
similarity_group_id
group_representative
hash_schema_version
clip_model_used
status
diagnostics_json
created_at
updated_at
```

短期实现建议：

- 先做 `dhash` / `phash` / 尺寸 / OCR 文本 hash。
- CLIP embedding 可作为第二阶段增强，不阻塞当前企业微盘继续导入。
- 初期不自动跳过 VLM，只记录相似关系和分组。

### 4.7 新增 `kb_image_similar_pairs`

用途：保存两张图片之间的相似判定证据。

建议字段：

```text
id
owner_id
source_asset_id
target_asset_id
hamming_phash
hamming_dhash
ocr_text_similarity
clip_cosine
ssim_score
similarity_level       -- high/suspected/different
decision_reason
calc_version
manual_review
review_result          -- confirm/reject/null
created_at
updated_at
```

说明：

- 两两相似分数要落库，便于审计。
- 自动继承代表图结果前，必须能追溯为什么判定相似。

### 4.8 新增 `kb_image_similarity_groups`

用途：视觉近似图片分组和代表图管理。

建议字段：

```text
id
owner_id
representative_asset_id
asset_count
asset_type
status
rep_vlm_artifact_id
rep_vlm_cache_json
created_at
updated_at
```

短期策略：

- 只分组，不默认复用。
- 高相似度组可在后续启用“代表图 VLM 结果辅助继承”，但必须保留当前图片自身 OCR 和证据。

## 5. 图片相似分组策略

### 5.1 当前阶段策略

精度优先，所以初期：

1. 所有图片/海报/扫描页照常进入 VLM 分析。
2. 同时计算感知哈希和 OCR 文本 hash。
3. 建立相似 pair 和 group。
4. 不因为相似就跳过 VLM。
5. 只把相似关系作为后续治理、素材归类、重复分析优化依据。

### 5.2 后续可选复用策略

当真实数据验证稳定后，再启用保守复用：

- `high`：pHash/dHash 距离达标，且 OCR 文本差异低，且 CLIP 相似高时，允许继承代表图 VLM 版式结构作为辅助。
- `suspected`：只建立关系，不继承；可轻量 VLM 校验或人工复核。
- `different`：不关联。

继承时必须：

- 当前图片仍保留独立 OCR。
- 继承字段标记 `source=group_rep`。
- 检索证据优先展示 `source=self_vision` 或当前图片自身证据。
- 人工 reject 后立即断开 group，并可强制独立重跑。

### 5.3 初始阈值

先作为诊断，不作为跳过依据：

- pHash high：Hamming <= 8
- pHash suspected：9-16
- dHash high：Hamming <= 6
- dHash suspected：7-14
- OCR 文本高度相似：MinHash/Jaccard >= 0.85
- CLIP high：cosine >= 0.90，后续实现
- CLIP suspected：0.75-0.89，后续实现

## 6. 重跑规划器

### 6.1 Stage 依赖

当前核心依赖：

```text
source_file
  -> raw_text/raw_ocr/raw_vision
  -> page_fusion
  -> profile
  -> entity
  -> relations
  -> retrieval_index
```

图片相似分组是旁路 stage：

```text
raw_vision/image_preprocess
  -> image_fingerprint
  -> image_similarity_group
```

它不应该阻塞主知识库入库，但应写入诊断和证据。

### 6.2 重跑触发规则

| 变化 | 重跑范围 |
|---|---|
| 源文件 MD5 变化 | 对变化页/块执行 raw + downstream |
| OCR 引擎或 OCR prompt 变化 | raw_ocr + page_fusion + downstream |
| VLM 图片压缩算法变化 | raw_vision + page_fusion + downstream |
| page_fusion prompt 变化 | page_fusion + profile + entity + relations |
| profile prompt 变化 | profile + relations |
| entity prompt 变化 | entity + relations |
| relation 算法变化 | relations |
| embedding 模型变化 | retrieval_index / vector 重建，不重跑 raw/fusion |
| 标签治理规则变化 | 不重跑模型分析，只跑标签归一治理 |
| 图片 hash 算法变化 | image_fingerprint + image_similarity_group，不重跑 VLM |
| CLIP 模型变化 | image_similarity_group，不重跑 raw/fusion |

### 6.3 跳过规则

- 当前 stage 的 `input_hash + prompt_hash + schema_version + model_profile` 与最新 artifact 一致，并且 status 为 `done`，则跳过。
- 如果 output_hash 未变化，下游可以继续跳过。
- 如果 status 为 `degraded`，默认不视为最终可跳过；除非配置允许 degraded 作为可依赖产物。
- 如果 status 为 `failed`，从 failed stage 恢复，不重跑上游已 done stage。

## 7. 企业微盘导入策略

### 7.1 当前优先级

先继续大量导入企业微盘，目标是形成足够样本：

- PDF / PPT / Word / 图片 / 文本优先。
- 视频跳过或只登记，不做本轮分析。
- MD5 完全重复文件跳过重复分析。
- MD5 不同但视觉近似的图片不跳过，先完整分析并记录相似分组。
- 所有模型原始标签原样保存。

### 7.2 导入目录结构

必须保持企业微盘原目录结构映射到网站文件夹中，避免“企业微盘导入”下文件乱堆。

原则：

- 企业微盘原相对路径必须保存到 framework file metadata 或知识库 metadata。
- 上传到账号文件夹时按原目录层级建 folder。
- 知识库左侧目录树展示应能按导入目录展开。

### 7.3 批量节奏

在新账本和断点能力稳定前，继续小批量验证：

1. 先跑 20 个文件，覆盖 PDF、图片、docx。
2. 验证每个 stage artifact 是否落库。
3. 验证失败后能从失败 stage 恢复。
4. 验证相似图片是否能生成 pair/group，但不跳过 VLM。
5. 再提升批次和并发。

## 8. 分阶段执行路线

本方案按“薄底座 → 真实小批验证 → 放量导入 → 后置治理”的节奏推进。每阶段都必须能独立提交、验证、回滚；目标模式执行时也必须按阶段推进，不能把后置阶段提前混进第一阶段。

优先级定义：

- P0：必须先做，否则后续大量导入会制造不可控债务。
- P1：应尽快做，能显著提升断点、证据和精度。
- P2：有价值，但等真实样本和前序能力稳定后再做。
- P3：长期增强，当前只保留扩展口，不实现。

### Phase 0：基线收口与保护点（P0，已完成）

目标：

- 当前 GPT-5.5 路由、fallback pause、worker 热配置、断点恢复、前端修复已提交并合并主线。
- 保证后续架构升级从干净主线出发。

进入条件：

- 当前分支无未提交代码。
- `main` 已包含当前知识库断点与 worker 配置改动。

退出验收：

- GitHub PR 已合并。
- 本地可从 `main` 新建下一阶段分支。

### Phase 1：分析账本最小闭环（P0）

目标：

- 新增 `kb_analysis_artifacts`。
- 建立稳定 hash 工具：`input_hash`、`output_hash`、`prompt_hash`、`schema_version`。
- raw/fusion/profile/entity/relations 每个 stage 运行后写 artifact。
- 当前阶段只做 append-only 账本，不把 artifact 账本作为调度权威。

必须做：

- 表结构和幂等迁移。
- artifact service：创建账本记录、稳定 hash、prompt hash、模型诊断提取。
- hash 规范：JSON 排序、排除时间/耗时/token 等非业务字段。
- prompt hash 尽量从实际 prompt 文本生成；无 prompt 的确定性 stage 允许为空。
- 所有 stage 写入 artifact，不影响原业务表。
- 旧数据兼容：没有 artifact 的历史数据不报错；是否生成 `legacy_imported` 占位留到重跑规划阶段。

暂不做：

- block/entity/relation 级完整 DAG。
- artifact 驱动的跳过、latest 查询、stale 标记和自动重跑。
- token 成本精细核算 UI。
- 自动批量重跑全库。

退出验收：

- 每个核心 stage 运行或跳过后能写入 `kb_analysis_artifacts`。
- artifact 写入失败不影响 pipeline 主流程。
- 同一文档重复跑时，现有 stage status/stale 逻辑继续可用，并额外记录 skipped artifact。
- artifact 中包含稳定 `input_hash`、`output_hash`、`prompt_hash`、`schema_version`、模型诊断和耗时。
- 已有知识库测试通过，并新增 artifact hash 测试。

真实验证：

- 选 3 个文件：1 个 PDF、1 张图片、1 个 Office 文档。
- 每个文件至少产生 raw/fusion/profile/entity/relations artifact。
- 人工制造一次失败，确认失败 artifact 和 stage_run 都可追踪。

回滚策略：

- 新表不影响旧业务表；如有问题，关闭 artifact 跳过逻辑，保留只写账本。

### Phase 2：证据链最小增强（P0/P1）

目标：

- 重要判断必须能回溯到来源页、raw 轮次、fusion 页和 artifact。
- 先增强现有 `kb_evidence`，不急着拆出复杂 claim 系统。

必须做：

- 给 evidence 增加或通过 metadata 保存：`raw_data_id`、`page_fusion_id`、`artifact_id`、`source_round`、`claim_type`。
- page fusion 记录来自哪些 raw ids。
- profile 的 `doc_type`、labels evidence 尽量写回 evidence 或 profile `labels_json.evidence`。
- entity evidence 绑定 page_fusion/raw_data，而不是只有 chunk_id。
- 图片/海报视觉结构证据能指向 raw_vision 记录。

暂不做：

- 完整 claim 表。
- 人工审核工作流。
- 标签标准化映射。

退出验收：

- 任意文档的 doc_type/标签能找到页码和 excerpt。
- 任意实体能找到 evidence，并能回到 page_fusion/raw_data。
- 图片视觉描述能回到 raw_vision 的模型诊断。

真实验证：

- 抽 5 个企业文件，人工检查模型结论和证据是否对应。

回滚策略：

- evidence 增强字段只附加，不改变检索主流程；如证据写入异常，pipeline 不应整体失败，应标记 diagnostics。

### Phase 3：重跑规划器 dry-run（P0/P1）

目标：

- 在真正批量重跑前，先能回答“为什么要跑、跑哪些、跳过哪些”。
- 初期只做 dry-run，不自动执行大范围重跑。

必须做：

- `plan_rerun(document_id, reason, stage?)` 返回重跑计划。
- 支持原因：`prompt_changed`、`schema_changed`、`model_changed`、`source_changed`、`vlm_preprocess_changed`、`manual_failed_retry`。
- 输出预计 stage、页数、artifact 数、是否需要模型调用。
- 和 `pipeline_orchestrator` 的 stage registry 保持同一依赖图。

暂不做：

- 全库自动重跑。
- UI 批量治理面板。
- token 成本预测精算。

退出验收：

- `prompt_changed(entity)` 规划 entity + relations。
- `prompt_changed(profile)` 规划 profile + relations。
- `vlm_preprocess_changed` 规划 raw_vision + fusion + downstream。
- `manual_failed_retry` 从 failed artifact 开始，不动上游 done artifact。

真实验证：

- 对 3 个已完成文档跑 dry-run，计划和人工预期一致。

回滚策略：

- dry-run 不修改业务数据；如计划器有误，不接入执行入口。

### Phase 4：图片相似分组最小版（P1）

目标：

- 记录 MD5 不同但视觉近似的图片关系。
- 当前阶段不因为相似跳过 VLM，不自动继承代表图分析结果。

必须做：

- 新增 `kb_image_assets`、`kb_image_similar_pairs`、`kb_image_similarity_groups`。
- 对图片文件、PDF 渲染页、PPT 页面图生成 pHash/dHash。
- 保存 Hamming distance、判定等级、decision reason。
- 记录 group，但不覆盖图片自身 OCR/VLM 证据。

暂不做：

- CLIP 必选。
- SSIM 批量复核。
- 自动复用代表图 VLM。
- 自动跳过相似图片分析。

退出验收：

- MD5 不同但视觉近似图片能进入 suspected/high pair。
- pair 表有可审计距离和版本。
- 相似分组不会改变主 pipeline 分析结果。

真实验证：

- 从企业微盘选 20 张图片/海报/截图，确认相似分组结果。
- 人工抽查 false positive，调整阈值。

回滚策略：

- 图片相似是旁路 stage；关闭后不影响知识库主入库。

### Phase 5：企业微盘小批放量（P1）

目标：

- 使用 Phase 1-4 的断点、证据、相似关系能力跑真实企业数据。
- 继续保留混沌标签，不做标签治理。

执行节奏：

1. 20 个文件：覆盖 PDF、图片、Word/PPT。
2. 100 个文件：观察失败率、fallback、耗时、证据质量。
3. 300+ 文件：观察混沌标签分布、图片相似分组、重复跳过。
4. 再决定是否继续全量导入。

必须监控：

- done/degraded/failed/paused 数量。
- 每 stage 平均耗时。
- GPT/VLM fallback 率。
- 失败恢复是否从断点继续。
- evidence 覆盖率。
- 图片相似 false positive 样本。

退出验收：

- 重复文件不重复分析。
- 单点失败不导致整文件从头重跑。
- 真实文件可查到证据链。
- 混沌标签样本开始形成可治理分布。

回滚策略：

- 失败文件保留 artifact 和 stage run，不清空源数据。
- 可按 document/stage 重跑，不做全库清空。

### Phase 6：混沌标签样本审计与治理准备（P2）

目标：

- 样本足够后，不急着改模型，先导出分布和候选治理集。

必须做：

- 高频 raw tag 导出。
- raw doc_type 分布导出。
- 实体类型分布导出。
- 关系类型分布导出。
- 低置信/冲突/高频无意义标签导出。
- 同义标签候选聚类。

暂不做：

- 直接硬编码标签树。
- 一次性替换历史标签。

退出验收：

- 能给出第一版企业标签治理报告。
- 能决定哪些标签进入标准词典，哪些保留 raw，哪些黑名单。

### Phase 7：标准标签/实体/关系治理（P2/P3）

目标：

- 在真实样本基础上，逐步把混沌输出收敛成企业本体。

候选能力：

- `kb_tag_dictionary`
- `kb_tag_aliases`
- `kb_entity_type_mapping`
- `kb_relation_type_mapping`
- raw tag -> standard tag 批处理
- 人工确认/合并/禁用

启动条件：

- 企业微盘已导入足够样本。
- raw 标签和实体关系分布已审计。
- 已明确业务常用标签和需要禁用的噪声标签。

暂不作为当前阶段目标。

### Phase 8：高级图片复用与多模型校验（P3）

候选能力：

- CLIP 图片 embedding。
- SSIM 抽样复核。
- high similarity 图片继承代表图 VLM 作为辅助。
- 多模型交叉校验实体/关系。
- 冲突样本人工审核。

启动条件：

- 图片相似最小版 false positive 可控。
- 证据链已经足够区分 `self_vision` 和 `group_rep`。
- 大量重复图片造成真实 token 压力。

暂不作为当前阶段目标。

## 8.1 目标模式执行规则

如果后续开启目标模式，执行者必须遵守：

1. 每个 Phase 单独建分支或至少单独 commit。
2. 每个 Phase 完成后跑对应测试和真实数据验证。
3. 未通过退出验收，不进入下一 Phase。
4. P2/P3 能力不得混入 P0/P1 阶段。
5. 任何自动重跑能力必须先支持 dry-run。
6. 所有新增测试数据必须有标记和清理路径。
7. 不清空企业微盘已入库数据，除非用户明确要求。
8. 不用标签标准化阻塞当前导入。

## 8.2 阶段性提交建议

- Commit 1：`feat: add knowledge analysis artifacts`
- Commit 2：`feat: persist knowledge evidence lineage`
- Commit 3：`feat: add knowledge rerun planner dry run`
- Commit 4：`feat: track visual similarity for knowledge images`
- Commit 5：`chore: validate enterprise wedrive ingestion batch`

每个 commit body 必须包含：

- 数据库变更摘要。
- 行为变化。
- 回滚方式。
- 测试结果。
- 真实数据验证样本。

## 9. 测试计划

### 单元测试

- artifact hash 稳定性测试。
- prompt_hash 变化触发 stale。
- schema_version 变化触发 stale。
- stage 依赖展开测试。
- image hash Hamming distance 分级测试。
- evidence source link 序列化测试。

### 集成测试

- 选一个 PDF：raw done 后中断，从 fusion 恢复。
- 选一张图片：raw_vision failed 后补跑，只重跑该页/round。
- 选一组相似图片：MD5 不同，生成相似 pair/group。
- 修改 profile prompt：只重跑 profile/relations。
- 修改 entity prompt：只重跑 entity/relations。

### 真实数据验证

从企业微盘抽样：

- 5 个 PDF/报告。
- 5 张海报/宣传图。
- 5 张产品图。
- 3 个 Word/PPT 文件。
- 2 个低信息量素材。

验证：

- 每个文件有 pipeline run。
- 每个 stage 有 artifact。
- 每个重要结论有 evidence。
- 图片有 hash 记录。
- 相似图片有 pair/group。
- 出错后可从失败节点恢复。

## 10. 风险和边界

### 风险 1：表太多导致复杂度上升

处理：只新增一个统一 artifact 表和必要图片相似表，不按每个 stage 拆 ledger 表。

### 风险 2：混沌标签污染检索

处理：原始标签先保存，但作为弱信号；正式标签治理后再变强过滤。

### 风险 3：相似图片误继承污染知识库

处理：当前阶段不自动跳过 VLM，不自动复用代表图结果；只记录相似关系。后续启用继承时必须保留 source 标记和独立证据。

### 风险 4：断点逻辑误跳过

处理：hash 规则必须稳定；degraded 默认不作为完全 done；所有跳过写 stage run 和 artifact 诊断。

### 风险 5：schema 演进影响旧数据

处理：每个 stage 都带 schema_version；查询层兼容旧版本；必要时 dry-run 规划重跑。

## 11. 暂不做

本轮不做：

- 固定标签树。
- 正式实体类型本体。
- 正式关系类型本体。
- Neo4j / Elasticsearch / FAISS 引入。
- CLIP 必选实现。
- 自动跳过相似图片 VLM。
- 全库标签治理。
- 全量重跑。

这些等企业微盘样本积累后再单独规划。

## 12. 推荐下一步

1. 先收尾当前未提交代码，commit/push。
2. 开始 Phase 1：`kb_analysis_artifacts` + hash 工具 + pipeline artifact 写入。
3. 跑 20 个企业微盘文件做断点验证。
4. 开始 Phase 2：增强证据链。
5. 开始 Phase 3：图片相似分组，但不启用 VLM 自动复用。
6. 继续放量导入企业微盘。
7. 样本达到足够规模后，再启动“混沌标签治理/实体归一/关系收敛”任务。
