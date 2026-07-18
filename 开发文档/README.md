# 开发文档

## 文档怎么用

| 位置 | 写什么 | 不写什么 |
|------|--------|----------|
| 主文档（本目录与 01/02/03） | 架构、如何调用、有什么能力 | 施工流水、过程争论、逐日进度 |
| `临时文档/` | **未落地** 的进行中方案/审计 | 已完成方案正文（应蒸馏后归档） |
| `开发历史记录/` | 已蒸馏归档的历史方案 | 当作现行合同 |

规则：临时文档宜少而干净；落地后把“如何调用/架构”并入主文档，原稿归档，不在临时区留尸体。

## 架构边界

- 框架能力（鉴权/文件/网关/任务/桌面壳/产品运行时）→ `frontend/src/` 或 `backend/app/` 或 `products/`
- 业务能力 → `modules/{key}/`
- 模块只改自己目录；跨模块走 capability bus / `/api/modules/call`

## 主文档索引

| 文档 | 内容 |
|------|------|
| [`01_框架开发文档/README.md`](01_框架开发文档/README.md) | 桌面壳、窗口、Product 加载、Content Open |
| [`02_底层开发文档/README.md`](02_底层开发文档/README.md) | 网关、任务、鉴权、内容/产品平台服务 |
| [`03_模块开发文档/README.md`](03_模块开发文档/README.md) | 模块结构、manifest、capability、知识库调用摘要 |
| [`算法调优手册.md`](算法调优手册.md) | Agent 引擎参数调优 |

## 正式主路径（摘要）

```text
桌面清单  GET  /api/desktop/products
打开文件  POST /api/content/open
内容读写  /api/content/drafts|packages/...
模型调用  backend/app/gateway + models.json
```

细节见 01 / 02 主文档。

## 当前临时文档（仅未落地 / 进行中）

| 文件 | 主题 |
|------|------|
| `临时文档/04_桌面壳统一一致性收口方案_双Demo对照_20260718.md` | 壳层材质/几何/双皮肤底座（mac 壳已收；Win 插槽） |
| `临时文档/02_底座未完成收口清单_20260718.md` | 网关熔断、PgBouncer、召回阈值等 |
| `临时文档/03_规则优先实体抽取_待落地_20260718.md` | 知识库实体抽取规则优先方案 |

历史完成索引：

- `临时文档/01_桌面壳LiquidGlass视觉收口_20260718.md`（V1–V3 已完成，不再施工）
- `临时文档/05_mac应用UI契约与软件风格统一施工方案_20260718.md`（切片 1–6 完成；用法见 `01_框架开发文档/README.md` §1.1）

运维脚本目录：`临时文档/本轮运维脚本_20260717/`、`临时文档/语义治理验证脚本/`（脚本工具，非方案正文）。

## 模型路由

单一配置：`backend/data/config/models.json`（改后需重启/reload 才被常驻进程读取）。

```text
Agent 对话        → deepseek-v4-flash (opencode)
Agent 视觉/生图   → gpt-5.5 via jayce
知识库文本分析    → deepseek-v4-flash 优先
知识库视觉分析    → gpt-5.5 via jayce → qwen3-vl
向量嵌入          → qwen3-embedding-8b
重排序            → bge-reranker
```

## 验证命令

```bash
cd backend && .venv/bin/python -m pytest
cd frontend && npm run build
python3.14 dev_toolkit/release_gate.py --preflight --skip-ui
```

## 蒸馏约定

1. 已落地：合并“架构 / 调用 / 能力”进 01/02/03，原稿移入 `开发历史记录/`
2. 未落地：压成短临时文档（目标、边界、验收），删流水账
3. 主文档禁止过程日记；临时文档禁止假“已验收”若代码未齐
