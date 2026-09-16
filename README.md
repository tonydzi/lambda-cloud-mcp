# lambda-cloud-mcp

An MCP server for the [Lambda Cloud API](https://docs-api.lambda.ai/api/cloud).
It lets an AI agent (Claude Code, Claude Desktop, or any MCP client) check GPU prices and capacity, find the cheapest GPU that is available right now, and see your instances.

If you turn it on, the agent can also launch, restart and terminate instances, with a hard price limit.

> Not affiliated with Lambda. Tested against mocked responses built from the public API docs; live test pending.

## Why

Lambda has a clean REST API but, as of September 2026, no official MCP server.
Agents that train or serve models need to answer simple questions fast: "Is there an H100 free? Where? How much per hour?" This server answers them in one tool call.

## Tools

Read-only (always on):

| Tool | What it does | API call |
|---|---|---|
| `list_instance_types` | Types with price in USD/hour, specs, regions with capacity. Sorted cheapest first. `only_available=true` hides sold-out types. | `GET /api/v1/instance-types` |
| `cheapest_available_instance` | Cheapest type with capacity now. Filters: `min_gpus`, `gpu_contains` (e.g. `"H100"`), `region`, `max_hourly_usd`. | `GET /api/v1/instance-types` |
| `list_instances` | Your running instances | `GET /api/v1/instances` |
| `get_instance` | One instance by id | `GET /api/v1/instances/{id}` |
| `list_ssh_keys` | SSH keys in your account | `GET /api/v1/ssh-keys` |
| `list_file_systems` | Persistent file systems | `GET /api/v1/file-systems` |
| `list_images` | Available machine images | `GET /api/v1/images` |
| `list_regions` | Regions | `GET /api/v1/regions` |

Write tools (cost money, only with `LAMBDA_MCP_ALLOW_WRITE=1`):

| Tool | What it does | API call |
|---|---|---|
| `launch_instance` | Launch one instance. **Requires `max_hourly_usd`.** Refuses if the price is higher, or if the region has no capacity. | `POST /api/v1/instance-operations/launch` |
| `restart_instances` | Restart instances by id | `POST /api/v1/instance-operations/restart` |
| `terminate_instances` | Terminate instances by id. Irreversible. | `POST /api/v1/instance-operations/terminate` |

## Install

You need an API key from the [Lambda Cloud API keys page](https://cloud.lambda.ai/api-keys).

Run with [uv](https://docs.astral.sh/uv/) (no install step):

```bash
LAMBDA_API_KEY=your-key uvx --from git+https://github.com/tonydzi/lambda-cloud-mcp lambda-cloud-mcp
```

Or with pip:

```bash
pip install git+https://github.com/tonydzi/lambda-cloud-mcp
LAMBDA_API_KEY=your-key lambda-cloud-mcp
```

Python 3.10 or newer.

## Configure

### Claude Code

Read-only:

```bash
claude mcp add lambda-cloud -e LAMBDA_API_KEY=your-key -- \
  uvx --from git+https://github.com/tonydzi/lambda-cloud-mcp lambda-cloud-mcp
```

With launch / terminate enabled:

```bash
claude mcp add lambda-cloud -e LAMBDA_API_KEY=your-key -e LAMBDA_MCP_ALLOW_WRITE=1 -- \
  uvx --from git+https://github.com/tonydzi/lambda-cloud-mcp lambda-cloud-mcp
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lambda-cloud": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/tonydzi/lambda-cloud-mcp", "lambda-cloud-mcp"],
      "env": {
        "LAMBDA_API_KEY": "your-key"
      }
    }
  }
}
```

Add `"LAMBDA_MCP_ALLOW_WRITE": "1"` to `env` only if you want the agent to spend money.

## Safety

- **Read-only by default.** Without `LAMBDA_MCP_ALLOW_WRITE=1` the write tools are not even shown to the agent. They also check the flag again when called. Only the exact value `1` turns it on.
- **Price limit on launch.** `launch_instance` has no default for `max_hourly_usd`. The server reads the current price from the API and refuses if it is higher. Price is per instance per hour, as returned by the API (`price_cents_per_hour`).
- **Capacity check.** Launch is refused if the region is not in `regions_with_capacity_available`.
- **One instance per launch call.** No bulk launches.
- **Key handling.** The key is read only from `LAMBDA_API_KEY`, sent as `Authorization: Bearer`, and never logged or returned in errors.
- API errors come back as readable text with Lambda's error `code`, e.g. `Lambda API 401 on /instances: global/invalid-api-key`.

Lambda rate-limits the API to about 1 request per second, and launch to 1 request per 12 seconds.

## Source of truth

Every endpoint and field comes from Lambda's public OpenAPI spec, version 1.10.0:

- Spec: https://cloud.lambda.ai/api/v1/openapi.json
- Docs: https://docs-api.lambda.ai/api/cloud

## Development

```bash
uv venv && uv pip install -e ".[test]"
.venv/bin/pytest -q
```

Tests use [respx](https://lundberg.github.io/respx/) to mock HTTP. No real API calls, no key needed.

## Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `LAMBDA_API_KEY` | yes | Your Lambda Cloud API key |
| `LAMBDA_MCP_ALLOW_WRITE` | no | `1` enables launch / restart / terminate |
| `LAMBDA_API_BASE_URL` | no | Override base URL (default `https://cloud.lambda.ai`) |

## License

MIT

— Anton Dziatkovskii · github.com/tonydzi
