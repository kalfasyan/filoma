#!/bin/bash

# Setup script for filoma with Rust acceleration

echo "🦀 Setting up filoma with Rust acceleration..."

# Check if Rust is installed
if ! command -v rustc &> /dev/null; then
    echo "❌ Rust is not installed. Please install Rust first:"
    echo "   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    echo "   source ~/.cargo/env"
    exit 1
fi

echo "✅ Rust found: $(rustc --version)"

# Check if we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "⚠️  Not in a virtual environment. Creating one..."
    
    # Check if uv is available (faster)
    if command -v uv &> /dev/null; then
        echo "📦 Using uv to create virtual environment..."
        uv venv .venv
        source .venv/bin/activate
        echo "✅ Virtual environment activated"
    else
        echo "📦 Creating virtual environment with python..."
        python3 -m venv .venv
        source .venv/bin/activate
        echo "✅ Virtual environment activated"
    fi
else
    echo "✅ Already in virtual environment: $VIRTUAL_ENV"
fi

# Check if maturin is installed
if ! command -v maturin &> /dev/null; then
    echo "📦 Installing maturin..."
    
    # Check if we have a pyproject.toml (indicating this is a uv project)
    if [[ -f "pyproject.toml" ]] && command -v uv &> /dev/null; then
        echo "📁 Detected uv project, using 'uv add' for proper dependency management..."
        uv add maturin --dev
    elif command -v uv &> /dev/null; then
        echo "📦 Using 'uv pip install' for standalone setup..."
        uv pip install maturin
    else
        echo "📦 Using pip install..."
        pip install maturin
    fi
fi

echo "✅ Maturin found: $(maturin --version)"

# Install the project in development mode first
echo "📦 Installing filoma in development mode..."
if [[ -f "pyproject.toml" ]] && command -v uv &> /dev/null; then
    echo "📁 Detected uv project, installing dependencies..."
    uv sync
    uv pip install -e .
elif command -v uv &> /dev/null; then
    echo "📦 Using uv pip install for editable install..."
    uv pip install -e .
else
    echo "📦 Using pip install for editable install..."
    pip install -e .
fi

# Build the Rust extension in development mode
echo "🔨 Building Rust extension..."
maturin develop

if [ $? -eq 0 ]; then
    echo "✅ Rust extension built successfully!"
    echo "🎉 You can now use the accelerated directory profiler!"
    echo ""
    echo "Test it with:"
    echo "python -c \"from filoma.directories import DirectoryProfiler; profiler = DirectoryProfiler(); print('Rust available:', profiler.use_rust)\""
else
    echo "❌ Failed to build Rust extension"
    echo "You can still use the pure Python implementation"
    exit 1
fi
