# 文件管理

## 模块目标

文件管理是桌面里的文件浏览、上传、下载、删除和预览入口模块，目标路径：

```text
modules/file-manager/
```

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
