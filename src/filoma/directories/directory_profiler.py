import time
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from loguru import logger
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

# Try to import the Rust implementation
try:
    from filoma.filoma_core import probe_directory_rust, probe_directory_rust_parallel

    RUST_AVAILABLE = True
    RUST_PARALLEL_AVAILABLE = True
except ImportError:
    try:
        from filoma.filoma_core import probe_directory_rust

        RUST_AVAILABLE = True
        RUST_PARALLEL_AVAILABLE = False
    except ImportError:
        RUST_AVAILABLE = False
        RUST_PARALLEL_AVAILABLE = False

# Optional async prober if compiled with tokio support
try:
    from filoma.filoma_core import probe_directory_rust_async  # type: ignore

    RUST_ASYNC_AVAILABLE = True
except Exception:
    RUST_ASYNC_AVAILABLE = False

# Import DataFrame for enhanced functionality
try:
    from ..dataframe import DataFrame

    DATAFRAME_AVAILABLE = True
except ImportError:
    DATAFRAME_AVAILABLE = False

# Import fd integration
try:
    from ..core import FdIntegration

    FD_AVAILABLE = True
except ImportError:
    FD_AVAILABLE = False

# Sentinel to detect when optional boolean flags are omitted by callers.
# Define at module scope so it's always available regardless of fd import outcome.
_NOT_SET = object()


def _is_interactive_environment():
    """Detect if running in IPython/Jupyter or other interactive environment."""
    try:
        # Check for IPython
        from IPython import get_ipython

        if get_ipython() is not None:
            return True
    except ImportError:
        pass

    # Check for other interactive indicators
    import sys

    if hasattr(sys, "ps1"):  # Python interactive shell
        return True

    return False


@dataclass
class DirectoryAnalysis(Mapping):
    """Structured container for directory analysis results.

    This is the canonical, dataclass-first return value for directory probes.
    Use :meth:`to_dict` to convert to a plain dict and :meth:`to_df`
    to access the optional DataFrame. The class exists to provide a typed,
    ergonomic API for programmatic consumption.
    """

    path: str
    summary: Dict
    file_extensions: Dict
    common_folder_names: Dict
    empty_folders: List[str]
    top_folders_by_file_count: List
    depth_distribution: Dict
    dataframe: Optional["DataFrame"] = None
    timing: Optional[Dict] = None
    dataframe_note: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict) -> "DirectoryAnalysis":
        return cls(
            path=d.get("path"),
            summary=d.get("summary", {}),
            file_extensions=d.get("file_extensions", {}),
            common_folder_names=d.get("common_folder_names", {}),
            empty_folders=d.get("empty_folders", []),
            top_folders_by_file_count=d.get("top_folders_by_file_count", []),
            depth_distribution=d.get("depth_distribution", {}),
            dataframe=d.get("dataframe"),
            timing=d.get("timing"),
            dataframe_note=d.get("dataframe_note"),
        )

    def to_dict(self) -> Dict:
        # Convert to a plain dict shape
        d = {
            "path": self.path,
            "summary": self.summary,
            "file_extensions": self.file_extensions,
            "common_folder_names": self.common_folder_names,
            "empty_folders": self.empty_folders,
            "top_folders_by_file_count": self.top_folders_by_file_count,
            "depth_distribution": self.depth_distribution,
        }
        if self.dataframe is not None:
            d["dataframe"] = self.dataframe
        if self.timing is not None:
            d["timing"] = self.timing
        if self.dataframe_note is not None:
            d["dataframe_note"] = self.dataframe_note
        return d

    def to_df(self) -> Optional["DataFrame"]:
        """Return the attached DataFrame wrapper or log a helpful warning when absent.

        This method used to silently return None when no DataFrame was built which
        often confused interactive users calling ``analysis.to_df()``. We now log a
        warning explaining the likely causes (DataFrame building disabled or polars
        not installed) to surface actionable next steps.
        """
        if self.dataframe is None:
            # Emit a helpful, actionable warning rather than silently returning None
            logger.warning(
                "No DataFrame available for analysis at path {path!s}. "
                "DataFrame building is disabled by default or 'polars' is not installed. "
                "Call DirectoryProfiler(build_dataframe=True) or use filoma.probe_to_df(...) to obtain a DataFrame.",
                path=self.path,
            )
        return self.dataframe

    def as_dict(self) -> Dict:
        return self.to_dict()

    # Convenience printing helpers so callers can write `analysis.print_summary()`
    # or `analysis.print_report()` without importing DirectoryProfiler. These
    # delegate to the existing DirectoryProfiler rich printers for consistency.
    def print_summary(self, profiler: "DirectoryProfiler" = None):
        """Pretty-print a short summary using the rich-based DirectoryProfiler printer.

        If `profiler` is provided it will be used (useful to customize show_progress,
        console, or other profiler settings); otherwise a default profiler is created.
        """
        # Local import to avoid import cycles at module import time
        if profiler is None:
            profiler = DirectoryProfiler()
        profiler.print_summary(self)

    def print_report(self, profiler: "DirectoryProfiler" = None):
        """Pretty-print the full report (summary + extras) via DirectoryProfiler.

        This is an alias for `print_summary` + additional report sections; kept
        as a separate method name for discoverability and symmetry with other
        profilers in the project.
        """
        if profiler is None:
            profiler = DirectoryProfiler()
        profiler.print_report(self)

    # Mapping protocol implementations so callers can still use dict-like access
    # (e.g., result['summary']) even though the canonical return type is a dataclass.
    def _as_dict(self) -> Dict:
        return self.to_dict()

    def __getitem__(self, key):
        return self._as_dict()[key]

    def __iter__(self):
        return iter(self._as_dict())

    def __len__(self):
        return len(self._as_dict())


class DirectoryProfiler:
    """
    Analyzes directory structures for basic statistics and patterns.
    Provides file counts, folder patterns, empty directories, and extension analysis.

    Can use either a pure Python implementation or a faster Rust implementation
    when available. Supports both sequential and parallel Rust processing.
    """

    def __init__(
        self,
        use_rust: object = _NOT_SET,
        use_parallel: bool = True,
        use_async: bool = False,
        use_fd: object = _NOT_SET,
        search_backend: str = "auto",  # "rust", "python", "fd", "auto"
        parallel_threshold: int = 1000,
        build_dataframe: bool = False,
        return_absolute_paths: bool = False,
        show_progress: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        fast_path_only: bool = False,
        network_concurrency: int = 64,
        network_timeout_ms: int = 5000,
        network_retries: int = 0,
        threads: Optional[int] = None,
    ):
        """
        Initialize the directory profiler.

        Args:
            use_rust: Whether to use the Rust implementation when available.
                     Falls back to Python if Rust is not available.
            use_parallel: Whether to use parallel processing in Rust (when available).
                         Only effective when use_rust=True.
            use_fd: Whether to use fd for file discovery when available.
            search_backend: Backend to use ("rust", "python", "fd", "auto").
                          "auto" chooses the best available backend.
            parallel_threshold: Minimum estimated directory size to trigger parallel processing.
                              Larger values = less likely to use parallel processing.
            build_dataframe: Whether to build a DataFrame with all file paths for enhanced analysis.
                           Requires polars to be installed. When using Rust acceleration,
                           statistics are computed in Rust but file paths are collected
                           using Python for DataFrame consistency.
            show_progress: Whether to show progress indication during analysis.
            progress_callback: Optional callback function for custom progress handling.
                             Signature: callback(message: str, current: int, total: int)
            fast_path_only: Internal flag to use fast path (no metadata) in Rust backend.
        """
        self.console = Console()

        # Resolve backend preference from the user's explicit flags and the
        # search_backend hint. Use sentinel detection so callers that explicitly
        # pass one of the `use_*` flags override the other default.
        self.search_backend = search_backend

        rust_provided = use_rust is not _NOT_SET
        fd_provided = use_fd is not _NOT_SET
        requested_use_rust = bool(use_rust) if rust_provided else None
        requested_use_fd = bool(use_fd) if fd_provided else None

        chosen_preference: Optional[str] = None
        if self.search_backend in ("rust", "fd", "python"):
            # Explicit backend override from the search_backend parameter
            chosen_preference = self.search_backend
        else:
            # Infer preference using explicit flags when provided.
            if requested_use_rust is True and requested_use_fd is not True:
                chosen_preference = "rust"
            elif requested_use_fd is True and requested_use_rust is not True:
                chosen_preference = "fd"
            elif requested_use_rust is True and requested_use_fd is True:
                # Both explicitly requested: prefer fd but inform the user
                chosen_preference = "fd"
                self.console.print(
                    (
                        "[yellow]Note: both use_rust and use_fd were enabled; "
                        "treating this as a preference for fd. Set search_backend='rust' "
                        "to prefer Rust instead.[/yellow]"
                    )
                )
            elif requested_use_rust is False and requested_use_fd is False:
                chosen_preference = "python"
            elif requested_use_rust is False and requested_use_fd is None:
                chosen_preference = "fd"
            elif requested_use_fd is False and requested_use_rust is None:
                chosen_preference = "rust"
            else:
                # No explicit preference provided: default to Rust -> fd -> python
                if RUST_AVAILABLE:
                    chosen_preference = "rust"
                elif FD_AVAILABLE:
                    chosen_preference = "fd"
                else:
                    chosen_preference = "python"

        # Final flags reflect chosen preference but also the actual availability
        # of the underlying implementations.
        self.use_rust = (chosen_preference == "rust") and RUST_AVAILABLE
        self.use_fd = (chosen_preference == "fd") and FD_AVAILABLE

        # Parallel Rust depends on Rust being chosen and available
        self.use_parallel = use_parallel and RUST_PARALLEL_AVAILABLE and self.use_rust

        # User-visible async toggle for the Rust network-optimized scanner.
        # Off by default because async can be slower on local SSD/HDD.
        self.use_async = use_async
        if use_async and not RUST_ASYNC_AVAILABLE:
            # If user requested async but the native async implementation isn't
            # available, disable it and warn.
            self.console = self.console if hasattr(self, "console") else Console()
            self.console.print("[yellow]Warning: Rust async implementation not available, async disabled[/yellow]")
            self.use_async = False

        # Apply remaining constructor arguments to instance state
        self.use_fd = use_fd and FD_AVAILABLE
        self.search_backend = search_backend
        self.parallel_threshold = parallel_threshold
        self.build_dataframe = build_dataframe and DATAFRAME_AVAILABLE
        # Control whether final results use absolute paths (True) or relative paths (False)
        self.return_absolute_paths = bool(return_absolute_paths)

        # Automatically disable progress bars in interactive environments to avoid conflicts
        if _is_interactive_environment() and show_progress:
            logger.debug("Interactive environment detected, disabling progress bars to avoid conflicts")
            self.show_progress = False
        else:
            self.show_progress = show_progress

        self.progress_callback = progress_callback
        self._fast_path_only = fast_path_only

        # Network tuning
        self.network_concurrency = network_concurrency
        self.network_timeout_ms = network_timeout_ms
        self.network_retries = network_retries

        # Optional threads setting to pass to fd (maps to fd's --threads flag).
        # If None, fd will use its own default concurrency; a numeric value will be forwarded.
        self.threads = threads

        # Defer fd integration initialization until actually used to avoid
        # probing the environment at import/constructor time (helps CI tests
        # that monkeypatch availability flags).
        self.fd_integration = None

        if use_rust and not RUST_AVAILABLE:
            self.console.print("[yellow]Warning: Rust implementation not available, falling back to Python[/yellow]")
        elif use_parallel and self.use_rust and not RUST_PARALLEL_AVAILABLE:
            self.console.print("[yellow]Warning: Rust parallel implementation not available, using sequential Rust[/yellow]")

        if use_fd and not FD_AVAILABLE:
            self.console.print("[yellow]Warning: fd command not found, fd search disabled[/yellow]")
        elif use_fd and FD_AVAILABLE and not self.use_fd:
            self.console.print("[yellow]Warning: fd integration failed, fd search disabled[/yellow]")

        if build_dataframe and not DATAFRAME_AVAILABLE:
            self.console.print("[yellow]Warning: DataFrame functionality not available (polars not installed), disabling DataFrame building[/yellow]")
            self.build_dataframe = False
        # Warn if show_progress is True and Rust is being used
        if self.show_progress and (self.use_rust is None or self.use_rust):
            import warnings

            warnings.warn(
                "[filoma] Progress bar updates are limited when using the Rust backend. "
                "You will only see updates at the start and end of the scan. For live progress, use the Python backend (use_rust=False)."
            )

    def is_rust_available(self) -> bool:
        """
        Check if Rust implementation is available and being used.

        Returns:
            True if Rust implementation is available and enabled, False otherwise
        """
        return self.use_rust and RUST_AVAILABLE

    def is_parallel_available(self) -> bool:
        """
        Check if parallel Rust implementation is available and being used.

        Returns:
            True if parallel Rust implementation is available and enabled, False otherwise
        """
        return self.use_parallel and RUST_PARALLEL_AVAILABLE

    def is_fd_available(self) -> bool:
        """
        Check if fd integration is available and being used.

        Returns:
            True if fd is available and enabled, False otherwise
        """

        # Use FD_AVAILABLE to reflect whether the fd integration package is importable
        # Tests may monkeypatch FD_AVAILABLE without having the fd binary present.
        return self.use_fd and FD_AVAILABLE

    def get_implementation_info(self) -> Dict[str, bool]:
        """
        Get information about which implementations are available and being used.

        Returns:
            Dictionary with implementation availability status
        """
        return {
            "rust_available": RUST_AVAILABLE,
            "rust_parallel_available": RUST_PARALLEL_AVAILABLE,
            "rust_async_available": RUST_ASYNC_AVAILABLE,
            "fd_available": FD_AVAILABLE,
            "dataframe_available": DATAFRAME_AVAILABLE,
            "using_rust": self.use_rust,
            "using_parallel": self.use_parallel,
            "using_async": bool(self.use_async and RUST_ASYNC_AVAILABLE),
            "using_fd": self.use_fd,
            "using_dataframe": self.build_dataframe,
            "return_absolute_paths": self.return_absolute_paths,
            "search_backend": self.search_backend,
            "python_fallback": not (self.use_rust or self.use_fd),
        }

    def probe(self, path: str, max_depth: Optional[int] = None, threads: Optional[int] = None) -> "DirectoryAnalysis":
        """
        Analyze a directory tree and return comprehensive statistics.

        Args:
            path: Path to the root directory to probe
            max_depth: Maximum depth to traverse (None for unlimited)

        Returns:
            A :class:`DirectoryAnalysis` instance containing analysis results
        """
        start_time = time.time()

        # Choose the best backend
        backend = self._choose_backend()

        # Log the start of analysis
        impl_type = self._get_impl_display_name(backend)
        logger.info(f"Starting directory analysis of '{path}' using {impl_type} implementation")

        try:
            if backend == "fd":
                # threads param overrides instance threads when provided
                chosen_threads = threads if threads is not None else self.threads
                result = self._probe_fd(path, max_depth, threads=chosen_threads)
            elif backend == "rust":
                result = self._probe_rust(path, max_depth, fast_path_only=self._fast_path_only)
            else:
                result = self._probe_python(path, max_depth)

            # Calculate and log timing
            elapsed_time = time.time() - start_time
            total_items = result["summary"]["total_files"] + result["summary"]["total_folders"]

            logger.success(
                f"Directory analysis completed in {elapsed_time:.2f}s - "
                f"Found {total_items:,} items ({result['summary']['total_files']:,} files, "
                f"{result['summary']['total_folders']:,} folders) using {impl_type}"
            )

            # Add timing information to result
            result["timing"] = {
                "elapsed_seconds": elapsed_time,
                "implementation": impl_type,
                "items_per_second": total_items / elapsed_time if elapsed_time > 0 else 0,
            }

            # Return a structured dataclass by default for easier programmatic use
            return DirectoryAnalysis.from_dict(result)

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Directory analysis failed after {elapsed_time:.2f}s: {str(e)}")
            raise

    def _choose_backend(self) -> str:
        """
        Choose the best available backend based on settings and availability.

        Returns:
            Backend name: "fd", "rust", or "python"
        """
        # If search_backend is 'auto' and neither rust nor fd are requested
        # by the resolved preferences, prefer the Python backend. This avoids
        # forcing Python when the user specifically preferred fd.
        if self.search_backend == "auto" and not (self.use_rust or self.use_fd):
            return "python"

        if self.search_backend == "fd":
            if self.use_fd and FD_AVAILABLE:
                return "fd"
            else:
                logger.warning("fd backend requested but not available, falling back to auto selection")

        elif self.search_backend == "rust":
            if self.use_rust:
                return "rust"
            else:
                logger.warning("Rust backend requested but not available, falling back to auto selection")

        elif self.search_backend == "python":
            return "python"

        # Auto selection logic
        if self.search_backend == "auto":
            # Based on cold cache benchmarks Rust tends to be the fastest
            # general-purpose backend. Prefer Rust when available; fall back
            # to fd when Rust is not enabled/available but fd is explicitly
            # enabled by the user.
            if self.use_rust and RUST_AVAILABLE:
                return "rust"
            elif self.use_fd and FD_AVAILABLE:
                return "fd"
            else:
                return "python"

        # Fallback to python if nothing else works
        return "python"

    def _get_impl_display_name(self, backend: str) -> str:
        """Get display name for implementation type."""
        if backend == "fd":
            return "🔍 fd"
        elif backend == "rust":
            if self.use_parallel and RUST_PARALLEL_AVAILABLE:
                return "🦀 Rust (Parallel)"
            else:
                return "🦀 Rust (Sequential)"
        else:
            return "🐍 Python"

    def _probe_fd(self, path: str, max_depth: Optional[int] = None, threads: Optional[int] = None) -> Dict:
        """
        Use fd for file discovery + Python for analysis.

        This hybrid approach leverages fd's ultra-fast file discovery
        while using Python for statistical analysis to maintain
        consistency with other backends.
        """
        # Lazily initialize fd integration here. This ensures tests that
        # monkeypatch FD_AVAILABLE can control availability without the
        # constructor eagerly probing the environment.
        if self.fd_integration is None:
            # If the fd integration package wasn't importable at module
            # import time, reflect that now.
            if not FD_AVAILABLE:
                raise RuntimeError("fd integration not available")
            try:
                self.fd_integration = FdIntegration()
                if not self.fd_integration.is_available():
                    # fd binary is not usable on this system
                    self.fd_integration = None
                    raise RuntimeError("fd integration not available")
            except Exception:
                self.fd_integration = None
                raise RuntimeError("fd integration not available")

        progress = None
        task_id = None

        if self.show_progress:
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Discovering files with fd..."),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=self.console,
                transient=True,
            )
            progress.start()
            task_id = progress.add_task("Discovering...", total=None)

        # Run the fd discovery and analysis inside a try so we always stop
        # the progress bar in the finally block below.
        try:
            # Use fd to get all files and directories rapidly
            if progress and task_id is not None:
                progress.update(task_id, description="[bold blue]Finding files...")

            # fd's --max-depth applies to the matched path; to match the
            # Python/Rust semantics where files up to depth (max_depth + 1)
            # are included, when a max_depth is provided for the probe we
            # increase the file search depth by 1.
            file_max_depth = None if max_depth is None else max_depth + 1
            # When using fd in auto mode, prefer flags that match a raw
            # traversal (include hidden files, don't honor ignore files, follow symlinks)
            fd_find_kwargs = {
                "path": path,
                "file_types": ["f"],
                "max_depth": file_max_depth,
                "absolute_paths": self.return_absolute_paths,
                "threads": threads,
            }
            if self.search_backend == "auto":
                fd_find_kwargs.update({"search_hidden": True, "no_ignore": True, "follow_links": True})

            all_files = self.fd_integration.find(**fd_find_kwargs)

            if progress and task_id is not None:
                progress.update(task_id, description="[bold blue]Finding directories...")

            all_dirs = self.fd_integration.find(
                path=path,
                file_types=["d"],  # Directories only
                max_depth=max_depth,
                absolute_paths=self.return_absolute_paths,
                threads=threads,
                search_hidden=True if self.search_backend == "auto" else False,
                no_ignore=True if self.search_backend == "auto" else False,
                follow_links=True if self.search_backend == "auto" else False,
            )

            # Convert to Path objects for analysis
            root_path_obj = Path(path).resolve()
            all_paths = [Path(p) for p in all_files + all_dirs]

            # If DataFrame building is enabled and DataFrame support is available,
            # build a prebuilt DataFrame from the fd results and pass it to the
            # Python probing logic to avoid rebuilding the DataFrame there.
            prebuilt_df = None
            if self.build_dataframe and DATAFRAME_AVAILABLE:
                try:
                    prebuilt_df = DataFrame([str(p) for p in all_paths])
                except Exception:
                    # If DataFrame construction fails for any reason, fall back
                    # to letting _probe_paths_python collect paths itself.
                    prebuilt_df = None

            if progress and task_id is not None:
                progress.update(task_id, description="[bold yellow]Analyzing discovered files...")
                progress.update(task_id, total=100, completed=50)

                # Now probe the discovered paths using Python logic
                # Pass the existing progress to avoid conflicts. If a prebuilt DataFrame
                # exists, provide it to avoid rebuilding the DataFrame inside the probe.
                result = self._probe_paths_python(
                    root_path_obj,
                    all_paths,
                    max_depth,
                    existing_progress=progress,
                    existing_task_id=task_id,
                    prebuilt_dataframe=prebuilt_df,
                )
            else:
                # No progress provided; run probe without progress integration
                result = self._probe_paths_python(
                    root_path_obj,
                    all_paths,
                    max_depth,
                    existing_progress=None,
                    existing_task_id=None,
                    prebuilt_dataframe=prebuilt_df,
                )

            if progress and task_id is not None:
                progress.update(task_id, description="[bold green]Analysis complete!")
                progress.update(task_id, completed=100)

            return result

        finally:
            if progress:
                progress.stop()

    def sample_paths(self, path: str, sample_size: int = 20) -> Dict[str, List[str]]:
        """Return small samples of paths for quick backend-diffing.

        Returns a dict with keys 'fd_files', 'fd_dirs', 'python_files'. Rust currently
        does not expose a path list in the public API so it is omitted (you can
        re-run the Rust prober separately if needed).
        """
        samples = {"fd_files": [], "fd_dirs": [], "python_files": []}
        try:
            if FD_AVAILABLE:
                fd = FdIntegration()
                samples["fd_files"] = fd.find(
                    path=path,
                    file_types=["f"],
                    max_results=sample_size,
                    search_hidden=True,
                    no_ignore=True,
                    follow_links=True,
                    absolute_paths=self.return_absolute_paths,
                )
                samples["fd_dirs"] = fd.find(
                    path=path,
                    file_types=["d"],
                    max_results=sample_size,
                    search_hidden=True,
                    no_ignore=True,
                    follow_links=True,
                    absolute_paths=self.return_absolute_paths,
                )
        except Exception:
            samples["fd_files"] = []
            samples["fd_dirs"] = []

        # Python sample
        try:
            root = Path(path)
            python_files = []
            for i, p in enumerate(root.rglob("*")):
                if p.is_file():
                    python_files.append(str(p.resolve()))
                if len(python_files) >= sample_size:
                    break
            samples["python_files"] = python_files
        except Exception:
            samples["python_files"] = []

        return samples

    def _probe_paths_python(
        self,
        path_root: Path,
        all_paths: List[Path],
        max_depth: Optional[int] = None,
        existing_progress=None,
        existing_task_id=None,
        prebuilt_dataframe=None,
    ) -> Dict:
        """
        Analyze pre-discovered paths using Python logic.

        This method takes a list of paths (from fd or other source) and performs
        the statistical analysis to maintain consistency with the Python backend.

        Args:
            path: Root directory being probed
            all_paths: List of paths to probe
            max_depth: Maximum depth for analysis
            existing_progress: Existing progress bar to reuse (avoids conflicts)
            existing_task_id: Existing task ID to update
        """
        # Initialize counters and collections
        file_count = 0
        folder_count = 1  # Start with 1 to count the root directory itself
        total_size = 0
        empty_folders = []
        file_extensions = Counter()
        folder_names = Counter()
        files_per_folder = defaultdict(int)
        depth_stats = defaultdict(int)

        # Count the root directory at depth 0
        depth_stats[0] = 1

        # Collection for DataFrame if enabled. If a prebuilt_dataframe is provided
        # (e.g. from fd results), skip collecting paths and attach it at the end.
        dataframe_paths = [] if (self.build_dataframe and prebuilt_dataframe is None) else None

        # Sort paths for better progress indication (guard against None or unsortable lists)
        if all_paths:
            try:
                all_paths.sort()
            except Exception:
                # If sorting fails (e.g., mixed types), ignore and proceed
                pass

        progress = existing_progress
        task_id = existing_task_id
        processed_items = 0
        progress_owned = False  # Track if we own the progress bar

        if self.show_progress and existing_progress is None:
            # Only create new progress if none was provided
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Analyzing file metadata..."),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed:,}/{task.total:,} items)"),
                TimeElapsedColumn(),
                console=self.console,
                transient=True,
            )
            progress.start()
            task_id = progress.add_task("Analyzing...", total=len(all_paths))
            progress_owned = True
        elif existing_progress and existing_task_id:
            # Update existing progress for the analysis phase
            existing_progress.update(existing_task_id, description="[bold yellow]Analyzing file metadata...", total=len(all_paths), completed=0)

        try:
            for current_path in all_paths:
                processed_items += 1

                # Update progress
                if progress and task_id is not None:
                    if processed_items % 100 == 0:
                        progress.update(task_id, completed=processed_items)

                    if self.progress_callback:
                        self.progress_callback(f"Processing: {current_path.name}", processed_items, len(all_paths))

                # Calculate current depth
                try:
                    depth = len(current_path.relative_to(path_root).parts)
                except ValueError:
                    depth = 0

                # Skip if beyond max depth (should not happen with fd filtering, but safety check)
                if max_depth is not None:
                    if current_path.is_dir() and depth > max_depth:
                        continue
                    elif current_path.is_file() and depth > max_depth + 1:
                        continue

                # Add to paths collection if DataFrame is enabled and we're collecting paths
                if self.build_dataframe and dataframe_paths is not None:
                    dataframe_paths.append(str(current_path))

                if current_path.is_dir():
                    depth_stats[depth] += 1
                    folder_count += 1

                    # Check for empty folders
                    try:
                        if not any(current_path.iterdir()):
                            empty_folders.append(str(current_path))
                    except (OSError, PermissionError):
                        pass

                    # Analyze folder names for patterns
                    folder_names[current_path.name] += 1

                elif current_path.is_file():
                    file_count += 1

                    # Count files in parent directory
                    files_per_folder[str(current_path.parent)] += 1

                    # Get file extension
                    ext = current_path.suffix.lower()
                    if ext:
                        file_extensions[ext] += 1
                    else:
                        file_extensions["<no extension>"] += 1

                    # Add to total size
                    try:
                        total_size += current_path.stat().st_size
                    except (OSError, IOError):
                        pass

            # Final progress update
            if progress and task_id is not None:
                progress.update(task_id, completed=processed_items)

            # Calculate summary statistics
            avg_files_per_folder = file_count / max(1, folder_count)

            # Find folders with most files
            top_folders_by_file_count = sorted(files_per_folder.items(), key=lambda x: x[1], reverse=True)[:10]

            # Build result dictionary
            result = {
                "path": str(path_root),
                "summary": {
                    "total_files": file_count,
                    "total_folders": folder_count,
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                    "avg_files_per_folder": round(avg_files_per_folder, 2),
                    "max_depth": max(depth_stats.keys()) if depth_stats else 0,
                    "empty_folder_count": len(empty_folders),
                },
                "file_extensions": dict(file_extensions.most_common(20)),
                "common_folder_names": dict(folder_names.most_common(20)),
                "empty_folders": empty_folders,
                "top_folders_by_file_count": top_folders_by_file_count,
                "depth_distribution": dict(depth_stats),
            }

            # Add DataFrame if enabled
            if self.build_dataframe and DATAFRAME_AVAILABLE:
                if prebuilt_dataframe is not None:
                    # Use prebuilt DataFrame supplied by caller (fd results)
                    result["dataframe"] = prebuilt_dataframe
                else:
                    result["dataframe"] = DataFrame(dataframe_paths)

            return result

        finally:
            if progress and progress_owned:
                progress.stop()

    def _probe_rust(self, path: str, max_depth: Optional[int] = None, fast_path_only: bool = False) -> Dict:
        """
        Use the Rust implementation for analysis.

        For performance, the main statistical analysis is done in Rust.
        If DataFrame building is enabled, file paths are collected separately
        using Python/pathlib to maintain consistency with the Python implementation.
        """
        progress = None
        task_id = None

        if self.show_progress:
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Analyzing directory structure..."),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=self.console,
                transient=True,  # Remove progress bar when done
            )
            progress.start()
            task_id = progress.add_task("Analyzing...", total=None)

        try:
            # Choose Rust variant: async for network filesystems, sync otherwise
            try:
                fs_type = self._detect_filesystem_type(path)
            except Exception:
                fs_type = None

            is_network_fs = False
            if fs_type:
                # Common network FS types
                if any(x in fs_type.lower() for x in ("nfs", "cifs", "smb", "ceph", "gluster", "sshfs")):
                    is_network_fs = True

            # If network FS choose async Rust prober which limits concurrency and uses tokio
            # Only use the async Rust variant when the path looks like a network
            # filesystem AND the user explicitly enabled async via `use_async`.
            if is_network_fs and self.use_async:
                # Default concurrency limit can be tuned; use configured values
                if RUST_ASYNC_AVAILABLE:
                    # Decide Rust flag defaults: when search_backend is 'auto', prefer fd-like semantics
                    if self.search_backend == "auto":
                        follow = True
                        hidden = True
                        no_ignore = True
                    else:
                        follow = None
                        hidden = None
                        no_ignore = None

                    result = probe_directory_rust_async(
                        path,
                        max_depth,
                        self.network_concurrency,
                        self.network_timeout_ms,
                        self.network_retries,
                        fast_path_only,
                        follow_links=follow,
                        search_hidden=hidden,
                        no_ignore=no_ignore,
                    )
                else:
                    # Async variant not available; fall back to parallel or sequential Rust
                    if self.use_parallel and RUST_PARALLEL_AVAILABLE:
                        if self.search_backend == "auto":
                            follow = True
                            hidden = True
                            no_ignore = True
                        else:
                            follow = None
                            hidden = None
                            no_ignore = None

                        result = probe_directory_rust_parallel(
                            path,
                            max_depth,
                            self.parallel_threshold,
                            fast_path_only,
                            follow_links=follow,
                            search_hidden=hidden,
                            no_ignore=no_ignore,
                        )
                    else:
                        result = probe_directory_rust(path, max_depth, fast_path_only)
            elif is_network_fs and not self.use_async:
                # User explicitly disabled async; prefer parallel or sequential Rust
                if self.use_parallel and RUST_PARALLEL_AVAILABLE:
                    if self.search_backend == "auto":
                        follow = True
                        hidden = True
                        no_ignore = True
                    else:
                        follow = None
                        hidden = None
                        no_ignore = None

                    result = probe_directory_rust_parallel(
                        path,
                        max_depth,
                        self.parallel_threshold,
                        fast_path_only,
                        follow_links=follow,
                        search_hidden=hidden,
                        no_ignore=no_ignore,
                    )
                else:
                    if self.search_backend == "auto":
                        follow = True
                        hidden = True
                        no_ignore = True
                    else:
                        follow = None
                        hidden = None
                        no_ignore = None

                    result = probe_directory_rust(
                        path,
                        max_depth,
                        fast_path_only,
                        follow_links=follow,
                        search_hidden=hidden,
                        no_ignore=no_ignore,
                    )
            else:
                if self.search_backend == "auto":
                    follow = True
                    hidden = True
                    no_ignore = True
                else:
                    follow = None
                    hidden = None
                    no_ignore = None

                if self.use_parallel and RUST_PARALLEL_AVAILABLE:
                    result = probe_directory_rust_parallel(
                        path,
                        max_depth,
                        self.parallel_threshold,
                        fast_path_only,
                        follow_links=follow,
                        search_hidden=hidden,
                        no_ignore=no_ignore,
                    )
                else:
                    result = probe_directory_rust(
                        path,
                        max_depth,
                        fast_path_only,
                        follow_links=follow,
                        search_hidden=hidden,
                        no_ignore=no_ignore,
                    )

            # Update progress to show completion
            if progress and task_id is not None:
                progress.update(task_id, description="[bold green]Analysis complete!")
                progress.update(task_id, total=100, completed=100)

            # Rust now returns absolute (or canonicalized when follow_links=True) paths,
            # so Python-side normalization is no longer necessary here.

            # If DataFrame building is enabled, we need to collect file paths
            # since the Rust implementation doesn't return them
            if self.build_dataframe and DATAFRAME_AVAILABLE:
                if progress and task_id is not None:
                    progress.update(task_id, description="[bold yellow]Building DataFrame...")

                root_path_obj = Path(path)
                all_paths = []
                permission_errors_encountered = False

                # Collect paths using Python (pathlib) with error handling for system directories
                try:
                    for current_path in root_path_obj.rglob("*"):
                        try:
                            # Calculate current depth
                            depth = len(current_path.relative_to(root_path_obj).parts)

                            # Skip if beyond max depth
                            if max_depth is not None and depth > max_depth:
                                continue

                            all_paths.append(str(current_path))
                        except (ValueError, OSError, PermissionError):
                            # Skip paths that can't be accessed or processed
                            permission_errors_encountered = True
                            continue
                except (OSError, PermissionError, FileNotFoundError):
                    # If rglob fails entirely, provide DataFrame with whatever we collected
                    self.console.print("[yellow]Warning: Some paths couldn't be accessed for DataFrame building[/yellow]")
                    logger.warning(f"DataFrame building encountered permission errors on {path}, providing partial results")
                    permission_errors_encountered = True

                # Add DataFrame to the result (may be partial if there were permission errors)
                result["dataframe"] = DataFrame(all_paths)
                if permission_errors_encountered:
                    # Add a note only if we actually encountered permission errors
                    result["dataframe_note"] = "DataFrame may be incomplete due to permission restrictions"

                if progress and task_id is not None:
                    progress.update(task_id, description="[bold green]DataFrame built!")

            return result

        finally:
            if progress:
                progress.stop()

    def _probe_python(self, path: str, max_depth: Optional[int] = None) -> Dict:
        """
        Pure Python implementation with enhanced DataFrame support and progress indication.
        """
        path_root = Path(path)
        if not path_root.exists():
            raise ValueError(f"Path does not exist: {path_root}")
        if not path_root.is_dir():
            raise ValueError(f"Path is not a directory: {path_root}")

        # Initialize counters and collections
        file_count = 0
        folder_count = 1  # Start with 1 to count the root directory itself
        total_size = 0
        empty_folders = []
        file_extensions = Counter()
        folder_names = Counter()
        files_per_folder = defaultdict(int)
        depth_stats = defaultdict(int)

        # Count the root directory at depth 0
        depth_stats[0] = 1

        # Collection for DataFrame if enabled
        all_paths = [] if self.build_dataframe else None

        # Estimate total items for progress tracking
        progress = None
        task_id = None
        total_items = None
        processed_items = 0

        if self.show_progress:
            # Quick estimation pass
            total_items = sum(1 for _ in path_root.rglob("*"))

            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Analyzing directory structure..."),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed:,}/{task.total:,} items)"),
                TimeElapsedColumn(),
                console=self.console,
                transient=True,
            )
            progress.start()
            task_id = progress.add_task("Analyzing...", total=total_items)

        try:
            # Walk through directory tree using pathlib for consistency
            try:
                for current_path in path_root.rglob("*"):
                    try:
                        processed_items += 1

                        # Update progress
                        if progress and task_id is not None:
                            if processed_items % 100 == 0:  # Update every 100 items for performance
                                progress.update(task_id, completed=processed_items)

                            # Call custom progress callback if provided
                            if self.progress_callback:
                                self.progress_callback(f"Processing: {current_path.name}", processed_items, total_items or 0)

                        # Calculate current depth
                        try:
                            depth = len(current_path.relative_to(path_root).parts)
                        except ValueError:
                            depth = 0

                        # Skip if beyond max depth (match Rust implementation logic)
                        if max_depth is not None:
                            try:
                                if current_path.is_dir() and depth > max_depth:
                                    continue
                                elif current_path.is_file() and depth > max_depth + 1:
                                    continue
                            except (OSError, PermissionError):
                                # Skip paths we can't access for depth checking
                                continue

                        # Add to paths collection if DataFrame is enabled
                        if self.build_dataframe:
                            all_paths.append(str(current_path))

                        try:
                            is_dir = current_path.is_dir()
                            is_file = current_path.is_file()
                        except (OSError, PermissionError):
                            # Skip paths we can't determine type for
                            continue

                        if is_dir:
                            depth_stats[depth] += 1
                            folder_count += 1

                            # Check for empty folders
                            try:
                                if not any(current_path.iterdir()):
                                    empty_folders.append(str(current_path))
                            except (OSError, PermissionError):
                                # Skip directories we can't read
                                pass

                            # Analyze folder names for patterns
                            folder_names[current_path.name] += 1

                        elif is_file:
                            file_count += 1

                            # Count files in parent directory
                            files_per_folder[str(current_path.parent)] += 1

                            # Get file extension
                            ext = current_path.suffix.lower()
                            if ext:
                                file_extensions[ext] += 1
                            else:
                                file_extensions["<no extension>"] += 1

                            # Add to total size
                            try:
                                total_size += current_path.stat().st_size
                            except (OSError, IOError):
                                # Skip files we can't stat (permissions, broken symlinks, etc.)
                                pass

                    except (OSError, PermissionError):
                        # Skip individual files/directories we can't access
                        continue

            except (OSError, PermissionError):
                # If rglob fails entirely, we can't probe this directory
                self.console.print(f"[yellow]Warning: Cannot access directory {path_root} - insufficient permissions[/yellow]")
                # Return minimal result
                return {
                    "path": str(path_root),
                    "summary": {
                        "total_files": 0,
                        "total_folders": 0,
                        "total_size_bytes": 0,
                        "total_size_mb": 0.0,
                        "avg_files_per_folder": 0.0,
                        "max_depth": 0,
                        "empty_folder_count": 0,
                    },
                    "file_extensions": {},
                    "common_folder_names": {},
                    "empty_folders": [],
                    "top_folders_by_file_count": [],
                    "depth_distribution": {},
                    "timing": {"error": "Permission denied"},
                }

            # Final progress update
            if progress and task_id is not None:
                progress.update(task_id, completed=processed_items)

            # Calculate summary statistics
            avg_files_per_folder = file_count / max(1, folder_count)

            # Find folders with most files
            top_folders_by_file_count = sorted(files_per_folder.items(), key=lambda x: x[1], reverse=True)[:10]

            # Build result dictionary
            result = {
                "path": str(path_root),
                "summary": {
                    "total_files": file_count,
                    "total_folders": folder_count,
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                    "avg_files_per_folder": round(avg_files_per_folder, 2),
                    "max_depth": max(depth_stats.keys()) if depth_stats else 0,
                    "empty_folder_count": len(empty_folders),
                },
                "file_extensions": dict(file_extensions.most_common(20)),
                "common_folder_names": dict(folder_names.most_common(20)),
                "empty_folders": empty_folders,
                "top_folders_by_file_count": top_folders_by_file_count,
                "depth_distribution": dict(depth_stats),
            }

            # Add DataFrame if enabled
            if self.build_dataframe and DATAFRAME_AVAILABLE:
                result["dataframe"] = DataFrame(all_paths)

            return result

        finally:
            if progress:
                progress.stop()

    def print_summary(self, analysis: "DirectoryAnalysis"):
        """Print a summary of the directory analysis (expects DirectoryAnalysis)."""
        if not isinstance(analysis, DirectoryAnalysis):
            raise TypeError("print_summary expects a DirectoryAnalysis instance")

        summary = analysis.summary
        timing = analysis.timing or {}

        # Show which implementation was used with more detail
        impl_type = timing.get("implementation", "Unknown")

        # Add DataFrame indicator
        if self.build_dataframe and analysis.dataframe is not None:
            impl_type += " + 📊 DataFrame"

        # Main summary table
        title = f"Directory Analysis: {analysis.path} ({impl_type})"
        if timing:
            title += f" - {timing.get('elapsed_seconds', 0):.2f}s"

        table = Table(title=title)
        table.add_column("Metric", style="bold cyan")
        table.add_column("Value", style="white")

        table.add_row("Total Files", f"{summary['total_files']:,}")
        table.add_row("Total Folders", f"{summary['total_folders']:,}")
        table.add_row("Total Size", f"{summary['total_size_mb']:,} MB")
        table.add_row("Average Files per Folder", str(summary["avg_files_per_folder"]))
        table.add_row("Maximum Depth", str(summary["max_depth"]))
        table.add_row("Empty Folders", str(summary["empty_folder_count"]))

        # Add DataFrame info if available
        if self.build_dataframe and analysis.dataframe is not None:
            df = analysis.dataframe
            table.add_row("DataFrame Rows", f"{len(df):,}")

        # Add timing information if available
        if timing:
            table.add_row("Analysis Time", f"{timing['elapsed_seconds']:.2f}s")
            if timing.get("items_per_second", 0) > 0:
                table.add_row("Processing Speed", f"{timing['items_per_second']:,.0f} items/sec")

        self.console.print(table)
        self.console.print()

    def get_dataframe(self, analysis: "DirectoryAnalysis") -> Optional["DataFrame"]:
        """
        Get the DataFrame from analysis results.

        Args:
            analysis: :class:`DirectoryAnalysis` instance

        Returns:
            DataFrame object if available, None otherwise
        """
        if not isinstance(analysis, DirectoryAnalysis):
            raise TypeError("get_dataframe expects a DirectoryAnalysis instance")
        return analysis.to_df()

    def is_dataframe_enabled(self) -> bool:
        """
        Check if DataFrame building is enabled and available.

        Returns:
            True if DataFrame building is enabled, False otherwise
        """
        return self.build_dataframe and DATAFRAME_AVAILABLE

    def _detect_filesystem_type(self, path: str) -> Optional[str]:
        """
        Attempt to detect the filesystem type for a given path.

        Returns the fs type string (e.g., 'nfs', 'ext4') or None if not detected.
        """
        import os

        try:
            # Parse /proc/mounts for the mount containing the path
            mounts = []
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3:
                        mounts.append((parts[1], parts[2]))  # (mount_point, fs_type)

            # Find best match by longest mount_point prefix
            best = ("", None)
            p = os.path.abspath(path)
            for mnt, fst in mounts:
                if p.startswith(mnt) and len(mnt) > len(best[0]):
                    best = (mnt, fst)

            if best[1]:
                return best[1]

        except Exception:
            pass

        # Fallback: try os.statvfs and map f_fsid is not portable; return None
        return None

    def print_file_extensions(self, analysis: "DirectoryAnalysis", top_n: int = 10):
        """Print the most common file extensions (expects DirectoryAnalysis)."""
        if not isinstance(analysis, DirectoryAnalysis):
            raise TypeError("print_file_extensions expects a DirectoryAnalysis instance")

        extensions = analysis.file_extensions

        if not extensions:
            return

        table = Table(title="File Extensions")
        table.add_column("Extension", style="bold magenta")
        table.add_column("Count", style="white")
        table.add_column("Percentage", style="green")
        total_files = analysis.summary["total_files"]

        for ext, count in list(extensions.items())[:top_n]:
            percentage = (count / total_files * 100) if total_files > 0 else 0
            table.add_row(ext, f"{count:,}", f"{percentage:.1f}%")

        self.console.print(table)
        self.console.print()

    def print_folder_patterns(self, analysis: "DirectoryAnalysis", top_n: int = 10):
        """Print the most common folder names (expects DirectoryAnalysis)."""
        if not isinstance(analysis, DirectoryAnalysis):
            raise TypeError("print_folder_patterns expects a DirectoryAnalysis instance")

        folder_names = analysis.common_folder_names

        if not folder_names:
            return

        table = Table(title="Common Folder Names")
        table.add_column("Folder Name", style="bold blue")
        table.add_column("Occurrences", style="white")

        for name, count in list(folder_names.items())[:top_n]:
            table.add_row(name, f"{count:,}")

        self.console.print(table)
        self.console.print()

    def print_empty_folders(self, analysis: "DirectoryAnalysis", max_show: int = 20):
        """Print empty folders found (expects DirectoryAnalysis)."""
        if not isinstance(analysis, DirectoryAnalysis):
            raise TypeError("print_empty_folders expects a DirectoryAnalysis instance")

        empty_folders = analysis.empty_folders

        if not empty_folders:
            self.console.print("[green]✓ No empty folders found![/green]")
            return

        table = Table(title=f"Empty Folders (showing {min(len(empty_folders), max_show)} of {len(empty_folders)})")
        table.add_column("Path", style="yellow")

        for folder in empty_folders[:max_show]:
            table.add_row(folder)

        if len(empty_folders) > max_show:
            table.add_row(f"... and {len(empty_folders) - max_show} more")

        self.console.print(table)
        self.console.print()

    def print_report(self, analysis: "DirectoryAnalysis"):
        """Print a comprehensive report of the directory analysis.

        Expects a :class:`DirectoryAnalysis` instance. Use :meth:`to_dict`
        if you need a plain dict shape for downstream tooling.
        """
        if not isinstance(analysis, DirectoryAnalysis):
            raise TypeError("print_report expects a DirectoryAnalysis instance")

        self.print_summary(analysis)
        self.print_file_extensions(analysis)
        self.print_folder_patterns(analysis)
        self.print_empty_folders(analysis)
