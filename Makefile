# Makefile for filoma package management

.PHONY: help bump-patch bump-minor bump-major release-patch release-minor release-major build test lint clean benchmark

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Version bumping
bump-patch:  ## Bump patch version (0.1.14 -> 0.1.15)
	python scripts/bump_version.py patch

bump-minor:  ## Bump minor version (0.1.14 -> 0.2.0)
	python scripts/bump_version.py minor

bump-major:  ## Bump major version (0.1.14 -> 1.0.0)
	python scripts/bump_version.py major

# Release process
release-patch:  ## Bump patch version and create release
	./scripts/release.sh patch

release-minor:  ## Bump minor version and create release
	./scripts/release.sh minor

release-major:  ## Bump major version and create release
	./scripts/release.sh major

# Development
test:  ## Run tests
	uv run --extra dev pytest tests/

lint:  ## Run linting
	uv run --extra dev ruff check .

build:  ## Build package
	uv build

clean:  ## Clean build artifacts
	rm -rf dist/ build/ *.egg-info/

# Quick development tasks
dev-install:  ## Install package in development mode with dev dependencies
	uv sync --extra dev

benchmark:  ## Run performance benchmark (Python vs Rust)
	python scripts/benchmark.py

publish:  ## Publish to PyPI (manual - normally done by GitHub Actions)
	@echo "⚠️  Note: Publishing is normally automated via GitHub Actions"
	@echo "🚀 To publish: git tag vX.Y.Z && git push --tags"
	@echo "📖 See VERSION_MANAGEMENT.md for setup instructions"
	@echo ""
	@echo "🔄 Manual publish (not recommended):"
	uv publish

# Show current version
version:  ## Show current version
	@python -c "import filoma; print(f'Current version: {filoma.__version__}')"

# Check release status
check-release:  ## Check if current version is published
	@python -c "import filoma, requests; r=requests.get(f'https://pypi.org/pypi/filoma/{filoma.__version__}/json'); print(f'✅ Version {filoma.__version__} is published' if r.status_code==200 else f'❌ Version {filoma.__version__} not found on PyPI')"
