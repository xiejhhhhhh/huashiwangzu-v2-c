---
name: "前端UI集测+xlsx解析修复"
type: task
tags: ["ui", "excel-engine", "knowledge", "test"]
created: 2026-06-23
agent: opencode
---

UI端到端真测(Playwright 36测全过):27应用无白窗、6类文件双击开对查看器。修复:xlsx解析3bug(workbook_parser import ET/rid_map双路径前缀/router未检查parse返回码,真测2-sheet xlsx parse已正常)、E4 storage_path从_FILE_FIELDS移除、knowledge前端liveProgressMap空时回退文档status避免重复触发分析、测试CSS选择器.window-action-close。Playwright specs在frontend/tests/可复跑。
