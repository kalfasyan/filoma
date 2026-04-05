#!/usr/bin/env bash
# Filoma Brain - One-Line Installer
# Usage: curl -sL https://filoma.io/install | sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Filoma ASCII art
print_banner() {
    cat << 'EOF'
    ███████╗██╗██╗      ██████╗ ███╗   ███╗ █████╗
    ██╔════╝██║██║     ██╔═══██╗████╗ ████║██╔══██╗
    █████╗  ██║██║     ██║   ██║██╔████╔██║███████║
    ██╔══╝  ██║██║     ██║   ██║██║╚██╔╝██║██╔══██║
    ██║     ██║███████╗╚██████╔╝██║ ╚═╝ ██║██║  ██║
    ╚═╝     ╚═╝╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝

         AI Filesystem Analysis via MCP
EOF
    echo ""
}

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Darwin*)    echo "macos";;
        Linux*)     echo "linux";;
        MINGW*|MSYS*|CYGWIN*) echo "windows";;
        *)          echo "unknown";;
    esac
}

# Check if uv is installed
check_uv() {
    if command -v uv &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Get Claude Desktop config path
get_claude_config_path() {
    local os="$1"
    case "$os" in
        macos)
            echo "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
            ;;
        linux)
            echo "$HOME/.config/Claude/claude_desktop_config.json"
            ;;
        windows)
            echo "$(cygpath "$APPDATA")/Claude/claude_desktop_config.json"
            ;;
        *)
            echo ""
            ;;
    esac
}

# Get Cursor config path
get_cursor_config_path() {
    local os="$1"
    case "$os" in
        macos|linux)
            echo "$HOME/.cursor/mcp.json"
            ;;
        windows)
            echo "$(cygpath "$USERPROFILE")/.cursor/mcp.json"
            ;;
        *)
            echo ""
            ;;
    esac
}

# Get Goose config path
get_goose_config_path() {
    local os="$1"
    case "$os" in
        macos|linux)
            echo "$HOME/.config/goose/config.yaml"
            ;;
        windows)
            echo "$(cygpath "$USERPROFILE")/.config/goose/config.yaml"
            ;;
        *)
            echo ""
            ;;
    esac
}

# Generate Goose YAML config
generate_goose_config() {
    cat << 'EOF'
extensions:
  filoma:
    type: stdio
    cmd: uvx
    args:
      - "--python"
      - ">=3.11"
      - filoma
      - mcp
      - serve
    enabled: true
EOF
}

# Generate MCP config JSON
generate_config() {
    cat << 'EOF'
{
  "mcpServers": {
    "filoma": {
      "command": "uvx",
      "args": ["--python", ">=3.11", "filoma", "mcp", "serve"]
    }
  }
}
EOF
}

# Generate MCP config with uv fallback
generate_config_with_uv() {
    cat << 'EOF'
{
  "mcpServers": {
    "filoma": {
      "command": "uv",
      "args": ["run", "--python", ">=3.11", "filoma", "mcp", "serve"]
    }
  }
}
EOF
}

# Main installation flow
main() {
    print_banner

    OS=$(detect_os)
    echo -e "${BLUE}→ Detected OS: $OS${NC}"
    echo ""

    # Check uv
    if check_uv; then
        UV_VERSION=$(uv --version 2>/dev/null | head -n1)
        echo -e "${GREEN}✓ uv is installed: $UV_VERSION${NC}"
        USE_UVX=true
    else
        echo -e "${YELLOW}! uv not found. Installing uv first...${NC}"
        echo ""
        echo "Run this command to install uv:"
        echo -e "${BLUE}  curl -LsSf https://astral.sh/uv/install.sh | sh${NC}"
        echo ""
        echo "Then re-run this installer."
        exit 1
    fi

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  MCP Configuration${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""

    # Config paths
    CLAUDE_CONFIG=$(get_claude_config_path "$OS")
    CURSOR_CONFIG=$(get_cursor_config_path "$OS")
    GOOSE_CONFIG=$(get_goose_config_path "$OS")

    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  🦆 Goose + Ollama (Recommended - Local & Private)${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""

    # Check if Goose is installed
    if command -v goose &> /dev/null; then
        echo -e "${GREEN}✓ Goose is installed${NC}"
        if [ -n "$GOOSE_CONFIG" ]; then
            echo -e "${GREEN}Goose config path:${NC}"
            echo "  $GOOSE_CONFIG"
        fi
    else
        echo -e "${YELLOW}○ Goose not found${NC}"
        echo "  Install: curl -fsSL https://raw.githubusercontent.com/block/goose/main/install.sh | bash"
    fi

    echo ""
    echo -e "${GREEN}Goose YAML Configuration:${NC}"
    echo ""
    generate_goose_config
    echo ""
    echo "Add the above to: $GOOSE_CONFIG"
    echo "Or run: goose configure"
    echo ""

    # Check Ollama
    if command -v ollama &> /dev/null; then
        echo -e "${GREEN}✓ Ollama is installed${NC}"
        echo -e "${YELLOW}  Recommended: ollama pull qwen2.5:14b (best for MCP)${NC}"
    else
        echo -e "${YELLOW}○ Ollama not found${NC}"
        echo "  Install: curl -fsSL https://ollama.ai/install.sh | sh"
    fi

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  🌐 Cloud Assistants (Claude/Cursor)${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""

    # Show config paths
    if [ -n "$CLAUDE_CONFIG" ]; then
        echo -e "${GREEN}Claude Desktop config:${NC}"
        echo "  $CLAUDE_CONFIG"
    fi

    if [ -n "$CURSOR_CONFIG" ]; then
        echo -e "${GREEN}Cursor config:${NC}"
        echo "  $CURSOR_CONFIG"
    fi

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Configuration JSON${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""

    if [ "$USE_UVX" = true ]; then
        echo -e "${GREEN}Using uvx (recommended):${NC}"
        echo ""
        generate_config
    else
        echo -e "${YELLOW}Using uv run:${NC}"
        echo ""
        generate_config_with_uv
    fi

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Next Steps${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""

    # Goose next steps
    if [ -n "$GOOSE_CONFIG" ]; then
        echo -e "${GREEN}🦆 Goose Setup:${NC}"
        if [ -f "$GOOSE_CONFIG" ]; then
            echo "  1. Edit: $GOOSE_CONFIG"
        else
            echo "  1. Run: goose configure"
            echo "     Or create: $GOOSE_CONFIG"
        fi
        echo "  2. Add the YAML config shown above"
        echo "  3. Ensure Ollama is running: ollama serve"
        echo "  4. Start a Goose session: goose session"
        echo ""
    fi

    # Check if configs exist and offer to show commands
    if [ -n "$CLAUDE_CONFIG" ] && [ -f "$CLAUDE_CONFIG" ]; then
        echo -e "${GREEN}✓ Claude Desktop config exists${NC}"
        echo "  Add the JSON above to: $CLAUDE_CONFIG"
        echo "  Then restart Claude Desktop"
    elif [ -n "$CLAUDE_CONFIG" ]; then
        echo -e "${YELLOW}○ Claude Desktop config not found${NC}"
        echo "  Create: $CLAUDE_CONFIG"
        echo "  And add the JSON above"
    fi

    echo ""

    if [ -n "$CURSOR_CONFIG" ] && [ -f "$CURSOR_CONFIG" ]; then
        echo -e "${GREEN}✓ Cursor config exists${NC}"
        echo "  Add the JSON above to: $CURSOR_CONFIG"
        echo "  Or go to Settings → MCP → Add Server"
    elif [ -n "$CURSOR_CONFIG" ]; then
        echo -e "${YELLOW}○ Cursor config not found${NC}"
        echo "  Create: $CURSOR_CONFIG"
        echo "  Or go to Settings → MCP → Add Server"
    fi

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Once configured, you can:"
    echo "  • Ask Goose/Claude/Cursor about files in your project"
    echo "  • Run 'filoma brain chat' for interactive mode"
    echo "  • Visit https://filoma.io for documentation"
    echo ""
    echo -e "${YELLOW}Note: First run may take a moment as uvx downloads filoma${NC}"
    echo ""
}

# Run main function
main "$@"
