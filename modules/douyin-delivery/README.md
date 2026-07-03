# 抖音投放助手 (douyin-delivery)

## 是什么

抖音投放内容的 AI 加速器。为俏小喵品牌解决抖音投放太花时间的问题，把投放相关的内容生产用 AI 加速。

三个方向一次覆盖：
- **投放内容创意**：口播脚本生成（钩子/痛点/卖点/信任/引导）
- **投放素材文案**：广告标题/描述/定向建议（按渠道风格）
- **投放计划管理**：计划 CRUD + ROI 分析

## 能力清单

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/douyin-delivery/scripts/generate` | 生成口播脚本 |
| POST | `/api/douyin-delivery/ad-copies/generate` | 生成广告文案 |
| POST | `/api/douyin-delivery/validate` | 知识库校验成分/功效 |
| POST | `/api/douyin-delivery/campaigns/{id}/analyze` | ROI 分析 |
| GET/POST/PUT/DELETE | `/api/douyin-delivery/products` | 产品 CRUD |
| GET/POST/PUT/DELETE | `/api/douyin-delivery/scripts` | 脚本 CRUD |
| GET/POST/PUT/DELETE | `/api/douyin-delivery/ad-copies` | 文案 CRUD |
| GET/POST/PUT/DELETE | `/api/douyin-delivery/campaigns` | 计划 CRUD |
| GET/POST/PUT/DELETE | `/api/douyin-delivery/accounts` | 投放账号 CRUD |
| GET/POST/PUT/DELETE | `/api/douyin-delivery/materials` | 投放素材 CRUD |
| GET/POST/PUT/DELETE | `/api/douyin-delivery/delivery-tasks` | 投递任务 CRUD |
| POST | `/api/douyin-delivery/delivery-tasks/{id}/status` | 更新投递任务状态 |
| POST | `/api/douyin-delivery/cleanup` | 按 marker 清理当前用户测试数据 |
| GET/POST/DELETE | `/api/douyin-delivery/prompts` | 提示词管理 |

### 跨模块能力

| 能力 | 说明 | 权限 |
|------|------|------|
| `douyin-delivery:generate_script` | 生成口播脚本 | editor |
| `douyin-delivery:generate_ad_copy` | 生成广告文案 | editor |
| `douyin-delivery:validate_content` | 知识库校验 | editor |
| `douyin-delivery:create_delivery_task` | 创建投递任务 | editor |
| `douyin-delivery:mark_task_failed` | 标记投递失败并记录原因 | editor |
| `douyin-delivery:cleanup_marked_data` | 按 marker 清理当前用户测试数据 | editor |

### 投放渠道

| 渠道 key | 说明 |
|----------|------|
| `local_push` | 本地推（门店引流，强调到店体验） |
| `ocean_engine` | 巨量引擎（精准投放，数据化效果） |
| `qianchuan` | 千川（直播/短视频带货，限时优惠） |

## 数据表

所有表以 `douyin_` 为前缀，`owner_id` 隔离。

| 表名 | 说明 | 核心字段 |
|------|------|----------|
| `douyin_products` | 产品/卖点库 | name, selling_points(JSON), ingredients(JSON), target_audience |
| `douyin_scripts` | 口播脚本 | channel, hook, pain_point, full_script, hashtags(JSON), suggested_titles(JSON) |
| `douyin_ad_copies` | 广告文案 | channel, ad_type, headline, description, call_to_action, target_audience_desc |
| `douyin_campaigns` | 投放计划 | channel, budget, target_audience(JSON), performance_metrics(JSON) |
| `douyin_accounts` | 投放账号 | channel, account_name, external_account_id, status |
| `douyin_materials` | 投放素材 | material_type, channel, source_file_id, content_url, content_text, status |
| `douyin_delivery_tasks` | 投递任务 | task_type, target_type, target_id, status, payload(JSON), result_payload(JSON), error_message |
| `douyin_prompts` | 提示词模板 | key, content, category, channel |

## 状态与失败语义

投递相关状态是后端契约，不允许写入任意字符串：

| 对象 | 状态 |
|------|------|
| 脚本/文案/素材 | `draft` / `ready` / `published` / `archived` |
| 计划 | `planning` / `running` / `paused` / `ended` |
| 账号 | `active` / `paused` / `disabled` |
| 投递任务 | `pending` / `running` / `succeeded` / `failed` / `cancelled` |

`douyin_delivery_tasks.status = failed` 必须带 `error_message`。投递任务完成态会写 `finished_at`；运行态会写 `started_at`。调用方不能把投递平台失败包进成功 payload，必须通过 `/delivery-tasks/{id}/status` 或 `mark_task_failed` 落失败状态。

## Cleanup 契约

测试数据必须带唯一 marker（建议形如 `r2-douyin-20260703-xxxx`）。marker 可出现在标题、备注、正文、投递任务 `error_message`、`payload` 或 `result_payload` 中。清理调用：

```text
POST /api/douyin-delivery/cleanup
{ "marker": "r2-douyin-20260703-xxxx" }
```

marker 至少 6 个字符；仅清理当前用户数据，不清理 `owner_id=0` 的系统默认提示词。

## 可复现验收

```bash
cd backend && ruff check ../modules/douyin-delivery/backend ../modules/douyin-delivery/sandbox/test_module.py
cd .. && backend/.venv/bin/python -m pytest modules/douyin-delivery/sandbox/test_module.py
```

活栈能力验收使用项目工具台 `call_capability`：

```text
douyin-delivery:create_delivery_task
douyin-delivery:mark_task_failed
douyin-delivery:cleanup_marked_data
```

`generate_script` / `generate_ad_copy` / `validate_content` 的空输入或非法枚举必须返回结构化失败，不得进入模型调用后再假成功。

## 业务流程

```
产品/卖点 → 选择渠道/账号/素材 → AI 生成 → 校验(知识库) → 保存草稿 → 投放计划 → 投递任务状态
```

## 技术栈

- 后端：Python 3.14 + FastAPI + SQLAlchemy 2.0 async
- 前端：Vue3 + Element Plus + TypeScript
- AI：模型网关 `gateway.service.chat`（profile: deepseek-v4-flash）
- 知识库：`call_capability("knowledge", "search")`
