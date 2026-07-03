---
name: "R4 模块能力契约 drift 第一稳定节点"
type: "task"
tags: [r4, capability-contract, manifest, runtime, drift]
agent: "codex-contract-lane-r4"
created: "2026-07-03T11:20:47.853582+00:00"
---

R4 大泳道完成第一稳定节点：使用 dev_toolkit/contract_tools.py 暴露的 capability_contract_diff 全量扫描 modules/* public_actions 与 register_capability metadata。初扫发现 agent 参数 metadata、desktop-tools list/search 参数静态不可解析、image-gen usage_history.limit、codemap report_inaccuracy.agent_id（并行 codemap 现场）与 agent/bootstrap 动态注册 uncheckable。已在本泳道修复 agent manifest/bootstrap metadata、desktop-tools runtime metadata 与 sandbox 参数断言、image-gen manifest 与 sandbox 断言；未修改 dev_toolkit、backend/app、frontend/src、knowledge/codemap/douyin-delivery。复扫结果：checked_modules=36, modules_with_drift=0, uncheckable_sites=0。
