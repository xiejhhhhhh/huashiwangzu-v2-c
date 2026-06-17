# 华世王镞 V2 开发文档

## 项目目标

华世王镞 V2 的目标是一个由 Python FastAPI 后端、Vue 3 桌面壳和可热插拔业务模块组成的新架构项目。

目标目录职责：

```text
frontend/   桌面壳前端，负责登录、桌面、窗口、任务栏、启动器、共享 UI 和模块加载
backend/    平台服务层，负责 API、数据库、权限、任务、队列、模型网关、文件存储和系统能力
modules/    桌面软件和业务模块，每个模块先在自己的 sandbox 中独立开发和验收
```

`README.md` 只描述项目目标和当前已经真实存在的内容。未完成、待迁移、待修复的内容放到对应目录的 `{序号}_{待执行任务名字}.md`，完成后再精炼合并回对应 `README.md`。

## 当前真实状态

- 当前仓库已经有 `frontend/`，使用 Vue 3、Vite、Pinia、Element Plus。
- 当前仓库已经有 `backend/`，使用 Python FastAPI、SQLAlchemy、Alembic。
- 当前仓库已经有 `modules/` 目录，含 `modules/_template/`（标准化 sandbox 模板和 runtime 中间层）和 `modules/ai-assistant/`（前端占位入口 + sandbox）。
- 当前桌面应用清单仍在 `backend/app/seed_data/apps.json`。
- 当前后端入口是 `backend/app/main.py`，已注册 21 个平台 router（认证、桌面、文件、回收站、用户、角色、系统、日志、仪表盘、设置、备份、任务、Office、通知、反馈、应用管理、菜单等）。模块 router 由 manifest 动态挂载。
- 当前前端入口是 `frontend/src/main.ts`。
- 当前桌面壳代码主要在 `frontend/src/desktop/`。
- 当前平台共享代码主要在 `frontend/src/platform/` 和 `frontend/src/shared/`。
- 当前模型网关在 `backend/app/gateway/`（框架能力），支持 DeepSeek/OpenCode/OpenAI 兼容协议，含指数退避重试。
- 平台层已无模块业务代码，AI 助手和知识库代码已清理，待按模块规范从 V1 重建。

## 文档结构

```text
开发文档/
  README.md
  01_框架开发文档/
    README.md
    ...
  02_底层开发文档/
    README.md
    ...
  03_模块开发文档/
    README.md
    ...
    01_AI助手/
      README.md
      ...
    02_文件管理/
      README.md
      ...
    03_知识库/
      README.md
      ...
```

## 阅读顺序

1. 接手项目时，先读本文件。
2. 改框架读 `01_框架开发文档/README.md`。
3. 改底层平台读 `02_底层开发文档/README.md`。
4. 改模块读 `03_模块开发文档/README.md` 和对应模块的 `README.md`。
5. 看待执行任务时，读对应目录的 `{序号}_{待执行任务名字}.md`。
6. Agent 行为规则在根目录 `AGENTS.md`。

## 文档规则

1. V2 是全新架构，不在 Laravel/PHP 旧目录上继续缝补。
2. 除 `开发文档/` 外，所有目录和文件名必须英文。
3. `开发文档/` 是用户阅读区，目录、文件名、正文可以中文。
4. Markdown 文档不限制字数和行数。
5. README 不记录历史流水，不写“什么时候改了什么”。
6. README 写当前目标、当前真实状态、当前使用方式和当前规则。
7. 待做事项写入同目录 `{序号}_{待执行任务名字}.md`。
8. 任务完成后，把仍然有效的内容合并回对应 README，再删除或清空已完成任务条目。

## 文档归档规则

`README.md` 是长期文档，也是事实源。其他 Markdown 只允许作为临时任务文档存在。

1. 可以为任何任务临时创建方案、审计、计划、验收记录。
2. 任务完成后，必须把仍然有效的内容精炼合并回对应 `README.md`。
3. 合并后删除临时文档。
4. `README.md` 不记录“什么时候增加了什么”，只描述当前实际功能、使用方式、开发规则和验收规则。
5. 如果一个目录里出现多个长期 Markdown，说明文档已经失控，需要合并回 `README.md`。
