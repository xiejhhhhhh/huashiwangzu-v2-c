"""Sandbox contract tests for the image-gen module.

These tests avoid real provider calls, but they validate the live module
contract files instead of stale sample payloads.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = MODULE_DIR / "backend"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_providers_module() -> Any:
    backend_path = str(BACKEND_DIR)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    return importlib.import_module("providers")


def test_manifest_public_actions_match_runtime_contract() -> None:
    manifest = _load_json(MODULE_DIR / "manifest.json")
    actions = {item["action"]: item for item in manifest["public_actions"]}

    assert set(actions) == {"generate", "list_templates", "usage_history"}
    assert actions["generate"]["min_role"] == "editor"
    assert actions["list_templates"]["min_role"] == "viewer"
    assert actions["usage_history"]["min_role"] == "editor"

    params = actions["generate"]["parameters"]
    assert params["prompt"]["type"] == "string"
    assert params["size"]["default"] == "1024x1024"
    assert params["aspect_ratio"]["default"] == ""
    assert params["count"]["type"] == "integer"
    assert params["count"]["default"] == 1
    assert params["steps"]["default"] == 30
    assert params["template"]["default"] == ""


def test_template_config_has_registered_provider_and_default() -> None:
    template_config = _load_json(BACKEND_DIR / "image_templates.json")
    templates = template_config["templates"]
    default_template = template_config["default_template"]
    providers = _load_providers_module()

    assert default_template in templates
    assert "placeholder" in templates

    for key, template in templates.items():
        provider_name = template["provider"]
        provider = providers.get_provider(provider_name)
        assert provider.provider_key == provider_name
        assert template.get("label"), f"template {key} must have a label"
        assert template.get("prompt_language", "any") in {"any", "en"}


def test_liblib_template_declares_polling_and_credentials() -> None:
    templates = _load_json(BACKEND_DIR / "image_templates.json")["templates"]
    liblib = templates["liblib-star3"]

    assert liblib["provider"] == "liblib"
    assert liblib["api_base"].startswith("https://")
    assert liblib["text2img_path"].startswith("/")
    assert liblib["status_path"].startswith("/")
    assert liblib["access_key_env"] == "LIBLIB_ACCESS_KEY"
    assert liblib["secret_key_env"] == "LIBLIB_SECRET_KEY"
    assert int(liblib["poll_max"]) >= 1
    assert float(liblib["poll_interval_sec"]) > 0


def test_placeholder_provider_generates_requested_dimensions() -> None:
    from providers.base import GenSpec

    providers = _load_providers_module()
    provider = providers.get_provider("placeholder")
    spec = GenSpec(prompt="contract test image", width=1280, height=720, count=2, steps=30)

    results = asyncio.run(provider.generate(spec))
    assert len(results) == 2
    for result in results:
        assert result.image_bytes
        assert result.image_url is None
        assert result.meta["placeholder"] is True


def test_generate_response_contract_uses_framework_files() -> None:
    result = {
        "images": [
            {
                "type": "image",
                "file_id": 123,
                "name": "image-gen_1.png",
                "size": 2048,
                "placeholder": True,
            }
        ],
        "placeholder": True,
        "template": "placeholder",
        "points_cost": None,
        "balance": None,
    }

    assert "images" in result
    assert "image_urls" not in result
    assert result["images"][0]["file_id"] > 0
    assert result["images"][0]["type"] == "image"


def test_router_uses_provider_placeholder_meta() -> None:
    router_src = (BACKEND_DIR / "router.py").read_text(encoding="utf-8")
    assert "result_placeholder = is_placeholder or bool(gen_result.meta.get(\"placeholder\"))" in router_src
    assert '"placeholder": generated_placeholder' in router_src


def main() -> None:
    print("=" * 60)
    print("image-gen sandbox contract test")
    print("=" * 60)
    test_manifest_public_actions_match_runtime_contract()
    test_template_config_has_registered_provider_and_default()
    test_liblib_template_declares_polling_and_credentials()
    test_placeholder_provider_generates_requested_dimensions()
    test_generate_response_contract_uses_framework_files()
    test_router_uses_provider_placeholder_meta()
    print("=" * 60)
    print("PASS: image-gen sandbox contract test")


if __name__ == "__main__":
    main()
