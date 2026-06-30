---
name: "新建 github-search 模块：GitHub 搜索能力"
type: task
tags: ["github-search", "module", "capability"]
created: 2026-06-30
agent: opencode
---

新增 modules/github-search/ 模块，为 Agent 提供 GitHub 搜索能力，注册两个跨模块能力：
- github-search:search — 搜索 GitHub 开源项目，按活跃度和质量排序。自动过滤归档/不活跃项目，返回含 README 预览。
- github-search:search_code — 在 GitHub 上搜索代码片段，返回仓库/文件路径/代码片段预览。

实现方案：底层用 `gh` CLI（已安装、已登录），封装为异步调用 + 10分钟缓存 + 活跃度过滤（2年内有更新）。

模块结构：
- manifest.json — 声明后端路由和 public_actions
- backend/router.py — 注册 capabilities + HTTP 端点
- backend/services/github_client.py — gh CLI 封装（搜索仓库/搜索代码/获取 README）

模块边界校验：全部改动在 modules/github-search/ 内，未改动框架或其他模块。
