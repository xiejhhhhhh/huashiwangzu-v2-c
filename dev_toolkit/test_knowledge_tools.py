from __future__ import annotations

from dev_toolkit import knowledge_source_gap, knowledge_source_manifest_audit, knowledge_tools


def test_knowledge_tool_component_exports_pipeline_and_source_gap_tools() -> None:
    names = {tool.name for tool in knowledge_tools.tool_definitions()}

    assert names == {
        "knowledge_pipeline_snapshot",
        "knowledge_source_gap_snapshot",
        "knowledge_source_manifest_audit",
        "knowledge_source_manifest_summary",
        "knowledge_source_manifest_scan",
        "knowledge_source_manifest_enqueue",
    }
    assert knowledge_tools.handles_tool("knowledge_pipeline_snapshot") is True
    assert knowledge_tools.handles_tool("knowledge_source_gap_snapshot") is True
    assert knowledge_tools.handles_tool("knowledge_source_manifest_audit") is True
    assert knowledge_tools.handles_tool("knowledge_source_manifest_summary") is True
    assert knowledge_tools.handles_tool("knowledge_source_manifest_scan") is True
    assert knowledge_tools.handles_tool("knowledge_source_manifest_enqueue") is True


def test_source_gap_extension_normalization_defaults_to_documents_and_images() -> None:
    extensions = knowledge_source_gap.normalize_extensions(None)

    assert "pdf" in extensions
    assert "docx" in extensions
    assert "jpg" in extensions
    assert "png" in extensions


def test_source_gap_extension_normalization_accepts_dotted_values() -> None:
    extensions = knowledge_source_gap.normalize_extensions([".PDF", "jpg", "pdf", ""])

    assert extensions == ["jpg", "pdf"]


def test_source_gap_root_id_normalization_ignores_invalid_values() -> None:
    assert knowledge_source_gap.normalize_int_list(["48", "bad", -1, 0, 1141]) == [48, 1141]


def test_source_manifest_audit_stage_normalization_defaults_to_pipeline_stages() -> None:
    stages = knowledge_source_manifest_audit.normalize_stage_list(None)

    assert "source_validate" in stages
    assert "parse_index" in stages
    assert "raw_vision" in stages
    assert "relations" in stages


def test_source_manifest_audit_stage_normalization_deduplicates() -> None:
    assert knowledge_source_manifest_audit.normalize_stage_list(["parse_index", "", "parse_index"]) == ["parse_index"]
