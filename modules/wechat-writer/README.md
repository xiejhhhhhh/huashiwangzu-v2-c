# 公众号写作助手（wechat-writer）

## 业务目标

解决华哥写公众号文章「憋选题、搭框架、成文」耗时过长的痛点。订阅号「华世王镞问题肌修护专家」，每篇要保证专业性和品牌调性（俏小喵）。本模块把「憋一篇文章」从几小时压到几十分钟——AI 出选题/大纲/初稿，同事改定即可。

## 能力清单

### 跨模块能力（通过 `register_capability` 注册）

| 能力 | 说明 | 参数 |
|------|------|------|
| `wechat-writer:generate_topics` | 根据创作方向生成公众号选题建议 | `direction` (string) |
| `wechat-writer:generate_outline` | 根据选题生成文章大纲 | `topic`, `direction` |
| `wechat-writer:generate_article` | 根据大纲生成完整初稿 | `topic`, `outline`, `direction` |
| `wechat-writer:validate_content` | 校验成分/功效内容专业性（接知识库） | `content` |

### HTTP API 端点（前缀 `/api/wechat-writer`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/topics` | 生成选题 |
| POST | `/outline` | 生成大纲 |
| POST | `/article` | 生成文章 |
| POST | `/validate` | 校验内容 |
| GET | `/drafts` | 列表草稿 |
| POST | `/drafts` | 创建草稿 |
| GET | `/drafts/{id}` | 获取草稿 |
| PUT | `/drafts/{id}` | 更新草稿 |
| DELETE | `/drafts/{id}` | 删除草稿 |
| GET | `/prompts` | 列表提示词 |
| POST | `/prompts` | 保存提示词 |
| DELETE | `/prompts/{id}` | 删除提示词 |

## 数据表

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `wechat_drafts` | 文章草稿 | `owner_id`, `title`, `outline`(JSON), `content`, `status`, `version` |
| `wechat_prompts` | 提示词模板 | `owner_id`, `key`, `content`, `category` (system/topic/outline/article/validation/custom) |

所有查询带 `owner_id` 隔离。

## 业务流程

1. **选题**：用户输入创作方向 → AI 生成 5 个选题建议 → 用户选定一个
2. **大纲**：选定选题 → AI 生成详细大纲（含成分标记） → 用户确认
3. **成文**：按大纲 → AI 生成 1500-2500 字初稿 → 用户编辑修改
4. **校验**：自动/手动触发成分功效校验 → 调用知识库搜索 + AI 科学审核
5. **保存**：草稿可随时保存，多版本管理

## 底座能力接入

| 底座 | 用法 |
|------|------|
| 模型网关 | `gateway.service.chat(messages, profile_key="deepseek-v4-flash")` |
| 知识库 | `call_capability("knowledge", "search", {query, top_k})` 校验成分功效 |
| 提示词存 DB | `wechat_prompts` 表动态加载，支持运行时编辑 |

## 目录结构

```text
modules/wechat-writer/
  manifest.json          — 模块注册信息
  frontend/
    index.vue            — 主入口
    generate-panel.vue   — 创作面板（选题→大纲→成文→校验）
    drafts-panel.vue     — 草稿列表
    prompts-panel.vue    — 提示词管理
  backend/
    router.py            — HTTP 端点 + 能力注册
    services.py          — 业务逻辑（生成/校验/CRUD）
    models.py            — SQLAlchemy ORM 模型
    init_db.py           — 建表 + 默认提示词种子
  runtime/
    index.ts             — 运行时中间层
  sandbox/               — 独立开发环境
```

## 配置

默认提示词（5条）在 `init_db.py` 的 `DEFAULT_PROMPTS` 中，启动时自动写入 `wechat_prompts` 表。用户可通过前端「提示词管理」页面实时编辑。

当前写作模型：`deepseek-v4-flash`（可通过 `WRITING_PROFILE` 在 `services.py` 中切换）。

## 验收命令

```bash
cd /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2
backend/.venv/bin/python -m ruff check modules/wechat-writer/backend/init_db.py modules/wechat-writer/backend/router.py modules/wechat-writer/backend/services.py modules/wechat-writer/sandbox/test_module.py
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modules/wechat-writer/sandbox/test_module.py
```

`sandbox/test_module.py` 不调用真实模型网关或数据库；它会在 running event loop 中真调用 `_run_startup_init()`，用假 `run_init()` 验证模块启动初始化不会再触发 `asyncio.run()` 的协程未 await 警告。
