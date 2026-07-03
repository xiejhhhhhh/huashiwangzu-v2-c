"""Sandbox tests for csv-parser.

The sandbox imports the module backend parser directly and validates real sample
files plus edge cases that previously drifted from the production parser.
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
MODULE_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("JWT_SECRET", "csv-parser-sandbox-test-secret")

from app.core.exceptions import ValidationError  # noqa: E402


def _load_router_module():
    router_path = MODULE_ROOT / "backend" / "router.py"
    spec = importlib.util.spec_from_file_location("csv_parser_router", router_path)
    assert spec and spec.loader, f"Cannot load router module from {router_path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


csv_router = _load_router_module()


def _validate_shape(result: dict[str, object]) -> list[dict[str, object]]:
    assert result["file_id"] == 0
    assert result["resources"] == []
    blocks = result["blocks"]
    assert isinstance(blocks, list)
    for block in blocks:
        assert isinstance(block, dict)
        assert set(("type", "text", "page", "resource_ref")).issubset(block)
    return blocks


def _block_text(result: dict[str, object]) -> str:
    blocks = _validate_shape(result)
    return "\n".join(str(block["text"]) for block in blocks)


def test_real_sample_csv_parses_with_unified_blocks() -> None:
    result = csv_router.parse_csv_path(0, SAMPLES_DIR / "sample.csv", "csv")
    text = _block_text(result)

    assert result["format"] == "csv"
    assert "表格：2列 x 2行数据" in text
    assert "表头：name | score" in text
    assert "行2：alpha | 1" in text
    assert "行3：beta | 2" in text


def test_real_sample_tsv_uses_tab_delimiter() -> None:
    result = csv_router.parse_csv_path(0, SAMPLES_DIR / "sample.tsv", "tsv")
    text = _block_text(result)

    assert result["format"] == "tsv"
    assert "分隔符：tab" in text
    assert "行2：alpha | 1" in text


def test_semicolon_and_gbk_content_parse(tmp_path: Path) -> None:
    sample = tmp_path / "gbk_semicolon.csv"
    sample.write_bytes("姓名;分数\n张三;98\n李四;87\n".encode("gbk"))

    result = csv_router.parse_csv_path(0, sample, "csv")
    text = _block_text(result)

    assert "分隔符：semicolon" in text
    assert "表头：姓名 | 分数" in text
    assert "行3：李四 | 87" in text


def test_empty_file_returns_explicit_empty_table(tmp_path: Path) -> None:
    sample = tmp_path / "empty.csv"
    sample.write_text("", encoding="utf-8")

    result = csv_router.parse_csv_path(0, sample, "csv")
    blocks = _validate_shape(result)

    assert len(blocks) == 1
    assert "空CSV/TSV文件：0列 x 0行数据" in str(blocks[0]["text"])


def test_large_file_output_is_bounded(tmp_path: Path) -> None:
    sample = tmp_path / "large.csv"
    rows = ["name,score", *(f"row{i},{i}" for i in range(1, 1006))]
    sample.write_text("\n".join(rows), encoding="utf-8")

    result = csv_router.parse_csv_path(0, sample, "csv")
    text = _block_text(result)
    blocks = _validate_shape(result)

    assert "表格：2列 x 1005行数据" in text
    assert "仅输出前 1000 行，剩余 5 行已省略。" in text
    assert len(blocks) == 22
    assert "row1000 | 1000" in text
    assert "row1001 | 1001" not in text


def test_malformed_csv_raises_validation_error(tmp_path: Path) -> None:
    sample = tmp_path / "broken.csv"
    sample.write_text('name,score\n"unterminated,1\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        csv_router.parse_csv_path(0, sample, "csv")


def test_invalid_file_id_rejected_before_runner() -> None:
    with pytest.raises(ValidationError):
        csv_router._coerce_file_id({"file_id": "not-a-number"})
    with pytest.raises(ValidationError):
        csv_router._coerce_file_id({"file_id": 0})


def main() -> None:
    sample_result = csv_router.parse_csv_path(0, SAMPLES_DIR / "sample.csv", "csv")
    sample_text = _block_text(sample_result)
    assert "表格：2列 x 2行数据" in sample_text

    tsv_result = csv_router.parse_csv_path(0, SAMPLES_DIR / "sample.tsv", "tsv")
    tsv_text = _block_text(tsv_result)
    assert "分隔符：tab" in tsv_text

    print("PASS: csv-parser sandbox samples parsed with production parser")


if __name__ == "__main__":
    main()
