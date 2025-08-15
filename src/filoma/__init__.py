"""
filoma - A modular Python tool for profiling files, analyzing directory structures, and inspecting image data.

Features:
- Directory analysis with optional Rust acceleration (5-20x faster)
- fd integration for ultra-fast file discovery
- Image analysis for .tif, .png, .npy, .zarr files
- File profiling with system metadata
- Modular, extensible codebase
"""

# Make main modules easily accessible
from . import core, directories, files, images
from ._version import __version__
from .dataframe import DataFrame

__all__ = ["__version__", "core", "directories", "images", "files", "DataFrame"]
