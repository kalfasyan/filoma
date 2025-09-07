"""
filoma - A modular Python tool for profiling files, analyzing directory structures, and inspecting image data.

Features:
- Directory analysis with optional Rust acceleration (5-20x faster)
- fd integration for ultra-fast file discovery
- Image analysis for .tif, .png, .npy, .zarr files
- File profiling with system metadata
- Modular, extensible codebase
"""

from typing import Any

# Make main modules easily accessible
from . import core, directories, files, images, ml
from ._version import __version__
from .dataframe import DataFrame
from .directories.directory_profiler import DirectoryProfiler
from .files.file_profiler import FileProfiler
from .images.image_profiler import ImageProfiler

__all__ = ["__version__", "core", "directories", "images", "files", "DataFrame", "probe_to_df", "ml"]


# Convenience wrappers for quick, one-off usage. These are thin helpers that
# instantiate the appropriate profiler and return the canonical dataclass result.
def probe(path: str, **kwargs: Any) -> Any:
    """Quick helper: probe a directory path and return a DirectoryAnalysis.

    This wrapper accepts probe-specific keyword arguments such as
    `max_depth` and `threads` and forwards them to
    `DirectoryProfiler.probe`. Other kwargs are used to configure the
    `DirectoryProfiler` constructor.
    """
    # Extract probe-only parameters so they are not passed to the
    # DirectoryProfiler constructor (which doesn't accept them).
    max_depth = kwargs.pop("max_depth", None)
    threads = kwargs.pop("threads", None)

    # If the provided path points to a file, dispatch to FileProfiler.probe
    try:
        from pathlib import Path

        p = Path(path)
        if p.exists() and p.is_file():
            # Forward any file-specific kwargs (e.g., compute_hash) via kwargs
            from .files.file_profiler import FileProfiler

            return FileProfiler().probe(path, **kwargs)
    except Exception:
        # If any checks fail, fall back to directory probing behaviour and
        # let the underlying profiler raise appropriate errors.
        pass

    profiler = DirectoryProfiler(**kwargs)
    return profiler.probe(path, max_depth=max_depth, threads=threads)


def probe_file(path: str, **kwargs: Any) -> Any:
    """Quick helper: probe a single file and return a Filo dataclass."""
    return FileProfiler().probe(path, **kwargs)


def probe_image(arg: Any, **kwargs: Any) -> Any:
    """Quick helper: analyze an image. If `arg` is a numpy array, ImageProfiler.probe is used;
    if it's a path-like, attempt to locate an image-specific profiler or load it to numpy and analyze.
    This wrapper favors simplicity for interactive use; for advanced control instantiate profilers directly.
    """
    # Lazy import to avoid heavy image dependencies at import time
    try:
        from pathlib import Path

        import numpy as _np
    except Exception:
        _np = None

    # If it's a numpy array, use ImageProfiler directly
    if _np is not None and hasattr(_np, "ndarray") and isinstance(arg, _np.ndarray):
        return ImageProfiler().probe(arg)

    # If path-like, try to dispatch to specialized profilers by extension
    p = Path(arg)
    suffix = p.suffix.lower() if p.suffix else ""

    try:
        # Use images package specializers when available
        from .images import NpyProfiler, PngProfiler, TifProfiler, ZarrProfiler

        if suffix == ".png":
            return PngProfiler().probe(p)
        if suffix == ".npy":
            return NpyProfiler().probe(p)
        if suffix in (".tif", ".tiff"):
            return TifProfiler().probe(p)
        if suffix == ".zarr":
            return ZarrProfiler().probe(p)
    except Exception:
        # If specialist creation fails, fall back to generic loader below
        pass

    # Generic fallback: try Pillow + numpy loader
    try:
        from PIL import Image as _PILImage

        img = _PILImage.open(p)
        arr = _np.array(img) if _np is not None else None
        if arr is not None:
            return ImageProfiler().probe(arr)
    except Exception:
        pass

    # Last resort: return an ImageReport with status explaining failure
    from .images.image_profiler import ImageReport

    return ImageReport(path=str(p), status="failed_to_load_or_unsupported_format")


def probe_to_df(path: str, to_pandas: bool = False, enrich: bool = True, **kwargs: Any) -> Any:
    """Convenience helper: return a Polars DataFrame (or pandas if to_pandas=True).

    This forces DataFrame building on the profiler and optionally runs a small
    enrichment chain: .add_depth_col(path).add_path_components().add_file_stats_cols().

    Args:
        path: directory path to probe
        to_pandas: if True, return a pandas.DataFrame instead of a Polars DataFrame
        enrich: if True, run the enrichment chain on the DataFrame wrapper
        **kwargs: forwarded to DirectoryProfiler constructor (probe-only kwargs
                  like max_depth and threads are accepted and forwarded)

    Returns:
        polars.DataFrame or pandas.DataFrame depending on to_pandas

    Raises:
        RuntimeError: if DataFrame support is not available or building failed.
    """
    # Extract probe-only parameters
    max_depth = kwargs.pop("max_depth", None)
    threads = kwargs.pop("threads", None)

    # Lazy import to avoid heavy deps at module import time
    from .directories import DirectoryProfiler

    profiler = DirectoryProfiler(build_dataframe=True, **kwargs)
    analysis = profiler.probe(path, max_depth=max_depth, threads=threads)

    df_wrapper = analysis.to_df()
    if df_wrapper is None:
        raise RuntimeError("DataFrame was not built. Ensure 'polars' is installed and that DataFrame building is enabled (build_dataframe=True).")

    # Optionally enrich the DataFrame wrapper with useful columns/stats
    df_enriched = df_wrapper
    if enrich:
        try:
            df_enriched = df_enriched.add_depth_col(path).add_path_components().add_file_stats_cols()
        except Exception:
            # If enrichment fails for any reason, fall back to the raw DataFrame
            pass

    # Return requested format: Polars DataFrame or pandas
    pl_df = df_enriched.df
    if to_pandas:
        try:
            return pl_df.to_pandas()
        except Exception as e:
            raise RuntimeError(f"Failed to convert Polars DataFrame to pandas: {e}")

    return pl_df
