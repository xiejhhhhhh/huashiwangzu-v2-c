---
name: "前端 Runtime 合约审计与 openApp 契约补齐"
type: "task"
tags: [frontend, runtime, contract-drift, openApp, type-safety]
agent: "opencode-r5-frontend-runtime"
created: "2026-07-03T05:13:48.670001+00:00"
---

## 任务摘要
深审前端/runtime 合约问题，发现并修复 runtime SDK `openApp` 跨模块契约漂移。

## 审计覆盖范围
- frontend/src/shared/api/ (统一响应解包、类型定义、API helper)
- frontend/src/desktop/app-registry/ (模块加载/registry)
- modules/*/runtime/index.ts (29 份 runtime SDK 副本)
- frontend/src/types/global.d.ts (window 类型声明)
- frontend/src/main.ts (框架注入)

## 发现的问题

### 已修复：openApp 跨模块契约漂移 (P2)
- 发现: knowledge/runtime 有 `openApp()` 方法 (通过 `__HSWZ_WINDOW_MANAGER__` 打开其他模块)，但 agent/memory/office-gen/terminal-tools/doc-viewer 等有真实前端的模块 runtime 缺少该方法。
- 修复: 在 5 个 module runtime 的 `modules` 命名空间中添加 `openApp`。前置条件: 框架已在 `main.ts:16` 注入 `window.__HSWZ_WINDOW_MANAGER__`；`global.d.ts` 已声明 `Window.platform.modules.openApp`。
- 验证: `vue-tsc -b --noEmit` 通过 (exit 0, 无类型错误)

### 正式发现 (未修，需要主线程决策)
1. **`__MODULE_OPEN_FILE_PAYLOAD__` 残余 (P3, 29/29 运行时有)** — `files.getOpenPayload()` 在所有运行时读 `window.__MODULE_OPEN_FILE_PAYLOAD__`。`global.d.ts` 已清 (治理6)，但运行时仍引用。现代代码走 `app-opener.ts` 直接传递 payload。需等运行时集中化时统一清理。
2. **Runtime 29 副本维护债 (P4)** — 所有 29 模块的 runtime/index.ts 是近一模一样的副本。`scripts/check-runtime-drift.js` 跟踪差异。已确认 12 exact + 12 known variants + 4 unexpected drift。
3. **6 模板存根组件 (P4)** — docx-parser/image-vision/pdf-parser/pptx-parser/text-parser 仍用 `_template` 存根 UI。各 parser/vision 模块要有自己的前端时需自行替换。
4. **Shared API login 特殊路径 (P3)** — 拦截器 login 路径 (line 60-65) 在 `access_token` 出现时返回非标准 `{user, access_token, token_type}`。工作正常但需留意它不是标准 unwrap 路径。
5. **excel-engine/runtime 已恢复为精确模板副本** — 不会增加 drift

## 验证
- `vue-tsc -b --noEmit` → exit 0, 类型检查通过
- `node scripts/check-runtime-drift.js` → 12 exact + 12 known variants + 4 unexpected (pre-existing)
- `git diff -- modules/*/runtime/index.ts` → 5 文件各 +9 行 openApp 函数

## 残留风险
- 未修改的 modules (im, wechat-writer, douyin-delivery 等) 仍缺 `openApp`。如有跨模块打开窗口需求，需逐模块添加。
- 模板运行时本身也不含 `openApp` — 建议考虑是否将 `openApp` 提升到模板中作为标准能力。
