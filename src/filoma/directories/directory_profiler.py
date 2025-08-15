import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Dict, Optional

from loguru import logger
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

# Try to import the Rust implementation
try:
    from filoma.filoma_core import analyze_directory_rust, analyze_directory_rust_parallel

    RUST_AVAILABLE = True
    RUST_PARALLEL_AVAILABLE = True
except ImportError:
    try:
        from filoma.filoma_core import analyze_directory_rust

        RUST_AVAILABLE = True
        RUST_PARALLEL_AVAILABLE = False
    except ImportError:
        RUST_AVAILABLE = False
        RUST_PARALLEL_AVAILABLE = False

# Import DataFrame for enhanced functionality
try:
    from ..dataframe import DataFrame

    DATAFRAME_AVAILABLE = True
except ImportError:
    DATAFRAME_AVAILABLE = False


class DirectoryProfiler:
    """
    Analyzes directory structures for basic statistics and patterns.
    Provides file counts, folder patterns, empty directories, and extension analysis.

    Can use either a pure Python implementation or a faster Rust implementation
    when available. Supports both sequential and parallel Rust processing.
    """

    def __init__(
        self,
        use_rust: bool = True,
        use_parallel: bool = True,
        parallel_threshold: int = 1000,
        build_dataframe: bool = False,
        show_progress: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        fast_path_only: bool = False,
    ):
        """
        Initialize the directory profiler.

        Args:
            use_rust: Whether to use the Rust implementation when available.
                     Falls back to Python if Rust is not available.
            use_parallel: Whether to use parallel processing in Rust (when available).
                         Only effective when use_rust=True.
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
        self.use_rust = use_rust and RUST_AVAILABLE
        self.use_parallel = use_parallel and RUST_PARALLEL_AVAILABLE and self.use_rust
        self.parallel_threshold = parallel_threshold
        self.build_dataframe = build_dataframe and DATAFRAME_AVAILABLE
        self.show_progress = show_progress
        self.progress_callback = progress_callback
        self._fast_path_only = fast_path_only

        if use_rust and not RUST_AVAILABLE:
            self.console.print("[yellow]Warning: Rust implementation not available, falling back to Python[/yellow]")
        elif use_parallel and self.use_rust and not RUST_PARALLEL_AVAILABLE:
            self.console.print("[yellow]Warning: Rust parallel implementation not available, using sequential Rust[/yellow]")

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

    def get_implementation_info(self) -> Dict[str, bool]:
        """
        Get information about which implementations are available and being used.

        Returns:
            Dictionary with implementation availability status
        """
        return {
            "rust_available": RUST_AVAILABLE,
            "rust_parallel_available": RUST_PARALLEL_AVAILABLE,
            "dataframe_available": DATAFRAME_AVAILABLE,
            "using_rust": self.use_rust,
            "using_parallel": self.use_parallel,
            "using_dataframe": self.build_dataframe,
            "python_fallback": not self.use_rust,
        }

    def analyze_directory(self, root_path: str, max_depth: Optional[int] = None) -> Dict:
        """
        Alias for analyze() method for backward compatibility.

        Args:
            root_path: Path to the root directory to analyze
            max_depth: Maximum depth to traverse (None for unlimited)

        Returns:
            Dictionary containing analysis results
        """
        return self.analyze(root_path, max_depth)

    def analyze(self, root_path: str, max_depth: Optional[int] = None) -> Dict:
        """
        Analyze a directory tree and return comprehensive statistics.

        Args:
            root_path: Path to the root directory to analyze
            max_depth: Maximum depth to traverse (None for unlimited)

        Returns:
            Dictionary containing analysis results
        """
        start_time = time.time()

        # Log the start of analysis
        impl_type = "Rust (Parallel)" if self.use_parallel else "Rust (Sequential)" if self.use_rust else "Python"
        logger.info(f"Starting directory analysis of '{root_path}' using {impl_type} implementation")

        try:
            if self.use_rust:
                result = self._analyze_rust(root_path, max_depth, fast_path_only=self._fast_path_only)
            else:
                result = self._analyze_python(root_path, max_depth)

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

            return result

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Directory analysis failed after {elapsed_time:.2f}s: {str(e)}")
            raise

    def _analyze_rust(self, root_path: str, max_depth: Optional[int] = None, fast_path_only: bool = False) -> Dict:
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
            # Get the main analysis from Rust
            if self.use_parallel and RUST_PARALLEL_AVAILABLE:
                result = analyze_directory_rust_parallel(root_path, max_depth, self.parallel_threshold, fast_path_only)
            else:
                result = analyze_directory_rust(root_path, max_depth, fast_path_only)

            # Update progress to show completion
            if progress and task_id is not None:
                progress.update(task_id, description="[bold green]Analysis complete!")
                progress.update(task_id, total=100, completed=100)

            # If DataFrame building is enabled, we need to collect file paths
            # since the Rust implementation doesn't return them
            if self.build_dataframe and DATAFRAME_AVAILABLE:
                if progress and task_id is not None:
                    progress.update(task_id, description="[bold yellow]Building DataFrame...")

                root_path_obj = Path(root_path)
                all_paths = []

                # Collect paths using Python (pathlib) to match the Python implementation
                for current_path in root_path_obj.rglob("*"):
                    # Calculate current depth
                    try:
                        depth = len(current_path.relative_to(root_path_obj).parts)
                    except ValueError:
                        depth = 0

                    # Skip if beyond max depth
                    if max_depth is not None and depth > max_depth:
                        continue

                    all_paths.append(str(current_path))

                # Add DataFrame to the result
                result["dataframe"] = DataFrame(all_paths)

                if progress and task_id is not None:
                    progress.update(task_id, description="[bold green]DataFrame built!")

            return result

        finally:
            if progress:
                progress.stop()

    def _analyze_python(self, root_path: str, max_depth: Optional[int] = None) -> Dict:
        """
        Pure Python implementation with enhanced DataFrame support and progress indication.
        """
        root_path = Path(root_path)
        if not root_path.exists():
            raise ValueError(f"Path does not exist: {root_path}")
        if not root_path.is_dir():
            raise ValueError(f"Path is not a directory: {root_path}")

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
            total_items = sum(1 for _ in root_path.rglob("*"))

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
            for current_path in root_path.rglob("*"):
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
                    depth = len(current_path.relative_to(root_path).parts)
                except ValueError:
                    depth = 0

                # Skip if beyond max depth (match Rust implementation logic)
                if max_depth is not None:
                    if current_path.is_dir() and depth > max_depth:
                        continue
                    elif current_path.is_file() and depth > max_depth + 1:
                        continue

                # Add to paths collection if DataFrame is enabled
                if self.build_dataframe:
                    all_paths.append(str(current_path))

                if current_path.is_dir():
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
                        # Skip files we can't stat (permissions, broken symlinks, etc.)
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
                "root_path": str(root_path),
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

    def print_summary(self, analysis: Dict):
        """Print a summary of the directory analysis."""
        summary = analysis["summary"]
        timing = analysis.get("timing", {})

        # Show which implementation was used with more detail
        if self.use_rust:
            if self.use_parallel and RUST_PARALLEL_AVAILABLE:
                impl_type = "🦀 Rust (Parallel)"
            else:
                impl_type = "🦀 Rust (Sequential)"
        else:
            impl_type = "🐍 Python"

        # Add DataFrame indicator
        if self.build_dataframe and "dataframe" in analysis:
            impl_type += " + 📊 DataFrame"

        # Main summary table
        title = f"Directory Analysis: {analysis['root_path']} ({impl_type})"
        if timing:
            title += f" - {timing['elapsed_seconds']:.2f}s"

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
        if self.build_dataframe and "dataframe" in analysis:
            df = analysis["dataframe"]
            table.add_row("DataFrame Rows", f"{len(df):,}")

        # Add timing information if available
        if timing:
            table.add_row("Analysis Time", f"{timing['elapsed_seconds']:.2f}s")
            if timing.get("items_per_second", 0) > 0:
                table.add_row("Processing Speed", f"{timing['items_per_second']:,.0f} items/sec")

        self.console.print(table)
        self.console.print()

    def get_dataframe(self, analysis: Dict) -> Optional["DataFrame"]:
        """
        Get the DataFrame from analysis results.

        Args:
            analysis: Analysis results dictionary

        Returns:
            DataFrame object if available, None otherwise
        """
        return analysis.get("dataframe")

    def is_dataframe_enabled(self) -> bool:
        """
        Check if DataFrame building is enabled and available.

        Returns:
            True if DataFrame building is enabled, False otherwise
        """
        return self.build_dataframe and DATAFRAME_AVAILABLE

    def print_file_extensions(self, analysis: Dict, top_n: int = 10):
        """Print the most common file extensions."""
        extensions = analysis["file_extensions"]

        if not extensions:
            return

        table = Table(title="File Extensions")
        table.add_column("Extension", style="bold magenta")
        table.add_column("Count", style="white")
        table.add_column("Percentage", style="green")

        total_files = analysis["summary"]["total_files"]

        for ext, count in list(extensions.items())[:top_n]:
            percentage = (count / total_files * 100) if total_files > 0 else 0
            table.add_row(ext, f"{count:,}", f"{percentage:.1f}%")

        self.console.print(table)
        self.console.print()

    def print_folder_patterns(self, analysis: Dict, top_n: int = 10):
        """Print the most common folder names."""
        folder_names = analysis["common_folder_names"]

        if not folder_names:
            return

        table = Table(title="Common Folder Names")
        table.add_column("Folder Name", style="bold blue")
        table.add_column("Occurrences", style="white")

        for name, count in list(folder_names.items())[:top_n]:
            table.add_row(name, f"{count:,}")

        self.console.print(table)
        self.console.print()

    def print_empty_folders(self, analysis: Dict, max_show: int = 20):
        """Print empty folders found."""
        empty_folders = analysis["empty_folders"]

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

    def print_report(self, analysis: Dict):
        """Print a comprehensive report of the directory analysis."""
        self.print_summary(analysis)
        self.print_file_extensions(analysis)
        self.print_folder_patterns(analysis)
        self.print_empty_folders(analysis)
