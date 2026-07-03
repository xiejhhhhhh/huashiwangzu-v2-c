---
name: "github-search sweep r2 阶段1扫描发现"
type: "task"
tags: [github-search, module-sweep, r2, findings, task_id:github-search-sweep-20260703-r2]
agent: "codex-github-search-sweep-20260703-r2"
created: "2026-07-03T07:09:31.045514+00:00"
---

阶段1扫描发现：1) github_client._run_gh 返回 None 吞掉超时/gh缺失/CLI错误/JSON解析错误，search_repositories/search_code 又把失败转为空列表，导致能力和 HTTP 端点把网络/CLI失败与真实空结果混淆。2) _cap_search_code 判断 items is None，但 search_code 当前失败只返回 []，该错误语义分支不可达。3) _cap_search 对空查询返回 data.error，HTTP 仍 success:true，属于假成功语义；limit int 转换也可能 ValueError 冒成 500。4) 缓存是纯内存且不区分成功/失败语义；无显式限流，可能在并发/多 worker 下放大 gh/GitHub 调用。5) manifest 的 search 参数声明包含 search_code，但后端 search capability 不支持该参数。6) sandbox/test_module.py 未导入 Any，且输出 shape 断言是 name/full_name/html_url/topics，与真实 router 返回 name/url/stars/language/license/last_updated/open_issues 不一致。7) 模块无持久 README；按本任务范围先不新增长期文档，除非修复需要。
