# 迁移为 file-manager 模块

# 文件管理模块迁移

## 当前发现

- 文件管理前端仍通过旧组件映射加载（`应用/desktop/入口.vue` → `@应用模块/文件管理/frontend/index.vue`）。
- 桌面应用清单 `backend/app/seed_data/apps.json` 中 `desktop` 应用的 `component_key` 仍是旧中文路径。
- 没有 `modules/file-manager/manifest.json`。
- 没有 `sandbox/`，无法独立测试文件管理流程。

## 目标

- 创建 `modules/file-manager/`。
- 建立 `manifest.json`、`runtime.config.json`、`runtime/`、`frontend/`、`backend/`、`sandbox/`、`tests/`。
- 文件管理先通过 sandbox 独立运行和验收，再接入桌面壳。

## 验收

- sandbox 中可以浏览文件、上传、下载、删除、恢复。
- 主桌面壳可以通过模块 manifest 打开文件管理。

## 完成后归档

完成后把当前文件管理模块结构合并回本目录 `README.md`，再删除本文件。
