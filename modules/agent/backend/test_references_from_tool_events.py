"""Tests for extracting real user-facing references from tool events."""

import sys
from pathlib import Path

AGENT_BACKEND_DIR = Path(__file__).resolve().parent
if str(AGENT_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_BACKEND_DIR))

from _utils import references_from_tool_events


def test_skill_use_web_search_extracts_real_urls():
    refs = references_from_tool_events([
        {
            "type": "tool_result",
            "name": "skill_use",
            "result": {
                "name": "web-tools__search",
                "result": {
                    "results": [
                        {
                            "title": "巨量千川帮助中心",
                            "url": "https://qianchuan.jinritemai.com/docs/help",
                            "snippet": "巨量千川官方帮助文档",
                        }
                    ]
                },
            },
        }
    ])

    assert refs == [
        {
            "type": "web",
            "title": "巨量千川帮助中心",
            "url": "https://qianchuan.jinritemai.com/docs/help",
            "source": "https://qianchuan.jinritemai.com/docs/help",
            "excerpt": "巨量千川官方帮助文档",
        }
    ]


def test_tool_names_are_not_treated_as_sources():
    refs = references_from_tool_events([
        {"type": "tool_result", "name": "skill_list", "result": {"skills": []}},
        {"type": "tool_result", "name": "web_search", "result": {"query": "x"}},
    ])

    assert refs == []


def test_skill_use_knowledge_search_extracts_clickable_file_refs():
    refs = references_from_tool_events([
        {
            "type": "tool_result",
            "name": "skill_use",
            "effective_tool_name": "knowledge__search",
            "result": {
                "query": "蔻诺 清颜 博泉 俏小喵",
                "results": [
                    {
                        "document_name": "产品讲解宣传片（娇薇诗+蔻诺）",
                        "source_file": "产品讲解宣传片（娇薇诗+蔻诺）.pdf",
                        "file_id": 9840,
                        "source_file_id": 9840,
                        "document_id": 120,
                        "chunk_id": 456,
                        "page": 3,
                        "extension": "pdf",
                        "text": "蔻诺与清颜相关资料片段",
                    }
                ],
            },
        }
    ])

    assert refs == [
        {
            "type": "knowledge",
            "ref_key": "file_id",
            "ref_id": "9840",
            "title": "产品讲解宣传片（娇薇诗+蔻诺） 第3页",
            "source": "产品讲解宣传片（娇薇诗+蔻诺）",
            "source_module": "knowledge",
            "file_id": 9840,
            "source_file_id": 9840,
            "document_id": 120,
            "chunk_id": 456,
            "package_id": None,
            "page": 3,
            "section": None,
            "score": None,
            "excerpt": "蔻诺与清颜相关资料片段",
            "download_url": "/api/files/download/9840",
            "format": "pdf",
            "open_url": "app://file/open?file_id=9840&file_name=%E4%BA%A7%E5%93%81%E8%AE%B2%E8%A7%A3%E5%AE%A3%E4%BC%A0%E7%89%87%EF%BC%88%E5%A8%87%E8%96%87%E8%AF%97%2B%E8%94%BB%E8%AF%BA%EF%BC%89&format=pdf&page=3",
            "url": "app://file/open?file_id=9840&file_name=%E4%BA%A7%E5%93%81%E8%AE%B2%E8%A7%A3%E5%AE%A3%E4%BC%A0%E7%89%87%EF%BC%88%E5%A8%87%E8%96%87%E8%AF%97%2B%E8%94%BB%E8%AF%BA%EF%BC%89&format=pdf&page=3",
        }
    ]


def test_knowledge_search_refs_do_not_emit_generic_artifact_noise():
    refs = references_from_tool_events([
        {
            "type": "tool_result",
            "name": "knowledge__search",
            "result": {
                "results": [
                    {
                        "document_name": "录音故事汇(1)(1)",
                        "file_id": 42,
                        "document_id": 7,
                        "chunk_id": 9,
                        "page": 1,
                        "extension": "pdf",
                    }
                ],
            },
        }
    ])

    assert len(refs) == 1
    assert refs[0]["type"] == "knowledge"
    assert refs[0]["file_id"] == 42
