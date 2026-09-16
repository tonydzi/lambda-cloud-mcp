"""Tests against mocked responses shaped like the public OpenAPI spec
(https://cloud.lambda.ai/api/v1/openapi.json, version 1.10.0)."""

import asyncio
import inspect

import httpx
import pytest
import respx

from lambda_cloud_mcp import client as C
from lambda_cloud_mcp import server as S

BASE = "https://cloud.lambda.ai/api/v1"
KEY = "secret_test_key_do_not_leak"


def itype(name, desc, gpu, cents, gpus, regions):
    return {
        "instance_type": {
            "name": name, "description": desc, "gpu_description": gpu,
            "price_cents_per_hour": cents,
            "specs": {"vcpus": 30, "memory_gib": 200, "storage_gib": 1400, "gpus": gpus},
            "architecture": "x86_64",
        },
        "regions_with_capacity_available": [
            {"name": r, "description": r} for r in regions
        ],
    }


TYPES = {"data": {
    "gpu_1x_a10": itype("gpu_1x_a10", "1x A10 (24 GB PCIe)", "A10 (24 GB PCIe)", 75, 1, []),
    "gpu_1x_a100": itype("gpu_1x_a100", "1x A100 (40 GB SXM4)", "A100 (40 GB SXM4)", 129, 1, ["us-west-1"]),
    "gpu_8x_h100_sxm5gdr": itype("gpu_8x_h100_sxm5gdr", "8x H100 (80 GB SXM5)", "H100 (80 GB SXM5)", 3592, 8, ["us-east-1", "us-west-1"]),
}}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("LAMBDA_API_KEY", KEY)
    monkeypatch.delenv("LAMBDA_MCP_ALLOW_WRITE", raising=False)


@pytest.fixture
def write_on(monkeypatch):
    monkeypatch.setenv("LAMBDA_MCP_ALLOW_WRITE", "1")


@respx.mock
def test_list_types_sorted_and_bearer_auth():
    route = respx.get(f"{BASE}/instance-types").mock(return_value=httpx.Response(200, json=TYPES))
    out = S.list_instance_types()
    assert [t["name"] for t in out] == ["gpu_1x_a10", "gpu_1x_a100", "gpu_8x_h100_sxm5gdr"]
    assert out[1]["price_usd_per_hour"] == 1.29
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {KEY}"
    assert [t["name"] for t in S.list_instance_types(only_available=True)] == ["gpu_1x_a100", "gpu_8x_h100_sxm5gdr"]


@respx.mock
def test_cheapest_available_skips_no_capacity_and_filters():
    respx.get(f"{BASE}/instance-types").mock(return_value=httpx.Response(200, json=TYPES))
    assert S.cheapest_available_instance()["name"] == "gpu_1x_a100"
    assert S.cheapest_available_instance(gpu_contains="h100")["name"] == "gpu_8x_h100_sxm5gdr"
    assert S.cheapest_available_instance(region="us-east-1")["name"] == "gpu_8x_h100_sxm5gdr"
    assert S.cheapest_available_instance(min_gpus=8, max_hourly_usd=10) == {"found": False}


@respx.mock
def test_read_endpoints():
    respx.get(f"{BASE}/instances").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get(f"{BASE}/instances/abc").mock(return_value=httpx.Response(200, json={"data": {"id": "abc", "status": "active"}}))
    respx.get(f"{BASE}/ssh-keys").mock(return_value=httpx.Response(200, json={"data": [{"id": "k", "name": "my-public-key", "public_key": "ssh-ed25519 AAA"}]}))
    respx.get(f"{BASE}/file-systems").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get(f"{BASE}/images").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get(f"{BASE}/regions").mock(return_value=httpx.Response(200, json={"data": [{"name": "us-west-1", "description": "California, USA"}]}))
    assert S.list_instances() == []
    assert S.get_instance("abc")["status"] == "active"
    assert S.list_ssh_keys()[0]["name"] == "my-public-key"
    assert S.list_file_systems() == [] and S.list_images() == []
    assert S.list_regions()[0]["name"] == "us-west-1"


@respx.mock
def test_api_error_is_readable_and_hides_key():
    respx.get(f"{BASE}/instances").mock(return_value=httpx.Response(
        401, json={"error": {"code": "global/invalid-api-key", "message": "API key was invalid"}}))
    with pytest.raises(C.LambdaError) as e:
        S.list_instances()
    assert "global/invalid-api-key" in str(e.value)
    assert KEY not in str(e.value) and KEY not in repr(S.client)


# ---------------- write gate ----------------

@respx.mock
def test_write_tools_refuse_without_flag():
    launch = respx.post(f"{BASE}/instance-operations/launch")
    term = respx.post(f"{BASE}/instance-operations/terminate")
    restart = respx.post(f"{BASE}/instance-operations/restart")
    respx.get(f"{BASE}/instance-types").mock(return_value=httpx.Response(200, json=TYPES))
    with pytest.raises(C.WriteDisabled):
        S.launch_instance("gpu_1x_a100", "us-west-1", ["k"], max_hourly_usd=100)
    with pytest.raises(C.WriteDisabled):
        S.terminate_instances(["abc"])
    with pytest.raises(C.WriteDisabled):
        S.restart_instances(["abc"])
    with pytest.raises(C.WriteDisabled):  # client layer is gated too
        C.LambdaClient().terminate(["abc"])
    assert not launch.called and not term.called and not restart.called


def test_flag_must_be_exactly_1(monkeypatch):
    for v in ["", "0", "true", "yes"]:
        monkeypatch.setenv("LAMBDA_MCP_ALLOW_WRITE", v)
        assert C.write_enabled() is False
    monkeypatch.setenv("LAMBDA_MCP_ALLOW_WRITE", "1")
    assert C.write_enabled() is True


def _tool_names():
    tools = S.mcp.list_tools()
    if inspect.isawaitable(tools):  # mcp SDK 1.x returns a coroutine
        tools = asyncio.run(tools)
    return {t.name for t in tools}


def test_write_tools_not_registered_by_default():
    names = _tool_names()
    assert "cheapest_available_instance" in names
    assert not names & {"launch_instance", "terminate_instances", "restart_instances"}


# ---------------- price cap ----------------

@respx.mock
def test_launch_refused_when_price_above_cap(write_on):
    respx.get(f"{BASE}/instance-types").mock(return_value=httpx.Response(200, json=TYPES))
    launch = respx.post(f"{BASE}/instance-operations/launch")
    with pytest.raises(C.PriceTooHigh):
        S.launch_instance("gpu_8x_h100_sxm5gdr", "us-east-1", ["k"], max_hourly_usd=35.91)
    with pytest.raises(C.PriceTooHigh):
        S.launch_instance("gpu_1x_a100", "us-west-1", ["k"], max_hourly_usd=0)
    assert not launch.called


@respx.mock
def test_launch_refused_without_capacity(write_on):
    respx.get(f"{BASE}/instance-types").mock(return_value=httpx.Response(200, json=TYPES))
    launch = respx.post(f"{BASE}/instance-operations/launch")
    with pytest.raises(ValueError, match="No capacity"):
        S.launch_instance("gpu_1x_a100", "us-east-1", ["k"], max_hourly_usd=5)
    assert not launch.called


@respx.mock
def test_launch_ok_at_exact_cap(write_on):
    respx.get(f"{BASE}/instance-types").mock(return_value=httpx.Response(200, json=TYPES))
    launch = respx.post(f"{BASE}/instance-operations/launch").mock(
        return_value=httpx.Response(200, json={"data": {"instance_ids": ["0920582c7ff041399e34823a0be62549"]}}))
    out = S.launch_instance("gpu_8x_h100_sxm5gdr", "us-east-1", ["my-public-key"],
                            max_hourly_usd=35.92, image_family="lambda-stack-22-04")
    assert out["instance_ids"] == ["0920582c7ff041399e34823a0be62549"]
    import json
    body = json.loads(launch.calls[0].request.content)
    assert body == {"region_name": "us-east-1", "instance_type_name": "gpu_8x_h100_sxm5gdr",
                    "ssh_key_names": ["my-public-key"], "image": {"family": "lambda-stack-22-04"}}


@respx.mock
def test_terminate_and_restart_with_flag(write_on):
    t = respx.post(f"{BASE}/instance-operations/terminate").mock(
        return_value=httpx.Response(200, json={"data": {"terminated_instances": []}}))
    r = respx.post(f"{BASE}/instance-operations/restart").mock(
        return_value=httpx.Response(200, json={"data": {"restarted_instances": []}}))
    assert S.terminate_instances(["abc"]) == {"terminated_instances": []}
    assert S.restart_instances(["abc"]) == {"restarted_instances": []}
    assert t.called and r.called
