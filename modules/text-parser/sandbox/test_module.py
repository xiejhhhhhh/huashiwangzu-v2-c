"""Sandbox tests for text-parser module."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
PARSER_PATH = Path(__file__).resolve().parents[1] / "backend" / "parser.py"

spec = importlib.util.spec_from_file_location("text_parser_core", PARSER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Failed to load text-parser backend parser")
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


def _block_texts(result: dict[str, object]) -> list[str]:
    blocks = result["blocks"]
    assert isinstance(blocks, list)
    return [str(block["text"]) for block in blocks]


def _assert_valid_shape(result: dict[str, object]) -> None:
    assert {"file_id", "format", "blocks", "resources", "metadata"} <= set(result)
    blocks = result["blocks"]
    resources = result["resources"]
    metadata = result["metadata"]
    assert isinstance(blocks, list)
    assert isinstance(resources, list)
    assert isinstance(metadata, dict)
    for block in blocks:
        assert {"type", "text", "page", "resource_ref"} <= set(block)


def test_plain_text_sample_parses_paragraphs() -> None:
    result = parser.parse_text_file(1, SAMPLES_DIR / "sample.txt", "txt")

    _assert_valid_shape(result)
    assert result["format"] == "txt"
    assert result["metadata"]["truncated"] is False
    assert _block_texts(result) == [
        "Hello World",
        "This is a plain text file for testing.\nIt has multiple paragraphs separated by blank lines.",
        "Another paragraph here.\nAnd a third one for good measure.",
    ]


def test_markdown_sample_parses_headings_and_code() -> None:
    result = parser.parse_text_file(2, SAMPLES_DIR / "sample.md", "md")

    _assert_valid_shape(result)
    assert result["format"] == "markdown"
    block_types = [block["type"] for block in result["blocks"]]
    assert "heading" in block_types
    assert "code" in block_types
    assert "def hello():" in "\n".join(_block_texts(result))


def test_empty_file_is_successful_empty_parse(tmp_path: Path) -> None:
    sample = tmp_path / "empty.txt"
    sample.write_bytes(b"")

    result = parser.parse_text_file(3, sample, "txt")

    _assert_valid_shape(result)
    assert result["blocks"] == []
    assert result["metadata"]["original_size"] == 0
    assert result["metadata"]["truncated"] is False


def test_gbk_encoded_text_decodes_without_replacement(tmp_path: Path) -> None:
    sample = tmp_path / "gbk.txt"
    sample.write_bytes("中文段落\n\n第二段".encode("gbk"))

    result = parser.parse_text_file(4, sample, "txt")

    _assert_valid_shape(result)
    assert result["metadata"]["encoding"] in {"gb18030", "gbk"}
    assert _block_texts(result) == ["中文段落", "第二段"]


def test_large_file_is_truncated_with_metadata(tmp_path: Path) -> None:
    sample = tmp_path / "large.txt"
    sample.write_bytes(b"a" * 32)

    result = parser.parse_text_file(5, sample, "txt", max_bytes=10)

    _assert_valid_shape(result)
    assert result["metadata"]["original_size"] == 32
    assert result["metadata"]["max_bytes"] == 10
    assert result["metadata"]["truncated"] is True
    assert result["metadata"]["parsed_bytes"] == 14
    assert _block_texts(result) == ["a" * 14]


def test_unsupported_format_raises() -> None:
    try:
        parser.parse_text_bytes(6, b"hello", "bin")
    except parser.TextParseError:
        return
    raise AssertionError("unsupported text format should fail")
