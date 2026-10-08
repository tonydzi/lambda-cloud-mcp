# -*- coding: utf-8 -*-
"""The MCP handshake must carry a real version, and the package must agree with it.

The server used to be built as `_Server("lambda-cloud")`, leaving the SDK's
`version` default of `""`. Clients display `serverInfo.version` verbatim, so an
empty string reads as a broken server, and it makes a bug report impossible to
pin to a build.

RED-FIRST: drop the `version=__version__` keyword in
`lambda_cloud_mcp.server._build_server` and `test_server_reports_its_version`
fails with `version == ""`.
"""
import re
from pathlib import Path

import lambda_cloud_mcp
from lambda_cloud_mcp import server as srv


def _server_version() -> str:
    """The version the server will advertise, across both SDK generations."""
    for attr in ("version", "_version"):
        value = getattr(srv.mcp, attr, None)
        if isinstance(value, str):
            return value
    inner = getattr(srv.mcp, "_mcp_server", None) or getattr(srv.mcp, "_server", None)
    if inner is not None:
        value = getattr(inner, "version", None)
        if isinstance(value, str):
            return value
    raise AssertionError(
        "cannot read the version off the server object — the SDK changed shape, "
        "so this test must be updated rather than deleted"
    )


def test_server_reports_its_version():
    assert _server_version() == lambda_cloud_mcp.__version__


def test_server_version_is_not_empty():
    """Guards the exact defect: the SDK default is an empty string."""
    assert _server_version().strip(), "serverInfo.version is empty"


def test_package_version_matches_pyproject():
    """One version, not two.

    pyproject.toml carries a literal `version`, so it can drift from
    `__version__` while every test stays green and the wheel ships a number
    the code disagrees with.
    """
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if not pyproject.exists():          # installed-wheel run, no source tree
        return
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"))
    assert match, "no literal version in pyproject.toml"
    assert match.group(1) == lambda_cloud_mcp.__version__
