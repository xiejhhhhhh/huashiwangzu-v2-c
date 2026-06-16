# 创建 modules 根目录和模块规范

## 当前发现

- 当前仓库还没有 `modules/` 目录。
- 模块规范已在文档中定义，但没有落地到代码结构。

## 目标

- 创建 `modules/`。
- 每个顶层模块使用 `modules/{module_name}/manifest.json` 作为唯一人工事实源。
- 每个模块必须包含 `sandbox/`。
- 每个模块通过 runtime 读取正式配置或 sandbox 配置。

## 验收

- 至少一个最小模块可以在 sandbox 独立运行。
- 至少一个最小模块可以被桌面壳通过 manifest 加载。

## 完成后归档

完成后把当前模块目录结构合并回本目录 `README.md`，再删除本文件。
