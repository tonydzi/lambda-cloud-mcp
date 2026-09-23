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

<!-- READ-WITH-AI:START (generated by read_with_ai.py - do not hand-edit) -->

### READ THIS WITH AI

One click and an agent reads the repo, pulls out the patterns and helps you apply them to your own work.

<a href="https://chatgpt.com/codex?prompt=Read%20this%20repo%3A%20https%3A%2F%2Fgithub.com%2Ftonydzi%2Flambda-cloud-mcp%20%28%E2%80%9Clambda-cloud-mcp%E2%80%9D%20-%20MCP%20server%20for%20the%20Lambda%20Cloud%20API%3A%20GPU%20prices%2C%20live%20capacity%2C%20cheapest-available%20lookup%2C%20and%20env-gated%20launch%2Fterminate%20with%20a%20price%20cap.%20Read-only%20by%20default%29.%20Work%20out%20what%20problem%20it%20actually%20solves%2C%20pull%20out%20the%20reusable%20patterns%20and%20help%20me%20apply%20them%20to%20my%20own%20setup.%20Start%20by%20asking%20what%20I%20am%20working%20on."><img alt="Codex - open" src="https://img.shields.io/badge/Codex-open-000000?style=for-the-badge&logo=openai&logoColor=white"></a> <a href="https://chatgpt.com/?q=Read%20this%20repo%3A%20https%3A%2F%2Fgithub.com%2Ftonydzi%2Flambda-cloud-mcp%20%28%E2%80%9Clambda-cloud-mcp%E2%80%9D%20-%20MCP%20server%20for%20the%20Lambda%20Cloud%20API%3A%20GPU%20prices%2C%20live%20capacity%2C%20cheapest-available%20lookup%2C%20and%20env-gated%20launch%2Fterminate%20with%20a%20price%20cap.%20Read-only%20by%20default%29.%20Work%20out%20what%20problem%20it%20actually%20solves%2C%20pull%20out%20the%20reusable%20patterns%20and%20help%20me%20apply%20them%20to%20my%20own%20setup.%20Start%20by%20asking%20what%20I%20am%20working%20on."><img alt="ChatGPT - open" src="https://img.shields.io/badge/ChatGPT-open-10a37f?style=for-the-badge&logo=openai&logoColor=white"></a> <a href="https://claude.ai/new?q=Read%20this%20repo%3A%20https%3A%2F%2Fgithub.com%2Ftonydzi%2Flambda-cloud-mcp%20%28%E2%80%9Clambda-cloud-mcp%E2%80%9D%20-%20MCP%20server%20for%20the%20Lambda%20Cloud%20API%3A%20GPU%20prices%2C%20live%20capacity%2C%20cheapest-available%20lookup%2C%20and%20env-gated%20launch%2Fterminate%20with%20a%20price%20cap.%20Read-only%20by%20default%29.%20Work%20out%20what%20problem%20it%20actually%20solves%2C%20pull%20out%20the%20reusable%20patterns%20and%20help%20me%20apply%20them%20to%20my%20own%20setup.%20Start%20by%20asking%20what%20I%20am%20working%20on."><img alt="Claude - open" src="https://img.shields.io/badge/Claude-open-d97757?style=for-the-badge&logo=anthropic&logoColor=white"></a>

<details>
<summary>Copy the prompt (works in any agent: Gemini, Grok, a local model, your own CLI)</summary>

```text
Read this repo: https://github.com/tonydzi/lambda-cloud-mcp (“lambda-cloud-mcp” - MCP server for the Lambda Cloud API: GPU prices, live capacity, cheapest-available lookup, and env-gated launch/terminate with a price cap. Read-only by default). Work out what problem it actually solves, pull out the reusable patterns and help me apply them to my own setup. Start by asking what I am working on.
```

</details>

<sub>— TonyDzi, Palo Alto AI Research Lab · second brain, agent coordination, persistent memory: github.com/tonydzi</sub>

<!-- READ-WITH-AI:END -->

---

<!--ecosystem-map:start-->

## 🧩 One piece of a working system

This repository is one piece lifted out of a live operation: one non-technical founder, an AI
cofounder, and a fleet of machines that reach consensus with each other and wake the human only
for money or the irreversible. It was extracted after it survived production, not written as a
demo — and it runs on its own: nothing here phones home to the rest.

**See how the whole thing fits together → [SYSTEM.md](https://github.com/tonydzi/tonydzi/blob/main/SYSTEM.md)**

<!--ecosystem-map:end-->

## AI contributors

This project is built by a human + AI team, and the git log says so: Claude writes most of
the code, Codex and Grok review it, Gemini feeds the research. Each is credited on a commit
**only if its output changed that commit's content** — no decorative credits. Lab-wide
policy, one source for every repo: [AI-CONTRIBUTORS.md](https://github.com/tonydzi/.github/blob/main/AI-CONTRIBUTORS.md).
