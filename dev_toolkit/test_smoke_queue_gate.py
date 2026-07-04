import asyncio

from dev_toolkit import smoke


class _FakeResponse:
    def __init__(self, status_code: int, data: dict) -> None:
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self) -> dict:
        return self._data


def test_smoke_queue_gate_is_zero_tolerance_for_new_failures() -> None:
    assert smoke._no_new_queue_failures(failed_now=10, baseline_failed=10)
    assert not smoke._no_new_queue_failures(failed_now=11, baseline_failed=10)


def test_smoke_queue_gate_ignores_external_failed_count_cleanup() -> None:
    assert smoke._new_failed_delta(failed_now=9, baseline_failed=10) == 0
    assert smoke._no_new_queue_failures(failed_now=9, baseline_failed=10)


def test_cap_ok_rejects_outer_or_inner_semantic_failure() -> None:
    assert not smoke._cap_ok({
        "status": 200,
        "data": {"success": False, "data": {"success": True}, "error": "outer failed"},
    })
    assert not smoke._cap_ok({
        "status": 200,
        "data": {"success": True, "data": {"error": "inner failed"}},
    })
    assert not smoke._cap_ok({
        "status": 500,
        "data": {"success": True, "data": {"ok": True}},
    })
    assert smoke._cap_ok({
        "status": 200,
        "data": {"success": True, "data": {"ok": True}},
    })


def test_smoke_samples_queue_before_business_steps(monkeypatch) -> None:
    order: list[str] = []

    async def fake_probe(method: str, path: str, body: dict | None = None, role: str = "admin") -> dict:
        if path == "/api/tasks/worker/status":
            order.append("queue_status")
            return {"status": 200, "data": {"data": {"failed": 7, "pending": 1, "oldest_waiting_seconds": 0}}}
        return {"status": 200, "data": {"success": True, "data": {}}}

    async def fake_group() -> None:
        order.append("business")

    async def fake_settle(baseline_pending: int = 0, timeout: int = 30) -> dict:
        order.append(f"settle:{baseline_pending}")
        return {"failed": 7, "pending": baseline_pending, "oldest_waiting_seconds": 0}

    async def fake_flush() -> int:
        return 0

    def fake_cleanup_pollution() -> dict:
        order.append("pollution_cleanup")
        return {
            "success": True,
            "selected_files": 0,
            "deleted_file_rows": 0,
            "archived_documents": 0,
            "archived_packages": 0,
            "physical_delete_errors": [],
        }

    monkeypatch.setattr(smoke, "probe", fake_probe)
    for name in ("health_check", "test_a", "test_b", "test_c", "test_d", "test_e"):
        monkeypatch.setattr(smoke, name, fake_group)
    monkeypatch.setattr(smoke, "_await_queue_settle", fake_settle)
    monkeypatch.setattr(smoke, "_flush_pending_deletions", fake_flush)
    monkeypatch.setattr(smoke, "_cleanup_test_data_pollution", fake_cleanup_pollution)
    monkeypatch.setenv("SMOKE_SKIP_UI", "1")
    smoke.results.clear()
    smoke._pending_deletions.clear()

    asyncio.run(smoke.main())

    assert order[0] == "queue_status"
    assert order.index("queue_status") < order.index("business")
    assert order.index("pollution_cleanup") > order.index("business")
    assert order.count("settle:1") == 1
    assert any(item["scenario"] == "Z3 测试数据污染清理" and item["passed"] for item in smoke.results)


def test_read_queue_state_rejects_success_false_body(monkeypatch) -> None:
    async def fake_probe(method: str, path: str, body: dict | None = None, role: str = "admin") -> dict:
        return {
            "status": 200,
            "data": {
                "success": False,
                "error": "queue broken",
                "data": {"failed": 0, "pending": 0},
            },
        }

    monkeypatch.setattr(smoke, "probe", fake_probe)

    try:
        asyncio.run(smoke._read_queue_state())
    except RuntimeError as exc:
        assert "Queue status probe failed" in str(exc)
        return
    raise AssertionError("success:false queue body must fail closed")


def test_ensure_token_caches_by_role(monkeypatch) -> None:
    smoke._TOKEN_CACHE.clear()
    login_calls: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            pass

        async def post(self, path: str, json: dict) -> _FakeResponse:
            login_calls.append(json["username"])
            return _FakeResponse(200, {"data": {"access_token": f"token-{len(login_calls)}"}})

    monkeypatch.setattr(smoke.httpx, "AsyncClient", FakeClient)

    first = asyncio.run(smoke._ensure_token("admin"))
    second = asyncio.run(smoke._ensure_token("admin"))

    assert first == "token-1"
    assert second == "token-1"
    assert login_calls == ["何焜华"]


def test_probe_refreshes_cached_token_once_on_401(monkeypatch) -> None:
    smoke._TOKEN_CACHE.clear()
    smoke._TOKEN_CACHE["admin"] = "stale"
    seen_auth: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            pass

        async def post(self, path: str, json: dict) -> _FakeResponse:
            return _FakeResponse(200, {"data": {"access_token": "fresh"}})

        async def request(self, method: str, path: str, headers: dict, **kwargs) -> _FakeResponse:
            seen_auth.append(headers["Authorization"])
            if len(seen_auth) == 1:
                return _FakeResponse(401, {"success": False, "error": "expired"})
            return _FakeResponse(200, {"success": True, "data": {"ok": True}})

    monkeypatch.setattr(smoke.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(smoke.probe("GET", "/api/health"))

    assert result["status"] == 200
    assert seen_auth == ["Bearer stale", "Bearer fresh"]
    assert smoke._TOKEN_CACHE["admin"] == "fresh"


def test_smoke_summary_tracks_debt_and_model_fallback() -> None:
    original_results = list(smoke.results)
    original_model = list(smoke.model_fallback_observations)
    try:
        smoke.results[:] = []
        smoke.model_fallback_observations[:] = [{
            "source": "image-vision:semantic",
            "primary_model": "vision.primary",
            "primary_failed": True,
            "fallback_used": True,
            "fallback_model": "local_analysis",
            "final_success": True,
            "failure_category": "auth_config_debt",
            "summary": "primary auth failed; local fallback used",
        }]
        smoke.add_result("clean", True, "ok")
        smoke.add_result("fallback", True, "fallback used", status="DEBT")

        summary = smoke._build_summary()

        assert summary["verdict"] == "PASS_WITH_DEBT"
        assert summary["counts"]["debt"] == 1
        assert summary["model_fallback"]["status"] == "DEBT"
        assert summary["model_fallback"]["fallback_used_count"] == 1
    finally:
        smoke.results[:] = original_results
        smoke.model_fallback_observations[:] = original_model
