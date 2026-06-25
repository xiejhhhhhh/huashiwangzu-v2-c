# 桌面交互统一收口与稳定性Bug修复

**Agent**: executor  
**时间**: 2026-06-25  
**关联 Commit**: （待提交）

## 做了什么

- 新建统一交互层 `frontend/src/shared/ui/interaction.ts`（confirmDialog/alertDialog/toast）
- 替换 agent/knowledge 模块的15处原生alert/confirm为统一ElMessage/ElMessageBox调用
- 新增ESLint no-alert规则（`eslint.config.mjs`）
- 修复窗口越界8px bug（硬编码48→CSS变量--taskbar-height）
- 3处CSS overlay替换为ElDialog（ApprovalPanel、knowledge/index、IM）
- session持久化吞错修复（静默catch→toast.warning）
- 右键菜单颜色对齐深色设计令牌

## 改了哪些

见`修改文件清单.md`，共新增2文件、修改10文件。

## 踩过的坑

1. 模块内路径用 `@/shared/ui/interaction` 需确保 vite alias `@/*`→`./src/*` 能正确解析（自 `frontend/` 基准）
2. ESLint v10 flat config 默认不处理 config 目录外文件，需移至项目根目录 + 使用 `.mjs` 扩展 + `--no-inline-config`

## 遗留问题

R1开窗路径一致性未改、第二批框架内ElMessage→toast未做（均按任务指示跳过）。
