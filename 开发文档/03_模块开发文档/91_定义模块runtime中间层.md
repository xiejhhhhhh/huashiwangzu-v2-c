# 定义模块 runtime 中间层

## 目标

- 模块正式代码不直接判断自己运行在 sandbox 还是主框架。
- 模块通过 `runtime/` 获取 API 根路径、资源路径、权限、平台能力、模块配置。
- 切换正式配置和 sandbox 配置时，只改 runtime 配置，不改业务组件。

## 验收

- 同一模块前端代码能在 sandbox 和主框架中运行。
- 路径、API、权限由 runtime 提供。

## 完成后归档

完成后把当前 runtime 使用方式合并回本目录 `README.md`，再删除本文件。
