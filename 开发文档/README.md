# 华世王镞 V2 开发文档

## 项目目标

Python FastAPI 后端 + Vue 3 桌面壳 + 可热插拔业务模块。

```text
frontend/   桌面壳前端（登录、桌面、窗口、任务栏、启动器、模块加载）
backend/    平台服务层（API、数据库、权限、任务、模型网关、文件存储）
modules/    业务模块（sandbox 独立开发 → manifest 接入）
```

## 当前状态

| 分类 | 现状 |
|------|------|
| 前端 | Vue 3 + Vite + Pinia + Element Plus，`vue-tsc -b` 0 错误 |
| 后端 | FastAPI + SQLAlchemy async + Alembic，22 个平台 router，42+16 个测试通过 |
| 数据库 | 21 张 `framework_*` 表，干净基线，历史污染已清除 |
| 文件系统 | **底座已夯实**：CRUD、上传下载、去重、分享、回收站、批量、面包屑、审计日志 |
| 模块 | `modules/_template/` 含 sandbox + runtime SDK，无已接入模块 |
| 文档 | `01_框架开发文档/` `02_底层开发文档/` `03_模块开发文档/` |

## 阅读顺序

1. 本文件 → 了解全貌
2. `01_框架开发文档/README.md` → 改框架
3. `02_底层开发文档/README.md` → 改底层平台
4. `03_模块开发文档/README.md` → 改模块
5. `AGENTS.md` → Agent 行为规则

## 文档规则

1. 除 `开发文档/` 外，所有目录和文件名必须英文
2. `开发文档/` 内目录、文件名、正文可以中文
3. Markdown 文档不限制长度
4. README 写当前目标、当前真实状态、当前使用方式和当前规则，不写历史流水
5. 待做事项写入 `{序号}_{待执行任务名字}.md`，完成后合并回 README 并删除临时文档
