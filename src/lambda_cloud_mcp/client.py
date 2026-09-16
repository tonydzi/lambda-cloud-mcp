"""Small HTTP client for the Lambda Cloud API plus the safety rules.

Source of truth for every endpoint and field used here:
https://cloud.lambda.ai/api/v1/openapi.json (Lambda Cloud API 1.10.0),
rendered docs at https://docs-api.lambda.ai/api/cloud

Safety rules live in this file so they can be tested without MCP:
- write_enabled(): money-moving calls need LAMBDA_MCP_ALLOW_WRITE=1
- check_price():   launch is refused if the hourly price is above the cap
The API key is read from LAMBDA_API_KEY and is never logged or returned.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

BASE_URL = os.environ.get("LAMBDA_API_BASE_URL", "https://cloud.lambda.ai")
API_PREFIX = "/api/v1"
WRITE_ENV = "LAMBDA_MCP_ALLOW_WRITE"
KEY_ENV = "LAMBDA_API_KEY"


class LambdaError(RuntimeError):
    """Readable error. Never contains the API key."""


class WriteDisabled(LambdaError):
    pass


class PriceTooHigh(LambdaError):
    pass


def write_enabled() -> bool:
    return os.environ.get(WRITE_ENV, "").strip() == "1"


def require_write() -> None:
    if not write_enabled():
        raise WriteDisabled(
            f"This server is read-only. Set {WRITE_ENV}=1 to allow launch, "
            "terminate and restart (these cost money)."
        )


def check_price(price_cents_per_hour: int, max_hourly_usd: float) -> None:
    if max_hourly_usd is None or max_hourly_usd <= 0:
        raise PriceTooHigh("max_hourly_usd must be a positive number.")
    if price_cents_per_hour > round(max_hourly_usd * 100):
        raise PriceTooHigh(
            f"Price ${price_cents_per_hour / 100:.2f}/h is above your limit "
            f"${max_hourly_usd:.2f}/h. Nothing was launched."
        )


def _api_key() -> str:
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise LambdaError(f"{KEY_ENV} is not set.")
    return key


class LambdaClient:
    def __init__(self, api_key: str | None = None, base_url: str = BASE_URL,
                 timeout: float = 30.0) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def __repr__(self) -> str:  # never show the key
        return f"LambdaClient(base_url={self._base!r})"

    def _request(self, method: str, path: str, json: Any = None) -> Any:
        key = self._key or _api_key()
        headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        try:
            with httpx.Client(base_url=self._base, timeout=self._timeout) as c:
                r = c.request(method, API_PREFIX + path, headers=headers, json=json)
        except httpx.HTTPError as e:
            raise LambdaError(f"Network error calling {path}: {type(e).__name__}") from None
        try:
            body = r.json()
        except ValueError:
            body = None
        if r.status_code >= 400:
            err = (body or {}).get("error", {}) if isinstance(body, dict) else {}
            msg = f"Lambda API {r.status_code} on {path}: {err.get('code', 'unknown')}"
            if err.get("message"):
                msg += f" - {err['message']}"
            if err.get("suggestion"):
                msg += f" (suggestion: {err['suggestion']})"
            raise LambdaError(msg)
        if not isinstance(body, dict) or "data" not in body:
            raise LambdaError(f"Unexpected response from {path}.")
        return body["data"]

    # ---- read ----
    def instance_types(self) -> dict[str, Any]:
        return self._request("GET", "/instance-types")

    def instances(self) -> list[dict[str, Any]]:
        return self._request("GET", "/instances")

    def instance(self, instance_id: str) -> dict[str, Any]:
        return self._request("GET", f"/instances/{instance_id}")

    def ssh_keys(self) -> list[dict[str, Any]]:
        return self._request("GET", "/ssh-keys")

    def file_systems(self) -> list[dict[str, Any]]:
        return self._request("GET", "/file-systems")

    def images(self) -> list[dict[str, Any]]:
        return self._request("GET", "/images")

    def regions(self) -> list[dict[str, Any]]:
        return self._request("GET", "/regions")

    # ---- write (costs money) ----
    def launch(self, body: dict[str, Any]) -> dict[str, Any]:
        require_write()
        return self._request("POST", "/instance-operations/launch", json=body)

    def terminate(self, instance_ids: list[str]) -> dict[str, Any]:
        require_write()
        return self._request("POST", "/instance-operations/terminate",
                             json={"instance_ids": instance_ids})

    def restart(self, instance_ids: list[str]) -> dict[str, Any]:
        require_write()
        return self._request("POST", "/instance-operations/restart",
                             json={"instance_ids": instance_ids})


def flatten_types(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn the /instance-types map into a simple sorted list."""
    out = []
    for name, item in data.items():
        t = item.get("instance_type", {})
        specs = t.get("specs", {})
        out.append({
            "name": t.get("name", name),
            "description": t.get("description"),
            "gpu_description": t.get("gpu_description"),
            "gpus": specs.get("gpus"),
            "vcpus": specs.get("vcpus"),
            "memory_gib": specs.get("memory_gib"),
            "storage_gib": specs.get("storage_gib"),
            "architecture": t.get("architecture"),
            "price_cents_per_hour": t.get("price_cents_per_hour"),
            "price_usd_per_hour": (t.get("price_cents_per_hour") or 0) / 100,
            "regions_with_capacity": [r.get("name") for r in
                                      item.get("regions_with_capacity_available", [])],
        })
    out.sort(key=lambda x: (x["price_cents_per_hour"] or 0, x["name"]))
    return out


def pick_cheapest(types: list[dict[str, Any]], min_gpus: int = 1,
                  gpu_contains: str | None = None, region: str | None = None,
                  max_hourly_usd: float | None = None) -> dict[str, Any] | None:
    for t in types:  # already sorted by price
        regions = t["regions_with_capacity"]
        if not regions:
            continue
        if region and region not in regions:
            continue
        if (t["gpus"] or 0) < min_gpus:
            continue
        if gpu_contains and gpu_contains.lower() not in (t["gpu_description"] or "").lower():
            continue
        if max_hourly_usd is not None and t["price_cents_per_hour"] > round(max_hourly_usd * 100):
            continue
        return t
    return None
