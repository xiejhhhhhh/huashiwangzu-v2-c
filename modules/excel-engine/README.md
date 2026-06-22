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

## 边界

- 表名前缀固定为 `excel_*`。
- 前端 UI 自研，不整体引入第三方表格编辑器。
- 文件读取和导出必须经框架文件权限/文件服务。
- 模块对外只声明 `parse` 能力；编辑 API 是模块自身 HTTP 表面。

## 验证

```bash
cd modules/excel-engine/sandbox && python3 test_module.py
cd frontend && npm run build
```
