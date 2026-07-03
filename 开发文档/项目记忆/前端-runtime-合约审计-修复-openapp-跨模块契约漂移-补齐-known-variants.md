---
name: "前端 Runtime 合约审计：修复 openApp 跨模块契约漂移 + 补齐 KNOWN_VARIANTS"
type: "task"
tags: [frontend, runtime, contract-drift, openApp, KNOWN_VARIANTS, type-safety]
agent: "opencode-r5-frontend-runtime"
created: "2026-07-03T05:14:41.971073+00:00"
---

# 改了什么

1. **修复 openApp 跨模块契约漂移 (5 模块 runtime)**
   - 发现: 只有 knowledge/runtime/index.ts 有 `openApp()` 方法，其他有前端界面的模块 (agent, memory, office-gen, terminal-tools, doc-viewer) 均缺失
   - 修复: 在 5 个模块的 runtime `modules` 命名空间添加 openApp (依赖框架在 main.ts:16 注入的 `__HSWZ_WINDOW_MANAGER__`)
   - 模板 `_template/runtime/index.ts` 维持不变 (按设计决策，新模块需要时自行添加)

2. **补齐 KNOWN_VARIANTS**
   - `office-gen` 有 `content` 命名空间 + `apiPut` (content pipeline 操作)，是预存 drift，加入 KNOWN_VARIANTS

# 验证了什么
- `vue-tsc -b --noEmit` → exit 0 (类型检查通过)
- `node scripts/check-runtime-drift.js` → 12 exact / 13 known variants / 3 unexpected (pre-existing, 未动)
- `excel-engine` 已通过 `git checkout` 恢复为精确模板副本，未新增 drift

# 审计发现 (未修)
1. `__MODULE_OPEN_FILE_PAYLOAD__` 残余：全部 29 运行时的 `files.getOpenPayload()` 仍读此 window 属性。global.d.ts 已清 (治理6)，但运行时引用仍存。等运行时集中化时统一清理。
2. 3 预存 drift: douyin-delivery, media-asr, wechat-writer — 需主线程决断是否为有效 variant。
3. `openApp` 尚未加入模板基线，新模块需自行添加。
4. Shared API login 拦截器路径 (line 60-65) 在 access_token 出现时返回非标准 `{user, access_token, token_type}`，工作正常但非标准 unwrap 路径。

# 边界合规
- 改动范围: 仅 modules/*/runtime/index.ts (5 文件) + frontend/scripts/check-runtime-drift.js (1 文件)
- 未改 backend/app、frontend/src 框架代码
