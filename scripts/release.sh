#!/bin/bash
# Release script for filoma

if [ $# -eq 0 ]; then
    echo "Usage: $0 [major|minor|patch]"
    echo "Example: $0 patch"
    exit 1
fi

BUMP_TYPE=$1

echo "🚀 Starting release process..."

# Check if working directory is clean
if ! git diff-index --quiet HEAD --; then
    echo "❌ Working directory is not clean. Please commit your changes first."
    exit 1
fi

# Install dev dependencies
echo "📦 Installing dev dependencies..."
uv sync --extra dev --extra all

# Bump version
echo "📝 Bumping version..."
python scripts/bump_version.py $BUMP_TYPE

# Get new version
echo "🔍 Getting new version..."
NEW_VERSION=$(python -c "import sys; sys.path.insert(0, 'src'); from filoma._version import __version__; print(__version__)")

# Validate version was captured
if [ -z "$NEW_VERSION" ]; then
    echo "❌ Failed to get new version!"
    exit 1
fi

echo "✅ New version: $NEW_VERSION"

# Run tests
echo "🧪 Running tests..."
uv run --extra dev --extra all pytest tests/

# Run linting
echo "🔍 Running linting..."
uv run --extra dev --extra all ruff check .

# Build package
echo "📦 Building package..."
uv build

# Git operations
echo "📝 Committing changes..."
git add src/filoma/_version.py pyproject.toml uv.lock
git commit -m "Bump version to $NEW_VERSION"

echo "🏷️ Creating tag..."
if git tag "v$NEW_VERSION"; then
    echo "✅ Tag v$NEW_VERSION created successfully"
else
    echo "❌ Failed to create tag v$NEW_VERSION"
    exit 1
fi

echo "📤 Pushing to GitHub..."
git push && git push --tags

echo "✅ Release $NEW_VERSION complete!"
echo ""
echo "🎉 GitHub Actions will automatically publish to PyPI!"
echo "👀 Check the progress at: https://github.com/kalfasyan/filoma/actions"
