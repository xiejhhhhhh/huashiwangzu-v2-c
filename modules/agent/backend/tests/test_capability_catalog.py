from __future__ import annotations

import pytest

from modules.agent.backend.services import capability_catalog


def _candidate(capability_id: int, module: str, action: str, description: str) -> dict:
    return {
        "capability_id": capability_id,
        "module": module,
        "action": action,
        "brief": description,
        "description": description,
        "parameters": {"query": {"type": "string"}},
        "execution_contract": {"output_reference_types": []},
        "retrieval": {"aliases": [], "when_to_use": description},
        "contract_hash": str(capability_id) * 64,
    }


_RECALL_CAPABILITIES = [
    _candidate(1, "knowledge", "search", "搜索公司内部知识库和企业文档"),
    _candidate(2, "desktop-tools", "search_files", "按名称定位用户文件"),
    _candidate(3, "desktop-tools", "open_file", "打开已经定位的文件"),
    _candidate(4, "office-gen", "docx", "创建 Word DOCX 文档"),
    _candidate(5, "office-gen", "convert", "转换 Office 文件格式"),
    _candidate(6, "image-gen", "generate", "根据提示词生成新图片"),
    _candidate(7, "image-gen", "transform", "编辑或变换已有 JPG PNG 图片"),
    _candidate(8, "tasks", "get", "查询异步任务状态"),
    _candidate(9, "artifact", "publish", "发布已生成制品"),
    _candidate(10, "web-tools", "search", "搜索互联网公开资料"),
    _candidate(11, "memory", "recall", "召回用户个人记忆"),
    _candidate(12, "agent", "get_my_profile", "读取用户个人画像"),
]


def _keyword_embedding(values: list[str]) -> list[list[float]]:
    groups = (
        ("知识库", "内部", "企业文档", "knowledge"),
        ("文件", "定位", "打开", "file"),
        ("word", "docx", "office", "转换"),
        ("图片", "jpg", "png", "生成", "编辑", "image"),
        ("任务", "异步", "task", "制品", "发布"),
        ("互联网", "公开", "web"),
    )
    return [
        [float(sum(term in value.lower() for term in terms)) for terms in groups]
        for value in values
    ]


@pytest.mark.asyncio
async def test_catalog_retrieval_handles_chinese_and_returns_direct_tools(monkeypatch) -> None:
    async def fake_snapshot(*, user_id: int, caller=None):
        assert user_id == 4
        return {
            "catalog_hash": "a" * 64,
            "principal": {"user_id": 4, "profile_version": "b" * 20},
            "capabilities": [
                {
                    "capability_id": 1,
                    "module": "knowledge",
                    "action": "search",
                    "brief": "搜索企业知识库",
                    "description": "根据问题检索知识库内容",
                    "parameters": {"query": {"type": "string"}},
                    "retrieval": {"aliases": ["查资料"], "when_to_use": "查询内部文档"},
                },
                {
                    "capability_id": 2,
                    "module": "image-gen",
                    "action": "generate",
                    "brief": "生成图片",
                    "description": "根据提示词生成图片",
                    "parameters": {"prompt": {"type": "string"}},
                    "retrieval": {"aliases": [], "when_to_use": ""},
                },
            ],
        }

    monkeypatch.setattr(capability_catalog, "authorized_capability_snapshot", fake_snapshot)
    result = await capability_catalog.retrieve_capabilities(
        user_id=4,
        query="帮我查一下公司知识库资料",
        limit=1,
    )

    assert result["candidates"][0]["capability_id"] == 1
    tools = capability_catalog.direct_function_tools(result["candidates"])
    assert tools[0]["function"]["name"] == "knowledge__search"
    assert tools[0]["function"]["parameters"]["properties"]["query"]["type"] == "string"
    assert "capability_id" not in tools[0]


@pytest.mark.asyncio
async def test_catalog_retrieval_hides_internal_capabilities(monkeypatch) -> None:
    async def fake_snapshot(*, user_id: int, caller=None):
        return {
            "catalog_hash": "a" * 64,
            "principal": {"user_id": user_id, "profile_version": "b" * 20},
            "capabilities": [
                {
                    "capability_id": 1,
                    "module": "image-vision",
                    "action": "describe",
                    "brief": "legacy image parser",
                    "description": "internal image parser",
                    "parameters": {"file_id": {"type": "integer"}},
                    "retrieval": {"expose_to_agent": False},
                },
                {
                    "capability_id": 2,
                    "module": "media-intelligence",
                    "action": "analyze_image",
                    "brief": "看图理解",
                    "description": "Agent-facing image understanding",
                    "parameters": {"file_id": {"type": "integer"}},
                    "retrieval": {"aliases": ["看图"], "when_to_use": "用户要求理解图片"},
                },
            ],
        }

    async def no_experiences(**_kwargs):
        return []

    async def embed(values: list[str]) -> list[list[float]]:
        return [[1.0] for _ in values]

    monkeypatch.setattr(capability_catalog, "authorized_capability_snapshot", fake_snapshot)
    monkeypatch.setattr(capability_catalog, "_visible_experience_patterns", no_experiences)
    result = await capability_catalog.retrieve_capabilities(
        user_id=4,
        query="帮我看图",
        limit=8,
        embedding_fn=embed,
    )

    names = [f"{item['module']}__{item['action']}" for item in result["candidates"]]
    assert names == ["media-intelligence__analyze_image"]
    assert result["total_snapshot_capabilities"] == 2
    assert result["total_authorized"] == 1


def test_direct_tools_normalize_legacy_parameter_metadata() -> None:
    tools = capability_catalog.direct_function_tools([
        {
            "capability_id": 9,
            "module": "demo",
            "action": "read",
            "description": "Read a demo record",
            "parameters": {"record_id": "integer", "note": "Optional note"},
        },
    ])

    properties = tools[0]["function"]["parameters"]["properties"]
    assert properties["record_id"] == {"type": "integer"}
    assert properties["note"] == {"type": "string", "description": "Optional note"}


def test_parameter_schema_normalizes_dict_type_aliases_recursively() -> None:
    schema = capability_catalog.parameter_schema({
        "file_id": {"type": "int", "description": "Image file ID"},
        "refine": {"type": "bool", "description": "Run VLM refine when configured"},
        "options": {
            "type": "object",
            "properties": {
                "threshold": {"type": "float"},
                "tags": {"type": "array", "items": {"type": "str"}},
            },
        },
    })

    properties = schema["properties"]
    assert properties["file_id"]["type"] == "integer"
    assert properties["refine"]["type"] == "boolean"
    assert properties["options"]["properties"]["threshold"]["type"] == "number"
    assert properties["options"]["properties"]["tags"]["items"]["type"] == "string"


@pytest.mark.asyncio
async def test_skill_list_query_prefers_read_only_capability(monkeypatch) -> None:
    async def fake_snapshot(*, user_id: int, caller=None):
        return {
            "catalog_hash": "a" * 64,
            "principal": {"user_id": user_id, "profile_version": "b" * 20},
            "capabilities": [
                {
                    "capability_id": 13,
                    "module": "agent",
                    "action": "list_skills",
                    "brief": "读取技能列表",
                    "description": "读取当前注册的技能列表和治理状态",
                    "parameters": {"limit": {"type": "integer"}},
                    "retrieval": {
                        "aliases": ["所有技能", "技能列表", "可用技能"],
                        "when_to_use": "用户要求查看当前注册的技能",
                    },
                    "execution_contract": {"side_effect_level": "none"},
                },
                {
                    "capability_id": 14,
                    "module": "agent",
                    "action": "skill_manage",
                    "brief": "管理技能",
                    "description": "创建、更新、删除和审批技能",
                    "parameters": {"action": {"type": "string"}},
                    "retrieval": {"when_to_use": "管理技能治理状态"},
                    "execution_contract": {
                        "side_effect_level": "admin_config",
                        "approval_policy": "requires_confirmation",
                    },
                },
            ],
        }

    async def no_experiences(**_kwargs):
        return []

    monkeypatch.setattr(capability_catalog, "authorized_capability_snapshot", fake_snapshot)
    monkeypatch.setattr(capability_catalog, "_visible_experience_patterns", no_experiences)
    result = await capability_catalog.retrieve_capabilities(
        user_id=4,
        query="那你试试直接用技能读取一下你所有的技能列表",
        limit=2,
        embedding_fn=None,
    )

    names = [f"{item['module']}__{item['action']}" for item in result["candidates"]]
    assert names[0] == "agent__list_skills"
    assert result["candidates"][0]["execution_contract"]["side_effect_level"] == "none"


@pytest.mark.asyncio
async def test_fixed_agent_regression_corpus_meets_recall_and_mrr(monkeypatch) -> None:
    async def fake_snapshot(*, user_id: int, caller=None):
        return {
            "catalog_hash": "a" * 64,
            "principal": {"user_id": user_id, "profile_version": "b" * 20},
            "capabilities": _RECALL_CAPABILITIES,
        }

    async def no_experiences(**_kwargs):
        return []

    async def embed(values: list[str]) -> list[list[float]]:
        return _keyword_embedding(values)

    monkeypatch.setattr(capability_catalog, "authorized_capability_snapshot", fake_snapshot)
    monkeypatch.setattr(capability_catalog, "_visible_experience_patterns", no_experiences)
    cases = (
        ("查一下公司知识库里的报销制度", "knowledge__search"),
        ("帮我定位并打开季度总结文件", "desktop-tools__search_files"),
        ("生成一份 Word DOCX 会议纪要", "office-gen__docx"),
        ("把这份 Office 文档转换成另一个格式", "office-gen__convert"),
        ("根据提示词生成一张新图片", "image-gen__generate"),
        ("编辑这张 JPG 图片，不要送进文本读取器", "image-gen__transform"),
        ("查看异步任务现在是否完成", "tasks__get"),
        ("搜索互联网公开资料", "web-tools__search"),
    )
    hits = 0
    reciprocal_rank = 0.0
    for query, expected in cases:
        result = await capability_catalog.retrieve_capabilities(
            user_id=4,
            query=query,
            limit=8,
            embedding_fn=embed,
        )
        names = [f"{item['module']}__{item['action']}" for item in result["candidates"]]
        if expected in names:
            hits += 1
            reciprocal_rank += 1 / (names.index(expected) + 1)

    assert hits / len(cases) >= 0.95
    assert reciprocal_rank / len(cases) >= 0.75


@pytest.mark.asyncio
async def test_semantic_cache_embeds_only_query_on_hit_and_isolates_users(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[int] = []
    catalog_hash = "c" * 64

    async def fake_snapshot(*, user_id: int, caller=None):
        return {
            "catalog_hash": catalog_hash,
            "principal": {"user_id": user_id, "profile_version": f"p{user_id}" * 10},
            "capabilities": _RECALL_CAPABILITIES[:2],
        }

    async def embedding(values: list[str]) -> list[list[float]]:
        calls.append(len(values))
        return _keyword_embedding(values)

    async def embedding_profile():
        return "regression-embedding", embedding

    async def no_experiences(**_kwargs):
        return []

    monkeypatch.setattr(capability_catalog, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(capability_catalog, "authorized_capability_snapshot", fake_snapshot)
    monkeypatch.setattr(capability_catalog, "_embedding_profile", embedding_profile)
    monkeypatch.setattr(capability_catalog, "_visible_experience_patterns", no_experiences)

    first = await capability_catalog.retrieve_capabilities(user_id=4, query="知识库", limit=1)
    second = await capability_catalog.retrieve_capabilities(user_id=4, query="企业文档", limit=1)
    assert calls == [2, 1, 1]
    assert first["semantic_index"]["cache_rebuilt"] is True
    assert second["semantic_index"]["cache_rebuilt"] is False
    assert "cache_path" not in second["semantic_index"]
    assert second["semantic_index"]["cache_key"].startswith("u4-")

    await capability_catalog.retrieve_capabilities(user_id=5, query="知识库", limit=1)
    assert calls[-2:] == [2, 1]
    assert len(list(tmp_path.glob("*.json"))) == 2

    catalog_hash = "d" * 64
    await capability_catalog.retrieve_capabilities(user_id=4, query="知识库", limit=1)
    assert calls[-2:] == [2, 1]
    assert len(list(tmp_path.glob("*.json"))) == 3


@pytest.mark.asyncio
async def test_sql_snapshot_boundary_cannot_restore_other_users_capabilities(monkeypatch) -> None:
    async def fake_snapshot(*, user_id: int, caller=None):
        visible = _RECALL_CAPABILITIES[:1] if user_id == 4 else _RECALL_CAPABILITIES[5:7]
        return {
            "catalog_hash": str(user_id) * 64,
            "principal": {"user_id": user_id, "profile_version": str(user_id) * 20},
            "capabilities": visible,
        }

    async def no_experiences(**_kwargs):
        return []

    async def embed(values: list[str]) -> list[list[float]]:
        return _keyword_embedding(values)

    monkeypatch.setattr(capability_catalog, "authorized_capability_snapshot", fake_snapshot)
    monkeypatch.setattr(capability_catalog, "_visible_experience_patterns", no_experiences)
    viewer = await capability_catalog.retrieve_capabilities(
        user_id=4,
        query="生成图片",
        embedding_fn=embed,
    )
    image_user = await capability_catalog.retrieve_capabilities(
        user_id=5,
        query="生成图片",
        embedding_fn=embed,
    )

    assert {item["module"] for item in viewer["candidates"]} == {"knowledge"}
    assert {item["module"] for item in image_user["candidates"]} == {"image-gen"}
