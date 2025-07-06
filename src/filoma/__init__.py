"""
filoma - A modular Python tool for profiling files, analyzing directory structures, and inspecting image data.

Features:
- Directory analysis with optional Rust acceleration (5-20x faster)
- Image analysis for .tif, .png, .npy, .zarr files
- File profiling with system metadata
- Modular, extensible codebase
"""

from ._version import __version__

# Make main modules easily accessible
from . import dir, fileinfo, img

__all__ = ["__version__", "dir", "img", "fileinfo"]
