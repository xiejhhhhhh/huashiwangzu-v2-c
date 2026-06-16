# 迁移为 knowledge 模块

# 知识库模块迁移

## 当前发现

- 知识库后端代码仍在 `backend/app/services/knowledge/`，不是模块目录。
- 知识库 router 多达 16 个文件，直接在 `backend/app/main.py` 注册。
- 前端仍通过旧组件映射加载知识库。
- 没有 `modules/knowledge/manifest.json`。
- 没有 `sandbox/`，无法独立测试知识库编目、抽取、检索流程。

## 目标

- 创建 `modules/knowledge/`。
- 建立 `manifest.json`、`runtime.config.json`、`runtime/`、`frontend/`、`backend/`、`sandbox/`、`submodules/`、`tests/`。
- 知识库先通过 sandbox 独立运行和验收，再接入桌面壳。

## 验收

- sandbox 中可以完成编目、抽取、检索、问答的最小闭环。
- 主桌面壳可以通过模块 manifest 打开知识库。

## 完成后归档

完成后把当前知识库模块结构合并回本目录 `README.md`，再删除本文件。
