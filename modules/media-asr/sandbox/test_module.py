"""Sandbox contract tests for the media-asr production module.

The tests import the real router/service code and stub only DB/media/model
boundaries, so sandbox failures track production contract drift without
touching framework uploads or running expensive ASR.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_ROOT = REPO_ROOT / "modules" / "media-asr"
BACKEND_DIR = MODULE_ROOT / "backend"
MANIFEST_PATH = MODULE_ROOT / "manifest.json"
FRAMEWORK_BACKEND_DIR = REPO_ROOT / "backend"

if str(FRAMEWORK_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_BACKEND_DIR))

os.environ.setdefault("JWT_SECRET", "media-asr-sandbox-test-secret")

from app.core.exceptions import ValidationError
from app.services import module_registry


def load_router(capture: list[dict] | None = None):
    package_name = "media_asr_sandbox_backend"
    package = types.ModuleType(package_name)
    package.__path__ = [str(BACKEND_DIR)]  # type: ignore[attr-defined]
    sys.modules[package_name] = package

    old_register = module_registry.register_capability

    def fake_register_capability(module: str, action: str, handler: Callable[..., Any], **kwargs: Any) -> None:
        if capture is not None:
            capture.append({
                "module": module,
                "action": action,
                "handler": handler,
                "min_role": kwargs.get("min_role"),
                "parameters": kwargs.get("parameters", {}),
            })

    module_registry.register_capability = fake_register_capability
    try:
        spec = importlib.util.spec_from_file_location(
            f"{package_name}.router",
            BACKEND_DIR / "router.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{package_name}.router"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        module_registry.register_capability = old_register


def load_audio_service():
    package_name = "media_asr_sandbox_backend"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(BACKEND_DIR)]  # type: ignore[attr-defined]
        sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(
        f"{package_name}.services.audio_service",
        BACKEND_DIR / "services" / "audio_service.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{package_name}.services.audio_service"] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_public_actions_match_registered_capabilities() -> None:
    captured: list[dict] = []
    load_router(captured)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    public_actions = {item["action"]: item for item in manifest["public_actions"]}
    registered = {item["action"]: item for item in captured if item["module"] == "media-asr"}

    assert set(public_actions) == {"extract_audio", "transcribe_audio", "transcribe_video"}
    assert set(public_actions) == set(registered)
    for action, item in registered.items():
        assert item["min_role"] == public_actions[action]["min_role"] == "editor"
        assert set(item["parameters"]) == set(public_actions[action]["parameters"])


def test_production_validators_reject_bad_inputs() -> None:
    service = load_audio_service()

    assert service.validate_sample_rate(16000) == 16000
    try:
        service.validate_sample_rate(11025)
    except ValidationError:
        pass
    else:
        raise AssertionError("11025 must not be accepted by production validator")

    assert service.validate_whisper_model("tiny") == "tiny"
    try:
        service.validate_whisper_model("unknown-model")
    except ValidationError:
        pass
    else:
        raise AssertionError("unknown Whisper model must be rejected before ASR")

    assert service.normalize_language(" zh ") == "zh"
    assert service.normalize_language("") is None


def test_bad_capability_params_fail_before_file_runner() -> None:
    router = load_router()
    calls = 0

    async def fail_if_called(*_args: Any, **_kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("file runner should not run for invalid params")

    router.run_uploaded_file_capability = fail_if_called

    for params in (
        {"file_id": "abc"},
        {"file_id": 0},
        {"file_id": 1, "sample_rate": "fast"},
        {"file_id": 1, "folder_id": -1},
    ):
        try:
            asyncio.run(router._extract_audio(params, "user:1"))
        except ValidationError:
            pass
        else:
            raise AssertionError(f"invalid params were accepted: {params}")

    try:
        asyncio.run(router._transcribe_audio({"file_id": 1, "model": "remote/huge"}, "user:1"))
    except ValidationError:
        pass
    else:
        raise AssertionError("unknown model should fail before file runner")

    assert calls == 0


def test_extract_audio_uses_framework_file_runner_and_returns_contract() -> None:
    router = load_router()
    observed: dict[str, Any] = {}

    async def fake_extract(_full_path: Path, tmp_path: Path, sample_rate: int, audio_format: str) -> dict:
        observed["sample_rate"] = sample_rate
        observed["audio_format"] = audio_format
        return {
            "audio_path": tmp_path / f"audio.{audio_format}",
            "duration_seconds": 2.5,
            "size": 32000,
        }

    async def fake_upload(_path: Path, filename: str, owner_id: int, folder_id: int | None) -> int:
        observed["filename"] = filename
        observed["owner_id"] = owner_id
        observed["folder_id"] = folder_id
        return 9001

    async def fake_file_runner(params: dict, caller: str, allowed_exts: set[str], handler: Callable[..., Any]) -> dict:
        observed["params"] = params
        observed["caller"] = caller
        observed["allowed_exts"] = allowed_exts
        file = SimpleNamespace(name="clip.mp4")
        return await handler(params["file_id"], file, Path("/tmp/clip.mp4"), "mp4")

    router.extract_audio_from_video = fake_extract
    router._upload_with_conflict_retry = fake_upload
    router.run_uploaded_file_capability = fake_file_runner

    result = asyncio.run(router._extract_audio({
        "file_id": "42",
        "sample_rate": "16000",
        "audio_format": "wav",
        "save_file": True,
        "folder_id": "7",
    }, "user:123"))

    assert observed["params"]["file_id"] == 42
    assert observed["caller"] == "user:123"
    assert observed["allowed_exts"] == router.VIDEO_EXTS
    assert observed["sample_rate"] == 16000
    assert observed["audio_format"] == "wav"
    assert observed["owner_id"] == 123
    assert observed["folder_id"] == 7
    assert observed["filename"] == "clip-audio.wav"
    assert result["source_file_id"] == 42
    assert result["audio_file_id"] == 9001
    assert result["duration_seconds"] == 2.5
    assert result["resources"] == [{"id": 1, "type": "video", "file_storage_id": 42}]


def main() -> None:
    tests = [
        test_manifest_public_actions_match_registered_capabilities,
        test_production_validators_reject_bad_inputs,
        test_bad_capability_params_fail_before_file_runner,
        test_extract_audio_uses_framework_file_runner_and_returns_contract,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print("PASS: media-asr sandbox production contract tests")


if __name__ == "__main__":
    main()
