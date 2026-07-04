---
name: "全链路产品化落地总攻收口：主链路能力补齐与 ReleaseGate 无 blocker"
type: "task"
tags: [full-productization, knowledge, agent, content-ir, desktop, release-gate, smoke, readme-matrix]
agent: "codex-full-productization-r1"
created: "2026-07-04T13:16:27.352925+00:00"
---

# 改了什么

执行《全链路产品化落地总攻大信》，合并 5 条 lane 审计并落地主链路补齐：Knowledge search 增加来源解释和 context_data；Agent workflow 列表增加步骤/工具/失败/产物/引用计数，Evidence reference 增加 source_module 和复制 ID；csv-parser/image-vision 输出收口为 Content IR 兼容 block type；Desktop app-loader 对普通 app 空 component_key fail visible，terminal-tools/web-tools background-service component_key 置空；35 个模块 README 补验收矩阵并新增 5 个缺失 README；smoke.py 接入 test_data_pollution_cleanup，修复 full gate 跑 smoke 后测试数据污染残留。

# 验证了什么

ruff 相关 Python 通过；toolkit lifecycle tests 48 passed/1 skipped；csv-parser/image-vision sandbox 通过；Agent workflow tests 18 passed；content artifact publish 8 passed；release/toolkit tests 65 passed/1 skipped；frontend build 通过；smoke_all(skip_ui=true) PASS_WITH_DEBT，29 passed/0 failed/1 skipped；release_gate preflight/full skip-ui 均 PASS_WITH_DEBT，无 blocker；test_data_pollution_audit 为 active=0/recycled=0/knowledge=0/content=0。

# 残留风险

剩余 debt 为未跑完整 UI gate、skip-ui 导致 UI coverage debt、sandbox matrix 35 pass/0 fail/0 skip 但 19 个模块有 chunk warning、工作区未提交。视觉模型链路有 mimo 401 与 qwen3-vl context 过大观察项，但本轮按降级路径通过。下一封收口信建议跑完整 UI gate、处理 sandbox chunk warning、做 Knowledge 有数据 e2e、Agent failure recovery、视觉解析质量专项。

# 关联 commit

尚未提交。收口文档：开发文档/项目记忆/全链路产品化落地总攻收口.md
