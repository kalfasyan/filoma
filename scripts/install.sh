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

# Get nanobot config path
get_nanobot_config_path() {
    echo "$HOME/.nanobot/config.json"
}

# Generate nanobot MCP config JSON snippet
generate_nanobot_config() {
    cat << 'EOF'
"mcpServers": {
  "filoma": {
    "command": "uvx",
    "args": ["--python", ">=3.11", "filoma", "mcp", "serve"]
  }
}
EOF
}

# Generate full nanobot config with Ollama
generate_full_nanobot_config() {
    cat << 'EOF'
{
  "agents": {
    "defaults": {
      "provider": "ollama",
      "model": "qwen2.5:14b"
    }
  },
  "providers": {
    "ollama": {
      "apiBase": "http://localhost:11434/v1"
    }
  },
  "mcpServers": {
    "filoma": {
      "command": "uvx",
      "args": ["--python", ">=3.11", "filoma", "mcp", "serve"]
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
    echo -e "${BLUE}  MCP Configuration with Nanobot${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""

    # Config path
    NANOBOT_CONFIG=$(get_nanobot_config_path)

    # Check if nanobot is installed
    if command -v nanobot &> /dev/null; then
        echo -e "${GREEN}✓ nanobot is installed${NC}"
        echo -e "${GREEN}Config path:${NC}"
        echo "  $NANOBOT_CONFIG"
    else
        echo -e "${YELLOW}○ nanobot not found${NC}"
        echo "  Install: uv tool install nanobot-ai"
        echo "  Then run: nanobot onboard"
    fi

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  🤖 nanobot + Ollama (Local & Private)${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
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
    echo -e "${BLUE}  Full Configuration${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""
    generate_full_nanobot_config

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  MCP Server Snippet${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Add this to your existing nanobot config:"
    echo ""
    generate_nanobot_config

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Next Steps${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""

    echo -e "${GREEN}1. Install nanobot:${NC}"
    echo "   uv tool install nanobot-ai"
    echo "   nanobot onboard"
    echo ""
    echo -e "${GREEN}2. Create/edit nanobot config:${NC}"
    echo "   $NANOBOT_CONFIG"
    echo ""
    echo -e "${GREEN}3. Add the configuration above${NC}"
    echo ""
    echo -e "${GREEN}4. Ensure Ollama is running:${NC}"
    echo "   ollama serve"
    echo ""
    echo -e "${GREEN}5. Test nanobot:${NC}"
    echo "   nanobot agent --logs -m \"hello\""
    echo "   nanobot agent -m \"probe directory ~/my/project\""
    echo ""

    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Once configured, you can:"
    echo "  • Ask nanobot about files in your project"
    echo "  • Run 'filoma brain chat' for interactive mode"
    echo "  • Visit https://filoma.io for documentation"
    echo ""
    echo -e "${YELLOW}Tips:${NC}"
    echo "  • Use '--logs' to see tool calls and debug issues"
    echo "  • apiBase must include '/v1' for Ollama"
    echo "  • First run may take a moment as uvx downloads filoma"
    echo ""
}

# Run main function
main "$@"
