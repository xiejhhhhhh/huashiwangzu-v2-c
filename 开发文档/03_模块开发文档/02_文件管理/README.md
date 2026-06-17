# 文件管理

> ⚠️ **此模块尚未创建。**
> 以下内容是设计参考，描述目标状态。当前 `modules/` 仅保留 `_template/`，不包含 `file-manager` 目录。
> 实际实现时，请复制 `modules/_template/` 并按最新规范创建，本 README 在模块创建后需更新为真实状态。

## 模块目标

文件管理是一个独立的完整文件管理器窗口应用（类似于启动器中打开 Finder/Explorer 的大窗口），目标路径：

```text
modules/file-manager/
```

> ⚠️ **框架 vs 模块边界**：桌面壳自带的文件浏览（桌面文件列表、右键菜单、拖拽上传、双击打开）属于**框架**的"文件管理入口"层，定位为操作系统桌面文件层。本模块是**一个独立的文件管理器窗口应用**，通过调用框架公开的文件 API 工作，不应覆盖或重复桌面壳已有的文件入口功能。框架文件系统夯实完成前，本模块不应开始开发。

## 当前真实状态

- 当前还没有 `modules/file-manager/` 目录。
- 当前文件相关后端 router 在 `backend/app/routers/files.py`、`backend/app/routers/file_transfer.py`、`backend/app/routers/recycle.py`。
- 当前文件相关 service 在 `backend/app/services/file_service.py`、`backend/app/services/file_ops_service.py`、`backend/app/services/file_upload_service.py`、`backend/app/services/file_preview_service.py`。
- 当前文件 model 在 `backend/app/models/file.py`，回收站 model 在 `backend/app/models/recycle.py`。
- 当前文件管理桌面入口仍来自 `backend/app/seed_data/apps.json` 中 `desktop` 应用记录。
- 当前前端文件管理仍通过旧应用组件映射链路加载，不是 `modules/file-manager/manifest.json`。

## 当前定位

文件管理负责文件业务界面和用户操作流程。文件存储、权限校验、上传下载能力由 `backend/` 提供。

## 目标必需功能

- 文件和文件夹列表。
- 上传、下载、删除、恢复。
- 文件夹创建、重命名、移动。
- 文件预览入口。
- 权限不足、空目录、加载失败、重试状态。
- sandbox 独立调试。

## 目标接入规则

1. 文件业务流程归 `modules/file-manager/`。
2. 文件存储能力由 `backend/` 提供。
3. API 根路径、权限、资源路径通过模块 runtime 获取。
4. 测试上传文件和临时文件用完必须删除。
