"""MCP server exposing the Lambda Cloud API as tools.

Read-only by default. Launch / terminate / restart are registered only when
LAMBDA_MCP_ALLOW_WRITE=1, and they check that flag again when called.
"""

from __future__ import annotations

from typing import Any

try:  # mcp SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from .client import (LambdaClient, check_price, flatten_types, pick_cheapest,
                     require_write, write_enabled)

mcp = _Server("lambda-cloud")
client = LambdaClient()


@mcp.tool()
def list_instance_types(only_available: bool = False) -> list[dict[str, Any]]:
    """List Lambda Cloud instance types with price (USD/hour), specs and the
    regions that have capacity right now. Sorted from cheapest."""
    types = flatten_types(client.instance_types())
    if only_available:
        types = [t for t in types if t["regions_with_capacity"]]
    return types


@mcp.tool()
def cheapest_available_instance(min_gpus: int = 1, gpu_contains: str | None = None,
                                region: str | None = None,
                                max_hourly_usd: float | None = None) -> dict[str, Any]:
    """Find the cheapest instance type that has capacity now.
    Filters: min_gpus, gpu_contains (e.g. "H100"), region (e.g. "us-east-1"),
    max_hourly_usd. Returns {"found": false} if nothing matches."""
    t = pick_cheapest(flatten_types(client.instance_types()), min_gpus=min_gpus,
                      gpu_contains=gpu_contains, region=region,
                      max_hourly_usd=max_hourly_usd)
    return {"found": False} if t is None else {"found": True, **t}


@mcp.tool()
def list_instances() -> list[dict[str, Any]]:
    """List your running instances."""
    return client.instances()


@mcp.tool()
def get_instance(instance_id: str) -> dict[str, Any]:
    """Get details of one instance by id."""
    return client.instance(instance_id)


@mcp.tool()
def list_ssh_keys() -> list[dict[str, Any]]:
    """List SSH keys saved in your Lambda Cloud account."""
    return client.ssh_keys()


@mcp.tool()
def list_file_systems() -> list[dict[str, Any]]:
    """List your persistent file systems."""
    return client.file_systems()


@mcp.tool()
def list_images() -> list[dict[str, Any]]:
    """List available machine images."""
    return client.images()


@mcp.tool()
def list_regions() -> list[dict[str, Any]]:
    """List Lambda Cloud regions."""
    return client.regions()


# ---------------- write tools (cost money) ----------------

def launch_instance(instance_type_name: str, region_name: str, ssh_key_names: list[str],
                    max_hourly_usd: float, name: str | None = None,
                    file_system_names: list[str] | None = None,
                    image_family: str | None = None) -> dict[str, Any]:
    """Launch ONE instance. Costs money. Refuses if the type's hourly price is
    above max_hourly_usd or the region has no capacity right now."""
    require_write()
    types = {t["name"]: t for t in flatten_types(client.instance_types())}
    t = types.get(instance_type_name)
    if t is None:
        raise ValueError(f"Unknown instance type {instance_type_name!r}.")
    check_price(t["price_cents_per_hour"], max_hourly_usd)
    if region_name not in t["regions_with_capacity"]:
        raise ValueError(f"No capacity for {instance_type_name} in {region_name} right now. "
                         f"Regions with capacity: {t['regions_with_capacity'] or 'none'}.")
    body: dict[str, Any] = {"region_name": region_name,
                            "instance_type_name": instance_type_name,
                            "ssh_key_names": ssh_key_names}
    if name:
        body["name"] = name
    if file_system_names:
        body["file_system_names"] = file_system_names
    if image_family:
        body["image"] = {"family": image_family}
    data = client.launch(body)
    return {**data, "price_usd_per_hour": t["price_usd_per_hour"]}


def terminate_instances(instance_ids: list[str]) -> dict[str, Any]:
    """Terminate instances. Irreversible: local disk data is lost."""
    require_write()
    return client.terminate(instance_ids)


def restart_instances(instance_ids: list[str]) -> dict[str, Any]:
    """Restart instances."""
    require_write()
    return client.restart(instance_ids)


def register_write_tools() -> None:
    for fn in (launch_instance, terminate_instances, restart_instances):
        mcp.tool()(fn)


def main() -> None:
    if write_enabled():
        register_write_tools()
    mcp.run()


if __name__ == "__main__":
    main()
