---
name: "low-data-module-flow节点2-douyin自然空与excel布局入库补修"
type: "task"
tags: [low-data, douyin-delivery, excel-engine, db-reverse-audit, 20260703]
agent: "low-data-flow-review-r3"
created: "2026-07-02T16:45:15.972145+00:00"
---

节点2：完成 douyin/excel 空表抽查与 excel 小修。

证据：db_reverse_audit 显示 douyin_products/douyin_campaigns/douyin_ad_copies 为 0 行但模块 router/CRUD/manifest/capability 均存在；活系统 GET /api/douyin-delivery/products、campaigns、ad-copies 返回 200 空数组，prompts 有 7 条种子，scripts 表 1 行属于 owner_id=1，admin 列表为空是 owner 隔离结果。结论：三张 douyin 空业务表更像自然未使用，不是创建入口断链。

另发现 douyin 前端 api.ts 的 update/delete 用 apiPost 调 PUT/DELETE 后端路径，活系统 POST /products/{id}/campaigns/{id}/ad-copies/{id} 均 405；该文件已在 frontend-runtime-review-r3/cleanup 相关并行改动范围，未碰，只报告。

excel：db_reverse_audit 显示 excel_col_widths/excel_row_heights/excel_redo_stack 为空；活系统有 20 workbooks、33 sheets、562 cells、8 history，但所有含 cell/history 的 workbook 关联 col/row 布局计数仍为 0。CodeGraph 证实 parser 会解析 col_widths/row_heights，/open 与 import_file_to_workbook 只 sync_cells，导致导入布局不入库。已在 modules/excel-engine/backend/router.py 增加 _sync_sheet_data，并让 open/import 同步 cells/styles/merges/col_widths/row_heights。

验证：ruff check modules/excel-engine/backend/router.py 通过；run_test modules/excel-engine/sandbox/test_module.py 11 passed；临时 DB 验证 low_data_layout_probe_* 创建后调用 _sync_sheet_data，读回 2 col widths + 1 row height，并已清理（cleanup check 0）。未重启活栈，避免影响并行代理；新代码需后端重启后进入 live stack。
