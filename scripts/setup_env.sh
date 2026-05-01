#!/usr/bin/env bash
# Filoma Environment Setup Script
# Interactive wizard to configure provider and environment variables for filoma filaraki.
# Usage: bash scripts/setup_env.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Output file
ENV_FILE=".env"

print_banner() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${BOLD}Filoma Environment Setup Wizard${NC}                          ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  Configure your AI provider for filoma filaraki            ${CYAN}║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}▶${NC} ${BOLD}$1${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

print_info() {
    echo -e "  ${CYAN}ℹ${NC} $1"
}

# Prompt user for input with a default value
# Usage: prompt_input "message" "default_value" "variable_name"
prompt_input() {
    local message="$1"
    local default="$2"
    local varname="$3"
    local input

    if [ -n "$default" ]; then
        echo -ne "  ${message} ${YELLOW}[${default}]${NC}: "
    else
        echo -ne "  ${message}: "
    fi
    read -r input
    if [ -z "$input" ]; then
        input="$default"
    fi
    printf -v "$varname" '%s' "$input"
}

# Prompt for a secret (no echo)
prompt_secret() {
    local message="$1"
    local varname="$2"
    local input

    echo -ne "  ${message}: "
    read -rs input
    echo ""
    printf -v "$varname" '%s' "$input"
}

# Write a line to the .env file
write_env() {
    echo "$1" >> "$ENV_FILE"
}

# Check if .env already exists
check_existing_env() {
    if [ -f "$ENV_FILE" ]; then
        echo ""
        print_warning "An existing ${ENV_FILE} file was found."
        echo -ne "  Overwrite it? (y/N): "
        read -r confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            echo ""
            print_info "Setup cancelled. Your existing ${ENV_FILE} is unchanged."
            exit 0
        fi
        echo ""
    fi
}

# Provider selection menu
select_provider() {
    echo ""
    print_step "Select your AI provider:"
    echo ""
    echo -e "  ${BOLD}1)${NC} Ollama         — Local, private, zero-cost (requires Ollama installed)"
    echo -e "  ${BOLD}2)${NC} Mistral AI     — European cloud, excellent tool-calling"
    echo -e "  ${BOLD}3)${NC} Google Gemini  — Google cloud, generous free tier"
    echo -e "  ${BOLD}4)${NC} OpenAI         — OpenAI API (GPT-4o, etc.)"
    echo -e "  ${BOLD}5)${NC} OpenRouter     — Access to Claude, GPT-4, Llama, Gemini, and more"
    echo -e "  ${BOLD}6)${NC} Other          — Any OpenAI-compatible endpoint"
    echo ""
    echo -ne "  Enter your choice (1-6): "
    read -r choice
    echo ""
}

# Setup Ollama
setup_ollama() {
    print_step "Configuring Ollama (local provider)"
    echo ""
    print_info "Ollama runs locally — no API key needed."
    print_info "Make sure Ollama is running: ollama serve"
    echo ""

    prompt_input "Model name" "qwen2.5:14b" "MODEL"
    prompt_input "Base URL (leave empty for auto-detection)" "" "BASE_URL"

    # Write .env
    write_env "# Filoma Filaraki - Ollama (Local)"
    write_env "FILOMA_FILARAKI_MODEL=${MODEL}"
    if [ -n "$BASE_URL" ]; then
        write_env "FILOMA_FILARAKI_BASE_URL=${BASE_URL}"
    else
        write_env "# FILOMA_FILARAKI_BASE_URL=http://localhost:11434/v1  # Auto-detected"
    fi

    echo ""
    print_success "Ollama configured with model: ${MODEL}"
    print_info "Recommended models: qwen2.5:14b, dolphincoder, codellama, deepseek-coder"
    print_info "Pull your model: ollama pull ${MODEL}"
}

# Setup Mistral
setup_mistral() {
    print_step "Configuring Mistral AI"
    echo ""
    print_info "Get your API key at: https://console.mistral.ai/"
    echo ""

    prompt_secret "Mistral API key" "API_KEY"
    if [ -z "$API_KEY" ]; then
        print_warning "No API key provided. You'll need to set MISTRAL_API_KEY before using filoma."
    fi
    prompt_input "Model name" "mistral-small-latest" "MODEL"

    # Write .env
    write_env "# Filoma Filaraki - Mistral AI"
    write_env "MISTRAL_API_KEY=${API_KEY}"
    write_env "FILOMA_FILARAKI_MODEL=mistral:${MODEL}"

    echo ""
    print_success "Mistral AI configured with model: ${MODEL}"
}

# Setup Gemini
setup_gemini() {
    print_step "Configuring Google Gemini"
    echo ""
    print_info "Get your API key at: https://aistudio.google.com/"
    echo ""

    prompt_secret "Gemini API key" "API_KEY"
    if [ -z "$API_KEY" ]; then
        print_warning "No API key provided. You'll need to set GEMINI_API_KEY before using filoma."
    fi
    prompt_input "Model name" "gemini-1.5-flash" "MODEL"

    # Write .env
    write_env "# Filoma Filaraki - Google Gemini"
    write_env "GEMINI_API_KEY=${API_KEY}"
    write_env "FILOMA_FILARAKI_MODEL=${MODEL}"

    echo ""
    print_success "Google Gemini configured with model: ${MODEL}"
}

# Setup OpenAI
setup_openai() {
    print_step "Configuring OpenAI"
    echo ""
    print_info "Get your API key at: https://platform.openai.com/api-keys"
    echo ""

    prompt_secret "OpenAI API key" "API_KEY"
    if [ -z "$API_KEY" ]; then
        print_warning "No API key provided. You'll need to set OPENAI_API_KEY before using filoma."
    fi
    prompt_input "Model name" "gpt-4o-mini" "MODEL"

    # Write .env
    write_env "# Filoma Filaraki - OpenAI"
    write_env "FILOMA_FILARAKI_BASE_URL=https://api.openai.com/v1"
    write_env "OPENAI_API_KEY=${API_KEY}"
    write_env "FILOMA_FILARAKI_MODEL=${MODEL}"

    echo ""
    print_success "OpenAI configured with model: ${MODEL}"
}

# Setup OpenRouter
setup_openrouter() {
    print_step "Configuring OpenRouter"
    echo ""
    print_info "Get your API key at: https://openrouter.ai/keys"
    print_info "OpenRouter gives access to Claude, GPT-4, Llama, Gemini, and more."
    echo ""

    prompt_secret "OpenRouter API key" "API_KEY"
    if [ -z "$API_KEY" ]; then
        print_warning "No API key provided. You'll need to set OPENAI_API_KEY before using filoma."
    fi
    prompt_input "Model name" "anthropic/claude-3.5-sonnet" "MODEL"

    # Write .env
    write_env "# Filoma Filaraki - OpenRouter"
    write_env "FILOMA_FILARAKI_BASE_URL=https://openrouter.ai/api/v1"
    write_env "OPENAI_API_KEY=${API_KEY}"
    write_env "FILOMA_FILARAKI_MODEL=${MODEL}"

    echo ""
    print_success "OpenRouter configured with model: ${MODEL}"
    print_info "Popular models: anthropic/claude-3.5-sonnet, openai/gpt-4o, meta-llama/llama-3-70b"
}

# Setup other OpenAI-compatible endpoint
setup_other() {
    print_step "Configuring OpenAI-compatible endpoint"
    echo ""
    print_info "This works with any provider that offers an OpenAI-compatible API."
    print_info "Examples: Together AI, Azure OpenAI, Anyscale, vLLM, LM Studio, etc."
    echo ""

    prompt_input "Base URL (e.g. https://api.together.xyz/v1)" "" "BASE_URL"
    if [ -z "$BASE_URL" ]; then
        print_warning "Base URL is required for custom endpoints."
        echo -ne "  Base URL: "
        read -r BASE_URL
    fi
    prompt_secret "API key" "API_KEY"
    if [ -z "$API_KEY" ]; then
        print_warning "No API key provided. You'll need to set OPENAI_API_KEY before using filoma."
    fi
    prompt_input "Model name" "gpt-4o-mini" "MODEL"

    # Write .env
    write_env "# Filoma Filaraki - OpenAI-compatible (${BASE_URL})"
    write_env "FILOMA_FILARAKI_BASE_URL=${BASE_URL}"
    write_env "OPENAI_API_KEY=${API_KEY}"
    write_env "FILOMA_FILARAKI_MODEL=${MODEL}"

    echo ""
    print_success "Custom endpoint configured: ${BASE_URL} with model: ${MODEL}"
}

# Print final instructions
print_final() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}${BOLD}Setup complete!${NC} Configuration saved to ${BOLD}${ENV_FILE}${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${BOLD}Next steps:${NC}"
    echo ""
    echo -e "  1. Start chatting:"
    echo -e "     ${BLUE}uv run --env-file .env filoma filaraki chat${NC}"
    echo ""
    echo -e "  2. Or export variables to your shell:"
    echo -e "     ${BLUE}export \$(cat .env | grep -v '^#' | xargs)${NC}"
    echo -e "     ${BLUE}uvx filoma filaraki chat${NC}"
    echo ""
    echo -e "  3. For persistent configuration, add exports to your shell profile"
    echo -e "     (e.g. ~/.bashrc, ~/.zshrc)."
    echo ""
    echo -e "  ${CYAN}ℹ${NC} Run this script again anytime to reconfigure."
    echo -e "  ${CYAN}ℹ${NC} See .env_example for all available options."
    echo ""
}

# Main
main() {
    print_banner
    check_existing_env

    select_provider

    # Start fresh .env
    : > "$ENV_FILE"
    write_env "# Generated by filoma setup wizard ($(date +%Y-%m-%d))"
    write_env ""

    case "$choice" in
        1) setup_ollama ;;
        2) setup_mistral ;;
        3) setup_gemini ;;
        4) setup_openai ;;
        5) setup_openrouter ;;
        6) setup_other ;;
        *)
            print_warning "Invalid choice. Please run the script again and select 1-6."
            rm -f "$ENV_FILE"
            exit 1
            ;;
    esac

    print_final
}

main "$@"
