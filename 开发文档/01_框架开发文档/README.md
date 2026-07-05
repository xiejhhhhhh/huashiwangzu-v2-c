# 框架开发文档

框架负责桌面壳和平台加载能力，不承载具体业务模块。

```text
frontend/   桌面壳前端（Vue 3 + Vite）
backend/    平台服务层（FastAPI + SQLAlchemy）
modules/    被框架加载的业务模块
```

## 本地运行入口与端口

| 跑什么 | 地址/端口 | 用途 |
|---|---|---|
| 主框架前端 | `http://127.0.0.1:5173` | 桌面壳加载所有模块 |
| 主框架后端 | `127.0.0.1:33000` | 平台服务层，watchdog 守护 |
| 模块 sandbox | 模块自定端口 | 单模块开发态调试 |

主框架登录态由框架统一接管；模块 sandbox 是独立开发世界，不能当作主框架验收结果。

## 桌面壳能力

| 能力 | 位置 |
|---|---|
| 窗口管理 | `frontend/src/desktop/window-manager/` |
| 任务栏、启动器、托盘、右侧栏 | `frontend/src/desktop/` |
| 应用注册表和组件映射 | `frontend/src/desktop/app-registry/` |
| 桌面文件、右键、拖拽上传 | `frontend/src/desktop/shell/` |
| 模块 manifest 扫描 | `frontend/scripts/scan-modules.js` |

## 文件系统底座

| 能力 | 后端 API |
|---|---|
| 文件 CRUD | `/api/files/*` |
| 上传/下载/预览 | `/api/files/upload`, `/api/files/download/{id}`, `/api/files/preview/{id}` |
| 回收站 | `/api/recycle/*` |
| 分享 | `/api/files/share`, `/api/files/share/*` |
| 批量操作 | `/api/files/batch-*` |

规则：所有文件查询按 owner/share 隔离；重名返回 409；读文件内容前必须先校验访问权限。

## Runtime SDK

模块通过 runtime `platform` 对象使用框架能力：

```text
auth, files, office, gateway, tasks, notifications, logs, settings, modules
```

跨模块前端调用使用 `platform.modules.call/capabilities`。

## 模块可用框架公开能力

| 类型 | 允许模块使用 | 规则 |
|---|---|---|
| DB 会话 | `app.database.get_db`, `AsyncSessionLocal` | 只作为连接/事务入口；模块只读写自身表 |
| 鉴权 | `require_permission`, `User` | router 依赖注入；不得绕过 owner 隔离 |
| 响应和异常 | `ApiResponse`, framework exceptions | 统一 envelope；业务错误抛异常 |
| 能力注册 | `register_capability`, `call_capability` | 后端跨模块唯一通路 |
| 任务队列 | `register_task_handler`, `SystemTaskQueue` | payload 存逻辑 ID；状态持久化 |
| 模型网关 | gateway/model services | 模块不得散落 provider/key |
| 文件桥接 | `check_file_access`, file upload/preview services | 读盘前必须鉴权 |
| ORM 基类 | `Base`, `TimestampMixin` | 模块表仍归模块自己 |
| 前端共享 | `frontend/src/shared/` | 不得 import desktop shell internals |

未列入的 `backend/app/*` 和 `frontend/src/*` 内部实现默认不可作为模块依赖。多个模块都需要的新公共能力必须先作为框架任务定义契约。

## Framework Decisions

| ID | Decision |
|---|---|
| C1 | 框架接口稳定，不随模块业务膨胀。 |
| C2 | 模块通过 manifest/runtime/API 接入，禁止手写框架 import 列表。 |
| C3 | 跨模块必须走框架统一通路。 |
| C4 | API 使用统一 envelope，禁止假成功。 |
| C5 | owner/share 文件隔离是强契约。 |
| C6 | 模块图标、组件、业务类型不写入框架目录。 |
| C7 | terminal-tools 本地执行但锁工作区；成果显式 publish 才进桌面。 |

## Verification

```bash
cd frontend && npm run build
python3.14 dev_toolkit/release_gate.py --preflight --skip-ui
```
