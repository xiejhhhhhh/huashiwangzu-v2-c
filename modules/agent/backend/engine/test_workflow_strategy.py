"""Tests for workflow_strategy module."""
from .workflow_strategy import (
    WORKFLOW_DEFINITIONS,
    apply_workflow_injection,
    format_workflow_injection,
    get_all_workflows,
    match_workflow,
)


class TestMatchWorkflow:
    def test_matches_project_keywords(self):
        assert match_workflow("这个项目需要收口") is not None
        assert match_workflow("验收一下这个任务") is not None
        assert match_workflow("发信给华哥") is not None

    def test_matches_database_keywords(self):
        assert match_workflow("数据库迁移需要执行") is not None
        assert match_workflow("改一下SQL schema") is not None

    def test_matches_module_keywords(self):
        assert match_workflow("新建模块 user") is not None
        assert match_workflow("新模块开发") is not None

    def test_no_match_for_generic_input(self):
        assert match_workflow("你好，今天天气怎么样") is None
        assert match_workflow("") is None
        assert match_workflow(None) is None

    def test_case_insensitive(self):
        # Latin-script keywords are case-insensitive
        assert match_workflow("Migration") is not None
        assert match_workflow("SCHEMA") is not None


class TestFormatWorkflowInjection:
    def test_default_format(self):
        result = format_workflow_injection(None)
        assert result is not None
        assert "<project_workflow>" in result
        assert "</project_workflow>" in result

    def test_custom_workflow_format(self):
        workflow = {
            "label": "test_workflow",
            "workflow_steps": [
                {"action": "step1", "detail": "do step 1"},
                {"action": "step2", "detail": "do step 2"},
            ],
        }
        result = format_workflow_injection(workflow)
        assert "<test_workflow>" in result
        assert "</test_workflow>" in result
        assert "step1" in result
        assert "step2" in result

    def test_empty_steps(self):
        workflow = {"label": "empty_wf", "workflow_steps": []}
        result = format_workflow_injection(workflow)
        assert "<empty_wf>" in result


class TestGetAllWorkflows:
    def test_returns_all_definitions(self):
        workflows = get_all_workflows()
        assert len(workflows) == len(WORKFLOW_DEFINITIONS)
        for wf in workflows:
            assert "label" in wf
            assert "keywords" in wf
            assert "step_count" in wf

    def test_each_has_positive_step_count(self):
        for wf in get_all_workflows():
            assert wf["step_count"] > 0


class TestApplyWorkflowInjection:
    def test_injects_when_matched(self):
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        diag = apply_workflow_injection("开始项目收口验收", messages)
        assert diag["workflow_injected"] is True
        assert diag["workflow_label"] == "project_workflow"
        assert len(messages[0]["content"]) > len("You are a helpful assistant.")

    def test_no_injection_when_no_match(self):
        messages = [{"role": "system", "content": "base prompt"}]
        original_len = len(messages[0]["content"])
        diag = apply_workflow_injection("hello world", messages)
        assert diag["workflow_injected"] is False
        assert len(messages[0]["content"]) == original_len

    def test_injection_into_first_system_message_only(self):
        messages = [
            {"role": "system", "content": "first sys"},
            {"role": "system", "content": "second sys"},
        ]
        apply_workflow_injection("项目任务", messages)
        # Only first system message should have been modified
        assert len(messages[0]["content"]) > len("first sys")
        assert messages[1]["content"] == "second sys"

    def test_graceful_handling_of_empty_messages(self):
        diag = apply_workflow_injection("项目", [])
        assert diag["workflow_injected"] is False

    def test_graceful_handling_of_no_system_message(self):
        messages = [{"role": "user", "content": "hi"}]
        diag = apply_workflow_injection("项目", messages)
        # Matched but no system message to inject into — gracefully no-op
        assert diag["workflow_injected"] is True
        assert diag["workflow_label"] == "project_workflow"
        assert len(messages[0]["content"]) == len("hi")
