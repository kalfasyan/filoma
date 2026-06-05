#!/usr/bin/env bash
# Filoma Environment Setup Script
# Interactive wizard to configure provider and environment variables for filoma filaraki.
# Usage: filoma setup   (preferred)
#        bash src/filoma/scripts/setup_env.sh   (from a repo checkout)

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
#
# Probes likely Ollama hosts (localhost; on WSL2 also the Windows-host
# default gateway), queries /api/tags to surface models the user has
# actually pulled, and pre-fills the URL field accordingly. Falls back
# cleanly when curl is missing or no daemon answers.
setup_ollama() {
    print_step "Configuring Ollama (local provider)"
    echo ""
    print_info "Ollama runs locally — no API key needed."

    local detected_url=""
    local detected_models=""
    local default_model="qwen2.5:7b"   # safe public default with tool calling
    local candidate
    local candidates=("http://localhost:11434")

    # On WSL2, also try the Windows host (Ollama frequently runs there).
    if grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
        local gw
        gw=$(ip route show default 2>/dev/null | awk '{print $3; exit}')
        if [ -n "$gw" ] && [ "$gw" != "127.0.0.1" ]; then
            candidates+=("http://${gw}:11434")
            print_info "WSL2 detected — also probing Windows host at ${gw}:11434."
        fi
    fi

    # Pick the JSON parser: prefer python3 (filoma already requires it),
    # fall back to a tolerant grep+sed pipeline.
    parse_models() {
        local body="$1"
        if command -v python3 >/dev/null 2>&1; then
            printf '%s' "$body" | python3 -c "import json,sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for m in data.get('models', [])[:10]:
    name = m.get('name') or m.get('model')
    if name:
        print(name)"
        else
            printf '%s' "$body" \
                | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]+"' \
                | sed -E 's/"name"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/' \
                | head -10
        fi
    }

    # Embedding-only models can't drive chat / tool calls — skip them when
    # picking the default but still mention them in the visible list.
    pick_default_model() {
        local first_chat
        first_chat=$(printf '%s' "$1" | grep -viE 'embed|embedding' | head -1)
        if [ -n "$first_chat" ]; then
            printf '%s' "$first_chat"
        else
            printf '%s' "$1" | head -1
        fi
    }

    # Validate an Ollama model name. Real names are like "name" or
    # "namespace/name:tag" — letters/digits with ., _, -, /, : only. No
    # spaces. Catches the classic typo of pasting a CLI command into the
    # model prompt.
    is_valid_model_name() {
        local name="$1"
        [ -n "$name" ] && [[ "$name" =~ ^[A-Za-z0-9._/-]+(:[A-Za-z0-9._-]+)?$ ]]
    }

    # Interactive picker: when we have a list of pulled models, show a
    # numbered menu (with chat / embedding labels) so users select by
    # index instead of retyping. Free-text input is still allowed for
    # models the user plans to ``ollama pull`` next.
    #
    # Writes the chosen model name into the variable named by the third
    # argument via ``printf -v``. Doing this (instead of returning the
    # value on stdout) keeps the UI prints from being captured by
    # command substitution at the call site.
    pick_model_interactive() {
        local list_csv="$1"     # comma-space separated
        local default="$2"
        local outvar="$3"
        local input

        if [ -z "$list_csv" ]; then
            # No daemon / no list — fall back to the simple prompt with
            # validation.
            while true; do
                prompt_input "Model name" "$default" "input"
                if is_valid_model_name "$input"; then
                    printf -v "$outvar" '%s' "$input"
                    return
                fi
                print_warning "Invalid Ollama model name: '${input}' (no spaces; use name[:tag])."
            done
        fi

        # Convert "a, b, c" → indexed array.
        local IFS_BAK="$IFS"
        IFS=',' read -ra MODELS <<<"$list_csv"
        IFS="$IFS_BAK"
        local i=0
        local default_index=1
        local model_trimmed
        echo ""
        echo -e "  ${BOLD}Pulled models:${NC}"
        for raw in "${MODELS[@]}"; do
            i=$((i + 1))
            model_trimmed="${raw#"${raw%%[![:space:]]*}"}"
            MODELS[$((i - 1))]="$model_trimmed"
            local label=""
            if [[ "$model_trimmed" =~ embed|embedding ]]; then
                label=" ${YELLOW}(embedding-only — not suitable for chat)${NC}"
            fi
            if [ "$model_trimmed" = "$default" ]; then
                default_index=$i
                echo -e "    ${BOLD}${i})${NC} ${model_trimmed}${label} ${CYAN}← default${NC}"
            else
                echo -e "    ${BOLD}${i})${NC} ${model_trimmed}${label}"
            fi
        done
        echo -e "    ${BOLD}o)${NC} other (type a different model name to pull later)"
        echo ""

        while true; do
            echo -ne "  Pick a model (number or full name) ${YELLOW}[${default_index}: ${default}]${NC}: "
            read -r input
            if [ -z "$input" ]; then
                printf -v "$outvar" '%s' "$default"
                return
            fi
            if [[ "$input" =~ ^[0-9]+$ ]] && [ "$input" -ge 1 ] && [ "$input" -le "${#MODELS[@]}" ]; then
                printf -v "$outvar" '%s' "${MODELS[$((input - 1))]}"
                return
            fi
            if [[ "$input" =~ ^[oO]$ ]] || [[ "$input" =~ ^[oO]ther$ ]]; then
                while true; do
                    echo -ne "  Custom model name (e.g. qwen2.5:7b): "
                    read -r input
                    if is_valid_model_name "$input"; then
                        printf -v "$outvar" '%s' "$input"
                        return
                    fi
                    print_warning "Invalid Ollama model name: '${input}' (no spaces; use name[:tag])."
                done
            fi
            if is_valid_model_name "$input"; then
                printf -v "$outvar" '%s' "$input"
                return
            fi
            print_warning "Pick a number 1–${#MODELS[@]}, type 'o' for other, or enter a valid model name."
        done
    }

    if command -v curl >/dev/null 2>&1; then
        for candidate in "${candidates[@]}"; do
            local body
            body=$(curl -sS --max-time 1.5 "${candidate}/api/tags" 2>/dev/null || true)
            if [ -n "$body" ] && [[ "$body" == *'"models"'* ]]; then
                local models_raw
                models_raw=$(parse_models "$body")
                if [ -n "$models_raw" ]; then
                    detected_url="${candidate}/v1"
                    default_model=$(pick_default_model "$models_raw")
                    detected_models=$(printf '%s' "$models_raw" | tr '\n' ',' | sed 's/,$//; s/,/, /g')
                    break
                fi
            fi
        done
    fi

    echo ""
    if [ -n "$detected_url" ]; then
        print_success "Found Ollama at ${detected_url}"
    else
        print_info "No Ollama daemon detected. Make sure it's running: ollama serve"
    fi

    MODEL=""
    pick_model_interactive "$detected_models" "$default_model" "MODEL"
    echo ""
    prompt_input "Base URL (leave empty for auto-detected / localhost)" "$detected_url" "BASE_URL"

    # Write .env
    write_env "# Filoma Filaraki - Ollama (Local)"
    write_env "FILOMA_FILARAKI_MODEL=${MODEL}"
    if [ -n "$BASE_URL" ]; then
        write_env "FILOMA_FILARAKI_BASE_URL=${BASE_URL}"
    else
        write_env "FILOMA_FILARAKI_BASE_URL=http://localhost:11434/v1"
    fi

    echo ""
    print_success "Ollama configured with model: ${MODEL}"
    if [ -z "$detected_models" ]; then
        print_info "Recommended models: qwen2.5:7b, qwen3:8b, llama3.2:3b, deepseek-coder"
    fi
    print_info "Pull your model if you haven't already: ollama pull ${MODEL}"
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
    prompt_input "Model name" "gemini-3.1-flash-lite" "MODEL"

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
    echo -e "     ${BLUE}uv run filoma chat${NC}"
    echo ""
    echo -e "  2. Or one-shot from the command line:"
    echo -e "     ${BLUE}filoma ask \"how many python files are here?\"${NC}"
    echo ""
    echo -e "  3. Or if filoma is already installed in your active environment:"
    echo -e "     ${BLUE}filoma chat${NC}"
    echo ""
    echo -e "  4. For persistent configuration, add exports to your shell profile"
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
