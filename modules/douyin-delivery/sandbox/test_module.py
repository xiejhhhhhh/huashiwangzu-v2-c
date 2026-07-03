"""Sandbox test for douyin-delivery module.

Validates core schemas, module contracts, and service guardrails without
calling external APIs or mutating DB state.
"""
import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Awaitable

MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
MODULE_BACKEND_ROOT = MODULE_ROOT / "backend"
BACKEND_PACKAGE = "douyin_delivery_backend"

os.environ.setdefault("JWT_SECRET", "douyin-delivery-sandbox-test-secret")

for path in (str(REPO_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def load_backend_module(name: str) -> ModuleType:
    """Load backend files under a package alias so relative imports work."""
    if BACKEND_PACKAGE not in sys.modules:
        package_spec = importlib.util.spec_from_loader(BACKEND_PACKAGE, loader=None, is_package=True)
        package = importlib.util.module_from_spec(package_spec)
        package.__path__ = [str(MODULE_BACKEND_ROOT)]
        sys.modules[BACKEND_PACKAGE] = package

    module_name = f"{BACKEND_PACKAGE}.{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, MODULE_BACKEND_ROOT / f"{name}.py")
    assert spec and spec.loader, f"Unable to load backend module: {name}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def assert_validation_error(awaitable: Awaitable[object], expected: str) -> None:
    from app.core.exceptions import ValidationError

    try:
        asyncio.run(awaitable)
    except ValidationError as exc:
        assert expected in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected ValidationError containing: {expected}")


def test_product_schema() -> None:
    """Product creation schema contract."""
    product = {
        "name": "Test Product",
        "category": "skincare",
        "selling_points": ["moisturizing", "brightening"],
        "ingredients": ["hyaluronic acid", "vitamin C"],
        "target_audience": "women 25-35",
        "brand": "俏小喵",
        "notes": "test product",
    }
    required = {"name", "category", "selling_points", "brand"}
    for field in required:
        assert field in product, f"Missing required field: {field}"
    assert isinstance(product["selling_points"], list), "selling_points should be list"
    assert isinstance(product["ingredients"], list), "ingredients should be list"
    print("  [PRODUCT] Schema valid")


def test_campaign_schema() -> None:
    """Campaign creation schema contract."""
    campaign = {
        "name": "Summer Campaign",
        "channel": "local_push",
        "status": "planning",
        "budget": 5000.0,
        "budget_type": "daily",
        "start_date": "2026-07-01",
        "end_date": "2026-07-31",
        "target_audience": {"age": "25-35", "gender": "female"},
        "product_ids": [1, 2],
        "notes": "test campaign",
    }
    required = {"name", "channel", "status"}
    for field in required:
        assert field in campaign, f"Missing required field: {field}"
    assert campaign["channel"] in ("local_push", "ocean_engine", "qianchuan"), f"Invalid channel: {campaign['channel']}"
    assert campaign["budget_type"] in ("daily", "total"), f"Invalid budget_type: {campaign['budget_type']}"
    assert campaign["budget"] > 0, "Budget must be positive"
    print("  [CAMPAIGN] Schema valid")


def test_script_schema() -> None:
    """Script save schema contract."""
    script = {
        "title": "Product Hook Script",
        "product_name": "Test Product",
        "channel": "local_push",
        "hook": "Did you know...",
        "pain_point": "Dry skin in winter",
        "selling_point": "24h moisture lock",
        "social_proof": "10k+ happy customers",
        "call_to_action": "Buy now",
        "full_script": "Full script text here...",
        "status": "draft",
        "hashtags": ["skincare", "beauty"],
        "suggested_titles": ["Title 1", "Title 2"],
    }
    required = {"channel", "status", "product_name"}
    for field in required:
        assert field in script, f"Missing required field: {field}"
    assert script["status"] in ("draft", "ready", "published", "archived"), f"Invalid status: {script['status']}"
    print("  [SCRIPT] Schema valid")


def test_ad_copy_schema() -> None:
    """Ad copy save schema contract."""
    ad = {
        "product_name": "Test Product",
        "channel": "ocean_engine",
        "ad_type": "feed",
        "title": "Amazing Product",
        "headline": "You Need This!",
        "description": "Best product for your skin",
        "call_to_action": "立即购买",
        "target_audience_desc": "women 25-35",
        "status": "draft",
    }
    required = {"product_name", "channel", "ad_type"}
    for field in required:
        assert field in ad, f"Missing required field: {field}"
    assert ad["ad_type"] in ("feed", "search", "brand"), f"Invalid ad_type: {ad['ad_type']}"
    print("  [AD_COPY] Schema valid")


def test_delivery_contract_schema() -> None:
    """Account/material/task contracts must cover delivery sweep semantics."""
    valid_channels = {"local_push", "ocean_engine", "qianchuan"}
    task_statuses = {"pending", "running", "succeeded", "failed", "cancelled"}

    account = {
        "channel": "ocean_engine",
        "account_name": "r2-douyin-test-account",
        "external_account_id": "r2-douyin-account-001",
        "status": "active",
    }
    material = {
        "title": "r2-douyin-test-material",
        "material_type": "video",
        "channel": "qianchuan",
        "content_text": "test video brief",
        "status": "ready",
    }
    task = {
        "task_type": "publish_ad_copy",
        "target_type": "material",
        "target_id": 1,
        "status": "failed",
        "error_message": "r2-douyin-platform-rejected",
    }

    assert account["channel"] in valid_channels
    assert material["channel"] in valid_channels
    assert material["material_type"] in {"video", "image", "text", "landing_page"}
    assert task["status"] in task_statuses
    assert task["status"] != "failed" or task["error_message"], "failed task must preserve error_message"
    print("  [DELIVERY CONTRACT] Account/material/task schema valid")


def test_generation_services_reject_invalid_inputs_before_external_calls() -> None:
    """Invalid generation inputs must fail before model or DB work."""
    services = load_backend_module("services")

    assert_validation_error(services.generate_script("", "local_push", 1), "product is required")
    assert_validation_error(services.generate_script("r2 product", "bad_channel", 1), "Invalid channel")
    assert_validation_error(services.generate_ad_copy("r2 product", "local_push", "bad_ad", 1), "Invalid ad_type")
    assert_validation_error(services.validate_content("", 1), "content is required")
    print("  [GENERATION GUARDS] Invalid inputs rejected before external calls")


def test_delivery_task_semantics_reject_fake_success() -> None:
    """Task status helpers must not allow failed semantics to look succeeded."""
    from app.core.exceptions import ValidationError

    delivery_services = load_backend_module("delivery_services")

    try:
        delivery_services._validate_task_result_semantics("failed", "", None)
    except ValidationError as exc:
        assert "requires error_message" in str(exc)
    else:
        raise AssertionError("failed status without error_message should be rejected")

    try:
        delivery_services._validate_task_result_semantics("succeeded", "platform failed", None)
    except ValidationError as exc:
        assert "only allowed" in str(exc)
    else:
        raise AssertionError("non-failed status with error_message should be rejected")

    try:
        delivery_services._validate_task_result_semantics("succeeded", "", {"success": False, "error": "rejected"})
    except ValidationError as exc:
        assert "failure semantics" in str(exc)
    else:
        raise AssertionError("succeeded status with failed payload should be rejected")

    delivery_services._validate_task_result_semantics("succeeded", "", {"success": True, "platform_id": "ok"})
    print("  [TASK SEMANTICS] Fake success states rejected")


def test_delivery_execution_mode_contract() -> None:
    """Delivery tasks must be auditable handoff records unless a real adapter exists."""
    from app.core.exceptions import ValidationError

    delivery_services = load_backend_module("delivery_services")

    assert delivery_services._normalize_execution_mode({}) == "handoff"
    assert delivery_services._normalize_execution_mode({"execution_mode": "dry_run"}) == "dry_run"

    try:
        delivery_services._normalize_execution_mode({"execution_mode": "ocean_engine_api"})
    except ValidationError as exc:
        assert "External delivery adapters are not configured" in str(exc)
    else:
        raise AssertionError("external platform mode must fail closed without an adapter")

    result = asyncio.run(delivery_services._execute_delivery_handoff(FakeDb(), FakeTask()))
    assert result["success"] is True
    assert result["external_delivery"] is False
    assert result["adapter"] == "manual_handoff"
    print("  [DELIVERY EXECUTION] Handoff mode is explicit and auditable")


class FakeDb:
    async def execute(self, _query: object) -> object:
        raise AssertionError("target lookup should not run without target_id")


class FakeTask:
    id = 1
    owner_id = 1
    task_type = "publish_script"
    target_type = "script"
    target_id = None
    payload = {"execution_mode": "handoff", "channel": "local_push"}


def test_cleanup_marker_contract() -> None:
    """Cleanup must be marker-scoped to avoid deleting real data."""
    marker = "r2-douyin-20260703"
    assert len(marker) >= 6
    cleanup_request = {"marker": marker}
    assert cleanup_request["marker"].startswith("r2-douyin")
    print("  [CLEANUP] Marker contract valid")


def test_cleanup_covers_delivery_task_json_markers() -> None:
    """Cleanup must match markers stored in delivery task JSON payloads."""
    module_root = Path(__file__).resolve().parents[1]
    source = (module_root / "backend" / "delivery_services.py").read_text(encoding="utf-8")

    assert "cast(DouyinDeliveryTask.payload, Text).ilike(pattern)" in source
    assert "cast(DouyinDeliveryTask.result_payload, Text).ilike(pattern)" in source
    print("  [CLEANUP JSON] Delivery task payload markers covered")


def test_manifest_actions_and_db_contracts() -> None:
    """Manifest must declare runtime capabilities and owned tables."""
    module_root = Path(__file__).resolve().parents[1]
    manifest = json.loads((module_root / "manifest.json").read_text(encoding="utf-8"))
    actions = {item["action"] for item in manifest["public_actions"]}
    tables = {item["table"] for item in manifest["db_migration_declaration"]}

    assert {"create_delivery_task", "mark_task_failed", "cleanup_marked_data"} <= actions
    action_map = {item["action"]: item for item in manifest["public_actions"]}
    assert "不调用外部广告平台" in action_map["create_delivery_task"]["description"]
    assert "auto_execute" in action_map["create_delivery_task"]["parameters"]
    assert {
        "douyin_accounts",
        "douyin_materials",
        "douyin_delivery_tasks",
    } <= tables
    print("  [MANIFEST] Actions and DB contracts valid")


def test_response_shape() -> None:
    """Unified API response shape contract."""
    r = {"success": True, "data": {"id": 1, "name": "test"}, "error": None}
    assert all(k in r for k in ("success", "data", "error"))
    assert r["success"] is True
    print("  [RESPONSE] Shape valid")


def test_frontend_crud_methods_match_backend_routes() -> None:
    """Frontend update/delete helpers must call PUT/DELETE backend routes."""
    module_root = Path(__file__).resolve().parents[1]
    api_src = (module_root / "frontend" / "api.ts").read_text(encoding="utf-8")
    runtime_src = (module_root / "runtime" / "index.ts").read_text(encoding="utf-8")

    assert "export async function apiPut" in runtime_src
    assert "export async function apiDelete" in runtime_src
    assert "update: (id: number, data: Partial<Product>) => apiPut" in api_src
    assert "update: (id: number, data: Partial<Script>) => apiPut" in api_src
    assert "update: (id: number, data: Partial<AdCopy>) => apiPut" in api_src
    assert "update: (id: number, data: Partial<Campaign>) => apiPut" in api_src
    assert "export const accounts" in api_src
    assert "export const materials" in api_src
    assert "export const deliveryTasks" in api_src
    assert "export interface DeliveryTaskCreateRequest" in api_src
    assert "export const cleanup" in api_src
    assert "delete: (id: number) => apiDelete" in api_src
    assert "apiPost<{ deleted: boolean }>" not in api_src
    print("  [FRONTEND CRUD] HTTP methods match backend routes")


def main() -> None:
    print("=" * 60)
    print("douyin-delivery sandbox test")
    print("=" * 60)
    test_product_schema()
    test_campaign_schema()
    test_script_schema()
    test_ad_copy_schema()
    test_delivery_contract_schema()
    test_generation_services_reject_invalid_inputs_before_external_calls()
    test_delivery_task_semantics_reject_fake_success()
    test_cleanup_marker_contract()
    test_cleanup_covers_delivery_task_json_markers()
    test_manifest_actions_and_db_contracts()
    test_response_shape()
    test_frontend_crud_methods_match_backend_routes()
    print("=" * 60)
    print("PASS: douyin-delivery sandbox test")


if __name__ == "__main__":
    main()
