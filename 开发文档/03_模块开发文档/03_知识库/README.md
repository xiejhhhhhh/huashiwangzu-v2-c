# 知识库

> ⚠️ **此模块尚未创建。**
> 以下内容是设计参考，描述目标状态。当前 `modules/` 仅保留 `_template/`，不包含 `knowledge` 目录。
> 实际实现时，请复制 `modules/_template/` 并按最新规范创建，本 README 在模块创建后需更新为真实状态。

## 模块目标

知识库是桌面里的资料编目、抽取、检索、问答、图谱和质量评估模块，目标路径：

```text
modules/knowledge/
```

## 当前真实状态

- 当前还没有 `modules/knowledge/` 目录，模块尚未创建。
- 知识库后端代码已从平台层全部清理：
  - `backend/app/routers/knowledge_*.py`（16 个 router）已删除。
  - `backend/app/models/knowledge/`（16 个模型）已删除。
  - `backend/app/schemas/knowledge.py` 和 `backend/app/schemas/knowledge_ext.py` 已删除。
  - `backend/app/services/knowledge/`（含 aggregation、candidate、dictionary、evaluation、extract、fusion、graph、label、llm、retrieval、vision 等子目录）已删除。
- 知识库不再作为平台种子应用写入 `backend/app/seed_data/apps.json`；创建 `modules/knowledge/manifest.json` 前，桌面壳不注册知识库入口。
- 知识库业务待按模块规范从 V1 代码库重建。

## 当前定位

知识库业务复杂，必须拆成子模块开发。平台提供数据库、队列、模型、文件、权限能力；知识库业务规则、页面、流程和子模块归 `modules/knowledge/`。

## 目标子模块结构

```text
modules/knowledge/submodules/catalog/
modules/knowledge/submodules/ingestion/
modules/knowledge/submodules/retrieval/
modules/knowledge/submodules/qa/
modules/knowledge/submodules/graph/
modules/knowledge/submodules/evaluation/
```

## 目标必需功能

- 资料编目。
- 文件抽取。
- 切片和向量化。
- 检索和 rerank。
- 问答和证据引用。
- 图谱和实体关系。
- 标签、词典、治理。
- 质量评估。
- sandbox 独立调试。

## 目标接入规则

1. 知识库可以调用 `backend/` 的数据库、队列、模型、文件、权限能力。
2. 子模块由知识库父模块扫描和管理，不进入桌面壳全局扫描。
3. 测试文档、测试切片、测试向量、测试问答记录用完必须清理。
4. 未通过 sandbox 自测前，不接入主桌面壳。

## 待办

- 从 V1 代码库提取知识库业务代码，按 `modules/_template/` 规范创建 `modules/knowledge/`。
- 建立 `manifest.json`、`frontend/`、`backend/`、`sandbox/`、`submodules/`。
- 按目标子模块结构拆分。
- sandbox 自测通过后接入主桌面壳。
