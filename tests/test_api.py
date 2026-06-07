"""Tests for the FastAPI REST layer — orchestrator stubbed at the module seam.

Uses httpx.AsyncClient + ASGITransport so background tasks spawned inside
the request handler share the test's event loop (TestClient runs the portal
on a separate thread, which makes polling for background-task completion
racy).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from api import app as app_module
from api import routes as routes_module


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client(monkeypatch, tmp_path):
    """Fresh app + AsyncClient per test, with orchestrator.run stubbed."""
    async def _stub_run(*, domain, target, seed=None, resume=True, gen_batch_size=None):
        await asyncio.sleep(0.01)
        out = tmp_path / f"run_{domain}.jsonl"
        out.write_text('{"id": "x", "instruction": "i", "response": "r"}\n', encoding="utf-8")
        return {
            "run_id": f"run_test_{domain}",
            "domain": domain,
            "target": target,
            "accepted": target,
            "rejected": 0,
            "last_node_idx": target - 1,
            "output_path": str(out),
        }

    monkeypatch.setattr(routes_module.orchestrator, "run", _stub_run)
    app = app_module.create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, tmp_path


async def _wait_done(ac: httpx.AsyncClient, job_id: str, timeout: float = 2.0) -> dict:
    """Poll /runs/{job_id} until status != 'running'."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    body = None
    while loop.time() < deadline:
        body = (await ac.get(f"/runs/{job_id}")).json()
        if body["status"] != "running":
            return body
        await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s: {body}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_healthz(client):
    ac, _ = client
    r = await ac.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_start_run_returns_202_with_job_id(client):
    ac, _ = client
    r = await ac.post("/runs", json={"domain": "customer_support", "target": 3})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "running"
    assert body["domain"] == "customer_support"
    assert body["target"] == 3
    assert len(body["job_id"]) == 32  # uuid4 hex
    await _wait_done(ac, body["job_id"])


async def test_get_run_404_for_unknown(client):
    ac, _ = client
    r = await ac.get("/runs/does-not-exist")
    assert r.status_code == 404


async def test_run_completes_and_export_streams_jsonl(client):
    ac, _ = client
    started = (await ac.post("/runs", json={"domain": "customer_support", "target": 1})).json()
    final = await _wait_done(ac, started["job_id"])
    assert final["status"] == "done"
    assert final["accepted"] == 1
    assert final["output_path"] is not None

    r = await ac.get(f"/runs/{started['job_id']}/export")
    assert r.status_code == 200
    assert "x-ndjson" in r.headers["content-type"]
    assert r.text.startswith('{"id": "x"')


async def test_export_before_completion_returns_409(client):
    ac, _ = client
    started = (await ac.post("/runs", json={"domain": "customer_support", "target": 1})).json()
    r = await ac.get(f"/runs/{started['job_id']}/export")
    assert r.status_code == 409
    await _wait_done(ac, started["job_id"])  # drain


async def test_list_runs_includes_started_jobs(client):
    ac, _ = client
    j1 = (await ac.post("/runs", json={"domain": "customer_support", "target": 1})).json()["job_id"]
    j2 = (await ac.post("/runs", json={"domain": "customer_support", "target": 2})).json()["job_id"]
    listed = {j["job_id"] for j in (await ac.get("/runs")).json()}
    assert {j1, j2} <= listed
    await _wait_done(ac, j1)
    await _wait_done(ac, j2)


async def test_failed_job_records_error(client, monkeypatch):
    ac, _ = client

    async def _boom(**_):
        raise RuntimeError("nim went down")

    monkeypatch.setattr(routes_module.orchestrator, "run", _boom)
    job_id = (await ac.post("/runs", json={"domain": "customer_support", "target": 1})).json()["job_id"]
    final = await _wait_done(ac, job_id)
    assert final["status"] == "failed"
    assert "nim went down" in (final["error"] or "")


async def test_coverage_endpoint(client, monkeypatch):
    ac, _ = client

    class _StubStore:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None
        async def coverage(self, domain, dimension):
            return {"billing_dispute": 4, "refund_request": 7}

    monkeypatch.setattr(routes_module, "Store", _StubStore)
    r = await ac.get("/coverage/customer_support", params={"dimension": "topic"})
    assert r.status_code == 200
    body = r.json()
    assert body["domain"] == "customer_support"
    assert body["dimension"] == "topic"
    assert body["counts"] == {"billing_dispute": 4, "refund_request": 7}
    assert body["gaps"] == {}


async def test_coverage_endpoint_with_expected_returns_gaps(client, monkeypatch):
    ac, _ = client

    class _StubStore:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None
        async def coverage(self, domain, dimension):
            return {"a": 2, "b": 5, "c": 1}

    monkeypatch.setattr(routes_module, "Store", _StubStore)
    r = await ac.get(
        "/coverage/customer_support",
        params={"dimension": "topic", "expected_per_value": 4},
    )
    assert r.status_code == 200
    body = r.json()
    # 'b' is satisfied; 'c' has deficit 3; 'a' has deficit 2.
    assert body["gaps"] == {"c": 3, "a": 2}


async def test_diversity_endpoint(client, monkeypatch):
    ac, _ = client

    class _StubStore:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None
        async def all_embeddings(self, domain=None):
            # Two orthogonal vectors → Vendi score == 2.0.
            return [[1.0, 0.0], [0.0, 1.0]]

    monkeypatch.setattr(routes_module, "Store", _StubStore)
    r = await ac.get("/diversity/customer_support")
    assert r.status_code == 200
    body = r.json()
    assert body["domain"] == "customer_support"
    assert body["n_examples"] == 2
    assert abs(body["vendi_score"] - 2.0) < 1e-6


async def test_diversity_endpoint_empty_store(client, monkeypatch):
    ac, _ = client

    class _StubStore:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None
        async def all_embeddings(self, domain=None):
            return []

    monkeypatch.setattr(routes_module, "Store", _StubStore)
    r = await ac.get("/diversity/customer_support")
    assert r.status_code == 200
    body = r.json()
    assert body["n_examples"] == 0
    assert body["vendi_score"] == 0.0


async def test_validation_rejects_zero_target(client):
    ac, _ = client
    r = await ac.post("/runs", json={"domain": "customer_support", "target": 0})
    assert r.status_code == 422
