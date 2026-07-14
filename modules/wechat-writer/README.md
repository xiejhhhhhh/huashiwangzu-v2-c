# wechat-writer — 公众号写作助手

WeChat writing module for prompt-managed article/draft generation and content validation workflows.

## 对外能力

| 能力 | 说明 |
|------|------|
| `generate_article` | 根据大纲生成完整初稿 |
| `generate_outline` | 根据选题生成文章大纲 |
| `generate_topics` | 根据产品/季节/问题肌主题生成选题建议 |
| `validate_content` | 校验成分/功效内容的专业性 |

## 接口

后端前缀：`/api/wechat-writer`

| 路径族 | 方法 |
|------|------|
| /article | POST |
| /drafts | DELETE/GET/POST/PUT |
| /outline | POST |
| /prompts | DELETE/GET/POST |
| /topics | POST |
| /validate | POST |

## 数据表

| 表名 |
|------|
| `wechat_drafts` |
| `wechat_prompts` |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/wechat-writer/sandbox/test_module.py
cd modules/wechat-writer/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module wechat-writer --check
```
