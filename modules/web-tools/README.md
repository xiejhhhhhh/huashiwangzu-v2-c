# web-tools — 联网工具

联网搜索和网页正文抓取，无需 API key，含 SSRF 防护拒绝内网地址。

## 对外能力

| 能力 | 说明 |
|------|------|
| `fetch` | 抓取指定网址正文文本(无需API key)。自动过滤 script/style/nav/footer。含SSRF防护，拒绝内网地址。 |
| `search` | 联网搜索网页,返回标题/链接/摘要(无需API key)。基于 DuckDuckGo HTML 端点。 |

## 接口

后端前缀：`/api/web-tools`

| 路径族 | 方法 |
|------|------|
| /fetch | POST |
| /health | GET |
| /search | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/web-tools/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module web-tools --check
```
