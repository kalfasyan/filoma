# Filoma Filaraki - AI Agent Integration

Filoma Filaraki provides an intelligent AI agent for filesystem analysis using [PydanticAI](https://ai.pydantic.dev/). It can be used both programmatically and as an MCP server for integration with AI assistants like [nanobot](https://github.com/HKUDS/nanobot).

## Features

- **Interactive Chat**: Have natural conversations about your filesystem
- **30 Powerful Tools**: Directory analysis, file operations, data quality checks, image analysis, and more
- **Smart DataFrames**: Automatically build and manipulate file metadata DataFrames
- **Read-Only Safety**: Safe analysis that never modifies your files (except export)
- **Multiple Backends**: Uses Rust (fastest), `fd`, or Python (fallback) for operations
- **MCP Server**: Expose all tools to any MCP-compatible client

## Quick Start

> **Which AI service should I use?**
>
> | Provider                                        | Requires                                      | Privacy       |
> | ----------------------------------------------- | --------------------------------------------- | ------------- |
> | **Ollama** (auto-detected, default)             | `ollama serve` on `localhost:11434`           | 🔒 100% local |
> | **Mistral AI**                                  | `MISTRAL_API_KEY`                             | Cloud         |
> | **Google Gemini**                               | `GEMINI_API_KEY`                              | Cloud         |
> | **OpenAI / OpenRouter / any OpenAI-compatible** | `FILOMA_FILARAKI_BASE_URL` + `OPENAI_API_KEY` | Cloud         |
>
> All four are supported out-of-the-box. See [AI Model Configuration](#ai-model-configuration) for full details.

### Setup Wizard (Recommended)

The easiest way to configure your AI provider is with the interactive setup wizard:

```bash
filoma setup
```

It walks you through selecting a provider, entering your API key, and choosing a model. The result is a `.env` file that is automatically loaded when you start the chat.

### Interactive Chat

```bash
# Start the chat interface
filoma filaraki chat

# Or with uv
uv run filoma filaraki chat
```

> 💡 The `.env` file is automatically loaded by filoma — no need for `--env-file` flags or manual `export` commands.

**Prerequisites for Ollama (if using local models):**

```bash
ollama pull gemma4:e4b
ollama serve
```

### Programmatic Usage

```python
from filoma.filaraki import get_agent
import asyncio

async def analyze_directory():
    agent = get_agent()

    # Simple query
    result = await agent.run("How many files are in the current directory?")
    print(result.output)

    # Complex analysis
    result = await agent.run("Find all Python files and show me the 5 largest ones")
    print(result.output)

asyncio.run(analyze_directory())
```

## Using Filoma with GitHub Copilot

GitHub Copilot (VS Code chat, [Copilot CLI](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-copilot-cli), and Copilot coding agent) all understand filoma natively through two open standards: [Agent Skills](https://agentskills.io) and MCP.

### Option 1 — Agent Skill (instructions only, nothing to run)

```bash
filoma skills install --scope vscode   # writes ./.github/skills/filoma-*/SKILL.md
```

Commit `.github/skills/` to your repo and it's picked up automatically for every collaborator — no extension, no settings change. Copilot reads each skill's `description` to decide when to load it (e.g. "audit this dataset for training"), then follows instructions that call filoma's regular CLI / Python API. `filoma skills agents-md --write` additionally appends a filoma section to `AGENTS.md`, which Copilot also reads as always-on context.

### Option 2 — MCP server (real tool calls, no `pip install filoma` required)

**Copilot CLI — one command, nothing to write:**

```bash
copilot mcp add filoma -- uvx -p 3.11 filoma mcp serve
```

That's it. `copilot mcp list` immediately shows `filoma`, and Copilot can call `probe_directory`, `search_files`, `audit_dataset`, and the rest of the toolset right away — no restart needed. Remove it any time with `copilot mcp remove filoma`.

**VS Code chat** — add a `.vscode/mcp.json` to any repo (commit it so colleagues get it too):

```json
{
  "servers": {
    "filoma": {
      "command": "uvx",
      "args": ["--python", "3.11", "filoma", "mcp", "serve"]
    }
  }
}
```

`uvx` downloads and caches filoma on first use and runs it in an isolated environment, so nobody needs to `pip install filoma` into their project. Paste the same block into your user profile MCP config (Command Palette → **MCP: Open User Configuration**) to get filoma's tools in every workspace.

> Pin an exact Python version — `-p 3.11` (short for `--python 3.11`) — rather than a range like `>=3.11`. Filoma only publishes prebuilt wheels for cp311, so an exact pin guarantees `uvx` grabs the fast prebuilt wheel instead of silently falling back to a slower from-source build on whatever Python happens to be ambient by default.

> This filoma repo ships its own `.vscode/mcp.json`, pointed at the local development build (`uv run filoma mcp serve`) instead of `uvx`, so contributors get the in-progress MCP server automatically when they open this workspace in Copilot Chat.

## MCP Server Configuration with Nanobot

Filoma Filaraki can be exposed as an MCP (Model Context Protocol) server to [nanobot](https://github.com/HKUDS/nanobot), a Rust-based AI agent that runs locally with [Ollama](https://ollama.com).

This setup keeps everything on your machine—no API keys, no cloud services.

### 1. Install nanobot

```bash
uv tool install nanobot-ai
nanobot onboard
```

### 2. Configure Ollama as Provider

Edit `~/.nanobot/config.json` and set the following:

```json
{
  "agents": {
    "defaults": {
      "provider": "ollama",
      "model": "gemma4:e4b"
    }
  },
  "providers": {
    "ollama": {
      "apiBase": "http://localhost:11434/v1"
    }
  }
}
```

> **Important:** the `apiBase` must include `/v1` — without it nanobot hits a 404 and silently returns no response.

Make sure Ollama is running and the model is pulled before starting nanobot:

```bash
ollama pull gemma4:e4b
ollama serve
```

> ⚠️ **Model recommendation:** Avoid Llama 3 for tool-calling. Gemma 4 and Qwen 2.5 are significantly better at it.

### 3. Connect Filoma as an MCP Tool Server

In `~/.nanobot/config.json`, find `"mcpServers": {}` and replace it with:

```json
"mcpServers": {
  "filoma": {
    "command": "uvx",
    "args": ["--python", "3.11", "filoma", "mcp", "serve"]
  }
}
```

### 4. Test It

```bash
nanobot agent --logs -m "hello"
nanobot agent -m "probe directory ~/my/folder"
```

Use `--logs` when troubleshooting — it shows tool calls and any errors clearly.

**Example queries:**

- "How many files are in ~/my_project?"
- "Find all duplicate images in ./data"
- "Create a dataframe from this directory and show me the largest files"

### Running the MCP Server Manually

```bash
# Via CLI
filoma mcp serve

# Via Python module
python -m filoma.mcp_server

# Via uv
uv run python -m filoma.mcp_server
```

### Environment Variables

- `FILOMA_MCP_TRANSPORT`: Transport type - `stdio` (default) or `sse`
- `FILOMA_MCP_PORT`: Port for SSE transport (default: 8000)

## Available Tools (24 via MCP)

### Directory Analysis

- **`count_files`** - Full recursive scan counting all files/folders
- **`probe_directory`** - Scan directory for summary statistics with top extensions
- **`get_directory_tree`** - List immediate directory contents (non-recursive)
- **`find_duplicates`** - Find duplicate files in a directory

### File Operations

- **`get_file_info`** - Detailed file metadata (JSON)
- **`search_files`** - Search by pattern, extension, or size (loads DataFrame)
- **`open_file`** - Display file to user's terminal (bat/cat)
- **`read_file`** - Read file content for analysis (with line numbers)

### Dataset & DataFrame

- **`create_dataset_dataframe`** - Create metadata DataFrame from directory
- **`filter_by_extension`** - Filter DataFrame by file extension(s)
- **`filter_by_pattern`** - Filter DataFrame by regex pattern
- **`sort_dataframe_by_size`** - Sort by file size (descending/ascending)
- **`add_duplicate_cols`** - Flag exact duplicate rows (by SHA-256) as columns
- **`add_corruption_cols`** - Flag corrupt/zero-byte rows as columns
- **`dataframe_head`** - Show first N rows
- **`summarize_dataframe`** - Get summary statistics
- **`export_dataframe`** - Export to CSV/JSON/Parquet (only write operation)

### Image Analysis

- **`analyze_image`** - Get image shape, dtype, statistics
- **`preview_image`** - Generate visual preview (ANSI color blocks or ASCII)

### Data Quality

- **`audit_corrupted_files`** - Find corrupted/zero-byte files
- **`generate_hygiene_report`** - Quality metrics and issues
- **`assess_migration_readiness`** - Dataset migration assessment
- **`audit_dataset`** - One-call audit workflow (corruption + hygiene + readiness, optional HTML/JSON/MD report)

### Utilities

- **`list_available_tools`** - Show all available tools with descriptions

The interactive chat agent (`flm.ask()`, `filoma filaraki chat`) has 6 more tools beyond the MCP set above — `verify_integrity`, `run_quality_check`, `list_directory`, `list_directory_all`, `index_for_rag`, and `search_rag` — 30 tools in total.

## AI Model Configuration

Filoma Filaraki supports multiple AI backends with **Ollama as the default**, prioritizing privacy and local execution.

### Configuration Priority

1. **Ollama** (Local) - Auto-detected if running on `localhost:11434`
2. **Mistral AI** (Cloud) - If `MISTRAL_API_KEY` is set
3. **Google Gemini** (Cloud) - If `GEMINI_API_KEY` is set
4. **OpenAI-Compatible** (Generic) - If `FILOMA_FILARAKI_BASE_URL` is set

### Ollama (Local - Default, Recommended)

**Auto-detection:** Filoma will automatically detect Ollama running on `localhost:11434` and use `gemma4:e4b` as the default model. Auto-detection is skipped if a cloud provider API key is already configured.

```bash
# Just start filoma - it will auto-detect Ollama
filoma filaraki chat
```

**If Ollama runs on a different host/port:**

```bash
export FILOMA_FILARAKI_BASE_URL="http://localhost:11434/v1"
export FILOMA_FILARAKI_MODEL="gemma4:e4b"
filoma filaraki chat
```

**Setup:**

```bash
ollama pull gemma4:e4b
ollama serve
```

> 💡 **Why gemma4:e4b?** It has excellent tool-calling capabilities, runs well on consumer hardware, and respects your privacy.

### Mistral AI (Cloud)

```bash
export MISTRAL_API_KEY="your-api-key"
filoma filaraki chat

# Optional: override default model
export FILOMA_FILARAKI_MODEL="mistral:mistral-small-latest"
```

### Google Gemini (Cloud)

```bash
export GEMINI_API_KEY="your-api-key"
filoma filaraki chat

# Optional: override default model
export FILOMA_FILARAKI_MODEL="gemini-3.1-flash-lite"
```

### OpenAI-Compatible (Generic)

Use any OpenAI-compatible API endpoint including OpenAI, OpenRouter, Together AI, Azure OpenAI, etc.

**OpenAI:**

```bash
export FILOMA_FILARAKI_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="your-api-key"
filoma filaraki chat
```

**OpenRouter (access to multiple models):**

```bash
export FILOMA_FILARAKI_BASE_URL="https://openrouter.ai/api/v1"
export OPENAI_API_KEY="your-openrouter-key"
export FILOMA_FILARAKI_MODEL="anthropic/claude-3.5-sonnet"
filoma filaraki chat
```

### Custom Model (Programmatic)

```python
from filoma.filaraki import get_agent

# Using model name
agent = get_agent(model="mistral:mistral-large-latest")

# Using custom Model instance
from pydantic_ai.models.openai import OpenAIChatModel

model = OpenAIChatModel(model_name="custom-model", api_key="xxx")
agent = get_agent(model=model)
```

## Environment Configuration File

The recommended way to create your `.env` is with the setup wizard:

```bash
filoma setup
```

Alternatively, copy `.env_example` to `.env` manually:

```bash
cp .env_example .env
```

Then edit `.env` and uncomment only ONE scenario:

```bash
# Ollama (Default - recommended)
FILOMA_FILARAKI_MODEL=gemma4:e4b

# Or for cloud providers, set the API key:
# MISTRAL_API_KEY=your_key_here
# GEMINI_API_KEY=your_key_here
# OPENAI_API_KEY=your_key_here
# FILOMA_FILARAKI_BASE_URL=https://api.openai.com/v1
```

> ⚠️ **Note:** When using `uvx`, environment variables from `.env` are not automatically loaded. Use `uv run filoma filaraki chat` instead, or export them in your shell.

## Example Workflows

### Full Dataset Audit with HTML Report

The most powerful single workflow: one prompt runs corruption checks, hygiene scoring, and migration readiness all at once, then exports a **self-contained interactive HTML report**.

```
User: perform an audit on /data/images and export an html report called audit.html
Filaraki: audit_dataset completed.
       ✔ 4,208 files checked — 0 corrupted, 0 zero-byte
       ✔ Hygiene score: 65/100 (2 duplicate groups found)
       ✔ Migration readiness: 100/100 — no blockers
       Report exported to: /abs/path/audit.html
```

The HTML report includes score gauges, KPI tiles, stage timing bars, priority-tagged next actions, duplicate evidence cards, and a collapsible full JSON payload. Export formats also include `json` and `md`:

```
User: perform an audit on /data/images and export a json report called audit.json
User: perform an audit on /data/images and export a markdown report called audit.md
```

### Dataset Audit (Inline)

```
User: Audit the /data/images directory for corrupted files
Filaraki: Running audit_corrupted_files...
       Found 3 corrupted files: [list]
       Recommendation: Remove or repair these files before training.
```

### File Analysis Pipeline

```
User: Find all JPG files in ./photos
Filaraki: search_files completed. Found 1,247 JPG files.

User: Show me the 10 largest ones
Filaraki: sort_dataframe_by_size completed. Here are the top 10:
       1. ./photos/vacation/dsc_001.jpg (15.2 MB)
       2. ...

User: Export the list to photos.csv
Filaraki: export_dataframe completed. Saved to photos.csv
```

### Codebase Exploration

```
User: How many Python files are in this project?
Filaraki: search_files completed. Found 42 Python files.

User: Show me the largest one
Filaraki: [displays largest Python file with line numbers]
```

## Architecture

Filoma Filaraki consists of:

- **`FilarakiAgent`** (`agent.py`): PydanticAI agent with 30 registered tools
- **Tools** (`tools.py`): Individual tool implementations with `RunContext` support
- **CLI** (`cli.py`): Rich-based interactive chat interface
- **MCP Server** (`mcp_server.py`): MCP server exposing tools to external agents
- **Models** (`models.py`): Structured response models for reports

## Best Practices

1. **Start Broad**: Use `probe_directory` for initial exploration
2. **Search Smart**: Use `search_files` instead of `count_files` for specific types
3. **Chain Operations**: Filter, sort, and export DataFrames in sequence
4. **View vs Analyze**: Use `open_file` for viewing, `read_file` for analysis
5. **Safety First**: The agent is read-only except for `export_dataframe`
6. **Ollama First**: Use local Ollama for privacy and zero cost
7. **Tool Calling Models**: Prefer models with good tool-calling (qwen2.5, mistral)

## Troubleshooting

**Issue**: Agent can't find files

- **Solution**: Check the working directory with `get_directory_tree(".")`

**Issue**: "No DataFrame loaded" error

- **Solution**: Run `search_files` or `create_dataset_dataframe` first

**Issue**: "Make sure Ollama is running" error

- **Solution**: Ensure Ollama is running: `ollama serve` and you have the model: `ollama pull qwen2.5:14b`

**Issue**: Model not responding correctly

- **Solution**: Check API keys are set: `MISTRAL_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.

**Issue**: MCP server not connecting

- **Solution**: Verify the path in your MCP config and ensure uv/pip is available

**Issue**: Tool-calling not working

- **Solution**: Switch to a model with better tool-calling support (qwen2.5:14b, mistral-small)

## See Also

- [CLI Guide](../guides/cli.md) - Command-line interface documentation
- [Data Quality Guide](../guides/data-integrity.md) - Data validation and quality checks
- [PydanticAI Documentation](https://ai.pydantic.dev/) - Framework powering Filoma Filaraki
- [MCP Documentation](https://modelcontextprotocol.io/) - Model Context Protocol specification
- [Ollama Documentation](https://ollama.com/) - Run LLMs locally
