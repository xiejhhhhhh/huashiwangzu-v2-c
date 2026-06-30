---
name: "Agent 上下文压缩升级 10 补强—递归裁剪 skill_use 内层参数"
type: task
tags: ["agent", "上下文压缩", "tool-result-reducer", "skill-use", "递归裁剪", "观测验证"]
created: 2026-06-30
agent: opencode
---

在既有升级 10 未提交工作区上，仅补强 modules/agent/backend/engine/context_injectors/tool_result_reducer.py 与 test_tool_result_reducer.py。新增递归 tool argument 裁剪：dict 递归 value、list 保留前 5 项并追加 marker、str 超 500 字符截断、最大深度 4 后用占位；不可 JSON 序列化值通过 json.dumps(default=str) 兜底，异常 dict key 转 str。_truncate_tool_call_arguments 保证裁剪后 arguments 为合法 JSON 字符串；原本是短 JSON 字符串时保持原始格式；短 dict 经 reduce 后转换为 JSON 字符串。补充 skill_use.args.query、args.items、深层 dict、短参数保真、JSON 字符串类型/合法性测试。指定三文件回归 65 passed，两个修改文件 ruff 全绿。直接 reduce 样本：tool_args_truncated=1，arguments_type=str，query 长度 4800→511，json_valid=true。残留风险：深度超过 4 的参数会有意替换为占位，截断是确定性保头策略，不做语义摘要。仓库开始时已有 compressor/event_store/handlers/prompt_seeds 等升级 10 未提交改动，本次未触碰。
