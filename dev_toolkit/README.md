# 项目工具台 MCP Server

开工先连我。`python3.14 dev_toolkit/server.py` (stdio), 注册在 `.mcp.json`。

通过 MCP 协议暴露 15 个开发加速工具, 供 AI agent 直接调用。

## 工具清单

### 全景感知
| 工具 | 说明 |
|------|------|
| `brief()` | 项目全景: README + 最近变更 + 投递箱待处理 + 最近 Git 提交 + 最近项目记忆(带 agent) |

### 代码探索与修改验证
| 工具 | 说明 |
|------|------|
| `code_explore(query)` | codegraph 探索: 查符号/调用链/影响面 |
| `code_node(symbol)` | codegraph 查符号或文件定义 |
| `code_impact(path)` | codegraph 查文件改动的影响面 |
| `lint(path)` | ruff 静态检查 Python 文件 |

### 接口与能力查询
| 工具 | 说明 |
|------|------|
| `routes(filter)` | 从 openapi.json 查端点(方法/路径/参数) |
| `capabilities(module)` | 扫描模块 manifest.json 查准能力+参数 |
| `db_schema(table)` | 查数据库表结构(列名/类型/nullable) |

### 系统探测
| 工具 | 说明 |
|------|------|
| `probe(method, path, body)` | 自动登录后打后端任意 HTTP 接口 |
| `call_capability(module, action, params)` | 调模块能力(跨模块) |
| `tail_log(module, lines)` | 查看模块日志尾部 |
| `sql(query)` | 只读 SQL 查询(SELECT/WITH/EXPLAIN) |
| `web_read(url)` | 读网页返回 markdown 正文 |

### 记忆与归因
| 工具 | 说明 |
|------|------|
| `memory_search(query, k)` | 语义+关键词搜索项目记忆 |
| `memory_write(type, title, body, tags, agent)` | 写入项目记忆, agent 字段用于归因 |
| `memory_recent(n)` | 最近 N 条记忆 |

### 测试
| 工具 | 说明 |
|------|------|
| `run_test(target)` | 跑单个测试(文件/用例)不跑全局 |

## 开发铁律

1. 每个开发 agent 开工先调 `brief()` 看全貌。
2. 查代码优先 `code_explore`/`code_node`/`code_impact` (codegraph)。
3. 查准端点/能力/表用 `routes`/`capabilities`/`db_schema`。
4. 改完先 `lint` 静态查错。
5. 验证用 `probe`/`call_capability` 打活系统。
6. 单测用 `run_test`, 不跑全局。
7. 收工 `memory_write(agent="<自己>")` 落条归因。
