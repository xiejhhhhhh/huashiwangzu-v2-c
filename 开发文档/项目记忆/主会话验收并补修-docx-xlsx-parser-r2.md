---
name: "主会话验收并补修 docx/xlsx parser r2"
type: "task"
tags: [verification, docx-parser, xlsx-parser, r2, office-parser]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:54:12.618515+00:00"
---

主会话接收 docx-parser/xlsx-parser 子代理结果后重新验收。发现 docx-parser:parse 在 file_id=0 仍返回 500，原因是 router 未把 run_uploaded_file_capability 的 ValueError 转为框架 ValidationError；同时 corrupt DOCX 解析异常也缺少模块级错误类型。已补 DocxParseError，并在 router 中把 file_id 校验/解析错误转 422。验收：ruff 通过；docx sandbox 4 passed；xlsx sandbox 1 passed；compileall docx 通过；重启后端到 uvicorn 父进程 82128、workers 82575/82576/82577 后 /api/health module_errors=null；docx-parser/xlsx-parser health 200；call_capability docx/xlsx file_id=0 均 422 success:false；xlsx file_id=2018 返回真实 table block；docx file_id=2017 返回有效空 DOCX 成功结构。提交时只 stage modules/docx-parser、modules/xlsx-parser 和相关项目记忆/反馈，不混入 text/csv/data/uploads。
