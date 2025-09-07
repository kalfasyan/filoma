"""filoma - A modular Python tool for profiling files, analyzing
directory structures, and inspecting image data.

This module exposes a tiny, ergonomic public surface while importing
heavy optional dependencies lazily (Polars, Pillow, Rust extension,
etc.). Accessing convenience classes like :class:`DataFrame` or
subpackages like ``filoma.directories`` will import the underlying
modules on-demand.
"""

import importlib
from typing import Any

# Lightweight metadata
from ._version import __version__

# Public API: avoid importing heavy submodules at import time so
# `import filoma` stays fast in minimal scripts and REPLs.
__all__ = [
    "__version__",
    "core",
    "directories",
    "images",
    "files",
    "DataFrame",
    "probe",
    "probe_to_df",
    "probe_file",
    "probe_image",
    "ml",
]


def __getattr__(name: str):
    """Lazy import and attribute resolution for top-level names.

    Implements PEP 562: import submodules or attributes on demand.
    """
    mapping = {
        # top-level subpackages
        "core": "filoma.core",
        "directories": "filoma.directories",
        "files": "filoma.files",
        "images": "filoma.images",
        "ml": "filoma.ml",
        # common classes placed in submodules (module:attr)
        "DataFrame": "filoma.dataframe:DataFrame",
        "DirectoryProfiler": "filoma.directories.directory_profiler:DirectoryProfiler",
        "FileProfiler": "filoma.files.file_profiler:FileProfiler",
        "ImageProfiler": "filoma.images.image_profiler:ImageProfiler",
    }

    if name in mapping:
        target = mapping[name]
        if ":" in target:
            module_name, attr = target.split(":", 1)
            mod = importlib.import_module(module_name)
            value = getattr(mod, attr)
        else:
            value = importlib.import_module(target)

        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    # Helpful for tab-completion in REPLs
    return sorted(list(globals().keys()) + ["core", "directories", "files", "images", "ml", "DataFrame"])


# Convenience wrappers for quick, one-off usage. These are thin helpers that
# instantiate the appropriate profiler and return the canonical dataclass result.
def probe(path: str, **kwargs: Any) -> Any:
    """Quick helper: probe a directory path and return a DirectoryAnalysis.

    This wrapper accepts probe-specific keyword arguments such as
    ``max_depth`` and ``threads`` and forwards them to
    :class:`DirectoryProfiler.probe`. Other kwargs are used to configure the
    :class:`DirectoryProfiler` constructor.
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

    # Local import to ensure the class is available without forcing it at
    # module import time.
    from .directories import DirectoryProfiler

    profiler = DirectoryProfiler(**kwargs)
    return profiler.probe(path, max_depth=max_depth, threads=threads)


def probe_file(path: str, **kwargs: Any) -> Any:
    """Quick helper: probe a single file and return a Filo dataclass."""
    from .files.file_profiler import FileProfiler

    return FileProfiler().probe(path, **kwargs)


def probe_image(arg: Any, **kwargs: Any) -> Any:
    """Quick helper: analyze an image. If ``arg`` is a numpy array,
    :class:`ImageProfiler.probe` is used; if it's path-like, attempt to
    locate an image-specific profiler or load it to numpy and analyze.

    This wrapper favors simplicity for interactive use; for advanced
    control instantiate profilers directly.
    """
    # Local imports; keep them inside the function to avoid heavy deps at
    # module import time.
    from pathlib import Path

    try:
        import numpy as _np
    except Exception:
        _np = None

    # If it's a numpy array, use ImageProfiler directly
    if _np is not None and hasattr(_np, "ndarray") and isinstance(arg, _np.ndarray):
        from .images.image_profiler import ImageProfiler

        return ImageProfiler().probe(arg)

    # Treat as path-like
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
        # Third-party import
        from PIL import Image as _PILImage

        # Local import
        from .images.image_profiler import ImageProfiler

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
