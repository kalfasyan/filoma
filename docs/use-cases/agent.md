# Talk to Your Data

filoma includes Filaraki, an AI agent that lets you ask natural-language questions about your filesystem. You can use it from the CLI, from Python, or as an MCP server connected to any compatible AI assistant.

## One-shot: `filoma ask`

The fastest way to get an answer:

```bash
filoma ask "how many Python files are in src/?"
filoma ask "find corrupted images in ./data"
filoma ask "what are the 5 largest files in this project?"
```

Each `filoma ask` invocation starts a fresh agent, runs your query, prints the answer, and exits. No setup beyond installing filoma.

## Interactive chat: `filoma filaraki chat`

For multi-turn exploration, use the interactive chat:

```bash
filoma filaraki chat
```

Example session:

```text
You: probe the current directory
Filaraki: Scanned 1,247 items across 89 directories. Top extensions: .py (342), .jpg (201), .json (56)...

You: find all jpg files over 5MB
Filaraki: search_files completed. Found 23 JPG files over 5 MB...

You: export that list to large_photos.csv
Filaraki: Exported to /home/user/large_photos.csv
```

## Python API: `flm.ask()`

```python
import filoma as flm

answer = flm.ask("How many corrupted images are in ./data?")
print(answer)
```

For more control, get an agent instance directly:

```python
from filoma.filaraki import get_agent
import asyncio

async def main():
    agent = get_agent()
    result = await agent.run("Audit ./data and summarize the top 3 issues")
    print(result.output)

asyncio.run(main())
```

## MCP server

Filaraki can run as a Model Context Protocol server, exposing all of filoma's filesystem tools to any MCP-compatible client (nanobot, Claude Desktop, VS Code chat, Copilot CLI, etc.).

```bash
filoma mcp serve
```

### Connect to Copilot CLI

```bash
copilot mcp add filoma -- uvx -p 3.11 filoma mcp serve
```

One command, no config file to write. See [Using Filoma with GitHub Copilot](../guides/filaraki.md#using-filoma-with-github-copilot) in the Filaraki guide for VS Code chat and Copilot coding agent setup too.

### Connect to nanobot

Add to `~/.nanobot/config.json`:

```json
"mcpServers": {
  "filoma": {
    "command": "uvx",
    "args": ["--python", "3.11", "filoma", "mcp", "serve"]
  }
}
```

Then ask nanobot about your filesystem:

```text
nanobot agent -m "how many python files are in ~/projects?"
nanobot agent -m "find duplicate images in ./data and tell me which to delete"
```

## Provider setup

Filaraki auto-detects providers in this order:

| Provider              | What you need                                       | Privacy |
| --------------------- | --------------------------------------------------- | ------- |
| **Ollama**            | `ollama serve` on `localhost:11434` (auto-detected) | Local   |
| **Mistral**           | `MISTRAL_API_KEY` env var                           | Cloud   |
| **Gemini**            | `GEMINI_API_KEY` env var                            | Cloud   |
| **OpenAI-compatible** | `FILOMA_FILARAKI_BASE_URL` + `OPENAI_API_KEY`       | Cloud   |

### Local setup (Ollama — no API keys)

```bash
ollama pull gemma4:e4b
ollama serve
filoma filaraki chat
```

### Cloud setup

Use the interactive setup wizard:

```bash
filoma setup
```

Or set environment variables manually:

```bash
export MISTRAL_API_KEY="your-key"
filoma filaraki chat
```

For OpenAI, OpenRouter, or any compatible endpoint:

```bash
export FILOMA_FILARAKI_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="your-key"
export FILOMA_FILARAKI_MODEL="gpt-4o"
filoma filaraki chat
```

## Example dialogues

**Find data quality issues:**

```text
You: audit ./training_data and export an HTML report
Filaraki: Running audit_dataset...
    4,208 files checked — 0 corrupted, 2 duplicate groups found
    Hygiene score: 65/100 — class imbalance in 3 categories
    Migration readiness: 100/100 — no blockers
    Report exported to: /abs/path/audit.html
```

**Explore an unknown directory:**

```text
You: what's in ~/downloads/dataset_dump/?
Filaraki: probe_directory completed.
    12,400 files, 1,203 folders
    Top extensions: .jpg (8,200), .json (2,100), .csv (1,500), .txt (600)
    Total size: 34.2 GB

You: are there any corrupted jpgs?
Filaraki: Running audit_corrupted_files...
    Found 12 corrupted JPEGs. Recommendation: remove or repair before training.
```

**Find the biggest space hogs:**

```text
You: show me the 10 largest files in this project
Filaraki: sort_dataframe_by_size completed. Top 10:
    1. ./data/backups/dump_2024.sql (2.1 GB)
    2. ./models/checkpoint_epoch50.pt (850 MB)
    ...
```

## Available tools

Filaraki has 24 tools covering directory analysis, file operations, DataFrame manipulation, image analysis, and data quality checks. The agent decides which tools to call based on your query — you don't need to know the tool names.

## What to read next

- [Filaraki guide](../guides/filaraki.md) — full reference: all 24 tools, environment config, troubleshooting, nanobot setup details
- [Audit a Dataset](audit.md) — the audit use case Filaraki can automate
- [Explore a Dataset](explore.md) — understand the probe/DataFrame tools the agent uses under the hood
