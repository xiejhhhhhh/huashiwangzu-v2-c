---
name: "主会话验收 markdown email structured parser r2"
type: "task"
tags: [verification, markdown-parser, email-parser, structured-parser, r2, parser]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T08:06:07.365555+00:00"
---

主会话接收 markdown-parser、email-parser、structured-parser 子代理结果后复核并补修。额外发现 markdown 独立图片行会同时产出 paragraph 与 image block，已在 router 中改为行内识别独立图片块并去除末尾全局图片扫描，sandbox 增加不重复断言。验收：ruff 覆盖 markdown/email/structured 8 个 Python 文件全部通过；pytest 单跑 markdown 2 passed、email 1 passed、structured 10 passed；三者合跑 --import-mode=importlib 共 13 passed；后端重启到 uvicorn 父进程 84842、workers 85385/85386/85387 后 /api/health module_errors=null；三个模块 health 均 200；call_capability markdown/email/structured 坏 file_id 均 422 success:false；直接 POST /parse file_id=0 均 422。库中未找到现成 md/eml/json/yaml/yml/msg 文件记录，未创建 data/uploads；正向成功路径由 sandbox 使用生产 parser/router 样例覆盖。
