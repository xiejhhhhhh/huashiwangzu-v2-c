# WP3 内容旁路收口：Canonical Normalizer 与 Content Runtime 施工方案

日期：2026-07-17
承接：会话 492662d7（WP0/WP1/WP2 已落），本会话续做 WP3
边界母文档：§24（临时文档08审计 + 记忆 [[方案07产品底座-已审计回填与本轮边界]]）

---

## 一、阶段一：发现的问题（子代理三路实测，全带 file:line 证据）

### 1.1 三套 legacy IR 都不是真正写库的结构（最关键发现）

| IR | 定义位置 | 结构 | type | 写库？ |
|----|----------|------|------|--------|
| `ContentPackageIR` | `backend/app/schemas/content_package.py:79` | manifest+blocks，**递归 children** | 英文13种 | 否（写库结构和它对不齐） |
| `DocumentIR` | `backend/app/schemas/document_ir.py:84` | 扁平 blocks + PatchIR/ProjectionIR 一整套 | 英文7种 | 否（野心版，没接写路径） |
| `DocumentIr`（小写） | `modules/knowledge/backend/ir_models.py:52` | 递归 children + 中英转换表 | 英文17种 | 否（纯运行时中转，不落库） |

**真身**：parser raw dict（`schema_version:content-ir/v1`，英文 type，无 id）→ `package_service.run_pipeline` 轻加工（`_ensure_block_ids` 加 id）→ 组 `{manifest, blocks, parse_status}` 存进 `ContentPackageVersion.content_json`。这是**第四种事实结构**，既不是上面任何一套。

### 1.2 已有 `ir_normalizer.py` 是旧归一器，产出旧 schema，且没被调用

- `backend/app/services/content/ir_normalizer.py:17` `normalize_parser_output` 产出的是 **`content-ir/v1`**（content_type + 递归 children + 英文 type），**不是 CanonicalContentIRV1**（扁平 nodes/parent_id+order/profile_data/fidelity）。
- 而且 `package_service.run_pipeline` **根本没调它**——写库走裸 blocks。归一器与写路径脱节。
- 价值：它的 profile 塑形逻辑（spreadsheet 拢 sheet、presentation 按 slide 分组、image 兜底）可作为新 canonical 归一器的**参考**，但 schema 不同，要重写。

### 1.3 两条平行写/读管线，各吸各的 raw dict

- **Content 线**：`pipeline_service.handle_file_uploaded`（已被 WP2 下线，改唤醒编排器）→ `package_service.run_pipeline` → content_json。
- **Knowledge 线**：`parsing_service.parse_document` 独立按扩展名调 parser → `from_legacy_blocks` 收敛成 `DocumentIr`（小写）→ 当场分块/向量/导出 → 丢弃。两条线互不通。

### 1.4 直读物理原件 / 重新解析的旁路清单（WP3 要清除的目标）

**A. 纯重解析/直读物理（真旁路）**
1. `doc-viewer`：`index.vue:117` 每次打开重解析物理 docx（docx-parser→`read_uploaded_file`）
2. `ppt-viewer`：`index.vue:168` 每次打开重解析物理 pptx
3. `docs-open _read_content`：`handlers/content.py:30` 文本直读、xlsx/pdf/docx/pptx 全部重解析物理原件
4. `docs-open _write_content`：`content.py:106` `replace_file_content` 写物理内容库，**不落 ContentPackage**
5. `text_editor_service`：`:16/:36` 直读+直写物理原件
6. `csv_editor_service`：`:18/:41` 直读+直写物理原件
7. `editors.py`：`:43/61/80/98` 上面两个 service 的 HTTP 外壳

**B. Knowledge 旁路**
8. 重解析回退：`document_service.py:1154-1159`（CP 缺失/读失败即 `parse_document` 拉原件）
9. raw 阶段重解析：`raw_collection_service.py:434/485`（各自 `parse_document` 取分页文本）
10. **独立监听 `file.uploaded`**：`router.py:1311`——**和 WP2 编排器并存，重复摄取入口**（上一轮 WP2 下线 content 同步解析时的对称漏项）

**C. Excel 旁路**
11. `excel-engine`：彻底独立事实源，8 张 `excel_*` 表，零 ContentPackage 感知，`router.py:628` 首次打开直接 `parse_xlsx` 磁盘原件

**D. 部分旁路（已 Package 优先、仅回退物理，健康）**
- pdf/doc/ppt-viewer 的 `downloadBlob` 走 `/api/files/download`，`file_transfer.py:390` 已「先 ContentPackage 编译→回退物理」，物理只是兜底。
- `export_service` 是**反向正确形态**（ContentPackage→物理产物），WP3 目标就是让读取也长这样。

---

## 二、决定 WP3 边界的硬事实：改 content_json 形状会打断线上

`canonical_parse` 现在写的 content_json 是旧形状 `{manifest, blocks, parse_status}`。**若这一轮直接把它翻成 CanonicalContentIRV1，会同时打断所有当前读者**：

- Knowledge `_flatten_cp_blocks`（`document_service.py:1103-1146`）按旧 blocks 拍平——**你的主线，碰了就炸**
- `export_service` 按 content_json blocks 编译
- `package_service` 的 update_blocks/replace_text/append_blocks 编辑操作全对着旧结构
- WP2 的 `resource_extract` 阶段扫 content_json blocks 建 ResourceRef

**这正是方案 §WP7「回填 + 影子读 + 一次切换，须华哥在场」管的事。** 一次性翻形状 = 把 WP7 提前，高风险，且直接动知识库主线。

---

## 三、本轮 WP3 施工范围（安全增量，不打断线上）

**原则**：Canonical 层「产出可用、可读、可测」，但**不翻转线上读者**；翻转留到 WP7（你在场）。这样 WP3 底座是真的，goal-mode 可验收，且零风险打断知识库。

### 做（本轮，纯结构不烧额度）

1. **Canonical Normalizer 新写**（`backend/app/services/content/canonical_normalizer.py`）
   - 输入：parser raw dict（+ 三套 legacy IR 的读取适配，按 §19.2 迁移优先级）
   - 输出：`CanonicalContentIRV1`（扁平 nodes、parent_id+order、UUIDv7 新/UUIDv5 迁移、profile_data 按 6 种 profile 填必填键、fidelity 判定、diagnostics）
   - 复用 `ir_normalizer.py` 的 profile 塑形思路，但产出 canonical schema
   - 保真门禁：达不到阈值的格式 `fidelity.editable=false`（只读），不假绿

2. **canonical_parse 阶段双写**（改 `ingestion_stages.py::_stage_canonical_parse`）
   - 继续写旧 `{manifest, blocks}`（线上读者不动）
   - **额外**把 canonical IR 存到 Version 的 canonical 载荷（新增列 or extensions 键，见设计确认点）
   - `content_sha256`（RFC8785）+ `source_sha256`（真字节）落 Version 新字段（WP1 已建）

3. **Content Runtime read/hydrate 服务**（`backend/app/services/content/content_runtime_service.py`）
   - `read(package_id/version_id)` → 返回 CanonicalContentIRV1（有 canonical 载荷读它，无则现场 Normalize 旧 blocks 兜底）
   - `hydrate(version_id, page/slice/sheet/range)` → 大文件分片按需加载（profile_data 骨架 + Resource 分片）
   - 这是 Viewer/Editor/Knowledge 未来的统一读入口，本轮先建好、单测覆盖

4. **架构测试**（`backend/tests/test_wp3_content_runtime.py`）
   - Normalizer 往返：parser raw → canonical → 结构/必填键/fidelity 校验
   - 三套 legacy IR → canonical 迁移各一例
   - Content Runtime read/hydrate 正确性
   - **Gate3 扫描（记账用）**：列出仍直读物理/重解析的旁路，标注"待 WP7 翻转"，不误报为已完成

### 越过（本轮不做，标 deferred / WP7，留可重入入口）

- **翻转线上读者**（Knowledge `_flatten_cp_blocks`、Viewer 重解析、docs-open/text/csv editor 直读直写）→ WP7 影子读+一次切换，**须华哥在场**
- **Excel 迁回 Content Runtime**（8 张表→Spreadsheet Profile 双向边界）→ 大工程，本轮只在架构测试里记账，WP5/WP7 处理
- **图像 VLM 描述 / OCR-VLM / ASR**（canonical_parse 对图片仍 metadata_only+deferred）→ 额度恢复后 replay
- **Knowledge embedding 索引**（knowledge_register 恒 skipped）→ 沿用 WP2

### 需你确认的设计点（动手前）

**Knowledge 独立监听 `file.uploaded`（`router.py:1311`）要不要本轮下线？**
- 现状：它和 WP2 编排器**并存**，同一次上传两条摄取入口都触发（Knowledge 登记时又触发一次 content pipeline）。
- 影响：这是 §19.4「Content 和 Knowledge 不再分别直接监听 file.uploaded」明确要求下线的。但它连着你知识库的登记链路，下线要确认 Knowledge 登记改由编排器 knowledge_register 阶段驱动——而 knowledge_register 本轮是 deferred 的。
- **我的建议**：本轮**保留**这个监听（否则 deferred 期知识库彻底不登记新文件），只在文档里标记"WP7 额度恢复、knowledge_register 转正后同步下线"。避免为了架构纯洁性打断你正在用的知识库入库。

---

## 四、阶段二：实际结果（2026-07-17 完成）

本轮 WP3 安全增量全部落地并真实验证。华哥拍板：知识库独立监听不动，其他继续。

### 落地清单（5 个任务全绿）

**Task#1 — canonical_json 列 + ORM 映射补全**
- `content_runtime_schema.py::_COLUMN_ADDS` 加 `framework_content_package_versions.canonical_json TEXT`（启动 patcher 自动建，已实测入库）。Alembic `a1b2c3d4e5f6` import 同一份定义，两路径覆盖。
- `models/content.py`：补全 `ContentPackageVersion` 的 7 个 WP1 字段映射（parent_version_id/schema_version/profile/content_sha256/source_sha256/fidelity_level/retention_state）+ 新 canonical_json；补全 `ContentPackage` 的 4 字段（profile/schema_version/source_revision_id/active_ingestion_id）。此前 DB 有列、ORM 无字段。

**Task#2 — Canonical Normalizer 新写**
- `services/content/canonical_normalizer.py`：parser raw dict / 三套 legacy IR → `CanonicalContentIRV1`。
- 递归 blocks 拍平成扁平 nodes（parent_id+order）；新解析 UUIDv7 / 迁移确定性 UUIDv5；6 种 profile 填必填键骨架（validate_profile_data 返回空）；fidelity 保守（导入文件一律 editable=false）；deferred 记 diagnostics。
- 对外入口：`normalize_parser_output`（新解析）、`normalize_legacy_content_package_ir`（第2档）、`normalize_legacy_knowledge_ir`（第4档）。第3档平台 DocumentIR 无写路径、第5档 Excel legacy 本轮 deferred，不迁。

**Task#3 — canonical_parse 双写**
- `package_service.run_pipeline`：content_ir 组好后归一出 canonical，塞进 version 的 canonical_json/schema_version/profile/content_sha256/source_sha256/fidelity_level，回填 pkg.profile/schema_version。整段 try/except 包住，归一失败不打断旧写路径（安全增量）。
- `ingestion_stages._write_metadata_only_version`：图片 deferred 路径也补 canonical 骨架（nodes 空、fidelity=metadata_only、带 deferred diagnostic），不假绿。
- **真实验证**：docx 包 2214 跑 run_pipeline → version_no=2，旧 content_json(3507B) + 新 canonical_json(4362B) 双写，17 扁平 nodes，document profile 6 必填键全齐，content/source sha256 落库。

**Task#4 — Content Runtime read/hydrate 服务**
- `services/content/content_runtime_service.py`：`read/read_dict`（整份 canonical，有 canonical_json 读它、无则现场归一旧 content_json 兜底）、`hydrate`（anchor子树/page/slide/sheet 定位 + 分页）、`describe`（轻量元信息，不拉正文）。
- 只读服务，未翻转任何线上读者（Viewer/Knowledge 仍走旧路径）。save/edit/publish 属 WP5，不在此。
- **真实验证**：包 2214 → describe(17节点/has_canonical_payload=True)、read(全量17)、hydrate(分页5/17/truncated对)。

**Task#5 — 架构测试 + Gate3 记账**
- `tests/test_wp3_content_runtime.py`：19 passed。覆盖 parser 往返扁平树 / profile_data 完整 / fidelity 只读 / resource 锚定 / profile 推断 / legacy 确定性ID / knowledge 迁移 / Content Runtime 真实包读+hydrate / Gate3 记账。
- WP2 基线（test_ingestion_orchestrator.py）7 passed 不变，双写未打破摄取链路。

### Gate3 旁路记账（本轮不翻转，登记待 WP7 一次切换）

以下 7 类仍直读物理/重解析原件的旁路，本轮**故意保留**（翻转须华哥在场），测试里断言"清单未扩大"防回归：
1. doc-viewer → docx-parser 重解析物理 docx
2. ppt-viewer → pptx-parser 重解析物理 pptx
3. docs-open `_read_content` 直读/重解析物理
4. docs-open `_write_content` 写物理内容库不落 Package
5. text_editor_service 直读直写物理
6. csv_editor_service 直读直写物理
7. editors.py 四端点（上面两 service 的 HTTP 壳）

Excel 独立事实源（8 张 excel_* 表）与 Knowledge 重解析回退（document_service.py:1154）也登记在案，WP5/WP7 处理。

### 诚实的 deferred 项（§24，额度恢复后 replay）

- 图像 VLM 描述 / OCR-VLM / ASR：canonical_parse 对图片仍 metadata_only + deferred diagnostic，不假绿。
- Knowledge embedding 索引：knowledge_register 阶段沿用 WP2 恒 skipped(model_budget_deferred)。
- 知识库独立监听 file.uploaded（router.py:1311）：**华哥拍板保留**，不为架构纯洁打断在用的入库；WP7 knowledge_register 转正后同步下线。
- 线上读者翻转（Knowledge _flatten_cp_blocks / Viewer 重解析 / editor 直读写）：WP7 影子读 + 一次切换，须华哥在场。
- Excel 迁回 Spreadsheet Profile：WP5/WP7 大工程。

### 接口调用方式（Content Runtime，供后续 WP5/WP7 及 gpt5.6 目标模式接入）

```python
from app.services.content import content_runtime_service as rt
ir   = await rt.read(db, package_id=..., version_id=...)        # CanonicalContentIRV1
d    = await rt.read_dict(db, package_id=...)                    # dict（HTTP/capability 层用）
page = await rt.hydrate(db, package_id=..., page=1, limit=500)  # 分片：{profile,total,nodes,...}
info = await rt.describe(db, package_id=...)                    # 轻量元信息，不拉正文
```
