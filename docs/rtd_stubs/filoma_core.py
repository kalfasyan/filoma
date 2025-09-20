"""Lightweight stub of the compiled filoma.filoma_core module for Read the Docs builds.

This file is used only during documentation builds to avoid requiring a Rust
toolchain. It provides no real functionality — only the symbols needed by
mkdocstrings at import time so the docs can be rendered.
"""

def probe_directory_rust(*args, **kwargs):
    """Stub function used for docs builds. Returns an empty dict placeholder."""
    return {}


def probe_directory_rust_parallel(*args, **kwargs):
    """Stub parallel probe placeholder."""
    return {}


def probe_directory_rust_async(*args, **kwargs):
    """Stub async probe placeholder."""
    return {}


__all__ = [
    "probe_directory_rust",
    "probe_directory_rust_parallel",
    "probe_directory_rust_async",
]
