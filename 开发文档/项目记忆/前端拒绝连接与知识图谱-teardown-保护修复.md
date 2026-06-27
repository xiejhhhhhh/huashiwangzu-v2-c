---
name: "前端拒绝连接与知识图谱 teardown 保护修复"
type: task
tags: ["frontend", "knowledge", "backend", "gateway", "dev_toolkit", "stability", "sanity_check"]
created: 2026-06-27
agent: zcode
---

本次处理了前端拒绝连接与知识图谱 teardown 报错排查：修复 modules/knowledge/frontend/graph3d/labels.ts 的 dispose 链路，改为幂等清理并对 CSS2DRenderer.dispose 做运行时守卫，避免卸载时报错把错误扩散；修复 backend/app/gateway/config.py / modules/agent/backend/engine/budget_allocator.py 的 MODEL_PROFILES 导入链，消除后端模块导入失败；在 dev_toolkit/server.py 增加 sanity_check 规范检查工具，用于检查 5173 监听、后端 health、模块导入失败与知识图谱卸载风险。后续可结合该检查继续收敛前端热更新/运行时异常。
