"""Sandbox contract test for the email-parser module."""

from __future__ import annotations

import importlib.util
import sys
from email.message import EmailMessage
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PARSER_PATH = REPO_ROOT / "modules" / "email-parser" / "backend" / "parser.py"
SAMPLE = Path(__file__).resolve().parent / "samples" / "sample.eml"


def load_parser() -> ModuleType:
    spec = importlib.util.spec_from_file_location("email_parser_backend_parser_under_test", PARSER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load parser from {PARSER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_success(result: dict[str, Any], *, expected_resources: int = 0) -> None:
    assert result["file_id"] == 1
    assert result["format"] == "email"
    assert isinstance(result["blocks"], list)
    assert result["blocks"], "email parsing should produce content blocks"
    assert isinstance(result["resources"], list)
    assert isinstance(result["resource_diagnostics"], list)

    for block in result["blocks"]:
        assert set(("type", "text", "page", "resource_ref")).issubset(block)
        assert block["type"] in {"heading", "paragraph"}
        assert isinstance(block["text"], str)

    assert len(result["resources"]) == expected_resources
    for resource in result["resources"]:
        assert set((
            "id",
            "type",
            "resource_type",
            "mime_type",
            "filename",
            "description",
            "file_storage_id",
            "text_desc",
            "_bytes_b64",
        )).issubset(resource)
        assert resource["filename"]
        assert resource["description"]


def write_message(message: EmailMessage) -> Path:
    handle = NamedTemporaryFile(suffix=".eml", delete=False)
    path = Path(handle.name)
    handle.close()
    path.write_bytes(message.as_bytes())
    return path


def parse_sample(parser: ModuleType) -> None:
    assert SAMPLE.exists(), f"Sample not found: {SAMPLE}"
    result = parser.parse_email_file(1, SAMPLE, "eml")
    validate_success(result)
    assert any("Parser sample" in block["text"] for block in result["blocks"])
    assert any("This is a sample email body." in block["text"] for block in result["blocks"])


def parse_html_fallback(parser: ModuleType) -> None:
    message = EmailMessage()
    message["From"] = "Alice <alice@example.com>"
    message["To"] = "Bob <bob@example.com>"
    message["Subject"] = "HTML only"
    message.set_content("<html><body><h1>Hello</h1><p>HTML body</p><script>bad()</script></body></html>", subtype="html")
    path = write_message(message)
    try:
        result = parser.parse_email_file(1, path, "eml")
    finally:
        path.unlink(missing_ok=True)
    validate_success(result)
    body = "\n".join(block["text"] for block in result["blocks"])
    assert "Hello" in body
    assert "HTML body" in body
    assert "bad()" not in body


def parse_attachment(parser: ModuleType) -> None:
    message = EmailMessage()
    message["From"] = "Alice <alice@example.com>"
    message["To"] = "Bob <bob@example.com>"
    message["Subject"] = "Attachment"
    message.set_content("See attachment.")
    message.add_attachment(
        b"attachment bytes",
        maintype="application",
        subtype="octet-stream",
        filename="report.bin",
    )
    path = write_message(message)
    try:
        result = parser.parse_email_file(1, path, "eml")
    finally:
        path.unlink(missing_ok=True)
    validate_success(result, expected_resources=1)
    resource = result["resources"][0]
    assert resource["filename"] == "report.bin"
    assert resource["type"] == "attachment"
    assert resource["_bytes_b64"]
    assert any(block["resource_ref"] == resource["id"] for block in result["blocks"])


def reject_bad_eml(parser: ModuleType) -> None:
    with NamedTemporaryFile(suffix=".eml") as invalid:
        invalid_path = Path(invalid.name)
        invalid_path.write_bytes(b"not a structured email")
        try:
            parser.parse_email_file(1, invalid_path, "eml")
        except parser.EmailParseError:
            pass
        else:
            raise AssertionError("bad EML bytes should raise EmailParseError")


def run_sandbox_contract() -> None:
    print("=" * 60)
    print("email-parser sandbox test")
    print("=" * 60)
    parser = load_parser()
    parse_sample(parser)
    parse_html_fallback(parser)
    parse_attachment(parser)
    reject_bad_eml(parser)
    print("PASS: email-parser sandbox test")


def main() -> None:
    run_sandbox_contract()


def test_sandbox_contract() -> None:
    run_sandbox_contract()


if __name__ == "__main__":
    main()
