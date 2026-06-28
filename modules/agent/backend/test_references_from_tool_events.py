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
