---
name: "frontend-runtime-cleanup-r2 节点2：目标文件 CodeGraph 读取"
type: "investigation"
tags: [frontend, runtime, audit, codegraph]
agent: "frontend-runtime-cleanup-worker-r2"
created: "2026-07-02T16:15:19.066840+00:00"
---

用 code_node 读取了 frontend/src/shared/api/index.ts、modules/_template/runtime/index.ts、modules/knowledge/frontend/api.ts，以及 pdf-viewer/text-editor runtime 代表文件。下一步对裸 fetch、Authorization/localStorage token、any/@ts-ignore 和字段名映射做 rg 验证，并只修会形成完整链路分叉的问题。
