#!/usr/bin/env sh
# Filoma + nanobot + Ollama — Local AI Setup
# ------------------------------------------------------------
# Installs everything needed to run Filoma Filaraki fully offline:
#   1. uv          (https://docs.astral.sh/uv/)
#   2. Ollama      (https://ollama.com)              [local LLM runtime]
#   3. nanobot-ai  (https://github.com/HKUDS/nanobot) [MCP-aware agent]
#   4. Configures ~/.nanobot/config.json with Filoma's MCP server
#
# Usage:
#   curl -sL https://raw.githubusercontent.com/kalfasyan/filoma/main/scripts/install.sh | sh
#
# Environment flags:
#   FILOMA_INSTALL_YES=1            skip confirmation prompts
#   FILOMA_INSTALL_DRY_RUN=1        show actions without executing
#   FILOMA_INSTALL_SKIP_OLLAMA=1    don't touch Ollama
#   FILOMA_INSTALL_SKIP_NANOBOT=1   don't touch nanobot
#   FILOMA_INSTALL_MODEL=<name>     default model written into nanobot config
#
# This script is POSIX-shell compatible (works under bash, dash, zsh).
# ------------------------------------------------------------

set -eu

# ---------- constants ----------
NANOBOT_CONFIG_DIR="${HOME}/.nanobot"
NANOBOT_CONFIG_PATH="${NANOBOT_CONFIG_DIR}/config.json"
DEFAULT_MODEL="${FILOMA_INSTALL_MODEL:-qwen2.5:7b}"
DOC_URL="https://github.com/kalfasyan/filoma/blob/main/docs/guides/filaraki.md#mcp-server-configuration-with-nanobot"

# ---------- colors (auto-disabled if not a TTY) ----------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED="$(printf '\033[0;31m')"
    GREEN="$(printf '\033[0;32m')"
    YELLOW="$(printf '\033[1;33m')"
    BLUE="$(printf '\033[0;34m')"
    BOLD="$(printf '\033[1m')"
    NC="$(printf '\033[0m')"
else
    RED=""; GREEN=""; YELLOW=""; BLUE=""; BOLD=""; NC=""
fi

# ---------- helpers ----------
log()  { printf '%s→%s %s\n' "$BLUE" "$NC" "$*"; }
ok()   { printf '%s✓%s %s\n' "$GREEN" "$NC" "$*"; }
warn() { printf '%s!%s %s\n' "$YELLOW" "$NC" "$*"; }
fail() { printf '%s✗%s %s\n' "$RED" "$NC" "$*" >&2; exit 1; }

step() {
    printf '\n%s═══════════════════════════════════════════════════════%s\n' "$BLUE" "$NC"
    printf '%s  %s%s%s\n'                                                   "$BLUE" "$BOLD" "$*" "$NC"
    printf '%s═══════════════════════════════════════════════════════%s\n' "$BLUE" "$NC"
}

is_yes()       { [ "${FILOMA_INSTALL_YES:-0}" = "1" ]; }
is_dry()       { [ "${FILOMA_INSTALL_DRY_RUN:-0}" = "1" ]; }
skip_ollama()  { [ "${FILOMA_INSTALL_SKIP_OLLAMA:-0}" = "1" ]; }
skip_nanobot() { [ "${FILOMA_INSTALL_SKIP_NANOBOT:-0}" = "1" ]; }
have()         { command -v "$1" >/dev/null 2>&1; }

# Prompt helper that works even when the script is piped from curl.
# Returns 0 (yes) / 1 (no). Auto-yes when FILOMA_INSTALL_YES=1.
confirm() {
    prompt="$1"
    if is_yes; then
        return 0
    fi
    # When running as `curl ... | sh`, stdin is the script. Reopen /dev/tty.
    if [ ! -t 0 ]; then
        if [ -r /dev/tty ]; then
            exec </dev/tty
        else
            warn "Non-interactive shell — assuming \"no\". Set FILOMA_INSTALL_YES=1 to skip prompts."
            return 1
        fi
    fi
    printf '%s%s%s [y/N]: ' "$YELLOW" "$prompt" "$NC"
    read -r ans || return 1
    case "$ans" in
        y|Y|yes|YES|Yes) return 0 ;;
        *)               return 1 ;;
    esac
}

# Run a command (or just echo it under --dry-run).
run() {
    if is_dry; then
        printf '  %s[dry-run]%s %s\n' "$YELLOW" "$NC" "$*"
        return 0
    fi
    sh -c "$*"
}

detect_os() {
    case "$(uname -s)" in
        Darwin*)              echo macos   ;;
        Linux*)               echo linux   ;;
        MINGW*|MSYS*|CYGWIN*) echo windows ;;
        *)                    echo unknown ;;
    esac
}

banner() {
    cat <<'EOF'
    ███████╗██╗██╗      ██████╗ ███╗   ███╗ █████╗
    ██╔════╝██║██║     ██╔═══██╗████╗ ████║██╔══██╗
    █████╗  ██║██║     ██║   ██║██╔████╔██║███████║
    ██╔══╝  ██║██║     ██║   ██║██║╚██╔╝██║██╔══██║
    ██║     ██║███████╗╚██████╔╝██║ ╚═╝ ██║██║  ██║
    ╚═╝     ╚═╝╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝

       Local AI for your filesystem  ·  nanobot + Ollama + Filoma MCP
EOF
}

# ---------- install steps ----------

install_uv() {
    if have uv; then
        ok "uv already installed: $(uv --version 2>/dev/null | head -n1)"
        return 0
    fi
    log "Installing uv (Astral's Python tool manager)…"
    if ! confirm "Install uv via the official installer?"; then
        fail "uv is required. Install it manually: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
    run "curl -LsSf https://astral.sh/uv/install.sh | sh"
    # uv installs to $HOME/.local/bin (or $HOME/.cargo/bin on older versions)
    PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    export PATH
    if ! is_dry && ! have uv; then
        fail "uv installer finished but 'uv' is not on PATH. Restart your shell and re-run this script."
    fi
    ok "uv installed."
}

install_ollama() {
    if skip_ollama; then
        warn "Skipping Ollama install (FILOMA_INSTALL_SKIP_OLLAMA=1)"
        return 0
    fi
    if have ollama; then
        ok "Ollama already installed: $(ollama --version 2>/dev/null | head -n1)"
        return 0
    fi
    log "Ollama runs LLMs locally and is required for offline operation."
    log "Source: https://ollama.com/install.sh  (may prompt for sudo on Linux)"
    if ! confirm "Install Ollama via its official installer?"; then
        warn "Skipping Ollama. Install later from https://ollama.com — Filoma's MCP server will still work, but nanobot needs an LLM."
        return 0
    fi
    run "curl -fsSL https://ollama.com/install.sh | sh"
    if ! is_dry && ! have ollama; then
        warn "Ollama installer finished but 'ollama' is not on PATH yet. Restart your shell or check the installer output."
    else
        ok "Ollama installed."
    fi
}

install_nanobot() {
    if skip_nanobot; then
        warn "Skipping nanobot install (FILOMA_INSTALL_SKIP_NANOBOT=1)"
        return 0
    fi
    if have nanobot; then
        ok "nanobot already installed."
        return 0
    fi
    log "Installing nanobot-ai via 'uv tool install'…"
    run "uv tool install nanobot-ai"
    PATH="$HOME/.local/bin:$PATH"
    export PATH
    if ! is_dry && ! have nanobot; then
        warn "'nanobot' is not on PATH yet. Run \`uv tool update-shell\` and restart your shell."
    else
        ok "nanobot installed."
    fi
}

write_nanobot_config() {
    log "Configuring nanobot for Filoma + Ollama…"
    if is_dry; then
        printf '  %s[dry-run]%s would write/merge %s\n' "$YELLOW" "$NC" "$NANOBOT_CONFIG_PATH"
        return 0
    fi

    mkdir -p "$NANOBOT_CONFIG_DIR"

    if [ ! -f "$NANOBOT_CONFIG_PATH" ]; then
        cat > "$NANOBOT_CONFIG_PATH" <<EOF
{
  "agents": {
    "defaults": {
      "provider": "ollama",
      "model": "${DEFAULT_MODEL}"
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
      "args": ["--python", "3.11", "filoma", "mcp", "serve"]
    }
  }
}
EOF
        ok "Wrote new config: $NANOBOT_CONFIG_PATH"
        return 0
    fi

    # Existing config: merge non-destructively with Python.
    backup="${NANOBOT_CONFIG_PATH}.bak.$(date +%s)"
    cp "$NANOBOT_CONFIG_PATH" "$backup"
    log "Backed up existing config to: $backup"

    py="$(command -v python3 || command -v python || true)"
    if [ -z "$py" ]; then
        warn "Could not find 'python3' to merge the existing config. Original left untouched."
        warn "Add this snippet manually under 'mcpServers' in $NANOBOT_CONFIG_PATH:"
        cat <<EOF

  "filoma": {
    "command": "uvx",
    "args": ["--python", "3.11", "filoma", "mcp", "serve"]
  }

EOF
        return 0
    fi

    FILOMA_CFG_PATH="$NANOBOT_CONFIG_PATH" \
    FILOMA_CFG_MODEL="$DEFAULT_MODEL" \
    "$py" - <<'PY'
import json, os, pathlib, sys

path = pathlib.Path(os.environ["FILOMA_CFG_PATH"])
model = os.environ["FILOMA_CFG_MODEL"]

try:
    cfg = json.loads(path.read_text())
    if not isinstance(cfg, dict):
        raise ValueError("top-level config is not an object")
except Exception as exc:  # noqa: BLE001
    print(f"!! Could not parse existing config ({exc}); leaving it untouched.", file=sys.stderr)
    sys.exit(2)

agents = cfg.setdefault("agents", {})
defaults = agents.setdefault("defaults", {})
defaults.setdefault("provider", "ollama")
defaults.setdefault("model", model)

providers = cfg.setdefault("providers", {})
ollama = providers.setdefault("ollama", {})
ollama.setdefault("apiBase", "http://localhost:11434/v1")

mcp = cfg.setdefault("mcpServers", {})
mcp["filoma"] = {
    "command": "uvx",
    "args": ["--python", "3.11", "filoma", "mcp", "serve"],
}

path.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"merged into {path}")
PY
    ok "Merged Filoma MCP server into existing config."
}

print_next_steps() {
    cat <<EOF

${BOLD}Next steps${NC}

  1. Pull a tool-calling model (one-time, ~4.7 GB for qwen2.5:7b):
     ${GREEN}ollama pull ${DEFAULT_MODEL}${NC}

  2. Make sure Ollama is running (${YELLOW}skip on Linux — installer starts a service${NC}):
     ${GREEN}ollama serve${NC}

  3. Talk to your filesystem via nanobot:
     ${GREEN}nanobot agent --logs -m "probe directory ~/my/project"${NC}

  4. Or use Filoma's built-in chat (after \`pip install filoma\`):
     ${GREEN}filoma chat${NC}

${BOLD}Config:${NC} ${NANOBOT_CONFIG_PATH}
${BOLD}Docs:${NC}   ${DOC_URL}

${YELLOW}Tip:${NC} run \`nanobot agent --logs\` while debugging — it shows tool calls.
${YELLOW}Tip:${NC} \`apiBase\` must end in \`/v1\` for Ollama (handled for you).

EOF
}

main() {
    banner

    OS="$(detect_os)"
    log "Detected OS: $OS"
    case "$OS" in
        macos|linux) ;;
        windows)     fail "Windows is not directly supported. Run this installer inside WSL." ;;
        *)           fail "Unsupported OS: $(uname -s)." ;;
    esac

    if is_dry; then
        warn "DRY-RUN MODE — no changes will be made."
    fi

    step "1/4  Install uv"
    install_uv

    step "2/4  Install Ollama"
    install_ollama

    step "3/4  Install nanobot"
    install_nanobot

    step "4/4  Configure nanobot for Filoma + Ollama"
    write_nanobot_config

    step "Done"
    ok "Filoma + nanobot + Ollama is set up."
    print_next_steps
}

main "$@"
