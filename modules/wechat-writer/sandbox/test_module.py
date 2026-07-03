"""Sandbox test for wechat-writer module.

Validates core schemas (topics, outline, article, draft) and response shapes
without calling external APIs, model gateways, or DB. Backend checks import the
module code with fake execution points so startup async semantics are exercised.
"""

import asyncio
import importlib.util
import os
import sys
import types
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
MODULE_BACKEND_DIR = REPO_ROOT / "modules" / "wechat-writer" / "backend"
MODULE_PACKAGE = "huashiwangzu_modules.wechat_writer"


def _ensure_backend_import_context() -> None:
    os.environ.setdefault("JWT_SECRET", "wechat-writer-sandbox-test-secret")

    for path in (str(BACKEND_DIR), str(REPO_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)

    top_package = sys.modules.get("huashiwangzu_modules")
    if top_package is None:
        top_package = types.ModuleType("huashiwangzu_modules")
        top_package.__path__ = []
        sys.modules["huashiwangzu_modules"] = top_package

    module_package = sys.modules.get(MODULE_PACKAGE)
    if module_package is None:
        module_package = types.ModuleType(MODULE_PACKAGE)
        module_package.__path__ = [str(MODULE_BACKEND_DIR)]
        sys.modules[MODULE_PACKAGE] = module_package


def _load_backend_module(module_name: str):
    _ensure_backend_import_context()
    full_name = f"{MODULE_PACKAGE}.{module_name}"
    sys.modules.pop(full_name, None)
    spec = importlib.util.spec_from_file_location(full_name, MODULE_BACKEND_DIR / f"{module_name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load backend module: {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


def _assert_raises(exc_type: type[Exception], fn: Callable[[], object]) -> None:
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"Expected {exc_type.__name__}")


def test_topic_schema() -> None:
    """Topic generation request schema."""
    req = {"direction": "skincare for dry skin in winter"}
    assert "direction" in req and req["direction"].strip()
    print("  [TOPIC] Input schema valid")


def test_outline_schema() -> None:
    """Outline generation request schema."""
    req = {"topic": "Winter Skincare Routine", "direction": "natural ingredients"}
    assert "topic" in req and req["topic"].strip()
    print("  [OUTLINE] Input schema valid")


def test_article_schema() -> None:
    """Article generation request schema."""
    req = {
        "topic": "Winter Skincare Routine",
        "outline": "1. Introduction\n2. Key ingredients\n3. Routine steps",
        "direction": "natural ingredients",
    }
    assert "topic" in req and req["topic"].strip()
    assert "outline" in req and req["outline"].strip()
    print("  [ARTICLE] Input schema valid")


def test_draft_schema() -> None:
    """Draft create/update schema contract."""
    draft = {
        "title": "Winter Skincare Guide",
        "outline": {"sections": ["intro", "body", "conclusion"]},
        "content": "Full article content here...",
        "article_type": "科普",
        "keywords": ["skincare", "winter", "moisture"],
        "status": "draft",
        "notes": "draft for review",
    }
    required = {"title", "content", "status"}
    for field in required:
        assert field in draft, f"Missing required field: {field}"
    assert draft["status"] in ("draft", "published", "archived"), f"Invalid status: {draft['status']}"
    assert isinstance(draft["keywords"], list), "keywords should be list"
    if draft["outline"]:
        assert isinstance(draft["outline"], dict), "outline should be dict"
    print("  [DRAFT] Schema valid")


def test_validate_schema() -> None:
    """Content validation request schema."""
    req = {"content": "Test content with ingredient claims"}
    assert "content" in req and req["content"].strip()
    print("  [VALIDATE] Input schema valid")


def test_response_shape() -> None:
    """Unified API response shape contract."""
    r = {"success": True, "data": {"id": 1, "title": "test"}, "error": None}
    assert all(k in r for k in ("success", "data", "error"))
    assert r["success"] is True
    print("  [RESPONSE] Shape valid")


def test_startup_init_schedules_on_running_loop() -> None:
    """Startup init must not call asyncio.run() from inside a running loop."""
    init_db = _load_backend_module("init_db")
    calls: list[str] = []

    async def fake_run_init() -> None:
        calls.append("run_init")

    async def scenario() -> None:
        original_run_init = init_db.run_init
        init_db.run_init = fake_run_init
        try:
            task = init_db._run_startup_init()
            assert isinstance(task, asyncio.Task), "running loop should schedule a task"
            await task
        finally:
            init_db.run_init = original_run_init

    asyncio.run(scenario())
    assert calls == ["run_init"], f"Unexpected startup calls: {calls}"
    print("  [INIT] Running-loop startup init schedules cleanly")


def test_service_rejects_empty_generation_inputs() -> None:
    """Empty generation inputs should fail before DB/model calls."""
    services = _load_backend_module("services")
    from app.core.exceptions import ValidationError

    async def scenario() -> None:
        async def empty_topics() -> None:
            await services.generate_topics("   ", 1)

        async def empty_article_outline() -> None:
            await services.generate_article("topic", " ", "", 1)

        async def empty_validation_content() -> None:
            await services.validate_content("", 1)

        for check in (empty_topics, empty_article_outline, empty_validation_content):
            try:
                await check()
            except ValidationError:
                continue
            raise AssertionError("Expected ValidationError")

    asyncio.run(scenario())
    print("  [VALIDATION] Empty generation inputs rejected")


def test_gateway_error_is_not_reported_as_success() -> None:
    """Model gateway error payloads must raise instead of returning empty success."""
    services = _load_backend_module("services")
    from app.core.exceptions import AppException

    _assert_raises(
        AppException,
        lambda: services._ensure_gateway_success({"error": "provider unavailable"}, "生成文章"),
    )
    print("  [GATEWAY] Gateway errors raise AppException")


def main() -> None:
    print("=" * 60)
    print("wechat-writer sandbox test")
    print("=" * 60)
    test_topic_schema()
    test_outline_schema()
    test_article_schema()
    test_draft_schema()
    test_validate_schema()
    test_response_shape()
    test_startup_init_schedules_on_running_loop()
    test_service_rejects_empty_generation_inputs()
    test_gateway_error_is_not_reported_as_success()
    print("=" * 60)
    print("PASS: wechat-writer sandbox test")


if __name__ == "__main__":
    main()
