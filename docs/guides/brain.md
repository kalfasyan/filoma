# Filoma Brain - AI Agent Integration

Filoma Brain provides an intelligent AI agent for filesystem analysis using [PydanticAI](https://ai.pydantic.dev/). It can be used both programmatically and as an MCP server for integration with AI assistants like Claude Desktop, Cline, Cursor, and others.

## Features

- **Interactive Chat**: Have natural conversations about your filesystem
- **21 Powerful Tools**: Directory analysis, file operations, data quality checks, image analysis, and more
- **Smart DataFrames**: Automatically build and manipulate file metadata DataFrames
- **Read-Only Safety**: Safe analysis that never modifies your files (except export)
- **Multiple Backends**: Uses Rust (fastest), `fd`, or Python (fallback) for operations
- **MCP Server**: Expose all tools to any MCP-compatible client

## Quick Start

### Interactive Chat

```bash
# Start the chat interface
filoma brain chat

# Or use uv
uv run filoma brain chat
```

### Programmatic Usage

```python
from filoma.brain import get_agent
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

## MCP Server Configuration

Filoma Brain can be exposed as an MCP (Model Context Protocol) server, allowing AI assistants to use its filesystem analysis tools directly.

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the appropriate config for your platform:

```json
{
  "mcpServers": {
    "filoma": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/filoma", "filoma", "mcp", "serve"]
    }
  }
}
```

For development (using the local project):
```json
{
  "mcpServers": {
    "filoma": {
      "command": "uv",
      "args": ["run", "--directory", "/home/user/filoma", "python", "-m", "filoma.mcp_server"]
    }
  }
}
```

### Cline Configuration

Add to Cline's MCP settings (typically in VS Code settings):

```json
{
  "mcpServers": {
    "filoma": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/filoma", "filoma", "mcp", "serve"],
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

### Cursor Configuration

Add to Cursor's MCP settings (Settings > MCP):

```json
{
  "mcpServers": {
    "filoma": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/filoma", "filoma", "mcp", "serve"]
    }
  }
}
```

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

## Available Tools (21 Total)

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

### Utilities
- **`list_available_tools`** - Show all available tools with descriptions

## AI Model Configuration

Filoma Brain supports multiple AI backends:

### Mistral AI (Default)
```bash
export MISTRAL_API_KEY="your-api-key"
filoma brain chat
```

### Ollama (Local)
```bash
export FILOMA_BRAIN_BASE_URL="http://localhost:11434"
export FILOMA_BRAIN_MODEL="llama3.1:8b"
filoma brain chat
```

### Google Gemini
```bash
export GEMINI_API_KEY="your-api-key"
filoma brain chat
```

### Custom Model
```python
from filoma.brain import get_agent

# Using model name
agent = get_agent(model="mistral:mistral-large-latest")

# Using custom Model instance
from pydantic_ai.models.openai import OpenAIChatModel

model = OpenAIChatModel(model_name="custom-model", api_key="xxx")
agent = get_agent(model=model)
```

## Example Workflows

### Dataset Audit
```
User: Audit the /data/images directory for corrupted files
Brain: Running audit_corrupted_files...
       Found 3 corrupted files: [list]
       Recommendation: Remove or repair these files before training.
```

### File Analysis Pipeline
```
User: Find all JPG files in ./photos
Brain: search_files completed. Found 1,247 JPG files.

User: Show me the 10 largest ones
Brain: sort_dataframe_by_size completed. Here are the top 10:
       1. ./photos/vacation/dsc_001.jpg (15.2 MB)
       2. ...

User: Export the list to photos.csv
Brain: export_dataframe completed. Saved to photos.csv
```

### Codebase Exploration
```
User: How many Python files are in this project?
Brain: search_files completed. Found 42 Python files.

User: Show me the largest one
Brain: [displays largest Python file with line numbers]
```

## Architecture

Filoma Brain consists of:

- **`FilomaAgent`** (`agent.py`): PydanticAI agent with 21 registered tools
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

## Troubleshooting

**Issue**: Agent can't find files
- **Solution**: Check the working directory with `get_directory_tree(".")`

**Issue**: "No DataFrame loaded" error
- **Solution**: Run `search_files` or `create_dataset_dataframe` first

**Issue**: Model not responding correctly
- **Solution**: Check API keys are set: `MISTRAL_API_KEY`, `GEMINI_API_KEY`, etc.

**Issue**: MCP server not connecting
- **Solution**: Verify the path in your MCP config and ensure uv/pip is available

## See Also

- [CLI Guide](../guides/cli.md) - Command-line interface documentation
- [Data Quality Guide](../guides/data-integrity.md) - Data validation and quality checks
- [PydanticAI Documentation](https://ai.pydantic.dev/) - Framework powering Filoma Brain
- [MCP Documentation](https://modelcontextprotocol.io/) - Model Context Protocol specification
