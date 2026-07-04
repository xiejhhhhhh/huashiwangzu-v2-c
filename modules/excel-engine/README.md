# excel-engine — spreadsheet editor

excel-engine 是桌面壳里的表格编辑器，负责打开、编辑、保存、导出 XLSX/CSV。它也是文件引擎样板：解析借内核，状态和 UI 自研，跨模块能力只暴露必要的 parse。

## 功能

| 功能 | 说明 |
|---|---|
| 打开文件 | 解析 XLSX/CSV，写入 `excel_*` 状态表 |
| 编辑 | 单元格值、样式、合并、行列、剪贴板 |
| 历史 | 每次写操作前记录快照，支持撤销和恢复 |
| 导出 | 状态重新生成 XLSX/CSV |
| Agent 能力 | `excel-engine:parse` 供知识库和 Agent 读取表格结构 |

## 如何调用

HTTP 前缀：`/api/excel-engine`

| 端点 | 方法 | 用途 |
|---|---|---|
| `/health` | GET | 健康检查 |
| `/parse` | POST | 解析 xlsx/csv 文件 |
| `/open` | POST | 打开并入库 |
| `/dispatch` | POST | 兼容旧 API 的统一调度 |
| `/edit` | POST | 编辑单元格 |
| `/style` | POST | 修改样式 |
| `/clipboard` | POST | 复制/粘贴 |
| `/table` | POST | 行列和合并操作 |
| `/state` | POST | 读取状态、撤销、恢复、历史 |
| `/export` | POST | 导出 |
| `/download/{state_key}` | GET | 下载导出文件 |

跨模块调用：

```python
call_capability("excel-engine", "parse", {"file_id": 123}, caller="user:1")
```

## 目录

| 路径 | 说明 |
|---|---|
| `frontend/` | Vue 网格、工具栏、右键菜单、历史面板 |
| `backend/router.py` | HTTP API 和能力注册 |
| `backend/models.py` | `excel_*` SQLAlchemy 模型 |
| `backend/engine/` | XLSX/CSV 解析和生成 |
| `backend/state/` | 状态持久化、快照、撤销恢复 |
| `backend/table/` | 编辑、样式、剪贴板、行列业务 |
| `backend/tool/` | A1 地址、公式、配置 |

## 数据表

`excel_workbooks`、`excel_sheets`、`excel_cells`、`excel_col_widths`、`excel_row_heights`、`excel_history`、`excel_redo_stack`、`excel_versions`。

### 2026-07-03 反向审计结论

本轮从数据库空表反查 `create_workbook/import_file_to_workbook/update_range/append_rows/undo/redo/list_history/list_versions/restore_version/compile_xlsx` 链路，修复点如下：

- `excel_col_widths`、`excel_row_heights`：导入和写回链路已统一经完整状态持久化，写入 cells/styles/merges 的同时写入宽高和 sheet 尺寸。
- `excel_redo_stack`：undo 会保存当前状态到 redo，redo 后清栈；新增写操作成功后清 redo，避免旧 redo 误恢复。
- `excel_versions`：`export.save_version` 已落库版本快照，`list_versions/restore_version` 覆盖 file_id + owner 过滤，恢复时同步 cells/styles/merges/宽高/尺寸。
- 快照从浅引用改为深拷贝，避免“操作前快照”被后续原地修改污染，导致 undo/redo 看似成功但状态没变。
- `append_rows` 修正列偏移，追加行从 A 列开始；`create_workbook` 现在把传入 name 写入数据库。
- `table.delete_shift_right/delete_shift_up/insert_shift_right/insert_shift_down` 从空实现改为真实移位，避免 `code:0` 假成功。
- `compile_xlsx` 成功返回临时文件信息；缺失 workbook 返回结构化业务失败，不产生文件记录。

验证时会创建临时 workbook/file/version/compile 文件，测试结束必须删除。当前 sandbox 测试已覆盖导入带宽高 XLSX、update/append、undo/redo、history、save/list/restore version、compile_xlsx，并清理测试数据；因此生产库中这些可选表为空不再单独视为链路不可用，需要结合流程探针判断。

## 边界

- 表名前缀固定为 `excel_*`。
- 前端 UI 自研，不整体引入第三方表格编辑器。
- 文件读取和导出必须经框架文件权限/文件服务。
- 模块对外只声明 `parse` 能力；编辑 API 是模块自身 HTTP 表面。

## 验证

```bash
cd modules/excel-engine/sandbox && ../../../backend/.venv/bin/python test_module.py
cd frontend && npm run build
```

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `excel-engine`, window `normal`, formats: xlsx, xls, csv. |
| Backend capability | PASS | 13 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | SKIP | Module does not directly consume framework file_id content. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/excel-engine/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `excel-engine:<action>` and release smoke/capability drift gates. |
| Known debt | PASS | None tracked in this matrix. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/excel-engine/sandbox/test_module.py
cd modules/excel-engine/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module excel-engine --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
