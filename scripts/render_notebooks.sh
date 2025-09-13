#!/usr/bin/env bash
set -euo pipefail

# Render notebooks to docs/ as standalone HTML pages.
# Prefer `python -m nbconvert` if available, otherwise try `jupyter nbconvert`.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOTEBOOKS_DIR="$ROOT_DIR/notebooks"
OUT_DIR="$ROOT_DIR/docs"

NBCONVERT_CMD=""
if command -v python >/dev/null 2>&1 && python -m nbconvert --version >/dev/null 2>&1; then
  NBCONVERT_CMD=(python -m nbconvert)
elif command -v jupyter >/dev/null 2>&1; then
  NBCONVERT_CMD=(jupyter nbconvert)
else
  echo "ERROR: Neither 'python -m nbconvert' nor 'jupyter nbconvert' is available in PATH." >&2
  echo "Install nbconvert (e.g. 'uv pip install nbconvert' or add it to your docs requirements)." >&2
  exit 127
fi

echo "Rendering notebooks from $NOTEBOOKS_DIR to $OUT_DIR using: ${NBCONVERT_CMD[*]}"

for nb in "$NOTEBOOKS_DIR"/*.ipynb; do
  [ -e "$nb" ] || continue
  base=$(basename "$nb" .ipynb)

  # Special-case mapping: render ydata-profiling_example.ipynb -> life-after-filoma.html
  if [ "$base" = "ydata-profiling_example" ]; then
    out="$OUT_DIR/life-after-filoma.html"
  elif [ "$base" = "demo" ]; then
    out="$OUT_DIR/demo.html"
  else
    out="$OUT_DIR/$base.html"
  fi

  echo "- $nb -> $out"
  # Use non-executing conversion by default (matches CI). If you need execution,
  # run nbconvert manually with --execute or adjust this script.
  if "${NBCONVERT_CMD[@]}" --to html --output "$out" "$nb"; then
    :
  else
    echo "nbconvert failed for $nb (conversion without execution). Continuing..." >&2
  fi
done

echo "Done."
