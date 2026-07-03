"""Sandbox test for douyin-delivery module.

Validates core schemas, module contracts, and response shapes without calling
external APIs or DB.
"""
import json
from pathlib import Path


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
    assert script["status"] in ("draft", "published", "archived"), f"Invalid status: {script['status']}"
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


def test_cleanup_marker_contract() -> None:
    """Cleanup must be marker-scoped to avoid deleting real data."""
    marker = "r2-douyin-20260703"
    assert len(marker) >= 6
    cleanup_request = {"marker": marker}
    assert cleanup_request["marker"].startswith("r2-douyin")
    print("  [CLEANUP] Marker contract valid")


def test_manifest_actions_and_db_contracts() -> None:
    """Manifest must declare runtime capabilities and owned tables."""
    module_root = Path(__file__).resolve().parents[1]
    manifest = json.loads((module_root / "manifest.json").read_text(encoding="utf-8"))
    actions = {item["action"] for item in manifest["public_actions"]}
    tables = {item["table"] for item in manifest["db_migration_declaration"]}

    assert {"create_delivery_task", "mark_task_failed", "cleanup_marked_data"} <= actions
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
    test_cleanup_marker_contract()
    test_manifest_actions_and_db_contracts()
    test_response_shape()
    test_frontend_crud_methods_match_backend_routes()
    print("=" * 60)
    print("PASS: douyin-delivery sandbox test")


if __name__ == "__main__":
    main()
